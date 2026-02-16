#!/usr/bin/env bats
# Tests for hooks/lib-sprint.sh — sprint state library for Clavain.
# Uses mock bd() shell function to avoid needing a real beads database.

setup() {
    load test_helper

    # Create isolated temp project directory for each test
    TEST_PROJECT="$(mktemp -d)"
    mkdir -p "$TEST_PROJECT/.beads"
    export SPRINT_LIB_PROJECT_DIR="$TEST_PROJECT"
    export HOME="$TEST_PROJECT"

    # Ensure interphase is NOT found (avoids real plugin delegation)
    mkdir -p "$TEST_PROJECT/.claude/plugins/cache"
    export INTERPHASE_ROOT=""
    export INTERLOCK_ROOT=""

    # Reset double-source guards so we can re-source in each test
    unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED

    # Clean up lock dirs from previous tests
    rm -rf /tmp/sprint-lock-* /tmp/sprint-claim-lock-* /tmp/sprint-advance-lock-* 2>/dev/null || true

    # Clean up discovery caches
    rm -f /tmp/clavain-discovery-brief-*.cache 2>/dev/null || true

    # BD_CALL_LOG tracks calls to mock bd for verification
    BD_CALL_LOG="$TEST_PROJECT/bd_calls.log"
    export BD_CALL_LOG
}

teardown() {
    rm -rf "$TEST_PROJECT" 2>/dev/null || true
    rm -rf /tmp/sprint-lock-* /tmp/sprint-claim-lock-* /tmp/sprint-advance-lock-* 2>/dev/null || true
    rm -f /tmp/clavain-discovery-brief-*.cache 2>/dev/null || true
    unset -f bd 2>/dev/null || true
}

# Helper: source lib-sprint.sh with guards cleared
_source_sprint_lib() {
    unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED
    source "$HOOKS_DIR/lib-sprint.sh"
}

# ─── 1. sprint_create returns a valid bead ID ────────────────────────

@test "sprint_create returns a valid bead ID" {
    bd() {
        case "$1" in
            create) echo "Created iv-test1" ;;
            set-state) return 0 ;;
            state)
                case "$3" in
                    phase) echo "brainstorm" ;;
                    *) echo "" ;;
                esac
                ;;
            update) return 0 ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_create "My Sprint"
    assert_success
    assert_output "iv-test1"
}

# ─── 2. sprint_create partial init failure cancels bead ──────────────

@test "sprint_create partial init failure cancels bead" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            create) echo "Created iv-fail1" ;;
            set-state)
                # Fail when setting phase=brainstorm (second set-state call)
                if [[ "$*" == *"phase=brainstorm"* ]]; then
                    return 1
                fi
                return 0
                ;;
            update) return 0 ;;
            state) echo "brainstorm" ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_create "Failing Sprint"
    assert_success
    assert_output ""

    # Verify cancel was called
    run grep "update iv-fail1 --status=cancelled" "$BD_CALL_LOG"
    assert_success
}

# ─── 3. sprint_finalize_init sets sprint_initialized=true ────────────

@test "sprint_finalize_init sets sprint_initialized=true" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        return 0
    }
    export -f bd

    _source_sprint_lib
    run sprint_finalize_init "iv-test1"
    assert_success

    run grep 'set-state iv-test1 sprint_initialized=true' "$BD_CALL_LOG"
    assert_success
}

# ─── 4. sprint_find_active returns only initialized sprint beads ─────

@test "sprint_find_active returns only initialized sprint beads" {
    bd() {
        case "$1" in
            list) echo '[{"id":"iv-s1","title":"Sprint 1"},{"id":"iv-s2","title":"Sprint 2"}]' ;;
            state)
                case "$2" in
                    iv-s1)
                        case "$3" in
                            sprint) echo "true" ;;
                            sprint_initialized) echo "true" ;;
                            phase) echo "brainstorm" ;;
                        esac
                        ;;
                    iv-s2)
                        case "$3" in
                            sprint) echo "true" ;;
                            sprint_initialized) echo "false" ;;  # Not initialized
                            phase) echo "planned" ;;
                        esac
                        ;;
                esac
                ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_find_active
    assert_success

    # Should contain iv-s1 but NOT iv-s2
    local result="$output"
    echo "$result" | jq -e '.[0].id == "iv-s1"'
    echo "$result" | jq -e 'length == 1'
}

