#!/usr/bin/env bats
# mk-wyvz6: a thread can carry the exact bb account-pool route but no pool
# bearer. Dispatch must fall back to the provider's own non-pooled login with a
# stderr notice, not send bearer-less requests to the route. The fallback is
# narrow: a PRESENT token that the availability probe rejects (401) stays a
# terminal_configuration error. Dummy values only; the fakes record "set" or
# "unset", never a value.

setup() {
    load test_helper
    ROOT="$BATS_TEST_DIRNAME/../.."
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    DUMMY=sk-test-dummy-0123456789abcdef
    mkdir -p "$T/repo" "$T/bin"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base

    # Availability server: counts every request and always answers 401, which
    # is what a present-but-rejected bearer (or a missing one) would get.
    cat > "$T/server.py" <<'PY'
import http.server, sys, pathlib
hits = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        open(hits, "a").write("hit\n")
        eligible = pathlib.Path(hits + ".eligible").exists()
        self.send_response(200 if eligible else 401)
        self.end_headers()
        if eligible:
            self.wfile.write(b'{"claude":true,"codex":true}')
    def log_message(self, *a):
        pass
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[2], "w").write(str(s.server_port))
s.serve_forever()
PY
    : > "$T/hits"
    python3 "$T/server.py" "$T/hits" "$T/port" &
    SERVER_PID=$!
    for _ in $(seq 1 50); do [ -s "$T/port" ] && break; sleep 0.1; done
    PORT="$(cat "$T/port")"
    ORIGIN="http://127.0.0.1:$PORT"
    ROUTE="$ORIGIN/api/v1/plugins/account-pool/http"

    cat > "$T/bin/bb" <<'SH'
#!/bin/sh
if [ "$1 $2" = "pool exec" ] && [ "${FAKE_POOL_EXEC:-}" = 1 ]; then
  shift 2
  [ "$1" != --help ] || exit 0
  echo pooled > "$FAKE_POOL_LOG"
  [ "$1" = -- ] && [ "$2" = claude ] || exit 2
  shift
  input=
  prev=
  for arg in "$@"; do
    [ "$prev" != --prompt-file ] || input=$arg
    prev=$arg
  done
  [ -n "$input" ] || exit 2
  [ "$(dirname "$input")" = "$PWD" ] || exit 2
  for arg in "$@"; do
    case "$arg" in --add-dir|--allowedTools|--include-partial-messages|--session-id|hello) exit 2 ;; esac
  done
  case " $* " in *' --tools=Read,Glob,Grep '*) ;; *) exit 2 ;; esac
  case " $* " in *' --restricted '*) ;; *) exit 2 ;; esac
  if [ -n "${FAKE_POOL_ERROR:-}" ]; then
    echo "$FAKE_POOL_ERROR" >&2
    exit 1
  fi
  "$@" < "$input"
  rc=$?
  echo 'bb-pool-exec: transport=pooled provider=claude' >&2
  exit "$rc"
elif [ "$1 $2 $3" = "pool exec --help" ]; then
  exit 0
elif [ "$1 $2" = "status --json" ]; then
  echo '{"thread":{"id":"thr_fixture","environment":{"hostId":"host_pda34naxgq"}}}'
else
  exit 1
fi
SH
    cat > "$T/bin/claude" <<'SH'
#!/usr/bin/env bash
cat > /dev/null
{ echo "ran"; for v in ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY; do
    if [ -n "${!v+x}" ]; then echo "$v=set"; else echo "$v=unset"; fi
  done; } > "$FAKE_LOG"
if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then echo "base_is_pool_route=$([ "$ANTHROPIC_BASE_URL" = "$POOL_ROUTE" ] && echo yes || echo no)" >> "$FAKE_LOG"; fi
jq -cn '{type:"result",subtype:"success",is_error:false,result:"VERDICT: PASS"}'
SH
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
case "$1" in
  sandbox) exit 0 ;;
  exec)
    { echo "ran"; echo "codex_base=${CODEX_OPENAI_BASE_URL+set}"; echo "codex_token=${CODEX_POOL_AUTH_TOKEN+set}"
      case "$*" in *bb-account-pool*) echo "pool_config=yes" ;; *) echo "pool_config=no" ;; esac
    } > "$FAKE_LOG"
    echo '{"type":"turn.completed"}'; exit 0 ;;
  *) echo 'codex-cli 9.9.9' ;;
