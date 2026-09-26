#!/usr/bin/env bash
# Role-aware dispatch acceptance suite. Uses fake ic/codex binaries and never
# invokes a model service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work"
git init -q "$TMP_ROOT/work"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

contains() {
  local haystack="$1" needle="$2"
  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain '$needle'"
}

cat > "$TMP_ROOT/bin/ic" <<'FAKE_IC'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_IC_LOG"
if [[ "$*" == *"route dispatch"* ]]; then
  cat <<'JSON' | jq --arg args "$*" --arg policy "$FAKE_ROUTING_POLICY" --arg hash "$FAKE_POLICY_HASH" '.policy_source=$policy | .policy_hash=$hash | if env.FAKE_ROUTE_KIMI_FIRST == "1" then .profile_ref="unsupported-kimi" | .profile.backend="kimi" | .profile.model="kimi-code/k3" else . end | if ($args | contains("--producer-identity=")) then .producer_model="gpt-6-astra" | .validator_relationship="different-model" | .fallback_reason="producer_model_conflict" | .profile_ref=.fallback_chain[0].profile_ref | .profile=.fallback_chain[0].profile | .fallback_chain=[] else . end | if env.FAKE_ROUTE_CROSS_LAB_REORDER == "1" then .cross_lab_reorder={"from":["a","b"],"to":["b","a"]} else . end'
{
  "requested_role": "deep-execution",
  "profile_ref": "deep-astra",
  "profile": {
    "role": "deep-execution",
    "backend": "codex",
    "model": "gpt-6-astra",
    "reasoning_effort": "high",
    "service_tier": "standard",
    "minimum_codex_version": "0.153.1",
    "fallbacks": ["deep-sol"]
  },
  "fallback_chain": [
    {
      "profile_ref": "deep-sol",
      "profile": {
        "role": "deep-execution",
        "backend": "codex",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "service_tier": "standard"
      }
    }
  ]
}
JSON
fi
if [[ "$*" == *"route record"* && "${FAKE_IC_RECORD_FAIL:-0}" == "1" ]]; then
  exit 1
fi
if [[ "$*" == *"route record"* ]]; then
  for arg in "$@"; do
    case "$arg" in --context=*) printf '%s\n' "${arg#--context=}" >> "$FAKE_IC_CONTEXT_LOG" ;; esac
  done
fi
FAKE_IC

cat > "$TMP_ROOT/bin/codex" <<'FAKE_CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "codex-cli ${FAKE_CODEX_VERSION:-0.153.2}"
  exit 0
fi
model=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[$i]}" == "-m" ]]; then
    model="${args[$((i+1))]:-}"
  fi
done
printf '%s\n' "$model" >> "$FAKE_CODEX_LOG"
pooled=0; for a in "$@"; do [[ "$a" != 'model_provider="bb-account-pool"' ]] || pooled=1; done
printf '%s:%s:%s\n' "$model" "$pooled" "${CODEX_POOL_AUTH_TOKEN:-}" >> "$FAKE_CODEX_LOG.pool"
if [[ "${FAKE_CODEX_MODE:-}" == quota* ]]; then
  printf '%s:%s\n' "$model" "${CLAVAIN_BB_POOL_RETRY:-0}" >> "$FAKE_CODEX_LOG.axes"
  if [[ "$model" == gpt-6-astra && ( "${FAKE_CODEX_MODE}" == quota_all || "${CLAVAIN_BB_POOL_RETRY:-0}" != 1 ) ]]; then
    echo '{"type":"task_complete","error":{"codex_error_info":"usage_limit_exceeded"}}'
    exit 0
  fi
fi
case "${FAKE_CODEX_MODE:-success}" in
  unsupported)
    if [[ "$model" == "gpt-6-astra" ]]; then
      echo '{"type":"error","status":400,"error":{"message":"The gpt-6-astra model is not supported when using Codex with a ChatGPT account."}}' >&2
      exit 1
    fi
    ;;
  policy403)
    echo 'stream error: unexpected status 403 Forbidden: misalignment policy blocked request' >&2
    exit 1
    ;;
  policy_account)
    echo 'HTTP 403 Forbidden: misalignment policy blocked account access' >&2
    exit 1
    ;;
  policy_after_rate)
    echo 'HTTP 429 Too Many Requests' >&2
    echo 'HTTP 403 Forbidden: misalignment policy blocked request' >&2
    exit 1
    ;;
  policy_model)
    echo 'HTTP 403 Forbidden: policy denied; model unavailable' >&2
    exit 1
    ;;
  rate429)
    echo 'stream error: unexpected status 429 Too Many Requests: rate limited' >&2
    exit 1
    ;;
  evidence)
    echo '{"type":"turn.failed","request_id":"req-fixture","error":{"code":"unknown_failure","provider_reason":"seat_exhausted","provider_token":"tok-provider-fixture-secret"}}'
    echo 'Authorization: Bearer bearer-fixture-secret for dev@example.test in /home/private-user/repo' >&2
    exit 7
    ;;
