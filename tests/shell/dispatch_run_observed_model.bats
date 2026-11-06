#!/usr/bin/env bats

setup() {
    load test_helper
    source "$BATS_TEST_DIRNAME/../../scripts/lib-dispatch-audit.sh"
    T="$(mktemp -d)"
    export CODEX_HOME="$T/codex"
    mkdir -p "$CODEX_HOME/sessions/2026/11/06"
    ROLE=validation ENGINE=codex MODEL=gpt-6.1-sol
    OUTPUT="$T/out" PROVIDER_EVENTS="$T/events" DISPATCH_RESULT_READY=true
    ATTEMPT_ID=attempt-1 VIA=
    TID=01a0f12b-4441-7732-b494-da5347122cea
    printf '{"type":"thread.started","thread_id":"%s"}\n' "$TID" > "$PROVIDER_EVENTS"
}
teardown() { rm -rf "$T"; }
rollout() {
    printf '{"type":"session_meta","payload":{"id":"%s"}}\n{"type":"turn_context","payload":{"model":"%s","effort":"high"}}\n{"type":"response_item","payload":{"type":"message","role":"assistant"}}\n' "$TID" "$1" > "$CODEX_HOME/sessions/2026/11/06/rollout-test-$TID.jsonl"
}
@test "JSONL receipt records the answering model and its own provider thread" {
    rollout gpt-6.1-sol
    run _build_dispatch_run_receipt 0
    [ "$status" -eq 0 ]
    [ "$(jq -r .observed_model <<< "$output")" = gpt-6.1-sol ]
    [ "$(jq -r .observed_thread_id <<< "$output")" = "$TID" ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = true ]
}
@test "JSONL receipt preserves a different answering model on failure" {
    rollout gpt-6-astra
    run _build_dispatch_run_receipt 1
    [ "$(jq -r .model <<< "$output")" = gpt-6.1-sol ]
    [ "$(jq -r .observed_model <<< "$output")" = gpt-6-astra ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = false ]
}
@test "JSONL receipt never uses another latest rollout when its own is missing" {
    rollout gpt-6-astra
    OTHER=01a0f12b-4441-7732-b494-da5347122ceb
    sed "s/$TID/$OTHER/g" "$CODEX_HOME/sessions/2026/11/06/rollout-test-$TID.jsonl" > "$CODEX_HOME/sessions/2026/11/06/rollout-test-$OTHER.jsonl"
    rm "$CODEX_HOME/sessions/2026/11/06/rollout-test-$TID.jsonl"
    run _build_dispatch_run_receipt 0
    [ "$(jq -r .observed_model <<< "$output")" = unknown ]
    [ "$(jq -r .observed_model_matches_requested <<< "$output")" = null ]
    [[ "$(jq -r .observed_reason <<< "$output")" == *"no session rollout for thread $TID"* ]]
}
