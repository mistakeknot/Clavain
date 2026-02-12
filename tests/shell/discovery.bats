#!/usr/bin/env bats
# Tests for hooks/lib-discovery.sh work discovery scanner

setup() {
    load test_helper

    # Create isolated temp project directory for each test
    TEST_PROJECT="$(mktemp -d)"
    export DISCOVERY_PROJECT_DIR="$TEST_PROJECT"

    # Create .beads directory (required for scanner to proceed)
    mkdir -p "$TEST_PROJECT/.beads"

    # Reset the double-source guard so we can re-source in each test
    unset _DISCOVERY_LOADED
    source "$HOOKS_DIR/lib-discovery.sh"
}

teardown() {
    rm -rf "$TEST_PROJECT"
}

# ─── Mock helpers ─────────────────────────────────────────────────────

# Create a mock bd command that returns given JSON for --status=open
# and empty array for --status=in_progress (unless MOCK_BD_IP_JSON is set)
mock_bd() {
    local json="$1"
    export MOCK_BD_JSON="$json"
    export MOCK_BD_IP_JSON="${2:-[]}"
    bd() {
        if [[ "$1" == "list" ]]; then
            if [[ "$*" == *"--status=in_progress"* ]]; then
                echo "$MOCK_BD_IP_JSON"
            else
                echo "$MOCK_BD_JSON"
            fi
            return 0
        fi
        return 1
    }
    export -f bd
}

# Create a mock bd that fails
mock_bd_error() {
    bd() { return 1; }
    export -f bd
}

# Create a mock bd that returns invalid JSON
mock_bd_garbage() {
    bd() {
        echo "Error: database locked"
        return 0
    }
    export -f bd
}

# ─── discovery_scan_beads: bd not available ───────────────────────────

@test "discovery: outputs DISCOVERY_UNAVAILABLE when bd not installed" {
    # Hide bd from PATH
    bd() { return 127; }
    unset -f bd
    # Temporarily remove bd from PATH
    local old_path="$PATH"
    PATH="/nonexistent"
    unset _DISCOVERY_LOADED
    source "$HOOKS_DIR/lib-discovery.sh"
    run discovery_scan_beads
    PATH="$old_path"
    assert_success
    assert_output "DISCOVERY_UNAVAILABLE"
}

@test "discovery: outputs DISCOVERY_UNAVAILABLE when .beads dir missing" {
    rmdir "$TEST_PROJECT/.beads"
    mock_bd '[]'
    run discovery_scan_beads
    assert_success
    assert_output "DISCOVERY_UNAVAILABLE"
}

# ─── discovery_scan_beads: bd error handling ──────────────────────────

@test "discovery: outputs DISCOVERY_ERROR when bd fails" {
    mock_bd_error
    run discovery_scan_beads
    assert_success
    assert_output "DISCOVERY_ERROR"
}

@test "discovery: outputs DISCOVERY_ERROR when bd returns invalid JSON" {
    mock_bd_garbage
    run discovery_scan_beads
    assert_success
    assert_output "DISCOVERY_ERROR"
}

# ─── discovery_scan_beads: empty results ──────────────────────────────

@test "discovery: outputs empty array when no open beads" {
    mock_bd '[]'
    run discovery_scan_beads
    assert_success
    assert_output "[]"
}

# ─── discovery_scan_beads: JSON output format ─────────────────────────

@test "discovery: outputs valid JSON with required fields" {
    mock_bd '[{"id":"Test-abc1","title":"Fix auth","status":"open","priority":1,"updated_at":"2026-02-12T10:00:00Z"}]'
    run discovery_scan_beads
    assert_success

    # Verify it's valid JSON
    echo "$output" | jq empty

    # Verify required fields exist
    local id title priority status action plan_path stale
    id=$(echo "$output" | jq -r '.[0].id')
    title=$(echo "$output" | jq -r '.[0].title')
    priority=$(echo "$output" | jq '.[0].priority')
    status=$(echo "$output" | jq -r '.[0].status')
    action=$(echo "$output" | jq -r '.[0].action')
    plan_path=$(echo "$output" | jq -r '.[0].plan_path')
    stale=$(echo "$output" | jq '.[0].stale')

    [[ "$id" == "Test-abc1" ]]
    [[ "$title" == "Fix auth" ]]
    [[ "$priority" == "1" ]]
    [[ "$status" == "open" ]]
    [[ -n "$action" ]]
    [[ "$stale" == "true" || "$stale" == "false" ]]
}

