#!/usr/bin/env bats
# mk-ouz83: Claude-backed dispatch keeps ANTHROPIC_AUTH_TOKEN and scans every
# artifact for it afterwards; other backends lose it; two other bearer tokens
# never reach any child. Only a dummy token value is used here.

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
    printf '{"decision":"x"}\n' > "$T/ctx.json"
    POLICY_HASH="$(sha256sum "$ROOT/config/routing.yaml" | awk '{print $1}')"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$T/bin/ic"
    # Fake backends record which of the three token variables are present
    # (names only, never values) and can leak the dummy value on demand.
    cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
cat > /dev/null
{
  echo "anthropic:${ANTHROPIC_AUTH_TOKEN+set}"
  echo "bbparent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message:${CLAUDE_CODE_MESSAGING_TOKEN+set}"
} > "$FAKE_ENV_LOG"
body="clean answer"
[[ "${LEAK:-}" != *out* ]] || body="answer with ${ANTHROPIC_AUTH_TOKEN} inside"
[[ "${LEAK:-}" != *err* ]] || echo "auth detail ${ANTHROPIC_AUTH_TOKEN}" >&2
[[ "${LEAK:-}" != *event* ]] || jq -cn --arg t "${ANTHROPIC_AUTH_TOKEN}" '{type:"system",note:$t}'
jq -cn --arg body "$body" '{type:"result",subtype:"success",is_error:false,result:$body}'
FAKE
    cat > "$T/bin/kimi" <<'FAKE'
#!/usr/bin/env bash
{
  echo "anthropic:${ANTHROPIC_AUTH_TOKEN+set}"
  echo "bbparent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message:${CLAUDE_CODE_MESSAGING_TOKEN+set}"
} > "$FAKE_ENV_LOG"
echo "kimi answer"
FAKE
    cat > "$T/bin/codex" <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == --version ]]; then echo "codex-cli 9.9.9"; exit 0; fi
{
  echo "anthropic:${ANTHROPIC_AUTH_TOKEN+set}"
  echo "bbparent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message:${CLAUDE_CODE_MESSAGING_TOKEN+set}"
} > "$FAKE_ENV_LOG"
echo '{"type":"turn.completed"}'
FAKE
    # Leak hook: records its arguments and never sees the token.
    cat > "$T/bin/hook" <<'FAKE'