esac
echo 'VERDICT: CLEAN'
FAKE_CODEX
chmod +x "$TMP_ROOT/bin/ic" "$TMP_ROOT/bin/codex"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_ROUTING_POLICY="$ROOT/config/routing.yaml"
FAKE_POLICY_HASH="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$FAKE_ROUTING_POLICY")"
export FAKE_POLICY_HASH
export FAKE_IC_LOG="$TMP_ROOT/ic.log"
export FAKE_IC_CONTEXT_LOG="$TMP_ROOT/contexts.jsonl"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_BB_DIRECT_POOL=0

dry_run="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --role deep-execution -C "$TMP_ROOT/work" "hi" 2>&1)" \
  || fail "role dry-run failed"
contains "$dry_run" "-m gpt-6-astra"
contains "$dry_run" "model_reasoning_effort=high"
contains "$dry_run" "service_tier=default"

dry_zaka="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --via zaka --role deep-execution -C "$TMP_ROOT/work" "hi" 2>&1)" \
  || fail "role zaka dry-run failed"
contains "$dry_zaka" "zaka spawn"
contains "$dry_zaka" "--agent-arg=-c"
contains "$dry_zaka" "--agent-arg=model_reasoning_effort=high"
contains "$dry_zaka" "--agent-arg=service_tier=default"

: > "$FAKE_CODEX_LOG"
unsupported_out="$(FAKE_CODEX_MODE=unsupported bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" 2>&1)" \
  || { echo "$unsupported_out" >&2; fail "account-access fallback failed"; }
attempts=()
while IFS= read -r attempt; do
  attempts+=("$attempt")
done < "$FAKE_CODEX_LOG"
[[ "${#attempts[@]}" == "2" ]] || fail "account-access fallback attempts=${#attempts[@]}, want 2"
[[ "${attempts[0]}" == "gpt-6-astra" && "${attempts[1]}" == "gpt-5.6-sol" ]] \
  || fail "account-access fallback order was: ${attempts[*]}"

: > "$FAKE_CODEX_LOG"
set +e
FAKE_CODEX_MODE=policy403 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
policy_rc=$?
set -e
[[ "$policy_rc" != "0" ]] || fail "policy 403 unexpectedly succeeded"
[[ "$(wc -l < "$FAKE_CODEX_LOG" | tr -d ' ')" == "1" ]] || fail "policy 403 triggered fallback"

for policy_mode in policy_account policy_after_rate policy_model; do
  : > "$FAKE_CODEX_LOG"
  set +e
  FAKE_CODEX_MODE="$policy_mode" bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
  policy_rc=$?
  set -e
  [[ "$policy_rc" != "0" ]] || fail "$policy_mode unexpectedly succeeded"
  [[ "$(wc -l < "$FAKE_CODEX_LOG" | tr -d ' ')" == "1" ]] || fail "$policy_mode triggered retry or fallback"
done

: > "$FAKE_CODEX_LOG"
set +e
FAKE_CODEX_MODE=rate429 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
rate_rc=$?
set -e
# An exhausted-retries 429 is capacity, not a reason to keep hammering the
# same model (mk ruling 2026-09-25, mk-nh6v): exactly one attempt on the
# first model, then the walk moves to its declared fallback — which also
# 429s here, so the role stays blocked rather than looping.
[[ "$rate_rc" != "0" ]] || fail "persistent 429 unexpectedly succeeded"
[[ "$(cat "$FAKE_CODEX_LOG")" == "$(printf 'gpt-6-astra\ngpt-5.6-sol')" ]] \
  || fail "429 did not make exactly one attempt per candidate then walk: $(cat "$FAKE_CODEX_LOG")"

: > "$FAKE_CODEX_LOG"
FAKE_CODEX_VERSION=0.150.0 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1 \
  || fail "minimum-version fallback failed"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "old Codex did not skip Astra: $(cat "$FAKE_CODEX_LOG")"

: > "$FAKE_CODEX_LOG"
bash "$ROOT/scripts/dispatch.sh" --role validation --producer-identity codex/gpt-6-astra -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1 \
  || fail "validator model separation failed"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] \
  || fail "validator reused producer model: $(cat "$FAKE_CODEX_LOG")"

set +e
bash "$ROOT/scripts/dispatch.sh" --role validation -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
missing_producer_rc=$?
set -e
[[ "$missing_producer_rc" != "0" ]] || fail "validation role accepted no producer identity"

set +e
FAKE_IC_RECORD_FAIL=1 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
record_rc=$?
set -e
[[ "$record_rc" != "0" ]] || fail "role dispatch succeeded without a durable routing record"

