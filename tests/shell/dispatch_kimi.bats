#!/usr/bin/env bats

# Tests for the --to/--engine backend selector in dispatch.sh (kimi backend).
# All tests use --dry-run, so neither the codex nor the kimi binary is
# required — the tests assert on the assembled command line only.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"

    # Fixture kimi config defining both tier aliases
    KIMI_CFG="$TMPDIR_T/kimi-config.toml"
    cat > "$KIMI_CFG" <<'EOF'
default_model = "kimi-code/k3"

[models."kimi-code/kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"

[models."kimi-code/k3"]
provider = "managed:kimi-code"
model = "k3"
EOF
    export KIMI_CONFIG="$KIMI_CFG"
}

teardown() {
    rm -rf "$TMPDIR_T"
    unset KIMI_CONFIG
}

@test "engine: default (no --to) builds codex exec command" {
    run bash "$DISPATCH_SCRIPT" --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"codex exec -s workspace-write"* ]]
    [[ "$output" != *"kimi -p"* ]]
}

@test "engine: --to kimi builds kimi -p command" {
    run bash "$DISPATCH_SCRIPT" --to kimi --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"kimi -p"* ]]
    [[ "$output" != *"codex exec"* ]]
}

@test "engine: --engine kimi is an alias for --to kimi" {
    run bash "$DISPATCH_SCRIPT" --engine kimi --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"kimi -p"* ]]
}

@test "engine: invalid backend value exits 1" {
    run bash "$DISPATCH_SCRIPT" --to bogus "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"must be 'codex' or 'kimi'"* ]]
}

@test "kimi tier: fast maps to kimi-code/kimi-for-coding" {
    run bash "$DISPATCH_SCRIPT" --to kimi --tier fast --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"-m kimi-code/kimi-for-coding"* ]]
}

@test "kimi tier: deep maps to kimi-code/k3" {
    run bash "$DISPATCH_SCRIPT" --to kimi --tier deep --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"-m kimi-code/k3"* ]]
}

@test "kimi tier: unknown tier degrades to default model with warning" {
    run bash "$DISPATCH_SCRIPT" --to kimi --tier turbo --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"no kimi mapping"* ]]
    [[ "$output" != *"-m "* ]]
}

@test "kimi tier: alias missing from config degrades to default model with warning" {
    export KIMI_CONFIG="$TMPDIR_T/does-not-exist.toml"
    run bash "$DISPATCH_SCRIPT" --to kimi --tier fast --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"not found"* ]]
    [[ "$output" != *"-m "* ]]
}

@test "kimi: -m overrides model directly" {
    run bash "$DISPATCH_SCRIPT" --to kimi -m custom/model --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"kimi -m custom/model -p"* ]]
}

@test "kimi: --tier and -m are mutually exclusive" {
    run bash "$DISPATCH_SCRIPT" --to kimi --tier fast -m custom/model --dry-run "test prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Cannot use both --tier and --model"* ]]
}

@test "kimi: -C displays as cd prefix" {
    run bash "$DISPATCH_SCRIPT" --to kimi --dry-run -C /tmp "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"cd /tmp && kimi -p"* ]]
}

@test "kimi: -o displays as stdout redirect" {
    run bash "$DISPATCH_SCRIPT" --to kimi --dry-run -o /tmp/kimi-out.md "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"-p > /tmp/kimi-out.md"* ]]
}

@test "kimi: codex-only options warn and are dropped" {
    run bash "$DISPATCH_SCRIPT" --to kimi -s read-only --full-auto --dry-run "test prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"sandbox is codex-only"* ]]
    [[ "$output" == *"passthrough flags are not supported"* ]]
    [[ "$output" != *"read-only"* ]]
    [[ "$output" != *"--full-auto -p"* ]]
}

@test "kimi: --prompt-file is read and passed via -p" {
    printf 'review the auth handler\n' > "$TMPDIR_T/task.md"
    run bash "$DISPATCH_SCRIPT" --to kimi --dry-run --prompt-file "$TMPDIR_T/task.md"
    [ "$status" -eq 0 ]
    [[ "$output" == *"kimi -p"* ]]
    [[ "$output" == *"review the auth handler"* ]]
}
