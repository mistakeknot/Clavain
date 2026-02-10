#!/usr/bin/env bats
# Tests for hooks/auto-compound.sh

setup_file() {
    export TMPDIR_COMPOUND="$(mktemp -d)"
    # Create transcript fixtures in temp dir
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_COMPOUND/transcript_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_insight.jsonl" "$TMPDIR_COMPOUND/transcript_insight.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_clean.jsonl" "$TMPDIR_COMPOUND/transcript_clean.jsonl"
}

teardown_file() {
    rm -rf "$TMPDIR_COMPOUND"
}

setup() {
    load test_helper
}

@test "auto-compound: noop when stop_hook_active" {
    run bash -c "echo '{\"stop_hook_active\": true, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Should produce no output when stop_hook_active is true
    assert_output ""
}

@test "auto-compound: detects commit signal" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Should output block decision with commit signal
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-compound: detects insight signal" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_insight.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Should output block decision with insight signal
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

    # Even with commit signal
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
}

@test "auto-compound: handles missing transcript" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"/nonexistent/path/transcript.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    assert_output ""
}
