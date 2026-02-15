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

@test "session-start: no sprint status when clean (run from /tmp)" {
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        cd /tmp && bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    # Should not contain sprint status section
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" != *"Sprint status"* ]]
}

@test "session-start: includes inflight agents from manifest" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.clavain/scratch"
    cat > "$tmpdir/.clavain/scratch/inflight-agents.json" <<'ENDJSON'
{"session_id":"prev-session-123","agents":[{"id":"agent-fd-arch","task":"review architecture"}],"timestamp":1234567890}
ENDJSON
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" == *"In-flight agents"* ]]
    [[ "$context" == *"review architecture"* ]]
}

@test "session-start: consumes manifest after reading" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.clavain/scratch"
    echo '{"session_id":"old","agents":[{"id":"agent-1","task":"test"}],"timestamp":0}' > "$tmpdir/.clavain/scratch/inflight-agents.json"
    bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    " >/dev/null 2>&1
    # Manifest should be deleted after reading
    [[ ! -f "$tmpdir/.clavain/scratch/inflight-agents.json" ]]
    rm -rf "$tmpdir"
}

@test "session-start: detects HANDOFF.md in sprint scan" {
    local tmpdir
    tmpdir=$(mktemp -d)
    touch "$tmpdir/HANDOFF.md"
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" == *"HANDOFF.md found"* ]]
}