# ─── 5. sprint_find_active excludes non-sprint beads ─────────────────

@test "sprint_find_active excludes non-sprint beads" {
    bd() {
        case "$1" in
            list) echo '[{"id":"iv-regular","title":"Regular Bead"},{"id":"iv-sprint","title":"A Sprint"}]' ;;
            state)
                case "$2" in
                    iv-regular)
                        case "$3" in
                            sprint) echo "false" ;;
                            sprint_initialized) echo "true" ;;
                            phase) echo "brainstorm" ;;
                        esac
                        ;;
                    iv-sprint)
                        case "$3" in
                            sprint) echo "true" ;;
                            sprint_initialized) echo "true" ;;
                            phase) echo "executing" ;;
                        esac
                        ;;
                esac
                ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_find_active
    assert_success

    local result="$output"
    echo "$result" | jq -e 'length == 1'
    echo "$result" | jq -e '.[0].id == "iv-sprint"'
}

# ─── 6. sprint_read_state returns all fields as valid JSON ───────────

@test "sprint_read_state returns all fields as valid JSON" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    phase) echo "executing" ;;
                    sprint_artifacts) echo '{"brainstorm":"/tmp/bs.md"}' ;;
                    phase_history) echo '{"brainstorm_at":"2026-01-01T00:00:00Z"}' ;;
                    complexity) echo "medium" ;;
                    auto_advance) echo "true" ;;
                    active_session) echo "sess-123" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_read_state "iv-test1"
    assert_success

    # Validate it's valid JSON
    echo "$output" | jq empty

    # Check fields
    echo "$output" | jq -e '.id == "iv-test1"'
    echo "$output" | jq -e '.phase == "executing"'
    echo "$output" | jq -e '.artifacts.brainstorm == "/tmp/bs.md"'
    echo "$output" | jq -e '.history.brainstorm_at == "2026-01-01T00:00:00Z"'
    echo "$output" | jq -e '.complexity == "medium"'
    echo "$output" | jq -e '.auto_advance == "true"'
    echo "$output" | jq -e '.active_session == "sess-123"'
}

# ─── 7. sprint_read_state recovers from corrupt JSON ─────────────────

@test "sprint_read_state recovers from corrupt JSON (returns defaults)" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    phase) echo "brainstorm" ;;
                    sprint_artifacts) echo "NOT-VALID-JSON{{{" ;;
                    phase_history) echo "also broken" ;;
                    complexity) echo "" ;;
                    auto_advance) echo "true" ;;
                    active_session) echo "" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_read_state "iv-corrupt"
    assert_success

    # Should still be valid JSON with defaults for corrupt fields
    echo "$output" | jq empty
    echo "$output" | jq -e '.id == "iv-corrupt"'
    echo "$output" | jq -e '.phase == "brainstorm"'
    # Corrupt artifacts/history should fall back to {}
    echo "$output" | jq -e '.artifacts == {}'
    echo "$output" | jq -e '.history == {}'
}

# ─── 8. sprint_set_artifact updates artifact path under lock ─────────

@test "sprint_set_artifact updates artifact path under lock" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            state)
                case "$3" in
                    sprint_artifacts) echo '{}' ;;
                esac
                ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_set_artifact "iv-test1" "brainstorm" "/tmp/brainstorm.md"
    assert_success

    # Verify the set-state call was made with the artifact
    run grep 'set-state iv-test1' "$BD_CALL_LOG"
    assert_success

    # Lock directory should be cleaned up
    [[ ! -d /tmp/sprint-lock-iv-test1 ]]
}

# ─── 9. sprint_set_artifact handles concurrent calls ─────────────────

