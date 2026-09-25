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

@test "lib-signals: insight signal was removed (no detection)" {
    local transcript='Insight ─ The key realization is that X causes Y'
    detect_signals "$transcript"
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
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
    local transcript=$'Running "git commit -m fix"\n"the issue was a cache bug"'
    detect_signals "$transcript"
    # commit(1) + investigation(2) = 3 (insight signal was removed)
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 3 ]]
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

@test "lib-signals: detects goal-completed from a met goal_status (weight 0, structural)" {
    local transcript='{"type":"attachment","attachment":{"type":"goal_status","met":true,"condition":"x"}}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: an unmet goal_status is not goal-completed" {
    local transcript='{"type":"attachment","attachment":{"type":"goal_status","met":false,"condition":"x"}}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

@test "lib-signals: detects goal-completed when an epic closes" {
    local transcript='Closed the last child, so the epic is now closed.'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
}

@test "lib-signals: milestone and goal wording alone is not goal-completed" {
    local transcript=$'The goal is complete.\nRan /goal review and it landed successfully\nThis goal-scale milestone landed after three sprints\n/goal Ship it. DONE WHEN tests pass.'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

@test "lib-signals: goal-completed does not fire on unrelated text" {
    local transcript='Just fixed a typo in the README, nothing goal-related'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

@test "lib-signals: goal-completed does not add to weight ladder alongside other signals" {
    local transcript=$'Running "git commit -m fix"\n{"type":"goal_status","met":true}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$CLAVAIN_SIGNALS" == *"commit"* ]]
    # commit(1) + goal-completed(0) = 1
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}
