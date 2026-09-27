#!/usr/bin/env bash
# route-spawn.sh acceptance suite (mk-42j9.25 Phase 2a Task 2). Real Intercore
# resolver against the packaged policy, fake `bb` for the pool probe. No model
# calls and no thread spawns.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/scripts/route-spawn.sh"
command -v ic >/dev/null
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/failic" "$TMP_ROOT/receipts"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Fake bb: FAKE_POOL=ready (default) | claude-down | error.
cat > "$TMP_ROOT/bin/bb" <<'FAKE_BB'
#!/usr/bin/env bash
[[ "$*" == "pool status --json" ]] || { echo "unexpected bb call: $*" >&2; exit 64; }
case "${FAKE_POOL:-ready}" in
  error) echo "pool unreachable" >&2; exit 1 ;;
  claude-down) claude_status=exhausted ;;
  *) claude_status=ready ;;
esac
cat <<JSON
{"accepting":true,"accounts":[
 {"provider":"codex","enabled":true,"status":"ready"},
 {"provider":"claude","enabled":true,"status":"$claude_status"},
 {"provider":"claude","enabled":false,"status":"ready"}]}
JSON
FAKE_BB
chmod +x "$TMP_ROOT/bin/bb"
cat > "$TMP_ROOT/failic/ic" <<'FAKE_IC'
#!/usr/bin/env bash
echo '{"partial":true}'
exit 1
FAKE_IC
chmod +x "$TMP_ROOT/failic/ic"

export PATH="$TMP_ROOT/bin:$PATH"
export ROUTE_SPAWN_RECEIPT_DIR="$TMP_ROOT/receipts"
unset CLAVAIN_POLICY_PROFILE CLAVAIN_DECISION_CONTEXT CLAVAIN_ROUTING_POLICY

RC=0
OUT=""
run() {
  RC=0
  OUT="$(bash "$SCRIPT" "$@" 2>"$TMP_ROOT/stderr")" || RC=$?
}
expect() {
  local want_rc="$1" want_out="$2" label="$3"
  [[ "$RC" == "$want_rc" ]] || fail "$label: exit $RC, want $want_rc ($(cat "$TMP_ROOT/stderr"))"
  [[ "$OUT" == "$want_out" ]] || fail "$label: stdout '$OUT', want '$want_out'"
}
latest_receipt() {
  local f
  f="$(ls -t "$ROUTE_SPAWN_RECEIPT_DIR"/*.json 2>/dev/null | head -1)"
  [[ -n "$f" ]] || fail "no receipt written"
  cat "$f"
}

OPUS="claude-code claude-opus-5-5 medium"
SONNET="claude-code claude-sonnet-5 medium"

# --- The mk-42j9.5 table, by slug (15 rows) and by alias (10 dedicated ids).
for slug in aleph clavain autarch after-them bbops shadow-work quilan sylvesteops nartopo; do
  run --role coordination --project "$slug"
  expect 0 "$OPUS" "coordination --project $slug"
done
for slug in autosigil rakes uncrancher cujgel agmodb linsenkasten; do
  run --role coordination --project "$slug"
  expect 0 "$SONNET" "coordination --project $slug"
done
for pair in proj_dnrqkvnf5x:autarch proj_fsrj27djw2:after-them proj_2apc9fag87:after-them \
            proj_eh66ikerj2:shadow-work proj_ewcj55ndy5:nartopo; do
  run --role coordination --project "${pair%%:*}"
  expect 0 "$OPUS" "coordination alias ${pair%%:*} (${pair#*:})"
  jq -e --arg s "${pair#*:}" '.project == $s' <<< "$(latest_receipt)" >/dev/null \
    || fail "alias ${pair%%:*} must record slug ${pair#*:}"
done
for pair in proj_3ktdvx76vj:autosigil proj_sy6myvvmq2:rakes proj_94669ff46u:uncrancher \
            proj_qdsjncqfd4:cujgel proj_5wt5mmgska:agmodb proj_g4vgbq6jst:linsenkasten; do
  run --role coordination --project "${pair%%:*}"
  expect 0 "$SONNET" "coordination alias ${pair%%:*} (${pair#*:})"
done

# --- Usage errors: exit 2, empty stdout, no spawn tuple.
run --role coordination
expect 2 "" "coordination without --project"
run --role coordination --project proj_personal
expect 2 "" "coordination on the shared proj_personal"
run --role coordination --project no-such-project
expect 2 "" "coordination on an unknown project"
run --role lane --project clavain
expect 2 "" "lane without --lineage"
run --project clavain
expect 2 "" "missing --role"
run --role lane --lineage L1 --bogus
expect 2 "" "unknown flag"
run --role plan-review
expect 2 "" "plan-review without --producer-identity"
run --role validation
expect 2 "" "validation without --producer-identity"
run --role cross-lab-review
expect 2 "" "cross-lab-review without --producer-identity"

# --- Lane: the arm stub is control in Phase 2a, so lane resolves the
# status-quo tier and the receipt records the arm and lineage.
run --role lane --lineage coord-123 --project clavain
expect 0 "$OPUS" "lane control arm"
receipt="$(latest_receipt)"
jq -e '.role == "lane" and .arm == "control" and .lineage == "coord-123" and .route.profile_ref == "lane-status-quo"' <<< "$receipt" >/dev/null \
  || fail "lane receipt must record arm control, lineage and the lane-status-quo route"

