#!/usr/bin/env bats
# mk-zek32: cross-lab-review writes a self-contained JSON receipt per PR head.

bats_require_minimum_version 1.5.0

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

@test "verdict mapping: notes pass, FAIL blocks, unknown words are UNKNOWN, no verdict line fails" {
    _review_receipt_prepare "$R"
    printf 'x\n\n**VERDICT: PASS WITH NOTES**\n' > "$OUT"
    [ "$(_review_receipt_verdict "$OUT")" = "PASS WITH NOTES" ]
    printf 'VERDICT: FAIL\n' > "$OUT"
    [ "$(_review_receipt_verdict "$OUT")" = BLOCK ]
    # mk-0qjva: an unlisted word is UNKNOWN (rc 0, warning on stderr), never
    # a pass and never a block.
    for w in APPROVE approve "changes requested" question CLEAN; do
        printf 'VERDICT: %s\n' "$w" > "$OUT"
        run --separate-stderr _review_receipt_verdict "$OUT"
        [ "$status" -eq 0 ]
        [ "$output" = UNKNOWN ]
        [[ "$stderr" == *"unrecognised verdict word"* ]]
    done
    printf 'no verdict here\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf 'VERDICT: PASS\n\nmore prose after\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
    printf '```\nVERDICT: PASS\n' > "$OUT"
    run _review_receipt_verdict "$OUT"; [ "$status" -ne 0 ]
}

@test "verdict mapping: BLOCK is an alias of FAIL, plain and markdown-wrapped" {
    _review_receipt_prepare "$R"
    for line in 'VERDICT: BLOCK' 'verdict: block' '**VERDICT: BLOCK**' '**VERDICT:** BLOCK' '__VERDICT: BLOCK__'; do
        printf 'x\n\n%s\n' "$line" > "$OUT"
        [ "$(_review_receipt_verdict "$OUT")" = BLOCK ]
    done
    for line in 'VERDICT: PASS' '**VERDICT:** PASS' 'Verdict: pass'; do
        printf 'x\n\n%s\n' "$line" > "$OUT"
        [ "$(_review_receipt_verdict "$OUT")" = PASS ]
    done
    printf 'x\n\nVERDICT: BLOCKED\n' > "$OUT"
    run --separate-stderr _review_receipt_verdict "$OUT"
    [ "$status" -eq 0 ]; [ "$output" = UNKNOWN ]
    printf 'x\n\nVERDICT: approve\n' > "$OUT"
    run --separate-stderr _review_receipt_verdict "$OUT"
    [ "$status" -eq 0 ]; [ "$output" = UNKNOWN ]
    [[ "$stderr" == *"accepted: PASS, PASS WITH NOTES, FAIL"* ]]
}

@test "write stores a BLOCK verdict word as BLOCK" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = BLOCK ]
}

@test "blocking verdict suffixes preserve the leading ruling across existing forms" {
    for verdict in BLOCK FAIL; do
        want="$verdict"; [[ "$verdict" != FAIL ]] || want=BLOCK
        for suffix in '' ' (fetch can erase unpushed refs).' ' - explanation' ': explanation' '. Explanation' ' because checks completed' ' (not safe to merge)' ' (tests pass but data loss)'; do
            for line in "VERDICT: $verdict$suffix" "**VERDICT: $verdict$suffix**" "**VERDICT:** $verdict$suffix" "__Verdict: $verdict$suffix__"; do
                printf 'Findings\n\n%s\n' "$line" > "$OUT"
                run _review_receipt_verdict "$OUT"
                [ "$status" -eq 0 ]
                [ "$output" = "$want" ]
            done
        done
    done
}

@test "passing verdicts accept only whitespace and at most one trailing period" {
    for verdict in PASS 'PASS WITH NOTES'; do
        for suffix in '' ' ' '.' '.  '; do
            for line in "VERDICT: $verdict$suffix" "**VERDICT: $verdict$suffix**" "**VERDICT:** $verdict$suffix" "__Verdict: $verdict$suffix__"; do
                printf 'Findings\n\n%s\n' "$line" > "$OUT"
                run _review_receipt_verdict "$OUT"
                [ "$status" -eq 0 ]
                [ "$output" = "$verdict" ]
            done
        done
        for suffix in ' (explanation)' ' - explanation' ': explanation' '. Explanation' '..' ' because checks completed'; do
            printf 'Findings\n\nVERDICT: %s%s\n' "$verdict" "$suffix" > "$OUT"
            run --separate-stderr _review_receipt_verdict "$OUT"
            [ "$status" -eq 0 ]
            [ "$output" = UNKNOWN ]
        done
    done
}

