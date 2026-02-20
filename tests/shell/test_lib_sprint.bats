#!/usr/bin/env bats
# Tests for hooks/lib-sprint.sh — sprint state library for Clavain.
# All sprint state flows through intercore (ic). Tests mock intercore_* wrappers.

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
    rm -rf /tmp/intercore/locks/sprint-claim 2>/dev/null || true

    # Clean up discovery caches
    rm -f /tmp/clavain-discovery-brief-*.cache 2>/dev/null || true

    # BD_CALL_LOG tracks calls to mock bd for verification
    BD_CALL_LOG="$TEST_PROJECT/bd_calls.log"
    export BD_CALL_LOG

    # IC_CALL_LOG tracks calls to mock intercore_* for verification
    IC_CALL_LOG="$TEST_PROJECT/ic_calls.log"
    export IC_CALL_LOG
}

teardown() {
    rm -rf "$TEST_PROJECT" 2>/dev/null || true
    rm -rf /tmp/sprint-lock-* /tmp/sprint-claim-lock-* /tmp/sprint-advance-lock-* 2>/dev/null || true
    rm -rf /tmp/intercore/locks/sprint-claim 2>/dev/null || true
    rm -f /tmp/clavain-discovery-brief-*.cache 2>/dev/null || true
    unset -f bd 2>/dev/null || true
}

# Helper: source lib-sprint.sh with guards cleared
_source_sprint_lib() {
    unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED
    source "$HOOKS_DIR/lib-sprint.sh"
}

# Helper: set up standard intercore mocks that make ic "available"
# Override individual functions in tests as needed AFTER calling this + _source_sprint_lib
_mock_intercore_available() {
    # Make intercore_available return 0 (available)
    INTERCORE_BIN="/usr/bin/true"
    export INTERCORE_BIN
}

# ═══════════════════════════════════════════════════════════════════
# sprint_require_ic tests
# ═══════════════════════════════════════════════════════════════════

# ─── 1. sprint_require_ic succeeds when ic available ──────────────

@test "sprint_require_ic succeeds when ic available" {
    _mock_intercore_available
    _source_sprint_lib
    run sprint_require_ic
    assert_success
}

# ─── 2. sprint_require_ic fails when ic unavailable ──────────────

@test "sprint_require_ic fails when ic unavailable" {
    INTERCORE_BIN=""
    export INTERCORE_BIN
    # Override PATH to exclude any real ic
    export PATH="/usr/bin:/bin"

    _source_sprint_lib

    # Ensure intercore_available returns 1
    intercore_available() { return 1; }

    run sprint_require_ic
    assert_failure
    [[ "$output" == *"Sprint requires intercore"* ]]
}

# ═══════════════════════════════════════════════════════════════════
# _sprint_resolve_run_id tests
# ═══════════════════════════════════════════════════════════════════

# ─── 3. _sprint_resolve_run_id caches on first call ──────────────

@test "_sprint_resolve_run_id caches run_id and reuses on second call" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-abc-123" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Note: $() runs in a subshell, so cache from first call doesn't survive.
    # Test caching by calling directly in the current shell and checking the log.

    # First call — populates cache
    _sprint_resolve_run_id "iv-test1" >/dev/null
    local bd_count_first
    bd_count_first=$(grep -c "state iv-test1 ic_run_id" "$BD_CALL_LOG")
    [[ "$bd_count_first" -eq 1 ]]

    # Second call in same shell — should use cache (no new bd call)
    _sprint_resolve_run_id "iv-test1" >/dev/null
    local bd_count_second
    bd_count_second=$(grep -c "state iv-test1 ic_run_id" "$BD_CALL_LOG")
    [[ "$bd_count_second" -eq 1 ]]

    # Verify we can get the cached value
    local cached="${_SPRINT_RUN_ID_CACHE[iv-test1]:-}"
    [[ "$cached" == "run-abc-123" ]]
}

# ─── 4. _sprint_resolve_run_id returns empty for missing run ─────

