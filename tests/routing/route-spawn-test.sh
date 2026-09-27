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

# Fake bb: FAKE_POOL=ready (default) | claude-down | claude-held | codex-down |
# opus-weekly-rejected | not-accepting | hang | error. Every call is logged.
cat > "$TMP_ROOT/bin/bb" <<'FAKE_BB'
#!/usr/bin/env bash
[[ "$*" == "pool status --json" ]] || { echo "unexpected bb call: $*" >&2; exit 64; }
echo "$*" >> "${FAKE_BB_LOG:-/dev/null}"
claude_status=ready codex_status=ready accepting=true opus_weekly=null
case "${FAKE_POOL:-ready}" in
  error) echo "pool unreachable" >&2; exit 1 ;;
  hang) exec sleep 60 ;;
  claude-down) claude_status=exhausted ;;
  claude-held) claude_status=held ;;
  codex-down) codex_status=exhausted ;;
  opus-weekly-rejected) opus_weekly='{"status":"rejected","utilization":1}' ;;
  not-accepting) accepting=false ;;
esac
cat <<JSON
{"accepting":$accepting,"accounts":[
 {"provider":"codex","enabled":true,"status":"$codex_status","familyWeekly":{"fable":null,"sonnet":null,"opus":null,"haiku":null,"other":null}},
 {"provider":"claude","enabled":true,"status":"$claude_status","familyWeekly":{"fable":null,"sonnet":{"status":"allowed"},"opus":$opus_weekly,"haiku":null,"other":null}},
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
mkdir -p "$TMP_ROOT/hangic"
printf '#!/usr/bin/env bash\nexec sleep 60\n' > "$TMP_ROOT/hangic/ic"
chmod +x "$TMP_ROOT/hangic/ic"

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
  jq -e --arg s "${pair#*:}" '.project == $s' <<< "$(latest_receipt)" >/dev/null \
    || fail "alias ${pair%%:*} must record slug ${pair#*:}"
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


# --- Review round 1 (mk-42j9.25 Phase 2a) regressions.
# Option values that look like flags, and unreadable contexts, are usage errors.
run --role lane --lineage -x
expect 2 "" "option value starting with a dash"
run --role lane --lineage L1 --context-file "$TMP_ROOT/no-such-context.json"
expect 2 "" "missing context file"
printf 'not json\n' > "$TMP_ROOT/bad-context.json"
run --role lane --lineage L1 --context-file "$TMP_ROOT/bad-context.json"
expect 2 "" "non-JSON context file"

# The main backend is the host session; bb cannot spawn it.
run --role release-authority
expect 3 "" "release-authority resolves a main-backend seat"

# An empty or "default" CLAVAIN_POLICY_PROFILE is no campaign.
for value in "" default; do
  RC=0; OUT="$(CLAVAIN_POLICY_PROFILE="$value" bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 0 "$OPUS" "CLAVAIN_POLICY_PROFILE='$value' is unset"
done

# Pool states: held accounts still serve; a rejected weekly family is down;
# a pool that is not accepting leaves fallbacks unevaluated.
RC=0; OUT="$(FAKE_POOL=claude-held bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "held Claude accounts count as up"
RC=0; OUT="$(FAKE_POOL=opus-weekly-rejected bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "a rejected Opus weekly family excludes Opus seats"
grep -qi fallback "$TMP_ROOT/stderr" || fail "a fallback seat must be announced on stderr"
jq -e '(.available_models | index("claude-opus-5-5") | not) and (.available_models | index("claude-sonnet-5"))' <<< "$(latest_receipt)" >/dev/null \
  || fail "a rejected Opus family must drop only Opus models"
RC=0; OUT="$(FAKE_POOL=claude-down bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
grep -qi fallback "$TMP_ROOT/stderr" || fail "a provider change must be announced on stderr"
RC=0; OUT="$(FAKE_POOL=codex-down bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "coordination with the Codex pool exhausted"
jq -e '.fallbacks_evaluated == true and (.available_models | index("gpt-5.6-sol") | not) and (.available_models | index("claude-opus-5-5"))' <<< "$(latest_receipt)" >/dev/null \
  || fail "a Codex outage must drop Codex models only"
jq -e '[.available_models[] | select(. == "gpt-6-astra" or . == "kimi-code/k3")] == []' <<< "$(latest_receipt)" >/dev/null \
  || fail "main and unspawnable backends must not count as available"
RC=0; OUT="$(FAKE_POOL=not-accepting bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "pool not accepting"
jq -e '.fallbacks_evaluated == false and .available_models == null' <<< "$(latest_receipt)" >/dev/null \
  || fail "a pool that is not accepting must leave fallbacks unevaluated"

# A hanging pool probe is bounded and treated as not evaluated.
RC=0; OUT="$(FAKE_POOL=hang ROUTE_SPAWN_POOL_TIMEOUT=1 timeout 30 bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "hanging pool probe"
jq -e '.fallbacks_evaluated == false' <<< "$(latest_receipt)" >/dev/null || fail "a timed-out probe is not evaluated"
# A hanging resolver is bounded and fails closed.
RC=0; OUT="$(PATH="$TMP_ROOT/hangic:$PATH" ROUTE_SPAWN_IC_TIMEOUT=1 timeout 30 bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "hanging resolver"

# Governed roles keep dispatch-time capacity handling: no pool probe.
rm -f "$TMP_ROOT/bbcalls"
RC=0; OUT="$(FAKE_BB_LOG="$TMP_ROOT/bbcalls" bash "$SCRIPT" --role validation --producer-identity claude-opus-5-5 2>"$TMP_ROOT/stderr")" || RC=$?
[[ "$RC" == 0 ]] || fail "validation must resolve ($(cat "$TMP_ROOT/stderr"))"
[[ ! -s "$TMP_ROOT/bbcalls" ]] || fail "governed roles must not probe the pool"
RC=0; OUT="$(FAKE_BB_LOG="$TMP_ROOT/bbcalls" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
[[ -s "$TMP_ROOT/bbcalls" ]] || fail "lane must probe the pool"

# Caller available_models are canonicalized through model_aliases before the
# intersection: "sonnet" means claude-sonnet-5.
printf '%s\n' '{"reasons":[],"rationale":"caller capacity","available_models":["sonnet","gpt-5.6-sol"]}' > "$TMP_ROOT/avail.json"
run --role lane --lineage L1 --context-file "$TMP_ROOT/avail.json"
expect 0 "$SONNET" "caller available_models alias is canonicalized"

# A lane on an unknown project resolves but warns.
run --role lane --lineage L1 --project no-such-project
expect 0 "$OPUS" "lane on an unknown project"
grep -qi "unknown project" "$TMP_ROOT/stderr" || fail "an unknown lane project must warn on stderr"

# The policy must declare its project table explicitly.
python3 - "$ROOT/config/routing.yaml" "$TMP_ROOT/noprojects.yaml" <<'NOPROJ'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
cfg["reasoning"].pop("projects", None)
yaml.safe_dump(cfg, open(sys.argv[2], "w"))
NOPROJ
RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$TMP_ROOT/noprojects.yaml" bash "$SCRIPT" --role coordination --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "policy without reasoning.projects"

echo "PASS: route-spawn"