# A pass word with a qualifying suffix is never recorded as a pass. It is
# recorded as UNKNOWN (mk-0qjva): the receipt is written for the audit trail but
# the write returns 3, so the dispatch fails and the review is run again.
_reject_passing_suffix() {
    _review_receipt_prepare "$R"
    rm -rf "$T/reviews"
    for verdict in PASS 'PASS WITH NOTES'; do
        printf 'Findings\n\nVERDICT: %s%s\n' "$verdict" "$1" > "$OUT"
        run --separate-stderr _review_receipt_verdict "$OUT"
        [ "$status" -eq 0 ]
        [ "$output" = UNKNOWN ]
        rm -rf "$T/reviews"
        run --separate-stderr _review_receipt_write "$OUT" 0
        [ "$status" -eq 3 ]
        [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = UNKNOWN ]
    done
}

@test "PASS with blocking findings is recorded as UNKNOWN, never PASS" {
    _reject_passing_suffix ' (two blocking findings)'
}

@test "PASS contradicted by blocked is recorded as UNKNOWN, never PASS" {
    _reject_passing_suffix ' - no, blocked'
}

@test "PASS contradicted by failed tests is recorded as UNKNOWN, never PASS" {
    _reject_passing_suffix ' (tests failed)'
}

@test "PASS with a merge prohibition is recorded as UNKNOWN, never PASS" {
    _reject_passing_suffix " (don't merge)"
}

@test "PASS conditional on fixes is recorded as UNKNOWN, never PASS" {
    _reject_passing_suffix ' (conditional on fixes)'
}

@test "PASS followed by rejection after a period is recorded as UNKNOWN, never PASS" {
    _reject_passing_suffix '. No — REJECTED.'
}

@test "ambiguous or malformed suffixes never yield a passing verdict" {
    for line in 'PASSING' 'PASS WITH' 'PASS WITH CAVEATS' \
        'PASS WITH NOTES OR BLOCK' 'PASS / FAIL' 'PASS (VERDICT: BLOCK)' \
        'PASS if checks succeed' 'PASS unless tests fail' 'PASS, pending checks' \
        'PASS but changes required' 'PASS (not approved)' 'PASS or BLOCK'; do
        printf 'Findings\n\nVERDICT: %s\n' "$line" > "$OUT"
        run --separate-stderr _review_receipt_verdict "$OUT"
        [ "$status" -eq 0 ]
        [ "$output" = UNKNOWN ]
    done
}

@test "write records suffixed rulings and records ambiguous ones as UNKNOWN" {
    _review_receipt_prepare "$R"
    sequence=1
    for verdict in BLOCK FAIL; do
        printf 'Findings\n\nVERDICT: %s (explanation).\n' "$verdict" > "$OUT"
        _review_receipt_write "$OUT" 0
        receipt="$T/reviews/o__r/7-$HEAD_SHA.json"
        [[ "$sequence" -eq 1 ]] || receipt="$T/reviews/o__r/7-$HEAD_SHA.$sequence.json"
        want="$verdict"; [[ "$verdict" != FAIL ]] || want=BLOCK
        [ "$(jq -r .verdict "$receipt")" = "$want" ]
        sequence=$((sequence + 1))
    done
    printf 'Findings\n\nVERDICT: PASS / BLOCK\n' > "$OUT"
    run --separate-stderr _review_receipt_write "$OUT" 0
    [ "$status" -eq 3 ]
    [ "$(find "$T/reviews" -name '*.json' | wc -l)" -eq 3 ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.3.json")" = UNKNOWN ]
}