@test "_sprint_resolve_run_id returns empty when no ic_run_id on bead" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    run _sprint_resolve_run_id "iv-orphan"
    assert_failure
    assert_output ""
}

# ═══════════════════════════════════════════════════════════════════
# sprint_create tests
# ═══════════════════════════════════════════════════════════════════

# ─── 5. sprint_create returns bead ID on success ─────────────────

@test "sprint_create returns bead ID on success" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            create) echo "Created iv-test1" ;;
            set-state) return 0 ;;
            update) return 0 ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Mock intercore_run_create to return a run ID
    intercore_run_create() { echo "run-001"; return 0; }
    # Mock intercore_run_phase to verify phase
    intercore_run_phase() { echo "brainstorm"; return 0; }

    run sprint_create "My Sprint"
    assert_success
    assert_output "iv-test1"
}

# ─── 6. sprint_create fails when ic run creation fails ───────────

@test "sprint_create cancels bead when ic run creation fails" {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            create) echo "Created iv-fail1" ;;
            set-state) return 0 ;;
            update) return 0 ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Mock ic run create to fail
    intercore_run_create() { echo ""; return 1; }

    run sprint_create "Failing Sprint"
    assert_failure

    # Verify cancel was called on the bead
    run grep "update iv-fail1 --status=cancelled" "$BD_CALL_LOG"
    assert_success
}

# ─── 7. sprint_create fails when ic unavailable ─────────────────

@test "sprint_create fails when ic unavailable" {
    _source_sprint_lib

    # Override intercore_available to return false
    intercore_available() { return 1; }

    run sprint_create "Should Fail"
    assert_failure
    # stderr message is captured by run — just check it contains the error
    [[ "$output" == *"Sprint requires intercore"* ]] || [[ -z "$output" ]]
}

# ═══════════════════════════════════════════════════════════════════
# sprint_find_active tests
# ═══════════════════════════════════════════════════════════════════

# ─── 8. sprint_find_active returns runs from intercore ───────────

@test "sprint_find_active returns active runs from intercore" {
    _mock_intercore_available
    _source_sprint_lib

    # Mock intercore_run_list to return active runs
    intercore_run_list() {
        echo '[{"id":"run-001","scope_id":"iv-s1","phase":"executing","goal":"Sprint 1"},
               {"id":"run-002","scope_id":"iv-s2","phase":"planned","goal":"Sprint 2"}]'
    }

    run sprint_find_active
    assert_success

    local result="$output"
    echo "$result" | jq -e 'length == 2'
    echo "$result" | jq -e '.[0].id == "iv-s1"'
    echo "$result" | jq -e '.[0].phase == "executing"'
    echo "$result" | jq -e '.[1].id == "iv-s2"'
}

# ─── 9. sprint_find_active returns [] when ic unavailable ────────

@test "sprint_find_active returns empty array when ic unavailable" {
    _source_sprint_lib

    intercore_available() { return 1; }

    run sprint_find_active
    assert_success
    # Output includes stderr ("Sprint requires intercore...") + "[]" on stdout
    # Check last line is "[]"
    local last_line
    last_line=$(echo "$output" | tail -1)
    [[ "$last_line" == "[]" ]]
}

# ═══════════════════════════════════════════════════════════════════
# sprint_read_state tests
# ═══════════════════════════════════════════════════════════════════

# ─── 10. sprint_read_state returns all fields as valid JSON ──────

@test "sprint_read_state returns all fields as valid JSON" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Mock intercore_run_status
    intercore_run_status() {
        echo '{"phase":"executing","complexity":3,"auto_advance":true,"token_budget":250000}'
    }

    # Mock ic run artifact list (called directly via $INTERCORE_BIN)
    # We need to make INTERCORE_BIN point to a script that handles run artifact list
    local mock_bin="$TEST_PROJECT/mock_ic"
    cat > "$mock_bin" << 'MOCKEOF'
