#!/usr/bin/env bats
# mk-bi91j: a failing `claude -p` surfaces a bounded, redacted excerpt of its
# own stderr, and an authentication failure is classified as an operational
# access failure (account_access_absent) instead of terminal_error. Only dummy
# token values are used here.

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

@test "auth failure: operational class, auth note and redacted excerpt shown" {
    export FAKE_ERR='Failed to authenticate. API Error: 401 authentication_error'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = account_access_absent ]
    [[ "$output" == *"claude reported an authentication failure"* ]]
    [[ "$output" == *"claude stderr (last lines, redacted):"* ]]
    [[ "$output" == *"authentication_error"* ]]
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
    [[ "$output" == *"claude stderr (last lines, redacted):"* ]]
}

@test "policy denial in claude stderr keeps terminal_policy" {
    export FAKE_ERR='request blocked: 403 Forbidden'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_policy ]
}

@test "a token value in claude stderr is absent from all output and artifacts" {
    export ANTHROPIC_AUTH_TOKEN="$DUMMY"
    export FAKE_ERR="Failed to authenticate. bearer ${DUMMY} rejected"
    run_claude
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    ! grep -rqF "$DUMMY" "$T/out.md"* "$T/state" "$T/failure.class" 2>/dev/null
}

@test "the excerpt is bounded to 2 KB and 20 lines" {
    export FAKE_ERR="$(for i in $(seq 1 60); do printf 'line%03d filler text\n' "$i"; done)"
    run_claude
    [ "$status" -ne 0 ]
    excerpt="$(printf '%s\n' "$output" | sed -n '/claude stderr (last lines, redacted):/,$p' | grep -c '^  | ')"
    [ "$excerpt" -le 20 ]
    [[ "$output" != *"line001"* ]]
}

# Redaction runs over whole lines before any bound is applied. Dummy values only.
@test "redaction before bound: 80 hex inside a 4 KB line leaks no 40-char run" {
    # 2100 spaces, 80 hex, 2007 spaces: the 2 KB byte cut lands mid-hex.
    HEX=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    export FAKE_ERR="$(printf '%2100s' '')${HEX}$(printf '%2007s' '')"
    run_claude
    [ "$status" -ne 0 ]
    [[ "$output" != *"${HEX:40:40}"* ]]
    [[ "$output" != *"${HEX:0:40}"* ]]
}

@test "redaction before bound: sk- value at the byte boundary is redacted whole" {
    # The byte cut removes the sk- prefix; redaction must have run first.
    VAL=sk-test-dummy-abcdefghijklmnopqrstuvwxyz0123456789
    export FAKE_ERR="${VAL}$(printf '%1998s' '')"
    run_claude
    [ "$status" -ne 0 ]
    [[ "$output" != *"abcdefghijklmnopqrstuvwxyz0123456789"* ]]
    [[ "$output" != *"dummy-abc"* ]]
    [[ "$output" != *"<id>"* ]]
}

@test "redaction before bound: hex value at the 20-line boundary leaks no fragment" {
    HEX=fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba98
    export FAKE_ERR="$(printf 'head %s\n' "$HEX"; for i in $(seq 1 19); do printf 'filler %d\n' "$i"; done)"
    run_claude
    [ "$status" -ne 0 ]
    [[ "$output" != *"${HEX:0:40}"* ]]
    [[ "$output" != *"${HEX:30:40}"* ]]
}

@test "quoted login phrase mid-line stays terminal_error" {
    export FAKE_ERR='model said: you should please run /login and Failed to authenticate with the registry'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure.class")" = terminal_error ]
    [[ "$output" != *"authentication failure"* ]]
}

# Bare hex and base64-like values are not labeled, so the shared allowlist keeps
# 40- and 64-character hex as possible SHAs. The excerpt replaces any run of 20
# or more token-class characters. Dummy values only.
@test "long token-like runs are replaced, alone on a line and inside a sentence" {
    H40=0123456789abcdef0123456789abcdef01234567
    H64=fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210
    B32=QUJDREVGR0hJSktMTU5PUFFSU1RVVldY+/==
    export FAKE_ERR="$(printf 'Failed to authenticate\n%s\n%s\n%s\nrejected value %s here\nrejected value %s here\nrejected value %s here\n' \
        "$H40" "$H64" "$B32" "$H40" "$H64" "$B32")"
    run_claude
    [ "$status" -ne 0 ]
    # Only the excerpt section is checked: the earlier raw-stderr mirror is a
    # different path (_emit_provider_stderr) that this change does not alter.
    local excerpt
    excerpt="$(printf '%s\n' "$output" | sed -n '/claude stderr (last lines, redacted):/,$p')"
    [[ "$excerpt" == *"<redacted>"* ]]
    local v i
    for v in "$H40" "$H64" "$B32"; do
        for ((i = 0; i + 20 <= ${#v}; i++)); do
            [[ "$excerpt" != *"${v:i:20}"* ]]
        done
    done
}

@test "ordinary diagnostic words survive the long-run redaction" {
    export FAKE_ERR='Failed to authenticate with <provider> for model m1 (retry 3); see docs'
    run_claude
    [ "$status" -ne 0 ]
    local excerpt
    # The shared allowlist redactor rewrites some words (<word>, <id>); the
    # long-run pass must leave its output as it was.
    excerpt="$(printf '%s\n' "$output" | sed -n '/claude stderr (last lines, redacted):/,$p')"
    [[ "$excerpt" == *"| Failed to <word> with <provider> for model <id> (retry 3); <word> <word>"* ]]
    [[ "$excerpt" != *"<redacted>"* ]]
    [[ "$output" == *"claude reported an authentication failure"* ]]
}