@test "cleanup preserves successful process status when a suffixed BLOCK receipt is written" {
    _review_receipt_prepare "$R"
    source <(awk '/^_dispatch_cleanup_state\(\)/ { emit=1 } emit { print; if ($0 == "}") exit }' "$DISPATCH")
    _review_scratch_cleanup() { :; }
    ROLE_RESOLVED=true ROLE=cross-lab-review OUTPUT="$OUT" STATE_FILE="$T/state"
    printf 'Findings\n\nVERDICT: BLOCK (fetch can erase unpushed refs).\n' > "$OUT"
    true
    _dispatch_cleanup_state
    [ "$DISPATCH_FINAL_RC" -eq 0 ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = BLOCK ]
}

@test "cleanup still fails a successful process when its verdict is ambiguous" {
    _review_receipt_prepare "$R"
    source <(awk '/^_dispatch_cleanup_state\(\)/ { emit=1 } emit { print; if ($0 == "}") exit }' "$DISPATCH")
    _review_scratch_cleanup() { :; }
    ROLE_RESOLVED=true ROLE=cross-lab-review OUTPUT="$OUT" STATE_FILE="$T/state"
    printf 'Findings\n\nVERDICT: PASS / BLOCK\n' > "$OUT"
    true
    _dispatch_cleanup_state
    [ "$DISPATCH_FINAL_RC" -eq 1 ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = UNKNOWN ]
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

@test "unrecognised verdict word writes an UNKNOWN receipt and fails the write" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: APPROVE\n' > "$OUT"
    run --separate-stderr _review_receipt_write "$OUT" 0
    [ "$status" -eq 3 ]
    [[ "$stderr" == *"unrecognised verdict word 'APPROVE'"* ]]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .verdict "$f")" = UNKNOWN ]
    [ "$(jq -r .verdict_raw "$f")" = APPROVE ]
}

@test "a missing VERDICT line still writes no receipt" {
    _review_receipt_prepare "$R"
    printf 'no verdict here\n' > "$OUT"
    run _review_receipt_write "$OUT" 0
    [ "$status" -ne 0 ]; [ "$status" -ne 3 ]
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

@test "write records parsed findings, classes and sorted changed paths" {
    printf '### [P1] [test-gap] Missing empty case in `scripts/a.sh:42`\n### P2 [made-up] unlisted class\n\nVERDICT: FAIL\n' > "$OUT"
    _review_receipt_prepare "$R"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .schema_version "$f")" = 1 ]
    [ "$(jq -r .findings_source "$f")" = body ]
    [ "$(jq -r .findings_total "$f")" = 2 ]
    [ "$(jq -r '.findings[0].class' "$f")" = test-gap ]
    [ "$(jq -r '.findings[0].file' "$f")" = scripts/a.sh ]
    [ "$(jq -r '.findings[0].line' "$f")" = 42 ]
    [ "$(jq -r '.findings[1].class' "$f")" = other ]
    [ "$(jq -c .changed_paths "$f")" = '["b"]' ]
    [ "$(jq -r 'has("changed_paths_truncated")' "$f")" = false ]
}

@test "write records unknown, not zero, when no findings parse" {
    printf 'Looks fine to me, some prose.\n\nVERDICT: PASS WITH NOTES\n' > "$OUT"
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .findings_source "$f")" = unknown ]
    [ "$(jq -r .findings_total "$f")" = null ]
    [ "$(jq -c .findings "$f")" = '[]' ]
}

@test "changed_paths is capped at 200 and flagged truncated" {
    for i in $(seq 1 205); do echo x > "$R/f$i"; done
    git -C "$R" add -A; git -C "$R" commit -qm many
    RR_HEAD="$(git -C "$R" rev-parse HEAD)"
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    f="$T/reviews/o__r/7-$RR_HEAD.json"
    [ "$(jq '.changed_paths|length' "$f")" = 200 ]
    [ "$(jq -r .changed_paths_truncated "$f")" = true ]
    [ "$(jq -c '.changed_paths == (.changed_paths|sort)' "$f")" = true ]
}

@test "changed_paths keeps a filename with an embedded newline as one path" {
    printf 'x\n' > "$R/$(printf 'qq\nrr')"
    echo y > "$R/plain"
    git -C "$R" add -A; git -C "$R" commit -qm nl
    RR_HEAD="$(git -C "$R" rev-parse HEAD)"
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    f="$T/reviews/o__r/7-$RR_HEAD.json"
    [ "$(jq -r '.changed_paths | index("plain") != null' "$f")" = true ]
    [ "$(jq -r '.changed_paths | index("qq\nrr") != null' "$f")" = true ]
    [ "$(jq -r '.changed_paths | index("qq") == null and index("rr") == null' "$f")" = true ]
}

