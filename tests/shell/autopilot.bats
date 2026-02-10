#!/usr/bin/env bats
# Tests for hooks/autopilot.sh

setup() {
    load test_helper
    TEST_TMPDIR="$(mktemp -d)"
}

teardown() {
    rm -rf "$TEST_TMPDIR"
}

@test "autopilot: passthrough without flag file" {
    export CLAUDE_PROJECT_DIR="$TEST_TMPDIR"
    mkdir -p "$TEST_TMPDIR/.claude"
    # No autopilot.flag file
    run bash -c "echo '{}' | CLAUDE_PROJECT_DIR='$TEST_TMPDIR' bash '$HOOKS_DIR/autopilot.sh'"
    assert_success
    # Should produce no output (passthrough)
    assert_output ""
}

@test "autopilot: deny when flag exists" {
    export CLAUDE_PROJECT_DIR="$TEST_TMPDIR"
    mkdir -p "$TEST_TMPDIR/.claude"
    touch "$TEST_TMPDIR/.claude/autopilot.flag"
    run bash -c "echo '{\"tool_input\":{\"file_path\":\"/tmp/test.txt\"}}' | CLAUDE_PROJECT_DIR='$TEST_TMPDIR' bash '$HOOKS_DIR/autopilot.sh'"
    assert_success
    # Should output JSON with deny decision
    echo "$output" | jq -e '.hookSpecificOutput.permissionDecision == "deny"'
}

@test "autopilot: deny with flag, jq unavailable (fallback branch)" {
    export CLAUDE_PROJECT_DIR="$TEST_TMPDIR"
    mkdir -p "$TEST_TMPDIR/.claude"
    touch "$TEST_TMPDIR/.claude/autopilot.flag"
    # Hide jq by using a restricted PATH
    run bash -c "
        echo '{}' | CLAUDE_PROJECT_DIR='$TEST_TMPDIR' PATH='/usr/bin:/bin' bash -c '
            # Unset jq availability by removing it from PATH temporarily
            tmpbin=\$(mktemp -d)
            for cmd in /usr/bin/* /bin/*; do
                bn=\$(basename \"\$cmd\")
                if [ \"\$bn\" != \"jq\" ]; then
                    ln -sf \"\$cmd\" \"\$tmpbin/\$bn\" 2>/dev/null || true
                fi
            done
            export PATH=\"\$tmpbin\"
            bash \"$HOOKS_DIR/autopilot.sh\"
            rm -rf \"\$tmpbin\"
        '
    "
    assert_success
    echo "$output" | jq -e '.hookSpecificOutput.permissionDecision == "deny"'
}

@test "autopilot: handles missing CLAUDE_PROJECT_DIR" {
    run bash -c "echo '{}' | CLAUDE_PROJECT_DIR='' bash '$HOOKS_DIR/autopilot.sh'"
    assert_success
    assert_output ""
}

@test "autopilot: handles malformed stdin" {
    export CLAUDE_PROJECT_DIR="$TEST_TMPDIR"
    mkdir -p "$TEST_TMPDIR/.claude"
    touch "$TEST_TMPDIR/.claude/autopilot.flag"
    run bash -c "echo 'not-json' | CLAUDE_PROJECT_DIR='$TEST_TMPDIR' bash '$HOOKS_DIR/autopilot.sh'"
    assert_success
}
