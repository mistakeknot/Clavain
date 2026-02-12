#!/usr/bin/env bats
# Tests for hooks/lib-gates.sh shared gate library

setup() {
    load test_helper

    # Create isolated temp project directory for each test
    TEST_PROJECT="$(mktemp -d)"
    export GATES_PROJECT_DIR="$TEST_PROJECT"
    export HOME="$TEST_PROJECT"

    # Create .beads directory
    mkdir -p "$TEST_PROJECT/.beads"

    # Reset the double-source guards so we can re-source in each test
    unset _GATES_LOADED
    unset _PHASE_LOADED
    source "$HOOKS_DIR/lib-gates.sh"

    # Default mock: bd available, no phase set
    mock_bd_no_phase
}

teardown() {
    rm -rf "$TEST_PROJECT"
}

# ─── Mock helpers ─────────────────────────────────────────────────────

# Mock bd that returns a given phase for `bd state` and succeeds for `bd set-state`
mock_bd_with_phase() {
    local phase="$1"
    export MOCK_BD_PHASE="$phase"
    bd() {
        if [[ "$1" == "state" ]]; then
            echo "$MOCK_BD_PHASE"
            return 0
        fi
        if [[ "$1" == "set-state" ]]; then
            return 0
        fi
        return 1
    }
    export -f bd
}

# Mock bd that returns empty for `bd state`
mock_bd_no_phase() {
    bd() {
        if [[ "$1" == "state" ]]; then
            echo ""
            return 0
        fi
        if [[ "$1" == "set-state" ]]; then
            return 0
        fi
        return 1
    }
    export -f bd
}

# Mock bd that is unavailable
mock_bd_unavailable() {
    unset -f bd 2>/dev/null || true
    local old_path="$PATH"
    export PATH="/nonexistent"
    # Need to re-source since phase_get checks command -v bd
    unset _GATES_LOADED _PHASE_LOADED
    source "$HOOKS_DIR/lib-gates.sh"
    export PATH="$old_path"
}

# ─── Source & init ────────────────────────────────────────────────────

@test "gates: sources without errors" {
    unset _GATES_LOADED _PHASE_LOADED
    run source "$HOOKS_DIR/lib-gates.sh"
    assert_success
}

@test "gates: double-source guard prevents reloading" {
    # _GATES_LOADED is already set from setup()
    [[ -n "$_GATES_LOADED" ]]
    # Source again — should return immediately
    source "$HOOKS_DIR/lib-gates.sh"
    # If we get here, guard worked (no errors from double-source)
    [[ "$_GATES_LOADED" == "1" ]]
}

