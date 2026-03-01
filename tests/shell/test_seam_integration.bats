#!/usr/bin/env bats
# Seam integration tests — exercise lib-intercore.sh and lib-sprint.sh wrappers
# against a REAL ic binary and SQLite database. No mocks.
#
# These tests prove the kernel↔OS contract works end-to-end:
# wrapper functions → ic CLI → SQLite → back to bash callers.
#
# Requires: ic binary buildable from core/intercore, bats-support, bats-assert, jq

# ─── Setup / teardown ───────────────────────────────────────────

setup() {
    load test_helper

    # Build ic binary once per test file (cached in /tmp)
    IC_BIN="/tmp/ic-seam-$$"
    IC_SRC_DIR="$BATS_TEST_DIRNAME/../../../../core/intercore"
    if [[ ! -d "$IC_SRC_DIR" ]]; then
        skip "intercore source not available (standalone checkout)"
    fi
    if [[ ! -x "$IC_BIN" ]]; then
        cd "$IC_SRC_DIR" && go build -o "$IC_BIN" ./cmd/ic
    fi
    export PATH="${IC_BIN%/*}:$PATH"

    # Create isolated project directory with .clavain/intercore.db
    TEST_PROJECT="$(mktemp -d)"
    TEST_DB="$TEST_PROJECT/.clavain/intercore.db"
    mkdir -p "$TEST_PROJECT/.clavain"
    cd "$TEST_PROJECT"

    # Initialize DB
    "$IC_BIN" init --db="$TEST_DB"

    # Export for lib-intercore.sh
    export INTERCORE_DB="$TEST_DB"
    export SPRINT_LIB_PROJECT_DIR="$TEST_PROJECT"
    export HOME="$TEST_PROJECT"

    # Disable interphase/interlock plugin delegation
    export INTERPHASE_ROOT=""
    export INTERLOCK_ROOT=""

    # Clear source guards and load libraries
    unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED
    unset INTERCORE_BIN  # force re-detection

    # Source the real lib-intercore.sh
    source "$HOOKS_DIR/lib-intercore.sh"

    # Verify ic is found
    intercore_available || skip "ic binary not detected after sourcing lib-intercore.sh"
}

teardown() {
    rm -rf "$TEST_PROJECT" 2>/dev/null || true
    rm -f "$IC_BIN" 2>/dev/null || true
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 1: Wrapper smoke tests — do the wrappers produce correct CLI calls?
# ═══════════════════════════════════════════════════════════════════

@test "intercore_run_create creates a run and returns ID" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Test sprint" "" "" "3" "" "")
    [[ -n "$run_id" ]]
    # ID should be an alphanumeric string (base36 encoding)
    [[ "$run_id" =~ ^[a-z0-9]+$ ]]
}

@test "intercore_run_create with custom phases" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Custom phases" '["alpha","beta","done"]' "" "2" "" "")
    [[ -n "$run_id" ]]

    # Verify phase is at 'alpha' (first custom phase)
    local phase
    phase=$(intercore_run_phase "$run_id")
    [[ "$phase" == "alpha" ]]
}

@test "intercore_run_create with scope_id and token_budget" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Budgeted run" "" "my-scope-123" "3" "50000" "")
    [[ -n "$run_id" ]]

    # Verify via run status JSON
    local status_json
    status_json=$(intercore_run_status "$run_id")
    local budget scope
    budget=$(echo "$status_json" | jq -r '.token_budget')
    scope=$(echo "$status_json" | jq -r '.scope_id')
    [[ "$budget" == "50000" ]]
    [[ "$scope" == "my-scope-123" ]]
}

@test "intercore_run_list returns JSON array with active runs" {
    # Create a run first
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Listed run" "" "" "3" "" "")

    local list_json
    list_json=$(intercore_run_list "--active")
    [[ -n "$list_json" ]]

    # Should be a JSON array with at least one entry
    local count
    count=$(echo "$list_json" | jq 'length')
    [[ "$count" -ge 1 ]]

    # The run we created should be in the list
    local found
    found=$(echo "$list_json" | jq -r --arg id "$run_id" '[.[] | select(.id == $id)] | length')
    [[ "$found" == "1" ]]
}

