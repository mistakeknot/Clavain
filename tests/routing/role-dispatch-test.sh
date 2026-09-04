#!/usr/bin/env bash
# Role-aware dispatch acceptance suite. Uses fake ic/codex binaries and never
# invokes a model service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work"

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
  cat <<'JSON'
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
esac
echo 'VERDICT: CLEAN'
FAKE_CODEX
chmod +x "$TMP_ROOT/bin/ic" "$TMP_ROOT/bin/codex"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_IC_LOG="$TMP_ROOT/ic.log"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_429_BACKOFF_SECONDS=0

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
FAKE_CODEX_MODE=rate429 CLAVAIN_429_MAX_RETRIES=2 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" "hi" >/dev/null 2>&1
rate_rc=$?
set -e
[[ "$rate_rc" != "0" ]] || fail "persistent 429 unexpectedly succeeded"
[[ "$(wc -l < "$FAKE_CODEX_LOG" | tr -d ' ')" == "3" ]] || fail "429 attempts were not bounded at 3"
[[ "$(sort -u "$FAKE_CODEX_LOG")" == "gpt-6-astra" ]] || fail "429 silently changed models"

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

echo "PASS: role-aware dispatch profiles and fallback policy"
