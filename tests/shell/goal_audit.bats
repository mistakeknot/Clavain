#!/usr/bin/env bats
# Tests for hooks/lib-goal-audit.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/lib-intercore.sh"
    source "$HOOKS_DIR/lib-goal-audit.sh"
    STUB_DIR="$(mktemp -d)"
    PROJECT_DIR="$(cd "$(mktemp -d)" && pwd -P)"
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

make_ic_stub_capture() {
    # Records the audit argv, and backs `ic state get/set` with a file store so
    # the session pin behaves like the real thing.
    cat > "$STUB_DIR/ic" <<EOF
#!/usr/bin/env bash
STATE="$STUB_DIR/state"; mkdir -p "\$STATE"
case "\$1" in
    health|sentinel) exit 0 ;;
    state)
        if [[ "\$2" == "get" ]]; then cat "\$STATE/\$3-\$4" 2>/dev/null; exit 0; fi
        if [[ "\$2" == "set" ]]; then cat > "\$STATE/\$3-\$4"; exit 0; fi
        exit 0 ;;
    goal)
        if [[ "\$2" == "audit" ]]; then
            printf '%s ' "\$@" >> "$STUB_DIR/audit-args"; printf '\n' >> "$STUB_DIR/audit-args"
            echo '[{"goal_id":"g1","kind":"dormant"}]'
            exit 1
        fi
        exit 0 ;;
esac
exit 0
EOF
    chmod +x "$STUB_DIR/ic"
}

@test "goal_audit_reason: pin survives cwd drift into another repo" {
    make_ic_stub_capture
    unset CLAUDE_PROJECT_DIR
    OTHER_DIR="$(cd "$(mktemp -d)" && pwd -P)"

    # First call pins the project the session started in...
    ( cd "$PROJECT_DIR" && goal_audit_reason "pin-session" >/dev/null )
    # ...a later call from a drifted cwd must still audit the pinned project.
    ( cd "$OTHER_DIR" && goal_audit_reason "pin-session" >/dev/null )

    # The LAST call is the drifted one; it must still name the pinned project.
    # (A bare `! grep` is not set -e safe, so assert on the recorded line.)
    last_call="$(tail -1 "$STUB_DIR/audit-args")"
    [[ "$last_call" == *"--project=$PROJECT_DIR"* ]]
    [[ "$last_call" != *"--project=$OTHER_DIR"* ]]
    rm -rf "$OTHER_DIR"
}

@test "goal_audit_reason: reported command names the pinned project" {
    make_ic_stub_capture
    unset CLAUDE_PROJECT_DIR
    OTHER_DIR="$(cd "$(mktemp -d)" && pwd -P)"

    ( cd "$PROJECT_DIR" && goal_audit_reason "pin-session" >/dev/null )
    output=$( cd "$OTHER_DIR" && goal_audit_reason "pin-session" )

    [[ "$output" == *"$PROJECT_DIR"* ]]
    [[ "$output" != *"$OTHER_DIR"* ]]
    rm -rf "$OTHER_DIR"
}

@test "goal_audit_reason: CLAUDE_PROJECT_DIR is honoured at pin time" {
    make_ic_stub_capture
    OTHER_DIR="$(cd "$(mktemp -d)" && pwd -P)"
    export CLAUDE_PROJECT_DIR="$PROJECT_DIR"

    ( cd "$OTHER_DIR" && goal_audit_reason "env-session" >/dev/null )

    grep -qF -- "--project=$PROJECT_DIR" "$STUB_DIR/audit-args"
    rm -rf "$OTHER_DIR"
}

@test "goal_audit_reason: a pin to a vanished directory re-resolves" {
    make_ic_stub_capture
    unset CLAUDE_PROJECT_DIR
    GONE_DIR="$(cd "$(mktemp -d)" && pwd -P)"

    ( cd "$GONE_DIR" && goal_audit_reason "stale-session" >/dev/null )
    rm -rf "$GONE_DIR"
    ( cd "$PROJECT_DIR" && goal_audit_reason "stale-session" >/dev/null )

    grep -qF -- "--project=$PROJECT_DIR" "$STUB_DIR/audit-args"
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
