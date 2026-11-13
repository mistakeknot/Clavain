#!/usr/bin/env bats

setup() {
    source "$BATS_TEST_DIRNAME/../../scripts/lib-verdict.sh"
    source "$BATS_TEST_DIRNAME/../../scripts/lib-dispatch-audit.sh"
    OUTPUT="$BATS_TEST_TMPDIR/out"
    ROLE=validation ENGINE=claude MODEL=claude-opus-5-5
    DISPATCH_RESULT_READY=true
    CLAVAIN_BEAD_ID=test-1
}

@test "run receipt records classifier result for all review roles and aliases" {
    for ROLE in cross-lab-review plan-review validation; do
        for word in FAIL BLOCK 'BLOCK: fix it'; do
            printf 'Review\n\nVERDICT: %s\n' "$word" > "$OUTPUT"
            run _build_dispatch_run_receipt 0
            [ "$status" -eq 0 ]
            [ "$(jq -r .bead_id <<< "$output")" = test-1 ]
            [ "$(jq -r .verdict_class <<< "$output")" = FAIL ]
        done
    done
}

@test "passes notes and unknown verdicts never become failures" {
    for word in PASS 'PASS WITH NOTES' UNKNOWN APPROVE; do
        printf 'VERDICT: %s\n' "$word" > "$OUTPUT"
        run _build_dispatch_run_receipt 0
        [ "$status" -eq 0 ]
        [ "$(jq -r .verdict_class <<< "$output")" != FAIL ]
    done
}

@test "stale output operational failures and non-review roles add no verdict" {
    printf 'VERDICT: FAIL\n' > "$OUTPUT"
    DISPATCH_RESULT_READY=false
    run _build_dispatch_run_receipt 1
    [ "$(jq -r .verdict_class <<< "$output")" = null ]
    DISPATCH_RESULT_READY=true ROLE=planning
    run _build_dispatch_run_receipt 0
    [ "$(jq -r .verdict_class <<< "$output")" = null ]
}