@test "intercore_run_status returns JSON with expected fields" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Status test" "" "" "3" "" "")

    local status_json
    status_json=$(intercore_run_status "$run_id")

    # Verify expected fields exist
    local id phase goal status
    id=$(echo "$status_json" | jq -r '.id')
    phase=$(echo "$status_json" | jq -r '.phase')
    goal=$(echo "$status_json" | jq -r '.goal')
    status=$(echo "$status_json" | jq -r '.status')

    [[ "$id" == "$run_id" ]]
    [[ "$phase" == "brainstorm" ]]
    [[ "$goal" == "Status test" ]]
    [[ "$status" == "active" ]]
}

@test "intercore_run_agent_list returns empty array for new run" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Agent list test" "" "" "3" "" "")

    local agents_json
    agents_json=$(intercore_run_agent_list "$run_id")

    local count
    count=$(echo "$agents_json" | jq 'length')
    [[ "$count" == "0" ]]
}

@test "intercore_run_agent_add + agent_list roundtrip" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Agent roundtrip" "" "" "3" "" "")

    # Add an agent
    local agent_id
    agent_id=$(intercore_run_agent_add "$run_id" "session" "test-session-1")
    [[ -n "$agent_id" ]]

    # List agents — should find it
    local agents_json
    agents_json=$(intercore_run_agent_list "$run_id")
    local count
    count=$(echo "$agents_json" | jq 'length')
    [[ "$count" == "1" ]]

    local found_type found_name found_status
    found_type=$(echo "$agents_json" | jq -r '.[0].agent_type')
    found_name=$(echo "$agents_json" | jq -r '.[0].name')
    found_status=$(echo "$agents_json" | jq -r '.[0].status')
    [[ "$found_type" == "session" ]]
    [[ "$found_name" == "test-session-1" ]]
    [[ "$found_status" == "active" ]]
}

@test "intercore_run_agent_update changes status" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Agent update test" "" "" "3" "" "")

    local agent_id
    agent_id=$(intercore_run_agent_add "$run_id" "session" "update-test")

    # Update to completed
    intercore_run_agent_update "$agent_id" "completed"

    # Verify
    local agents_json status
    agents_json=$(intercore_run_agent_list "$run_id")
    status=$(echo "$agents_json" | jq -r '.[0].status')
    [[ "$status" == "completed" ]]
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 2: Sprint lifecycle — create → advance → gate → events
# ═══════════════════════════════════════════════════════════════════

@test "sprint lifecycle: create → advance through phases → events visible" {
    # Create a run with a short custom chain for fast testing
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Lifecycle test" '["phase-a","phase-b","done"]' "lifecycle-scope" "2" "" "")
    [[ -n "$run_id" ]]

    # Verify initial phase
    local phase
    phase=$(intercore_run_phase "$run_id")
    [[ "$phase" == "phase-a" ]]

    # Advance phase-a → phase-b
    local result
    result=$(intercore_run_advance "$run_id")
    local advanced to_phase
    advanced=$(echo "$result" | jq -r '.advanced')
    to_phase=$(echo "$result" | jq -r '.to_phase')
    [[ "$advanced" == "true" ]]
    [[ "$to_phase" == "phase-b" ]]

    # Verify phase updated
    phase=$(intercore_run_phase "$run_id")
    [[ "$phase" == "phase-b" ]]

    # Advance phase-b → done
    result=$(intercore_run_advance "$run_id")
    advanced=$(echo "$result" | jq -r '.advanced')
    to_phase=$(echo "$result" | jq -r '.to_phase')
    [[ "$advanced" == "true" ]]
    [[ "$to_phase" == "done" ]]

    # Verify run is now completed
    local status_json run_status
    status_json=$(intercore_run_status "$run_id")
    run_status=$(echo "$status_json" | jq -r '.status')
    [[ "$run_status" == "completed" ]]

    # Events should show the phase transitions
    local events
    events=$("$IC_BIN" events tail "$run_id" --db="$TEST_DB" 2>/dev/null)
    [[ -n "$events" ]]
    # Should see at least 2 advance events (phase-a→phase-b, phase-b→done)
    local advance_count
    advance_count=$(echo "$events" | grep -c "advance" || true)
    [[ "$advance_count" -ge 2 ]]
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 3: Artifact tracking through kernel
# ═══════════════════════════════════════════════════════════════════

@test "artifact: add and list roundtrip through wrappers" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Artifact test" "" "" "3" "" "")

    # Add an artifact
    local artifact_id
    artifact_id=$(intercore_run_artifact_add "$run_id" "brainstorm" "docs/brainstorms/test.md" "file")
    [[ -n "$artifact_id" ]]

    # List artifacts via ic CLI
    local artifacts_json
    artifacts_json=$("$IC_BIN" --json run artifact list "$run_id" --db="$TEST_DB" 2>/dev/null)
    local count
    count=$(echo "$artifacts_json" | jq 'length')
    [[ "$count" == "1" ]]

    local found_path found_phase
    found_path=$(echo "$artifacts_json" | jq -r '.[0].path')
    found_phase=$(echo "$artifacts_json" | jq -r '.[0].phase')
    [[ "$found_path" == "docs/brainstorms/test.md" ]]
    [[ "$found_phase" == "brainstorm" ]]
}