#!/bin/bash
case "$1 $2" in
    "run artifact") echo '[{"type":"brainstorm","path":"/tmp/bs.md"}]' ;;
    "run events")   echo '[{"event_type":"advance","to_phase":"brainstorm","created_at":"2026-01-01T00:00:00Z"}]' ;;
    "run tokens")   echo '{"input_tokens":5000,"output_tokens":3000}' ;;
    "health")       exit 0 ;;
    *)              echo '{}' ;;
esac
MOCKEOF
    chmod +x "$mock_bin"
    INTERCORE_BIN="$mock_bin"

    # Mock intercore_run_agent_list
    intercore_run_agent_list() {
        echo '[{"name":"sess-123","status":"active","agent_type":"session"}]'
    }

    run sprint_read_state "iv-test1"
    assert_success

    # Validate it's valid JSON
    echo "$output" | jq empty

    # Check fields
    echo "$output" | jq -e '.id == "iv-test1"'
    echo "$output" | jq -e '.phase == "executing"'
    echo "$output" | jq -e '.artifacts.brainstorm == "/tmp/bs.md"'
    echo "$output" | jq -e '.history.brainstorm_at == "2026-01-01T00:00:00Z"'
    echo "$output" | jq -e '.complexity == "3"'
    echo "$output" | jq -e '.active_session == "sess-123"'
    echo "$output" | jq -e '.tokens_spent == 8000'
}

# ─── 11. sprint_read_state returns {} for empty sprint_id ────────

@test "sprint_read_state returns {} for empty sprint_id" {
    _mock_intercore_available
    _source_sprint_lib

    run sprint_read_state ""
    assert_success
    assert_output "{}"
}

# ═══════════════════════════════════════════════════════════════════
# sprint_set_artifact tests
# ═══════════════════════════════════════════════════════════════════

# ─── 12. sprint_set_artifact records artifact via intercore ──────

@test "sprint_set_artifact records artifact via intercore" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Mock intercore_run_phase and intercore_run_artifact_add
    intercore_run_phase() { echo "brainstorm"; }
    intercore_run_artifact_add() {
        echo "ic artifact_add $*" >> "$IC_CALL_LOG"
        return 0
    }

    run sprint_set_artifact "iv-test1" "brainstorm" "/tmp/brainstorm.md"
    assert_success

    # Verify artifact_add was called with correct args
    run grep "run-001 brainstorm /tmp/brainstorm.md brainstorm" "$IC_CALL_LOG"
    assert_success
}

# ═══════════════════════════════════════════════════════════════════
# sprint_record_phase_completion tests
# ═══════════════════════════════════════════════════════════════════

# ─── 13. sprint_record_phase_completion invalidates caches ───────

@test "sprint_record_phase_completion invalidates discovery caches" {
    _source_sprint_lib

    # Override intercore_state_delete_all to just do the file cleanup
    intercore_state_delete_all() {
        local _key="$1" glob="$2"
        rm -f $glob 2>/dev/null || true
    }

    # Create a cache file
    touch /tmp/clavain-discovery-brief-test123.cache

    sprint_record_phase_completion "iv-test1" "brainstorm"

    # Cache should be deleted
    [[ ! -f /tmp/clavain-discovery-brief-test123.cache ]]
}

# ═══════════════════════════════════════════════════════════════════
# sprint_claim / sprint_release tests
# ═══════════════════════════════════════════════════════════════════

# ─── 14. sprint_claim succeeds for first claimer ─────────────────

@test "sprint_claim succeeds for first claimer" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Mock: no active agents
    intercore_run_agent_list() { echo '[]'; }
    intercore_run_agent_add() { echo "agent-001"; return 0; }
    intercore_lock() { return 0; }
    intercore_unlock() { return 0; }

    run sprint_claim "iv-test1" "session-abc"
    assert_success
}

# ─── 15. sprint_claim blocks second claimer ──────────────────────

@test "sprint_claim blocks second claimer with active session" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local now_ts
    now_ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Mock: one active session agent
    intercore_run_agent_list() {
        echo "[{\"id\":\"agent-001\",\"name\":\"session-first\",\"status\":\"active\",\"agent_type\":\"session\",\"created_at\":\"$IC_NOW_TS\"}]"
    }
    intercore_lock() { return 0; }
    intercore_unlock() { return 0; }
    export IC_NOW_TS="$now_ts"

    run sprint_claim "iv-test1" "session-second"
    assert_failure
}