@test "gates: inherits CLAVAIN_PHASES from lib-phase.sh" {
    [[ ${#CLAVAIN_PHASES[@]} -gt 0 ]]
    [[ "${CLAVAIN_PHASES[0]}" == "brainstorm" ]]
    [[ "${CLAVAIN_PHASES[-1]}" == "done" ]]
}

# ─── VALID_TRANSITIONS ───────────────────────────────────────────────

@test "transitions: array is non-empty" {
    [[ ${#VALID_TRANSITIONS[@]} -gt 0 ]]
}

@test "transitions: contains linear forward transitions" {
    local found_brainstorm_review=false
    local found_plan_execute=false
    local entry
    for entry in "${VALID_TRANSITIONS[@]}"; do
        [[ "$entry" == "brainstorm:brainstorm-reviewed" ]] && found_brainstorm_review=true
        [[ "$entry" == "plan-reviewed:executing" ]] && found_plan_execute=true
    done
    [[ "$found_brainstorm_review" == "true" ]]
    [[ "$found_plan_execute" == "true" ]]
}

@test "transitions: first-touch entry exists" {
    local found=false
    local entry
    for entry in "${VALID_TRANSITIONS[@]}"; do
        [[ "$entry" == ":brainstorm" ]] && found=true
    done
    [[ "$found" == "true" ]]
}

@test "transitions: all CLAVAIN_PHASES are reachable" {
    # Every phase should appear as a 'to' in at least one transition
    local phase
    for phase in "${CLAVAIN_PHASES[@]}"; do
        local found=false
        local entry
        for entry in "${VALID_TRANSITIONS[@]}"; do
            local to="${entry##*:}"
            if [[ "$to" == "$phase" ]]; then
                found=true
                break
            fi
        done
        [[ "$found" == "true" ]]
    done
}

# ─── is_valid_transition ─────────────────────────────────────────────

@test "is_valid_transition: valid forward transition" {
    run is_valid_transition "brainstorm" "brainstorm-reviewed"
    assert_success
}

@test "is_valid_transition: valid skip transition" {
    run is_valid_transition "brainstorm" "strategized"
    assert_success
}

@test "is_valid_transition: first-touch (empty to brainstorm)" {
    run is_valid_transition "" "brainstorm"
    assert_success
}

@test "is_valid_transition: first-touch (empty to executing)" {
    run is_valid_transition "" "executing"
    assert_success
}

@test "is_valid_transition: invalid backward transition" {
    run is_valid_transition "executing" "brainstorm"
    assert_failure
}

@test "is_valid_transition: invalid arbitrary skip" {
    run is_valid_transition "brainstorm" "done"
    assert_failure
}

@test "is_valid_transition: empty target returns failure" {
    run is_valid_transition "brainstorm" ""
    assert_failure
}

# ─── check_phase_gate ────────────────────────────────────────────────

@test "check_phase_gate: passes on valid transition" {
    mock_bd_with_phase "brainstorm"
    run check_phase_gate "Test-001" "brainstorm-reviewed"
    assert_success
}

@test "check_phase_gate: returns 1 on invalid transition" {
    mock_bd_with_phase "executing"
    run check_phase_gate "Test-001" "brainstorm"
    assert_failure
}

@test "check_phase_gate: stderr warning on invalid" {
    mock_bd_with_phase "executing"
    run check_phase_gate "Test-001" "brainstorm"
    assert_output --partial "WARNING: phase gate blocked"
}

@test "check_phase_gate: first-touch passes" {
    mock_bd_no_phase
    run check_phase_gate "Test-001" "brainstorm"
    assert_success
}

@test "check_phase_gate: fail-safe on empty bead_id" {
    run check_phase_gate "" "brainstorm"
    assert_success
}

@test "check_phase_gate: fail-safe on empty target" {
    run check_phase_gate "Test-001" ""
    assert_success
}

# ─── advance_phase ───────────────────────────────────────────────────

@test "advance_phase: calls phase_set (bead persistence)" {
    # Track whether bd set-state was called
    export MOCK_SET_STATE_CALLED=""
    bd() {
        if [[ "$1" == "set-state" ]]; then
            export MOCK_SET_STATE_CALLED="$2:$3"
            return 0
        fi
        return 0
    }
    export -f bd

    advance_phase "Test-001" "brainstorm" "Created brainstorm"
    [[ "$MOCK_SET_STATE_CALLED" == "Test-001:phase=brainstorm" ]]
}

@test "advance_phase: writes artifact header for brainstorms dir" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    local artifact="$TEST_PROJECT/docs/brainstorms/test-brainstorm.md"
    echo "# My Brainstorm" > "$artifact"

    advance_phase "Test-001" "brainstorm" "Created" "$artifact"

    grep -q '^\*\*Phase:\*\*' "$artifact"
    grep -q 'brainstorm' "$artifact"
}

@test "advance_phase: writes artifact header for plans dir" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    local artifact="$TEST_PROJECT/docs/plans/test-plan.md"
    echo "# My Plan" > "$artifact"

    advance_phase "Test-001" "planned" "Planned" "$artifact"

    grep -q '^\*\*Phase:\*\*' "$artifact"
    grep -q 'planned' "$artifact"
}

@test "advance_phase: skips PRD (not in ARTIFACT_PHASE_DIRS)" {
    mkdir -p "$TEST_PROJECT/docs/prds"
    local artifact="$TEST_PROJECT/docs/prds/test-prd.md"
    echo "# My PRD" > "$artifact"

    advance_phase "Test-001" "strategized" "PRD created" "$artifact"

    # PRD should NOT have Phase header
    ! grep -q '^\*\*Phase:\*\*' "$artifact"
}

@test "advance_phase: skips empty artifact path" {
    # Should succeed without errors even with no path
    run advance_phase "Test-001" "executing" "Started execution" ""
    assert_success
}

@test "advance_phase: fail-safe on empty bead_id" {
    run advance_phase "" "brainstorm" "test"
    assert_success
}

# ─── _gate_write_artifact_phase ──────────────────────────────────────

@test "_gate_write_artifact_phase: inserts after Bead line" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    local file="$TEST_PROJECT/docs/brainstorms/test.md"
    cat > "$file" << 'EOF'
# Brainstorm
**Bead:** Test-001
Some content here.
EOF

    _gate_write_artifact_phase "$file" "brainstorm"

    # Phase line should appear after Bead line
    local bead_line phase_line
    bead_line=$(grep -n '^\*\*Bead:\*\*' "$file" | head -1 | cut -d: -f1)
    phase_line=$(grep -n '^\*\*Phase:\*\*' "$file" | head -1 | cut -d: -f1)
    [[ "$phase_line" -eq $((bead_line + 1)) ]]
}

@test "_gate_write_artifact_phase: updates existing Phase line" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    local file="$TEST_PROJECT/docs/brainstorms/test.md"
    cat > "$file" << 'EOF'
# Brainstorm
**Bead:** Test-001
**Phase:** brainstorm (as of 2026-01-01T00:00:00Z)
Some content here.
EOF

    _gate_write_artifact_phase "$file" "brainstorm-reviewed"

    # Should have only one Phase line, updated to new value
    local count
    count=$(grep -c '^\*\*Phase:\*\*' "$file")
    [[ "$count" -eq 1 ]]
    grep -q 'brainstorm-reviewed' "$file"
    ! grep -q 'Phase:\*\* brainstorm ' "$file"
}

@test "_gate_write_artifact_phase: inserts after heading when no Bead line" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    local file="$TEST_PROJECT/docs/plans/test.md"
    cat > "$file" << 'EOF'
# My Plan
Some content here.
EOF

    _gate_write_artifact_phase "$file" "planned"

    grep -q '^\*\*Phase:\*\*' "$file"
    # Phase line should be after heading
    local heading_line phase_line
    heading_line=$(grep -n '^# ' "$file" | head -1 | cut -d: -f1)
    phase_line=$(grep -n '^\*\*Phase:\*\*' "$file" | head -1 | cut -d: -f1)
    [[ "$phase_line" -eq $((heading_line + 1)) ]]
}

@test "_gate_write_artifact_phase: skips file outside allowed dirs" {
    mkdir -p "$TEST_PROJECT/docs/prds"
    local file="$TEST_PROJECT/docs/prds/test.md"
    echo "# PRD" > "$file"

    _gate_write_artifact_phase "$file" "strategized"

    ! grep -q '^\*\*Phase:\*\*' "$file"
}

@test "_gate_write_artifact_phase: includes timestamp" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    local file="$TEST_PROJECT/docs/brainstorms/test.md"
    echo "# Brainstorm" > "$file"

    _gate_write_artifact_phase "$file" "brainstorm"

    grep -q 'as of' "$file"
}

