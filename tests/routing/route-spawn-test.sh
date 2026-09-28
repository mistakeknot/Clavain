#!/usr/bin/env bash
# route-spawn.sh acceptance suite (mk-42j9.25 Phase 2a Task 2; project-profile
# resolution updated for mk-h73i, which emptied reasoning.project_profiles).
# Real Intercore resolver against the packaged policy, fake `bb` for the pool
# probe. No model calls and no thread spawns.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/scripts/route-spawn.sh"
command -v ic >/dev/null
TMP_ROOT="$(mktemp -d)"
cleanup() {
  local f
  for f in "$TMP_ROOT/gc.pid" "$TMP_ROOT/setsid.pid"; do
    if [[ -s "$f" ]]; then kill "$(cat "$f")" 2>/dev/null || true; fi
  done
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/failic" "$TMP_ROOT/receipts"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Fake bb: FAKE_POOL=ready (default) | claude-down | claude-held | codex-down |
# all-down | opus-weekly-rejected | opus-weekly-warning | opus-weekly-below |
# opus-weekly-expired | claude-mixed | routing-off | child-host |
# not-accepting | hang | error. `pool config --json` reports
# FAKE_THRESHOLD (bb's default 0.98). Every call is logged. resetAt is in
# epoch milliseconds, as bb reports it.
cat > "$TMP_ROOT/bin/bb" <<'FAKE_BB'
#!/usr/bin/env bash
echo "$*" >> "${FAKE_BB_LOG:-/dev/null}"
if [[ "$*" == "pool config --json" ]]; then
  [[ "${FAKE_POOL:-}" == error ]] && exit 1
  printf '{"ok":true,"config":{"switchThreshold":%s,"parentMode":"proxy"}}\n' "${FAKE_THRESHOLD:-0.98}"
  exit 0
fi
[[ "$*" == "pool status --json" ]] || { echo "unexpected bb call: $*" >&2; exit 64; }
FUTURE=4102444800000 PAST=1000
claude_status=ready codex_status=ready accepting=true opus_weekly=null
second_claude='{"provider":"claude","enabled":false,"status":"ready"}'
routing='{"claude":true,"codex":true}' parent=null
case "${FAKE_POOL:-ready}" in
  error) echo "pool unreachable" >&2; exit 1 ;;
  hang) sleep 60; exit 0 ;;
  claude-down) claude_status=exhausted ;;
  claude-held) claude_status=held ;;
  codex-down) codex_status=exhausted ;;
  all-down) claude_status=exhausted codex_status=exhausted ;;
  opus-weekly-rejected) opus_weekly="{\"status\":\"rejected\",\"utilization\":1,\"resetAt\":$FUTURE}" ;;
  opus-weekly-warning) opus_weekly="{\"status\":\"allowed_warning\",\"utilization\":1.0,\"resetAt\":$FUTURE}" ;;
  opus-weekly-below) opus_weekly="{\"status\":\"allowed_warning\",\"utilization\":0.9,\"resetAt\":$FUTURE}" ;;
  opus-weekly-expired) opus_weekly="{\"status\":\"rejected\",\"utilization\":1,\"resetAt\":$PAST}" ;;
  claude-mixed)
    opus_weekly="{\"status\":\"rejected\",\"utilization\":1,\"resetAt\":$FUTURE}"
    second_claude='{"provider":"claude","enabled":true,"status":"ready","familyWeekly":{"sonnet":null,"opus":{"status":"allowed","utilization":0.2,"resetAt":null}}}' ;;
  routing-off) claude_status=exhausted routing='{"claude":false,"codex":true}' ;;
  child-host) claude_status=exhausted parent='{"hubUrl":"https://hub.example"}' ;;
  not-accepting) accepting=false ;;
esac
cat <<JSON
{"accepting":$accepting,"routing":$routing,"parent":$parent,"accounts":[
 {"provider":"codex","enabled":true,"status":"$codex_status","familyWeekly":{"fable":null,"sonnet":null,"opus":null,"haiku":null,"other":null}},
 {"provider":"claude","enabled":true,"status":"$claude_status","familyWeekly":{"fable":null,"sonnet":{"status":"allowed"},"opus":$opus_weekly,"haiku":null,"other":null}},
 $second_claude,
 {"provider":"kimi","enabled":true,"status":"ready"},
 {"provider":"main","enabled":true,"status":"ready"}]}
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
# Not `exec`: the grandchild sleep must die with the timed-out resolver (N5).
printf '#!/usr/bin/env bash\nsleep 60 &\necho $! > "%s/gc.pid"\nwait\n' "$TMP_ROOT" > "$TMP_ROOT/hangic/ic"
chmod +x "$TMP_ROOT/hangic/ic"
# P2: a descendant that leaves the session escapes killpg; it holds our stdout
# and the caller's stderr until it exits.
mkdir -p "$TMP_ROOT/setsidic"
printf '#!/usr/bin/env bash\nsetsid sleep 30 &\necho $! > "%s/setsid.pid"\nsleep 60\n' "$TMP_ROOT" > "$TMP_ROOT/setsidic/ic"
chmod +x "$TMP_ROOT/setsidic/ic"

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
ASTRA="codex gpt-6-astra medium"

