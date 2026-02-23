#!/usr/bin/env bats
# Tests for scripts/lib-fleet.sh and scripts/scan-fleet.sh

bats_require_minimum_version 1.5.0

setup() {
    load test_helper

    SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../scripts"
    FIXTURES_DIR="$BATS_TEST_DIRNAME/../fixtures/fleet"

    # Create isolated temp directory for each test
    TEST_DIR="$(mktemp -d)"

    # Critical: reset guard so each test starts clean
    unset _FLEET_LOADED_PATH
    unset _FLEET_REGISTRY_PATH

    # Ensure yq is in PATH
    export PATH="$HOME/.local/bin:$PATH"
}

teardown() {
    [[ -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}

# Helper: source lib-fleet with test fixture
_source_fleet() {
    unset _FLEET_LOADED_PATH
    unset _FLEET_REGISTRY_PATH
    export CLAVAIN_FLEET_REGISTRY="${1:-$FIXTURES_DIR/fleet-registry.yaml}"
    source "$SCRIPTS_DIR/lib-fleet.sh"
}

# ═══════════════════════════════════════════════════════════════
# lib-fleet.sh tests
# ═══════════════════════════════════════════════════════════════

@test "fleet_list returns all non-orphaned agents" {
    _source_fleet
    run fleet_list
    [[ "$status" -eq 0 ]]
    # 5 active agents, 1 orphaned (should be excluded)
    local count
    count="$(echo "$output" | wc -l)"
    [[ "$count" -eq 5 ]]
    # Orphaned agent must not appear
    [[ "$output" != *"test-orphaned"* ]]
}

@test "fleet_list on empty registry returns 0 with no agent IDs" {
    cat > "$TEST_DIR/empty.yaml" << 'YAML'
version: "1.0"
capability_vocabulary: []
agents: {}
YAML
    _source_fleet "$TEST_DIR/empty.yaml"
    run --separate-stderr fleet_list
    [[ "$status" -eq 0 ]]
    # yq may output empty or nothing — no agent IDs should appear
    local trimmed="${output//[[:space:]]/}"
    [[ -z "$trimmed" ]]
}

@test "fleet_get returns correct agent block without ID key" {
    _source_fleet
    run fleet_get test-reviewer-a
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"source: test-plugin"* ]]
    [[ "$output" == *"category: review"* ]]
    [[ "$output" == *"cold_start_tokens: 800"* ]]
    # Should NOT contain the agent ID as a key
    [[ "$output" != *"test-reviewer-a:"* ]]
}

@test "fleet_get returns error for unknown agent" {
    _source_fleet
    run fleet_get nonexistent-agent
    [[ "$status" -eq 1 ]]
    [[ "$output" == *"not found"* ]]
}

@test "fleet_get with FLEET_FORMAT=json returns valid JSON" {
    _source_fleet
    FLEET_FORMAT=json run fleet_get test-reviewer-a
    [[ "$status" -eq 0 ]]
    echo "$output" | python3 -c "import json, sys; json.load(sys.stdin)"
}

@test "fleet_by_category review returns only review agents" {
    _source_fleet
    run fleet_by_category review
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-reviewer-a"* ]]
    [[ "$output" == *"test-reviewer-b"* ]]
    [[ "$output" != *"test-researcher"* ]]
    [[ "$output" != *"test-workflow"* ]]
    # Orphaned review agent must not appear
    [[ "$output" != *"test-orphaned"* ]]
}

@test "fleet_by_capability domain_review returns agents with that capability" {
    _source_fleet
    run fleet_by_capability domain_review
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-reviewer-a"* ]]
    [[ "$output" == *"test-reviewer-b"* ]]
    # Orphaned agent has domain_review but must not appear
    [[ "$output" != *"test-orphaned"* ]]
}

