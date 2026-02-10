#!/usr/bin/env bats
# Tests for hooks/session-start.sh

setup() {
    load test_helper
    stub_network
    # Also stub pgrep and command lookups used by session-start
    pgrep() { return 1; }
    export -f pgrep
}

@test "session-start: outputs valid JSON" {
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
}

@test "session-start: has additionalContext key" {
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
    result=$(echo "$output" | jq -e '.hookSpecificOutput.additionalContext')
    [ $? -eq 0 ]
}

@test "session-start: additionalContext is nonempty" {
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
    length=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext | length')
    [ "$length" -gt 0 ]
}

@test "session-start: exits zero" {
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
}