esac
SH
    chmod +x "$T"/bin/*
    export PATH="$T/bin:$PATH"
    export FAKE_LOG="$T/seen.log" FAKE_POOL_LOG="$T/pool.log" POOL_ROUTE="$ROUTE"
    unset FAKE_POOL_EXEC FAKE_POOL_ERROR
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=1
    export BB_CLI="$T/bin/bb" BB_THREAD_ID=thr_fixture BB_SERVER_URL="$ORIGIN"
    export CLAVAIN_DISPATCH_FAILURE_FILE="$T/failure"
    unset CLAVAIN_BEAD_ID ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_API_KEY \
          CODEX_POOL_AUTH_TOKEN CODEX_OPENAI_BASE_URL
}

teardown() {
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    rm -rf "$T"
}

NOTICE_CLAUDE='dispatch: the bb account-pool route is set for claude but no pool token is available; ANTHROPIC_API_KEY is not set, so the claude child will use the non-pooled subscription login'
NOTICE_CLAUDE_KEY='dispatch: the bb account-pool route is set for claude but no pool token is available; ANTHROPIC_API_KEY is set, so the claude child will use that API key (metered) instead of the subscription login'
NOTICE_CODEX='dispatch: the bb account-pool route is set for codex but no pool token is available; using the non-pooled codex login'

# bats' run captures the command's stderr itself, so redirect inside the child.
run_claude() { if [ "${FAKE_POOL_EXEC:-}" != 1 ] && [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ]; then export BB_CLI="$T/missing-bb"; fi; ERRF="$T/err" run bash -c 'exec bash "$@" 2> "$ERRF"' _ "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" 'hello'; }
run_codex() { ERRF="$T/err" run bash -c 'exec bash "$@" 2> "$ERRF"' _ "$DISPATCH" --to codex -C "$T/repo" -o "$T/out.md" 'hello'; }

@test "claude: pool route set, token unset -> non-pooled login with a stderr notice" {
    export ANTHROPIC_BASE_URL="$ROUTE"
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ran' "$T/seen.log"
    grep -qx 'ANTHROPIC_BASE_URL=unset' "$T/seen.log"
    grep -qx 'ANTHROPIC_AUTH_TOKEN=unset' "$T/seen.log"
    grep -qxF "$NOTICE_CLAUDE" "$T/err"
    # No availability probe was made, so nothing was sent to the route.
    [ ! -s "$T/hits" ]
}

@test "claude: pool route set, token empty -> same fallback" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN=
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=unset' "$T/seen.log"
    grep -qxF "$NOTICE_CLAUDE" "$T/err"
    [ ! -s "$T/hits" ]
}

@test "claude: pool route set, token unset, kill switch on -> same fallback" {
    export ANTHROPIC_BASE_URL="$ROUTE" CLAVAIN_BB_DIRECT_POOL=0
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=unset' "$T/seen.log"
    grep -qxF "$NOTICE_CLAUDE" "$T/err"
}

@test "claude: token PRESENT and rejected with 401 stays terminal, no fallback" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN="$DUMMY"
    run_claude
    [ "$status" -ne 0 ]
    [ ! -e "$T/seen.log" ]
    [ "$(cat "$T/failure")" = terminal_configuration ]
    [ -s "$T/hits" ]
    ! grep -qF 'no pool token is available' "$T/err"
}

@test "claude: token unset and no pool route -> unchanged, no notice" {
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=unset' "$T/seen.log"
    ! grep -qF 'no pool token is available' "$T/err"
    [ ! -s "$T/hits" ]
}

@test "claude: token unset and a non-pool endpoint -> endpoint kept, no notice" {
    export ANTHROPIC_BASE_URL=https://dummy.invalid
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=set' "$T/seen.log"
    grep -qx 'base_is_pool_route=no' "$T/seen.log"
    ! grep -qF 'no pool token is available' "$T/err"
}

@test "claude: notice names no environment value" {
    export ANTHROPIC_BASE_URL="$ROUTE" CLAUDE_X_NOTE="$DUMMY" BB_ACCOUNT_POOL_PARENT_TOKEN="$DUMMY"
    run_claude
    [ "$status" -eq 0 ]
    grep -F 'no pool token is available' "$T/err" > "$T/notice"
    [ "$(cat "$T/notice")" = "$NOTICE_CLAUDE" ]
    ! grep -qF "$PORT" "$T/notice"
    ! grep -qF thr_fixture "$T/notice"
    ! grep -qF dummy- "$T/notice"
}

@test "codex: pool route set, token unset -> non-pooled login with a stderr notice" {
    export CODEX_OPENAI_BASE_URL="$ROUTE/v1"
    run_codex
    [ "$status" -eq 0 ]
    grep -qx 'ran' "$T/seen.log"
    grep -qx 'codex_base=' "$T/seen.log"
    grep -qx 'codex_token=' "$T/seen.log"
    grep -qx 'pool_config=no' "$T/seen.log"
    grep -qxF "$NOTICE_CODEX" "$T/err"
    [ ! -s "$T/hits" ]
}

@test "codex: token PRESENT and rejected with 401 stays terminal, no fallback" {
    export CODEX_OPENAI_BASE_URL="$ROUTE/v1" CODEX_POOL_AUTH_TOKEN="$DUMMY"
    run_codex
    [ "$status" -ne 0 ]
    [ ! -e "$T/seen.log" ]
    [ "$(cat "$T/failure")" = terminal_configuration ]
    [ -s "$T/hits" ]
    ! grep -qF 'no pool token is available' "$T/err"
}

@test "codex: token unset and no pool route -> unchanged, no notice" {
    run_codex
    [ "$status" -eq 0 ]
    grep -qx 'pool_config=no' "$T/seen.log"
    ! grep -qF 'no pool token is available' "$T/err"
}

@test "codex: notice names no environment value" {
    export CODEX_OPENAI_BASE_URL="$ROUTE/v1"
    run_codex
    [ "$status" -eq 0 ]
    grep -F 'no pool token is available' "$T/err" > "$T/notice"
    [ "$(cat "$T/notice")" = "$NOTICE_CODEX" ]
    ! grep -qF "$PORT" "$T/notice"
    ! grep -qF thr_fixture "$T/notice"
}

@test "claude: pool route set, token unset, API key set -> notice says the metered key is used, value never printed" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_API_KEY="$DUMMY"
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=unset' "$T/seen.log"
    # The child really does keep the key, which is why the notice must say so.
    grep -qx 'ANTHROPIC_API_KEY=set' "$T/seen.log"
    grep -qxF "$NOTICE_CLAUDE_KEY" "$T/err"
    ! grep -qF "$DUMMY" "$T/err"
    ! grep -qF "$DUMMY" "$T/out.md"
    [[ "$output" != *"$DUMMY"* ]]
    ! grep -qF 'will use the non-pooled subscription login' "$T/err"
}

@test "claude: pool route set, token unset, API key not set -> notice says subscription login" {
    export ANTHROPIC_BASE_URL="$ROUTE"
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_API_KEY=unset' "$T/seen.log"
    grep -qxF "$NOTICE_CLAUDE" "$T/err"
    grep -qF 'ANTHROPIC_API_KEY is not set' "$T/err"
    ! grep -qF 'metered' "$T/err"
}

@test "claude: whitespace-only token is present, so a 401 stays terminal, no fallback" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN=" "
    run_claude
    [ "$status" -ne 0 ]
    [ ! -e "$T/seen.log" ]
    [ "$(cat "$T/failure")" = terminal_configuration ]
    ! grep -qF 'no pool token is available' "$T/err"
}

# Without BB_SERVER_URL the exact pool route cannot be recognised, so the
# narrow match declines: existing behaviour is unchanged (the variable is left
# alone, nothing is probed, no notice). It is not a fallback case.
@test "claude: pool route set but BB_SERVER_URL unset -> not matched, unchanged, no notice" {
    export ANTHROPIC_BASE_URL="$ROUTE"
    unset BB_SERVER_URL
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=set' "$T/seen.log"
    ! grep -qF 'no pool token is available' "$T/err"
    [ ! -s "$T/hits" ]
}

@test "claude: scrubbed token uses pool exec and excludes its trailer from response" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN= FAKE_POOL_EXEC=1
    run_claude
    [ "$status" -eq 0 ]
    [ "$(cat "$T/pool.log")" = pooled ]
    [ "$(cat "$T/out.md")" = 'VERDICT: PASS' ]
    ! grep -q 'bb-pool-exec:' "$T/out.md"
    ! grep -qF "$DUMMY" "$T/err" "$T/out.md"
    ! grep -qF 'no pool token is available' "$T/err"
}

@test "claude: pool exec failure is terminal configuration without local fallback" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN= FAKE_POOL_EXEC=1
    export FAKE_POOL_ERROR='restricted profile unsupported'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure")" = terminal_configuration ]
    [ ! -e "$T/seen.log" ]
    ! grep -qF "$DUMMY" "$T/err" "$T/out.md"
}

@test "claude: pool exec transient failure preserves failure classification" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN= FAKE_POOL_EXEC=1
    export FAKE_POOL_ERROR='HTTP 429 Too Many Requests'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure")" = rate_limited ]
    [ ! -e "$T/seen.log" ]
}

@test "claude: a present token keeps direct pooled execution even with pool exec available" {
    export ANTHROPIC_BASE_URL="$ROUTE" ANTHROPIC_AUTH_TOKEN="$DUMMY" FAKE_POOL_EXEC=1
    touch "$T/hits.eligible"
    run_claude
    [ "$status" -eq 0 ]
    [ ! -e "$T/pool.log" ]
    grep -qx 'base_is_pool_route=yes' "$T/seen.log"
    ! grep -qF "$DUMMY" "$T/err" "$T/out.md"
}

@test "claude: pool exec receives the prompt through its stdin file" {
    export ANTHROPIC_BASE_URL="$ROUTE" FAKE_POOL_EXEC=1
    # Record only whether the prompt arrived, never inherited credentials.
    python3 - "$T/bin/claude" <<'PYTEST'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text().replace('cat > /dev/null', 'IFS= read -r prompt || :; [[ "$prompt" == hello* ]] || exit 2'))
PYTEST
    run_claude
    [ "$status" -eq 0 ]
    [ -e "$T/pool.log" ]
}

@test "claude: old host refusal stays terminal and never launches a local account" {
    export ANTHROPIC_BASE_URL="$ROUTE" FAKE_POOL_EXEC=1
    export FAKE_POOL_ERROR='unknown option --restricted'
    run_claude
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure")" = terminal_configuration ]
    [ ! -e "$T/seen.log" ]
    grep -q 'updated host support is required' "$T/err"
}