@test "_gate_write_artifact_phase: silent on missing file" {
    run _gate_write_artifact_phase "/nonexistent/file.md" "brainstorm"
    assert_success
}

# ─── _gate_read_artifact_phase ───────────────────────────────────────

@test "_gate_read_artifact_phase: extracts phase value" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    local file="$TEST_PROJECT/docs/brainstorms/test.md"
    cat > "$file" << 'EOF'
# Brainstorm
**Bead:** Test-001
**Phase:** brainstorm-reviewed (as of 2026-02-12T10:00:00Z)
Content.
EOF

    run _gate_read_artifact_phase "$file"
    assert_success
    assert_output "brainstorm-reviewed"
}

@test "_gate_read_artifact_phase: empty when no Phase header" {
    local file="$TEST_PROJECT/test.md"
    echo "# No phase" > "$file"

    run _gate_read_artifact_phase "$file"
    assert_success
    assert_output ""
}

@test "_gate_read_artifact_phase: strips timestamp" {
    local file="$TEST_PROJECT/test.md"
    echo '**Phase:** executing (as of 2026-02-12T10:00:00Z)' > "$file"

    run _gate_read_artifact_phase "$file"
    assert_success
    assert_output "executing"
}

@test "_gate_read_artifact_phase: empty for missing file" {
    run _gate_read_artifact_phase "/nonexistent/file.md"
    assert_success
    assert_output ""
}

# ─── phase_get_with_fallback ─────────────────────────────────────────

@test "phase_get_with_fallback: returns beads phase when available" {
    mock_bd_with_phase "planned"
    run phase_get_with_fallback "Test-001"
    assert_success
    assert_output "planned"
}

@test "phase_get_with_fallback: falls back to artifact" {
    mock_bd_no_phase
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    local file="$TEST_PROJECT/docs/brainstorms/test.md"
    echo '**Phase:** brainstorm (as of 2026-02-12T00:00:00Z)' > "$file"

    run phase_get_with_fallback "Test-001" "$file"
    assert_success
    assert_output "brainstorm"
}

@test "phase_get_with_fallback: warns on desync" {
    mock_bd_with_phase "executing"
    mkdir -p "$TEST_PROJECT/docs/plans"
    local file="$TEST_PROJECT/docs/plans/test.md"
    echo '**Phase:** planned (as of 2026-02-12T00:00:00Z)' > "$file"

    run phase_get_with_fallback "Test-001" "$file"
    assert_success
    # Should return beads phase (primary)
    [[ "${lines[0]}" == *"WARNING: phase desync"* || "${lines[-1]}" == "executing" ]]
    assert_output --partial "executing"
}

