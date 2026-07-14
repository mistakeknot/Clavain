#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    load test_helper

    SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../scripts/remontoire-attention.sh"
    TEST_DIR="$(mktemp -d)"
    FIXTURE="$TEST_DIR/attention.json"
    CALL_LOG="$TEST_DIR/calls.log"
    ADAPTER="$TEST_DIR/remontoire-operator.sh"

    cat > "$ADAPTER" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$REMONTOIRE_ATTENTION_CALL_LOG"
[[ "$#" -eq 1 && "$1" == "attention" ]] || exit 90
[[ "${REMONTOIRE_ATTENTION_FAKE_FAILURE:-0}" != "1" ]] || exit 1
cat "$REMONTOIRE_ATTENTION_FIXTURE"
EOF
    chmod +x "$ADAPTER"

    export CLAVAIN_REMONTOIRE_ADAPTER="$ADAPTER"
    export REMONTOIRE_ATTENTION_FIXTURE="$FIXTURE"
    export REMONTOIRE_ATTENTION_CALL_LOG="$CALL_LOG"
}

teardown() {
    rm -rf "$TEST_DIR"
}

write_projection() {
    local stage="$1"
    local signed_receipt_id="${2:-}"
    local failure="${3:-}"
    jq -n \
        --arg stage "$stage" \
        --arg receipt "$signed_receipt_id" \
        --arg failure "$failure" \
        '{
          schema_version: "remontoire.attention/v1",
          cycle: {
            schema_version: "remontoire.cycle/v1",
            id: "cycle-1",
            portfolio: "sylveste",
            mode: "proposal",
            stage: $stage,
            created_at: "2026-07-14T00:00:00Z",
            updated_at: "2026-07-14T00:01:00Z",
            signed_receipt_id: $receipt,
            failure: $failure
          },
          promotions: []
        }' > "$FIXTURE"
}

@test "attention hook is silent for non-actionable stages" {
    for stage in new observing ranked no_op proposed declined completed; do
        write_projection "$stage"
        run --separate-stderr env CLAVAIN_AGENT_SURFACE=claude bash "$SCRIPT_UNDER_TEST" --format=hook
        [ "$status" -eq 0 ]
        [ -z "$output" ]
    done
    [ "$(wc -l < "$CALL_LOG" | tr -d ' ')" -eq 7 ]
    [ "$(sort -u "$CALL_LOG")" = "attention" ]
}

@test "awaiting approval emits an inspect-first Claude principal decision" {
    write_projection awaiting_approval

    run --separate-stderr env CLAVAIN_AGENT_SURFACE=claude bash "$SCRIPT_UNDER_TEST" --format=hook

    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' >/dev/null
    context="$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')"
    [[ "$context" == *"principal decision"* ]]
    [[ "$context" == *"/clavain:remontoire inspect cycle-1"* ]]
    [[ "$context" == *"does not approve or resume"* ]]
    [ "$(cat "$CALL_LOG")" = "attention" ]
}

@test "Codex attention uses the generated prompt namespace" {
    write_projection awaiting_approval

    run --separate-stderr env CLAVAIN_AGENT_SURFACE=codex bash "$SCRIPT_UNDER_TEST" --format=hook

    [ "$status" -eq 0 ]
    context="$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')"
    [[ "$context" == *"/prompts:clavain-remontoire inspect cycle-1"* ]]
    [[ "$context" != *"/clavain:remontoire inspect"* ]]
}

@test "approved and interrupted execution stages require explicit resume" {
    for stage in approved executing reviewing compounding; do
        : > "$CALL_LOG"
        write_projection "$stage"
        run --separate-stderr env CLAVAIN_AGENT_SURFACE=claude bash "$SCRIPT_UNDER_TEST" --format=hook
        [ "$status" -eq 0 ]
        context="$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')"
        [[ "$context" == *"$stage"* ]]
        [[ "$context" == *"/clavain:remontoire resume cycle-1"* ]]
        [[ "$context" == *"explicit"* ]]
        [ "$(cat "$CALL_LOG")" = "attention" ]
    done
}

@test "failed cycle routes to receipt replay when signed and doctor otherwise" {
    write_projection failed receipt-1 "review backend timed out"
    run --separate-stderr env CLAVAIN_AGENT_SURFACE=claude bash "$SCRIPT_UNDER_TEST" --format=hook
    [ "$status" -eq 0 ]
    context="$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')"
    [[ "$context" == *"/clavain:remontoire receipt replay cycle-1"* ]]

    write_projection failed "" "receipt signing failed"
    run --separate-stderr env CLAVAIN_AGENT_SURFACE=claude bash "$SCRIPT_UNDER_TEST" --format=hook
    [ "$status" -eq 0 ]
    context="$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')"
    [[ "$context" == *"/clavain:remontoire doctor"* ]]
}

@test "JSON format carries compact ready promotions without making terminal cycles noisy" {
    write_projection completed
    jq '.promotions = [{
      id: "Revel-prom",
      title: "Land measured cache improvement",
      description: "Promoted from bounded experiment Revel-exp.",
      acceptance_criteria: "Measured target remains satisfied.",
      status: "open",
      priority: 2,
      issue_type: "feature",
      dependent_count: 4,
      labels: ["remontoire-promotion", "remontoire:cycle:cycle-0"],
      dependencies: [{depends_on_id: "Revel-exp", type: "discovered-from"}]
    }]' "$FIXTURE" > "$FIXTURE.next"
    mv "$FIXTURE.next" "$FIXTURE"

    run --separate-stderr env CLAVAIN_AGENT_SURFACE=codex bash "$SCRIPT_UNDER_TEST" --format=json

    [ "$status" -eq 0 ]
    echo "$output" | jq -e '
      .schema_version == "clavain.remontoire-attention/v1" and
      .available == true and
      .action == null and
      .promotions == [{
        id: "Revel-prom",
        title: "Land measured cache improvement",
        description: "Promoted from bounded experiment Revel-exp.",
        acceptance_criteria: "Measured target remains satisfied.",
        status: "open",
        priority: 2,
        issue_type: "feature",
        dependent_count: 4,
        labels: ["remontoire-promotion", "remontoire:cycle:cycle-0"],
        dependencies: [{depends_on_id: "Revel-exp", type: "discovered-from"}]
      }]' >/dev/null
}

@test "unavailable or malformed attention data fails silent for hooks and degrades for JSON" {
    write_projection completed
    run --separate-stderr env REMONTOIRE_ATTENTION_FAKE_FAILURE=1 bash "$SCRIPT_UNDER_TEST" --format=hook
    [ "$status" -eq 0 ]
    [ -z "$output" ]

    run --separate-stderr env REMONTOIRE_ATTENTION_FAKE_FAILURE=1 bash "$SCRIPT_UNDER_TEST" --format=json
    [ "$status" -eq 0 ]
    echo "$output" | jq -e '.available == false and .action == null and .promotions == []' >/dev/null

    printf 'not-json\n' > "$FIXTURE"
    run --separate-stderr bash "$SCRIPT_UNDER_TEST" --format=hook
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
