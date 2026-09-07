#!/usr/bin/env bats
# A codex validation seat replays `uv run ...` without syncing: uv's sync step
# panics under the codex sandbox (runs 70691474 and 8565586e, goal a7f02287).

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'prompt\n' > "$T/prompt.md"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    unset UV_NO_SYNC CLAVAIN_CODEX_UV_NO_SYNC
}

teardown() {
    rm -rf "$T"
}

@test "a codex validation seat runs uv without syncing" {
    run bash "$DISPATCH" --role validation --role-resolved --to codex --dry-run -s workspace-write -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    [[ "$output" == *"UV_NO_SYNC=1"* ]]
}

@test "an executor seat keeps syncing" {
    run bash "$DISPATCH" --role routine-execution --role-resolved --to codex --dry-run -s workspace-write -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    [[ "$output" != *"UV_NO_SYNC"* ]]
}

@test "CLAVAIN_CODEX_UV_NO_SYNC=0 turns it off" {
    CLAVAIN_CODEX_UV_NO_SYNC=0 run bash "$DISPATCH" --role validation --role-resolved --to codex --dry-run -s workspace-write -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    [[ "$output" != *"UV_NO_SYNC"* ]]
}
