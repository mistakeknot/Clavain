#!/usr/bin/env bats
# Claude role seats must not inherit the operator's user-scope settings. The
# dry-run command is the contract for the real command assembled by dispatch.sh.

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    printf 'prompt\n' > "$T/prompt.md"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    unset CLAVAIN_CLAUDE_KEEP_USER_SETTINGS
}

teardown() {
    rm -rf "$T"
}

dry() {
    bash "$DISPATCH" "$@" --dry-run --prompt-file "$T/prompt.md" -o "$T/out.md" 2>&1
}

@test "claude excludes user settings before -p exactly once" {
    run dry --to claude
    [ "$status" -eq 0 ]
    normalized="${output//\\/}"
    [[ "$normalized" == *"--setting-sources project,local -p"* ]]
    [ "$(printf '%s\n' "$normalized" | grep -o -- '--setting-sources' | wc -l | tr -d ' ')" -eq 1 ]
}

@test "claude operator opt-out keeps user settings" {
    CLAVAIN_CLAUDE_KEEP_USER_SETTINGS=1 run dry --to claude
    [ "$status" -eq 0 ]
    [[ "$output" != *"--setting-sources"* ]]
}

@test "codex never carries claude setting sources" {
    run dry --to codex
    [ "$status" -eq 0 ]
    [[ "$output" != *"--setting-sources"* ]]
}

@test "claude role seat excludes user settings despite operator opt-out" {
    CLAVAIN_CLAUDE_KEEP_USER_SETTINGS=1 run dry --role validation --role-resolved --to claude
    [ "$status" -eq 0 ]
    normalized="${output//\\/}"
    [[ "$normalized" == *"--setting-sources project,local -p"* ]]
}
