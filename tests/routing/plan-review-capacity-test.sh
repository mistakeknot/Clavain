#!/usr/bin/env bash
# mk-esex: a foundational plan review must degrade, not block, when the
# preferred other-lab reviewer is out of capacity. capacity-fallback-test.sh
# covers what `ic route dispatch` RESOLVES; this covers what dispatch.sh
# actually RUNS: --role plan-review under a Codex usage-limit failure, driven
# through the real dispatch walk (quota_exhausted -> next declared fallback).
#
# Invariants pinned here (reasoning-routing.md "Use one frontier author" and
# reasoning-routing-operations.md "Scope correction (mk-9yyt)"):
#   - Fable-authored plan: Astra quota-exhausts, review lands on Opus (a
#     distinct frontier model), dispatch succeeds.
#   - No leg of the walk ever reviews with the producer's own model.
#   - When every non-producer candidate is out, review stays blocked
#     (non-zero exit) instead of falling through to the producer.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

command -v ic >/dev/null 2>&1 || { echo "SKIP: ic not on PATH" >&2; exit 0; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not on PATH" >&2; exit 0; }

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work"
git -C "$TMP_ROOT/work" init -q
git -C "$TMP_ROOT/work" -c user.email=test@example.com -c user.name=test commit -q --allow-empty -m init

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Fake codex: every model reports the Codex usage-limit error unless
# FAKE_CODEX_MODE=success.
cat > "$TMP_ROOT/bin/codex" <<'FAKE_CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "codex-cli 0.154.0"
  exit 0
fi
model=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "-m" ]] && model="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CODEX_LOG"
if [[ "${FAKE_CODEX_MODE:-quota}" == success ]]; then
  echo '{"type":"task_complete","last_agent_message":"VERDICT: CLEAN"}'
  exit 0
fi
echo '{"type":"task_complete","error":{"codex_error_info":"usage_limit_exceeded"}}'
FAKE_CODEX

# Fake claude: logs the --model it was given. A model listed in
# FAKE_CLAUDE_QUOTA answers the way the Claude CLI's stream-json reports a
# subscription limit: error "rate_limit" plus the limit text, exit 1.
cat > "$TMP_ROOT/bin/claude" <<'FAKE_CLAUDE'
#!/usr/bin/env bash
model=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "--model" ]] && model="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CLAUDE_LOG"
cat > /dev/null
if [[ " ${FAKE_CLAUDE_QUOTA:-} " == *" $model "* ]]; then
  text="You've hit your weekly limit · resets Sep 26, 7pm (UTC)"
  jq -cn --arg t "$text" '{type:"assistant",message:{content:[{type:"text",text:$t}]},error:"rate_limit"}'
  jq -cn --arg t "$text" '{type:"result",subtype:"success",is_error:true,result:$t}'
  exit 1
fi
echo 'VERDICT: CLEAN'
FAKE_CLAUDE
chmod +x "$TMP_ROOT/bin/codex" "$TMP_ROOT/bin/claude"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export FAKE_CLAUDE_LOG="$TMP_ROOT/claude.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_BB_DIRECT_POOL=0
export CLAVAIN_429_BACKOFF_SECONDS=0
export CLAVAIN_ROUTING_POLICY="${PLAN_REVIEW_TEST_POLICY:-$ROOT/config/routing.yaml}"
(cd "$TMP_ROOT/work" && ic init >/dev/null 2>&1) || true

CONTEXT_FILE="$TMP_ROOT/context.json"
printf '%s\n' '{"reasons":["foundational-invariants"],"rationale":"plan-review capacity degradation coverage","domain":"routing policy","investigation_active":false}' > "$CONTEXT_FILE"

# Runs one plan review; leaves the exit code in $rc and stderr in $TMP_ROOT/err.
run_review() {
  local producer="$1"
  : > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
  rc=0
  bash "$ROOT/scripts/dispatch.sh" --role plan-review --producer-identity "$producer" \
    --context-file "$CONTEXT_FILE" -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer.md" \
    "review the plan" >/dev/null 2>"$TMP_ROOT/err" || rc=$?
}

