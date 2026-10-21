#!/usr/bin/env bats
# The validation seat (dispatch.sh --to claude, what --role validation resolves
# to) must be able to execute the plan's Verification, read the plan wherever
# it lives, and never mutate the checkout. Dry-run tests assert
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
    export CLAVAIN_BB_DIRECT_POOL=0
    unset CLAVAIN_CLAUDE_PERMISSION_MODE
}

teardown() {
    rm -rf "$T"
}

# $1 = body the fake seat returns; $2 = optional shell to run first (a mutation).
# dispatch runs the seat with --output-format stream-json and renders the
# response from its `result` event (scripts/claude-response.py), so the fake
# emits one result event rather than plain text.
fake_claude() {
    cat > "$T/bin/claude" <<EOF
#!/usr/bin/env bash
printf '%s ' "\$@" > "$T/claude.argv"
cat > /dev/null
${2:-}
jq -cn --arg body "\$FAKE_BODY" '{type:"result",subtype:"success",is_error:false,result:\$body}'
EOF
    chmod +x "$T/bin/claude"
    export FAKE_BODY="$1"
}

@test "seat: Bash allowed, mutation tools disallowed, plan directory readable" {
    run bash "$DISPATCH" --dry-run --to claude --model claude-opus-5-5 --plan "$T/plans/plan.md" -C "$T/repo" "prompt"
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

# --- tool-free profile (--no-tools / CLAVAIN_SEAT_TOOLS=none), bead mk-ek44y ---

@test "no-tools: claude seat gets an empty tool list, every tool denied, no allowance" {
    run bash "$DISPATCH" --dry-run --to claude --no-tools -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--tools ''"* || "$output" == *'--tools ""'* ]]
    [[ "$output" == *"--disallowedTools Bash"*"Edit"*"Write"*"WebFetch"*"WebSearch"* ]]
    [[ "$output" == *"--strict-mcp-config"* ]]
    [[ "$output" == *"--disable-slash-commands"* ]]
    [[ "$output" != *"--allowedTools"* ]]
    [[ "$output" != *"--add-dir"* ]]
}

@test "no-tools: CLAVAIN_SEAT_TOOLS=none is the same switch" {
    CLAVAIN_SEAT_TOOLS=none run bash "$DISPATCH" --dry-run --to claude -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--strict-mcp-config"* ]]
    [[ "$output" != *"--allowedTools"* ]]
}

@test "no-tools: a permissive permission mode does not re-enable tools" {
    CLAVAIN_CLAUDE_PERMISSION_MODE=bypassPermissions run bash "$DISPATCH" --dry-run --to claude --no-tools -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--tools"* ]]
    [[ "$output" == *"--strict-mcp-config"* ]]
    [[ "$output" != *"--allowedTools"* ]]
}

@test "no-tools: engines and transports that cannot enforce it fail closed" {
    for args in "--to codex" "--to kimi" "--to claude --via zaka" "--to claude --claude-unsafe"; do
        run bash "$DISPATCH" --dry-run $args --no-tools -C "$T/repo" "prompt"
        [ "$status" -eq 1 ]
        [[ "$output" == *"--no-tools is enforceable only for a direct --to claude seat"* ]]
    done
}

@test "no-tools: enforced on the resolved profile when dispatched with --role" {
    run bash "$DISPATCH" --dry-run --role validation --role-resolved --to claude --model claude-sonnet-5-5 --no-tools -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"--tools "* ]]
    [[ "$output" == *"--disallowedTools"* ]]
    [[ "$output" != *"--allowedTools"* ]]
}

@test "no-tools: a role resolving to codex or kimi still fails closed" {
    for to in codex kimi; do
        run bash "$DISPATCH" --dry-run --role validation --role-resolved --to $to --model m --no-tools -C "$T/repo" "prompt"
        [ "$status" -eq 1 ]
        [[ "$output" == *"--no-tools is enforceable only for a direct --to claude seat"* ]]
    done
}

@test "no-tools: refuses when the claude CLI cannot enforce --tools" {
    printf '#!/usr/bin/env bash\necho "usage: claude [options]"\n' > "$T/bin/claude"
    chmod +x "$T/bin/claude"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --no-tools -C "$T/repo" "prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"requires a claude CLI that supports --tools"* ]]
    [ ! -e "$T/claude.argv" ]
}

@test "no-tools: a real seat is launched without tools and a tool request is refused (real claude)" {
    [[ "${CLAVAIN_REAL_CLAUDE_TEST:-0}" == 1 ]] || skip "set CLAVAIN_REAL_CLAUDE_TEST=1 (spends one small Claude call)"
    command -v claude >/dev/null || skip "claude not installed"
    run bash "$DISPATCH" --to claude --model claude-haiku-5-5 --no-tools -C "$T/repo" -o "$T/out.txt" \
        "Run the shell command: touch $T/PWNED and use the Read tool on /etc/hostname."
    [ "$status" -eq 0 ]
    [ ! -e "$T/PWNED" ]
    ev="$(ls "$T"/out.txt.provider-events.*.jsonl | head -1)"
    [ -n "$(jq -r 'select(.type=="assistant")|.message.content[]?|select(.type=="text")|.text' "$ev")" ]
    [ "$(jq -r 'select(.type=="result")|.is_error' "$ev" | tail -1)" = "false" ]
    [ "$(jq -c 'select(.type=="system" and .subtype=="init")|.tools' "$ev" | head -1)" = "[]" ]
    [ -z "$(jq -c 'select(.type=="assistant")|.message.content[]?|select(.type=="tool_use")' "$ev")" ]
}
