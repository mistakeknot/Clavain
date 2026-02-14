#!/usr/bin/env bats
# Tests for hooks/lib-signals.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/lib-signals.sh"
}

teardown() {
    unset CLAVAIN_SIGNALS CLAVAIN_SIGNAL_WEIGHT
}

@test "lib-signals: detect_signals sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT" {
    local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'
    detect_signals "$transcript"
    [[ -n "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -ge 1 ]]
}

@test "lib-signals: detects commit signal (weight 1)" {
    local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"commit"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects bead-closed signal (weight 1)" {
    local transcript='{"role":"assistant","content":"Running \"bd close Clavain-abc1\""}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"bead-closed"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects resolution signal (weight 2)" {
    local transcript='{"role":"user","content":"that worked, thanks!"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"resolution"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects investigation signal (weight 2)" {
    local transcript='{"role":"assistant","content":"the issue was a race condition in the cache layer"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"investigation"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects insight signal (weight 1)" {
    local transcript='Insight ─ The key realization is that X causes Y'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"insight"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects recovery signal (weight 2)" {
    local transcript=$'test FAILED: expected 5 got 3\nAll tests passed after fix'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"recovery"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects version-bump signal (weight 2)" {
    local transcript='{"role":"assistant","content":"Running bump-version.sh 0.7.0"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"version-bump"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects interpub:release as version-bump (weight 2)" {
    local transcript='{"role":"assistant","content":"Running /interpub:release 1.0.0"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"version-bump"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: accumulates weights from multiple signals" {
    local transcript=$'Running "git commit -m fix"\nInsight ─ key insight\n"the issue was a cache bug"'
    detect_signals "$transcript"
    # commit(1) + insight(1) + investigation(2) = 4
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 4 ]]
}

@test "lib-signals: no signals returns weight 0 and empty SIGNALS" {
    local transcript='{"role":"user","content":"What is Python?"}'
    detect_signals "$transcript"
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: empty string returns weight 0" {
    detect_signals ""
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: CLAVAIN_SIGNALS has no trailing comma" {
    local transcript=$'Running "git commit -m fix"\nRunning "bd close Clavain-abc1"'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"," ]]  # no trailing comma
    [[ "$CLAVAIN_SIGNALS" == *","* ]]  # but has internal comma (2 signals)
}
