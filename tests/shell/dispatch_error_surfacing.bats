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

    # Extract the helpers into a sourced snippet (stop before the invocation block)
    HELPERS="$TMPDIR_T/helpers.sh"
    awk '
        /^_detect_codex_error\(\)[[:space:]]*\{/ { emit=1 }
        /^_write_error_verdict\(\)[[:space:]]*\{/ { emit=1 }
        /^_extract_verdict\(\)[[:space:]]*\{/ { emit=1 }
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

@test "detect: HTTP 400 in stderr + nonzero exit → error" {
    _load
    echo "stream error: unexpected status 400 Bad Request: model gpt-5.3-codex-xhigh not supported on ChatGPT account" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 1
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
    [[ "$output" == *"400"* ]]
}

@test "detect: HTTP 429 in stderr + nonzero exit → retry" {
    _load
    echo "429 Too Many Requests: rate limited" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 1
    [ "$status" -eq 0 ]
    [[ "$output" == retry$'\t'* ]]
}

@test "detect: ERROR prefix without HTTP code + nonzero exit → error" {
    _load
    echo "ERROR: something went wrong" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 1
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
    # The nonzero-exit fallback also yields "error" — require the scanned
    # stderr text so this pins the prefix scan, not the fallback.
    [[ "$output" == *"something went wrong"* ]]
}

# rc=0 gating (25e2b44): an executor QUOTING error-shaped text — grep results,
# docs snippets ("401 Unauthorized" inside a docs/solutions entry) — had a
# genuine CLEAN overwritten and the task redispatched forever (shadow-work run
# 39676448 rounds 11-13). Every real codex failure the scan has caught exited
# nonzero, so the stderr scan is gated on rc != 0; rc=0 runs stay policed by
# the zero-output heuristic below.

@test "detect: error-shaped stderr with rc=0 → no override (quoted text is not a failure)" {
    _load
    echo "docs excerpt: server returned 401 Unauthorized — see auth guide" > "$STDERR_FILE"
    printf '{"turns":3,"messages":2,"commands":1}\n' > "$STATE_FILE"
    printf 'Full review body.\nVERDICT: CLEAN\n' > "$OUTPUT"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 0 "$OUTPUT"
    [ "$status" -ne 0 ]
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
    run _detect_codex_error "$STDERR_FILE" "" 1
    [ "$status" -eq 0 ]
    [[ "$output" != *$'\x1b'* ]]
    # Fallback detail naturally has no escapes — require the scanned line's
    # content so stripping is actually what passed.
    [[ "$output" == *"400"* ]]
}

# --- mk-1hrx: zero-turn misread must not clobber a real pass -----------------
# Recorded incident (uncrancher run 61c1faeb, 2026-08-17): codex produced a
# full review ending "VERDICT: CLEAN", the verdict sidecar said STATUS: pass,
# but the JSONL meta parser read zero turns/messages/commands — and the warn
# override overwrote the pass. The state counters are a PROXY for "did
# anything happen"; the output file is direct evidence. When they disagree,
# the proxy is what's broken.

@test "detect: zero-state but real output → no override (mk-1hrx)" {
    _load
    : > "$STDERR_FILE"
    printf '{"turns":0,"messages":0,"commands":0}\n' > "$STATE_FILE"
    printf 'Full review body here.\nVERDICT: CLEAN\n' > "$OUTPUT"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 0 "$OUTPUT"
    [ "$status" -ne 0 ]
}

@test "detect: zero-state and EMPTY output still warns (heuristic keeps its job)" {
    _load
    : > "$STDERR_FILE"
    printf '{"turns":0,"messages":0,"commands":0}\n' > "$STATE_FILE"
    : > "$OUTPUT"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 0 "$OUTPUT"
    [ "$status" -eq 0 ]
    [[ "$output" == warn$'\t'* ]]
}

@test "detect: zero-state, no output file given → warn (old callers unaffected)" {
    _load
    : > "$STDERR_FILE"
    printf '{"turns":0,"messages":0,"commands":0}\n' > "$STATE_FILE"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 0
    [ "$status" -eq 0 ]
    [[ "$output" == warn$'\t'* ]]
}

@test "detect: real HTTP error is NOT suppressed by output existing" {
    _load
    echo "stream error: unexpected status 500 Internal Server Error" > "$STDERR_FILE"
    printf '{"turns":0,"messages":0,"commands":0}\n' > "$STATE_FILE"
    printf 'partial output before the failure\n' > "$OUTPUT"
    run _detect_codex_error "$STDERR_FILE" "$STATE_FILE" 1 "$OUTPUT"
    [ "$status" -eq 0 ]
    [[ "$output" == error$'\t'* ]]
    # Any nonzero exit yields "error" via fallback — require the HTTP detail
    # so this pins the scan-over-suppression branch it names.
    [[ "$output" == *"500"* ]]
}

# --- rc=0 gating (25e2b44): error-shaped text quoted by a successful run is not an error ---
#
# Before the gate, an executor that merely quoted "401 Unauthorized" from a docs
# snippet had its CLEAN verdict overwritten and was redispatched forever
# (shadow-work run 39676448 rounds 11-13). The five scan tests above pass a
# nonzero exit because every real codex failure the scan has caught exited
# nonzero; this one pins the other half of the contract.

@test "detect: error-shaped stderr with exit 0 is NOT an error (quoted, not raised)" {
    _load
    echo "grep hit: docs/solutions/x.md: 'HTTP 401 Unauthorized' means the token expired" > "$STDERR_FILE"
    run _detect_codex_error "$STDERR_FILE" "" 0
    [ "$status" -eq 1 ]
    [ -z "$output" ]
}

# --- ungrounded pass: unrecognized VERDICT line must not synthesize a pass ---
# _extract_verdict's fallback defaulted STATUS to pass when a VERDICT: line
# existed but matched neither CLEAN nor NEEDS_ATTENTION — so "VERDICT:
# QUESTION <q>" (or any future verdict vocabulary) produced a sidecar that
# orchestrate.py:736 reads as approved. An unrecognized verdict is not a pass.

@test "extract: VERDICT: QUESTION synthesizes warn, not pass" {
    _load
    printf 'Which schema should win?\nVERDICT: QUESTION which schema should win?\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q "^STATUS: warn$" "$VERDICT_FILE"
}

@test "extract: unknown verdict vocabulary synthesizes warn, not pass" {
    _load
    printf 'body\nVERDICT: SHIPSHAPE\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q "^STATUS: warn$" "$VERDICT_FILE"
}

@test "extract: CLEAN still synthesizes pass" {
    _load
    printf 'body\nVERDICT: CLEAN\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT"
    grep -q "^STATUS: pass$" "$VERDICT_FILE"
}
