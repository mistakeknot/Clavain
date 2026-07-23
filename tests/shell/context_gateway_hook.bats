#!/usr/bin/env bats

setup() {
    load test_helper

    HOOK="$BATS_TEST_DIRNAME/../../hooks/context-gateway.sh"
    TEST_DIR="$(mktemp -d)"
    GATEWAY="$TEST_DIR/gateway"
    LOG="$TEST_DIR/gateway.log"
    cat > "$GATEWAY" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
printf '%s\n' "$*" > "$CLAVAIN_GATEWAY_HOOK_TEST_LOG"
exit "${CLAVAIN_GATEWAY_HOOK_TEST_EXIT:-0}"
EOF
    chmod +x "$GATEWAY"
    export CLAVAIN_CONTEXT_GATEWAY_BIN="$GATEWAY"
    export CLAVAIN_GATEWAY_HOOK_TEST_LOG="$LOG"
}

teardown() {
    rm -rf "$TEST_DIR"
    unset CLAVAIN_CONTEXT_GATEWAY_BIN
    unset CLAVAIN_GATEWAY_HOOK_TEST_LOG
    unset CLAVAIN_GATEWAY_HOOK_TEST_EXIT
    unset KIMI_PLUGIN_ROOT
}

@test "hook: Claude plugin is the safe default harness" {
    run "$HOOK" <<< '{"prompt":"Fix auth.py","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    [ "$(cat "$LOG")" = "hook --harness claude --mode auto" ]
}

@test "hook: Kimi plugin root selects the Kimi adapter" {
    export KIMI_PLUGIN_ROOT="$TEST_DIR/plugin"
    run "$HOOK" <<< '{"prompt":"Fix auth.py","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    [ "$(cat "$LOG")" = "hook --harness kimi --mode auto" ]
}

@test "hook: installer can select the Codex adapter explicitly" {
    run "$HOOK" codex <<< '{"prompt":"Fix auth.py","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    [ "$(cat "$LOG")" = "hook --harness codex --mode auto" ]
}

@test "hook: runtime failures fail open" {
    export CLAVAIN_GATEWAY_HOOK_TEST_EXIT=19
    run "$HOOK" codex <<< '{"prompt":"Fix auth.py","cwd":"/tmp"}'
    [ "$status" -eq 0 ]
    [[ "$output" == *"failing open"* ]]
}
