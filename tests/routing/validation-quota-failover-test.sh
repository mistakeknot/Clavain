#!/usr/bin/env bash
# mk-ji9m: pin how the review-side roles behave when one lab runs out of
# quota. plan-review-capacity-test.sh covers plan-review (and one
# cross-lab-review case); this drives --role validation and --role
# cross-lab-review through the real dispatch walk and asserts the two
# invariants the failover must keep:
#   - the producer's own model never reviews (reviewer independence), and
#   - a same-lab substitute reached after a capacity failure is recorded in the
#     receipt as capacity_substitute, so a later reader can see the review was
#     not cross-lab.
# These are pinning tests of behaviour that already holds; they do not add the
# failover, they stop it regressing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

command -v ic >/dev/null 2>&1 || { echo "SKIP: ic not on PATH" >&2; exit 0; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not on PATH" >&2; exit 0; }

TMP_ROOT="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work"
git -C "$TMP_ROOT/work" init -q
git -C "$TMP_ROOT/work" -c user.email=test@example.com -c user.name=test commit -q --allow-empty -m init

fail() { echo "FAIL: $1" >&2; exit 1; }

# Fake codex: usage-limit error unless FAKE_CODEX_MODE=success.
cat > "$TMP_ROOT/bin/codex" <<'FAKE_CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then echo "codex-cli 0.154.0"; exit 0; fi
model="" outfile=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "-m" ]] && model="${args[$((i+1))]:-}"
  [[ "${args[$i]}" == "-o" ]] && outfile="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CODEX_LOG"
if [[ "${FAKE_CODEX_MODE:-quota}" == success ]]; then
  [[ -z "$outfile" ]] || printf 'VERDICT: PASS\nCRITERION: none\n' > "$outfile"
  echo '{"type":"task_complete","last_agent_message":"VERDICT: PASS"}'
  exit 0
fi
echo '{"type":"task_complete","error":{"codex_error_info":"usage_limit_exceeded"}}'
FAKE_CODEX

# Fake claude: a model listed in FAKE_CLAUDE_QUOTA reports the subscription
# limit the way the CLI's stream-json does.
cat > "$TMP_ROOT/bin/claude" <<'FAKE_CLAUDE'
#!/usr/bin/env bash
model=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "--model" ]] && model="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CLAUDE_LOG"
cat >/dev/null
if [[ " ${FAKE_CLAUDE_QUOTA:-} " == *" $model "* ]]; then
  text="You've hit your weekly limit · resets Sep 26, 7pm (UTC)"
  jq -cn --arg t "$text" '{type:"assistant",message:{content:[{type:"text",text:$t}]},error:"rate_limit"}'
  jq -cn --arg t "$text" '{type:"result",subtype:"success",is_error:true,result:$t}'
  exit 1
fi
jq -cn '{type:"result",subtype:"success",is_error:false,result:"VERDICT: PASS\nCRITERION: none"}'
FAKE_CLAUDE
chmod +x "$TMP_ROOT/bin/codex" "$TMP_ROOT/bin/claude"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export FAKE_CLAUDE_LOG="$TMP_ROOT/claude.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_BB_DIRECT_POOL=0
export CLAVAIN_RECHECK_BEADS_DIR=""
export CLAVAIN_ROUTING_POLICY="$ROOT/config/routing.yaml"

CONTEXT_FILE="$TMP_ROOT/context.json"
printf '%s\n' '{"reasons":[],"rationale":"review-role quota failover pinning","domain":"routing policy","investigation_active":false}' > "$CONTEXT_FILE"

# run_review ROLE PRODUCER — leaves the exit code in $rc, stderr in $TMP_ROOT/err.
run_review() {
  local role="$1" producer="$2"
  : > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
  (cd "$TMP_ROOT/work" && ic init >/dev/null 2>&1) || true
  rc=0
  bash "$ROOT/scripts/dispatch.sh" --role "$role" --producer-identity "$producer" \
    --context-file "$CONTEXT_FILE" -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer.md" \
    "review the work" >/dev/null 2>"$TMP_ROOT/err" || rc=$?
}

never_reviewed_by() {
  local label="$1" model="$2"
  if grep -qx -- "$model" "$FAKE_CODEX_LOG" "$FAKE_CLAUDE_LOG" 2>/dev/null; then
    fail "$label: the producer's own model $model reviewed its work (codex: $(paste -sd' ' "$FAKE_CODEX_LOG"); claude: $(paste -sd' ' "$FAKE_CLAUDE_LOG"))"
  fi
}

# Most recent terminal receipt for this run's project directory.
latest_receipt() {
  (cd "$TMP_ROOT/work" && ic route list --json 2>/dev/null) |
    jq -c --arg dir "$TMP_ROOT/work" '
      [.[] | select(.project_dir == $dir)] | sort_by(.id) |
      [.[] | (.context_json | fromjson) | select(.state == "completed" or .state == "failed")] | .[-1] // empty'
}

for role in validation cross-lab-review; do
  # Claude-lab producer, healthy Codex: the review lands on the other lab, and
  # the receipt carries no capacity_substitute (nothing degraded).
  FAKE_CODEX_MODE=success run_review "$role" claude-sonnet-5-5
  [[ "$rc" == 0 ]] || fail "$role, Sonnet producer: expected success, got exit $rc: $(grep '^dispatch:' "$TMP_ROOT/err" | tail -3)"
  [[ -s "$FAKE_CODEX_LOG" ]] || fail "$role, Sonnet producer: expected the cross-lab (Codex) seat to review, claude: $(paste -sd' ' "$FAKE_CLAUDE_LOG")"
  never_reviewed_by "$role, Sonnet producer" claude-sonnet-5-5
  receipt="$(latest_receipt)"
  [[ "$(jq -r '.capacity_substitute // "none"' <<< "$receipt")" == none ]] \
    || fail "$role, Sonnet producer: a cross-lab review recorded a capacity_substitute: $receipt"

  # Same producer, Codex out of quota: the walk degrades to a Claude seat that
  # is not the producer's own model, and the receipt records the substitute.
  run_review "$role" claude-sonnet-5-5
  [[ "$rc" == 0 ]] || fail "$role, Sonnet producer, Codex out: expected a same-lab substitute, got exit $rc: $(grep '^dispatch:' "$TMP_ROOT/err" | tail -3)"
  [[ -s "$FAKE_CODEX_LOG" ]] || fail "$role, Sonnet producer, Codex out: the Codex seat was never tried first"
  [[ -s "$FAKE_CLAUDE_LOG" ]] || fail "$role, Sonnet producer, Codex out: no Claude substitute ran"
  never_reviewed_by "$role, Sonnet producer, Codex out" claude-sonnet-5-5
  receipt="$(latest_receipt)"
  [[ "$(jq -r '.capacity_substitute.failure_class // empty' <<< "$receipt")" == quota_exhausted ]] \
    || fail "$role, Sonnet producer, Codex out: capacity_substitute.failure_class not recorded: $receipt"

  # Codex-lab producer, Claude out of quota: the walk must not review with the
  # producer's own model even though nothing else is left.
  FAKE_CODEX_MODE=success FAKE_CLAUDE_QUOTA="claude-opus-5-5 claude-sonnet-5-5" run_review "$role" gpt-6.1-sol
  never_reviewed_by "$role, Sol producer, Claude out" gpt-6.1-sol
done

echo "PASS: validation and cross-lab-review keep reviewer independence and record capacity_substitute under quota failover"
