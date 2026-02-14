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

@test "auto-compound: commit+bead-close below threshold (weight 2 < 3)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # commit (1) + bead-closed (1) = 2, below new threshold of 3
    assert_output ""
}

@test "auto-compound: detects insight+commit+investigation signals (weight >= 3)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_insight.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # insight (1) + commit (1) + investigation (2) = 4, above threshold of 3
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-compound: single commit below threshold (weight 1)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_single_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # Single commit has weight 1, below threshold of 3
    assert_output ""
}

@test "auto-compound: detects recovery+investigation signals (weight >= 3)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_recovery.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # recovery (2) + investigation (2) = 4, above threshold of 3
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

@test "auto-compound: skips when opt-out file exists" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude"
    touch "$tmpdir/.claude/clavain.no-autocompound"
    run bash -c "cd '$tmpdir' && echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_insight.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    rm -rf "$tmpdir"
    assert_success
    assert_output ""
}

@test "auto-compound: skips when throttle sentinel is recent" {
    local session_id="test-throttle-$$"
    local throttle_sentinel="/tmp/clavain-compound-last-${session_id}"
    touch "$throttle_sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_insight.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    rm -f "$throttle_sentinel"
    assert_success
    assert_output ""
}

@test "auto-compound: handles missing transcript" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"/nonexistent/path/transcript.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    assert_output ""
}

@test "auto-compound: version-bump+commit triggers (weight >= 3)" {
    # version-bump (2) + commit (1) = 3, meets threshold
    local fixture="$TMPDIR_COMPOUND/transcript_version_bump.jsonl"
    printf '{"role":"assistant","content":"Running bump-version.sh 0.7.0"}\n{"role":"assistant","content":"Running \"git commit -m bump\""}\n' > "$fixture"
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$fixture\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    echo "$output" | jq -e '.decision == "block"'
}
