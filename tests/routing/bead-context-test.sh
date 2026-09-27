#!/usr/bin/env bash
# Receipt-only bead context must survive self-exec without leaking to workers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work" "$TMP_ROOT/interstat"
git init -q "$TMP_ROOT/work"
cat > "$TMP_ROOT/bin/ic" <<'IC'
#!/usr/bin/env bash
if [[ "$*" == *'route dispatch'* ]]; then
  jq -n --arg policy "$TEST_ROOT/config/routing.yaml" --arg hash "$TEST_POLICY_HASH" \
    '{requested_role:"deep-execution",profile_ref:"deep-astra",policy_source:$policy,
      policy_hash:$hash,profile:{backend:"codex",model:"gpt-6-astra",
      reasoning_effort:"high",service_tier:"standard"},fallback_chain:[]}'
elif [[ "$*" == *'route record'* ]]; then
  for arg in "$@"; do
    case "$arg" in --context=*) printf '%s\n' "${arg#--context=}" >> "$TEST_RECEIPTS" ;; esac
  done
fi
IC
cat > "$TMP_ROOT/bin/codex" <<'CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == --version ]]; then echo 'codex-cli 0.153.2'; exit 0; fi
printf '%s|%s|%s\n' "${CLAVAIN_BEAD_ID-unset}" "${CLAVAIN_BEAD_SOURCE-unset}" \
  "${CLAVAIN_BEAD_CONTEXT_RESOLVED-unset}" >> "$TEST_ENV_LOG"
if [[ "${TEST_NESTED:-0}" == 1 ]]; then
  TEST_NESTED=0 DISPATCH_SESSION_ID=nested \
    bash "$TEST_ROOT/scripts/dispatch.sh" --role deep-execution -C "$TEST_WORK" 'child'
fi
while [[ $# -gt 0 ]]; do
  if [[ "$1" == -o ]]; then printf 'VERDICT: CLEAN\n' > "$2"; break; fi
  shift
done
echo 'VERDICT: CLEAN'
CODEX
chmod +x "$TMP_ROOT/bin/"*
export PATH="$TMP_ROOT/bin:$PATH" TEST_ROOT="$ROOT" TEST_WORK="$TMP_ROOT/work"
export TEST_RECEIPTS="$TMP_ROOT/receipts" TEST_ENV_LOG="$TMP_ROOT/env"
TEST_POLICY_HASH="$(sha256sum "$ROOT/config/routing.yaml" | awk '{print $1}')"
export TEST_POLICY_HASH
export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
export CLAVAIN_INTERSTAT_BEAD_DIR="$TMP_ROOT/interstat"
unset CLAVAIN_BEAD_ID CLAVAIN_BEAD_SOURCE CLAVAIN_BEAD_CONTEXT_RESOLVED
printf 'session-bead\n' > "$TMP_ROOT/interstat/interstat-bead-outer"
printf 'child-bead\n' > "$TMP_ROOT/interstat/interstat-bead-nested"
passed=0 failed=0
check() {
  local name="$1"; shift
  if "$@"; then echo "PASS: $name"; passed=$((passed+1))
  else echo "FAIL: $name"; failed=$((failed+1)); fi
}
receipt_has() {
  jq -se --arg bead "$1" --arg source "$2" \
    'any(.[]; .state == "completed" and .bead_id == $bead and .bead_source == $source)' "$TEST_RECEIPTS" >/dev/null
}
for source in flag env session; do
  : > "$TEST_RECEIPTS"; : > "$TEST_ENV_LOG"
  args=(); dispatch_env=()
  case "$source" in
    flag) args=(--bead flag-bead); bead=flag-bead; provenance=flag ;;
    env) dispatch_env=(CLAVAIN_BEAD_ID=env-bead); bead=env-bead; provenance=env ;;
    session) bead=session-bead; provenance=interstat-session ;;
  esac
  env "${dispatch_env[@]}" DISPATCH_SESSION_ID=outer TEST_NESTED=1 \
    bash "$ROOT/scripts/dispatch.sh" --role deep-execution "${args[@]}" \
    -C "$TEST_WORK" hi > "$TMP_ROOT/$source.log" 2>&1 \
    || { cat "$TMP_ROOT/$source.log"; exit 1; }
  check "$source survives self-exec" receipt_has "$bead" "$provenance"
  check "$source absent from model seat environment" test "$(sort -u "$TEST_ENV_LOG")" = 'unset|unset|unset'
  check "$source does not override nested session" receipt_has child-bead interstat-session
done
for value in 'not valid!' ''; do
  : > "$TEST_RECEIPTS"; : > "$TEST_ENV_LOG"
  rc=0
  CLAVAIN_BEAD_ID=env-bead bash "$ROOT/scripts/dispatch.sh" --role deep-execution \
    "--bead=$value" -C "$TEST_WORK" hi > "$TMP_ROOT/invalid.log" 2>&1 || rc=$?
  check "invalid flag '$value' fails before worker" test "$rc" -ne 0
  check "invalid flag '$value' warns" grep -q 'invalid --bead' "$TMP_ROOT/invalid.log"
  check "invalid flag '$value' records no other bead" test ! -s "$TEST_RECEIPTS"
done
: > "$TEST_RECEIPTS"
CLAVAIN_BEAD_ID='invalid env!' DISPATCH_SESSION_ID=outer \
  bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TEST_WORK" hi > "$TMP_ROOT/env-invalid.log" 2>&1
check 'invalid env warns before fallback' grep -q 'invalid CLAVAIN_BEAD_ID' "$TMP_ROOT/env-invalid.log"
check 'invalid env fallback provenance' receipt_has session-bead invalid-env-then-interstat-session
printf 'invalid session!\n' > "$TMP_ROOT/interstat/interstat-bead-invalid"
: > "$TEST_RECEIPTS"
DISPATCH_SESSION_ID=invalid bash "$ROOT/scripts/dispatch.sh" --role deep-execution \
  -C "$TEST_WORK" hi > "$TMP_ROOT/session-invalid.log" 2>&1
check 'invalid session warns' grep -q 'invalid interstat-session bead' "$TMP_ROOT/session-invalid.log"
check 'invalid session records no bead' receipt_has '' invalid-interstat-session
echo "RESULT: $passed passed, $failed failed"
[[ "$failed" == 0 ]]
