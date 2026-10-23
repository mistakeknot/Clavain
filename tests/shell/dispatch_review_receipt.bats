#!/usr/bin/env bats
# mk-zek32: cross-lab-review writes a self-contained JSON receipt per PR head.

setup() {
    load test_helper
    T="$(mktemp -d)"
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    # shellcheck disable=SC1090
    source "$BATS_TEST_DIRNAME/../../scripts/lib-review-receipt.sh"
    R="$T/repo"; git init -q -b main "$R"
    git -C "$R" config user.email t@t; git -C "$R" config user.name t
    echo a > "$R/a"; git -C "$R" add a; git -C "$R" commit -qm base
    BASE="$(git -C "$R" rev-parse HEAD)"
    echo b > "$R/b"; git -C "$R" add b; git -C "$R" commit -qm head
    HEAD_SHA="$(git -C "$R" rev-parse HEAD)"
    export CLAVAIN_REVIEW_RECEIPT_DIR="$T/reviews"
    RR_REPO=o/r RR_REPO_ID=R_abc123 RR_PR=7 RR_HEAD="$HEAD_SHA" RR_BASE="$BASE"
    PRODUCER_IDENTITY=claude-sonnet-5-5 MODEL=gpt-6.1-sol CAPACITY_SUBSTITUTE_JSON=""
    DISPATCH_ID=d1 ATTEMPT_ID=a1 VALIDATOR_RELATIONSHIP=different-model
    RESOLVED_ROUTE_JSON="{\"policy_hash\":\"$(printf 'a%.0s' {1..64})\"}"
    OUT="$T/out.md"; printf 'Findings: none\n\nVERDICT: PASS\n' > "$OUT"
}
teardown() { rm -rf "$T"; }

@test "prepare derives the diff hash from the raw git diff bytes" {
    _review_receipt_prepare "$R"
    want="$(git -C "$R" diff --no-ext-diff --no-renames --binary "$BASE" "$HEAD_SHA" | sha256sum | cut -d' ' -f1)"
    [ "$RR_DIFF_SHA256" = "$want" ]
    [ "$RR_HEAD_TREE" = "$(git -C "$R" rev-parse "$HEAD_SHA^{tree}")" ]
}

@test "prepare rejects a missing flag, a short sha and an unknown commit" {
    RR_PR=""; run _review_receipt_prepare "$R"; [ "$status" -ne 0 ]
    RR_PR=7; RR_HEAD="${HEAD_SHA:0:12}"; run _review_receipt_prepare "$R"; [ "$status" -ne 0 ]
    RR_HEAD="$(printf 'b%.0s' {1..40})"; run _review_receipt_prepare "$R"; [ "$status" -ne 0 ]
}

@test "write produces a 0600 self-contained receipt" {
    _review_receipt_prepare "$R"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(stat -c %a "$f")" = 600 ]
    [ "$(jq -r .role "$f")" = cross-lab-review ]
    [ "$(jq -r .verdict "$f")" = PASS ]
    [ "$(jq -r .head_sha "$f")" = "$HEAD_SHA" ]
    [ "$(jq -r .diff_sha256 "$f")" = "$RR_DIFF_SHA256" ]
    [ "$(jq -r .reviewer_identity "$f")" = gpt-6.1-sol ]
    [ "$(jq -r .pr "$f")" = 7 ]
}

@test "a second write for the same head never overwrites" {
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    printf 'VERDICT: FAIL\n' > "$OUT"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = PASS ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.2.json")" = BLOCK ]
}

@test "verdict mapping: notes pass, FAIL blocks, unknown words and none write nothing" {
    _review_receipt_prepare "$R"
    printf 'x\n\n**VERDICT: PASS WITH NOTES**\n' > "$OUT"
    [ "$(_review_receipt_verdict "$OUT")" = "PASS WITH NOTES" ]
    printf 'VERDICT: FAIL\n' > "$OUT"
    [ "$(_review_receipt_verdict "$OUT")" = BLOCK ]
    for w in APPROVE BLOCK "changes requested" question CLEAN; do
        printf 'VERDICT: %s\n' "$w" > "$OUT"
        run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    done
    printf 'no verdict here\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf 'VERDICT: PASS\n\nmore prose after\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf '```\nVERDICT: PASS\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
}

