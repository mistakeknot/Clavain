#!/usr/bin/env bats
# mk-rd9f: every hook reads the session it is in.
#
# Claude Code hands each hook its session_id on stdin and exports
# CLAUDE_CODE_SESSION_ID into the Bash tool. CLAUDE_SESSION_ID exists only after
# hooks/session-start.sh wrote it into CLAUDE_ENV_FILE, so a reader keyed on it
# alone degrades to "unknown" in every session whose start hook did not fire —
# the register defect mk-hxgi found in the next-goal receipts. These tests pin
# the one helper that resolves the registers, and then prove two hooks key
# their state on the stdin session when the env register is absent.

setup() {
    load test_helper
    TEST_HOME="$(mktemp -d)"
    export HOME="$TEST_HOME"
    unset CLAUDE_SESSION_ID CLAUDE_CODE_SESSION_ID CLAUDE_ENV_FILE CLAVAIN_BEAD_ID
    source "$HOOKS_DIR/lib.sh"
}

teardown() {
    rm -rf "$TEST_HOME"
}

# ─── W1: the helper ───────────────────────────────────────────────────────────

@test "clavain_session_id: stdin session_id wins over both env registers" {
    export CLAUDE_SESSION_ID=env-start
    export CLAUDE_CODE_SESSION_ID=env-app
    run clavain_session_id '{"session_id":"stdin-1","hook_event_name":"PostToolUse"}'
    assert_success
    assert_output "stdin-1"
}

@test "clavain_session_id: CLAUDE_SESSION_ID wins over CLAUDE_CODE_SESSION_ID" {
    export CLAUDE_SESSION_ID=env-start
    export CLAUDE_CODE_SESSION_ID=env-app
    run clavain_session_id
    assert_success
    assert_output "env-start"
}

@test "clavain_session_id: CLAUDE_CODE_SESSION_ID alone resolves (start hook never fired)" {
    export CLAUDE_CODE_SESSION_ID=env-app
    run clavain_session_id ""
    assert_success
    assert_output "env-app"
}

@test "clavain_session_id: nothing set gives the default fallback" {
    run clavain_session_id
    assert_success
    assert_output "unknown"
}

@test "clavain_session_id: caller-supplied fallback is honoured" {
    run clavain_session_id "" "pid-4242"
    assert_success
    assert_output "pid-4242"
}

@test "clavain_session_id: malformed stdin falls through to the env chain, silently" {
    export CLAUDE_CODE_SESSION_ID=env-app
    # run merges stderr into $output, so an exact match proves nothing leaked.
    run clavain_session_id 'this is not json'
    assert_success
    assert_output "env-app"
}

@test "clavain_session_id: stdin without a session_id falls through" {
    export CLAUDE_CODE_SESSION_ID=env-app
    run clavain_session_id '{"tool_name":"Bash","session_id":null}'
    assert_success
    assert_output "env-app"
}

@test "companion cache key: keyed on the resolved session, per-process when none" {
    export CLAUDE_CODE_SESSION_ID=env-app
    _discover_all_companions
    run head -1 "$HOME/.cache/clavain/companion-roots.env"
    assert_output "# session=env-app"
}

# ─── W2: hooks key state on the stdin session ────────────────────────────────

@test "agents-md-refresh: throttle file is keyed on the stdin session, not 'default'" {
    local sid="s-refresh-$$-$RANDOM"
    rm -f "/tmp/clavain-agents-md-refresh-${sid}" "/tmp/clavain-agents-md-refresh-default"
    local before_default=0
    [[ -f /tmp/clavain-agents-md-refresh-default ]] && before_default=1
    local payload
    payload="{\"session_id\":\"${sid}\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"git commit -m x\"},\"tool_output\":{\"stdout\":\"create mode 100644 a\\ncreate mode 100644 b\"},\"cwd\":\"$HOME\"}"
    run bash -c "printf '%s' '$payload' | bash '$HOOKS_DIR/agents-md-refresh.sh'"
    assert_success
    [[ -f "/tmp/clavain-agents-md-refresh-${sid}" ]]
    rm -f "/tmp/clavain-agents-md-refresh-${sid}"
    # The shared key must not have been created by this run.
    if [[ $before_default -eq 0 ]]; then
        [[ ! -f /tmp/clavain-agents-md-refresh-default ]]
    fi
}

@test "catalog-reminder: the once-per-session sentinel is keyed on the stdin session" {
    # A stub ic whose sentinel remembers (name, scope) pairs and logs the scope
    # it was asked about — the scope IS the session key under test.
    export STUB_IC_LOG="$TEST_HOME/ic.log" STUB_IC_DIR="$TEST_HOME/ic-sentinels"
    mkdir -p "$TEST_HOME/bin" "$STUB_IC_DIR"
    cat > "$TEST_HOME/bin/ic" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "sentinel" && "${2:-}" == "check" ]]; then
    printf '%s %s\n' "$3" "$4" >> "$STUB_IC_LOG"
    f="$STUB_IC_DIR/$3.$4"
    [[ -f "$f" ]] && exit 1
    : > "$f"
fi
exit 0
STUB
    chmod +x "$TEST_HOME/bin/ic"
    export PATH="$TEST_HOME/bin:$PATH"
    local payload_a payload_b
    payload_a='{"session_id":"s-cat-a","tool_name":"Edit","tool_input":{"file_path":"/repo/commands/example.md"}}'
    payload_b='{"session_id":"s-cat-b","tool_name":"Edit","tool_input":{"file_path":"/repo/commands/example.md"}}'
    run bash -c "printf '%s' '$payload_a' | bash '$HOOKS_DIR/catalog-reminder.sh'"
    assert_success
    assert_output --partial "gen-catalog"
    # Same session again: silent.
    run bash -c "printf '%s' '$payload_a' | bash '$HOOKS_DIR/catalog-reminder.sh'"
    assert_success
    refute_output --partial "gen-catalog"
    # A different session, same env: reminded again. With the old bare read both
    # sessions shared the key "unknown" and the second was silent.
    run bash -c "printf '%s' '$payload_b' | bash '$HOOKS_DIR/catalog-reminder.sh'"
    assert_success
    assert_output --partial "gen-catalog"
    run cat "$STUB_IC_LOG"
    assert_line --index 0 "catalog_remind s-cat-a"
    assert_line --index 1 "catalog_remind s-cat-a"
    assert_line --index 2 "catalog_remind s-cat-b"
}

@test "lib-sprint bead_claim: claims under CLAUDE_CODE_SESSION_ID when the start hook never fired" {
    export CLAUDE_CODE_SESSION_ID=env-app
    local log="$TEST_HOME/bd.log"
    mkdir -p "$TEST_HOME/bin"
    cat > "$TEST_HOME/bin/bd" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$log"
case "\$1" in
    state) echo "(no \$3 state set)" ;;
esac
exit 0
EOF
    chmod +x "$TEST_HOME/bin/bd"
    export PATH="$TEST_HOME/bin:$PATH"
    source "$HOOKS_DIR/lib-sprint.sh"
    bead_claim mk-test1 >/dev/null 2>&1 || true
    run grep -c -- '--add-label claimed_by:env-app' "$log"
    assert_output "1"
}
