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
# mk-hadt: bd filing only happens when $TMP_ROOT/work's own top level has a
# .beads — the baseline for every test below except the "no tracker
# resolved" block, which removes it again to reproduce the production shape.
mkdir -p "$TMP_ROOT/work/.beads"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Fake codex: every model reports the Codex usage-limit error unless
# FAKE_CODEX_MODE=success. --version answers FAKE_CODEX_VERSION (default new
# enough for every declared minimum_codex_version), so a test can simulate an
# old Codex CLI and exercise the insufficient_codex_version pre-run skip. On
# success, real codex writes its answer to the file named by -o directly (not
# to stdout — dispatch.sh passes -o "$OUTPUT"), so the fixture does too;
# otherwise OUTPUT stays empty and a future Codex substitute would misread as
# a missing re-check section.
cat > "$TMP_ROOT/bin/codex" <<'FAKE_CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "codex-cli ${FAKE_CODEX_VERSION:-0.154.0}"
  exit 0
fi
model="" outfile=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "-m" ]] && model="${args[$((i+1))]:-}"
  [[ "${args[$i]}" == "-o" ]] && outfile="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CODEX_LOG"
if [[ "${FAKE_CODEX_MODE:-quota}" == success ]]; then
  [[ -z "$outfile" ]] || printf '%s\n' "${FAKE_CODEX_ANSWER:-VERDICT: CLEAN}" > "$outfile"
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
# filing without touching the real tracker. FAKE_BD_MODE=fail still logs the
# call (bd was actually invoked with the right argv) but exits 1, so B3's
# loud-stderr-warning-never-fails-the-dispatch behavior can be checked. The
# success output "fake-42" is deliberately unambiguous under dispatch.sh's
# real id-extraction pattern (hooks/lib-sprint.sh's
# `match($0, /[A-Za-z]+-[a-z0-9]+/)`), which stops at the second `-` — a
# fixture id with more than one hyphen would silently truncate.
cat > "$TMP_ROOT/bin/bd" <<'FAKE_BD'
#!/usr/bin/env bash
{ printf '<<<BD-CALL>>>\n'; printf '%s\x1f' "$@"; printf '\n'; } >> "$FAKE_BD_LOG"
if [[ "${FAKE_BD_MODE:-}" == fail ]]; then
  echo "fake-bd: simulated failure" >&2
  exit 1
fi
echo "fake-42"
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

# Prints the context_json of the most recent terminal (completed/failed)
# `ic route record` receipt from this run's dispatch(es), so a test can
# assert on capacity_substitute/recheck_items/recheck_source the way a real
# receipt consumer would. `_record_role_routing_decision` runs `ic route
# record`/`ic route list` with cwd=$WORKDIR ("-C $TMP_ROOT/work" here); an
# unrecognized project directory like a throwaway mktemp resolves to a
# shared fallback store also used by OTHER concurrent test/integration runs
# on this machine (not a per-directory db) — --agent/--model/--limit are
# accepted but silently ignored by the installed `ic`, so filter client-side
# on project_dir (recorded from that same cwd) to isolate this run's own
# rows. One dispatch call writes a terminal record per attempted candidate
# (e.g. Astra's quota_exhausted, then the one that actually finished the
# review) — sort by row id (insertion order) and take the LAST terminal
# record to land on the outcome the caller actually saw.
latest_receipt() {
  (cd "$TMP_ROOT/work" && ic route list --json 2>/dev/null) |
    jq -c --arg dir "$TMP_ROOT/work" '
      [.[] | select(.project_dir == $dir)] | sort_by(.id) |
      [.[] | (.context_json | fromjson) | select(.state == "completed" or .state == "failed")] | .[-1] // empty'
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
receipt="$(latest_receipt)"
[[ -n "$receipt" ]] || fail "capacity substitute: no terminal ic route record receipt found for plan-review"
[[ "$(jq -r '.capacity_substitute.failure_class' <<< "$receipt")" == "quota_exhausted" ]] || fail "capacity substitute: receipt capacity_substitute.failure_class was not quota_exhausted: $receipt"
[[ "$(jq -r '.capacity_substitute.producer_lab' <<< "$receipt")" == "anthropic" ]] || fail "capacity substitute: receipt capacity_substitute.producer_lab was not anthropic: $receipt"
[[ "$(jq -r '.capacity_substitute.reviewer_lab' <<< "$receipt")" == "anthropic" ]] || fail "capacity substitute: receipt capacity_substitute.reviewer_lab was not anthropic: $receipt"
[[ "$(jq -r '.recheck_items' <<< "$receipt")" == "1" ]] || fail "capacity substitute: receipt recheck_items was not 1 for the fabricated item: $receipt"
[[ "$(jq -r '.recheck_source' <<< "$receipt")" == "missing" ]] || fail "capacity substitute: receipt recheck_source was not 'missing' for an absent heading: $receipt"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "fake-42" ]] || fail "capacity substitute: receipt recheck_bead was not the filed id: $receipt"

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
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_items' <<< "$receipt")" == "2" ]] || fail "two re-check items: receipt recheck_items was not 2: $receipt"
[[ "$(jq -r '.recheck_source' <<< "$receipt")" == "listed" ]] || fail "two re-check items: receipt recheck_source was not 'listed': $receipt"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "fake-42" ]] || fail "two re-check items: receipt recheck_bead was not the filed id: $receipt"

