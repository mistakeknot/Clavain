#!/usr/bin/env bats
# Tests for scripts/lib-compose.sh

setup() {
    load test_helper
    SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../scripts"
    source "$SCRIPTS_DIR/lib-compose.sh"
}

@test "compose_has_agents: returns 0 for plan with agents" {
    local plan
    plan=$(cat "$FIXTURES_DIR/compose-plan-single.json")
    run compose_has_agents "$plan"
    assert_success
}

@test "compose_has_agents: returns 1 for plan with empty agents" {
    local plan
    plan=$(cat "$FIXTURES_DIR/compose-plan-empty-agents.json")
    run compose_has_agents "$plan"
    assert_failure
}

@test "compose_has_agents: returns 1 for empty string" {
    run compose_has_agents ""
    assert_failure
}

@test "compose_agents_json: extracts agents array" {
    local plan
    plan=$(cat "$FIXTURES_DIR/compose-plan-single.json")
    run compose_agents_json "$plan"
    assert_success
    local count
    count=$(echo "$output" | jq 'length')
    [ "$count" -eq 1 ]
}

@test "compose_agents_json: extracts agent subagent_type" {
    local plan
    plan=$(cat "$FIXTURES_DIR/compose-plan-single.json")
    run compose_agents_json "$plan"
    assert_success
    local agent_type
    agent_type=$(echo "$output" | jq -r '.[0].subagent_type')
    [ "$agent_type" = "interflux:fd-correctness" ]
}

@test "compose_warn_if_expected: silent when no agency-spec" {
    _compose_has_agency_spec() { return 1; }
    run compose_warn_if_expected "test error"
    assert_success
    assert_output ""
}

@test "compose_warn_if_expected: warns and returns 0 when agency-spec exists" {
    _compose_has_agency_spec() { return 0; }
    run compose_warn_if_expected "test error"
    assert_success
}

@test "_compose_has_agency_spec: finds spec in CLAUDE_PLUGIN_ROOT" {
    mkdir -p "$BATS_TEST_TMPDIR/config"
    touch "$BATS_TEST_TMPDIR/config/agency-spec.yaml"
    CLAUDE_PLUGIN_ROOT="$BATS_TEST_TMPDIR" run _compose_has_agency_spec
    assert_success
}

@test "_compose_has_agency_spec: finds spec in project-local .clavain/" {
    mkdir -p "$BATS_TEST_TMPDIR/.clavain"
    touch "$BATS_TEST_TMPDIR/.clavain/agency-spec.yaml"
    SPRINT_LIB_PROJECT_DIR="$BATS_TEST_TMPDIR" CLAVAIN_CONFIG_DIR="" CLAVAIN_DIR="" CLAVAIN_SOURCE_DIR="" CLAUDE_PLUGIN_ROOT="" \
        run _compose_has_agency_spec
    assert_success
}

@test "_compose_has_agency_spec: returns 1 when no spec exists" {
    SPRINT_LIB_PROJECT_DIR="$BATS_TEST_TMPDIR" CLAVAIN_CONFIG_DIR="" CLAVAIN_DIR="" CLAVAIN_SOURCE_DIR="" CLAUDE_PLUGIN_ROOT="$BATS_TEST_TMPDIR" \
        run _compose_has_agency_spec
    assert_failure
}

@test "compose_dispatch: reads stored artifact for matching stage" {
    local mock_cli="$BATS_TEST_TMPDIR/mock-cli"
    cat > "$mock_cli" <<'MOCK'
#!/usr/bin/env bash
if [[ "$1" == "get-artifact" ]]; then
    echo "$COMPOSE_FIXTURE_PATH"
fi
MOCK
    chmod +x "$mock_cli"
    cp "$FIXTURES_DIR/compose-plan-array.json" "$BATS_TEST_TMPDIR/stored-plan.json"
    _compose_find_cli() { echo "$mock_cli"; }
    export COMPOSE_FIXTURE_PATH="$BATS_TEST_TMPDIR/stored-plan.json"

    run compose_dispatch "iv-test" "build"
    assert_success
    local agent_count
    agent_count=$(echo "$output" | jq '.agents | length')
    [ "$agent_count" -eq 2 ]
}

@test "compose_dispatch: falls back to on-demand when no stored artifact" {
    local mock_cli="$BATS_TEST_TMPDIR/mock-cli"
    cat > "$mock_cli" <<'MOCK'
#!/usr/bin/env bash
if [[ "$1" == "get-artifact" ]]; then
    exit 1
elif [[ "$1" == "compose" ]]; then
    echo '{"stage":"build","agents":[{"agent_id":"fallback"}]}'
fi
MOCK
    chmod +x "$mock_cli"
    _compose_find_cli() { echo "$mock_cli"; }

    run compose_dispatch "iv-missing" "build"
    assert_success
    local agent_id
    agent_id=$(echo "$output" | jq -r '.agents[0].agent_id')
    [ "$agent_id" = "fallback" ]
}

@test "source lib-compose.sh has no side effects" {
    run bash -c "source '$SCRIPTS_DIR/lib-compose.sh' 2>&1"
    assert_success
    assert_output ""
}
