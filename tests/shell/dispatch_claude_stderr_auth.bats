#!/usr/bin/env bats
# mk-bi91j: an authentication failure from `claude -p` (last non-empty stderr
# line, claude/API-specific shapes) is classified as an operational access
# failure (account_access_absent) instead of terminal_error. No stderr excerpt
# is printed. Only dummy token values are used here.

setup() {
    load test_helper
    ROOT="$BATS_TEST_DIRNAME/../.."
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    DUMMY=sk-test-dummy-0123456789abcdef
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'prompt\n' > "$T/prompt.md"
    # Fake claude: prints $FAKE_ERR on stderr and exits with $FAKE_EXIT.
    cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
cat > /dev/null
printf '%s\n' "$FAKE_ERR" >&2
exit "${FAKE_EXIT:-1}"
FAKE
    chmod +x "$T/bin/claude"
    export PATH="$T/bin:$PATH"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/state/receipts.jsonl"
    export CLAVAIN_DISPATCH_FAILURE_FILE="$T/failure.class"
    unset CLAVAIN_BEAD_ID BB_THREAD_ID BB_SERVER_URL ANTHROPIC_BASE_URL CLAUDE_SESSION_ID CODEX_THREAD_ID \
        DISPATCH_SESSION_ID CLAVAIN_TOKEN_LEAK_HOOK CODEX_POOL_AUTH_TOKEN ANTHROPIC_AUTH_TOKEN
}

teardown() { rm -rf "$T"; }

run_claude() {
    run bash "$DISPATCH" --to claude --model m1 -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
}

@test "auth failure: operational class and auth note, no excerpt header" {
    export FAKE_ERR='API Error: 401 authentication_error'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = account_access_absent ]
    [[ "$output" == *"claude reported an authentication failure"* ]]
    [[ "$output" != *"claude stderr (last lines, redacted):"* ]]
    grep -q 'claude reported an authentication failure' "$T/out.md.verdict"
}

@test "auth failure class is one the fallback walks continue past" {
    # The three fallback walks (profile, tier, backend) all list this class.
    run grep -A1 -F 'case "$CLAVAIN_LAST_FAILURE_CLASS" in' "$ROOT/scripts/dispatch.sh"
    [ "$(printf '%s\n' "$output" | grep -c 'account_access_absent')" -ge 3 ]
}

@test "other claude exit-1 failure keeps terminal_error and no auth note" {
    export FAKE_ERR='something else broke'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_error ]
    [[ "$output" != *"authentication failure"* ]]
    [[ "$output" == *"claude -p exited 1"* ]]
    [[ "$output" != *"claude stderr (last lines, redacted):"* ]]
}

@test "policy denial in claude stderr keeps terminal_policy" {
    export FAKE_ERR='request blocked: 403 Forbidden'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_policy ]
}

@test "a token value in claude stderr is absent from all output and artifacts" {
    export ANTHROPIC_AUTH_TOKEN="$DUMMY"
    export FAKE_ERR="API Error: 401 bearer ${DUMMY} rejected"
    run_claude
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    ! grep -rqF "$DUMMY" "$T/out.md"* "$T/state" "$T/failure.class" 2>/dev/null
}

@test "no stderr excerpt header on a non-auth failure" {
    export FAKE_ERR='something else broke'
    run_claude
    [ "$status" -ne 0 ]
    [[ "$output" != *"claude stderr (last lines"* ]]
}

@test "quoted login phrase mid-line stays terminal_error" {
    export FAKE_ERR='model said: you should please run /login and more text'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_error ]
    [[ "$output" != *"authentication failure"* ]]
}

@test "echoed text on a later line (reviewer reproduction) stays terminal_error" {
    export FAKE_ERR="$(printf 'model diagnostic follows:\nFailed to authenticate with the test registry\n')"
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_error ]
    [[ "$output" != *"authentication failure"* ]]
}

@test "generic 'failed to authenticate' as the last line stays terminal_error" {
    export FAKE_ERR='Failed to authenticate with the test registry'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_error ]
}

@test "auth line followed by a later unrelated line stays terminal_error" {
    export FAKE_ERR="$(printf 'Invalid API key\nsomething unrelated happened\n')"
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_error ]
    [[ "$output" != *"authentication failure"* ]]
}

@test "each kept shape as the last line reclassifies" {
    local shape
    for shape in 'Invalid API key' 'Please run /login' 'OAuth token has expired' \
        'OAuth token has been revoked' 'API Error: 401 unauthorized' \
        'authentication_error' 'Error: Invalid API key' "$(printf 'noise\nPlease run /login\n\n')"; do
        rm -f "$T/failure.class"
        FAKE_ERR="$shape" run_claude
        [ "$status" -ne 0 ]
        [ "$(cat "$T/failure.class")" = account_access_absent ]
        [[ "$output" == *"claude reported an authentication failure"* ]]
    done
}
