#!/usr/bin/env bats
# mk-1w54d: secret-named variables inherited by the dispatch shell must not
# reach what a seat's own shell commands see. Dummy values only. Stub engines
# record "set" or "unset" per name, never a value.

NAMES="ANTHROPIC_AUTH_TOKEN GH_TOKEN GITHUB_TOKEN OPENAI_API_KEY CODEX_POOL_AUTH_TOKEN AWS_SECRET_ACCESS_KEY AWS_REGION CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID MY_SERVICE_SECRET db_password SAFE_SETTING"

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    REAL_CODEX="$(command -v codex || true)"
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export KIMI_CONFIG="$T/kimi.toml"
    printf 'default_model = "kimi-code/k3"\n[models."kimi-code/k3"]\nprovider = "managed:kimi-code"\nmodel = "k3"\n' > "$KIMI_CONFIG"
    unset CLAVAIN_SEAT_ENV_SCRUB CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY
    unset BB_SERVER_URL ANTHROPIC_BASE_URL CODEX_OPENAI_BASE_URL
    for n in $NAMES; do export "$n=dummy-not-a-real-value"; done
    export KIMI_API_KEY=dummy-not-a-real-value MOONSHOT_API_KEY=dummy-not-a-real-value
    export CLAUDE_CODE_OAUTH_TOKEN=dummy-not-a-real-value
    export FAKE_LOG="$T/seen.log"
    # Records each watched name as set/unset, never its value.
    cat > "$T/record.sh" <<'SH'
for v in ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN KIMI_API_KEY MOONSHOT_API_KEY GH_TOKEN GITHUB_TOKEN OPENAI_API_KEY CODEX_POOL_AUTH_TOKEN AWS_SECRET_ACCESS_KEY AWS_REGION CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID MY_SERVICE_SECRET db_password SAFE_SETTING; do
  if [ -n "${!v+x}" ]; then echo "$v=set"; else echo "$v=unset"; fi
done > "$FAKE_LOG"
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

fake_kimi() {
    cat > "$T/bin/kimi" <<STUB
#!/usr/bin/env bash
bash "$T/record.sh"
echo ok
STUB
    chmod +x "$T/bin/kimi"
}

@test "claude child: keeps its own auth, loses every other secret-named variable" {
    fake_claude
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    seen ANTHROPIC_AUTH_TOKEN=set
    seen CLAUDE_CODE_OAUTH_TOKEN=set
    for n in GH_TOKEN GITHUB_TOKEN OPENAI_API_KEY CODEX_POOL_AUTH_TOKEN AWS_SECRET_ACCESS_KEY AWS_REGION \
             CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID MY_SERVICE_SECRET db_password KIMI_API_KEY MOONSHOT_API_KEY; do
        seen "$n=unset"
    done
    seen SAFE_SETTING=set
}

@test "claude child: a cloud-provider run keeps the provider's credentials" {
    fake_claude
    CLAUDE_CODE_USE_BEDROCK=1 PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    seen AWS_SECRET_ACCESS_KEY=set
    seen GH_TOKEN=unset
    seen CLOUDFLARE_API_TOKEN=unset
}

@test "claude child: CLAVAIN_SEAT_ENV_SCRUB=0 restores the inherited environment" {
    fake_claude
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    seen GH_TOKEN=unset
    CLAVAIN_SEAT_ENV_SCRUB=0 PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    seen GH_TOKEN=set
    seen AWS_REGION=set
}

@test "claude child: the token-leak scan still knows the token that was kept" {
    cat > "$T/bin/claude" <<STUB
#!/usr/bin/env bash
cat > /dev/null
bash "$T/record.sh"
jq -cn --arg b "VERDICT: PASS leaked \$ANTHROPIC_AUTH_TOKEN" '{type:"result",subtype:"success",is_error:false,result:\$b}'
STUB
    chmod +x "$T/bin/claude"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" "prompt"
    # The kept token is still a known value: the scan reports it and fails the run.
    [ "$status" -ne 0 ]
    [[ "$output" == *"bearer token found"* ]]
    seen GH_TOKEN=unset
    ! grep -q 'dummy-not-a-real-value' "$T/out.md"
}

@test "kimi child: keeps its own key, loses every other secret-named variable" {
    fake_kimi
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    seen KIMI_API_KEY=set
    seen MOONSHOT_API_KEY=set
    for n in GH_TOKEN GITHUB_TOKEN OPENAI_API_KEY AWS_SECRET_ACCESS_KEY CLOUDFLARE_API_TOKEN MY_SERVICE_SECRET db_password CLAUDE_CODE_OAUTH_TOKEN; do
        seen "$n=unset"
    done
    seen SAFE_SETTING=set
}

# codex: the engine-native control is a -c override the seat's tool commands obey.
codex_exclude_arg() {
    cat > "$T/bin/codex" <<STUB
#!/bin/sh
case "\$1" in
  exec) for a in "\$@"; do printf '%s\n' "\$a"; done > "$T/codex.argv"; echo '{"type":"turn.completed"}'; exit 0 ;;
  *) echo 'codex-cli 9.9.9' ;;
esac
STUB
    chmod +x "$T/bin/codex"
    PATH="$T/bin:$PATH" bash "$DISPATCH" --to codex -C "$T/repo" -o "$T/out.md" "prompt" >/dev/null 2>&1 || return 2
    grep '^shell_environment_policy.exclude=' "$T/codex.argv"
}

@test "codex: exec gets a shell_environment_policy exclude list naming the secret patterns" {
    run codex_exclude_arg
    [ "$status" -eq 0 ]
    for p in '"*TOKEN*"' '"*SECRET*"' '"*API_KEY*"' '"AWS_*"' '"CLOUDFLARE_*"' '"GH_*"' '"GITHUB_*"' '"OPENAI_*"'; do
        [[ "$output" == *"$p"* ]]
    done
}

@test "codex: CLAVAIN_SEAT_ENV_SCRUB=0 adds no exclude list" {
    run codex_exclude_arg
    [ "$status" -eq 0 ]
    CLAVAIN_SEAT_ENV_SCRUB=0 run codex_exclude_arg
    [ "$status" -eq 1 ]
}

@test "codex: the real codex sandbox obeys the exclude list dispatch passes (tool command path)" {
    [[ -n "$REAL_CODEX" && "$(uname -s)" == Linux ]] || skip 'codex sandbox (Linux) not installed'
    "$REAL_CODEX" sandbox true >/dev/null 2>&1 || skip 'codex sandbox not usable here'
    arg="$(codex_exclude_arg)"
    run "$REAL_CODEX" sandbox -c "$arg" bash "$T/record.sh"
    [ "$status" -eq 0 ]
    for n in GH_TOKEN GITHUB_TOKEN OPENAI_API_KEY CODEX_POOL_AUTH_TOKEN AWS_SECRET_ACCESS_KEY AWS_REGION \
             CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID MY_SERVICE_SECRET db_password ANTHROPIC_AUTH_TOKEN; do
        seen "$n=unset"
    done
    seen SAFE_SETTING=set
}
