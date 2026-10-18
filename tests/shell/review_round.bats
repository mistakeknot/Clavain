#!/usr/bin/env bats
# review-round.sh: pre-review gate, panel merge, CI log path, confirm scope.
# Uses a fake dispatch so no reviewer is contacted.

setup() {
    export R="$BATS_TEST_TMPDIR/repo" OUT="$BATS_TEST_TMPDIR/out"
    git init -q -b main "$R"; cd "$R"
    git config user.email t@e.com; git config user.name t
    echo a > a; git add a; git commit -qm base
    git checkout -q -b w; echo b > b; git add b; git commit -qm work
    HEAD_SHA=$(git rev-parse HEAD)
    cat > "$BATS_TEST_TMPDIR/fake-dispatch.sh" <<'FAKE'
#!/usr/bin/env bash
# args: --role R --producer-identity P -s read-only --prompt-file F -C DIR -o OUT
while [ $# -gt 0 ]; do case "$1" in --prompt-file) PF=$2; shift 2;; -o) O=$2; shift 2;; *) shift;; esac; done
echo "$PF" >> "$FAKE_LOG"
if [ -n "${FAKE_WAIT_CI:-}" ]; then for _ in $(seq 50); do grep -q '^CI-EXIT' "$(dirname "$O")/ci.log" 2>/dev/null && break; sleep 0.1; done; grep '^CI-EXIT' "$(dirname "$O")/ci.log" > "$(dirname "$O")/seen-ci-marker" 2>/dev/null || true; fi
[ "${FAKE_RC:-0}" = 0 ] || exit "$FAKE_RC"
if [ -n "${FAKE_BODY:-}" ]; then printf '%b' "$FAKE_BODY" > "$O"
elif grep -q "security and safety only" "$PF"; then
  printf -- '- HIGH: shared finding in x.go\n- MEDIUM: safety only\nVERDICT: FAIL\n' > "$O"
elif grep -q "correctness only" "$PF"; then
  printf -- '- HIGH: shared finding in x.go\nVERDICT: PASS WITH NOTES\n' > "$O"
else
  printf -- 'ok\nVERDICT: PASS\n' > "$O"
fi
last=$(grep '^VERDICT: ' "$O" | tail -1)
# Mirrors real dispatch (tests/shell/fixtures/dispatch-verdict-capture.tsv): the
# reviewer's own terminal block decides the sidecar; with no block a PASS or
# PASS WITH NOTES is pass and a FAIL is warn.
blk=$(awk '/^--- VERDICT ---/{f=1;next} f&&/^STATUS: /{sub(/^STATUS: /,"");print;exit}' "$O")
if [ -n "$blk" ]; then ST=$blk; else case "$last" in "VERDICT: FAIL") ST=warn;; *) ST=pass;; esac; fi
ST=${FAKE_STATUS:-$ST}; [ -z "${FAKE_SIDECAR_ERROR:-}" ] || ST=error
printf -- '--- VERDICT ---\nSTATUS: %s\n---\n' "$ST" > "$O.verdict"
[ -z "${FAKE_PROV:-}" ] || echo "PROVISIONAL: capacity-substitute" >> "$O.verdict"
FAKE
    chmod +x "$BATS_TEST_TMPDIR/fake-dispatch.sh"
    export REVIEW_ROUND_DISPATCH="$BATS_TEST_TMPDIR/fake-dispatch.sh" FAKE_LOG="$BATS_TEST_TMPDIR/calls"
    : > "$FAKE_LOG"
    RR="$BATS_TEST_DIRNAME/../../scripts/review-round.sh"
}

@test "failing pre-review gate dispatches nothing" {
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" --gate-cmd 'exit 1'
    [ "$status" -eq 10 ]
    [ ! -s "$FAKE_LOG" ]
}

@test "first round is a three-lens panel with one merged receipt, worst verdict wins" {
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" --gate-cmd 'true'
    [ "$status" -eq 0 ]
    [ "$(wc -l < "$FAKE_LOG")" -eq 3 ]
    grep -q "counts as one round" "$OUT/receipt.md"
    [ "$(grep -c 'shared finding' "$OUT/receipt.md")" -eq 1 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
}

@test "CI log path is given to the reviewer" {
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" --ci-cmd 'echo ci-ran'
    [ "$status" -eq 0 ]
    grep -q "$OUT/ci.log" "$OUT/prompt-general.txt"
    grep -q "CI-EXIT: 0" "$OUT/ci.log"
}

@test "confirm round is one reviewer scoped to the fix diff plus earlier findings" {
    echo "- HIGH: earlier" > "$BATS_TEST_TMPDIR/prior.md"
    run bash "$RR" --mode confirm --prior-findings "$BATS_TEST_TMPDIR/prior.md" --prior-head "$HEAD_SHA" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "$FAKE_LOG")" -eq 1 ]
    grep -q "fix diff since" "$OUT/prompt-general.txt"
    grep -q "earlier" "$OUT/prompt-general.txt"
}