# --- mk-h73i: all 15 table slugs resolve coordinator-seat to the fleet
# Sonnet default. No project carries a coordinator-seat override any more —
# this reverses the mk-42j9.25/mk-42j9.5 nine-Opus/six-Sonnet split that used
# to live here.
for slug in aleph clavain autarch after-them bbops shadow-work quilan sylvesteops nartopo \
            autosigil rakes uncrancher cujgel agmodb linsenkasten; do
  run --role coordinator-seat --project "$slug"
  expect 0 "$SONNET" "coordinator-seat --project $slug"
done
for pair in proj_dnrqkvnf5x:autarch proj_fsrj27djw2:after-them proj_2apc9fag87:after-them \
            proj_eh66ikerj2:shadow-work proj_ewcj55ndy5:nartopo \
            proj_3ktdvx76vj:autosigil proj_sy6myvvmq2:rakes proj_94669ff46u:uncrancher \
            proj_qdsjncqfd4:cujgel proj_5wt5mmgska:agmodb proj_g4vgbq6jst:linsenkasten; do
  run --role coordinator-seat --project "${pair%%:*}"
  expect 0 "$SONNET" "coordinator-seat alias ${pair%%:*} (${pair#*:})"
  jq -e --arg s "${pair#*:}" '.project == $s' <<< "$(latest_receipt)" >/dev/null \
    || fail "alias ${pair%%:*} must record slug ${pair#*:}"
done

# --- Usage errors: exit 2, empty stdout, no spawn tuple.
# coordination is the relay role for dispatch.sh; a coordinator thread's own
# seat is coordinator-seat, and route-spawn says so.
run --role coordination --project clavain
expect 2 "" "relay role coordination is not a spawn role"
grep -q "coordinator-seat" "$TMP_ROOT/stderr" || fail "rejecting coordination must point at coordinator-seat"
run --role coordinator-seat
expect 2 "" "coordination without --project"
run --role coordinator-seat --project proj_personal
expect 2 "" "coordination on the shared proj_personal"
run --role coordinator-seat --project no-such-project
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
run --role coordinator-seat --project autosigil --lineage coord-123
expect 0 "$SONNET" "coordination ignores --lineage"
jq -e '.arm == null and .route.requested_role == "coordinator-seat"' <<< "$(latest_receipt)" >/dev/null \
  || fail "coordinator-seat receipt must not carry an arm"
run --role validation --producer-identity claude-opus-5-5
base="$OUT"; [[ "$RC" == 0 ]] || fail "validation with producer must resolve ($(cat "$TMP_ROOT/stderr"))"
run --role validation --producer-identity claude-opus-5-5 --lineage coord-123
expect 0 "$base" "validation ignores --lineage"
jq -e '.arm == null and .route.requested_role == "validation" and .producer_identity == "claude-opus-5-5"' <<< "$(latest_receipt)" >/dev/null \
  || fail "validation receipt must keep its role, record the producer and carry no arm"
# Same-producer exclusion: an Opus producer never gets an Opus validator.
[[ "$base" != *claude-opus-5-5* ]] || fail "validation for an Opus producer must not resolve Opus: $base"
[[ "$base" == codex\ * ]] || fail "a Codex seat must map to the bb codex provider: $base"

# A synthetic fixture re-adding a coordinator-seat override for "clavain"
# only, so the campaign/context-scope-conflict paths that depend on a live
# project profile stay covered even though the packaged policy's
# project_profiles is now empty (mk-h73i).
python3 - "$ROOT/config/routing.yaml" "$TMP_ROOT/clavainprofile.yaml" <<'CLAVAINPROFILE'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
cfg["reasoning"]["project_profiles"]["clavain"] = "project-clavain"
cfg["reasoning"]["profiles"]["project-clavain"] = {
    "scope": "project:clavain", "roles": {"coordinator-seat": "coordinator-seat-opus"}}
yaml.safe_dump(cfg, open(sys.argv[2], "w"))
CLAVAINPROFILE
CLAVAINPOLICY="$TMP_ROOT/clavainprofile.yaml"

