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

@test "session-start: injects drift summary for Medium+ confidence" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.interwatch"
    cat > "$tmpdir/.interwatch/drift.json" <<'ENDJSON'
{"scan_date":"2026-02-20T10:00:00","watchables":{"roadmap":{"path":"docs/roadmap.md","exists":true,"score":5,"confidence":"Medium","stale":false,"signals":{},"recommended_action":"suggest-refresh","generator":"interpath:artifact-gen","generator_args":{"type":"roadmap"}},"vision":{"path":"docs/vision.md","exists":false,"score":0,"confidence":"Green","stale":false,"signals":{},"recommended_action":"none","generator":"interpath:artifact-gen","generator_args":{"type":"vision"}}}}
ENDJSON
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        # Fake interwatch detection so drift code activates
        export INTERWATCH_ROOT='/tmp/fake-interwatch'
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" == *"Drift detected"* ]]
    [[ "$context" == *"roadmap"* ]]
    # Green items should NOT appear
    [[ "$context" != *"vision"* ]]
}

@test "session-start: no drift injection when all items are Green/Low" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.interwatch"
    cat > "$tmpdir/.interwatch/drift.json" <<'ENDJSON'
{"scan_date":"2026-02-20T10:00:00","watchables":{"roadmap":{"path":"docs/roadmap.md","exists":true,"score":1,"confidence":"Low","stale":false,"signals":{},"recommended_action":"none","generator":"interpath:artifact-gen","generator_args":{"type":"roadmap"}},"vision":{"path":"docs/vision.md","exists":false,"score":0,"confidence":"Green","stale":false,"signals":{},"recommended_action":"none","generator":"interpath:artifact-gen","generator_args":{"type":"vision"}}}}
ENDJSON
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        export INTERWATCH_ROOT='/tmp/fake-interwatch'
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" != *"Drift detected"* ]]
}

@test "session-start: no drift injection when drift.json is missing" {
    local tmpdir
    tmpdir=$(mktemp -d)
    # No .interwatch directory at all
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        export INTERWATCH_ROOT='/tmp/fake-interwatch'
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" != *"Drift detected"* ]]
}

@test "session-start: handles malformed drift.json gracefully" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.interwatch"
    echo "not valid json {{{" > "$tmpdir/.interwatch/drift.json"
    run bash -c "
        curl() { return 1; }
        pgreg() { return 1; }
        export -f curl pgreg
        export INTERWATCH_ROOT='/tmp/fake-interwatch'
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    [[ "$context" != *"Drift detected"* ]]
}

@test "session-start: drift injection caps at 3 watchables" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.interwatch"
    cat > "$tmpdir/.interwatch/drift.json" <<'ENDJSON'
{"scan_date":"2026-02-20T10:00:00","watchables":{"a":{"path":"a.md","exists":true,"score":8,"confidence":"High","stale":false,"signals":{},"recommended_action":"auto-refresh","generator":"x","generator_args":{}},"b":{"path":"b.md","exists":true,"score":6,"confidence":"High","stale":false,"signals":{},"recommended_action":"auto-refresh","generator":"x","generator_args":{}},"c":{"path":"c.md","exists":true,"score":4,"confidence":"Medium","stale":false,"signals":{},"recommended_action":"suggest-refresh","generator":"x","generator_args":{}},"d":{"path":"d.md","exists":true,"score":3,"confidence":"Medium","stale":false,"signals":{},"recommended_action":"suggest-refresh","generator":"x","generator_args":{}}}}
ENDJSON
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        export -f curl pgrep
        export INTERWATCH_ROOT='/tmp/fake-interwatch'
        cd '$tmpdir' && bash '$HOOKS_DIR/session-start.sh'
    "
    rm -rf "$tmpdir"
    assert_success
    context=$(echo "$output" | jq -r '.hookSpecificOutput.additionalContext')
    # Should contain a, b, c (top 3 by score) but NOT d
    [[ "$context" == *"a ("* ]]
    [[ "$context" == *"b ("* ]]
    [[ "$context" == *"c ("* ]]
    [[ "$context" != *"d ("* ]]
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
