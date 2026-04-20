#!/usr/bin/env bats

# Tests for codex error surfacing in dispatch.sh (sylveste-mb3i).
# Exercises _detect_codex_error + _write_error_verdict by sourcing dispatch.sh
# with a guard that prevents the top-level codex invocation from running.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    STATE_FILE="$TMPDIR_T/state.json"
    STDERR_FILE="$TMPDIR_T/stderr.txt"
    OUTPUT="$TMPDIR_T/out.md"
    VERDICT_FILE="${OUTPUT}.verdict"

    # Extract both helpers into a sourced snippet (stop before the invocation block)
    HELPERS="$TMPDIR_T/helpers.sh"
    awk '
        /^_detect_codex_error\(\)[[:space:]]*\{/ { emit=1 }
        /^_write_error_verdict\(\)[[:space:]]*\{/ { emit=1 }
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

@test "detect: HTTP 400 in stderr → error" {
    _load
    echo "stream error: unexpected status 400 Bad Request: model gpt-5.3-codex-xhigh not supported on ChatGPT account" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 0
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
    [[ "$output" == *"400"* ]]
}

@test "detect: HTTP 429 in stderr → retry" {
    _load
    echo "429 Too Many Requests: rate limited" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 0
    [ "$status" -eq 0 ]
    [[ "$output" == retry$'\t'* ]]
}

@test "detect: ERROR prefix without HTTP code → error" {
    _load
    echo "ERROR: something went wrong" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 0
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
}

@test "detect: non-zero exit with empty stderr → error" {
    _load
    : > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 137
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
    [[ "$output" == *"137"* ]]
}

@test "detect: zero-everything state + zero exit → warn" {
    _load
    : > "$STDERR_FILE"
    printf '{"turns":0,"messages":0,"commands":0}\n' > "$STATE_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 0
    [ "$status" -eq 0 ]
    [[ "$output" == warn$'\t'* ]]
}

@test "detect: healthy session → no error" {
    _load
    : > "$STDERR_FILE"
    printf '{"turns":3,"messages":2,"commands":1}\n' > "$STATE_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 0
    [ "$status" -ne 0 ]
}

@test "write: error verdict overrides existing verdict" {
    _load
    cat > "$VERDICT_FILE" <<PRE
--- VERDICT ---
STATUS: pass
FILES: 0 changed
FINDINGS: 0 (P0: 0, P1: 0, P2: 0)
SUMMARY: Agent reports clean completion.
---
PRE
    _write_error_verdict "$OUTPUT" "error" "Codex HTTP 400: model not supported"
    [ -f "$VERDICT_FILE" ]
    grep -q "^STATUS: error$" "$VERDICT_FILE"
    grep -q "Codex HTTP 400" "$VERDICT_FILE"
    # Pre-error snapshot preserved for debugging
    [ -f "${VERDICT_FILE}.pre-error" ]
    grep -q "STATUS: pass" "${VERDICT_FILE}.pre-error"
}

@test "write: retry kind yields STATUS: retry" {
    _load
    _write_error_verdict "$OUTPUT" "retry" "HTTP 429"
    grep -q "^STATUS: retry$" "$VERDICT_FILE"
}

@test "write: warn kind yields STATUS: warn" {
    _load
    _write_error_verdict "$OUTPUT" "warn" "No model output"
    grep -q "^STATUS: warn$" "$VERDICT_FILE"
}

@test "detect: ANSI escapes stripped from error detail" {
    _load
    printf '\x1b[31mstream error: unexpected status 400 Bad Request\x1b[0m\n' > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 0
    [ "$status" -eq 0 ]
    [[ "$output" != *$'\x1b'* ]]
}