# ─── 16. sprint_claim allows takeover after 60 min expiry ────────

@test "sprint_claim allows takeover after TTL expiry (61 minutes ago)" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local expired_ts
    expired_ts=$(date -u -d "61 minutes ago" +%Y-%m-%dT%H:%M:%SZ)

    # Mock: one expired session agent
    intercore_run_agent_list() {
        echo "[{\"id\":\"agent-old\",\"name\":\"session-old\",\"status\":\"active\",\"agent_type\":\"session\",\"created_at\":\"$IC_EXPIRED_TS\"}]"
    }
    intercore_run_agent_update() { return 0; }
    intercore_run_agent_add() { echo "agent-new"; return 0; }
    intercore_lock() { return 0; }
    intercore_unlock() { return 0; }
    export IC_EXPIRED_TS="$expired_ts"

    run sprint_claim "iv-test1" "session-new"
    assert_success
}

# ─── 17. sprint_claim blocks at 59 minutes (not yet expired) ────

@test "sprint_claim blocks at 59 minutes (not yet expired)" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local recent_ts
    recent_ts=$(date -u -d "59 minutes ago" +%Y-%m-%dT%H:%M:%SZ)

    intercore_run_agent_list() {
        echo "[{\"id\":\"agent-001\",\"name\":\"session-active\",\"status\":\"active\",\"agent_type\":\"session\",\"created_at\":\"$IC_RECENT_TS\"}]"
    }
    intercore_lock() { return 0; }
    intercore_unlock() { return 0; }
    export IC_RECENT_TS="$recent_ts"

    run sprint_claim "iv-test1" "session-wannabe"
    assert_failure
}

# ─── 18. sprint_claim re-claim by same session succeeds ──────────

@test "sprint_claim re-claim by same session succeeds" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local now_ts
    now_ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    intercore_run_agent_list() {
        echo "[{\"id\":\"agent-001\",\"name\":\"session-abc\",\"status\":\"active\",\"agent_type\":\"session\",\"created_at\":\"$IC_NOW_TS\"}]"
    }
    intercore_lock() { return 0; }
    intercore_unlock() { return 0; }
    export IC_NOW_TS="$now_ts"

    run sprint_claim "iv-test1" "session-abc"
    assert_success
}

# ─── 19. sprint_release marks active agents completed ────────────

@test "sprint_release marks active agents completed" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    intercore_run_agent_list() {
        echo '[{"id":"agent-001","name":"session-abc","status":"active","agent_type":"session"}]'
    }
    intercore_run_agent_update() {
        echo "ic agent_update $*" >> "$IC_CALL_LOG"
        return 0
    }

    run sprint_release "iv-test1"
    assert_success

    # Verify agent was marked completed
    run grep "agent-001 completed" "$IC_CALL_LOG"
    assert_success
}

# ═══════════════════════════════════════════════════════════════════
# sprint_next_step tests
# ═══════════════════════════════════════════════════════════════════

# ─── 20. sprint_next_step maps all phases correctly ──────────────

@test "sprint_next_step maps all phases correctly" {
    _source_sprint_lib

    # Empty/unknown phase → brainstorm (start from beginning)
    run sprint_next_step ""
    assert_output "brainstorm"

    run sprint_next_step "brainstorm"
    assert_output "strategy"

    run sprint_next_step "brainstorm-reviewed"
    assert_output "strategy"

    run sprint_next_step "strategized"
    assert_output "write-plan"

    run sprint_next_step "planned"
    assert_output "flux-drive"

    run sprint_next_step "plan-reviewed"
    assert_output "work"

    # executing → quality-gates (changed from old "ship")
    run sprint_next_step "executing"
    assert_output "quality-gates"

    # shipping → reflect (changed from old "done")
    run sprint_next_step "shipping"
    assert_output "reflect"

    run sprint_next_step "reflect"
    assert_output "done"

    run sprint_next_step "done"
    assert_output "done"
}

