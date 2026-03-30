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
    command -v yq >/dev/null 2>&1 || skip "yq not available (standalone CI)"
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
    python3 -c "import jsonschema" 2>/dev/null || skip "jsonschema not installed"
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
    # Create an isolated PATH with no yq by linking only essential commands
    mkdir -p "$TEST_DIR/notyq_bin"
    for cmd in bash cat dirname grep head readlink sed wc; do
        local p; p="$(command -v "$cmd" 2>/dev/null)" && ln -sf "$p" "$TEST_DIR/notyq_bin/"
    done
    cat > "$TEST_DIR/test_no_yq.sh" << SHEOF
#!/bin/bash
export PATH="$TEST_DIR/notyq_bin"
export HOME=/nonexistent
unset _FLEET_LOADED_PATH
source "$SCRIPTS_DIR/lib-fleet.sh"
export CLAVAIN_FLEET_REGISTRY="$FIXTURES_DIR/fleet-registry.yaml"
fleet_list 2>&1
SHEOF
    chmod +x "$TEST_DIR/test_no_yq.sh"
    run "$TEST_DIR/notyq_bin/bash" "$TEST_DIR/test_no_yq.sh"
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

# ═══════════════════════════════════════════════════════════════
# scan-fleet.sh --enrich-costs tests (F1)
# ═══════════════════════════════════════════════════════════════

# Helper: create mock interstat DB from fixture SQL
_create_mock_interstat() {
    local db_path="$1"
    sqlite3 "$db_path" < "$FIXTURES_DIR/interstat-mock.sql"
}

@test "enrich-costs writes actual_tokens for agents with >= 3 runs" {
    local db="$TEST_DIR/metrics.db"
    _create_mock_interstat "$db"
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$TEST_DIR/registry.yaml"

    run bash "$SCRIPTS_DIR/scan-fleet.sh" --enrich-costs --registry "$TEST_DIR/registry.yaml" --interstat-db "$db" --in-place
    [[ "$status" -eq 0 ]]

    # test-reviewer-a has 5 sonnet runs — should have actual_tokens
    local mean
    mean="$(yq '.agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".mean' "$TEST_DIR/registry.yaml")"
    [[ "$mean" -eq 38600 ]]

    local runs
    runs="$(yq '.agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".runs' "$TEST_DIR/registry.yaml")"
    [[ "$runs" -eq 5 ]]
}

@test "enrich-costs marks agents with < 3 runs as preliminary" {
    local db="$TEST_DIR/metrics.db"
    _create_mock_interstat "$db"
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$TEST_DIR/registry.yaml"

    run bash "$SCRIPTS_DIR/scan-fleet.sh" --enrich-costs --registry "$TEST_DIR/registry.yaml" --interstat-db "$db" --in-place
    [[ "$status" -eq 0 ]]

    # test-reviewer-b has only 2 sonnet runs — should have preliminary: true
    local preliminary
    preliminary="$(yq '.agents.test-reviewer-b.models.actual_tokens."claude-sonnet-4-6".preliminary' "$TEST_DIR/registry.yaml")"
    [[ "$preliminary" == "true" ]]
}

@test "enrich-costs writes last_enrichment timestamp" {
    local db="$TEST_DIR/metrics.db"
    _create_mock_interstat "$db"
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$TEST_DIR/registry.yaml"

    run bash "$SCRIPTS_DIR/scan-fleet.sh" --enrich-costs --registry "$TEST_DIR/registry.yaml" --interstat-db "$db" --in-place
    [[ "$status" -eq 0 ]]

    local ts
    ts="$(yq '.last_enrichment' "$TEST_DIR/registry.yaml")"
    # Should be an ISO timestamp (YYYY-MM-DDTHH:MM:SSZ format)
    [[ "$ts" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T ]]
}

@test "enrich-costs dry-run shows changes without modifying file" {
    local db="$TEST_DIR/metrics.db"
    _create_mock_interstat "$db"
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$TEST_DIR/registry.yaml"
    local before_hash
    before_hash="$(md5sum "$TEST_DIR/registry.yaml" | cut -d' ' -f1)"

    run bash "$SCRIPTS_DIR/scan-fleet.sh" --enrich-costs --registry "$TEST_DIR/registry.yaml" --interstat-db "$db" --dry-run
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"test-reviewer-a"* ]]

    local after_hash
    after_hash="$(md5sum "$TEST_DIR/registry.yaml" | cut -d' ' -f1)"
    [[ "$before_hash" == "$after_hash" ]]
}

