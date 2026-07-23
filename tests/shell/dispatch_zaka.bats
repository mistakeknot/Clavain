#!/usr/bin/env bats

# Tests for the --via zaka steerable-session mode in dispatch.sh.
# All tests use --dry-run, so neither the zaka nor the tmux binary is
# required — the tests assert on the assembled zaka commands only.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
}

teardown() {
    rm -rf "$TMPDIR_T"
    unset CLAVAIN_CONTEXT_GATEWAY_MODE
}

@test "zaka: default (no --to) spawns claude-code adapter" {
    run bash "$DISPATCH_SCRIPT" --via zaka --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"zaka spawn --agent claude-code"* ]]
    [[ "$output" == *"zaka steer <session>"* ]]
    [[ "$output" != *"codex exec"* ]]
}

@test "zaka: --to codex maps to codex adapter" {
    run bash "$DISPATCH_SCRIPT" --via zaka --to codex --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"zaka spawn --agent codex"* ]]
}

@test "zaka: --to kimi maps to kimi adapter" {
    run bash "$DISPATCH_SCRIPT" --via zaka --to kimi --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"zaka spawn --agent kimi"* ]]
}

@test "zaka: --to claude-code is valid in zaka mode" {
    run bash "$DISPATCH_SCRIPT" --via zaka --to claude-code --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"zaka spawn --agent claude-code"* ]]
}

@test "zaka: --to claude-code without --via zaka exits 1" {
    run bash "$DISPATCH_SCRIPT" --to claude-code --dry-run "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"requires --via zaka"* ]]
}

@test "zaka: invalid --via value exits 1" {
    run bash "$DISPATCH_SCRIPT" --via bogus "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"--via must be 'zaka'"* ]]
}

@test "zaka: invalid --to value still exits 1 with original message" {
    run bash "$DISPATCH_SCRIPT" --to bogus "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"must be 'codex' or 'kimi'"* ]]
}

@test "zaka: -C becomes --workdir" {
    run bash "$DISPATCH_SCRIPT" --via zaka --dry-run -C /tmp "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--workdir /tmp"* ]]
}

@test "zaka: -m becomes --model" {
    run bash "$DISPATCH_SCRIPT" --via zaka -m custom/model --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--model custom/model"* ]]
}

@test "zaka: codex-only options warn and are dropped" {
    run bash "$DISPATCH_SCRIPT" --via zaka -s read-only -o /tmp/out.md --name vet --full-auto --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"sandbox is codex-only"* ]]
    [[ "$output" == *"output-last-message is not supported"* ]]
    [[ "$output" == *"--name is not supported"* ]]
    [[ "$output" == *"passthrough flags are not supported"* ]]
    [[ "$output" != *"read-only"* ]]
    [[ "$output" != *"--name vet"* ]]
}

@test "zaka: --prompt-file is read and passed to steer" {
    printf 'refactor the auth handler\n' > "$TMPDIR_T/task.md"
    run bash "$DISPATCH_SCRIPT" --via zaka --dry-run --prompt-file "$TMPDIR_T/task.md"
    [ "$status" -eq 0 ]
    [[ "$output" == *"zaka steer <session>"* ]]
    [[ "$output" == *"refactor the auth handler"* ]]
}

@test "zaka: dry-run notes immediate return and steer/kill commands" {
    run bash "$DISPATCH_SCRIPT" --via zaka --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Returns immediately"* ]]
    [[ "$output" == *"zaka kill <session>"* ]]
}

@test "zaka: plain dispatch without --via still builds codex exec" {
    run bash "$DISPATCH_SCRIPT" --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"codex exec -s workspace-write"* ]]
    [[ "$output" != *"zaka spawn"* ]]
}