# ─── 21. sprint_next_step returns brainstorm for unknown phase ───

@test "sprint_next_step returns brainstorm for unknown phase input" {
    _source_sprint_lib

    run sprint_next_step "nonexistent-phase"
    assert_output "brainstorm"

    run sprint_next_step "garbage"
    assert_output "brainstorm"
}

# ═══════════════════════════════════════════════════════════════════
# sprint_invalidate_caches tests
# ═══════════════════════════════════════════════════════════════════

# ─── 22. sprint_invalidate_caches removes cache files ────────────

@test "sprint_invalidate_caches removes cache files" {
    _source_sprint_lib

    # Override intercore_state_delete_all to just do the file cleanup
    intercore_state_delete_all() {
        local _key="$1" glob="$2"
        rm -f $glob 2>/dev/null || true
    }

    # Create several cache files
    touch /tmp/clavain-discovery-brief-aaa.cache
    touch /tmp/clavain-discovery-brief-bbb.cache
    touch /tmp/clavain-discovery-brief-ccc.cache

    sprint_invalidate_caches

    [[ ! -f /tmp/clavain-discovery-brief-aaa.cache ]]
    [[ ! -f /tmp/clavain-discovery-brief-bbb.cache ]]
    [[ ! -f /tmp/clavain-discovery-brief-ccc.cache ]]
}

# ═══════════════════════════════════════════════════════════════════
# enforce_gate tests
# ═══════════════════════════════════════════════════════════════════

# ─── 23. enforce_gate delegates to intercore_gate_check ──────────

@test "enforce_gate delegates to intercore_gate_check" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    intercore_gate_check() {
        echo "gate_check $*" >> "$IC_CALL_LOG"
        return 0
    }

    run enforce_gate "iv-test1" "planned" "/tmp/artifact.md"
    assert_success

    run grep "gate_check run-001" "$IC_CALL_LOG"
    assert_success
}

# ═══════════════════════════════════════════════════════════════════
# sprint_should_pause tests
# ═══════════════════════════════════════════════════════════════════

# ─── 24. sprint_should_pause returns 1 when gate passes ──────────

@test "sprint_should_pause returns 1 (continue) when gate passes" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    intercore_gate_check() { return 0; }

    run sprint_should_pause "iv-test1" "strategized"
    assert_failure  # returns 1 = continue (no pause)
    assert_output ""
}

# ─── 25. sprint_should_pause returns 0 when gate blocks ─────────

@test "sprint_should_pause returns 0 (pause) when gate blocks" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    intercore_gate_check() { return 1; }

    run sprint_should_pause "iv-test1" "executing"
    assert_success  # returns 0 = pause
    assert_output "gate_blocked|executing|Gate prerequisites not met"
}

# ═══════════════════════════════════════════════════════════════════
# sprint_advance tests
# ═══════════════════════════════════════════════════════════════════

# ─── 26. sprint_advance succeeds and advances phase ──────────────

@test "sprint_advance succeeds and advances phase" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local mock_bin="$TEST_PROJECT/mock_ic"
    cat > "$mock_bin" << 'MOCKEOF'
#!/bin/bash
case "$1 $2" in
    "run budget") exit 0 ;;
    "run tokens") echo '{"input_tokens":1000,"output_tokens":500}' ;;
    "state get")  echo '{}' ;;
    "state set")  exit 0 ;;
    "health")     exit 0 ;;
    *)            exit 0 ;;
esac
MOCKEOF
    chmod +x "$mock_bin"
    INTERCORE_BIN="$mock_bin"

    # Mock intercore_run_advance to succeed
    intercore_run_advance() {
        echo '{"advanced":true,"from_phase":"brainstorm","to_phase":"brainstorm-reviewed"}'
    }

    # Mock intercore_state_get/set for token recording
    intercore_state_get() { echo "{}"; }
    intercore_state_set() { return 0; }

    # sprint_advance sends status to stderr; BATS `run` merges stderr into $output
    run sprint_advance "iv-test1" "brainstorm"
    assert_success
    # Status message appears in output (BATS captures stderr via 2>&1)
    assert_output "Phase: brainstorm → brainstorm-reviewed (auto-advancing)"
}