contains "$(cat "$FAKE_IC_LOG")" "route record"
contains "$(cat "$FAKE_IC_LOG")" "--role=deep-execution"
contains "$(cat "$FAKE_IC_LOG")" "--profile=deep-sol"
contains "$(cat "$FAKE_IC_LOG")" "--producer-identity=codex/gpt-6-astra"
[[ -s "$FAKE_IC_CONTEXT_LOG" ]] || fail "missing immutable routing contexts"
jq -s -e 'all(.[]; .schema_version == 1 and (.dispatch_id | length > 0) and (.attempt_id | length > 0) and .resolved_profile.profile.model != null and .resolved_route.profile != null and .execution.service_tier == "standard")' "$FAKE_IC_CONTEXT_LOG" >/dev/null || fail "incomplete routing snapshot"
jq -s -e 'any(.[]; .state == "started") and any(.[]; .state == "completed") and any(.[]; .state == "failed" and .result.failure_class == "terminal_policy")' "$FAKE_IC_CONTEXT_LOG" >/dev/null || fail "missing dispatch lifecycle evidence"

rm -rf "$TMP_ROOT/work/.clavain/intercept"
set +e
FAKE_CODEX_MODE=evidence bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
evidence_rc=$?
set -e
[[ "$evidence_rc" != "0" ]] || fail "evidence fixture unexpectedly succeeded"
mapfile -t evidence_files < <(find "$TMP_ROOT/work/.clavain/intercept" -maxdepth 1 -type f -name '*.json')
[[ "${#evidence_files[@]}" == "1" ]] || fail "expected one intercept artifact"
evidence_file="${evidence_files[0]}"
if rg -q 'bearer-fixture-secret|tok-provider-fixture-secret|dev@example.test|/home/private-user' "$evidence_file"; then
  fail "intercept artifact leaked redacted fixture data"
fi
evidence_ref="$(jq -sc '[.[] | select(.state == "failed" and .result.intercept_evidence != null)] | last.result.intercept_evidence' "$FAKE_IC_CONTEXT_LOG")"
[[ "$(jq -r '.path' <<< "$evidence_ref")" == ".clavain/intercept/$(basename "$evidence_file")" ]] || fail "receipt did not link intercept path"
[[ "$(jq -r '.sha256' <<< "$evidence_ref")" == "$(sha256sum "$evidence_file" | awk '{print $1}')" ]] || fail "receipt did not link intercept hash"
[[ -z "$(git -C "$TMP_ROOT/work" status --porcelain -- .clavain/intercept)" ]] || fail "intercept evidence is visible to target repository status"

rm -rf "$TMP_ROOT/work/.clavain/intercept"
mkdir -p "$TMP_ROOT/work/.clavain"
printf '%s\n' 'not a directory' > "$TMP_ROOT/work/.clavain/intercept"
set +e
FAKE_CODEX_MODE=policy403 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
evidence_write_rc=$?
set -e
[[ "$evidence_write_rc" != "0" ]] || fail "blocked evidence write unexpectedly succeeded"
evidence_write_result="$(jq -sc '[.[] | select(.state == "failed" and .result.intercept_evidence_error != null)] | last.result' "$FAKE_IC_CONTEXT_LOG")"
[[ "$(jq -r '.failure_class' <<< "$evidence_write_result")" == "terminal_policy" ]] || fail "evidence failure replaced provider class"
[[ "$(jq -r '.intercept_evidence_error' <<< "$evidence_write_result")" == "terminal_recording" ]] || fail "receipt omitted evidence write failure"
rm -f "$TMP_ROOT/work/.clavain/intercept"

: > "$FAKE_CODEX_LOG"
FAKE_IC_RECORD_FAIL=1 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1 && fail "dispatch accepted failed preflight audit"
[[ ! -s "$FAKE_CODEX_LOG" ]] || fail "model executed before durable start record"

: > "$FAKE_CODEX_LOG"
unsupported_adapter_out="$(FAKE_ROUTE_KIMI_FIRST=1 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" 2>&1)" \
  || fail "unsupported adapter stopped a declared eligible fallback"
contains "$unsupported_adapter_out" 'unsupported_adapter'
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "unsupported Kimi effort did not reach declared Sol fallback"
contains "$(cat "$FAKE_IC_LOG")" '--fallback-reason=unsupported_adapter'

# A route resolution that reordered candidates across labs is recorded verbatim
# on the routing decision; a route with no reorder never gets the flag.
: > "$FAKE_IC_LOG"
FAKE_ROUTE_CROSS_LAB_REORDER=1 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1 \
  || fail "cross-lab-reorder dispatch failed"
contains "$(cat "$FAKE_IC_LOG")" '--cross-lab-reorder={"from":["a","b"],"to":["b","a"]}'

