#!/usr/bin/env bash
# Coordinator-seat routing for a synthetic project table layered over the
# packaged policy. Real Intercore resolver; no model calls.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGED="$ROOT/config/routing.yaml"
command -v ic >/dev/null
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

ALL_SLUGS=(alpha clavain bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november)
POLICY="$TMP_ROOT/devbox.yaml"
python3 - "$PACKAGED" "$POLICY" <<'DEVBOX'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
cfg["reasoning"]["projects"] = ["alpha", "clavain", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
                                "hotel", "india", "juliet", "kilo", "lima", "mike", "november"]
cfg["reasoning"]["project_aliases"] = {"proj_synth1": "bravo", "proj_synth2": "charlie"}
yaml.safe_dump(cfg, open(sys.argv[2], "w"))
DEVBOX

policy_json() {
  python3 - "$POLICY" <<'PY'
import json, sys, yaml
print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))))
PY
}
CFG="$(policy_json)"

PACKAGED_CFG="$(python3 -c 'import json, sys, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))))' "$PACKAGED")"
jq -e '.reasoning.projects == [] and .reasoning.project_aliases == {} and .reasoning.project_profiles == {} and .reasoning.profiles == {}' <<< "$PACKAGED_CFG" >/dev/null \
  || fail "the packaged policy must carry no projects, aliases, project profiles or profiles"

jq -e '(.reasoning.project_profiles // {}) == {}' <<< "$CFG" >/dev/null \
  || fail "project_profiles must be empty"

jq -e --argjson slugs "$(printf '%s\n' "${ALL_SLUGS[@]}" | jq -R . | jq -s 'sort')" \
  '(.reasoning.projects | sort) == $slugs' <<< "$CFG" >/dev/null \
  || fail "reasoning.projects must list exactly the table slugs"

# Every alias targets a table slug; shared bb projects have no alias.
jq -e --argjson slugs "$(printf '%s\n' "${ALL_SLUGS[@]}" | jq -R . | jq -s .)" \
  '.reasoning.project_aliases | to_entries | all(.value as $v | $slugs | index($v))' <<< "$CFG" >/dev/null \
  || fail "every project alias must target a table slug"
jq -e '.reasoning.project_aliases | has("proj_personal") | not' <<< "$CFG" >/dev/null \
  || fail "proj_personal is shared and must not have an alias"

# No profile overrides main-session, lane, coordination or coordinator-seat.
jq -e '[.reasoning.profiles | to_entries[] | .value.roles | to_entries[] | select(.key == "main-session" or .key == "lane" or .key == "coordination" or .key == "coordinator-seat")] | length == 0' <<< "$CFG" >/dev/null \
  || fail "no profile may override main-session, lane, coordination or coordinator-seat"

# Tiers and roles.
jq -e '.dispatch.roles["main-session"] == "main-sonnet" and .dispatch.roles.lane == "lane-status-quo" and .dispatch.roles.coordination == "coordination-sonnet" and .dispatch.roles["coordinator-seat"] == "coordinator-seat-sonnet"' <<< "$CFG" >/dev/null \
  || fail "dispatch.roles must map main-session→main-sonnet, lane→lane-status-quo, coordination→coordination-sonnet, coordinator-seat→coordinator-seat-sonnet"
# Rule 6 holds unchanged: every tier of the relay role coordination is Sonnet or Sol.
jq -e '[.dispatch.tiers | to_entries[] | select(.value.role == "coordination") | .value.model] | all(test("sonnet|sol"))' <<< "$CFG" >/dev/null \
  || fail "coordination is the relay role; its tiers admit Sonnet or Sol only (roster rule 6)"
jq -e '.dispatch.tiers | has("coordination-opus") | not' <<< "$CFG" >/dev/null \
  || fail "coordination-opus is replaced by coordinator-seat-opus"
# coordinator-seat-opus itself stays defined: nothing in dispatch.roles or
# reasoning.profiles points to it any more, so no role/project resolution
# ever lands on it, but it stays explicitly selectable via
# `--tier=coordinator-seat-opus` for an operator who wants it directly.
jq -e '.dispatch.tiers | has("coordinator-seat-opus")' <<< "$CFG" >/dev/null \
  || fail "coordinator-seat-opus tier must still exist "