#!/usr/bin/env bash
{ echo "argc=$#"; echo "arg1=$1"; echo "token=${ANTHROPIC_AUTH_TOKEN+set}"; } > "$HOOK_LOG"
FAKE
    chmod +x "$T"/bin/*
    export PATH="$T/bin:$PATH"
    export FAKE_ENV_LOG="$T/env.log" HOOK_LOG="$T/hook.log"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/state/receipts.jsonl"
    export ANTHROPIC_AUTH_TOKEN="$DUMMY"
    export BB_ACCOUNT_POOL_PARENT_TOKEN=dummy-parent-value CLAUDE_CODE_MESSAGING_TOKEN=dummy-message-value
    unset CLAVAIN_BEAD_ID BB_THREAD_ID BB_SERVER_URL ANTHROPIC_BASE_URL CLAUDE_SESSION_ID CODEX_THREAD_ID \
        DISPATCH_SESSION_ID CLAVAIN_TOKEN_LEAK_HOOK CODEX_POOL_AUTH_TOKEN
}

teardown() { rm -rf "$T"; }

governed() {
    bash "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity prod-model \
        --to claude --model m1 --reasoning-effort high -C "$T/repo" \
        --prompt-file "$T/prompt.md" -o "$T/out.md" "$@"
}

# ---- environment handling ---------------------------------------------------

@test "claude backend keeps the pooled token; the other two bearer tokens are unset" {
    run governed
    [ "$status" -eq 0 ]
    grep -qx 'anthropic:set' "$T/env.log"
    grep -qx 'bbparent:' "$T/env.log"
    grep -qx 'message:' "$T/env.log"
}

@test "kimi backend loses all three tokens" {
    printf '[models."k"]\nmodel = "k"\n' > "$T/kimi.toml"
    KIMI_CONFIG="$T/kimi.toml" run bash "$DISPATCH" --to kimi -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    grep -qx 'anthropic:' "$T/env.log"
    grep -qx 'bbparent:' "$T/env.log"
    grep -qx 'message:' "$T/env.log"
}

@test "codex backend loses all three tokens" {
    run bash "$DISPATCH" --to codex -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    grep -qx 'anthropic:' "$T/env.log"
    grep -qx 'bbparent:' "$T/env.log"
    grep -qx 'message:' "$T/env.log"
}

# ---- leak scan --------------------------------------------------------------

@test "no leak: exit 0, no report, output unchanged, receipt completed" {
    run governed
    [ "$status" -eq 0 ]
    [ "$(cat "$T/out.md")" = "clean answer" ]
    [ ! -e "$T/out.md.token-leak.json" ]
    [ "$(jq -r .outcome "$T/state/receipts.jsonl")" = completed ]
    [[ "$output" != *"token leak"* ]]
}

@test "token in the output file fails the run and is redacted in place" {
    LEAK=out run governed
    [ "$status" -ne 0 ]
    ! grep -qF "$DUMMY" "$T/out.md"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md"
    [ "$(jq -r .outcome "$T/state/receipts.jsonl")" = failed ]
    grep -q '^STATUS: error' "$T/out.md.verdict"
    ! grep -qiE 'STATUS: *(pass|clean)' "$T/out.md.verdict"
}

@test "token in a provider-events sidecar is found and redacted" {
    LEAK=event run governed
    [ "$status" -ne 0 ]
    # the output itself was clean; only the events file carried the value
    [ "$(cat "$T/out.md")" = "clean answer" ]
    ev="$(ls "$T"/out.md.provider-events.*.jsonl)"
    ! grep -qF "$DUMMY" "$ev"
    grep -qF '[REDACTED:anthropic-token]' "$ev"
    jq -e --arg f "$ev" '.files | map(.path) | index($f) != null' "$T/out.md.token-leak.json" >/dev/null
}

@test "token in captured stderr is redacted before it is mirrored and fails the run" {
    LEAK=err run governed
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    [[ "$output" == *"leak report: $T/out.md.token-leak.json"* ]]
    # the mirror has its own sanitizer, so prove the dispatch scan itself caught it
    jq -e '.files | map(select(.path | endswith(".stderr"))) | length == 1' "$T/out.md.token-leak.json" >/dev/null
}

@test "a hit writes a report without the value and names it in one error line" {
    CLAVAIN_BEAD_ID=mk-test LEAK=out,event run governed
    [ "$status" -ne 0 ]
    rep="$T/out.md.token-leak.json"
    [ -f "$rep" ]
    ! grep -qF "$DUMMY" "$rep"
    [ "$(jq -r .kind "$rep")" = anthropic-token-leak ]
    [ "$(jq -r .bead "$rep")" = mk-test ]
    [ "$(jq -r .role "$rep")" = validation ]
    jq -e '.run_id | length > 0' "$rep" >/dev/null
    jq -e '.timestamp | test("^[0-9]{4}-.*Z$")' "$rep" >/dev/null
    jq -e '.files | length >= 2' "$rep" >/dev/null
    jq -e '.total_count >= 2' "$rep" >/dev/null
    [ "$(printf '%s\n' "$output" | grep -c 'leak report:')" -eq 1 ]
}

@test "the leak hook runs with the report path as its only argument and no token" {
    CLAVAIN_TOKEN_LEAK_HOOK="$T/bin/hook" LEAK=out run governed
    [ "$status" -ne 0 ]
    grep -qx 'argc=1' "$T/hook.log"
    grep -qx "arg1=$T/out.md.token-leak.json" "$T/hook.log"
    grep -qx 'token=' "$T/hook.log"
}

@test "a hook that is not executable is ignored" {
    printf '#!/usr/bin/env bash\ntouch "$HOOK_LOG"\n' > "$T/nohook"
    CLAVAIN_TOKEN_LEAK_HOOK="$T/nohook" LEAK=out run governed
    [ "$status" -ne 0 ]
    [ ! -e "$T/hook.log" ]
}

@test "the token value never reaches a command line" {
    LEAK=out run governed
    [ "$status" -ne 0 ]
    # the helper takes the value from its environment, not from argv
    ! grep -n 'ANTHROPIC_AUTH_TOKEN' "$ROOT/scripts/token-leak-scan.py" | grep -q 'argv'
    ! grep -nE 'token-leak-scan\.py.*\$\{?ANTHROPIC_AUTH_TOKEN' "$DISPATCH"
}

@test "unset token: scan skipped with a logged note, run unaffected" {
    unset ANTHROPIC_AUTH_TOKEN
    run governed
    [ "$status" -eq 0 ]
    [[ "$output" == *"token leak scan skipped"* ]]
    [ ! -e "$T/out.md.token-leak.json" ]
}

@test "token shorter than 16 characters: scan skipped, value not logged" {
    export ANTHROPIC_AUTH_TOKEN=short-tok-123
    LEAK=out run governed
    [ "$status" -eq 0 ]
    note="$(printf '%s\n' "$output" | grep 'token leak scan skipped')"
    [ -n "$note" ]
    [[ "$note" != *short-tok-123* ]]
    # skipped means untouched: the fake's body still carries the short value
    grep -qF short-tok-123 "$T/out.md"
    [ ! -e "$T/out.md.token-leak.json" ]
}

@test "non-claude backends are not scanned" {
    printf '[models."k"]\nmodel = "k"\n' > "$T/kimi.toml"
    KIMI_CONFIG="$T/kimi.toml" run bash "$DISPATCH" --to kimi -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    [[ "$output" != *"token leak scan"* ]]
}

# ---- helper -----------------------------------------------------------------

@test "helper redacts the JSON-escaped form too and keeps file mode" {
    export ANTHROPIC_AUTH_TOKEN='sk-test-dummy-"quoted"-0123456789'
    printf '{"k":"sk-test-dummy-\\"quoted\\"-0123456789"}\n' > "$T/ev.jsonl"
    chmod 640 "$T/ev.jsonl"
    run python3 "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" -- "$T/ev.jsonl" "$T/missing"
    [ "$status" -eq 3 ]
    grep -qF '[REDACTED:anthropic-token]' "$T/ev.jsonl"
    ! grep -qF 'quoted' "$T/ev.jsonl"
    [ "$(stat -c %a "$T/ev.jsonl")" = 640 ]
}