# --- Finding 8 and campaign precedence.
printf '%s\n' '{"reasons":[],"rationale":"campaign","scope":"mk-ag2s"}' > "$TMP_ROOT/campaign.json"
cp "$TMP_ROOT/campaign.json" "$TMP_ROOT/campaign.orig.json"
RC=0; OUT="$(CLAVAIN_POLICY_PROFILE=ci-campaign-pilot CLAVAIN_ROUTING_POLICY="$CLAVAINPOLICY" bash "$SCRIPT" --role coordinator-seat --project clavain --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "campaign profile over a project coordination profile fails closed"
RC=0; OUT="$(CLAVAIN_POLICY_PROFILE=ci-campaign-pilot bash "$SCRIPT" --role coordinator-seat --project autosigil --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "campaign profile with a project that has no profile"
jq -e '.project == "autosigil" and .policy_profile == "ci-campaign-pilot" and .route.policy_profile == "ci-campaign-pilot"' <<< "$(latest_receipt)" >/dev/null \
  || fail "campaign receipt must record the project and the campaign profile"
RC=0; OUT="$(CLAVAIN_POLICY_PROFILE=ci-campaign-pilot bash "$SCRIPT" --role routine-execution --project clavain --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "claude-code claude-sonnet-5 high" "campaign keeps precedence for other roles"
jq -e '.project == "clavain" and .route.decision_context.scope == "mk-ag2s"' <<< "$(latest_receipt)" >/dev/null \
  || fail "campaign scope must be preserved for non-coordination roles"
cmp -s "$TMP_ROOT/campaign.json" "$TMP_ROOT/campaign.orig.json" || fail "the caller's context file must never be modified"

# A caller context whose scope contradicts the project profile fails closed.
RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$CLAVAINPOLICY" bash "$SCRIPT" --role coordinator-seat --project clavain --context-file "$TMP_ROOT/campaign.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "context scope conflicting with the project profile"
# CLAVAIN_DECISION_CONTEXT is honored when --context-file is absent.
RC=0; OUT="$(CLAVAIN_DECISION_CONTEXT="$TMP_ROOT/campaign.json" CLAVAIN_ROUTING_POLICY="$CLAVAINPOLICY" bash "$SCRIPT" --role coordinator-seat --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
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
# unreachable pool leaves fallbacks unevaluated but still resolves. Uses lane
# (Opus 5.5 via lane-status-quo, same fallback shape as the retired
# coordinator-seat-opus) since coordinator-seat now defaults to Sonnet for
# every project (mk-h73i) and this section exercises Opus-headed fallback.
RC=0; OUT="$(FAKE_POOL=claude-down bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$ASTRA" "lane with the Claude pool exhausted"
jq -e '.fallbacks_evaluated == true and (.available_models | index("claude-opus-5-5") | not) and (.available_models | index("gpt-6-astra"))' <<< "$(latest_receipt)" >/dev/null \
  || fail "receipt must record the probed available_models"
RC=0; OUT="$(FAKE_POOL=error bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "lane with the pool unreachable"
receipt="$(latest_receipt)"
jq -e '.fallbacks_evaluated == false and .available_models == null' <<< "$receipt" >/dev/null \
  || fail "an unreachable pool must be recorded as fallbacks not evaluated"
jq -e '.policy_hash == .route.policy_hash and (.policy_hash | length == 64) and .spawn == {provider: "claude-code", model: "claude-opus-5-5", reasoning_level: "medium"} and .role == "lane" and .profile_source == "none"' <<< "$receipt" >/dev/null \
  || fail "receipt must carry policy hash, spawn tuple, role and profile source"


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

# An empty or "default" CLAVAIN_POLICY_PROFILE is no campaign — exercised
# against the clavainprofile.yaml fixture so this still tests that an unset
# campaign profile doesn't disable a live project profile (the packaged
# policy has no project profile of its own to disable any more).
for value in "" default; do
  RC=0; OUT="$(CLAVAIN_POLICY_PROFILE="$value" CLAVAIN_ROUTING_POLICY="$CLAVAINPOLICY" bash "$SCRIPT" --role coordinator-seat --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 0 "$OPUS" "CLAVAIN_POLICY_PROFILE='$value' is unset"
done

