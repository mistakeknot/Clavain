#!/usr/bin/env bats
# Tests for scripts/microrouter-deferral-status.sh — F4 surfacing of the
# microrouter architecture-decision deferral tiers (sylveste-58tb).
# Mocks bd so no real beads DB is required.

setup() {
    load test_helper
    SCRIPT="$CLAUDE_PLUGIN_ROOT/scripts/microrouter-deferral-status.sh"

    # Default deferral state: check_in 2026-05-20, deadline 2026-06-30,
    # named authority, no d2_result.
    export BD_SHOW_OUTPUT='[{"labels":["deferral_check_in:2026-05-20","deferral_deadline:2026-06-30","decision_authority_primary:arouth1","decision_authority_backup:arouth1","auto_revert_action:surface-forced-reentry"]}]'

    bd() {
        case "$1" in
            show) [[ -n "${BD_SHOW_OUTPUT:-}" ]] && echo "$BD_SHOW_OUTPUT" ;;
        esac
        return 0
    }
    export -f bd
}

teardown() {
    unset -f bd 2>/dev/null || true
}

@test "healthy: today before check-in -> PASS" {
    run bash "$SCRIPT" --today 2026-05-10
    [ "$status" -eq 0 ]
    [[ "$output" == *"PASS"* ]]
    [[ "$output" == *"check-in healthy"* ]]
}

@test "due: check-in date reached, <7d -> WARN" {
    run bash "$SCRIPT" --today 2026-05-22
    [ "$status" -eq 0 ]
    [[ "$output" == *"WARN"* ]]
    [[ "$output" == *"check-in DUE"* ]]
}

@test "overdue: 7..14d past check-in -> WARN with extend-or-reenter nudge" {
    run bash "$SCRIPT" --today 2026-05-29
    [ "$status" -eq 0 ]
    [[ "$output" == *"WARN"* ]]
    [[ "$output" == *"check-in OVERDUE"* ]]
    [[ "$output" == *"extend or re-enter"* ]]
}

@test "stale: >=14d past check-in -> FAIL with BLOCKING notice" {
    run bash "$SCRIPT" --today 2026-06-05
    [ "$status" -eq 0 ]
    [[ "$output" == *"FAIL"* ]]
    [[ "$output" == *"check-in STALE"* ]]
    [[ "$output" == *"BLOCKING"* ]]
}

@test "deadline approaching: within 7d -> APPROACHING line" {
    run bash "$SCRIPT" --today 2026-06-25
    [ "$status" -eq 0 ]
    [[ "$output" == *"deadline APPROACHING"* ]]
}

@test "deadline exceeded: forced-reentry notice with exact phrasing" {
    run bash "$SCRIPT" --today 2026-07-05
    [ "$status" -eq 0 ]
    [[ "$output" == *"deadline EXCEEDED"* ]]
    [[ "$output" == *"Run /clavain:route sylveste-s3z6.19.10"* ]]
    [[ "$output" == *"deadline passed"* ]]
}

@test "d2_result=kill-epic forces re-entry regardless of date" {
    export BD_SHOW_OUTPUT='[{"labels":["deferral_check_in:2026-05-20","deferral_deadline:2026-06-30","decision_authority_primary:arouth1","auto_revert_action:surface-forced-reentry","d2_result:kill-epic"]}]'
    run bash "$SCRIPT" --today 2026-05-10
    [ "$status" -eq 0 ]
    [[ "$output" == *"FAIL"* ]]
    [[ "$output" == *"kill-epic"* ]]
    [[ "$output" == *"forced re-entry"* ]]
}

@test "no deferral fields -> silent, exit 0" {
    export BD_SHOW_OUTPUT='[{"labels":["microrouter","clavain"]}]'
    run bash "$SCRIPT" --today 2026-06-22
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "bead unavailable -> silent, exit 0" {
    export BD_SHOW_OUTPUT=''
    run bash "$SCRIPT" --today 2026-06-22
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "authority and auto_revert are surfaced" {
    run bash "$SCRIPT" --today 2026-05-10
    [ "$status" -eq 0 ]
    [[ "$output" == *"authority: arouth1"* ]]
    [[ "$output" == *"surface-forced-reentry"* ]]
}
