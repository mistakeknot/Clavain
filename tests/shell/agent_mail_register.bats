#!/usr/bin/env bats
# Tests for hooks/agent-mail-register.sh

setup() {
    load test_helper
}

@test "agent-mail-register: exits zero when agent mail is down" {
    run bash -c "
        curl() { return 1; }
        export -f curl
        export CLAUDE_PROJECT_DIR='/tmp'
        echo '{\"session_id\":\"test-123\"}' | bash '$HOOKS_DIR/agent-mail-register.sh'
    "
    assert_success
}

@test "agent-mail-register: exits zero with empty stdin" {
    run bash -c "
        curl() { return 1; }
        export -f curl
        export CLAUDE_PROJECT_DIR='/tmp'
        echo '' | bash '$HOOKS_DIR/agent-mail-register.sh'
    "
    assert_success
}

@test "agent-mail-register: exits zero when CLAUDE_PROJECT_DIR is empty" {
    run bash -c "
        curl() { return 1; }
        export -f curl
        export CLAUDE_PROJECT_DIR=''
        echo '{\"session_id\":\"test-123\"}' | bash '$HOOKS_DIR/agent-mail-register.sh'
    "
    assert_success
}