# ─── discovery_scan_beads: sorting ────────────────────────────────────

@test "discovery: sorts by priority then recency" {
    mock_bd '[
        {"id":"Test-low","title":"Low priority","status":"open","priority":3,"updated_at":"2026-02-12T12:00:00Z"},
        {"id":"Test-high","title":"High priority","status":"open","priority":1,"updated_at":"2026-02-10T10:00:00Z"},
        {"id":"Test-mid","title":"Med priority","status":"open","priority":2,"updated_at":"2026-02-11T10:00:00Z"}
    ]'
    run discovery_scan_beads
    assert_success

    # First result should be highest priority (P1)
    local first_id second_id third_id
    first_id=$(echo "$output" | jq -r '.[0].id')
    second_id=$(echo "$output" | jq -r '.[1].id')
    third_id=$(echo "$output" | jq -r '.[2].id')

    [[ "$first_id" == "Test-high" ]]
    [[ "$second_id" == "Test-mid" ]]
    [[ "$third_id" == "Test-low" ]]
}

# ─── discovery_scan_beads: skips invalid beads ────────────────────────

@test "discovery: skips beads with missing id" {
    mock_bd '[
        {"title":"No ID","status":"open","priority":1,"updated_at":"2026-02-12T10:00:00Z"},
        {"id":"Test-ok","title":"Has ID","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"}
    ]'
    run discovery_scan_beads
    assert_success

    local count
    count=$(echo "$output" | jq 'length')
    [[ "$count" == "1" ]]
    [[ $(echo "$output" | jq -r '.[0].id') == "Test-ok" ]]
}

# ─── infer_bead_action: state-based inference ─────────────────────────

@test "infer_bead_action: in_progress returns continue" {
    run infer_bead_action "Test-abc1" "in_progress"
    assert_success
    [[ "$output" == "continue|"* ]]
}

@test "infer_bead_action: open with plan returns execute" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "**Bead:** Test-abc1 (Feature)" > "$TEST_PROJECT/docs/plans/test-plan.md"

    run infer_bead_action "Test-abc1" "open"
    assert_success
    [[ "$output" == "execute|"* ]]
    [[ "$output" == *"test-plan.md"* ]]
}

@test "infer_bead_action: open with PRD but no plan returns plan" {
    mkdir -p "$TEST_PROJECT/docs/prds"
    echo "**Bead:** Test-abc1" > "$TEST_PROJECT/docs/prds/test-prd.md"

    run infer_bead_action "Test-abc1" "open"
    assert_success
    [[ "$output" == "plan|"* ]]
}

@test "infer_bead_action: open with brainstorm but no PRD returns strategize" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    echo "**Bead:** Test-abc1" > "$TEST_PROJECT/docs/brainstorms/test-brainstorm.md"

    run infer_bead_action "Test-abc1" "open"
    assert_success
    [[ "$output" == "strategize|"* ]]
}

@test "infer_bead_action: open with nothing returns brainstorm" {
    run infer_bead_action "Test-abc1" "open"
    assert_success
    assert_output "brainstorm|"
}

# ─── infer_bead_action: word-boundary matching ───────────────────────

@test "infer_bead_action: does not match substring of longer bead ID" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    # Plan references "Test-abc12" (longer ID) — should NOT match "Test-abc1"
    echo "**Bead:** Test-abc12 (Feature)" > "$TEST_PROJECT/docs/plans/other-plan.md"

    run infer_bead_action "Test-abc1" "open"
    assert_success
    # Should return brainstorm (no match), not execute
    assert_output "brainstorm|"
}

@test "infer_bead_action: matches exact bead ID among others" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    # Plan references multiple beads on same line
    echo "**Bead:** Test-abc1 (F1), Test-abc2 (F2)" > "$TEST_PROJECT/docs/plans/multi-plan.md"

    run infer_bead_action "Test-abc1" "open"
    assert_success
    [[ "$output" == "execute|"* ]]
    [[ "$output" == *"multi-plan.md"* ]]
}

# ─── discovery_log_selection: safe telemetry ──────────────────────────