# ─── 27. sprint_advance returns pause when blocked ───────────────

@test "sprint_advance returns pause when blocked by gate" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local mock_bin="$TEST_PROJECT/mock_ic"
    cat > "$mock_bin" << 'MOCKEOF'
#!/bin/bash
case "$1 $2" in
    "run budget") exit 0 ;;
    "health")     exit 0 ;;
    *)            echo '{}' ;;
esac
MOCKEOF
    chmod +x "$mock_bin"
    INTERCORE_BIN="$mock_bin"

    # Mock intercore_run_advance to return block
    intercore_run_advance() {
        echo '{"advanced":false,"event_type":"block","to_phase":"brainstorm-reviewed"}'
    }

    run sprint_advance "iv-test1" "brainstorm"
    assert_failure
    assert_output "gate_blocked|brainstorm-reviewed|Gate prerequisites not met"
}

# ─── 28. sprint_advance returns pause on manual override ─────────

@test "sprint_advance returns pause on manual override" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local mock_bin="$TEST_PROJECT/mock_ic"
    cat > "$mock_bin" << 'MOCKEOF'
#!/bin/bash
case "$1 $2" in
    "run budget") exit 0 ;;
    "health")     exit 0 ;;
    *)            echo '{}' ;;
esac
MOCKEOF
    chmod +x "$mock_bin"
    INTERCORE_BIN="$mock_bin"

    # Mock intercore_run_advance to return pause
    intercore_run_advance() {
        echo '{"advanced":false,"event_type":"pause","to_phase":"brainstorm-reviewed"}'
    }

    run sprint_advance "iv-test1" "brainstorm"
    assert_failure  # returns 1 = paused
    assert_output "manual_pause|brainstorm-reviewed|auto_advance=false"
}

# ─── 29. sprint_advance returns 1 for no run_id ─────────────────

@test "sprint_advance returns 1 when no run_id" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_advance "iv-orphan" "brainstorm"
    assert_failure
}

# ─── 30. sprint_advance budget exceeded ──────────────────────────

@test "sprint_advance returns budget_exceeded when over budget" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    local mock_bin="$TEST_PROJECT/mock_ic"
    cat > "$mock_bin" << 'MOCKEOF'
#!/bin/bash
case "$1 $2" in
    "run budget") exit 1 ;;  # exceeded
    "run tokens") echo '{"input_tokens":300000,"output_tokens":200000}' ;;
    "run status") echo '{"token_budget":250000}' ;;
    "health")     exit 0 ;;
    *)            echo '{}' ;;
esac
MOCKEOF
    chmod +x "$mock_bin"
    INTERCORE_BIN="$mock_bin"

    # Also mock intercore_run_status for budget lookup
    intercore_run_status() {
        echo '{"token_budget":250000}'
    }

    run sprint_advance "iv-test1" "executing"
    assert_failure
    [[ "$output" == *"budget_exceeded"* ]]
}

# ═══════════════════════════════════════════════════════════════════
# sprint_classify_complexity tests
# ═══════════════════════════════════════════════════════════════════

# ─── 31. complexity returns 2 for short descriptions ─────────────

@test "sprint_classify_complexity returns 2 (simple) for short descriptions" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _mock_intercore_available
    _source_sprint_lib

    # Mock _sprint_resolve_run_id to return empty (no override)
    _sprint_resolve_run_id() { echo ""; return 1; }

    run sprint_classify_complexity "" "Add a logout button to the header"
    assert_output "2"
}

# ─── 32. complexity returns 4+ for long ambiguous descriptions ───

