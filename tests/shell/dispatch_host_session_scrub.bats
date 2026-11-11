#!/usr/bin/env bats
# mk-7bzyr: variables a host injects into the parent's session (notably
# CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST, which makes a child claude ignore the
# subscription login) must not reach the claude child. The user's own config
# and the account-pool transport must. Dummy values only. The stub claude
# records "set" or "unset" per name, never a value.

SCRUBBED="CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST CLAUDE_CODE_SESSION_ID CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH CLAUDE_CODE_SESSION_ATTENDED CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN CLAUDE_CODE_MESSAGING_FUTURE_NAME CLAUDE_AGENT_SDK_VERSION CLAUDECODE CLAUDE_PID CLAUDE_EFFORT"
KEPT="HOME XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME CLAUDE_CONFIG_DIR PATH CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ENABLE_TOOL_SEARCH CLAUDE_CODE_AUTO_COMPACT_WINDOW"

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    unset BB_SERVER_URL CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY
    for n in $SCRUBBED; do export "$n=dummy-not-a-real-value"; done
    export XDG_CONFIG_HOME="$T/xdg-config" XDG_DATA_HOME="$T/xdg-data"
    export XDG_STATE_HOME="$T/xdg-state" XDG_CACHE_HOME="$T/xdg-cache"
    export CLAUDE_CONFIG_DIR="$T/claude-config"
    export CLAUDE_CODE_USE_BEDROCK=0
    export CLAUDE_CODE_OAUTH_TOKEN=dummy-not-a-real-value ANTHROPIC_AUTH_TOKEN=dummy-not-a-real-value
    export ANTHROPIC_BASE_URL=https://dummy.invalid ENABLE_TOOL_SEARCH=true
    export CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000
    export FAKE_LOG="$T/seen.log"
    # Records each watched name as set/unset, never its value.
    cat > "$T/record.sh" <<SH
for v in $SCRUBBED $KEPT; do
  if [ -n "\${!v+x}" ]; then echo "\$v=set"; else echo "\$v=unset"; fi
done > "\$FAKE_LOG"
SH
}

teardown() { rm -rf "$T"; }

seen() { grep -qx "$1" "$FAKE_LOG"; }

fake_claude() {
    cat > "$T/bin/claude" <<STUB
#!/usr/bin/env bash
cat > /dev/null
bash "$T/record.sh"
jq -cn '{type:"result",subtype:"success",is_error:false,result:"VERDICT: PASS"}'
STUB
    chmod +x "$T/bin/claude"
}

@test "claude child: host-injected session variables are removed" {
    fake_claude
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    for n in $SCRUBBED; do seen "$n=unset"; done
}

@test "claude child: the user's own config, the engine's auth and the pool transport remain" {
    fake_claude
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    for n in $KEPT; do seen "$n=set"; done
}

@test "claude child: with usage accounting required the wrapped claude is scrubbed too" {
    fake_claude
    # The accounting wrapper resolves a model identity through ic; CI has no ic,
    # so answer that one query with a dummy and nothing else.
    cat > "$T/bin/ic" <<'STUB'
#!/bin/sh
case "$*" in
  *"route identity"*) echo '{"model_identity":"claude-sonnet-5-5"}' ;;
  *) exit 3 ;;
esac
STUB
    chmod +x "$T/bin/ic"
    CLAVAIN_REQUIRE_USAGE=1 CLAVAIN_REVIEW_EVENTS="$T/events.jsonl" PATH="$T/bin:$PATH" \
        run bash "$DISPATCH" --to claude --model claude-sonnet-5-5 -C "$T/repo" -o "$T/out.md" "prompt"
    # The stub reports no usage, so the run may fail accounting; what matters
    # is what the launched claude saw.
    [ -f "$FAKE_LOG" ]
    for n in $SCRUBBED; do seen "$n=unset"; done
    seen HOME=set
}

@test "codex and kimi children are not touched by the claude scrub list" {
    cat > "$T/bin/kimi" <<STUB
#!/usr/bin/env bash
bash "$T/record.sh"
echo ok
STUB
    chmod +x "$T/bin/kimi"
    export KIMI_CONFIG="$T/kimi.toml"
    printf 'default_model = "kimi-code/k3"\n[models."kimi-code/k3"]\nprovider = "managed:kimi-code"\nmodel = "k3"\n' > "$KIMI_CONFIG"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ -f "$FAKE_LOG" ]
    seen CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=set
    seen CLAUDE_EFFORT=set
}

@test "claude child: 'Not logged in' from the child is account_access_absent, not terminal_error" {
    cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
cat > /dev/null
jq -cn '{type:"assistant",error:"authentication_failed",message:{content:[{type:"text",text:"Not logged in · Please run /login"}]}}'
jq -cn '{type:"result",subtype:"success",is_error:true,result:"Not logged in · Please run /login"}'
exit 1
STUB
    chmod +x "$T/bin/claude"
    export CLAVAIN_DISPATCH_FAILURE_FILE="$T/failure-class"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    [ "$(head -1 "$T/failure-class")" = account_access_absent ]
}
