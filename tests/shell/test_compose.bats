#!/usr/bin/env bats

# Integration tests for clavain-cli compose
# Requires: clavain-cli-go binary built, real config files present

setup() {
    export CLI="${BATS_TEST_DIRNAME}/../../bin/clavain-cli-go"
    export CLAVAIN_CONFIG_DIR="${BATS_TEST_DIRNAME}/../../config"
    export SPRINT_LIB_PROJECT_DIR="${BATS_TEST_DIRNAME}/../../../.."

    if [[ ! -f "$CLI" ]]; then
        skip "clavain-cli-go not built — run build-clavain-cli.sh first"
    fi
}

@test "compose --stage=ship produces valid JSON" {
    run "$CLI" compose --stage=ship
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.stage == "ship"'
    echo "$output" | jq -e '.agents | length > 0'
}

@test "compose --stage=build produces valid JSON" {
    run "$CLI" compose --stage=build
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.stage == "build"'
}

@test "compose --stage=invalid fails" {
    run "$CLI" compose --stage=invalid
    [ "$status" -eq 1 ]
}

@test "compose requires --stage flag" {
    run "$CLI" compose
    [ "$status" -eq 1 ]
}

@test "compose agents have required fields" {
    run "$CLI" compose --stage=ship
    [ "$status" -eq 0 ]
    # No agent should have empty agent_id, subagent_type, or model
    empty_ids=$(echo "$output" | jq '[.agents[] | select(.agent_id == "")] | length')
    empty_types=$(echo "$output" | jq '[.agents[] | select(.subagent_type == "")] | length')
    empty_models=$(echo "$output" | jq '[.agents[] | select(.model == "")] | length')
    [ "$empty_ids" -eq 0 ]
    [ "$empty_types" -eq 0 ]
    [ "$empty_models" -eq 0 ]
}

@test "compose safety floors enforce sonnet minimum" {
    run "$CLI" compose --stage=ship
    [ "$status" -eq 0 ]
    safety_model=$(echo "$output" | jq -r '.agents[] | select(.agent_id == "fd-safety") | .model')
    correctness_model=$(echo "$output" | jq -r '.agents[] | select(.agent_id == "fd-correctness") | .model')
    [ "$safety_model" = "sonnet" ]
    [ "$correctness_model" = "sonnet" ]
}

@test "compose output is deterministic" {
    run "$CLI" compose --stage=ship
    first="$output"
    run "$CLI" compose --stage=ship
    [ "$output" = "$first" ]
}
