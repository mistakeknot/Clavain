#!/usr/bin/env bats
# mk-47vtm.2: the codex sandbox preflight and the helper children that run
# before the final token unset must not see any bearer token. Dummy values only;
# the fakes record "set" or "unset" markers, never a value.

setup() {
    load test_helper
    ROOT="$BATS_TEST_DIRNAME/../.."
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    DUMMY=sk-test-dummy-0123456789abcdef
    mkdir -p "$T/repo" "$T/bin"
    git -C "$T/repo" init -q
    cat > "$T/bin/ic" <<'SH'
#!/bin/sh
case "$*" in
  *"route list"*) echo '[]' ;;
  *"route identity"*) echo '{"model_identity":"gpt-6.1-sol"}' ;;
  *"route record"*) exit 0 ;;
  *) exit 3 ;;
esac
SH
    cat > "$T/bin/codex" <<'SH'
#!/bin/sh
rec() {
  echo "$1 anthropic:${ANTHROPIC_AUTH_TOKEN+set} pool:${CODEX_POOL_AUTH_TOKEN+set} parent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set} message:${CLAUDE_CODE_MESSAGING_TOKEN+set}" >> "$FAKE_ENV_LOG"
}
case "$1" in
  sandbox) rec sandbox; exit 0 ;;
  exec) rec exec; echo '{"type":"turn.completed"}'; exit 0 ;;
  *) rec version; echo 'codex-cli 9.9.9' ;;
esac
SH
    # sed and tail wrappers record their environment, then run the real tool.
    for tool in sed tail; do
        real="$(command -v "$tool")"
        cat > "$T/bin/$tool" <<SH
#!/bin/sh
echo "$tool anthropic:\${ANTHROPIC_AUTH_TOKEN+set} pool:\${CODEX_POOL_AUTH_TOKEN+set} parent:\${BB_ACCOUNT_POOL_PARENT_TOKEN+set} message:\${CLAUDE_CODE_MESSAGING_TOKEN+set}" >> "\$FAKE_HELPER_LOG"
exec "$real" "\$@"
SH
    done
    chmod +x "$T"/bin/*
    export PATH="$T/bin:$PATH"
    export FAKE_ENV_LOG="$T/env.log" FAKE_HELPER_LOG="$T/helper.log"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export ANTHROPIC_AUTH_TOKEN="$DUMMY" CODEX_POOL_AUTH_TOKEN="$DUMMY"
    export BB_ACCOUNT_POOL_PARENT_TOKEN=dummy-parent-value CLAUDE_CODE_MESSAGING_TOKEN=dummy-message-value
    unset CLAVAIN_BEAD_ID BB_THREAD_ID BB_SERVER_URL ANTHROPIC_BASE_URL CODEX_OPENAI_BASE_URL
}

teardown() { rm -rf "$T"; }

@test "the codex sandbox preflight child sees none of the bearer tokens" {
    [[ "$(uname -s)" == Linux ]] || skip 'Linux sandbox only'
    route="$(jq -n --arg h "$(sha256sum "$ROOT/config/routing.yaml" | cut -d' ' -f1)" '{policy_hash:$h,profile_ref:"primary",profile:{backend:"codex",model:"gpt-6.1-sol",model_identity:"gpt-6.1-sol"}}')"
    run bash "$DISPATCH" --role cross-lab-review --role-resolved --to codex \
        --resolved-route-json "$route" -C "$T/repo" -o "$T/out" 'Review it'
    [ "$status" -eq 0 ]
    grep -qx 'sandbox anthropic: pool: parent: message:' "$T/env.log"
}

@test "the codex version probe helpers (sed, tail) see none of the bearer tokens" {
    sed -n '/^_codex_version_at_least() {/,/^}/p' "$DISPATCH" > "$T/fn.sh"
    [ -s "$T/fn.sh" ]
    : > "$T/helper.log"
    export BB_ACCOUNT_POOL_PARENT_TOKEN=dummy-parent-value CLAUDE_CODE_MESSAGING_TOKEN=dummy-message-value
    run bash -c 'source "$1"; _codex_version_at_least 1.0.0' _ "$T/fn.sh"
    [ "$status" -eq 0 ]
    grep -qx 'version anthropic: pool: parent: message:' "$T/env.log"
    grep -q '^sed ' "$T/helper.log"
    grep -q '^tail ' "$T/helper.log"
    ! grep -qE ':set' "$T/helper.log"
}

@test "the codex preflight and exec children lose the Anthropic token and keep the pooled alias" {
    run bash "$DISPATCH" --to codex -C "$T/repo" -o "$T/out.md" 'hello'
    [ "$status" -eq 0 ]
    grep -qx 'exec anthropic: pool:set parent: message:' "$T/env.log"
}