# Pool states: held accounts still serve; a rejected weekly family is down;
# a pool that is not accepting leaves fallbacks unevaluated. Uses lane, same
# reason as the pool-probe section above.
RC=0; OUT="$(FAKE_POOL=claude-held bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "held Claude accounts count as up"
RC=0; OUT="$(FAKE_POOL=opus-weekly-rejected bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "a rejected Opus weekly family excludes Opus seats"
grep -q "fallback from .* to " "$TMP_ROOT/stderr" || fail "a fallback seat must be announced on stderr"
jq -e '(.available_models | index("claude-opus-5-5") | not) and (.available_models | index("claude-sonnet-5"))' <<< "$(latest_receipt)" >/dev/null \
  || fail "a rejected Opus family must drop only Opus models"
RC=0; OUT="$(FAKE_POOL=claude-down bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$ASTRA" "lane with the Claude pool exhausted"
grep -q "fallback from .* to " "$TMP_ROOT/stderr" || fail "a provider change must be announced on stderr"
RC=0; OUT="$(FAKE_POOL=codex-down bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "lane with the Codex pool exhausted"
jq -e '.fallbacks_evaluated == true and (.available_models | index("gpt-6-astra") | not) and (.available_models | index("claude-opus-5-5"))' <<< "$(latest_receipt)" >/dev/null \
  || fail "a Codex outage must drop Codex models only"
# The fake pool has ready kimi and main accounts; bb still cannot spawn them.
RC=0; OUT="$(bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
jq -e '[.available_models[] | select(. == "kimi-code/k3")] == []' <<< "$(latest_receipt)" >/dev/null \
  || fail "main and unspawnable backends must not count as available"
RC=0; OUT="$(FAKE_POOL=not-accepting bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "pool not accepting"
jq -e '.fallbacks_evaluated == false and .available_models == null' <<< "$(latest_receipt)" >/dev/null \
  || fail "a pool that is not accepting must leave fallbacks unevaluated"

# A hanging pool probe is bounded and treated as not evaluated.
RC=0; OUT="$(FAKE_POOL=hang ROUTE_SPAWN_POOL_TIMEOUT=1 timeout 30 bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
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
RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$TMP_ROOT/noprojects.yaml" bash "$SCRIPT" --role coordinator-seat --project clavain 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "policy without reasoning.projects"

# --- Rule-6 round (coordinator ruling 2026-09-27).
# mk ruling: never gpt-5.6-sol. With Claude exhausted every spawn role lands
# on gpt-6-astra medium; with no eligible seat it fails closed.
for args in "--role lane --lineage L1" "--role main-session" "--role coordinator-seat --project autosigil" "--role coordinator-seat --project clavain"; do
  # shellcheck disable=SC2086
  RC=0; OUT="$(FAKE_POOL=claude-down bash "$SCRIPT" $args 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 0 "$ASTRA" "Claude exhausted: $args"
  # shellcheck disable=SC2086
  RC=0; OUT="$(FAKE_POOL=all-down bash "$SCRIPT" $args 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 3 "" "no eligible seat: $args"
done
run --role main-session
expect 0 "$SONNET" "main-session default"
run --role coordinator-seat --project autosigil
jq -e '.route.profile_ref == "coordinator-seat-sonnet" and .profile_source == "none"' <<< "$(latest_receipt)" >/dev/null \
  || fail "an unprofiled coordinator seat resolves coordinator-seat-sonnet"
# mk-h73i: project_profiles is now empty, so every project resolves
# coordinator-seat unprofiled, including the former Opus slugs like clavain.
run --role coordinator-seat --project clavain
jq -e '.route.profile_ref == "coordinator-seat-sonnet" and .profile_source == "none"' <<< "$(latest_receipt)" >/dev/null \
  || fail "clavain has no project_profiles entry any more; coordinator-seat resolves coordinator-seat-sonnet"

# Defense in depth: even a policy whose spawn chain reaches Sol fails closed
# rather than spawning it.
python3 - "$ROOT/config/routing.yaml" "$TMP_ROOT/solchain.yaml" <<'SOLCHAIN'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
tiers = cfg["dispatch"]["tiers"]
tiers["spawn-sol-test"] = {"role": "main-session", "backend": "codex", "model": "gpt-5.6-sol",
                           "reasoning_effort": "medium", "service_tier": "standard"}
tiers["main-sonnet"]["fallbacks"] = ["spawn-sol-test"]
tiers["coordinator-seat-sonnet"]["fallbacks"] = ["spawn-sol-test"]
yaml.safe_dump(cfg, open(sys.argv[2], "w"))
SOLCHAIN
for args in "main-session" "lane --lineage L1" "coordinator-seat --project autosigil" "coordinator-seat --project clavain"; do
  # shellcheck disable=SC2086
  RC=0; OUT="$(FAKE_POOL=claude-down CLAVAIN_ROUTING_POLICY="$TMP_ROOT/solchain.yaml" bash "$SCRIPT" --role $args 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 3 "" "spawn role $args resolving gpt-5.6-sol fails closed"
  grep -q "gpt-5.6-sol" "$TMP_ROOT/stderr" || fail "the Sol refusal for $args must name the model"