@test "phase_get_with_fallback: empty when both fail" {
    mock_bd_no_phase
    run phase_get_with_fallback "Test-001" "/nonexistent.md"
    assert_success
    assert_output ""
}

# ─── Telemetry ────────────────────────────────────────────────────────

@test "telemetry: gate_check event is valid JSONL" {
    _gate_log_check "Test-001" "brainstorm" "brainstorm-reviewed" "pass"

    local file="$TEST_PROJECT/.clavain/telemetry.jsonl"
    [[ -f "$file" ]]
    local line
    line=$(cat "$file")
    echo "$line" | jq empty  # Validate JSON
    [[ $(echo "$line" | jq -r '.event') == "gate_check" ]]
    [[ $(echo "$line" | jq -r '.bead') == "Test-001" ]]
    [[ $(echo "$line" | jq -r '.result') == "pass" ]]
}

@test "telemetry: phase_advance event is valid JSONL" {
    _gate_log_advance "Test-001" "planned" "Plan written" "docs/plans/test.md"

    local file="$TEST_PROJECT/.clavain/telemetry.jsonl"
    [[ -f "$file" ]]
    local line
    line=$(cat "$file")
    echo "$line" | jq empty
    [[ $(echo "$line" | jq -r '.event') == "phase_advance" ]]
    [[ $(echo "$line" | jq -r '.phase') == "planned" ]]
    [[ $(echo "$line" | jq -r '.artifact') == "docs/plans/test.md" ]]
}

# ─── _gate_update_statusline ─────────────────────────────────────────

@test "_gate_update_statusline: writes state file when CLAUDE_SESSION_ID is set" {
    export CLAUDE_SESSION_ID="test-session-abc"
    _gate_update_statusline "Clavain-021h" "planned" "Plan: docs/plans/test.md"

    local state_file="/tmp/clavain-bead-test-session-abc.json"
    [[ -f "$state_file" ]]
    # Validate JSON structure
    jq empty "$state_file"
    [[ $(jq -r '.id' "$state_file") == "Clavain-021h" ]]
    [[ $(jq -r '.phase' "$state_file") == "planned" ]]
    [[ $(jq -r '.reason' "$state_file") == "Plan: docs/plans/test.md" ]]
    [[ $(jq -r '.ts' "$state_file") =~ ^[0-9]+$ ]]

    rm -f "$state_file"
}

@test "_gate_update_statusline: skips silently when CLAUDE_SESSION_ID is unset" {
    unset CLAUDE_SESSION_ID
    run _gate_update_statusline "Clavain-021h" "planned" "reason"
    assert_success
    # No file should exist with empty session id
    [[ ! -f "/tmp/clavain-bead-.json" ]]
}

@test "_gate_update_statusline: overwrites on phase change" {
    export CLAUDE_SESSION_ID="test-session-overwrite"
    _gate_update_statusline "Clavain-021h" "planned" "Plan created"
    _gate_update_statusline "Clavain-021h" "executing" "Started work"

    local state_file="/tmp/clavain-bead-test-session-overwrite.json"
    [[ $(jq -r '.phase' "$state_file") == "executing" ]]

    rm -f "$state_file"
}

@test "advance_phase: writes statusline state file" {
    export CLAUDE_SESSION_ID="test-session-advance"
    advance_phase "Test-001" "brainstorm" "Created brainstorm"

    local state_file="/tmp/clavain-bead-test-session-advance.json"
    [[ -f "$state_file" ]]
    [[ $(jq -r '.id' "$state_file") == "Test-001" ]]
    [[ $(jq -r '.phase' "$state_file") == "brainstorm" ]]

    rm -f "$state_file"
}

# ─── Telemetry ────────────────────────────────────────────────────────

@test "telemetry: phase_desync event is valid JSONL" {
    _gate_log_desync "Test-001" "executing" "planned" "docs/plans/test.md"

    local file="$TEST_PROJECT/.clavain/telemetry.jsonl"
    [[ -f "$file" ]]
    local line
    line=$(cat "$file")
    echo "$line" | jq empty
    [[ $(echo "$line" | jq -r '.event') == "phase_desync" ]]
    [[ $(echo "$line" | jq -r '.bead_phase') == "executing" ]]
    [[ $(echo "$line" | jq -r '.artifact_phase') == "planned" ]]
}