# CLAVAIN_RECHECK_BEADS=0: the sidecar is still written (items are not lost)
# but no bd create call is made.
CLAVAIN_BEAD_ID="bd-parent-1b" CLAVAIN_RECHECK_BEADS=0 \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n- confirmed nothing was executed\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "CLAVAIN_RECHECK_BEADS=0: expected review to succeed, got exit $rc"
[[ -f "$TMP_ROOT/answer.md.recheck.md" ]] || fail "CLAVAIN_RECHECK_BEADS=0: expected the sidecar to still be written"
grep -q "confirmed nothing was executed" "$TMP_ROOT/answer.md.recheck.md" || fail "CLAVAIN_RECHECK_BEADS=0: sidecar missing the item"
[[ ! -s "$FAKE_BD_LOG" ]] || fail "CLAVAIN_RECHECK_BEADS=0: expected no bd create call, got: $(cat "$FAKE_BD_LOG")"
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "null" ]] || fail "CLAVAIN_RECHECK_BEADS=0: receipt recheck_bead was not null: $receipt"

# A failing bd never fails the dispatch: exit 0, a loud stderr warning, and
# the sidecar is still there for a human to find.
FAKE_BD_MODE=fail \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n- confirmed nothing was executed\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "failing bd: expected the dispatch to still succeed, got exit $rc"
[[ -f "$TMP_ROOT/answer.md.recheck.md" ]] || fail "failing bd: expected the sidecar to still be written"
grep -qi "WARNING.*could not file the capacity-recheck bead" "$TMP_ROOT/err" || fail "failing bd: expected a loud stderr warning: $(tail -5 "$TMP_ROOT/err")"
[[ -s "$FAKE_BD_LOG" ]] || fail "failing bd: expected bd to have actually been invoked (and logged) before failing"
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "null" ]] || fail "failing bd: receipt recheck_bead was not null: $receipt"

# The reviewer writes the heading with no items under it (not "None."): B3
# treats an empty section the same as a missing one — the whole review still
# needs a re-check, not a silent "nothing to flag".
CLAVAIN_BEAD_ID="bd-parent-2b" \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "empty re-check section: expected review to succeed, got exit $rc"
grep -q "reviewer did not list re-check items" "$TMP_ROOT/answer.md.recheck.md" || fail "empty re-check section: expected the fabricated whole-review item, got: $(cat "$TMP_ROOT/answer.md.recheck.md" 2>/dev/null)"
[[ "$(grep -c '<<<BD-CALL>>>' "$FAKE_BD_LOG")" == 1 ]] || fail "empty re-check section: expected exactly one bd create call, got: $(cat "$FAKE_BD_LOG")"
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_source' <<< "$receipt")" == "missing" ]] || fail "empty re-check section: receipt recheck_source was not 'missing': $receipt"

