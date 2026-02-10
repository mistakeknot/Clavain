#!/usr/bin/env bats
# Tests for hooks/lib.sh — escape_for_json utility

setup() {
    load test_helper
    source "$HOOKS_DIR/lib.sh"
}

@test "escape_for_json: basic string unchanged" {
    run escape_for_json "hello"
    assert_success
    assert_output "hello"
}

@test "escape_for_json: escapes double quotes" {
    run escape_for_json 'say "hi"'
    assert_success
    assert_output 'say \"hi\"'
}

@test "escape_for_json: escapes backslashes" {
    run escape_for_json 'a\b'
    assert_success
    assert_output 'a\\b'
}

@test "escape_for_json: escapes newlines" {
    run escape_for_json $'line1\nline2'
    assert_success
    assert_output 'line1\nline2'
}

@test "escape_for_json: escapes tabs" {
    run escape_for_json $'col1\tcol2'
    assert_success
    assert_output 'col1\tcol2'
}

@test "escape_for_json: empty string" {
    run escape_for_json ''
    assert_success
    assert_output ""
}

@test "source lib.sh has no side effects" {
    run bash -c "source '$HOOKS_DIR/lib.sh' 2>&1"
    assert_success
    assert_output ""
}
