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
if [[ "${FAKE_CODEX_MODE:-quota}" == rate429 ]]; then
  # A pooled Codex lane whose own client already retried and gave up
  # (mk-nh6v): classifies rate_limited, distinct from the model-level
  # usage_limit_exceeded quota case below.
  echo '{"type":"error","message":"exceeded retry limit, last status: 429 Too Many Requests"}'
  echo '{"type":"turn.failed","error":{"message":"exceeded retry limit, last status: 429 Too Many Requests"}}'
  exit 1
fi
echo '{"type":"task_complete","error":{"codex_error_info":"usage_limit_exceeded"}}'
FAKE_CODEX

# Fake claude: logs the --model it was given and its full stdin prompt
# (FAKE_CLAUDE_PROMPT_LOG; B1's re-check paragraph is verified there — real
# Claude receives the prompt via stdin, never argv). A model listed in
# FAKE_CLAUDE_QUOTA answers the way the Claude CLI's stream-json reports a
# subscription limit: error "rate_limit" plus the limit text, exit 1.
# Otherwise it answers with FAKE_CLAUDE_ANSWER (default "VERDICT: CLEAN") as
# a real stream-json result event, so dispatch's claude-response.py renders
# it into OUTPUT — required for B3 to parse a "## Re-check" section back out.
cat > "$TMP_ROOT/bin/claude" <<'FAKE_CLAUDE'
#!/usr/bin/env bash
model=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "--model" ]] && model="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CLAUDE_LOG"
stdin_prompt="$(cat)"
if [[ -n "${FAKE_CLAUDE_PROMPT_LOG:-}" ]]; then
  { printf '%s' "$stdin_prompt"; printf '\n<<<END-OF-PROMPT>>>\n'; } >> "$FAKE_CLAUDE_PROMPT_LOG"
fi
if [[ " ${FAKE_CLAUDE_QUOTA:-} " == *" $model "* ]]; then
  text="You've hit your weekly limit · resets Sep 26, 7pm (UTC)"
  jq -cn --arg t "$text" '{type:"assistant",message:{content:[{type:"text",text:$t}]},error:"rate_limit"}'
  jq -cn --arg t "$text" '{type:"result",subtype:"success",is_error:true,result:$t}'
  exit 1
fi
jq -cn --arg t "${FAKE_CLAUDE_ANSWER:-VERDICT: CLEAN}" '{type:"result",subtype:"success",is_error:false,result:$t}'
FAKE_CLAUDE

# Fake bd (B3/B5): logs each invocation's argv as one \x1f-separated line
# per call, and returns a fake id — verifies the capacity-recheck bead
# filing without touching the real tracker.
cat > "$TMP_ROOT/bin/bd" <<'FAKE_BD'
#!/usr/bin/env bash
{ printf '<<<BD-CALL>>>\n'; printf '%s\x1f' "$@"; printf '\n'; } >> "$FAKE_BD_LOG"
echo "fake-bd-1"
FAKE_BD
chmod +x "$TMP_ROOT/bin/codex" "$TMP_ROOT/bin/claude" "$TMP_ROOT/bin/bd"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export FAKE_CLAUDE_LOG="$TMP_ROOT/claude.log"
export FAKE_CLAUDE_PROMPT_LOG="$TMP_ROOT/claude-prompt.log"
export FAKE_BD_LOG="$TMP_ROOT/bd.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_BB_DIRECT_POOL=0
export CLAVAIN_ROUTING_POLICY="${PLAN_REVIEW_TEST_POLICY:-$ROOT/config/routing.yaml}"
(cd "$TMP_ROOT/work" && ic init >/dev/null 2>&1) || true

CONTEXT_FILE="$TMP_ROOT/context.json"
printf '%s\n' '{"reasons":["foundational-invariants"],"rationale":"plan-review capacity degradation coverage","domain":"routing policy","investigation_active":false}' > "$CONTEXT_FILE"

# Runs one plan review; leaves the exit code in $rc and stderr in $TMP_ROOT/err.
run_review() {
  local producer="$1"
  : > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"; : > "$FAKE_CLAUDE_PROMPT_LOG"; : > "$FAKE_BD_LOG"
  rm -f "$TMP_ROOT/answer.md.recheck.md"
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

# Fable-authored plan, Codex 429 (exhausted-retries, not model-level quota):
# per mk-nh6v this classifies rate_limited, gets the same single account-pool
# retry quota_exhausted gets (none available here: CLAVAIN_BB_DIRECT_POOL=0),
# then walks to Opus exactly like the quota case above.
FAKE_CODEX_MODE=rate429 run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "Fable producer, Codex 429: expected review to degrade and succeed, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-6-astra" ]] || fail "Fable producer, Codex 429: expected one gpt-6-astra attempt first, got: $(cat "$FAKE_CODEX_LOG")"
[[ "$(cat "$FAKE_CLAUDE_LOG")" == "claude-opus-5" ]] || fail "Fable producer, Codex 429: expected the capacity substitute claude-opus-5, got: $(cat "$FAKE_CLAUDE_LOG")"
grep -q "rate_limited" "$TMP_ROOT/err" || fail "Fable producer, Codex 429: the Astra 429 failure left no record on stderr"
never_reviewed_by "Fable producer, Codex 429" claude-fable-5-1

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

