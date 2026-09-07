#!/usr/bin/env bats
# The validation seat (dispatch.sh --to claude, what --role validation resolves
# to) must be able to execute the plan's Verification, read the plan wherever
# it lives, and never mutate the checkout (Sylveste-soj7). Dry-run tests assert
# on the assembled command; the run tests put a fake `claude` on PATH.

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/plans" "$T/bin" "$T/repo"
    printf '# plan\n' > "$T/plans/plan.md"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    unset CLAVAIN_CLAUDE_PERMISSION_MODE
}

teardown() {
    rm -rf "$T"
}

# $1 = body the fake seat prints; $2 = optional shell to run first (a mutation)
fake_claude() {
    cat > "$T/bin/claude" <<EOF
#!/usr/bin/env bash
printf '%s ' "\$@" > "$T/claude.argv"
cat > /dev/null
${2:-}
printf '%s\n' "\$FAKE_BODY"
EOF
    chmod +x "$T/bin/claude"
    export FAKE_BODY="$1"
}

@test "seat: Bash allowed, mutation tools disallowed, plan directory readable" {
    run bash "$DISPATCH" --dry-run --to claude --model claude-fable-5-1 --plan "$T/plans/plan.md" -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--permission-mode dontAsk"* ]]
    [[ "$output" == *"--allowedTools Bash"* ]]
    # the dry-run printer quotes with %q, which escapes the commas
    [[ "$output" == *"--disallowedTools Edit"*"Write"*"NotebookEdit"* ]]
    [[ "$output" == *"--add-dir $T/plans"* ]]
}

@test "seat: --claude-unsafe allows the mutation tools instead" {
    run bash "$DISPATCH" --dry-run --to claude --claude-unsafe -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--allowedTools Bash"*"Edit"*"Write"*"NotebookEdit"* ]]
    [[ "$output" != *"--disallowedTools"* ]]
}

@test "seat: a missing --plan fails before any model runs" {
    run bash "$DISPATCH" --dry-run --to claude -C "$T/repo" --plan "$T/plans/missing.md" "prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"--plan not found"* ]]
}

@test "seat: VERDICT: UNRUN lands in the sidecar as warn, never pass" {
    fake_claude $'VERDICT: UNRUN\nCRITERION: uv run pytest (command not found)\nRECEIPT: none\nBEYOND THE GAUGE:\n- none'
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: warn"* ]]
    [[ "$output" == *"UNRUN"* ]]
    [[ "$output" == *"command not found"* ]]
    run cat "$T/claude.argv"
    [[ "$output" == *"--allowedTools Bash"* ]]
}

@test "seat: VERDICT: PASS lands in the sidecar as pass" {
    fake_claude $'VERDICT: PASS\nCRITERION: none'
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "seat: VERDICT: FAIL lands in the sidecar as warn with the criterion" {
    fake_claude $'VERDICT: FAIL\nCRITERION: bats tests/shell/x.bats: not ok 3'
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: warn"* ]]
    [[ "$output" == *"not ok 3"* ]]
}

@test "seat: a run that mutates the checkout is an error verdict and a failed dispatch" {
    fake_claude $'VERDICT: PASS\nCRITERION: none' "printf 'y\\n' >> \"$T/repo/f.txt\"; : > \"$T/repo/new.txt\""
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"mutated the checkout"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" == *"f.txt"* ]]
    [[ "$output" == *"new.txt"* ]]
}

@test "seat: --claude-unsafe is not snapshotted" {
    fake_claude $'VERDICT: PASS\nCRITERION: none' ": > \"$T/repo/new.txt\""
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --claude-unsafe --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" != *"mutated the checkout"* ]]
}