@test "sprint_set_artifact handles concurrent calls" {
    # We need a mock bd that tracks accumulated state
    local state_file="$TEST_PROJECT/artifacts_state.json"
    echo '{}' > "$state_file"

    bd() {
        case "$1" in
            state)
                case "$3" in
                    sprint_artifacts) cat "$BD_STATE_FILE" ;;
                esac
                ;;
            set-state)
                # Extract the JSON value from sprint_artifacts=...
                local val="${3#sprint_artifacts=}"
                echo "$val" > "$BD_STATE_FILE"
                return 0
                ;;
        esac
    }
    export -f bd
    export BD_STATE_FILE="$state_file"

    _source_sprint_lib

    # Run two set_artifact calls sequentially (they use locks internally)
    sprint_set_artifact "iv-conc" "brainstorm" "/tmp/bs.md"
    sprint_set_artifact "iv-conc" "plan" "/tmp/plan.md"

    # Verify both keys are present in the final state
    local final
    final=$(cat "$state_file")
    echo "$final" | jq -e '.brainstorm == "/tmp/bs.md"'
    echo "$final" | jq -e '.plan == "/tmp/plan.md"'
}

# ─── 10. sprint_set_artifact stale lock cleanup after 5s ─────────────

@test "sprint_set_artifact stale lock cleanup after 5s" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    sprint_artifacts) echo '{}' ;;
                esac
                ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd

    _source_sprint_lib

    # Create a stale lock directory and backdate its mtime
    mkdir -p /tmp/sprint-lock-iv-stale
    touch -d "10 seconds ago" /tmp/sprint-lock-iv-stale

    # This should break the stale lock and succeed
    run sprint_set_artifact "iv-stale" "brainstorm" "/tmp/bs.md"
    assert_success

    # Lock should be cleaned up
    [[ ! -d /tmp/sprint-lock-iv-stale ]]
}

# ─── 11. sprint_record_phase_completion adds timestamp to history ────

@test "sprint_record_phase_completion adds timestamp to history" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            state)
                case "$3" in
                    phase_history) echo '{}' ;;
                esac
                ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_record_phase_completion "iv-test1" "brainstorm"
    assert_success

    # Verify set-state was called with brainstorm_at key
    run grep 'set-state iv-test1 phase_history=' "$BD_CALL_LOG"
    assert_success
    # The logged line should contain brainstorm_at
    run grep 'brainstorm_at' "$BD_CALL_LOG"
    assert_success
}

# ─── 12. sprint_record_phase_completion invalidates discovery caches ──

@test "sprint_record_phase_completion invalidates discovery caches" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    phase_history) echo '{}' ;;
                esac
                ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd

    _source_sprint_lib

    # Create a cache file
    touch /tmp/clavain-discovery-brief-test123.cache

    sprint_record_phase_completion "iv-test1" "brainstorm"

    # Cache should be deleted
    [[ ! -f /tmp/clavain-discovery-brief-test123.cache ]]
}

# ─── 13. sprint_claim succeeds for first claimer ─────────────────────

@test "sprint_claim succeeds for first claimer" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            state)
                case "$3" in
                    active_session) echo "" ;;
                    claim_timestamp) echo "" ;;
                esac
                ;;
            set-state)
                # For verify step, record the session we set
                if [[ "$3" == active_session=* ]]; then
                    echo "${3#active_session=}" > "$TEST_PROJECT/claimed_session"
                fi
                return 0
                ;;
        esac
    }
    export -f bd

    # Override the verify read to return the session we wrote
    bd() {
        case "$1" in
            state)
                case "$3" in
                    active_session)
                        if [[ -f "$TEST_PROJECT/claimed_session" ]]; then
                            cat "$TEST_PROJECT/claimed_session"
                        else
                            echo ""
                        fi
                        ;;
                    claim_timestamp) echo "" ;;
                esac
                ;;
            set-state)
                if [[ "$3" == active_session=* ]]; then
                    echo "${3#active_session=}" > "$TEST_PROJECT/claimed_session"
                fi
                return 0
                ;;
        esac
    }
    export -f bd

    _source_sprint_lib
    run sprint_claim "iv-test1" "session-abc"
    assert_success
}

# ─── 14. sprint_claim blocks second claimer ──────────────────────────

@test "sprint_claim blocks second claimer" {
    local now_ts
    now_ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    bd() {
        case "$1" in
            state)
                case "$3" in
                    active_session) echo "session-first" ;;
                    claim_timestamp) echo "$BD_CLAIM_TS" ;;
                esac
                ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd
    export BD_CLAIM_TS="$now_ts"

    _source_sprint_lib
    run sprint_claim "iv-test1" "session-second"
    assert_failure
}

# ─── 15. sprint_claim allows takeover after TTL expiry ───────────────

