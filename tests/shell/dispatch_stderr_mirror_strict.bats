#!/usr/bin/env bats
# mk-47vtm.6: the provider stderr mirror replaces runs of 20 or more letters,
# digits, '+' or '=' after the shared redactor, which keeps bare 40- and
# 64-character hex as possible SHAs. Dummy values only, built at run time;
# assertions count matches and never print a value.

setup() {
    load test_helper
    ROOT="$BATS_TEST_DIRNAME/../.."
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'prompt\n' > "$T/prompt.md"
    printf '[models."k"]\nmodel = "k"\n' > "$T/kimi.toml"
    # Dummy values: 40- and 64-character hex runs, a UUID, a timestamp.
    HEX40="$(printf 'a1b2c3d4e5%.0s' 1 2 3 4)"
    HEX64="$(printf 'f0e1d2c3b4a59687%.0s' 1 2 3 4)"
    TS=2026-11-09T07:01:16Z
    UUID=12345678-1234-1234-1234-123456789abc
    export HEX40 HEX64 TS UUID
    cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
cat > /dev/null
printf 'detail %s\n' "$FAKE_ERR" >&2
jq -cn '{type:"result",subtype:"success",is_error:false,result:"clean answer"}'
FAKE
    cat > "$T/bin/kimi" <<'FAKE'
#!/usr/bin/env bash
printf 'detail %s\n' "$FAKE_ERR" >&2
echo "kimi answer"
FAKE
    chmod +x "$T"/bin/*
    export PATH="$T/bin:$PATH"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/state/receipts.jsonl"
    unset CLAVAIN_BEAD_ID BB_THREAD_ID BB_SERVER_URL ANTHROPIC_BASE_URL CLAUDE_SESSION_ID CODEX_THREAD_ID \
        DISPATCH_SESSION_ID CLAVAIN_TOKEN_LEAK_HOOK CODEX_POOL_AUTH_TOKEN ANTHROPIC_AUTH_TOKEN \
        BB_ACCOUNT_POOL_PARENT_TOKEN CLAUDE_CODE_MESSAGING_TOKEN
}

teardown() { rm -rf "$T"; }

run_engine() {
    if [[ "$1" == kimi ]]; then
        KIMI_CONFIG="$T/kimi.toml" run bash "$DISPATCH" --to kimi -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    else
        run bash "$DISPATCH" --to claude --model m1 -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    fi
    [ "$status" -eq 0 ]
}

@test "claude mirror: a bare 40-hex run is replaced" {
    FAKE_ERR="$HEX40" run_engine claude
    [ "$(printf '%s\n' "$output" | grep -c "$HEX40")" -eq 0 ]
    [ "$(printf '%s\n' "$output" | grep -c 'detail <redacted>')" -eq 1 ]
}

@test "claude mirror: a bare 64-hex run is replaced" {
    FAKE_ERR="$HEX64" run_engine claude
    [ "$(printf '%s\n' "$output" | grep -c "$HEX64")" -eq 0 ]
    [ "$(printf '%s\n' "$output" | grep -c 'detail <redacted>')" -eq 1 ]
}

@test "kimi mirror: a bare 40-hex run is replaced" {
    FAKE_ERR="$HEX40" run_engine kimi
    [ "$(printf '%s\n' "$output" | grep -c "$HEX40")" -eq 0 ]
    [ "$(printf '%s\n' "$output" | grep -c 'detail <redacted>')" -eq 1 ]
}

@test "kimi mirror: a bare 64-hex run is replaced" {
    FAKE_ERR="$HEX64" run_engine kimi
    [ "$(printf '%s\n' "$output" | grep -c "$HEX64")" -eq 0 ]
    [ "$(printf '%s\n' "$output" | grep -c 'detail <redacted>')" -eq 1 ]
}

@test "control: a UUID, a timestamp and a short error code are unchanged" {
    FAKE_ERR="$UUID $TS invalid_request_error" run_engine claude
    [ "$(printf '%s\n' "$output" | grep -c "detail $UUID $TS invalid_request_error")" -eq 1 ]
    FAKE_ERR="$UUID $TS invalid_request_error" run_engine kimi
    [ "$(printf '%s\n' "$output" | grep -c "detail $UUID $TS invalid_request_error")" -eq 1 ]
}

# Load only the helper from dispatch.sh so it can be run on its own.
load_helper() {
    eval "$(awk '/^_strict_token_runs\(\) \{/,/^\}/' "$DISPATCH")"
}

@test "helper: a failing sed fails closed to the placeholder" {
    load_helper
    printf '#!/usr/bin/env bash\nexit 1\n' > "$T/bin/sed"
    chmod +x "$T/bin/sed"
    out="$(printf 'some text\n' | _strict_token_runs)"
    [ "$(printf '%s\n' "$out" | grep -c -x '<redacted>')" -eq 1 ]
    [ "$(printf '%s\n' "$out" | grep -c 'some text')" -eq 0 ]
}

@test "helper: a newline ends a run; a 20+ run on one line is replaced" {
    load_helper
    short="$(printf 'a1b2c3d4e5%.0s' 1)"
    long="$(printf 'a1b2c3d4e5%.0s' 1 2)"
    out="$(printf '%s\n%s\n%s\n' "$short" "$short" "$long" | _strict_token_runs)"
    [ "$(printf '%s\n' "$out" | grep -c -x "$short")" -eq 2 ]
    [ "$(printf '%s\n' "$out" | grep -c "$long")" -eq 0 ]
    [ "$(printf '%s\n' "$out" | grep -c -x '<redacted>')" -eq 1 ]
}

@test "helper: a 25-letter segment inside an error code is replaced (documented)" {
    load_helper
    seg="$(printf 'abcde%.0s' 1 2 3 4 5)"
    out="$(printf 'x_%s_error\n' "$seg" | _strict_token_runs)"
    [ "$(printf '%s\n' "$out" | grep -c "$seg")" -eq 0 ]
    [ "$(printf '%s\n' "$out" | grep -c -x 'x_<redacted>_error')" -eq 1 ]
}
