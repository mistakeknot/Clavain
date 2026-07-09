#!/usr/bin/env bats
# Tests for hooks/lib-loop-breaker.sh (mk-ax8): identical Stop-hook demands
# with no intervening work park the session instead of looping forever.

setup() {
    load test_helper
    export HOME="$BATS_TEST_TMPDIR/home"
    export CLAVAIN_LOOP_BREAKER_DIR="$BATS_TEST_TMPDIR/lb-state"
    mkdir -p "$HOME"
    # Run inside a real git repo so the work fingerprint is exercised.
    export REPO="$BATS_TEST_TMPDIR/repo"
    git init -q -b main "$REPO"
    cd "$REPO"
    git config user.email test@example.com
    git config user.name "Bats Test"
    echo one > f.txt
    git add f.txt
    git commit -qm "c1"
    source "$HOOKS_DIR/../galiana/lib-galiana.sh"
    source "$HOOKS_DIR/lib-loop-breaker.sh"
}

@test "loop-breaker: first fire passes the reason through unchanged" {
    run loop_breaker_filter "sess-1" "do the thing"
    [ "$status" -eq 0 ]
    [ "$output" = "do the thing" ]
}

@test "loop-breaker: second identical fire with no work replaces reason with BLOCKED message" {
    loop_breaker_filter "sess-2" "do the thing" >/dev/null
    run loop_breaker_filter "sess-2" "do the thing"
    [ "$status" -eq 0 ]
    [[ "$output" == BLOCKED* ]]
}

@test "loop-breaker: third identical fire suppresses silently (return 1)" {
    loop_breaker_filter "sess-3" "do the thing" >/dev/null
    loop_breaker_filter "sess-3" "do the thing" >/dev/null
    run loop_breaker_filter "sess-3" "do the thing"
    [ "$status" -eq 1 ]
    [ -z "$output" ]
}

@test "loop-breaker: work between fires resets state (reason passes through)" {
    loop_breaker_filter "sess-4" "do the thing" >/dev/null
    echo two > f.txt # worktree changed → fingerprint moves
    run loop_breaker_filter "sess-4" "do the thing"
    [ "$status" -eq 0 ]
    [ "$output" = "do the thing" ]
    # and a commit also counts as progress after a BLOCKED park
    run loop_breaker_filter "sess-4" "do the thing"
    [[ "$output" == BLOCKED* ]]
    git add f.txt && git commit -qm "c2"
    run loop_breaker_filter "sess-4" "do the thing"
    [ "$status" -eq 0 ]
    [ "$output" = "do the thing" ]
}

@test "loop-breaker: a different reason passes through untouched" {
    loop_breaker_filter "sess-5" "reason A" >/dev/null
    run loop_breaker_filter "sess-5" "reason B"
    [ "$status" -eq 0 ]
    [ "$output" = "reason B" ]
}

@test "loop-breaker: suppressions are logged to galiana telemetry as KPI events" {
    loop_breaker_filter "sess-6" "do the thing" >/dev/null
    loop_breaker_filter "sess-6" "do the thing" >/dev/null # blocked_message
    loop_breaker_filter "sess-6" "do the thing" >/dev/null || true # silent
    run grep -c '"event":"stop_loop_suppression"' "$HOME/.clavain/telemetry.jsonl"
    [ "$output" -ge 2 ]
    run grep -c '"action":"blocked_message"' "$HOME/.clavain/telemetry.jsonl"
    [ "$output" -eq 1 ]
}