@test "sprint_claim allows takeover after TTL expiry (61 minutes ago)" {
    local expired_ts
    expired_ts=$(date -u -d "61 minutes ago" +%Y-%m-%dT%H:%M:%SZ)

    bd() {
        case "$1" in
            state)
                case "$3" in
                    active_session)
                        if [[ -f "$TEST_PROJECT/claimed_session" ]]; then
                            cat "$TEST_PROJECT/claimed_session"
                        else
                            echo "session-old"
                        fi
                        ;;
                    claim_timestamp) echo "$BD_EXPIRED_TS" ;;
                esac
                ;;
            set-state)
                if [[ "$3" == active_session=* ]]; then
                    echo "${3#active_session=}" > "$TEST_PROJECT/claimed_session"
                fi
                return 0
                ;;
        esac
    }
    export -f bd
    export BD_EXPIRED_TS="$expired_ts"

    _source_sprint_lib
    run sprint_claim "iv-test1" "session-new"
    assert_success
}

# ─── 16. sprint_claim blocks at 59 minutes (not yet expired) ────────

@test "sprint_claim blocks at 59 minutes (not yet expired)" {
    local recent_ts
    recent_ts=$(date -u -d "59 minutes ago" +%Y-%m-%dT%H:%M:%SZ)

    bd() {
        case "$1" in
            state)
                case "$3" in
                    active_session) echo "session-active" ;;
                    claim_timestamp) echo "$BD_RECENT_TS" ;;
                esac
                ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd
    export BD_RECENT_TS="$recent_ts"

    _source_sprint_lib
    run sprint_claim "iv-test1" "session-wannabe"
    assert_failure
}

# ─── 17. sprint_release clears claim ─────────────────────────────────

@test "sprint_release clears claim" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        return 0
    }
    export -f bd

    _source_sprint_lib
    run sprint_release "iv-test1"
    assert_success

    # Verify both active_session and claim_timestamp are cleared
    run grep 'set-state iv-test1 active_session=' "$BD_CALL_LOG"
    assert_success
    run grep 'set-state iv-test1 claim_timestamp=' "$BD_CALL_LOG"
    assert_success
}

# ─── 18. sprint_next_step maps all phases correctly ──────────────────

@test "sprint_next_step maps all phases correctly" {
    _source_sprint_lib

    # Empty/unknown phase → brainstorm (start from beginning)
    run sprint_next_step ""
    assert_output "brainstorm"

    # Phase 2: sprint_next_step returns the NEXT command (for auto-advance)
    # brainstorm is done → next is strategy
    run sprint_next_step "brainstorm"
    assert_output "strategy"

    # brainstorm-reviewed → strategized → strategy command produces it
    run sprint_next_step "brainstorm-reviewed"
    assert_output "strategy"

    run sprint_next_step "strategized"
    assert_output "write-plan"

    run sprint_next_step "planned"
    assert_output "flux-drive"

    run sprint_next_step "plan-reviewed"
    assert_output "work"

    # executing → shipping → ship
    run sprint_next_step "executing"
    assert_output "ship"

    # shipping → done → done
    run sprint_next_step "shipping"
    assert_output "done"

    run sprint_next_step "done"
    assert_output "done"
}

# ─── 19. sprint_next_step returns brainstorm for unknown phase ───────

@test "sprint_next_step returns brainstorm for unknown phase input" {
    _source_sprint_lib

    run sprint_next_step "nonexistent-phase"
    assert_output "brainstorm"

    run sprint_next_step "garbage"
    assert_output "brainstorm"
}

# ─── 20. sprint_invalidate_caches removes cache files ────────────────

@test "sprint_invalidate_caches removes cache files" {
    _source_sprint_lib

    # Create several cache files
    touch /tmp/clavain-discovery-brief-aaa.cache
    touch /tmp/clavain-discovery-brief-bbb.cache
    touch /tmp/clavain-discovery-brief-ccc.cache

    sprint_invalidate_caches

    [[ ! -f /tmp/clavain-discovery-brief-aaa.cache ]]
    [[ ! -f /tmp/clavain-discovery-brief-bbb.cache ]]
    [[ ! -f /tmp/clavain-discovery-brief-ccc.cache ]]
}