# --- Finding 1: only role lane consults the arm. Coordination and governed
# roles ignore --lineage and are never re-routed.
run --role coordination --project autosigil --lineage coord-123
expect 0 "$SONNET" "coordination ignores --lineage"
jq -e '.arm == null and .route.requested_role == "coordination"' <<< "$(latest_receipt)" >/dev/null \
  || fail "coordination receipt must not carry an arm"
run --role validation --producer-identity claude-opus-5-5
base="$OUT"; [[ "$RC" == 0 ]] || fail "validation with producer must resolve ($(cat "$TMP_ROOT/stderr"))"
run --role validation --producer-identity claude-opus-5-5 --lineage coord-123
expect 0 "$base" "validation ignores --lineage"
jq -e '.arm == null and .route.requested_role == "validation" and .producer_identity == "claude-opus-5-5"' <<< "$(latest_receipt)" >/dev/null \
  || fail "validation receipt must keep its role, record the producer and carry no arm"
# Same-producer exclusion: an Opus producer never gets an Opus validator.
[[ "$base" != *claude-opus-5-5* ]] || fail "validation for an Opus producer must not resolve Opus: $base"
[[ "$base" == codex\ * ]] || fail "a Codex seat must map to the bb codex provider: $base"

# --- Finding 8 and campaign precedence.
printf '%s\n' '{"reasons":[],"rationale":"campaign","scope":"mk-ag2s"}' > "$TMP_ROOT/campaign.json"
cp "$TMP_ROOT/campaign.json" "$TMP_ROOT/campaign.orig.json"
RC=0; OUT="$(CLAVAIN_POLICY_PROFILE=ci-campaign-pilot bash "$SCRIPT" --role coordination --project clavain --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "campaign profile over a project coordination profile fails closed"
RC=0; OUT="$(CLAVAIN_POLICY_PROFILE=ci-campaign-pilot bash "$SCRIPT" --role coordination --project autosigil --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "campaign profile with a project that has no profile"
jq -e '.project == "autosigil" and .policy_profile == "ci-campaign-pilot" and .route.policy_profile == "ci-campaign-pilot"' <<< "$(latest_receipt)" >/dev/null \
  || fail "campaign receipt must record the project and the campaign profile"
RC=0; OUT="$(CLAVAIN_POLICY_PROFILE=ci-campaign-pilot bash "$SCRIPT" --role routine-execution --project clavain --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "claude-code claude-sonnet-5 high" "campaign keeps precedence for other roles"
jq -e '.project == "clavain" and .route.decision_context.scope == "mk-ag2s"' <<< "$(latest_receipt)" >/dev/null \
  || fail "campaign scope must be preserved for non-coordination roles"
cmp -s "$TMP_ROOT/campaign.json" "$TMP_ROOT/campaign.orig.json" || fail "the caller's context file must never be modified"

# A caller context whose scope contradicts the project profile fails closed.
run --role coordination --project clavain --context-file "$TMP_ROOT/campaign.json"
expect 3 "" "context scope conflicting with the project profile"
# CLAVAIN_DECISION_CONTEXT is honored when --context-file is absent.
RC=0; OUT="$(CLAVAIN_DECISION_CONTEXT="$TMP_ROOT/campaign.json" bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "CLAVAIN_DECISION_CONTEXT is the default context"

# --- Resolution failures: exit 3 with empty stdout.
RC=0; OUT="$(PATH="$TMP_ROOT/failic:$PATH" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "ic failure"
RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$TMP_ROOT/missing.yaml" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "missing policy"
printf 'dispatch: [\n' > "$TMP_ROOT/bad.yaml"
RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$TMP_ROOT/bad.yaml" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "unparseable policy"

# --- Pool probe: an exhausted Claude pool moves the spawn to Codex; an
# unreachable pool leaves fallbacks unevaluated but still resolves.
RC=0; OUT="$(FAKE_POOL=claude-down bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "codex gpt-5.6-sol medium" "coordination with the Claude pool exhausted"
jq -e '.fallbacks_evaluated == true and (.available_models | index("claude-opus-5-5") | not) and (.available_models | index("gpt-5.6-sol"))' <<< "$(latest_receipt)" >/dev/null \
  || fail "receipt must record the probed available_models"
RC=0; OUT="$(FAKE_POOL=error bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "coordination with the pool unreachable"
receipt="$(latest_receipt)"
jq -e '.fallbacks_evaluated == false and .available_models == null' <<< "$receipt" >/dev/null \
  || fail "an unreachable pool must be recorded as fallbacks not evaluated"
jq -e '.policy_hash == .route.policy_hash and (.policy_hash | length == 64) and .spawn == {provider: "claude-code", model: "claude-opus-5-5", reasoning_level: "medium"} and .project_input == "clavain" and .profile_source == "project"' <<< "$receipt" >/dev/null \
  || fail "receipt must carry policy hash, spawn tuple, project input and profile source"

echo "PASS: route-spawn"