@test "no receipt for same-lab, substitute, failed or hashless runs" {
    _review_receipt_prepare "$R"
    MODEL=claude-opus-5-5; run _review_receipt_write "$OUT" 0; [ "$status" -ne 0 ]
    MODEL=gpt-6.1-sol; CAPACITY_SUBSTITUTE_JSON='{"x":1}'; run _review_receipt_write "$OUT" 0; [ "$status" -ne 0 ]
    CAPACITY_SUBSTITUTE_JSON=""; run _review_receipt_write "$OUT" 1; [ "$status" -ne 0 ]
    RESOLVED_ROUTE_JSON='{}'; run _review_receipt_write "$OUT" 0; [ "$status" -ne 0 ]
    [ ! -e "$T/reviews/o__r/7-$HEAD_SHA.json" ]
}

@test "dispatch rejects the receipt flags on other roles and partial sets" {
    run bash "$DISPATCH" --role validation --producer-identity x --repo o/r --prompt hi
    [ "$status" -ne 0 ]
    run bash "$DISPATCH" --role cross-lab-review --producer-identity x --repo o/r --prompt hi
    [ "$status" -ne 0 ]
    [[ "$output" == *"--repo-id"* ]]
}

@test "prepare rejects conflicting merges" {
    git -C "$R" checkout -q -b other "$BASE"
    echo x > "$R/a"; git -C "$R" commit -qam x
    X="$(git -C "$R" rev-parse HEAD)"
    git -C "$R" checkout -q main
    git -C "$R" checkout -q -b y "$BASE"; echo y > "$R/a"; git -C "$R" commit -qam y
    Y="$(git -C "$R" rev-parse HEAD)"
    RR_BASE="$X" RR_HEAD="$Y"; run _review_receipt_prepare "$R"
    [ "$status" -ne 0 ]
}

@test "diff hash ignores textconv and rejects a failed diff" {
    printf '*.bin diff=bad\n' > "$R/.gitattributes"
    echo 1 > "$R/f.bin"; git -C "$R" add -A; git -C "$R" commit -qm bin
    git -C "$R" config diff.bad.textconv false
    RR_HEAD="$(git -C "$R" rev-parse HEAD)"
    _review_receipt_prepare "$R"
    [ "$RR_DIFF_SHA256" != e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 ]
}

@test "verdict: fences, HTML comments, quotes and indentation never yield a receipt" {
    for body in '```\nx\n```\n\nVERDICT: PASS\n' '~~~\n\nVERDICT: PASS\n' '```text\n    ```\n\nVERDICT: PASS\n' \
        '<!-- example\n--> <!--\n\nVERDICT: PASS\n' '<!--\n\nVERDICT: PASS\n' '<!-- n -->\n\nVERDICT: PASS\n' \
        '> VERDICT: PASS\n' '    VERDICT: PASS\n' '> Quoted:\nVERDICT: PASS\n' 'Notes\nVERDICT: PASS\n' \
        '- ```text\n  VERDICT: PASS\n'; do
        printf -- "$body" > "$OUT"; run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    done
    printf '> Quoted\n\nVERDICT: PASS\n' > "$OUT"; [ "$(_review_receipt_verdict "$OUT")" = PASS ]
    printf '**VERDICT: PASS WITH NOTES**\n' > "$OUT"; [ "$(_review_receipt_verdict "$OUT")" = "PASS WITH NOTES" ]
}

@test "write refuses an existing directory or directory symlink at the receipt path" {
    _review_receipt_prepare "$R"
    mkdir -p "$T/reviews/o__r" "$T/elsewhere"
    mkdir "$T/reviews/o__r/7-$HEAD_SHA.json"
    run _review_receipt_write "$OUT" 0; [ "$status" -ne 0 ]
    rmdir "$T/reviews/o__r/7-$HEAD_SHA.json"
    ln -s "$T/elsewhere" "$T/reviews/o__r/7-$HEAD_SHA.json"
    run _review_receipt_write "$OUT" 0; [ "$status" -ne 0 ]
    [ -z "$(find "$T/elsewhere" "$T/reviews/o__r" -name '.new.*')" ]
    [ -z "$(ls -A "$T/elsewhere")" ]
}