@test "a 140000-byte changed-path list still writes a receipt capped at 200" {
    pad="$(printf 'p%.0s' $(seq 1 230))"
    for i in $(seq 1 610); do echo x > "$R/${pad}$(printf '%04d' "$i")"; done
    git -C "$R" add -A; git -C "$R" commit -qm big
    RR_HEAD="$(git -C "$R" rev-parse HEAD)"
    [ "$(git -C "$R" diff --name-only HEAD~1 HEAD | wc -c)" -gt 140000 ]
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    f="$T/reviews/o__r/7-$RR_HEAD.json"
    [ "$(jq '.changed_paths|length' "$f")" = 200 ]
    [ "$(jq -r .changed_paths_truncated "$f")" = true ]
}

@test "old receipts without the new fields and new receipts coexist and read the same" {
    # No other receipt reader lives in this repo; the verifier is outside it and
    # reads the unchanged fields by name. Check the old fields are identical in
    # both shapes, and that the append path accepts an old receipt already there.
    _review_receipt_prepare "$R"
    _review_receipt_write "$OUT" 0
    new="$T/reviews/o__r/7-$HEAD_SHA.json"
    old="$T/old.json"
    jq 'del(.findings,.findings_source,.findings_total,.changed_paths,.changed_paths_truncated)' "$new" > "$old"
    cp "$old" "$new"   # an old-format receipt now holds the first slot
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    n2="$T/reviews/o__r/7-$HEAD_SHA.2.json"
    [ "$(jq -S 'del(.created_at,.sequence,.supersedes,.supersedes_verdict,.verdict_raw,.findings,.findings_source,.findings_total,.changed_paths,.changed_paths_truncated)' "$n2")" = \
      "$(jq -S 'del(.created_at,.sequence,.verdict_raw)' "$old")" ]
    for f in "$new" "$n2"; do
        [ "$(jq -r '.schema_version' "$f")" = 1 ]
        [ "$(jq -r '.verdict' "$f")" = PASS ]
    done
}

@test "cross-lab-review prompt documents the class tag" {
    grep -q '\[P1\] \[test-gap\]' "$DISPATCH"
    grep -q 'process-gate (CI, hooks, instruction files)' "$DISPATCH"
}

@test "a 900-finding review (over 200000 bytes of findings JSON) still writes a receipt" {
    pad="$(printf 'w%.0s' $(seq 1 190))"
    { for i in $(seq 1 900); do printf '### [P2] [other] finding %04d %s in `scripts/a.sh:%d`\n' "$i" "$pad" "$i"; done
      printf '\nVERDICT: FAIL\n'; } > "$OUT"
    [ "$(python3 "$BATS_TEST_DIRNAME/../../scripts/receipt-findings.py" --detail "$OUT" | wc -c)" -gt 200000 ]
    _review_receipt_prepare "$R"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .findings_total "$f")" = 900 ]
    [ "$(jq '.findings|length' "$f")" = 200 ]
    [ "$(jq -r .findings_truncated "$f")" = true ]
    [ "$(jq -r .findings_source "$f")" = body ]
    [ "$(jq -r .verdict "$f")" = BLOCK ]
}

@test "a stale FINDINGS: 0 block with a parsed heading records a conflict, not zero" {
    printf '### [P1] [test-gap] Missing case in `scripts/a.sh:4`\n\n--- VERDICT ---\nSTATUS: revise\nFINDINGS: 0 (P0: 0, P1: 0, P2: 0)\n---\n\nVERDICT: FAIL\n' > "$OUT"
    _review_receipt_prepare "$R"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .findings_source "$f")" = conflict ]
    [ "$(jq -r .findings_total "$f")" = 1 ]
    [ "$(jq -r .findings_block_total "$f")" = 0 ]
    [ "$(jq '.findings|length' "$f")" = 1 ]
    [ "$(jq -r .verdict "$f")" = BLOCK ]
}