: > "$FAKE_IC_LOG"
bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1 \
  || fail "no-reorder dispatch failed"
if grep -q -- '--cross-lab-reorder=' "$FAKE_IC_LOG"; then
  fail "route record passed --cross-lab-reorder without a reorder"
fi

echo "PASS: role-aware dispatch profiles and fallback policy"

# Account capacity retry precedes changing the model; a candidate/axis is visited once.
cat > "$TMP_ROOT/pool-server.py" <<'POOL_SERVER'
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith('/api/v1/plugins/account-pool/http/availability?threadId='):
            self.send_error(404)
            return
        if not self.headers.get('x-bb-account-pool-token'):
            self.send_error(401)
            return
        body = json.dumps({'threadId': 'fixture-thread', 'availability': {'claude': True, 'codex': True}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
Path(sys.argv[1]).write_text(str(server.server_port))
server.serve_forever()
POOL_SERVER
python3 "$TMP_ROOT/pool-server.py" "$TMP_ROOT/pool-port" &
pool_server_pid=$!
trap 'kill "$pool_server_pid" 2>/dev/null || true; rm -rf "$TMP_ROOT"' EXIT
for _ in $(seq 1 50); do
  [[ -s "$TMP_ROOT/pool-port" ]] && break
  sleep 0.1
done
[[ -s "$TMP_ROOT/pool-port" ]] || fail "pool fixture did not start"
cat > "$TMP_ROOT/bin/bb" <<'BB'
#!/bin/sh
printf '%s\n' '{"thread":{"id":"fixture-thread","environment":{"hostId":"host_pda34naxgq"}}}'
BB
chmod +x "$TMP_ROOT/bin/bb"
export BB_CLI="$TMP_ROOT/bin/bb" BB_THREAD_ID=fixture-thread BB_SERVER_URL="http://127.0.0.1:$(cat "$TMP_ROOT/pool-port")"
export CODEX_POOL_AUTH_TOKEN=fixture-only CODEX_OPENAI_BASE_URL="$BB_SERVER_URL/api/v1/plugins/account-pool/http/v1" CLAVAIN_BB_DIRECT_POOL=1
for mode in quota_once quota_all; do
  : > "$FAKE_CODEX_LOG.axes"
  FAKE_CODEX_MODE="$mode" bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" fixture >/dev/null 2>&1 || fail "$mode failed"
  expected=$'gpt-6-astra:0\ngpt-6-astra:1'
  [[ "$mode" != quota_all ]] || expected+=$'\ngpt-5.6-sol:0'
  [[ "$(cat "$FAKE_CODEX_LOG.axes")" == "$expected" ]] || fail "wrong account/model fallback order"
done
echo 'PASS: quota account retry precedes model fallback'

# From a Claude Code BB thread there is no native Codex token: every Codex attempt,
# the quota pool retry included, borrows the machine bearer from the Anthropic pool route.
unset CODEX_POOL_AUTH_TOKEN CODEX_OPENAI_BASE_URL
export ANTHROPIC_AUTH_TOKEN=machine-fixture ANTHROPIC_BASE_URL="$BB_SERVER_URL/api/v1/plugins/account-pool/http"
: > "$FAKE_CODEX_LOG.axes"; : > "$FAKE_CODEX_LOG.pool"
FAKE_CODEX_MODE=quota_all bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" fixture >/dev/null 2>&1 || fail "claude-thread quota_all failed"
[[ "$(cat "$FAKE_CODEX_LOG.axes")" == $'gpt-6-astra:0\ngpt-6-astra:1\ngpt-5.6-sol:0' ]] || fail "claude-thread pool retry did not fire"
[[ "$(cat "$FAKE_CODEX_LOG.pool")" == $'gpt-6-astra:1:machine-fixture\ngpt-6-astra:1:machine-fixture\ngpt-5.6-sol:1:machine-fixture' ]] || fail "claude-thread codex attempts were not pooled"
: > "$FAKE_CODEX_LOG.axes"; : > "$FAKE_CODEX_LOG.pool"
CLAVAIN_BB_DIRECT_POOL=0 FAKE_CODEX_MODE=quota_all bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" fixture >/dev/null 2>&1 || fail "kill-switch dispatch did not reach its Sol fallback"
[[ "$(cat "$FAKE_CODEX_LOG.axes")" == $'gpt-6-astra:0\ngpt-5.6-sol:0' ]] || fail "kill switch still ran the pool retry"
[[ "$(cat "$FAKE_CODEX_LOG.pool")" == $'gpt-6-astra:0:\ngpt-5.6-sol:0:' ]] || fail "kill switch still pooled or borrowed"
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL
echo 'PASS: Claude-thread Codex seats borrow the pool token; kill switch holds'