@test "moved checkout is refused" {
    run bash "$RR" --repo "$R" --base main --head 0000000000000000000000000000000000000000 --producer-identity p --out-dir "$OUT"
    [ "$status" -eq 11 ]
}

rr() { bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" "$@"; }

@test "dispatch failure is never a pass" {
    FAKE_RC=7 run rr --mode first
    [ "$status" -eq 3 ]
    ! grep -q '^VERDICT: PASS' "$OUT/receipt.md"
}

@test "non-pass sidecar overrides a PASS body" {
    FAKE_SIDECAR_ERROR=1 FAKE_BODY='ok\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: NONE" ]
}

@test "provisional capacity-substitute lens is not a clean pass" {
    FAKE_PROV=1 FAKE_BODY='ok\nVERDICT: PASS\n' run rr
    [ "$status" -eq 5 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: PROVISIONAL" ]
}

@test "a genuine reviewer FAIL is a FAIL receipt, not a missing verdict" {
    FAKE_BODY='- HIGH: bad\nVERDICT: FAIL\n' run rr --mode first
    [ "$status" -eq 0 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
}

@test "body verdict that disagrees with the sidecar status is rejected" {
    FAKE_STATUS=fail FAKE_BODY='ok\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
}

@test "unclosed fence with a quoted verdict is rejected" {
    FAKE_BODY='Verdict: PASS\n```\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
}

@test "reviewers run in an isolated worktree that is removed afterwards" {
    run rr --gate-cmd 'echo scratch > untracked.txt; rm untracked.txt'
    [ "$status" -eq 0 ]
    grep -q "$OUT/wt" "$OUT/prompt-general.txt" || true
    [ ! -d "$OUT/wt" ]
    [ -z "$(git -C "$R" worktree list --porcelain | grep -c "$OUT/wt" | grep -v '^0$')" ]
}

@test "untracked file left by a gate fails the round before review" {
    run rr --gate-cmd 'echo x > leftover.txt'
    [ "$status" -eq 11 ]
    [ ! -s "$FAKE_LOG" ]
}

@test "quoted or non-final verdict lines are rejected" {
    FAKE_BODY='```\nVERDICT: PASS\n```\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
    rm -rf "$OUT"
    FAKE_BODY='VERDICT: PASS\nblocking issue remains\n' run rr
    [ "$status" -eq 3 ]
}

@test "failed CI fails the round" {
    FAKE_BODY='ok\nVERDICT: PASS\n' run rr --ci-cmd 'exit 3'
    [ "$status" -eq 4 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
}

@test "non-empty out-dir is refused (no stale lens files)" {
    mkdir -p "$OUT"; echo old > "$OUT/lens-general.md"
    run rr
    [ "$status" -eq 2 ]
    [ ! -s "$FAKE_LOG" ]
}

@test "a gate that changes the checkout is refused" {
    run rr --gate-cmd 'echo x >> a'
    [ "$status" -eq 11 ]
    [ ! -s "$FAKE_LOG" ]
}

@test "confirm round with a non-ancestor prior head (rebase) is refused" {
    echo "- HIGH: e" > "$BATS_TEST_TMPDIR/prior.md"
    git checkout -q -b other main; echo z > z; git add z; git commit -qm z
    OTHER=$(git rev-parse HEAD); git checkout -q w
    run rr --mode confirm --prior-findings "$BATS_TEST_TMPDIR/prior.md" --prior-head "$OTHER"
    [ "$status" -eq 12 ]
}

@test "dispatch maps a first-line FAIL to sidecar warn: still a FAIL receipt" {
    FAKE_STATUS=warn FAKE_BODY='VERDICT: FAIL\n- HIGH: bad\nVERDICT: FAIL\n' run rr
    [ "$status" -eq 3 ]   # two VERDICT lines: ambiguous, rejected
    rm -rf "$OUT"
    FAKE_STATUS=warn FAKE_BODY='- HIGH: bad\nVERDICT: FAIL\n' run rr
    [ "$status" -eq 0 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
}

@test "tilde fence with a quoted verdict is rejected" {
    FAKE_BODY='Verdict: PASS\n~~~\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
}

@test "CI runs in its own worktree and relative paths work from elsewhere" {
    mkdir -p "$BATS_TEST_TMPDIR/elsewhere"; cd "$BATS_TEST_TMPDIR/elsewhere"
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir rel-out --ci-cmd 'pwd'
    [ "$status" -eq 0 ]
    grep -q "wt-ci" rel-out/ci.log
    [ ! -d rel-out/wt ] && [ ! -d rel-out/wt-ci ]
}

@test "an intermediate verdict block cannot hide a later FAIL" {
    FAKE_STATUS=pass FAKE_BODY='VERDICT: PASS\n--- VERDICT ---\nSTATUS: pass\n---\nVERDICT: FAIL\n' run rr
    [ "$status" -eq 3 ]
    rm -rf "$OUT"
    FAKE_STATUS=warn FAKE_BODY='VERDICT: PASS WITH NOTES\n--- VERDICT ---\nSTATUS: warn\n---\n--- VERDICT ---\nSTATUS: fail\n---\n' run rr
    [ "$status" -eq 3 ]
}

@test "a genuine terminal verdict block is accepted" {
    FAKE_BODY='- note\nVERDICT: PASS\n--- VERDICT ---\nSTATUS: pass\n---\n' run rr
    [ "$status" -eq 0 ]
}

@test "a closing fence mixing backticks and tildes does not close the fence" {
    FAKE_BODY='x\n```\n```~~~\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
    rm -rf "$OUT"
    FAKE_BODY='x\n~~~\n~~~```\nVERDICT: PASS\n' run rr
    [ "$status" -eq 3 ]
}

@test "CI-EXIT marker is written by the CI process before reviewers finish" {
    FAKE_WAIT_CI=1 FAKE_BODY='ok\nVERDICT: PASS\n' run rr --ci-cmd 'true'
    [ "$status" -eq 0 ]
    grep -q '^CI-EXIT: 0' "$OUT/seen-ci-marker"
}

@test "a CI command that changes tracked files in its worktree is not evidence" {
    FAKE_BODY='ok\nVERDICT: PASS\n' run rr --ci-cmd 'echo x >> a'
    [ "$status" -eq 11 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
}

@test "a malformed terminal block with STATUS fail cannot hide behind an initial PASS" {
    FAKE_STATUS=pass FAKE_BODY='VERDICT: PASS\n--- VERDICT ---\nSTATUS: fail\nSUMMARY malformed\n---\n' run rr
    [ "$status" -eq 3 ]
    rm -rf "$OUT"
    FAKE_STATUS=pass FAKE_BODY='ok\nVERDICT: PASS\n--- VERDICT ---\nSTATUS: pass\n---\n---\n' run rr
    [ "$status" -eq 3 ]
    rm -rf "$OUT"
    FAKE_STATUS=pass FAKE_BODY='ok\nVERDICT: PASS\n--- VERDICT ---\nSTATUS: warn\n---\n' run rr
    [ "$status" -eq 3 ]
}

@test "a failing CI command still writes its CI-EXIT marker before reviewers finish" {
    FAKE_WAIT_CI=1 FAKE_BODY='ok\nVERDICT: PASS\n' run rr --ci-cmd 'exit 3'
    [ "$status" -eq 4 ]
    grep -q '^CI-EXIT: 3' "$OUT/seen-ci-marker"
    [ "$(tail -1 "$OUT/ci.log")" = "CI-EXIT: 3" ]
}

@test "a body FAIL with a STATUS fail block and a warn sidecar stays a FAIL receipt" {
    FAKE_STATUS=warn FAKE_BODY='- HIGH: bad\nVERDICT: FAIL\n--- VERDICT ---\nSTATUS: fail\n---\n' run rr
    [ "$status" -eq 0 ]
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
    rm -rf "$OUT"
    FAKE_STATUS=warn FAKE_BODY='- HIGH: bad\nVERDICT: FAIL\n--- VERDICT ---\nSTATUS: pass\n---\n' run rr
    [ "$status" -eq 3 ]
}

# ---- table tests: every body verdict x terminal block x sidecar x PROVISIONAL ----
_lens_table_file() { # shape bv blk -> writes $T/lens.md
    local shape=$1 bv=$2 blk=$3
    { [ "$shape" = both ] && printf 'VERDICT: %s\n' "$bv"; printf -- '- MEDIUM: x\nVERDICT: %s\n' "$bv"
      [ "$blk" = none ] || printf -- '--- VERDICT ---\nSTATUS: %s\n---\n' "$blk"; } > "$BATS_TEST_TMPDIR/lens.md"
}
# Oracle, written from the rule rather than from the code: the block must match the
# body verdict; the sidecar must be one dispatch can emit for it (PASS:pass,
# PASS WITH NOTES:warn, or pass only without a block, FAIL:warn|fail); a FAIL stays
# FAIL even when PROVISIONAL; otherwise PROVISIONAL wins over the body verdict.
_lens_expect() { # bv blk sst prov shape
    local bv=$1 blk=$2 sst=$3 prov=$4 shape=${5:-tail} bw
    [ "$shape" = tail ] || { echo NONE; return; }   # a second VERDICT line is never accepted
    case "$bv" in PASS) bw=pass;; "PASS WITH NOTES") bw=warn;; FAIL) bw=fail;; esac
    [ "$blk" = none ] || [ "$blk" = "$bw" ] || { echo NONE; return; }
    case "$bv:$sst" in
        PASS:pass|"PASS WITH NOTES:warn"|FAIL:fail|FAIL:warn) ;;
        "PASS WITH NOTES:pass") [ "$blk" = none ] || { echo NONE; return; } ;;
        *) echo NONE; return ;;
    esac
    if [ "$bv" = FAIL ]; then echo FAIL; elif [ "$prov" = 1 ]; then echo PROVISIONAL; else echo "$bv"; fi
}

