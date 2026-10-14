#!/usr/bin/env bats

# Regression tests for dispatch.sh papercuts: trailing-line verdicts with
# markdown dressing or no final newline, the real provider error behind a
# codex exit 1, and a clear message for a bad decision-context argument.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    STATE_FILE="$TMPDIR_T/state.json"
    STDERR_FILE="$TMPDIR_T/stderr.txt"
    OUTPUT="$TMPDIR_T/out.md"
    VERDICT_FILE="${OUTPUT}.verdict"
    EVENTS="$TMPDIR_T/events.jsonl"
    : > "$STDERR_FILE"

    HELPERS="$TMPDIR_T/helpers.sh"
    awk '
        /^_provider_error_text\(\)[[:space:]]*\{/ { emit=1 }
        /^_detect_codex_error\(\)[[:space:]]*\{/ { emit=1 }
        /^_write_error_verdict\(\)[[:space:]]*\{/ { emit=1 }
        /^_extract_verdict\(\)[[:space:]]*\{/ { emit=1 }
        /^_dispatch_role_profile\(\)[[:space:]]*\{/ { emit=1 }
        emit {
            print
            if ($0 ~ /^}[[:space:]]*$/) { emit=0 }
        }
    ' "$DISPATCH_SCRIPT" > "$HELPERS"
}

teardown() {
    rm -rf "$TMPDIR_T"
}

_load() {
    # shellcheck disable=SC1090
    source "$HELPERS"
}

@test "verdict: final-line 'VERDICT: PASS WITH NOTES' with no trailing newline is a pass" {
    _load
    printf 'Reviewed the plan.\n\nVERDICT: PASS WITH NOTES' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
    ! grep -q 'No verdict line' "$VERDICT_FILE"
}

@test "verdict: markdown-bold final verdict line is a pass" {
    _load
    printf 'Narrative first.\n\n**VERDICT: PASS**\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
}

@test "verdict: bold label with trailing token and no newline is a pass" {
    _load
    printf 'Narrative first.\n\n**Verdict:** PASS WITH NOTES' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
}

@test "verdict: a final FAIL line stays warn, never pass" {
    _load
    printf 'Narrative first.\n\n**VERDICT: FAIL**' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    ! grep -q '^STATUS: pass$' "$VERDICT_FILE"
}

@test "detect: exit 1 with turn.failed event surfaces the provider message" {
    _load
    printf '%s\n' '{"type":"turn.started"}' \
      '{"type":"turn.failed","error":{"message":"You have hit your usage limit. Try again later."}}' > "$EVENTS"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
    [[ "$output" == *"turn.failed"* ]]
    [[ "$output" == *"usage limit"* ]]
    [[ "$output" != *"no stderr error pattern matched)"* ]]
}

@test "detect: turn.failed content-filter error is classified explicitly" {
    _load
    printf '%s\n' '{"type":"turn.failed","error":{"message":"This request was flagged by the cyber content filter."}}' > "$EVENTS"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" == *"content filter"* ]]
    [[ "$output" == *"flagged"* ]]
}

@test "detect: top-level error event message is surfaced" {
    _load
    printf '%s\n' '{"type":"error","message":"stream disconnected before completion"}' > "$EVENTS"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" == *"stream disconnected"* ]]
}

@test "detect: usage-limit line on stderr is surfaced when no events exist" {
    _load
    printf "You've hit your usage limit. Upgrade to Pro.\n" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" == *"usage limit"* ]]
}

_role_stub() {
    ic() { echo 'json: unknown field "round"' >&2; return 1; }
    _dispatch_routing_precheck() { return 0; }
    PRODUCER_IDENTITY=""
    DISPATCH_SCRIPT_DIR="$BATS_TEST_DIRNAME/../../scripts"
}

@test "role: inline JSON in the decision context names the real cause" {
    _load; _role_stub
    CLAVAIN_DECISION_CONTEXT='{"reasons":[],"rationale":"x"}'
    run _dispatch_role_profile routine-execution
    [ "$status" -ne 0 ]
    [[ "$output" == *"must be the path of a JSON file, not inline JSON"* ]]
    [[ "$output" != *"could not resolve dispatch role"* ]]
}

@test "role: a missing context file names the file" {
    _load; _role_stub
    CLAVAIN_DECISION_CONTEXT="$TMPDIR_T/nope.json"
    run _dispatch_role_profile routine-execution
    [[ "$output" == *"is not a readable file"* ]]
}

@test "role: unknown context key is reported as a rejected decision context" {
    _load; _role_stub
    printf '{"reasons":[],"rationale":"x","round":3}\n' > "$TMPDIR_T/ctx.json"
    CLAVAIN_DECISION_CONTEXT="$TMPDIR_T/ctx.json"
    CLAVAIN_POOL_HEADROOM=0
    run _dispatch_role_profile routine-execution
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown field"* ]]
    [[ "$output" == *"decision context was rejected"* ]]
}
