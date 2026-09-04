#!/usr/bin/env bats
# Tests for hooks/gauge-gate-executor-spawn.sh: a PreToolUse gate on Pattern F
# executor spawns. The hook runs scripts/plan-gauge-lint.py on the plan named
# by the prompt's `PATTERN-F EXECUTOR PLAN:` marker and blocks the spawn when
# the plan fails the gauge or the plan file is missing. Every test builds a
# PreToolUse payload with jq and pipes it to the hook on stdin.

bats_require_minimum_version 1.5.0

setup() {
    load test_helper
    HOOK="$HOOKS_DIR/gauge-gate-executor-spawn.sh"
    # A refusal records a row in the register the hook resolves from
    # $INTERSPECT_DB / $CLAUDE_PROJECT_DIR; point both away from any live
    # register so no test writes into the developer's own evidence.
    unset INTERSPECT_DB
    export CLAUDE_PROJECT_DIR="$BATS_TEST_TMPDIR/nowhere"
    FIX_REPO="$BATS_TEST_TMPDIR/repo"
    BAD_PLAN="$BATS_TEST_TMPDIR/bad-plan.md"
    GOOD_PLAN="$BATS_TEST_TMPDIR/good-plan.md"
    PAYLOAD="$BATS_TEST_TMPDIR/payload.json"
    mkdir -p "$FIX_REPO/src"
    printf 'echo old\n' > "$FIX_REPO/src/thing.sh"
    # BAD PLAN: adds a TODO line, then claims grep for TODO prints nothing.
    # plan-gauge-lint reports GAUGE001 on it and exits 1.
    cat > "$BAD_PLAN" <<'PLAN'
# Plan: bad

## Task 1

In `src/thing.sh`:

old_string:
```bash
echo old
```

new_string:
```bash
echo old
# TODO remove marker
```

### Verify Task 1

```bash
grep -n 'TODO' src/thing.sh
```

Expected: prints NOTHING (exit 1).
PLAN
    # GOOD PLAN: the verify claim is consistent with the edit; linter exits 0.
    cat > "$GOOD_PLAN" <<'PLAN'
# Plan: good

## Task 1

In `src/thing.sh`:

old_string:
```bash
echo old
```

new_string:
```bash
echo old
echo new
```

### Verify Task 1

```bash
grep -n 'echo new' src/thing.sh
```

Expected: exit 0, one matching line.
PLAN
}

# Write a PreToolUse payload (tool_name Task) whose prompt is $1 to $PAYLOAD.
payload() {
    jq -nc --arg p "$1" \
        '{session_id:"s1",tool_name:"Task",tool_input:{prompt:$p,subagent_type:"general-purpose",model:"sonnet",description:"t"},cwd:"/tmp"}' \
        > "$PAYLOAD"
}

# An executor prompt: the two marker lines pointing at plan $1 and repo $2.
executor_prompt() {
    printf 'PATTERN-F EXECUTOR PLAN: %s\nREPO: %s\nYou are a Pattern F executor.\n' "$1" "$2"
}

@test "gauge-gate: prompt without the executor marker passes silently" {
    payload 'Summarise the README and report back.'
    run bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "gauge-gate: plan that fails the gauge blocks the spawn naming GAUGE001" {
    payload "$(executor_prompt "$BAD_PLAN" "$FIX_REPO")"
    run --separate-stderr bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.decision' <<<"$output")" = "block" ]
    [[ "$(jq -r '.reason' <<<"$output")" == *GAUGE001* ]]
}

@test "gauge-gate: plan that passes the gauge lets the spawn through" {
    payload "$(executor_prompt "$GOOD_PLAN" "$FIX_REPO")"
    run bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "gauge-gate: nonexistent plan path blocks with plan not found" {
    payload "$(executor_prompt "$BATS_TEST_TMPDIR/no-such-plan.md" "$FIX_REPO")"
    run --separate-stderr bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.decision' <<<"$output")" = "block" ]
    [[ "$(jq -r '.reason' <<<"$output")" == *"plan not found"* ]]
}

@test "gauge-gate: malformed stdin passes silently" {
    printf 'not json\n' > "$PAYLOAD"
    run bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "gauge-gate: a refusal writes one gate row into the project register" {
    local proj root db
    proj="$BATS_TEST_TMPDIR/proj"
    db="$proj/.clavain/interspect/interspect.db"
    mkdir -p "$proj/.clavain/interspect"
    export CLAUDE_PROJECT_DIR="$proj"
    export INTERSPECT_QUARANTINE_HOURS=0
    # shellcheck source=/dev/null
    source "$HOOKS_DIR/lib.sh" 2>/dev/null || skip "hooks/lib.sh not sourceable"
    root=$(_discover_interspect_plugin 2>/dev/null) || root=""
    [[ -n "$root" && -f "$root/hooks/lib-interspect.sh" ]] || skip "interspect library not found"
    # shellcheck source=/dev/null
    source "$root/hooks/lib-interspect.sh" 2>/dev/null || skip "lib-interspect.sh not sourceable"
    _interspect_ensure_db || skip "_interspect_ensure_db failed"
    [[ -f "$db" ]] || skip "register not created at $db"

    jq -nc --arg p "$(executor_prompt "$BAD_PLAN" "$FIX_REPO")" \
        '{session_id:"gate-test",tool_name:"Task",tool_input:{prompt:$p,subagent_type:"general-purpose",model:"sonnet",description:"t"},cwd:"/tmp"}' \
        > "$PAYLOAD"
    run --separate-stderr bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.decision' <<<"$output")" = "block" ]
    [[ "$(jq -r '.reason' <<<"$output")" == *GAUGE001* ]]

    run bash "$CLAUDE_PLUGIN_ROOT/scripts/pattern-f-verdict.sh" --list --session gate-test --db "$db"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [[ "${lines[0]}" == *$'\tgate\tgate\tFAIL\t'* ]]
    [[ "${lines[0]}" == *GAUGE001* ]]
    [[ "${lines[0]}" != *"plan-gauge-lint refused"* ]]
}

@test "gauge-gate: a refusal with no register still blocks and says the row was not recorded" {
    export CLAUDE_PROJECT_DIR="$BATS_TEST_TMPDIR/nowhere"
    payload "$(executor_prompt "$BAD_PLAN" "$FIX_REPO")"
    run --separate-stderr bash "$HOOK" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.decision' <<<"$output")" = "block" ]
    [[ "$stderr" == *"NOT recorded"* ]]
}