never_reviewed_by() {
  local label="$1" model="$2"
  if grep -qx -- "$model" "$FAKE_CODEX_LOG" "$FAKE_CLAUDE_LOG" 2>/dev/null; then
    fail "$label: the producer's own model $model reviewed its plan (codex: $(paste -sd' ' "$FAKE_CODEX_LOG"); claude: $(paste -sd' ' "$FAKE_CLAUDE_LOG"))"
  fi
}

# Fable-authored plan, Codex out: Astra is tried, quota-exhausts, and the
# walk continues to Opus rather than blocking.
run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "Fable producer, Codex out: expected review to degrade and succeed, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-6-astra" ]] || fail "Fable producer: expected one gpt-6-astra attempt first, got: $(cat "$FAKE_CODEX_LOG")"
[[ "$(cat "$FAKE_CLAUDE_LOG")" == "claude-opus-5" ]] || fail "Fable producer: expected the capacity substitute claude-opus-5, got: $(cat "$FAKE_CLAUDE_LOG")"
grep -q "quota_exhausted" "$TMP_ROOT/err" || fail "Fable producer: the Astra quota failure left no record on stderr"
never_reviewed_by "Fable producer" claude-fable-5-1

# Opus-authored plan: Fable is the preferred reviewer and Codex is never
# needed, so the outage does not touch it.
run_review claude-opus-5
[[ "$rc" == 0 ]] || fail "Opus producer: expected success, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ "$(cat "$FAKE_CLAUDE_LOG")" == "claude-fable-5-1" ]] || fail "Opus producer: expected claude-fable-5-1, got: $(cat "$FAKE_CLAUDE_LOG")"
never_reviewed_by "Opus producer" claude-opus-5

# Astra-authored plan: Fable reviews; Astra must never review itself even
# though its lane is the one reported out.
run_review gpt-6-astra
[[ "$rc" == 0 ]] || fail "Astra producer: expected success, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ "$(cat "$FAKE_CLAUDE_LOG")" == "claude-fable-5-1" ]] || fail "Astra producer: expected claude-fable-5-1, got: $(cat "$FAKE_CLAUDE_LOG")"
never_reviewed_by "Astra producer" gpt-6-astra

# Opus-authored plan, Fable out of Claude quota: the walk must continue to
# Astra. Before mk-esex the Claude limit classified as terminal_error and the
# fallback was suppressed, so this review blocked.
FAKE_CODEX_MODE=success FAKE_CLAUDE_QUOTA="claude-fable-5-1" run_review claude-opus-5
[[ "$rc" == 0 ]] || fail "Opus producer, Fable out: expected review to degrade to Astra, got exit $rc: $(grep '^dispatch:' "$TMP_ROOT/err" | tail -3)"
[[ "$(cat "$FAKE_CLAUDE_LOG")" == "claude-fable-5-1" ]] || fail "Opus producer, Fable out: expected one claude-fable-5-1 attempt first, got: $(cat "$FAKE_CLAUDE_LOG")"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-6-astra" ]] || fail "Opus producer, Fable out: expected the fallback gpt-6-astra, got: $(cat "$FAKE_CODEX_LOG")"
grep -q "quota_exhausted" "$TMP_ROOT/err" || fail "Opus producer, Fable out: the Fable quota failure left no record on stderr"
never_reviewed_by "Opus producer, Fable out" claude-opus-5

echo "PASS: plan review degrades to a distinct frontier model when the preferred reviewer is out of quota"

# Every non-producer seat out (Astra and Opus both quota-exhausted, Fable is
# the producer): the review must stay blocked, never fall through to Fable.
FAKE_CLAUDE_QUOTA="claude-opus-5" run_review claude-fable-5-1
[[ "$rc" != 0 ]] || fail "all non-producer reviewers out: expected a blocked review (non-zero exit), got success"
never_reviewed_by "all reviewers out" claude-fable-5-1

echo "PASS: plan review stays blocked rather than self-reviewing when no distinct frontier model is available"