done

# mk ruling 2026-09-27 covers every role route-spawn prints: governed roles
# never print gpt-5.6-sol under the packaged policy (GPT-6 Sol is allowed)...
for args in "validation --producer-identity claude-opus-5-5" "cross-lab-review --producer-identity claude-opus-5-5" \
    routine-execution planning scout release-preparation; do
  # shellcheck disable=SC2086
  run --role $args
  expect 0 "$OUT" "governed role $args resolves under the packaged policy"
  [[ -n "$OUT" && "$OUT" != *gpt-5.6* ]] || fail "governed role $args must not print gpt-5.6-sol: '$OUT'"
done
# ...and a policy that would give one gpt-5.6-sol, by any spelling, fails closed.
python3 - "$ROOT/config/routing.yaml" "$TMP_ROOT" <<'GOVSOL'
import sys, yaml, copy
base = yaml.safe_load(open(sys.argv[1]))
for name, model, aliases in (("gov-sol", "gpt-5.6-sol", {}), ("gov-alias", "gpt-5.6", {}),
                             ("gov-upper", "GPT-5.6-SOL", {}), ("gov-custom-alias", "old-sol", {"old-sol": "gpt-5.6-sol"})):
    cfg = copy.deepcopy(base)
    d = cfg["dispatch"]
    d["tiers"][d["roles"]["routine-execution"]]["model"] = model
    d.setdefault("model_aliases", {}).update(aliases)
    yaml.safe_dump(cfg, open(f"{sys.argv[2]}/{name}.yaml", "w"))
GOVSOL
for bad in gov-sol gov-alias gov-upper gov-custom-alias; do
  RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$TMP_ROOT/$bad.yaml" bash "$SCRIPT" --role routine-execution 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 3 "" "governed role resolving $bad fails closed"
  grep -q "gpt-5.6-sol" "$TMP_ROOT/stderr" || fail "the Sol refusal ($bad) must name gpt-5.6-sol"
done

# The refusal canonicalizes whatever ic returns: model_aliases to a fixed point
# (a cycle fails closed), suffixed or prefixed spellings, and both
# profile.model and profile.model_identity. A canned ic returns FAKE_MODEL and
# FAKE_IDENTITY; the policy supplies the aliases.
mkdir -p "$TMP_ROOT/cannedic"
cat > "$TMP_ROOT/cannedic/ic" <<'FAKE_IC'
#!/usr/bin/env bash
printf '{"profile":{"backend":"codex","model":"%s","model_identity":"%s","reasoning_effort":"medium"},"profile_ref":"canned","policy_hash":"%064d","fallback_reason":""}\n' \
  "$FAKE_MODEL" "${FAKE_IDENTITY:-$FAKE_MODEL}" 0
FAKE_IC
chmod +x "$TMP_ROOT/cannedic/ic"
python3 - "$ROOT/config/routing.yaml" "$TMP_ROOT/aliases.yaml" <<'ALIASES'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
cfg["dispatch"].setdefault("model_aliases", {}).update({
    "chain-a": "chain-b", "chain-b": "chain-c", "chain-c": "gpt-5.6-sol",
    "loop-a": "loop-b", "loop-b": "loop-a", "fine-a": "gpt-6-sol"})
yaml.safe_dump(cfg, open(sys.argv[2], "w"))
ALIASES
canned() {
  RC=0
  OUT="$(PATH="$TMP_ROOT/cannedic:$PATH" CLAVAIN_ROUTING_POLICY="$TMP_ROOT/aliases.yaml" \
    FAKE_MODEL="$1" FAKE_IDENTITY="$2" bash "$SCRIPT" --role routine-execution 2>"$TMP_ROOT/stderr")" || RC=$?
}
for pair in "chain-a chain-a" "gpt-5.6-sol-high gpt-5.6-sol-high" "GPT-5.6-SOL@high GPT-5.6-SOL@high" \
    "openai/gpt-5.6-sol openai/gpt-5.6-sol" "gpt-6-astra gpt-5.6-sol" "gpt-5.6-sol gpt-6-astra" "gpt-6-astra chain-b"; do
  read -r model identity <<<"$pair"
  canned "$model" "$identity"
  expect 3 "" "ic returning model=$model identity=$identity is refused"
  grep -q "gpt-5.6-sol" "$TMP_ROOT/stderr" || fail "the refusal of $pair must name gpt-5.6-sol"