# --- mk-gp32: capacity-substitute reviews are provisional, never blocking --
#
# The Fable-producer/Codex-out case above (Astra quota-exhausts or 429s,
# Opus reviews) is itself the same-lab substitute this covers: producer
# claude-fable-5-1 and reviewer claude-opus-5 are both anthropic, and the
# candidate is reached after a walk (fallback_reason non-empty). Reuse it to
# check the reviewer's prompt carries B1's fixed re-check paragraph.
run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "capacity substitute: expected review to succeed, got exit $rc"
grep -q "capacity-substitute" "$FAKE_CLAUDE_PROMPT_LOG" || fail "capacity substitute: reviewer prompt did not carry the re-check paragraph: $(cat "$FAKE_CLAUDE_PROMPT_LOG")"
grep -q "## Re-check by the other lab" "$FAKE_CLAUDE_PROMPT_LOG" || fail "capacity substitute: reviewer prompt did not ask for a re-check section"
# The reviewer's answer (fixture default "VERDICT: CLEAN") omitted the
# section entirely: B3's parser treats a missing section like a full-review
# item, not like "None." — it still files, using the fabricated item.
grep -q "reviewer did not list re-check items" "$TMP_ROOT/answer.md.recheck.md" || fail "capacity substitute: a missing re-check section did not fall back to the whole-review item: $(cat "$TMP_ROOT/answer.md.recheck.md" 2>/dev/null)"
[[ "$(grep -c '<<<BD-CALL>>>' "$FAKE_BD_LOG")" == 1 ]] || fail "capacity substitute: a missing re-check section should still file one bead, got: $(cat "$FAKE_BD_LOG")"

# The reviewer lists two re-check items: dispatch writes a recheck sidecar
# and files exactly one bead, tagged back to the producing bead.
CLAVAIN_BEAD_ID="bd-parent-1" \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n- confirmed the migration script runs without executing it\n- unsure whether the fallback order still matches routing.yaml\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "two re-check items: expected review to succeed, got exit $rc"
[[ -f "$TMP_ROOT/answer.md.recheck.md" ]] || fail "two re-check items: expected a recheck sidecar file"
grep -q "confirmed the migration script" "$TMP_ROOT/answer.md.recheck.md" || fail "two re-check items: sidecar missing first item"
grep -q "unsure whether the fallback order" "$TMP_ROOT/answer.md.recheck.md" || fail "two re-check items: sidecar missing second item"
[[ "$(grep -c '<<<BD-CALL>>>' "$FAKE_BD_LOG")" == 1 ]] || fail "two re-check items: expected exactly one bd create call, got: $(cat "$FAKE_BD_LOG")"
grep -q "capacity-recheck" "$FAKE_BD_LOG" || fail "two re-check items: bd create did not carry the capacity-recheck label"
grep -q "discovered-from:bd-parent-1" "$FAKE_BD_LOG" || fail "two re-check items: bd create did not carry --deps discovered-from"
grep -q "Re-check capacity-substitute plan-review review (bd-parent-1)" "$FAKE_BD_LOG" || fail "two re-check items: unexpected bd create title: $(cat "$FAKE_BD_LOG")"

# The reviewer writes "None." (nothing to flag): no bead is filed.
CLAVAIN_BEAD_ID="bd-parent-2" \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\nNone.\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "None. re-check: expected review to succeed, got exit $rc"
[[ ! -s "$FAKE_BD_LOG" ]] || fail "None. re-check: expected no bd create call, got: $(cat "$FAKE_BD_LOG")"

echo "PASS: capacity-substitute plan reviews carry the re-check paragraph and file re-check beads for real items only"

# Opus producer, Fable out of quota: the walk reaches Astra (openai), a
# different lab than the producer (anthropic) — not a capacity substitute.
# No re-check paragraph, no sidecar, no bead, even though this is also a
# fallback-walk review.
FAKE_CODEX_MODE=success FAKE_CLAUDE_QUOTA="claude-fable-5-1" run_review claude-opus-5
[[ "$rc" == 0 ]] || fail "cross-lab (not substitute): expected review to degrade to Astra, got exit $rc"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-6-astra" ]] || fail "cross-lab (not substitute): expected the fallback gpt-6-astra, got: $(cat "$FAKE_CODEX_LOG")"
grep -q "capacity-substitute" "$FAKE_CLAUDE_PROMPT_LOG" 2>/dev/null && fail "cross-lab (not substitute): the Fable prompt unexpectedly carried the re-check paragraph"
[[ ! -f "$TMP_ROOT/answer.md.recheck.md" ]] || fail "cross-lab (not substitute): unexpectedly wrote a recheck sidecar"
[[ ! -s "$FAKE_BD_LOG" ]] || fail "cross-lab (not substitute): unexpectedly filed a bd create call"

echo "PASS: a different-lab fallback review is not treated as a capacity substitute"