jq -e '[.reasoning.profiles | to_entries[] | .value.roles | to_entries[] | select(.value == "coordinator-seat-opus")] | length == 0' <<< "$CFG" >/dev/null \
  || fail "no profile may still point at coordinator-seat-opus"
jq -e '.dispatch.roles | to_entries | all(.value != "coordinator-seat-opus")' <<< "$CFG" >/dev/null \
  || fail "no fleet role may point at coordinator-seat-opus"

# No spawn chain (lane, main-session, coordinator-seat,
# or any profile override of them) ever reaches gpt-5.6-sol. Claude exhaustion
# lands on gpt-6-astra medium.
python3 - "$POLICY" <<'NOSOL' || fail "a spawn role chain reaches gpt-5.6-sol"
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
tiers, roles = cfg["dispatch"]["tiers"], cfg["dispatch"]["roles"]
aliases = {str(k).lower(): str(v).lower() for k, v in (cfg["dispatch"].get("model_aliases") or {}).items()}
spawn_roles = ("lane", "main-session", "coordinator-seat")
heads = [roles[r] for r in spawn_roles]
for prof in cfg["reasoning"]["profiles"].values():
    heads += [t for r, t in (prof.get("roles") or {}).items() if r in spawn_roles]
seen, stack, bad = set(), list(heads), []
while stack:
    name = stack.pop()
    if name in seen:
        continue
    seen.add(name)
    tier = tiers[name]
    model = str(tier.get("model", "")).lower()
    if aliases.get(model, model) in ("gpt-5.6-sol", "gpt-5.6"):
        bad.append(name)
    stack += tier.get("fallbacks") or []
assert not bad, f"spawn chains reach gpt-5.6-sol via {bad}"
assert "main-session-sol" not in tiers, "main-session-sol must be removed"
for head in ("main-sonnet", "coordinator-seat-sonnet"):
    last = tiers[tiers[head]["fallbacks"][-1]]
    assert (last["backend"], last["model"], last["reasoning_effort"]) == ("codex", "gpt-6-astra", "medium"), head
print("no spawn chain reaches gpt-5.6-sol")
NOSOL

route() {
  local ctx="$1"; shift
  ic --json route dispatch --policy="$POLICY" --context-file="$ctx" "$@"
}
printf '%s\n' '{"reasons":[],"rationale":"project-profiles test"}' > "$TMP_ROOT/plain.json"

# main-session: Sonnet 5.5 medium, and Opus is nowhere in its chain.
out="$(route "$TMP_ROOT/plain.json" --role=main-session)"
jq -e '.profile.model_identity == "claude-sonnet-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "main-session must resolve Sonnet 5.5 medium"
jq -e '[.profile.model_identity, (.fallback_chain[]?.profile.model_identity)] | all(test("opus|fable") | not)' <<< "$out" >/dev/null \
  || fail "main-session fallback chain must never include Opus or Fable"

# lane: the explicit status-quo control arm, Opus 5.5 medium.
out="$(route "$TMP_ROOT/plain.json" --role=lane)"
jq -e '.profile_ref == "lane-status-quo" and .profile.model_identity == "claude-opus-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "lane must resolve lane-status-quo (Opus 5.5 medium)"

# Relay coordination and the unprofiled coordinator seat stay on Sonnet.
out="$(route "$TMP_ROOT/plain.json" --role=coordination)"
jq -e '.profile.model_identity == "claude-sonnet-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "fleet coordination must stay Sonnet 5.5 medium"
out="$(route "$TMP_ROOT/plain.json" --role=coordinator-seat)"
jq -e '.profile_ref == "coordinator-seat-sonnet" and .profile.model_identity == "claude-sonnet-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "the fleet coordinator seat must be Sonnet 5.5 medium"

# Every table slug resolves coordinator-seat to the fleet Sonnet default,
# unprofiled.
for slug in "${ALL_SLUGS[@]}"; do
  jq --arg s "project:$slug" '. + {scope: $s}' "$TMP_ROOT/plain.json" > "$TMP_ROOT/$slug.json"
  out="$(route "$TMP_ROOT/$slug.json" --role=coordinator-seat)"
  jq -e '.profile_ref == "coordinator-seat-sonnet" and .profile.model_identity == "claude-sonnet-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
    || fail "$slug must resolve coordinator-seat to coordinator-seat-sonnet, unprofiled"
done

echo "PASS: project profiles"