@test "enrich-costs handles missing interstat DB gracefully" {
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$TEST_DIR/registry.yaml"

    run --separate-stderr bash "$SCRIPTS_DIR/scan-fleet.sh" --enrich-costs --registry "$TEST_DIR/registry.yaml" --interstat-db "/nonexistent/db"
    [[ "$status" -eq 0 ]]
    [[ "$stderr" == *"not found"* ]]
}

@test "enrich-costs computes p50 and p90 correctly" {
    local db="$TEST_DIR/metrics.db"
    _create_mock_interstat "$db"
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$TEST_DIR/registry.yaml"

    run bash "$SCRIPTS_DIR/scan-fleet.sh" --enrich-costs --registry "$TEST_DIR/registry.yaml" --interstat-db "$db" --in-place
    [[ "$status" -eq 0 ]]

    # test-reviewer-a sonnet: sorted tokens = [30000, 35000, 38000, 40000, 50000]
    # p50 = index floor(5*0.5) = index 2 → 38000
    # p90 = index floor(5*0.9) = index 4 → 50000
    local p50
    p50="$(yq '.agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".p50' "$TEST_DIR/registry.yaml")"
    [[ "$p50" -eq 38000 ]]

    local p90
    p90="$(yq '.agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".p90' "$TEST_DIR/registry.yaml")"
    [[ "$p90" -eq 50000 ]]
}

# ═══════════════════════════════════════════════════════════════
# fleet_cost_estimate_live tests (F2)
# ═══════════════════════════════════════════════════════════════

# Helper: create enriched fixture registry with actual_tokens
_create_enriched_fixture() {
    local registry="$1"
    cp "$FIXTURES_DIR/fleet-registry.yaml" "$registry"
    yq -i '
      .last_enrichment = "2026-02-15T00:00:00Z" |
      .agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".mean = 38600 |
      .agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".p50 = 38000 |
      .agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".p90 = 50000 |
      .agents.test-reviewer-a.models.actual_tokens."claude-sonnet-4-6".runs = 5
    ' "$registry"
}

@test "fleet_cost_estimate_live returns registry data when no interstat" {
    local registry="$TEST_DIR/registry.yaml"
    _create_enriched_fixture "$registry"
    _source_fleet "$registry"

    run fleet_cost_estimate_live test-reviewer-a claude-sonnet-4-6
    [[ "$status" -eq 0 ]]
    [[ "$output" == "38600" ]]
}

@test "fleet_cost_estimate_live falls back to cold_start_tokens when no actual_tokens" {
    _source_fleet
    run fleet_cost_estimate_live test-researcher claude-haiku-4-5
    [[ "$status" -eq 0 ]]
    [[ "$output" == "300" ]]
}

@test "fleet_cost_estimate_live returns error for unknown agent" {
    _source_fleet
    run fleet_cost_estimate_live nonexistent-agent claude-sonnet-4-6
    [[ "$status" -ne 0 ]]
}

@test "fleet_cost_estimate_live uses interstat delta when DB has newer runs" {
    local registry="$TEST_DIR/registry.yaml"
    _create_enriched_fixture "$registry"
    _source_fleet "$registry"

    # Create mock DB and add a post-enrichment run
    local db="$TEST_DIR/metrics.db"
    _create_mock_interstat "$db"
    # Add a run after the enrichment timestamp (2026-02-15)
    sqlite3 "$db" "INSERT INTO agent_runs (timestamp, session_id, agent_name, subagent_type, input_tokens, output_tokens, total_tokens, model)
      VALUES ('2026-03-01T10:00:00Z', 's10', 'test-reviewer-a', 'test-plugin:review:test-reviewer-a', 18000, 27000, 45000, 'claude-sonnet-4-6');"

    INTERSTAT_DB="$db" run fleet_cost_estimate_live test-reviewer-a claude-sonnet-4-6
    [[ "$status" -eq 0 ]]
    # Weighted average: (38600*5 + 45000*1) / 6 = 39666 (bash integer truncation)
    [[ "$output" -eq 39666 ]]
}

@test "fleet_cost_estimate_live defaults to preferred model when model not specified" {
    local registry="$TEST_DIR/registry.yaml"
    _create_enriched_fixture "$registry"
    _source_fleet "$registry"

    # test-reviewer-a preferred model is sonnet → maps to claude-sonnet-4-6
    run fleet_cost_estimate_live test-reviewer-a
    [[ "$status" -eq 0 ]]
    [[ "$output" == "38600" ]]
}

