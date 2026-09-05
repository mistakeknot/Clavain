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
    run bash "$DISPATCH_SCRIPT" --via zaka --to codex --model gpt-6-astra -s read-only --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"zaka spawn --agent codex"* ]]
    [[ "$output" == *"--transport app-server"* ]]
    [[ "$output" == *"--sandbox read-only"* ]]
    [[ "$output" == *"--approval-policy on-request"* ]]
    [[ "$output" != *"ignored"* ]]
}

@test "zaka: Codex requires an explicit model and rejects unsupported overrides" {
    run bash "$DISPATCH_SCRIPT" --via zaka --to codex --dry-run "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"explicit --model"* ]]
    run bash "$DISPATCH_SCRIPT" --via zaka --to codex --model gpt-6-astra -c sandbox_mode=danger-full-access --dry-run "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"unsupported"* ]]
}

@test "zaka: routing backend claude maps to claude-code adapter" {
    run bash "$DISPATCH_SCRIPT" --via zaka --to claude --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--agent claude-code"* ]]
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
    [[ "$output" == *"must be 'codex', 'kimi', or 'claude'"* ]]
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

@test "zaka: failed status capture kills the untracked App Server session" {
    mkdir -p "$TMPDIR_T/bin"
    export ZAKA_TEST_CALLS="$TMPDIR_T/calls"
    cat > "$TMPDIR_T/bin/zaka" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$ZAKA_TEST_CALLS"
case "$1" in
  spawn)
    if [[ "$*" == *--help* ]]; then echo '-transport'; else echo as-123456789012345678901234; fi ;;
  steer) echo '{}' ;;
  status) echo 'status unavailable' >&2; exit 1 ;;
  kill) exit 0 ;;
esac
FAKE
    chmod +x "$TMPDIR_T/bin/zaka"
    run env PATH="$TMPDIR_T/bin:$PATH" bash "$DISPATCH_SCRIPT" --via zaka --to codex --model gpt-6-astra -C "$TMPDIR_T" "test prompt"
    [ "$status" -ne 0 ]
    grep -q '^kill as-' "$ZAKA_TEST_CALLS"
}
