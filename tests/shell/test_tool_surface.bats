#!/usr/bin/env bats

# Integration tests for clavain-cli tool-surface
# Requires: clavain-cli-go binary built, config/tool-composition.yaml present

setup() {
    export CLI="${BATS_TEST_DIRNAME}/../../bin/clavain-cli-go"
    export CLAVAIN_CONFIG_DIR="${BATS_TEST_DIRNAME}/../../config"
    export SPRINT_LIB_PROJECT_DIR="${BATS_TEST_DIRNAME}/../../../.."

    if [[ ! -f "$CLI" ]]; then
        skip "clavain-cli-go not built — run build-clavain-cli.sh first"
    fi
}

@test "tool-surface produces formatted text with domains" {
    run "$CLI" tool-surface
    [ "$status" -eq 0 ]
    [[ "$output" == *"## Tool Composition"* ]]
    [[ "$output" == *"Coordination:"* ]]
    [[ "$output" == *"Quality:"* ]]
    [[ "$output" == *"### Workflow Groups"* ]]
    [[ "$output" == *"### Sequencing"* ]]
}

@test "tool-surface --json produces valid JSON with expected keys" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.version == 1'
    echo "$output" | jq -e '.domains | keys | length > 0'
    echo "$output" | jq -e '.curation_groups | keys | length > 0'
    echo "$output" | jq -e '.sequencing_hints | length > 0'
}

@test "tool-surface --json domains contain expected plugin names" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    # coordination domain should contain interlock
    echo "$output" | jq -e '.domains.coordination.plugins | index("interlock")'
    # quality domain should contain interflux
    echo "$output" | jq -e '.domains.quality.plugins | index("interflux")'
}

@test "tool-surface --json curation groups have context strings" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    # Each curation group must have non-empty context and plugins
    empty_ctx=$(echo "$output" | jq '[.curation_groups | to_entries[] | select(.value.context == "")] | length')
    empty_plugins=$(echo "$output" | jq '[.curation_groups | to_entries[] | select(.value.plugins | length == 0)] | length')
    [ "$empty_ctx" -eq 0 ]
    [ "$empty_plugins" -eq 0 ]
}

@test "tool-surface --json sequencing hints use first/then fields" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    # Every hint must have first, then, and hint fields
    missing=$(echo "$output" | jq '[.sequencing_hints[] | select(.first == "" or .then == "" or .hint == "")] | length')
    [ "$missing" -eq 0 ]
}

@test "tool-surface returns empty output when config missing" {
    CLAVAIN_CONFIG_DIR="/nonexistent" run "$CLI" tool-surface
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "sequencing hints are all <= 120 characters (R3 consolidation ratchet)" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    long_hints=$(echo "$output" | jq '[.sequencing_hints[] | select(.hint | length > 120)] | length')
    [ "$long_hints" -eq 0 ]
}

@test "tool-composition.yaml is < 100 lines" {
    config_file="${CLAVAIN_CONFIG_DIR}/tool-composition.yaml"
    [ -f "$config_file" ]
    line_count=$(wc -l < "$config_file")
    [ "$line_count" -lt 100 ]
}

@test "tool-surface --json includes disambiguation_hints key" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.disambiguation_hints'
}

@test "disambiguation hints are all <= 120 characters" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    long_hints=$(echo "$output" | jq '[.disambiguation_hints[] | select(.hint | length > 120)] | length')
    [ "$long_hints" -eq 0 ]
}

@test "disambiguation hints have required fields" {
    run "$CLI" tool-surface --json
    [ "$status" -eq 0 ]
    missing=$(echo "$output" | jq '[.disambiguation_hints[] | select(.plugins | length == 0 or .hint == "")] | length')
    [ "$missing" -eq 0 ]
}

@test "tool-surface output is deterministic" {
    run "$CLI" tool-surface
    first="$output"
    run "$CLI" tool-surface
    [ "$output" = "$first" ]
}
