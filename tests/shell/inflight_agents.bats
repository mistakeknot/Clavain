#!/usr/bin/env bats
# Tests for in-flight agent detection functions in hooks/lib.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/lib.sh"
    TEST_TMPDIR=$(mktemp -d)
}

teardown() {
    rm -rf "$TEST_TMPDIR"
}

@test "_claude_project_dir: derives path from CWD" {
    run _claude_project_dir "/root/projects/Clavain"
    assert_success
    [[ "$output" == *"/.claude/projects/-root-projects-Clavain" ]]
}

@test "_claude_project_dir: uses current dir when no arg" {
    run _claude_project_dir
    assert_success
    [[ -n "$output" ]]
}

@test "_extract_agent_task: returns unknown for missing file" {
    run _extract_agent_task "/nonexistent/file.jsonl"
    assert_success
    assert_output "unknown"
}

@test "_extract_agent_task: extracts save-to pattern" {
    echo '{"message":{"content":"You are reviewing code. save your FULL analysis to: /tmp/fd-arch-review.md"}}' > "$TEST_TMPDIR/agent-test.jsonl"
    run _extract_agent_task "$TEST_TMPDIR/agent-test.jsonl"
    assert_success
    assert_output "/tmp/fd-arch-review.md"
}

@test "_extract_agent_task: extracts read-and-execute pattern" {
    echo '{"message":{"content":"Read and execute /tmp/flux-dispatch-123/fd-quality.md"}}' > "$TEST_TMPDIR/agent-test.jsonl"
    run _extract_agent_task "$TEST_TMPDIR/agent-test.jsonl"
    assert_success
    assert_output "/tmp/flux-dispatch-123/fd-quality.md"
}

@test "_extract_agent_task: falls back to first line" {
    echo '{"message":{"content":"Analyze the architecture of this codebase for coupling issues"}}' > "$TEST_TMPDIR/agent-test.jsonl"
    run _extract_agent_task "$TEST_TMPDIR/agent-test.jsonl"
    assert_success
    assert_output "Analyze the architecture of this codebase for coupling issues"
}

@test "_extract_agent_task: truncates at 80 chars" {
    local long_content
    long_content=$(printf 'A%.0s' {1..120})
    echo "{\"message\":{\"content\":\"${long_content}\"}}" > "$TEST_TMPDIR/agent-test.jsonl"
    run _extract_agent_task "$TEST_TMPDIR/agent-test.jsonl"
    assert_success
    [[ ${#output} -le 80 ]]
}

@test "_detect_inflight_agents: returns 1 when no agents found" {
    # Override to point at an empty dir so no agents are found
    _claude_project_dir() { echo "$TEST_TMPDIR/empty-project"; }
    mkdir -p "$TEST_TMPDIR/empty-project"
    run _detect_inflight_agents "test-session" 10
    [[ $status -eq 1 ]]
}

@test "_write_inflight_manifest: creates manifest with agents" {
    # Create a fake session directory structure
    local fake_project="${TEST_TMPDIR}/projects"
    local fake_session="${fake_project}/test-session-123/tasks"
    mkdir -p "$fake_session"
    echo '{"message":{"content":"Review architecture"}}' > "$fake_session/agent-review-1.jsonl"
    # Touch it to ensure it's within 1 minute
    touch "$fake_session/agent-review-1.jsonl"

    # Override _claude_project_dir to return our fake dir
    _claude_project_dir() { echo "$fake_project"; }

    # Create .clavain/scratch in tmpdir
    mkdir -p "${TEST_TMPDIR}/.clavain/scratch"
    cd "$TEST_TMPDIR"

    run _write_inflight_manifest "test-session-123"
    assert_success
    [[ -f ".clavain/scratch/inflight-agents.json" ]]
    # Verify it's valid JSON with agents array
    jq -e '.agents | length > 0' ".clavain/scratch/inflight-agents.json"
}

@test "_write_inflight_manifest: skips compact artifacts" {
    local fake_project="${TEST_TMPDIR}/projects"
    local fake_session="${fake_project}/test-session/tasks"
    mkdir -p "$fake_session"
    echo '{"message":{"content":"compacting"}}' > "$fake_session/agent-acompact-1.jsonl"
    touch "$fake_session/agent-acompact-1.jsonl"

    _claude_project_dir() { echo "$fake_project"; }
    mkdir -p "${TEST_TMPDIR}/.clavain/scratch"
    cd "$TEST_TMPDIR"

    run _write_inflight_manifest "test-session"
    assert_success
    # No manifest should be written (only compact agents)
    [[ ! -f ".clavain/scratch/inflight-agents.json" ]]
}

@test "_write_inflight_manifest: no-op when session dir missing" {
    _claude_project_dir() { echo "/nonexistent/path"; }
    cd "$TEST_TMPDIR"

    run _write_inflight_manifest "nonexistent-session"
    assert_success
    [[ ! -f ".clavain/scratch/inflight-agents.json" ]]
}