done
canned loop-a loop-a
expect 3 "" "an alias cycle fails closed"
grep -qi "cycle" "$TMP_ROOT/stderr" || fail "an alias cycle must be reported as a cycle"
for pair in "gpt-6-sol gpt-6-sol" "gpt-6-sol gpt-6-sol-high" "fine-a fine-a"; do
  read -r model identity <<<"$pair"
  canned "$model" "$identity"
  expect 0 "codex $identity medium" "GPT-6 Sol ($pair) is allowed"
done

# N1: family exhaustion mirrors bb's activeWindow: resetAt null or future, and
# rejected or utilization >= the pool switchThreshold. Uses lane, same reason
# as the pool-probe sections above.
RC=0; OUT="$(FAKE_POOL=opus-weekly-warning bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "Opus at utilization 1.0 (allowed_warning) is exhausted"
RC=0; OUT="$(FAKE_POOL=opus-weekly-below bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "Opus below the threshold is available"
RC=0; OUT="$(FAKE_POOL=opus-weekly-below FAKE_THRESHOLD=0.85 bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "the pool's configured switchThreshold is honored"
RC=0; OUT="$(FAKE_POOL=opus-weekly-expired bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "a rejected window whose resetAt has passed is not active"
# Only a number in (0, 1] is a threshold; anything else keeps bb's 0.98.
for bad in 0 -1 '"0.85"' true null; do
  RC=0; OUT="$(FAKE_POOL=opus-weekly-below FAKE_THRESHOLD="$bad" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 0 "$OPUS" "switchThreshold $bad is ignored (0.9 < 0.98)"
done
RC=0; OUT="$(FAKE_POOL=opus-weekly-warning FAKE_THRESHOLD=1.5 bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "switchThreshold 1.5 is ignored (1.0 >= 0.98)"
RC=0; OUT="$(FAKE_POOL=opus-weekly-warning FAKE_THRESHOLD=1 bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$SONNET" "switchThreshold 1 is honored"
# N3: one exhausted and one available Claude account keeps Opus (all, not any).
RC=0; OUT="$(FAKE_POOL=claude-mixed bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "mixed Claude accounts keep Opus"

# N8: a provider bb does not route through the pool, or a child host, is not
# judged by pool accounts.
RC=0; OUT="$(FAKE_POOL=routing-off bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "Claude routing off: Claude is not judged by pool accounts"
RC=0; OUT="$(FAKE_POOL=child-host bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "child host: the pool is not evaluated"
jq -e '.fallbacks_evaluated == false' <<< "$(latest_receipt)" >/dev/null || fail "a child host leaves fallbacks unevaluated"

# N5: timeouts must be finite and positive, and a timed-out resolver's
# process group dies with it (hangic forks a sleep without exec).
for bad in abc 0 -1 inf nan; do
  RC=0; OUT="$(ROUTE_SPAWN_POOL_TIMEOUT="$bad" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 2 "" "ROUTE_SPAWN_POOL_TIMEOUT=$bad"
  RC=0; OUT="$(ROUTE_SPAWN_IC_TIMEOUT="$bad" bash "$SCRIPT" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 2 "" "ROUTE_SPAWN_IC_TIMEOUT=$bad"
done
start=$SECONDS
# Stderr goes to a pipe too: a surviving grandchild would hold it open.
RC=0; OUT="$(PATH="$TMP_ROOT/hangic:$PATH" ROUTE_SPAWN_IC_TIMEOUT=1 timeout 30 bash "$SCRIPT" --role lane --lineage L1 2> >(cat > "$TMP_ROOT/stderr"))" || RC=$?
expect 3 "" "forking hanging resolver"
(( SECONDS - start < 10 )) || fail "a timed-out resolver's grandchildren must not hold the caller's pipe"
[[ -s "$TMP_ROOT/gc.pid" ]] || fail "the forking resolver never ran"
! kill -0 "$(cat "$TMP_ROOT/gc.pid")" 2>/dev/null || fail "a timed-out resolver's grandchild must be killed"
# A setsid descendant escapes the group kill: route-spawn must still return
# within its timeout, and must not have lent it the caller's stderr.
start=$SECONDS
RC=0; ALL="$(PATH="$TMP_ROOT/setsidic:$PATH" ROUTE_SPAWN_IC_TIMEOUT=3 timeout 60 bash "$SCRIPT" --role lane --lineage L1 2>&1)" || RC=$?
[[ "$RC" == 3 ]] || fail "setsid descendant: exit $RC, want 3 ($ALL)"
[[ "$ALL" != *claude-code* ]] || fail "setsid descendant: no tuple on failure"
(( SECONDS - start < 10 )) || fail "a setsid descendant must not hold route-spawn or the caller's stderr past the timeout ($((SECONDS - start)) s)"