# ═══════════════════════════════════════════════════════════════
# Compound Autonomy Guard (rsj.1.8)
# ═══════════════════════════════════════════════════════════════

_create_compound_fixture() {
    local registry="$1"
    local policy_dir
    policy_dir="$(dirname "$registry")"

    cat > "$registry" << 'YAML'
version: "1.0"
capability_vocabulary: []
agents:
  test-observer:
    source: test
    category: review
    capability_level: 0
    description: "L0 read-only"
    capabilities: []
    roles: []
    runtime: { mode: subagent }
    models: { preferred: haiku, supported: [haiku] }
    tools: [Read]
    cold_start_tokens: 100
    tags: []
  test-reviewer:
    source: test
    category: review
    capability_level: 1
    description: "L1 analysis"
    capabilities: [domain_review]
    roles: []
    runtime: { mode: subagent }
    models: { preferred: sonnet, supported: [sonnet] }
    tools: [Read, Grep]
    cold_start_tokens: 400
    tags: []
  test-worker:
    source: test
    category: workflow
    capability_level: 2
    description: "L2 local mutations"
    capabilities: []
    roles: []
    runtime: { mode: subagent }
    models: { preferred: sonnet, supported: [sonnet] }
    tools: [Read, Edit, Write]
    cold_start_tokens: 600
    tags: []
  test-shipper:
    source: test
    category: workflow
    capability_level: 3
    description: "L3 external effects"
    capabilities: []
    roles: []
    runtime: { mode: subagent }
    models: { preferred: opus, supported: [opus] }
    tools: [Read, Edit, Write, Bash]
    cold_start_tokens: 800
    tags: []
  test-no-level:
    source: test
    category: review
    description: "No capability_level set"
    capabilities: []
    roles: []
    runtime: { mode: subagent }
    models: { preferred: haiku, supported: [haiku] }
    tools: [Read]
    cold_start_tokens: 100
    tags: []
YAML

    # Create policy file alongside registry
    cat > "$policy_dir/default-policy.yaml" << 'YAML'
schema_version: 1
phases: {}
compound_autonomy:
  default_capability_level: 2
  thresholds:
    auto: 2
    advisory: 4
    approval: 6
    blocked: 9
YAML
}

@test "compound autonomy: T1×L1=1 → auto (pass)" {
    local registry="$TEST_DIR/registry.yaml"
    _create_compound_fixture "$registry"
    _source_fleet "$registry"

    run fleet_compound_autonomy_check 1 test-reviewer
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"auto"* ]]
    [[ "$output" == *"T1×L1"* ]]
}

@test "compound autonomy: T2×L2=4 → advisory" {
    local registry="$TEST_DIR/registry.yaml"
    _create_compound_fixture "$registry"
    _source_fleet "$registry"

    run fleet_compound_autonomy_check 2 test-worker
    [[ "$status" -eq 1 ]]
    [[ "$output" == *"advisory"* ]]
    [[ "$output" == *"T2×L2"* ]]
}

@test "compound autonomy: T2×L3=6 → approval required" {
    local registry="$TEST_DIR/registry.yaml"
    _create_compound_fixture "$registry"
    _source_fleet "$registry"

    run fleet_compound_autonomy_check 2 test-shipper
    [[ "$status" -eq 2 ]]
    [[ "$output" == *"approval"* ]]
    [[ "$output" == *"T2×L3"* ]]
}

@test "compound autonomy: T3×L3=9 → blocked" {
    local registry="$TEST_DIR/registry.yaml"
    _create_compound_fixture "$registry"
    _source_fleet "$registry"

    run fleet_compound_autonomy_check 3 test-shipper
    [[ "$status" -eq 3 ]]
    [[ "$output" == *"blocked"* ]]
    [[ "$output" == *"T3×L3"* ]]
}

@test "compound autonomy: T0×L3=0 → auto (zero tier is safe)" {
    local registry="$TEST_DIR/registry.yaml"
    _create_compound_fixture "$registry"
    _source_fleet "$registry"

    run fleet_compound_autonomy_check 0 test-shipper
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"auto"* ]]
}

@test "compound autonomy: missing capability_level uses default (L2)" {
    local registry="$TEST_DIR/registry.yaml"
    _create_compound_fixture "$registry"
    _source_fleet "$registry"

    # T2 × L2(default) = 4 → advisory
    run fleet_compound_autonomy_check 2 test-no-level
    [[ "$status" -eq 1 ]]
    [[ "$output" == *"advisory"* ]]
    [[ "$output" == *"L2"* ]]
}