# ─── 21. sprint_find_active returns "[]" when bd not available ───────

@test "sprint_find_active returns empty array when bd not available" {
    # Ensure bd is NOT available
    unset -f bd 2>/dev/null || true

    # Override PATH to exclude any real bd
    export PATH="/usr/bin:/bin"

    _source_sprint_lib
    run sprint_find_active
    assert_success
    assert_output "[]"
}

# ─── 22. sprint_create returns "" when bd fails ─────────────────────

@test "sprint_create returns empty string when bd fails" {
    # Ensure bd is NOT available
    unset -f bd 2>/dev/null || true

    # Override PATH to exclude any real bd
    export PATH="/usr/bin:/bin"

    _source_sprint_lib
    run sprint_create "Should Fail"
    assert_success
    assert_output ""
}

# ─── 23. enforce_gate wrapper delegates to check_phase_gate ──────────

@test "enforce_gate wrapper delegates to check_phase_gate" {
    bd() { return 0; }
    export -f bd

    _source_sprint_lib

    # Define mock AFTER sourcing (lib-gates.sh stub would overwrite if before)
    check_phase_gate() {
        echo "gate_called: $1 $2 $3"
        return 0
    }

    run enforce_gate "iv-test1" "planned" "/tmp/artifact.md"
    assert_success
    assert_output "gate_called: iv-test1 planned /tmp/artifact.md"
}

# ═══════════════════════════════════════════════════════════════════
# Phase 2 Tests: Auto-Advance, Pause, Complexity Classification
# ═══════════════════════════════════════════════════════════════════

# ─── 24. _sprint_transition_table maps all phases correctly ────────────

@test "_sprint_transition_table maps all phases correctly" {
    bd() { return 0; }
    export -f bd
    _source_sprint_lib

    run _sprint_transition_table "brainstorm"
    assert_output "brainstorm-reviewed"

    run _sprint_transition_table "brainstorm-reviewed"
    assert_output "strategized"

    run _sprint_transition_table "strategized"
    assert_output "planned"

    run _sprint_transition_table "planned"
    assert_output "plan-reviewed"

    run _sprint_transition_table "plan-reviewed"
    assert_output "executing"

    run _sprint_transition_table "executing"
    assert_output "shipping"

    run _sprint_transition_table "shipping"
    assert_output "done"
}

# ─── 25. _sprint_transition_table returns empty for unknown phase ──────

@test "_sprint_transition_table returns empty for unknown phase" {
    bd() { return 0; }
    export -f bd
    _source_sprint_lib

    run _sprint_transition_table "nonexistent"
    assert_output ""
}

# ─── 26. _sprint_transition_table done→done (terminal) ────────────────

@test "_sprint_transition_table done→done (terminal)" {
    bd() { return 0; }
    export -f bd
    _source_sprint_lib

    run _sprint_transition_table "done"
    assert_output "done"
}

# ─── 27. sprint_should_pause returns 1 when auto_advance=true ─────────

@test "sprint_should_pause returns 1 when auto_advance=true" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    auto_advance) echo "true" ;;
                    *) echo "" ;;
                esac
                ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_should_pause "iv-test1" "strategized"
    assert_failure  # returns 1 = continue (no pause)
    assert_output ""
}

# ─── 28. sprint_should_pause returns 0 when auto_advance=false ────────

@test "sprint_should_pause returns 0 when auto_advance=false" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    auto_advance) echo "false" ;;
                    *) echo "" ;;
                esac
                ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_should_pause "iv-test1" "strategized"
    assert_success  # returns 0 = pause
    assert_output "manual_pause|strategized|auto_advance=false"
}

# ─── 29. sprint_should_pause returns 0 when gate blocks ───────────────

@test "sprint_should_pause returns 0 when gate blocks" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    auto_advance) echo "true" ;;
                    *) echo "" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _source_sprint_lib

    # Override enforce_gate to simulate gate failure
    enforce_gate() { return 1; }

    run sprint_should_pause "iv-test1" "executing"
    assert_success  # returns 0 = pause
    assert_output "gate_blocked|executing|Gate prerequisites not met"
}

# ─── 30. sprint_advance succeeds and advances phase ───────────────────