# N4: project-table cross-validation fails closed.
python3 - "$ROOT/config/routing.yaml" "$TMP_ROOT" <<'BADTABLE'
import sys, yaml, copy
base = yaml.safe_load(open(sys.argv[1]))
# mk-h73i emptied project_profiles; inject a synthetic project-aleph profile
# so cross-validation of profile scope/role shape stays covered even though
# the packaged policy no longer ships one.
base["reasoning"]["project_profiles"]["aleph"] = "project-aleph"
base["reasoning"]["profiles"]["project-aleph"] = {
    "scope": "project:aleph", "roles": {"coordinator-seat": "coordinator-seat-opus"}}
def emit(name, mutate):
    cfg = copy.deepcopy(base); mutate(cfg["reasoning"])
    yaml.safe_dump(cfg, open(f"{sys.argv[2]}/{name}.yaml", "w"))
emit("typo-profile", lambda r: r["project_profiles"].__setitem__("aleph", "project-alpeh"))
emit("slug-alias", lambda r: r["project_aliases"].__setitem__("clavain", "autosigil"))
emit("lane-override", lambda r: r["profiles"]["project-aleph"]["roles"].__setitem__("lane", "coordinator-seat-opus"))
emit("wrong-scope", lambda r: r["profiles"]["project-aleph"].__setitem__("scope", "project:clavain"))
BADTABLE
for bad in typo-profile slug-alias lane-override wrong-scope; do
  RC=0; OUT="$(CLAVAIN_ROUTING_POLICY="$TMP_ROOT/$bad.yaml" bash "$SCRIPT" --role coordinator-seat --project autosigil 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 3 "" "invalid project table: $bad"
done

# N6d: a governed producer exclusion is not reported as a capacity fallback.
run --role validation --producer-identity claude-opus-5-5
grep -q "producer_model_conflict" "$TMP_ROOT/stderr" || fail "a producer exclusion must state its reason"
! grep -q "fallback from" "$TMP_ROOT/stderr" || fail "a producer exclusion is not a capacity fallback"

# N7: --seat-out hands the spawner the seat tuple to pass into the
# coordinator's spawn prompt; nothing is written on failure.
run --role coordinator-seat --project clavain --seat-out "$TMP_ROOT/seat.json"
expect 0 "$SONNET" "coordinator-seat with --seat-out"
jq -e --slurpfile r <(latest_receipt) '
  .provider == "claude-code" and .model == "claude-sonnet-5" and .reasoning_level == "medium"
  and .role == "coordinator-seat" and .profile_ref == "coordinator-seat-sonnet"
  and .policy_profile == null and .policy_hash == $r[0].policy_hash
  and (.policy_hash | length) == 64 and (.receipt | test("\\.json$"))' "$TMP_ROOT/seat.json" >/dev/null \
  || fail "--seat-out must hold provider, model, reasoning_level, role, profile_ref, policy_profile, policy_hash and receipt"
run --role coordinator-seat --project no-such-project --seat-out "$TMP_ROOT/seat-bad.json"
expect 2 "" "--seat-out with a bad project"
[[ ! -e "$TMP_ROOT/seat-bad.json" ]] || fail "--seat-out is not written on failure"
RC=0; OUT="$(FAKE_POOL=all-down bash "$SCRIPT" --role coordinator-seat --project clavain --seat-out "$TMP_ROOT/seat-down.json" 2>"$TMP_ROOT/stderr")" || RC=$?
expect 3 "" "--seat-out with no eligible seat"
[[ ! -e "$TMP_ROOT/seat-down.json" ]] || fail "--seat-out is not written when no seat is eligible"
run --role lane --lineage L1 --seat-out
expect 2 "" "--seat-out needs a value"
# A bad --seat-out path is a usage error before bb or ic runs.
mkdir -p "$TMP_ROOT/markic"
printf '#!/usr/bin/env bash\ntouch "%s/ic.ran"\nexit 1\n' "$TMP_ROOT" > "$TMP_ROOT/markic/ic"
chmod +x "$TMP_ROOT/markic/ic"
for bad in "$TMP_ROOT/no-such-dir/seat.json" "$TMP_ROOT"; do
  before="$(ls "$ROUTE_SPAWN_RECEIPT_DIR" | wc -l)"
  : > "$TMP_ROOT/bb.log"
  RC=0; OUT="$(PATH="$TMP_ROOT/markic:$PATH" FAKE_BB_LOG="$TMP_ROOT/bb.log" bash "$SCRIPT" --role lane --lineage L1 --seat-out "$bad" 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 2 "" "--seat-out $bad is a usage error"
  [[ ! -s "$TMP_ROOT/bb.log" && ! -e "$TMP_ROOT/ic.ran" ]] || fail "--seat-out $bad must be rejected before bb or ic runs"
  [[ "$(ls "$ROUTE_SPAWN_RECEIPT_DIR" | wc -l)" == "$before" ]] || fail "--seat-out $bad must not leave a receipt"
