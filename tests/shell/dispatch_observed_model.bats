#!/usr/bin/env bats
# mk-28gt: the terminal routing receipt records the model a codex seat actually
# ran (bb seat receipt on --via bb, session rollout on direct exec), and never
# passes the requested model off as observed.

setup() {
    load test_helper
    LIB="$BATS_TEST_DIRNAME/../../scripts/lib-dispatch-audit.sh"
    T="$(mktemp -d)"
    export CODEX_HOME="$T/codex"
    TID=01a0f12b-4441-7732-b494-da5347122cea
    mkdir -p "$CODEX_HOME/sessions/2026/09/30"
    ENGINE=codex MODEL=gpt-6.1-sol REASONING_EFFORT=high SERVICE_TIER=standard SANDBOX=read-only
    DISPATCH_SESSION_ID=s ATTEMPT_ID=attempt-1 DISPATCH_ID=d-1 CHECKOUT_BEFORE= WORKDIR="$T"
    OUTPUT="$T/out.md" PROVIDER_EVENTS="$T/events.jsonl" DISPATCH_RESULT_READY=true VIA=
    # shellcheck disable=SC1090
    source "$LIB"
}

teardown() { rm -rf "$T"; }

rollout() {  # rollout MODEL [THREAD_ID]
    local tid="${2:-$TID}"
    printf '{"type":"session_meta","payload":{"id":"%s"}}\n{"type":"turn_context","payload":{"model":"%s","effort":"high"}}\n' \
        "$tid" "$1" > "$CODEX_HOME/sessions/2026/09/30/rollout-2026-09-30T00-00-00-$tid.jsonl"
    printf '{"type":"thread.started","thread_id":"%s"}\n' "$tid" > "$PROVIDER_EVENTS"
}

exec_of() { _role_audit_context "$1" "${2:-0}" "${3:-success}" | jq -c '.execution'; }

@test "direct exec: completed receipt carries the observed model from the session rollout" {
    rollout gpt-6.1-sol
    run exec_of completed
    [ "$status" -eq 0 ]
    [ "$(jq -r .model <<< "$output")" = gpt-6.1-sol ]
    [ "$(jq -r .observed_model <<< "$output")" = gpt-6.1-sol ]
    [ "$(jq -r .observed_source <<< "$output")" = codex-session-rollout ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = true ]
}

@test "direct exec: a different observed model is recorded as such, and failed runs are covered too" {
    rollout gpt-6-astra
    run exec_of failed 1 terminal_error
    [ "$status" -eq 0 ]
    [ "$(jq -r .model <<< "$output")" = gpt-6.1-sol ]
    [ "$(jq -r .observed_model <<< "$output")" = gpt-6-astra ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = false ]
}

@test "direct exec: no session evidence is unknown, never the requested model" {
    : > "$PROVIDER_EVENTS"
    run exec_of completed
    [ "$status" -eq 0 ]
    [ "$(jq -r .observed_model <<< "$output")" = unknown ]
    [ "$(jq -r .observed_source <<< "$output")" = unavailable ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = null ]
}

@test "a broken helper degrades to unknown instead of failing the receipt" {
    rollout gpt-6.1-sol
    DISPATCH_SCRIPT_DIR="$T/no-such-dir"
    run exec_of completed
    [ "$status" -eq 0 ]
    [ "$(jq -r .observed_model <<< "$output")" = unknown ]
    [ "$(jq -r .observed_reason <<< "$output")" = "observed-model capture failed" ]
}

@test "bb transport: observed model comes from the bb seat receipt" {
    VIA=bb
    jq -cn '{attempt_id:"attempt-1",actual_model:"gpt-6.1-sol",actual_effort:"high"}' > "$OUTPUT.receipt.json"
    run exec_of completed
    [ "$status" -eq 0 ]
    [ "$(jq -r .observed_model <<< "$output")" = gpt-6.1-sol ]
    [ "$(jq -r .observed_source <<< "$output")" = bb-seat-receipt ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = true ]
}

@test "bb transport: an unknown actual model is not promoted to observed" {
    VIA=bb
    jq -cn '{attempt_id:"attempt-1",actual_model:"unknown",actual_effort:"unknown"}' > "$OUTPUT.receipt.json"
    run exec_of completed
    [ "$(jq -r .observed_model <<< "$output")" = unknown ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = null ]
}

@test "bb transport: a receipt left by another attempt is ignored" {
    VIA=bb
    jq -cn '{attempt_id:"someone-else",actual_model:"gpt-6.1-sol",actual_effort:"high"}' > "$OUTPUT.receipt.json"
    run exec_of completed
    [ "$(jq -r .observed_model <<< "$output")" = unknown ]
    [ "$(jq -r .observed_reason <<< "$output")" = "no bb seat receipt for this attempt" ]
}

@test "started state, zaka transport and non-codex engines carry no observed-model claim" {
    rollout gpt-6.1-sol
    run exec_of started
    [ "$(jq 'has("observed_model")' <<< "$output")" = false ]
    VIA=zaka run exec_of completed
    [ "$(jq 'has("observed_model")' <<< "$output")" = false ]
    ENGINE=claude run exec_of completed
    [ "$(jq 'has("observed_model")' <<< "$output")" = false ]
}