@test "sprint_classify_complexity returns complex for long descriptions with ambiguity" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _mock_intercore_available
    _source_sprint_lib

    _sprint_resolve_run_id() { echo ""; return 1; }

    # 120+ word description with ambiguity signals
    local desc="We need to implement a new authentication system. There are several approach options to consider. We could use OAuth or JWT or session tokens. The alternative of using SAML vs OpenID is also worth exploring. Each approach has tradeoffs. The system should handle login logout registration password reset email verification two factor authentication social login guest access API keys service accounts webhook authentication rate limiting IP blocking geo restrictions audit logging compliance reporting GDPR consent management data export account deletion team management roles permissions"
    run sprint_classify_complexity "" "$desc"
    # Should be 4 or 5 (complex or research)
    [[ "$output" -ge 4 ]]
}

# ─── 33. complexity respects manual override ─────────────────────

@test "sprint_classify_complexity respects manual override from ic" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                    complexity) echo "" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    # Mock intercore_run_status to return complexity override
    intercore_run_status() {
        echo '{"complexity":5}'
    }

    run sprint_classify_complexity "iv-test1" "Simple task"
    assert_output "5"
}

# ─── 34. complexity returns 3 for empty description ──────────────

@test "sprint_classify_complexity returns 3 (moderate) for empty description" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_classify_complexity "" ""
    assert_output "3"
}

# ─── 35. complexity respects simplicity signals ──────────────────

@test "sprint_classify_complexity respects simplicity signals" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    _sprint_resolve_run_id() { echo ""; return 1; }

    # 40 words (medium by word count) but heavy simplicity signals should pull down
    local desc="This is just like the existing login page, similar to what we already have. Just add a simple straightforward existing pattern. Like the similar existing approach we just used for the other simple feature"
    run sprint_classify_complexity "" "$desc"
    # Should be 2 (simple) — simplicity signals pull it down from 3
    assert_output "2"
}

# ─── 36. complexity vacuous (<5 words) returns 3 ─────────────────

@test "sprint_classify_complexity vacuous (<5 words) returns 3 (moderate)" {
    bd() {
        case "$1" in
            state) echo "" ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    run sprint_classify_complexity "" "Make it better"
    assert_output "3"
}

# ─── 37. complexity boundary: 30 words = 3 ──────────────────────

@test "sprint_classify_complexity boundary: exactly 30 words = 3 (moderate)" {
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
    assert_output "3"
}

# ═══════════════════════════════════════════════════════════════════
# checkpoint tests
# ═══════════════════════════════════════════════════════════════════

# ─── 38. checkpoint_write stores checkpoint in ic state ──────────

@test "checkpoint_write stores checkpoint in intercore state" {
    bd() {
        case "$1" in
            state)
                case "$3" in
                    ic_run_id) echo "run-001" ;;
                esac
                ;;
        esac
    }
    export -f bd

    _mock_intercore_available
    _source_sprint_lib

    intercore_state_get() { echo "{}"; }
    intercore_state_set() {
        echo "ic state_set $*" >> "$IC_CALL_LOG"
        return 0
    }

    run checkpoint_write "iv-test1" "brainstorm" "step1" "/tmp/plan.md" "Used approach A"
    assert_success

    # Verify state_set was called with checkpoint key
    run grep "state_set checkpoint run-001" "$IC_CALL_LOG"
    assert_success
}

# ─── 39. checkpoint_read returns {} when no checkpoint ───────────

@test "checkpoint_read returns {} when no checkpoint exists" {
    _source_sprint_lib

    # ic unavailable → returns {}
    intercore_available() { return 1; }

    run checkpoint_read "iv-test1"
    assert_success
    assert_output "{}"
}

# ─── 40. checkpoint_clear removes legacy file ────────────────────

@test "checkpoint_clear removes legacy checkpoint file" {
    _source_sprint_lib

    local ckpt_file="$TEST_PROJECT/.clavain/checkpoint.json"
    mkdir -p "$(dirname "$ckpt_file")"
    echo '{"phase":"brainstorm"}' > "$ckpt_file"
    export CLAVAIN_CHECKPOINT_FILE="$ckpt_file"

    checkpoint_clear

    [[ ! -f "$ckpt_file" ]]
}