@test "a block claiming more findings than parsed headings records a conflict" {
    printf '### [P1] [test-gap] one heading\n\n--- VERDICT ---\nSTATUS: revise\nFINDINGS: 3 (P0: 0, P1: 2, P2: 1)\n---\n\nVERDICT: FAIL\n' > "$OUT"
    _review_receipt_prepare "$R"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .findings_source "$f")" = conflict ]
    [ "$(jq -r .findings_total "$f")" = 1 ]
    [ "$(jq -r .findings_block_total "$f")" = 3 ]
}

# --- mk-0qjva, mk-4c909, mk-8m912, mk-0ud4q, mk-n37ml: shared verdict words,
# --- UNKNOWN recording, append-only supersession ---------------------------

@test "PASS-WITH-NOTES and PASS_WITH_NOTES are recorded as PASS WITH NOTES" {
    _review_receipt_prepare "$R"
    for w in PASS-WITH-NOTES PASS_WITH_NOTES pass-with-notes; do
        printf 'x\n\nVERDICT: %s\n' "$w" > "$OUT"
        [ "$(_review_receipt_verdict "$OUT")" = "PASS WITH NOTES" ]
    done
    printf 'x\n\n**VERDICT: PASS-WITH-NOTES**\n' > "$OUT"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = "PASS WITH NOTES" ]
}

@test "an unknown word is UNKNOWN with verdict_raw and a warning, not BLOCK" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: APPROVE\n' > "$OUT"
    run --separate-stderr _review_receipt_write "$OUT" 0
    [ "$status" -eq 3 ]
    [[ "$stderr" == *"Recorded as UNKNOWN, not as a pass or a block"* ]]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r .verdict "$f")" = UNKNOWN ]
    [ "$(jq -r .verdict_raw "$f")" = APPROVE ]
    [ "$(jq -r .verdict "$f")" != BLOCK ]
}

@test "verdict_raw is the cleaned verdict word for every verdict" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .verdict_raw "$T/reviews/o__r/7-$HEAD_SHA.json")" = PASS ]
    printf 'x\n\nVERDICT: BLOCK (data loss)\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .verdict_raw "$T/reviews/o__r/7-$HEAD_SHA.2.json")" = "BLOCK (data loss)" ]
}

@test "verdict_raw drops control characters and is capped at 120 characters" {
    _review_receipt_prepare "$R"
    long="$(printf 'z%.0s' $(seq 1 300))"
    printf 'x\n\nVERDICT: %s\n' "$long" > "$OUT"
    run --separate-stderr _review_receipt_write "$OUT" 0
    [ "$status" -eq 3 ]
    raw="$(jq -r .verdict_raw "$T/reviews/o__r/7-$HEAD_SHA.json")"
    [ "${#raw}" -le 120 ]
    [[ "$raw" =~ ^z+$ ]]
}

@test "a later receipt at the same head supersedes the earlier one and keeps it" {
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: APPROVE\n' > "$OUT"
    run --separate-stderr _review_receipt_write "$OUT" 0
    [ "$status" -eq 3 ]
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    d="$T/reviews/o__r"
    # The first record is untouched.
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.json")" = UNKNOWN ]
    [ "$(jq -r '.supersedes // "none"' "$d/7-$HEAD_SHA.json")" = none ]
    # The second names the record it supersedes and what that said.
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.2.json")" = PASS ]
    [ "$(jq -r .sequence "$d/7-$HEAD_SHA.2.json")" = 2 ]
    [ "$(jq -r .supersedes "$d/7-$HEAD_SHA.2.json")" = "7-$HEAD_SHA.json" ]
    [ "$(jq -r .supersedes_verdict "$d/7-$HEAD_SHA.2.json")" = UNKNOWN ]
    # The third chains to the second.
    printf 'x\n\nVERDICT: PASS WITH NOTES\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .supersedes "$d/7-$HEAD_SHA.3.json")" = "7-$HEAD_SHA.2.json" ]
    [ "$(jq -r .supersedes_verdict "$d/7-$HEAD_SHA.3.json")" = PASS ]
}

