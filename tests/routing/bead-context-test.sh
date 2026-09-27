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
  # Only CLAVAIN_BEAD_ID itself may reach the model seat, and only when the
  # caller already had it exported (the "env" source, via `env VAR=... cmd`).
  # Bookkeeping (source/resolved) must never leak; a --bead flag or an
  # interstat-session file never exported anything for the caller to keep.
  if [[ "$source" == env ]]; then
    check "$source id reaches model seat, bookkeeping does not" \
      test "$(sort -u "$TEST_ENV_LOG")" = 'env-bead|unset|unset'
  else
    check "$source absent from model seat environment" test "$(sort -u "$TEST_ENV_LOG")" = 'unset|unset|unset'
  fi
  if [[ "$source" == env ]]; then
    # A genuinely caller-exported CLAVAIN_BEAD_ID is real shell state: it flows
    # to every descendant process the worker spawns, including a nested
    # dispatch.sh call, exactly as it did before cdaa910 introduced bead
    # resolution at all. Item 6 requires restoring that passthrough for the
    # worker's own environment; there is no env-var-scoping trick that gives
    # the worker the export while hiding it from a grandchild process the
    # worker itself launches, since both read the same process environment.
    # A nested dispatch therefore correctly reports the inherited env bead
    # here, not its own interstat-session mapping.
    check "env inherited by nested dispatch (accepted item-6 tradeoff)" receipt_has env-bead env
  else
    check "$source does not override nested session" receipt_has child-bead interstat-session
  fi
done
# Reviewer-flagged regression (mk-42j9.29 delta review of 0e08d59): a
# caller-exported CLAVAIN_BEAD_ID must only reach a nested dispatch's own
# environment when the RESOLVED bead source is literally "env" -- not merely
# because the caller happened to have it exported. An empty/invalid export,
# or one that loses to a higher-precedence --bead flag, must not leak into
# the nested dispatch labelled "env".
: > "$TEST_RECEIPTS"; : > "$TEST_ENV_LOG"
CLAVAIN_BEAD_ID= DISPATCH_SESSION_ID=outer TEST_NESTED=1 \
  bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TEST_WORK" hi \
  > "$TMP_ROOT/empty-env-session-nested.log" 2>&1 \
  || { cat "$TMP_ROOT/empty-env-session-nested.log"; exit 1; }
check 'exported-empty env + session: nested dispatch uses its own session, not env' \
  receipt_has child-bead interstat-session

: > "$TEST_RECEIPTS"; : > "$TEST_ENV_LOG"
CLAVAIN_BEAD_ID='not valid!' DISPATCH_SESSION_ID=outer TEST_NESTED=1 \
  bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TEST_WORK" hi \
  > "$TMP_ROOT/invalid-env-session-nested.log" 2>&1 \
  || { cat "$TMP_ROOT/invalid-env-session-nested.log"; exit 1; }
check 'exported-invalid env + session: nested dispatch uses its own session, not env' \
  receipt_has child-bead interstat-session

: > "$TEST_RECEIPTS"; : > "$TEST_ENV_LOG"
CLAVAIN_BEAD_ID=env-bead DISPATCH_SESSION_ID=outer TEST_NESTED=1 \
  bash "$ROOT/scripts/dispatch.sh" --role deep-execution --bead flag-bead -C "$TEST_WORK" hi \
  > "$TMP_ROOT/env-plus-flag-nested.log" 2>&1 \
  || { cat "$TMP_ROOT/env-plus-flag-nested.log"; exit 1; }
check 'exported env + --bead flag: nested dispatch uses its own session, not env' \
  receipt_has child-bead interstat-session

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

# The --role-resolved self-exec must preserve the parent's invalid-env label
# rather than silently re-deriving a different, less-honest one.
: > "$TEST_RECEIPTS"
CLAVAIN_BEAD_ID='invalid env!' DISPATCH_SESSION_ID=outer-no-session \
  bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TEST_WORK" hi \
  > "$TMP_ROOT/env-invalid-no-session.log" 2>&1
check 'invalid env with no session preserves invalid-env label' receipt_has '' invalid-env

: > "$TEST_RECEIPTS"
CLAVAIN_BEAD_ID='invalid env!' DISPATCH_SESSION_ID=invalid \
  bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TEST_WORK" hi \
  > "$TMP_ROOT/env-invalid-and-session-invalid.log" 2>&1
check 'invalid env then invalid session preserves compound label' \
  receipt_has '' invalid-env-then-invalid-interstat-session

echo "RESULT: $passed passed, $failed failed"
[[ "$failed" == 0 ]]