@test "table: all body x block x sidecar x PROVISIONAL combinations (144 rows)" {
    export REVIEW_ROUND_SOURCE_ONLY=1
    source "$RR"
    n=0
    for shape in tail both; do for bv in "PASS" "PASS WITH NOTES" "FAIL"; do for blk in none pass warn fail; do
    for sst in pass warn fail; do for prov in 0 1; do
        _lens_table_file "$shape" "$bv" "$blk"
        got=$(lens_verdict "$BATS_TEST_TMPDIR/lens.md" "$sst" "$prov")
        want=$(_lens_expect "$bv" "$blk" "$sst" "$prov" "$shape")
        [ "${got%% *}" = "${want%% *}" ] || { echo "row $shape|$bv|$blk|$sst|$prov: got '$got' want '$want'"; return 1; }
        [ "$want" = NONE ] || [ "$got" = "$want" ] || { echo "row $shape|$bv|$blk|$sst|$prov: got '$got' want '$want'"; return 1; }
        n=$((n+1))
    done; done; done; done; done
    [ "$n" -eq 144 ]
}

@test "table: rows captured from real dispatch _extract_verdict map as expected" {
    export REVIEW_ROUND_SOURCE_ONLY=1
    source "$RR"
    n=0
    while IFS=$'\t' read -r shape bv blk prov sst pl; do
        _lens_table_file "$shape" "$bv" "$blk"
        [ "$pl" = "$prov" ]
        got=$(lens_verdict "$BATS_TEST_TMPDIR/lens.md" "$sst" "$pl")
        want=$(_lens_expect "$bv" "$blk" "$sst" "$prov" "$shape")
        [ "$got" = "$want" ] || [ "${got%% *}" = "${want%% *}" ] || { echo "captured row $shape|$bv|$blk|$prov|$sst: got '$got' want '$want'"; return 1; }
        # the two cases the review found: real FAIL+PROVISIONAL and blockless PASS WITH NOTES (sidecar pass)
        if [ "$shape" = tail ] && [ "$bv" = FAIL ] && { [ "$blk" = none ] || [ "$blk" = fail ]; } && [ "$prov" = 1 ]; then [ "$got" = FAIL ]; fi
        if [ "$shape" = tail ] && [ "$bv" = "PASS WITH NOTES" ] && [ "$blk" = none ] && [ "$prov" = 0 ]; then [ "$got" = "PASS WITH NOTES" ]; fi
        n=$((n+1))
    done < "$BATS_TEST_DIRNAME/fixtures/dispatch-verdict-capture.tsv"
    [ "$n" -eq 48 ]
}

@test "table: the capture fixture still matches the real dispatch.sh" {
    run bash "$BATS_TEST_DIRNAME/fixtures/capture-dispatch-verdicts.sh" "$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    [ "$status" -eq 0 ]
    [ "$output" = "$(cat "$BATS_TEST_DIRNAME/fixtures/dispatch-verdict-capture.tsv")" ]
}

@test "a real FAIL on a PROVISIONAL lens is a FAIL receipt, not PROVISIONAL" {
    FAKE_PROV=1 FAKE_BODY='- HIGH: bad\nVERDICT: FAIL\n' run bash "$RR" --mode confirm --prior-head "$HEAD_SHA" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT"
    grep -q 'general: FAIL' "$OUT/receipt.md"
    [ "$(tail -1 "$OUT/receipt.md")" = "VERDICT: FAIL" ]
}