@test "sequences count insertion order and each same-scope receipt chains to the last" {
    _review_receipt_prepare "$R"
    d="$T/reviews/o__r"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: FAIL\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .sequence "$d/7-$HEAD_SHA.json")" = 1 ]
    [ "$(jq -r .sequence "$d/7-$HEAD_SHA.2.json")" = 2 ]
    [ "$(jq -r .sequence "$d/7-$HEAD_SHA.3.json")" = 3 ]
    [ "$(jq -r .supersedes "$d/7-$HEAD_SHA.3.json")" = "7-$HEAD_SHA.2.json" ]
    [ "$(jq -r .supersedes_verdict "$d/7-$HEAD_SHA.3.json")" = BLOCK ]
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.3.json")" = PASS ]
}

@test "a real BLOCK stays on disk and is never rewritten by a later PASS" {
    _review_receipt_prepare "$R"
    d="$T/reviews/o__r"
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    before="$(sha256sum "$d/7-$HEAD_SHA.json" | cut -d' ' -f1)"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(sha256sum "$d/7-$HEAD_SHA.json" | cut -d' ' -f1)" = "$before" ]
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.json")" = BLOCK ]
    # The supersession is visible to an auditor: the PASS says it replaced a BLOCK.
    [ "$(jq -r .supersedes_verdict "$d/7-$HEAD_SHA.2.json")" = BLOCK ]
}

@test "a BLOCK written after a PASS is recorded as BLOCK and names the PASS it follows" {
    _review_receipt_prepare "$R"
    d="$T/reviews/o__r"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.2.json")" = BLOCK ]
    [ "$(jq -r .supersedes_verdict "$d/7-$HEAD_SHA.2.json")" = PASS ]
}

# Design choice (mk-0qjva): a receipt supersedes an earlier one only when it
# reviewed the same base and the same diff. A review of different content is a
# receipt in its own right and clears nothing.
@test "a receipt for a different base and diff supersedes nothing and leaves a BLOCK in force" {
    _review_receipt_prepare "$R"
    d="$T/reviews/o__r"
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    before="$(sha256sum "$d/7-$HEAD_SHA.json" | cut -d' ' -f1)"
    # base == head: an empty reviewed diff, the case the round-1 review reproduced.
    RR_BASE="$HEAD_SHA"
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    run _review_receipt_write "$OUT" 0
    [ "$status" -eq 0 ]
    f="$d/7-$HEAD_SHA.2.json"
    [ "$(jq -r .verdict "$f")" = PASS ]
    [ "$(jq -r .sequence "$f")" = 2 ]
    [ "$(jq -r '.supersedes // "none"' "$f")" = none ]
    [ "$(jq -r '.supersedes_verdict // "none"' "$f")" = none ]
    [ "$(jq -r .base_sha "$f")" = "$HEAD_SHA" ]
    # The original BLOCK is byte-identical and still names no predecessor.
    [ "$(sha256sum "$d/7-$HEAD_SHA.json" | cut -d' ' -f1)" = "$before" ]
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.json")" = BLOCK ]
}

@test "same base but a different diff does not supersede; the nearest same-scope receipt does" {
    d="$T/reviews/o__r"
    echo c > "$R/c"; git -C "$R" add c; git -C "$R" commit -qm c
    NEW_HEAD="$(git -C "$R" rev-parse HEAD)"
    RR_HEAD="$NEW_HEAD"
    # Scope A (base = BASE): BLOCK.
    RR_BASE="$BASE"; _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    # Scope B (base = the previous head, a different diff): PASS.
    RR_BASE="$HEAD_SHA"; _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r '.supersedes // "none"' "$d/7-$NEW_HEAD.2.json")" = none ]
    # Scope A again: PASS. It supersedes the scope A BLOCK, skipping the scope B PASS.
    RR_BASE="$BASE"; _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS WITH NOTES\n' > "$OUT"
    _review_receipt_write "$OUT" 0
    [ "$(jq -r .sequence "$d/7-$NEW_HEAD.3.json")" = 3 ]
    [ "$(jq -r .supersedes "$d/7-$NEW_HEAD.3.json")" = "7-$NEW_HEAD.json" ]
    [ "$(jq -r .supersedes_verdict "$d/7-$NEW_HEAD.3.json")" = BLOCK ]
}

