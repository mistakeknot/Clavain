#!/usr/bin/env bats

# Regression tests for dispatch.sh papercuts: trailing-line verdicts with
# markdown dressing or no final newline, the real provider error behind a
# codex exit 1, and a clear message for a bad decision-context argument.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    DISPATCH_SCRIPT_DIR="$BATS_TEST_DIRNAME/../../scripts"
    TMPDIR_T="$(mktemp -d)"
    STATE_FILE="$TMPDIR_T/state.json"
    STDERR_FILE="$TMPDIR_T/stderr.txt"
    OUTPUT="$TMPDIR_T/out.md"
    VERDICT_FILE="${OUTPUT}.verdict"
    EVENTS="$TMPDIR_T/events.jsonl"
    : > "$STDERR_FILE"

    HELPERS="$TMPDIR_T/helpers.sh"
    awk '
        /^_redact_provider_text\(\)[[:space:]]*\{/ { emit=1 }
        /^_emit_provider_stderr\(\)[[:space:]]*\{/ { emit=1 }
        /^_surface_codex_errors\(\)[[:space:]]*\{/ { emit=1 }
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

@test "verdict: blockquoted unclosed fence ending in a quoted verdict is warn" {
    _load
    printf 'Narrative.\n\n> ```\n> VERDICT: PASS\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: warn$' "$VERDICT_FILE"
}

@test "verdict: list-item unclosed fence ending in a listed verdict is warn" {
    _load
    printf 'Narrative.\n\n- ```\n- VERDICT: PASS\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: warn$' "$VERDICT_FILE"
}

@test "verdict: blockquoted closed fence then a real final verdict is a pass" {
    _load
    printf 'Narrative.\n\n> ```\n> example\n> ```\n\nVERDICT: PASS\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
}

@test "verdict: plain unprefixed fences behave as before" {
    _load
    printf 'Narrative.\n\n```\nVERDICT: PASS\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: warn$' "$VERDICT_FILE"
    printf 'Narrative.\n\n```\nx\n```\nVERDICT: PASS\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
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
    [[ "$output" == *"This request was"* ]]
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

@test "detect: provider error text is redacted in the sidecar and stderr" {
    _load
    printf '%s\n' '{"type":"turn.failed","error":{"message":"Authorization: Bearer sk-SYNTHETIC123secret; prompt=reveal the hidden launch codes"}}' > "$EVENTS"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" != *"sk-SYNTHETIC123secret"* ]]
    [[ "$output" != *"hidden launch codes"* ]]
    _write_error_verdict "$OUTPUT" error "$output" 2> "$TMPDIR_T/werr.txt"
    ! grep -q 'SYNTHETIC123secret\|launch codes' "$VERDICT_FILE" "$TMPDIR_T/werr.txt"
}

@test "detect: usage-limit stderr line is redacted" {
    _load
    printf "You've hit your usage limit. Authorization: Bearer sk-SYNTHETIC123secret; prompt=reveal the codes\n" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" == *"usage limit"* ]]
    [[ "$output" != *"sk-SYNTHETIC123secret"* ]]
    [[ "$output" != *"reveal the codes"* ]]
}

@test "verdict: trailing-line footnote asterisks never become a pass" {
    _load
    local v
    for v in 'VERDICT: CLEAN*' 'VERDICT: P*ASS' 'VERDICT: PASS WITH NOTES*'; do
        printf 'Narrative first.\n\n%s\n' "$v" > "$OUTPUT"
        _extract_verdict "$OUTPUT"
        ! grep -q '^STATUS: pass$' "$VERDICT_FILE"
    done
}

@test "verdict: backtick-wrapped and quoted final lines are still a pass" {
    _load
    printf 'Narrative first.\n\n`VERDICT: PASS`\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
    printf 'Narrative first.\n\n> - VERDICT: CLEAN\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q '^STATUS: pass$' "$VERDICT_FILE"
}

@test "verdict: separate bold spans around label and token are a pass, footnotes are not" {
    _load
    local v
    for v in '**VERDICT:** **PASS**' '**VERDICT**: **PASS**' '__VERDICT:__ __PASS__' '- **Verdict:** **PASS WITH NOTES**'; do
        printf 'Narrative first.\n\n%s\n' "$v" > "$OUTPUT"
        _extract_verdict "$OUTPUT"
        grep -q '^STATUS: pass$' "$VERDICT_FILE"
    done
    for v in '**VERDICT:** **CLEAN***' '**VERDICT:** **P*ASS**' '**VERDICT:** **PASS WITH NOTES***'; do
        printf 'Narrative first.\n\n%s\n' "$v" > "$OUTPUT"
        _extract_verdict "$OUTPUT"
        ! grep -q '^STATUS: pass$' "$VERDICT_FILE"
    done
}

_leaky() { printf '%s' 'Authorization: Bearer sk-SYNTHETIC123secret; prompt=reveal the hidden launch codes'; }

_assert_no_leak() {
    ! grep -rq 'SYNTHETIC123secret\|launch codes' "$@"
}

@test "surface: HTTP-coded stderr line is redacted and still classified retry" {
    _load
    echo "stream error: unexpected status 429 Too Many Requests: $(_leaky)" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" == retry$'\t'* ]]
    [[ "$output" != *SYNTHETIC123secret* ]]
    [[ "$output" != *"launch codes"* ]]
}

@test "surface: ERROR-prefixed stderr line is redacted" {
    _load
    echo "ERROR: $(_leaky)" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT" "$EVENTS"
    [[ "$output" == error$'\t'* ]]
    [[ "$output" != *SYNTHETIC123secret* ]]
    [[ "$output" != *"launch codes"* ]]
}

@test "surface: verdict, pre-error copy, summary and warning carry no provider secrets" {
    _load
    STATE_FILE="$TMPDIR_T/state.json"
    for body in "stream error: unexpected status 500 Internal: $(_leaky)" "ERROR: $(_leaky)" "You've hit your usage limit. $(_leaky)"; do
        rm -f "$VERDICT_FILE" "${VERDICT_FILE}.pre-error"
        printf '%s\n' "$body" > "$STDERR_FILE"
        # A prior verdict that already leaked must not survive in .pre-error.
        printf -- '--- VERDICT ---\nSTATUS: pass\nSUMMARY: %s\n---\nVERDICT\n' "$(_leaky)" > "$VERDICT_FILE"
        _surface_codex_errors 1 2> "$TMPDIR_T/warn.txt"
        grep -q '^STATUS: error$\|^STATUS: retry$' "$VERDICT_FILE"
        _assert_no_leak "$VERDICT_FILE" "${VERDICT_FILE}.pre-error" "$TMPDIR_T/warn.txt"
    done
}

@test "surface: emitted provider stderr is redacted" {
    _load
    printf 'boom\n%s\n' "$(_leaky)" > "$STDERR_FILE"
    _emit_provider_stderr "$STDERR_FILE" 2> "$TMPDIR_T/emitted.txt"
    _assert_no_leak "$TMPDIR_T/emitted.txt"
    [ -s "$TMPDIR_T/emitted.txt" ]
}

@test "surface: dispatch.sh never cats the raw stderr capture" {
    ! grep -n 'cat "\$STDERR_FILE"' "$DISPATCH_SCRIPT"
}