# The reviewer writes "None." (nothing to flag): no bead is filed.
CLAVAIN_BEAD_ID="bd-parent-2" \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\nNone.\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "None. re-check: expected review to succeed, got exit $rc"
[[ ! -s "$FAKE_BD_LOG" ]] || fail "None. re-check: expected no bd create call, got: $(cat "$FAKE_BD_LOG")"
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_items' <<< "$receipt")" == "0" ]] || fail "None. re-check: receipt recheck_items was not 0: $receipt"
[[ "$(jq -r '.recheck_source' <<< "$receipt")" == "none" ]] || fail "None. re-check: receipt recheck_source was not 'none': $receipt"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "null" ]] || fail "None. re-check: receipt recheck_bead was not null: $receipt"

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
receipt="$(latest_receipt)"
[[ "$(jq -r '.capacity_substitute' <<< "$receipt")" == "null" ]] || fail "cross-lab (not substitute): receipt capacity_substitute was not null: $receipt"
[[ "$(jq -r '.recheck_items' <<< "$receipt")" == "null" ]] || fail "cross-lab (not substitute): receipt recheck_items was not null: $receipt"
[[ "$(jq -r '.recheck_source' <<< "$receipt")" == "null" ]] || fail "cross-lab (not substitute): receipt recheck_source was not null: $receipt"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "null" ]] || fail "cross-lab (not substitute): receipt recheck_bead was not null: $receipt"

echo "PASS: a different-lab fallback review is not treated as a capacity substitute"

# review-fable is excluded pre-walk with fallback_reason=producer_model_conflict
# (producer is also claude-fable-5-1); review-astra is then skipped pre-run
# via insufficient_codex_version (an old Codex CLI, never actually invoked
# with a real prompt); the walk lands on review-opus (claude-opus-5), same
# lab as the producer. Neither exclusion is a real capacity-class failure, so
# capacity_failure_class stays empty and this must NOT be flagged as a
# capacity substitute even though it is same-lab and reached after a walk.
FAKE_CODEX_VERSION="0.100.0" run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "producer_model_conflict only: expected review to succeed, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ ! -s "$FAKE_CODEX_LOG" ]] || fail "producer_model_conflict only: review-astra should never have been actually attempted, got: $(cat "$FAKE_CODEX_LOG")"
[[ "$(cat "$FAKE_CLAUDE_LOG")" == "claude-opus-5" ]] || fail "producer_model_conflict only: expected claude-opus-5 to review, got: $(cat "$FAKE_CLAUDE_LOG")"
grep -q "requires Codex >=" "$TMP_ROOT/err" || fail "producer_model_conflict only: expected the insufficient_codex_version pre-run skip recorded on stderr: $(cat "$TMP_ROOT/err")"
never_reviewed_by "producer_model_conflict only" claude-fable-5-1
grep -q "capacity-substitute" "$FAKE_CLAUDE_PROMPT_LOG" 2>/dev/null && fail "producer_model_conflict only: the Opus prompt unexpectedly carried the re-check paragraph"
[[ ! -f "$TMP_ROOT/answer.md.recheck.md" ]] || fail "producer_model_conflict only: unexpectedly wrote a recheck sidecar"
[[ ! -s "$FAKE_BD_LOG" ]] || fail "producer_model_conflict only: unexpectedly filed a bd create call"
receipt="$(latest_receipt)"
[[ "$(jq -r '.capacity_substitute' <<< "$receipt")" == "null" ]] || fail "producer_model_conflict only: receipt capacity_substitute was not null: $receipt"

echo "PASS: a pre-walk producer_model_conflict exclusion plus a pre-run version skip is not a capacity substitute"