@test "effective receipt: the latest receipt in the base+diff chain, from any member" {
    d="$T/reviews/o__r"
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"; _review_receipt_write "$OUT" 0
    [ "$(_review_receipt_effective "$d/7-$HEAD_SHA.json")" = "$d/7-$HEAD_SHA.json" ]
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"; _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: PASS WITH NOTES\n' > "$OUT"; _review_receipt_write "$OUT" 0
    [ "$(_review_receipt_effective "$d/7-$HEAD_SHA.json")" = "$d/7-$HEAD_SHA.3.json" ]
    [ "$(_review_receipt_effective "$d/7-$HEAD_SHA.2.json")" = "$d/7-$HEAD_SHA.3.json" ]
    # The original is preserved.
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.json")" = BLOCK ]
}

@test "effective receipt: a receipt for a different base and diff is not part of the chain" {
    d="$T/reviews/o__r"
    echo c > "$R/c"; git -C "$R" add c; git -C "$R" commit -qm c
    NEW_HEAD="$(git -C "$R" rev-parse HEAD)"
    RR_HEAD="$NEW_HEAD"
    RR_BASE="$BASE"; _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"; _review_receipt_write "$OUT" 0
    RR_BASE="$HEAD_SHA"; _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"; _review_receipt_write "$OUT" 0
    # The later PASS reviewed a different diff, so the BLOCK stays effective.
    [ "$(_review_receipt_effective "$d/7-$NEW_HEAD.json")" = "$d/7-$NEW_HEAD.json" ]
}

@test "effective receipt: a gapped chain (no .2) returns .3 when called from the original" {
    d="$T/reviews/o__r"
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"; _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"; _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"; _review_receipt_write "$OUT" 0
    rm "$d/7-$HEAD_SHA.2.json"
    [ "$(jq -r .verdict "$d/7-$HEAD_SHA.3.json")" = BLOCK ]
    [ "$(_review_receipt_effective "$d/7-$HEAD_SHA.json")" = "$d/7-$HEAD_SHA.3.json" ]
}

@test "effective receipt: a gapped chain (no .2) returns .3 when called from .3" {
    d="$T/reviews/o__r"
    _review_receipt_prepare "$R"
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"; _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: PASS\n' > "$OUT"; _review_receipt_write "$OUT" 0
    printf 'x\n\nVERDICT: BLOCK\n' > "$OUT"; _review_receipt_write "$OUT" 0
    rm "$d/7-$HEAD_SHA.2.json"
    [ "$(_review_receipt_effective "$d/7-$HEAD_SHA.3.json")" = "$d/7-$HEAD_SHA.3.json" ]
}

@test "effective receipt: refuses a missing file, a symlink and a non-receipt" {
    d="$T/reviews/o__r"; mkdir -p "$d"
    run _review_receipt_effective "$d/none.json"; [ "$status" -ne 0 ]
    echo '{}' > "$d/x.json"; ln -s x.json "$d/link.json"
    run _review_receipt_effective "$d/link.json"; [ "$status" -ne 0 ]
    run _review_receipt_effective "$d/x.json"; [ "$status" -ne 0 ]
}

@test "the receipt library header tells readers to follow the numbered chain" {
    grep -q 'follow the numbered chain' "$BATS_TEST_DIRNAME/../../scripts/lib-review-receipt.sh"
    ! grep -q '_review_receipt_current' "$BATS_TEST_DIRNAME/../../scripts/lib-review-receipt.sh"
}

@test "cleanup fails a successful process on an UNKNOWN verdict, never as BLOCK" {
    _review_receipt_prepare "$R"
    source <(awk '/^_dispatch_cleanup_state\(\)/ { emit=1 } emit { print; if ($0 == "}") exit }' "$DISPATCH")
    _review_scratch_cleanup() { :; }
    ROLE_RESOLVED=true ROLE=cross-lab-review OUTPUT="$OUT" STATE_FILE="$T/state"
    printf 'Findings\n\nVERDICT: APPROVE\n' > "$OUT"
    true
    _dispatch_cleanup_state 2>/dev/null
    [ "$DISPATCH_FINAL_RC" -eq 1 ]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = UNKNOWN ]
}

@test "cross-lab prompt says an unknown word is recorded as UNKNOWN and the review rerun" {
    grep -q 'any other word is recorded' "$DISPATCH"
    grep -q 'as UNKNOWN, which is neither a pass nor a block' "$DISPATCH"
    ! grep -q 'fails the dispatch without a receipt' "$DISPATCH"
}