@test "write refuses to go through an existing symlink" {
    _review_receipt_prepare "$R"
    mkdir -p "$T/reviews/o__r"; ln -s /dev/null "$T/reviews/o__r/7-$HEAD_SHA.json"
    run _review_receipt_write "$OUT" 0
    [ "$status" -ne 0 ]
    ls "$T/reviews/o__r" | grep -vq '^\.' || true
    [ -z "$(find "$T/reviews/o__r" -name '.new.*')" ]
}

@test "verdict: NUL bytes and delimiter-scan errors never yield a receipt" {
    printf 'Findings\n\nVERDICT: P\000ASS\n' > "$OUT"; run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf '\000VERDICT: PASS\n' > "$OUT"; run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf '```\nx\n\nVERDICT: PASS\n' > "$OUT"
    grep() { return 2; }
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    unset -f grep
    printf 'Findings\n\nVERDICT: P\000ASS\n' > "$OUT"
    wc() { return 127; }
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    unset -f wc
    cmp() { return 127; }
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf 'ok\n\nVERDICT: PASS\n' > "$OUT"; run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    unset -f cmp
}

@test "verdict: awk and tr exit statuses fail closed" {
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"
    awk() { printf 'VERDICT: PASS\n'; return 2; }
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    unset -f awk
    tr() { command tr "$@"; return 2; }
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    unset -f tr
    run _review_receipt_verdict "$OUT"; [ "$status" -eq 0 ]
}

@test "unrecognised verdict word writes no receipt" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: APPROVE\n' > "$OUT"
    run _review_receipt_write "$OUT" 0; [ "$status" -ne 0 ]
    [[ "$output" == *"VERDICT"* ]]
    [ -z "$(ls -A "$T/reviews/o__r" 2>/dev/null)" ]
}

@test "a second receipt for the same head is appended, never overwritten" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: FAIL\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    _review_receipt_write "$OUT" 0
    d="$T/reviews/o__r"
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.json")" = BLOCK ]
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.2.json")" = PASS ]
    [ -f "$d/7-$HEAD_SHA.3.json" ]
    [ "$(jq -r .sequence "$d/7-$HEAD_SHA.json")" = 1 ]
    [ "$(jq -r .sequence "$d/7-$HEAD_SHA.3.json")" = 3 ]
}

@test "concurrent writers for one head each get a distinct receipt and sequence" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    for i in 1 2 3 4 5 6 7 8; do ( _review_receipt_write "$OUT" 0 ) 2>/dev/null & done
    wait
    d="$T/reviews/o__r"
    [ "$(ls "$d"/7-"$HEAD_SHA"*.json | wc -l)" -eq 8 ]
    [ "$(jq -r .sequence "$d"/7-"$HEAD_SHA"*.json | sort -n | uniq | wc -l)" -eq 8 ]
}

@test "a dangling symlink at the next numbered path is refused" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    d="$T/reviews/o__r"
    ln -s /nonexistent "$d/7-$HEAD_SHA.2.json"
    run _review_receipt_write "$OUT" 0
    [ "$status" -ne 0 ]
    [ ! -e "$d/7-$HEAD_SHA.3.json" ]
}

@test "write stops at the 999th receipt and leaves no temp file" {
    _review_receipt_prepare "$R"
    d="$T/reviews/o__r"; mkdir -p "$d"
    : > "$d/7-$HEAD_SHA.json"
    for i in $(seq 2 999); do : > "$d/7-$HEAD_SHA.$i.json"; done
    run _review_receipt_write "$OUT" 0
    [ "$status" -ne 0 ]
    [ ! -e "$d/7-$HEAD_SHA.1000.json" ]
    [ -z "$(ls -A "$d" | grep '^\.new\.')" ]
}

@test "write refuses a fifo at the next numbered path" {
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    d="$T/reviews/o__r"
    mkfifo "$d/7-$HEAD_SHA.2.json"
    run _review_receipt_write "$OUT" 0
    [ "$status" -ne 0 ]
    [ ! -e "$d/7-$HEAD_SHA.3.json" ]
}

@test "dispatch cross-lab-review prompt names the accepted verdict words" {
    line="$(grep -n 'of: .*VERDICT: PASS.*VERDICT: FAIL' "$DISPATCH" | head -1)"
    [ -n "$line" ]
    [[ "$line" == *'\"VERDICT: PASS\"'* ]]
    [[ "$line" == *'\"VERDICT: PASS WITH NOTES\"'* ]]
    [[ "$line" == *'\"VERDICT: FAIL\"'* ]]
}