# --- mk-hadt: bd -C $WORKDIR must never resolve a tracker above the repo --
#
# Production incident: this branch's own capacity-recheck filing ran
# `bd -C $WORKDIR` from a worktree with no `.beads` of its own, and bd's own
# upward directory walk landed on an unrelated tracker one level up
# (/home/mk/projects/.beads, sitting above the real
# /home/mk/projects/.clavain-capreview worktree). Reproduce that shape:
# $TMP_ROOT/work loses the `.beads` every prior block relied on, and a decoy
# `.beads` sits at $TMP_ROOT itself — one level above work, exactly like the
# real incident's unrelated tracker sat one level above the worktree. Filing
# must refuse rather than reach the decoy.
rm -rf "$TMP_ROOT/work/.beads"
mkdir -p "$TMP_ROOT/.beads"
CLAVAIN_BEAD_ID="bd-parent-3" \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n- would have filed into the wrong tracker if bd walked up\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "no tracker resolved: expected review to still succeed, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ -f "$TMP_ROOT/answer.md.recheck.md" ]] || fail "no tracker resolved: expected the sidecar to still be written"
grep -q "would have filed" "$TMP_ROOT/answer.md.recheck.md" || fail "no tracker resolved: sidecar missing the item"
[[ ! -s "$FAKE_BD_LOG" ]] || fail "no tracker resolved: expected no bd call at all (not even to the decoy parent tracker), got: $(cat "$FAKE_BD_LOG")"
grep -qi "no beads tracker resolved" "$TMP_ROOT/err" || fail "no tracker resolved: expected a loud stderr warning: $(tail -5 "$TMP_ROOT/err")"
grep -q "CLAVAIN_RECHECK_BEADS_DIR" "$TMP_ROOT/err" || fail "no tracker resolved: expected the warning to name the override: $(tail -5 "$TMP_ROOT/err")"
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "null" ]] || fail "no tracker resolved: receipt recheck_bead was not null: $receipt"

# CLAVAIN_RECHECK_BEADS_DIR overrides tracker resolution outright: used even
# though $TMP_ROOT/work still has no .beads (from the block above) and a
# decoy .beads still sits at $TMP_ROOT/, one level up.
mkdir -p "$TMP_ROOT/override-tracker/.beads"
CLAVAIN_BEAD_ID="bd-parent-4" CLAVAIN_RECHECK_BEADS_DIR="$TMP_ROOT/override-tracker" \
  FAKE_CLAUDE_ANSWER="$(printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n- confirmed the override directory was used\n')" \
  run_review claude-fable-5-1
[[ "$rc" == 0 ]] || fail "CLAVAIN_RECHECK_BEADS_DIR: expected review to succeed, got exit $rc: $(tail -5 "$TMP_ROOT/err")"
[[ "$(grep -c '<<<BD-CALL>>>' "$FAKE_BD_LOG")" == 1 ]] || fail "CLAVAIN_RECHECK_BEADS_DIR: expected exactly one bd create call, got: $(cat "$FAKE_BD_LOG")"
grep -qF "$TMP_ROOT/override-tracker" "$FAKE_BD_LOG" || fail "CLAVAIN_RECHECK_BEADS_DIR: expected bd to be invoked with the override as -C, got: $(cat "$FAKE_BD_LOG")"
receipt="$(latest_receipt)"
[[ "$(jq -r '.recheck_bead' <<< "$receipt")" == "fake-42" ]] || fail "CLAVAIN_RECHECK_BEADS_DIR: receipt recheck_bead was not the filed id: $receipt"

# Restore the baseline .beads for cleanliness/order-independence, in case a
# future block is appended after this one.
rm -rf "$TMP_ROOT/.beads" "$TMP_ROOT/override-tracker"
mkdir -p "$TMP_ROOT/work/.beads"

echo "PASS: capacity-recheck bead filing never resolves a tracker above the repo root, and CLAVAIN_RECHECK_BEADS_DIR overrides resolution outright"
