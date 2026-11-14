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
import http.server, sys
hits = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        open(hits, "a").write("hit\n")
        self.send_response(401)
        self.end_headers()
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
if [ "$1 $2" = "status --json" ]; then
  echo '{"thread":{"id":"thr_fixture","environment":{"hostId":"host_pda34naxgq"}}}'
else
  exit 1
fi
SH
    cat > "$T/bin/claude" <<'SH'
#!/usr/bin/env bash
cat > /dev/null
{ echo "ran"; for v in ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN; do
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
    export FAKE_LOG="$T/seen.log" POOL_ROUTE="$ROUTE"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=1
    export BB_CLI="$T/bin/bb" BB_THREAD_ID=thr_fixture BB_SERVER_URL="$ORIGIN"
    export CLAVAIN_DISPATCH_FAILURE_FILE="$T/failure"
    unset CLAVAIN_BEAD_ID ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL \
          CODEX_POOL_AUTH_TOKEN CODEX_OPENAI_BASE_URL
}

teardown() {
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    rm -rf "$T"
}

NOTICE_CLAUDE='dispatch: the bb account-pool route is set for claude but no pool token is available; using the non-pooled claude login'
NOTICE_CODEX='dispatch: the bb account-pool route is set for codex but no pool token is available; using the non-pooled codex login'

# bats' run captures the command's stderr itself, so redirect inside the child.
run_claude() { ERRF="$T/err" run bash -c 'exec bash "$@" 2> "$ERRF"' _ "$DISPATCH" --to claude --model m -C "$T/repo" -o "$T/out.md" 'hello'; }
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
    ! grep -qF 'using the non-pooled' "$T/err"
}

@test "claude: token unset and no pool route -> unchanged, no notice" {
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=unset' "$T/seen.log"
    ! grep -qF 'using the non-pooled' "$T/err"
    [ ! -s "$T/hits" ]
}

@test "claude: token unset and a non-pool endpoint -> endpoint kept, no notice" {
    export ANTHROPIC_BASE_URL=https://dummy.invalid
    run_claude
    [ "$status" -eq 0 ]
    grep -qx 'ANTHROPIC_BASE_URL=set' "$T/seen.log"
    grep -qx 'base_is_pool_route=no' "$T/seen.log"
    ! grep -qF 'using the non-pooled' "$T/err"
}

@test "claude: notice names no environment value" {
    export ANTHROPIC_BASE_URL="$ROUTE" CLAUDE_X_NOTE="$DUMMY" BB_ACCOUNT_POOL_PARENT_TOKEN="$DUMMY"
    run_claude
    [ "$status" -eq 0 ]
    grep -F 'using the non-pooled' "$T/err" > "$T/notice"
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
    ! grep -qF 'using the non-pooled' "$T/err"
}

@test "codex: token unset and no pool route -> unchanged, no notice" {
    run_codex
    [ "$status" -eq 0 ]
    grep -qx 'pool_config=no' "$T/seen.log"
    ! grep -qF 'using the non-pooled' "$T/err"
}

@test "codex: notice names no environment value" {
    export CODEX_OPENAI_BASE_URL="$ROUTE/v1"
    run_codex
    [ "$status" -eq 0 ]
    grep -F 'using the non-pooled' "$T/err" > "$T/notice"
    [ "$(cat "$T/notice")" = "$NOTICE_CODEX" ]
    ! grep -qF "$PORT" "$T/notice"
    ! grep -qF thr_fixture "$T/notice"
}
