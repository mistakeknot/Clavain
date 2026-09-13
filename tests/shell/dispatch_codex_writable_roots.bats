#!/usr/bin/env bats
# A workspace-write codex seat is granted the tool caches it needs outside the
# workspace (uv's by default), else a validator replaying `uv run pytest`
# cannot run it and must answer UNRUN (run d9dd99e0, goal a7f02287).

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/cache" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'prompt\n' > "$T/prompt.md"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
}

teardown() {
    rm -rf "$T"
}

dry() {
    bash "$DISPATCH" --to codex --dry-run -s "$1" -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md" 2>&1
}

@test "workspace-write grants the configured root when it exists" {
    CLAVAIN_CODEX_WRITABLE_ROOTS="$T/cache" run dry workspace-write
    [ "$status" -eq 0 ]
    [[ "$output" == *"sandbox_workspace_write.writable_roots="* ]]
    [[ "$output" == *"$T/cache"* ]]
}

@test "two roots are both granted" {
    mkdir -p "$T/cache2"
    CLAVAIN_CODEX_WRITABLE_ROOTS="$T/cache:$T/cache2" run dry workspace-write
    [ "$status" -eq 0 ]
    [[ "$output" == *"$T/cache"* ]]
    [[ "$output" == *"$T/cache2"* ]]
}

@test "a root that does not exist is not granted" {
    CLAVAIN_CODEX_WRITABLE_ROOTS="$T/missing" run dry workspace-write
    [ "$status" -eq 0 ]
    [[ "$output" != *"writable_roots"* ]]
}

@test "an empty setting grants nothing" {
    CLAVAIN_CODEX_WRITABLE_ROOTS= run dry workspace-write
    [ "$status" -eq 0 ]
    [[ "$output" != *"writable_roots"* ]]
}

@test "a read-only sandbox never carries writable roots" {
    CLAVAIN_CODEX_WRITABLE_ROOTS="$T/cache" run dry read-only
    [ "$status" -eq 0 ]
    [[ "$output" != *"writable_roots"* ]]
}