@test "sprint_advance succeeds and advances phase" {
    local _set_state_calls=""
    bd() {
        case "$1" in
            state)
                case "$3" in
                    auto_advance) echo "true" ;;
                    phase) echo "brainstorm" ;;
                    phase_history) echo "{}" ;;
                    *) echo "" ;;
                esac
                ;;
            set-state)
                echo "bd set-state $*" >> "$BD_CALL_LOG"
                return 0
                ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    # sprint_advance sends status to stderr; BATS `run` merges stderr into $output
    run sprint_advance "iv-test1" "brainstorm"
    assert_success
    # Status message appears in output (BATS captures stderr via 2>&1)
    assert_output "Phase: brainstorm → brainstorm-reviewed (auto-advancing)"

    # Verify phase was set
    grep -q "phase=brainstorm-reviewed" "$BD_CALL_LOG"
}

# ─── 31. sprint_advance pauses on manual override ─────────────────────

@test "sprint_advance pauses on manual override" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    auto_advance) echo "false" ;;
                    *) echo "" ;;
                esac
                ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_advance "iv-test1" "brainstorm"
    assert_failure  # returns 1 = paused
    assert_output "manual_pause|brainstorm-reviewed|auto_advance=false"
}

# ─── 32. sprint_advance returns 1 for unknown phase ──────────────────

@test "sprint_advance returns 1 for unknown phase" {
    bd() { return 0; }
    export -f bd
    _source_sprint_lib

    run sprint_advance "iv-test1" "nonexistent"
    assert_failure
}

# ─── 33. sprint_classify_complexity returns simple for short descriptions

@test "sprint_classify_complexity returns simple for short descriptions" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_classify_complexity "" "Add a logout button to the header"
    assert_output "simple"
}

# ─── 34. sprint_classify_complexity returns complex for long+ambiguous ─

@test "sprint_classify_complexity returns complex for long descriptions with ambiguity" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    # Generate a 120-word description with ambiguity signals
    local desc="We need to implement a new authentication system. There are several approach options to consider. We could use OAuth or JWT or session tokens. The alternative of using SAML vs OpenID is also worth exploring. Each approach has tradeoffs. The system should handle login logout registration password reset email verification two factor authentication social login guest access API keys service accounts webhook authentication rate limiting IP blocking geo restrictions audit logging compliance reporting GDPR consent management data export account deletion team management roles permissions"
    run sprint_classify_complexity "" "$desc"
    assert_output "complex"
}

# ─── 35. sprint_classify_complexity respects manual override ──────────

@test "sprint_classify_complexity respects manual override on bead" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    complexity) echo "complex" ;;
                esac
                ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    # Even though description is short, manual override wins
    run sprint_classify_complexity "iv-test1" "Simple task"
    assert_output "complex"
}

# ─── 36. sprint_classify_complexity returns medium for empty description

@test "sprint_classify_complexity returns medium for empty description" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_classify_complexity "" ""
    assert_output "medium"
}

# ─── 37. sprint_classify_complexity respects simplicity signals ────────

@test "sprint_classify_complexity respects simplicity signals" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    # 40 words (medium by word count) but heavy simplicity signals should pull to simple
    local desc="This is just like the existing login page, similar to what we already have. Just add a simple straightforward existing pattern. Like the similar existing approach we just used for the other simple feature"
    run sprint_classify_complexity "" "$desc"
    assert_output "simple"
}

# ─── 38. sprint_classify_complexity vacuous (<5 words) returns medium ──

@test "sprint_classify_complexity vacuous (<5 words) returns medium" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_classify_complexity "" "Make it better"
    assert_output "medium"
}

# ─── 39. sprint_classify_complexity boundary: 30 words = medium ────────

@test "sprint_classify_complexity boundary: exactly 30 words = medium" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    # Generate exactly 30 words
    local desc="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone twentytwo twentythree twentyfour twentyfive twentysix twentyseven twentyeight twentynine thirty"
    run sprint_classify_complexity "" "$desc"
    assert_output "medium"
}

# ─── 40. sprint_advance rejects terminal→terminal (done→done) ─────────

@test "sprint_advance rejects terminal→terminal (done→done)" {
    bd() {
        case "$1" in
            state) echo "done" ;;
            set-state) return 0 ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_advance "iv-test1" "done"
    assert_failure
}
