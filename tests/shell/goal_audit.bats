#!/usr/bin/env bats
# Tests for hooks/lib-goal-audit.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/lib-intercore.sh"
    source "$HOOKS_DIR/lib-goal-audit.sh"
    STUB_DIR="$(mktemp -d)"
    PROJECT_DIR="$(mktemp -d)"
    export PATH="$STUB_DIR:$PATH"
}

teardown() {
    rm -rf "$STUB_DIR"
    rm -rf "$PROJECT_DIR"
}

make_ic_stub() {
    # $1 = audit stdout, $2 = audit exit code
    cat > "$STUB_DIR/ic" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "health" ]]; then exit 0; fi
if [[ "\$1" == "sentinel" ]]; then exit 0; fi
if [[ "\$1" == "goal" && "\$2" == "audit" ]]; then echo '$1'; exit $2; fi
exit 0
EOF
    chmod +x "$STUB_DIR/ic"
}

@test "goal_audit_reason: empty when no defects" {
    make_ic_stub "[]" 0
    run goal_audit_reason "test-session"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "goal_audit_reason: fires on defects" {
    make_ic_stub '[{"goal_id":"g1","kind":"dormant"}]' 1
    run goal_audit_reason "test-session"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Goal audit"* ]]
}

@test "goal_audit_reason: fail-open when ic absent" {
    export INTERCORE_BIN=""
    export PATH="/usr/bin:/bin"
    run goal_audit_reason "test-session"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "goal_audit_reason: fail-open when audit command errors" {
    make_ic_stub "ic usage" 3
    run goal_audit_reason "test-session"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "auto-stop-actions: fires entity-backed audit without prose signal" {
    make_ic_stub '[{"goal_id":"g1","kind":"dormant"}]' 1
    mkdir -p "$PROJECT_DIR/.claude" "$PROJECT_DIR/home"
    printf '%s\n' '{"type":"assistant","message":"Routine status update."}' > "$PROJECT_DIR/transcript.jsonl"
    hook_input=$(jq -nc --arg transcript "$PROJECT_DIR/transcript.jsonl" \
        '{session_id:"audit-hook-session",transcript_path:$transcript,stop_hook_active:false}')

    run env HOME="$PROJECT_DIR/home" bash -c \
        'cd "$1" && printf "%s\n" "$2" | "$3"' \
        _ "$PROJECT_DIR" "$hook_input" "$HOOKS_DIR/auto-stop-actions.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *'"decision": "block"'* ]]
    [[ "$output" == *"Goal audit"* ]]
}