done
# The recipe's mktemp file exists beforehand: success replaces it.
: > "$TMP_ROOT/seat-pre.json"
run --role coordinator-seat --project clavain --seat-out "$TMP_ROOT/seat-pre.json"
expect 0 "$SONNET" "--seat-out over an existing file"
jq -e '.model == "claude-sonnet-5"' "$TMP_ROOT/seat-pre.json" >/dev/null || fail "--seat-out replaces an existing file on success"
# The seat is replaced before the tuple is printed; a failed print exits
# non-zero and leaves the (accurate) new seat in place.
echo OLD > "$TMP_ROOT/seat-keep.json"
RC=0; bash "$SCRIPT" --role coordinator-seat --project clavain --seat-out "$TMP_ROOT/seat-keep.json" >/dev/full 2>"$TMP_ROOT/stderr" || RC=$?
[[ "$RC" == 3 ]] || fail "a failed stdout write must exit 3, got $RC"
jq -e '.model == "claude-sonnet-5"' "$TMP_ROOT/seat-keep.json" >/dev/null || fail "the seat is in place before the tuple is printed"
! compgen -G "$TMP_ROOT/.route-spawn-*" >/dev/null || fail "a failed stdout write must not leave temp files"
# A failed os.replace onto the seat path exits 3 with empty stdout, before
# the tuple is printed. sitecustomize makes that one rename raise.
mkdir -p "$TMP_ROOT/failreplace" "$TMP_ROOT/seatdir"
cat > "$TMP_ROOT/failreplace/sitecustomize.py" <<'SITE'
import os
_replace = os.replace
def replace(src, dst, *args, **kwargs):
    if os.path.abspath(dst) == os.path.abspath(os.environ["FAIL_REPLACE"]):
        raise PermissionError(13, "injected rename failure", str(dst))
    return _replace(src, dst, *args, **kwargs)
os.replace = replace
SITE
for pre in none file; do
  seat="$TMP_ROOT/seatdir/seat-$pre.json"
  [[ "$pre" == none ]] || echo OLD > "$seat"
  RC=0; OUT="$(PYTHONPATH="$TMP_ROOT/failreplace" FAIL_REPLACE="$seat" bash "$SCRIPT" --role coordinator-seat --project clavain --seat-out "$seat" 2>"$TMP_ROOT/stderr")" || RC=$?
  expect 3 "" "a failed seat rename ($pre beforehand)"
  grep -q "injected rename failure" "$TMP_ROOT/stderr" || fail "the injected os.replace failure must be the one reported ($pre)"
  if [[ "$pre" == none ]]; then [[ ! -e "$seat" ]] || fail "a failed seat rename must not create the seat file"
  else [[ "$(cat "$seat")" == OLD ]] || fail "a failed seat rename must leave the existing file alone"; fi
  ! compgen -G "$TMP_ROOT/seatdir/.route-spawn-*" >/dev/null || fail "a failed seat rename must not leave temp files ($pre)"
done

# N6c: a relative XDG_STATE_HOME is ignored and a symlinked script works.
unset ROUTE_SPAWN_RECEIPT_DIR
mkdir -p "$TMP_ROOT/home" "$TMP_ROOT/cwd"
ln -sf "$SCRIPT" "$TMP_ROOT/route-spawn-link"
RC=0; OUT="$(cd "$TMP_ROOT/cwd" && HOME="$TMP_ROOT/home" XDG_STATE_HOME=relative/state bash "$TMP_ROOT/route-spawn-link" --role lane --lineage L1 2>"$TMP_ROOT/stderr")" || RC=$?
expect 0 "$OPUS" "symlinked invocation with a relative XDG_STATE_HOME"
[[ ! -e "$TMP_ROOT/cwd/relative" ]] || fail "a relative XDG_STATE_HOME must be ignored"
find "$TMP_ROOT/home/.local/state" -name '*.json' | grep -q . || fail "receipts fall back to \$HOME/.local/state"
export ROUTE_SPAWN_RECEIPT_DIR="$TMP_ROOT/receipts"

echo "PASS: route-spawn"