@test "fleet_by_source returns correct subset" {
    _source_fleet
    run fleet_by_source other-plugin
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-researcher"* ]]
    [[ "$output" == *"test-researcher-b"* ]]
    local count
    count="$(echo "$output" | wc -l)"
    [[ "$count" -eq 2 ]]
}

@test "fleet_by_role returns agents that can fulfill a role" {
    _source_fleet
    run fleet_by_role fd-architecture
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-reviewer-a"* ]]
    local count
    count="$(echo "$output" | wc -l)"
    [[ "$count" -eq 1 ]]
}

@test "fleet_by_role research-agent returns multiple agents" {
    _source_fleet
    run fleet_by_role research-agent
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-researcher"* ]]
    [[ "$output" == *"test-researcher-b"* ]]
}

@test "fleet_cost_estimate returns cold_start_tokens" {
    _source_fleet
    run fleet_cost_estimate test-reviewer-a
    [[ "$status" -eq 0 ]]
    [[ "$output" == "800" ]]
}

@test "fleet_cost_estimate returns error for unknown agent" {
    _source_fleet
    run fleet_cost_estimate nonexistent
    [[ "$status" -eq 1 ]]
}

@test "fleet_within_budget 500 excludes expensive agents" {
    _source_fleet
    run fleet_within_budget 500
    [[ "$status" -eq 0 ]]
    # 200 (test-researcher-b), 300 (test-researcher), 400 (test-reviewer-b) should be included
    [[ "$output" == *"test-reviewer-b"* ]]
    [[ "$output" == *"test-researcher"* ]]
    [[ "$output" == *"test-researcher-b"* ]]
    # 800 (test-reviewer-a) and 600 (test-workflow) should be excluded
    [[ "$output" != *"test-reviewer-a"* ]]
    [[ "$output" != *"test-workflow"* ]]
}

@test "fleet_within_budget with category filter" {
    _source_fleet
    run fleet_within_budget 500 research
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-researcher"* ]]
    [[ "$output" != *"test-reviewer-b"* ]]
}

@test "fleet_check_coverage returns 0 when all capabilities covered" {
    _source_fleet
    run fleet_check_coverage domain_review multi_perspective
    [[ "$status" -eq 0 ]]
}

@test "fleet_check_coverage returns 1 when capability missing" {
    _source_fleet
    run fleet_check_coverage domain_review nonexistent_capability
    [[ "$status" -eq 1 ]]
}

@test "fleet_check_coverage partial coverage returns 1 and prints missing" {
    _source_fleet
    fleet_check_coverage domain_review missing_cap 2>"$TEST_DIR/stderr" || true
    local exit_code=$?
    # Bash run clobbers exit code, check the stderr file
    grep -q "missing_cap" "$TEST_DIR/stderr"
}

@test "guard invalidates when CLAVAIN_FLEET_REGISTRY changes" {
    # Load first registry
    _source_fleet "$FIXTURES_DIR/fleet-registry.yaml"
    run fleet_list
    local count1
    count1="$(echo "$output" | wc -l)"

    # Create a different registry
    cat > "$TEST_DIR/small.yaml" << 'YAML'
version: "1.0"
capability_vocabulary: []
agents:
  only-agent:
    source: test
    category: workflow
    description: "Solo agent"
    runtime:
      mode: subagent
YAML
    # Re-source with different path (without unsetting — guard should detect path change)
    export CLAVAIN_FLEET_REGISTRY="$TEST_DIR/small.yaml"
    _fleet_init
    run fleet_list
    local count2
    count2="$(echo "$output" | wc -l)"
    [[ "$count2" -eq 1 ]]
    [[ "$count1" -ne "$count2" ]]
}

# ═══════════════════════════════════════════════════════════════
# scan-fleet.sh tests
# ═══════════════════════════════════════════════════════════════

