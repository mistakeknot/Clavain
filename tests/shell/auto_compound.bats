#!/usr/bin/env bats
# Tests for hooks/auto-compound.sh

setup_file() {
    export TMPDIR_COMPOUND="$(mktemp -d)"
    # Create transcript fixtures in temp dir
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_COMPOUND/transcript_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_insight.jsonl" "$TMPDIR_COMPOUND/transcript_insight.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_clean.jsonl" "$TMPDIR_COMPOUND/transcript_clean.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_single_commit.jsonl" "$TMPDIR_COMPOUND/transcript_single_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_recovery.jsonl" "$TMPDIR_COMPOUND/transcript_recovery.jsonl"
}

teardown_file() {
    rm -rf "$TMPDIR_COMPOUND"
}

setup() {
    load test_helper
}

teardown() {
    # Clean up any sentinel files created during the test
    rm -f /tmp/clavain-stop-* /tmp/clavain-compound-last-* 2>/dev/null || true
}

@test "auto-compound: noop when stop_hook_active" {
    run bash -c "echo '{\"stop_hook_active\": true, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Should produce no output when stop_hook_active is true
    assert_output ""
}

@test "auto-compound: detects commit+bead-close signals (weight >= 2)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Should output block decision with combined signals
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-compound: detects insight+commit signals (weight >= 2)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_insight.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Should output block decision with combined signals
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-compound: single commit below threshold (weight 1)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_single_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Single commit has weight 1, below threshold of 2
    assert_output ""
}

@test "auto-compound: detects build/test recovery (weight >= 2)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_recovery.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Recovery signal (fail then pass) has weight 2, plus error-fix-cycle weight 1
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-compound: no signal passthrough" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_clean.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # No signals found, should produce no output
    assert_output ""
}

@test "auto-compound: exits zero always" {
    # Even with active stop hook
    run bash -c "echo '{\"stop_hook_active\": true}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success

    # Even with missing transcript
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"/nonexistent/file.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success

    # Even with combined signals
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
}

@test "auto-compound: skips when cross-hook sentinel exists" {
    local session_id="test-sentinel-$$"
    local sentinel="/tmp/clavain-stop-${session_id}"
    touch "$sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    rm -f "$sentinel"
    assert_success
    assert_output ""
}

@test "auto-compound: handles missing transcript" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"/nonexistent/path/transcript.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    assert_output ""
}
