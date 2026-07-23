#!/usr/bin/env bats

# The dispatch boundary must make exactly one context-gateway decision before
# constructing any Codex, Kimi, or Zaka invocation.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    GATEWAY_LOG="$TMPDIR_T/gateway.log"
    GATEWAY_STUB="$TMPDIR_T/context-gateway"
    cat > "$GATEWAY_STUB" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prompt="$(cat)"
printf '%s\n' "$*" >> "$CLAVAIN_GATEWAY_TEST_LOG"
if [[ "${CLAVAIN_GATEWAY_TEST_FAIL:-0}" == "1" ]]; then
    printf '%s' "$prompt"
    exit 3
fi
printf '<!-- clavain-context-gateway:v1 -->\n<tldrs-context>\nPACKET-%s\n</tldrs-context>\n\n%s' "$*" "$prompt"
EOF
    chmod +x "$GATEWAY_STUB"
    export CLAVAIN_CONTEXT_GATEWAY_BIN="$GATEWAY_STUB"
    export CLAVAIN_GATEWAY_TEST_LOG="$GATEWAY_LOG"
}

teardown() {
    rm -rf "$TMPDIR_T"
    unset CLAVAIN_CONTEXT_GATEWAY_BIN
    unset CLAVAIN_GATEWAY_TEST_LOG
    unset CLAVAIN_GATEWAY_TEST_FAIL
}

assert_one_gateway_call() {
    [ "$(wc -l < "$GATEWAY_LOG" | tr -d ' ')" -eq 1 ]
}

@test "gateway: codex dry-run injects one codex-profile packet" {
    run bash "$DISPATCH_SCRIPT" --dry-run -C "$TMPDIR_T" \
        "Refactor the authentication implementation and update its tests."

    [ "$status" -eq 0 ]
    [[ "$output" == *"PACKET-prepare --project $TMPDIR_T --harness codex --mode auto"* ]]
    assert_one_gateway_call
}

@test "gateway: kimi dry-run injects one kimi-profile packet" {
    run bash "$DISPATCH_SCRIPT" --to kimi --kimi-unsafe --dry-run -C "$TMPDIR_T" \
        "Refactor the authentication implementation and update its tests."

    [ "$status" -eq 0 ]
    [[ "$output" == *"PACKET-prepare --project $TMPDIR_T --harness kimi --mode auto"* ]]
    assert_one_gateway_call
}

@test "gateway: default Zaka route uses the Claude profile exactly once" {
    run bash "$DISPATCH_SCRIPT" --via zaka --dry-run -C "$TMPDIR_T" \
        "Refactor the authentication implementation and update its tests."

    [ "$status" -eq 0 ]
    [[ "$output" == *"PACKET-prepare --project $TMPDIR_T --harness claude --mode auto"* ]]
    [[ "$output" == *"zaka spawn --agent claude-code"* ]]
    assert_one_gateway_call
}

@test "gateway: explicit mode reaches the shared gateway" {
    run bash "$DISPATCH_SCRIPT" --context-gateway required --dry-run -C "$TMPDIR_T" \
        "Refactor the authentication implementation and update its tests."

    [ "$status" -eq 0 ]
    [[ "$output" == *"--harness codex --mode required"* ]]
    assert_one_gateway_call
}

@test "gateway: required failure prevents backend construction" {
    export CLAVAIN_GATEWAY_TEST_FAIL=1

    run bash "$DISPATCH_SCRIPT" --context-gateway required --dry-run -C "$TMPDIR_T" \
        "Refactor the authentication implementation and update its tests."

    [ "$status" -eq 3 ]
    [[ "$output" != *"codex exec"* ]]
    assert_one_gateway_call
}