@test "discovery_log_selection: writes valid JSONL" {
    export HOME="$TEST_PROJECT"
    run discovery_log_selection "Test-abc1" "execute" "true"
    assert_success

    # Verify file exists and contains valid JSON
    local line
    line=$(cat "$TEST_PROJECT/.clavain/telemetry.jsonl")
    echo "$line" | jq empty  # Will fail if not valid JSON

    [[ $(echo "$line" | jq -r '.event') == "discovery_select" ]]
    [[ $(echo "$line" | jq -r '.bead') == "Test-abc1" ]]
    [[ $(echo "$line" | jq -r '.action') == "execute" ]]
    [[ $(echo "$line" | jq '.recommended') == "true" ]]
}

@test "discovery_log_selection: handles special characters safely" {
    export HOME="$TEST_PROJECT"
    # Bead ID with characters that could cause printf injection
    run discovery_log_selection 'Test-%s%n"injection' "plan" "false"
    assert_success

    local line
    line=$(cat "$TEST_PROJECT/.clavain/telemetry.jsonl")
    echo "$line" | jq empty  # Must still be valid JSON

    # The special characters should be properly escaped in JSON
    [[ $(echo "$line" | jq -r '.bead') == 'Test-%s%n"injection' ]]
}

# ─── staleness ────────────────────────────────────────────────────────

@test "discovery: merges open and in_progress beads" {
    local open_json='[{"id":"Test-open1","title":"Open bead","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"}]'
    local ip_json='[{"id":"Test-ip1","title":"In progress","status":"in_progress","priority":1,"updated_at":"2026-02-12T11:00:00Z"}]'

    mock_bd "$open_json" "$ip_json"
    run discovery_scan_beads
    assert_success

    local count
    count=$(echo "$output" | jq 'length')
    [[ "$count" == "2" ]]

    # in_progress (P1) should sort before open (P2)
    [[ $(echo "$output" | jq -r '.[0].id') == "Test-ip1" ]]
    [[ $(echo "$output" | jq -r '.[1].id') == "Test-open1" ]]
}

@test "discovery: action priority — plan beats PRD beats brainstorm" {
    # Create all three artifact types for same bead
    mkdir -p "$TEST_PROJECT/docs/plans" "$TEST_PROJECT/docs/prds" "$TEST_PROJECT/docs/brainstorms"
    echo "**Bead:** Test-all1" > "$TEST_PROJECT/docs/plans/test-plan.md"
    echo "**Bead:** Test-all1" > "$TEST_PROJECT/docs/prds/test-prd.md"
    echo "**Bead:** Test-all1" > "$TEST_PROJECT/docs/brainstorms/test-brainstorm.md"

    mock_bd '[{"id":"Test-all1","title":"Has everything","status":"open","priority":1,"updated_at":"2026-02-12T10:00:00Z"}]'
    run discovery_scan_beads
    assert_success

    # Plan should win over PRD and brainstorm
    [[ $(echo "$output" | jq -r '.[0].action') == "execute" ]]
    [[ $(echo "$output" | jq -r '.[0].plan_path') == *"test-plan.md"* ]]
}

@test "discovery: marks bead as stale when plan file is old" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "**Bead:** Test-stale1" > "$TEST_PROJECT/docs/plans/old-plan.md"
    # Set mtime to 5 days ago using relative date
    local five_days_ago
    five_days_ago=$(date -d '5 days ago' +%Y%m%d%H%M 2>/dev/null || date -v-5d +%Y%m%d%H%M)
    touch -t "$five_days_ago" "$TEST_PROJECT/docs/plans/old-plan.md"

    mock_bd '[{"id":"Test-stale1","title":"Stale work","status":"open","priority":2,"updated_at":"2026-02-07T00:00:00Z"}]'
    run discovery_scan_beads
    assert_success

    [[ $(echo "$output" | jq '.[0].stale') == "true" ]]
}

@test "discovery: marks bead as not stale when plan file is recent" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "**Bead:** Test-fresh1" > "$TEST_PROJECT/docs/plans/fresh-plan.md"
    # mtime is now (just created) — not stale

    mock_bd '[{"id":"Test-fresh1","title":"Fresh work","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"}]'
    run discovery_scan_beads
    assert_success

    [[ $(echo "$output" | jq '.[0].stale') == "false" ]]
}