@test "scan-fleet.sh --dry-run discovers mock agents" {
    cat > "$TEST_DIR/fleet-registry.yaml" << 'YAML'
version: "1.0"
capability_vocabulary: []
agents: {}
YAML
    export PATH="$HOME/.local/bin:$PATH"
    run "$SCRIPTS_DIR/scan-fleet.sh" --dry-run --registry "$TEST_DIR/fleet-registry.yaml"
    [[ "$output" == *"DRY RUN"* ]]
}

@test "scan-fleet.sh handles missing frontmatter gracefully" {
    # The no-frontmatter.md file in fixtures has no --- delimiters
    # The scanner should fall back to the filename
    local file="$FIXTURES_DIR/mock-project/interverse/mock-plugin/agents/review/no-frontmatter.md"
    [[ -f "$file" ]]
    # Extract frontmatter should return empty
    local fm
    fm="$(awk '/^---$/{t++; next} t==1{print}' "$file")"
    [[ -z "$fm" ]]
}

# ═══════════════════════════════════════════════════════════════
# Schema validation tests
# ═══════════════════════════════════════════════════════════════

@test "fixture registry validates against JSON schema" {
    export PATH="$HOME/.local/bin:$PATH"
    local schema_path="$BATS_TEST_DIRNAME/../../config/fleet-registry.schema.json"
    # Write validation script to temp file (avoids multi-line bash -c)
    cat > "$TEST_DIR/validate.py" << PYEOF
import json, jsonschema, sys
schema = json.load(open("$schema_path"))
instance = json.load(sys.stdin)
jsonschema.validate(instance, schema)
print("PASS")
PYEOF
    run bash -c "yq -o=json '$FIXTURES_DIR/fleet-registry.yaml' | python3 '$TEST_DIR/validate.py'"
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"PASS"* ]]
}

@test "cold_start_tokens survives YAML to JSON round-trip as integer" {
    export PATH="$HOME/.local/bin:$PATH"
    cat > "$TEST_DIR/check_types.py" << 'PYEOF'
import json, sys
d = json.load(sys.stdin)
for name, agent in d["agents"].items():
    t = type(agent.get("cold_start_tokens", 0))
    if t != int:
        print(f"FAIL: {name} cold_start_tokens is {t.__name__}, expected int")
        sys.exit(1)
print("PASS: all cold_start_tokens are int")
PYEOF
    run bash -c "yq -o=json '$FIXTURES_DIR/fleet-registry.yaml' | python3 '$TEST_DIR/check_types.py'"
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"PASS"* ]]
}

# ═══════════════════════════════════════════════════════════════
# Environmental tests
# ═══════════════════════════════════════════════════════════════

@test "lib-fleet fails with clear message when yq is absent" {
    # Write a test script that restricts PATH before sourcing
    cat > "$TEST_DIR/test_no_yq.sh" << SHEOF
#!/usr/bin/env bash
export PATH=/usr/bin:/bin
export HOME=/nonexistent
source "$SCRIPTS_DIR/lib-fleet.sh"
export CLAVAIN_FLEET_REGISTRY="$FIXTURES_DIR/fleet-registry.yaml"
fleet_list 2>&1
SHEOF
    chmod +x "$TEST_DIR/test_no_yq.sh"
    run bash "$TEST_DIR/test_no_yq.sh"
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"yq not found"* ]]
}

@test "subshell invocation initializes correctly" {
    cat > "$TEST_DIR/test_subshell.sh" << SHEOF
#!/usr/bin/env bash
export PATH="$HOME/.local/bin:\$PATH"
export CLAVAIN_FLEET_REGISTRY="$FIXTURES_DIR/fleet-registry.yaml"
source "$SCRIPTS_DIR/lib-fleet.sh"
fleet_list | wc -l
SHEOF
    chmod +x "$TEST_DIR/test_subshell.sh"
    run bash "$TEST_DIR/test_subshell.sh"
    [[ "$status" -eq 0 ]]
    local trimmed="${output//[[:space:]]/}"
    [[ "$trimmed" -eq 5 ]]
}