@test "artifact: gate check sees artifact (hard gate pass)" {
    # Create run with custom phases and gate rule requiring artifact at step1→step2
    # Key format uses → arrow: "from→to"
    local gates_json='{"step1→step2":[{"check":"artifact_exists","phase":"step1","tier":"hard"}]}'
    local run_id
    run_id=$("$IC_BIN" run create --project="$TEST_PROJECT" --goal="Gate artifact test" \
        --phases='["step1","step2","done"]' --gates="$gates_json" --db="$TEST_DB" 2>/dev/null)
    [[ -n "$run_id" ]]

    # Gate should FAIL without artifact (hard gate blocks)
    local rc=0
    "$IC_BIN" gate check "$run_id" --db="$TEST_DB" >/dev/null 2>&1 || rc=$?
    [[ "$rc" -eq 1 ]]

    # Add artifact for step1
    intercore_run_artifact_add "$run_id" "step1" "docs/brainstorm.md" "file"

    # Gate should PASS now
    rc=0
    "$IC_BIN" gate check "$run_id" --db="$TEST_DB" >/dev/null 2>&1 || rc=$?
    [[ "$rc" -eq 0 ]]
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 4: Agent claim/release with lock contention
# ═══════════════════════════════════════════════════════════════════

@test "lock: acquire and release via wrappers" {
    # Acquire a lock
    local rc=0
    intercore_lock "seam-test" "test-scope" "500ms" || rc=$?
    [[ "$rc" -eq 0 ]]

    # Release
    intercore_unlock "seam-test" "test-scope"

    # Should be able to re-acquire after release
    rc=0
    intercore_lock "seam-test" "test-scope" "500ms" || rc=$?
    [[ "$rc" -eq 0 ]]
    intercore_unlock "seam-test" "test-scope"
}

@test "agent: add active session, verify via agent_list, update to completed" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Agent lifecycle" "" "" "3" "" "")

    # Add session agent
    local agent_id
    agent_id=$(intercore_run_agent_add "$run_id" "session" "session-alpha")
    [[ -n "$agent_id" ]]

    # Verify active via list
    local agents_json active_count
    agents_json=$(intercore_run_agent_list "$run_id")
    active_count=$(echo "$agents_json" | jq '[.[] | select(.status == "active")] | length')
    [[ "$active_count" == "1" ]]

    # Mark completed
    intercore_run_agent_update "$agent_id" "completed"

    # No more active agents
    agents_json=$(intercore_run_agent_list "$run_id")
    active_count=$(echo "$agents_json" | jq '[.[] | select(.status == "active")] | length')
    [[ "$active_count" == "0" ]]
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 5: Budget enforcement blocks advance
# ═══════════════════════════════════════════════════════════════════

@test "budget: run with enforced budget reports exceeded via JSON" {
    # Create run with tight budget + enforcement
    local run_id
    run_id=$("$IC_BIN" run create --project="$TEST_PROJECT" --goal="Budget test" \
        --token-budget=100 --budget-enforce --db="$TEST_DB" 2>/dev/null)
    [[ -n "$run_id" ]]

    # Create a prompt file (required by dispatch spawn)
    echo "test prompt" > "$TEST_PROJECT/prompt.txt"

    # Spawn a dispatch linked to this run via scope-id (= run_id for budget aggregation)
    local dispatch_id
    dispatch_id=$("$IC_BIN" dispatch spawn --prompt-file="$TEST_PROJECT/prompt.txt" \
        --project="$TEST_PROJECT" --name="budget-agent" --scope-id="$run_id" \
        --db="$TEST_DB" 2>/dev/null)
    [[ -n "$dispatch_id" ]]

    # Report tokens (200 > budget of 100)
    # Note: dispatch tokens triggers an inline budget check that sets the dedup flag,
    # so subsequent run budget calls won't return exceeded=true (by design — fire-once).
    # We verify via JSON that used > budget.
    "$IC_BIN" dispatch tokens "$dispatch_id" --in=150 --out=50 --db="$TEST_DB" 2>/dev/null

    # Verify budget state via JSON: used should exceed budget
    local budget_json
    budget_json=$("$IC_BIN" --json run budget "$run_id" --db="$TEST_DB" 2>/dev/null)
    local used budget_val
    used=$(echo "$budget_json" | jq -r '.used')
    budget_val=$(echo "$budget_json" | jq -r '.budget')
    [[ "$used" -ge "$budget_val" ]]
    [[ "$used" -eq 200 ]]
    [[ "$budget_val" -eq 100 ]]
}

@test "budget: run under budget allows advance" {
    local run_id
    run_id=$("$IC_BIN" run create --project="$TEST_PROJECT" --goal="Budget pass test" \
        --token-budget=100000 --budget-enforce --db="$TEST_DB" 2>/dev/null)
    [[ -n "$run_id" ]]

    # Budget check should pass (no tokens reported yet = 0 < 100000)
    local rc=0
    "$IC_BIN" run budget "$run_id" --db="$TEST_DB" 2>/dev/null || rc=$?
    [[ "$rc" -eq 0 ]]

    # Advance should succeed
    local result
    result=$("$IC_BIN" --json run advance "$run_id" --db="$TEST_DB" 2>/dev/null)
    local advanced
    advanced=$(echo "$result" | jq -r '.advanced')
    [[ "$advanced" == "true" ]]
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 6: Event bus visibility from sprint operations
# ═══════════════════════════════════════════════════════════════════

@test "events: phase transitions visible via events tail" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Event visibility test" '["step1","step2","done"]' "" "2" "" "")

    # Advance twice
    intercore_run_advance "$run_id" >/dev/null
    intercore_run_advance "$run_id" >/dev/null

    # Events tail should show transitions
    local events
    events=$("$IC_BIN" events tail "$run_id" --db="$TEST_DB" 2>/dev/null)
    [[ -n "$events" ]]

    # Should contain phase transition markers
    echo "$events" | grep -q "step1" || false
    echo "$events" | grep -q "step2" || false
}

@test "events: consumer cursor tracks position" {
    local run_id
    run_id=$(intercore_run_create "$TEST_PROJECT" "Cursor test" '["a","b","done"]' "" "2" "" "")

    # Advance once
    intercore_run_advance "$run_id" >/dev/null

    # Read with consumer cursor
    local events1
    events1=$("$IC_BIN" events tail "$run_id" --consumer=test-consumer --db="$TEST_DB" 2>/dev/null)
    [[ -n "$events1" ]]

    # Second read with same consumer should be empty (cursor past all events)
    local events2
    events2=$("$IC_BIN" events tail "$run_id" --consumer=test-consumer --db="$TEST_DB" 2>/dev/null)
    [[ -z "$events2" ]]

    # Advance again
    intercore_run_advance "$run_id" >/dev/null

    # Now consumer should see the new event only
    local events3
    events3=$("$IC_BIN" events tail "$run_id" --consumer=test-consumer --db="$TEST_DB" 2>/dev/null)
    [[ -n "$events3" ]]
}

@test "events: tail --all shows events across multiple runs" {
    local run1 run2
    run1=$(intercore_run_create "$TEST_PROJECT" "Run 1" '["x","done"]' "" "2" "" "")
    run2=$(intercore_run_create "$TEST_PROJECT" "Run 2" '["y","done"]' "" "2" "" "")

    intercore_run_advance "$run1" >/dev/null
    intercore_run_advance "$run2" >/dev/null

    local events
    events=$("$IC_BIN" events tail --all --db="$TEST_DB" 2>/dev/null)
    [[ -n "$events" ]]

    # Should contain events from both runs
    echo "$events" | grep -q "$run1" || false
    echo "$events" | grep -q "$run2" || false
}
