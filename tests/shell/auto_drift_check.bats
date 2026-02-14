#!/usr/bin/env bats
# Tests for hooks/auto-drift-check.sh

setup_file() {
    export TMPDIR_DRIFT="$(mktemp -d)"
    # Reuse transcript fixtures from auto-compound tests
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_DRIFT/transcript_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_insight.jsonl" "$TMPDIR_DRIFT/transcript_insight.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_clean.jsonl" "$TMPDIR_DRIFT/transcript_clean.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_single_commit.jsonl" "$TMPDIR_DRIFT/transcript_single_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_recovery.jsonl" "$TMPDIR_DRIFT/transcript_recovery.jsonl"
}

teardown_file() {
    rm -rf "$TMPDIR_DRIFT"
}

setup() {
    load test_helper
}

teardown() {
    rm -f /tmp/clavain-stop-* /tmp/clavain-drift-last-* 2>/dev/null || true
}

@test "auto-drift-check: noop when stop_hook_active" {
    run bash -c "echo '{\"stop_hook_active\": true, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}

@test "auto-drift-check: commit+bead-close triggers at threshold 2" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    # commit (1) + bead-closed (1) = 2, meets drift threshold of 2
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-drift-check: single commit below threshold (weight 1)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_single_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}

@test "auto-drift-check: no signal passthrough" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_clean.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}

@test "auto-drift-check: reason mentions interwatch:watch" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    echo "$output" | jq -r '.reason' | grep -q 'interwatch:watch'
}

@test "auto-drift-check: exits zero always" {
    run bash -c "echo '{\"stop_hook_active\": true}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"/nonexistent/file.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
}

@test "auto-drift-check: skips when shared sentinel exists" {
    local session_id="test-drift-sentinel-$$"
    local sentinel="/tmp/clavain-stop-${session_id}"
    touch "$sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    rm -f "$sentinel"
    assert_success
    assert_output ""
}

@test "auto-drift-check: skips when opt-out file exists" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude"
    touch "$tmpdir/.claude/clavain.no-driftcheck"
    run bash -c "cd '$tmpdir' && echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    rm -rf "$tmpdir"
    assert_success
    assert_output ""
}

@test "auto-drift-check: skips when throttle sentinel is recent" {
    local session_id="test-drift-throttle-$$"
    local throttle_sentinel="/tmp/clavain-drift-last-${session_id}"
    touch "$throttle_sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    rm -f "$throttle_sentinel"
    assert_success
    assert_output ""
}

@test "auto-drift-check: recovery signals trigger (weight 2)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_recovery.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    # recovery (2) + investigation (2) = 4, above threshold
    echo "$output" | jq -e '.decision == "block"'
}
