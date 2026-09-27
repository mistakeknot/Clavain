#!/usr/bin/env bash
# Per-project coordinator-seat profiles and the unpinned-default roles (mk-42j9.25
# Task 1). Real Intercore resolver against the packaged policy; no model calls.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="$ROOT/config/routing.yaml"
command -v ic >/dev/null
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# The mk-42j9.5 reversal table: Opus 5.5 medium coordinators get a project
# profile; every other coordinator keeps the fleet Sonnet default.
OPUS_SLUGS=(aleph clavain autarch after-them bbops shadow-work quilan sylvesteops nartopo)
SONNET_SLUGS=(autosigil rakes uncrancher cujgel agmodb linsenkasten)

policy_json() {
  python3 - "$POLICY" <<'PY'
import json, sys, yaml
print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))))
PY
}
CFG="$(policy_json)"

# Structure: every Opus slug has project-<slug> with scope project:<slug> that
# maps only the coordinator's own seat (coordinator-seat) to
# coordinator-seat-opus. `coordination` stays the relay role (roster rule 6).
for slug in "${OPUS_SLUGS[@]}"; do
  jq -e --arg s "$slug" '.reasoning.project_profiles[$s] == ("project-" + $s)' <<< "$CFG" >/dev/null \
    || fail "project_profiles.$slug must name project-$slug"
  jq -e --arg s "$slug" '.reasoning.profiles["project-" + $s] == {scope: ("project:" + $s), roles: {"coordinator-seat": "coordinator-seat-opus"}}' <<< "$CFG" >/dev/null \
    || fail "profile project-$slug must be {scope: project:$slug, roles: {coordinator-seat: coordinator-seat-opus}}"
done
for slug in "${SONNET_SLUGS[@]}"; do
  jq -e --arg s "$slug" '(.reasoning.project_profiles[$s] // null) == null' <<< "$CFG" >/dev/null \
    || fail "$slug is a Sonnet coordinator and must not have a project profile"
done
jq -e '(.reasoning.project_profiles | length) == 9' <<< "$CFG" >/dev/null \
  || fail "project_profiles must list exactly the 9 Opus coordinators"

# reasoning.projects is the explicit 15-slug table route-spawn.sh trusts.
jq -e --argjson slugs "$(printf '%s\n' "${OPUS_SLUGS[@]}" "${SONNET_SLUGS[@]}" | jq -R . | jq -s 'sort')" \
  '(.reasoning.projects | sort) == $slugs' <<< "$CFG" >/dev/null \
  || fail "reasoning.projects must list exactly the 15 table slugs"

# Every alias targets a table slug; shared bb projects have no alias.
jq -e --argjson slugs "$(printf '%s\n' "${OPUS_SLUGS[@]}" "${SONNET_SLUGS[@]}" | jq -R . | jq -s .)" \
  '.reasoning.project_aliases | to_entries | all(.value as $v | $slugs | index($v))' <<< "$CFG" >/dev/null \
  || fail "every project alias must target a table slug"
jq -e '.reasoning.project_aliases | has("proj_personal") | not' <<< "$CFG" >/dev/null \
  || fail "proj_personal is shared and must not have an alias"
jq -e '.reasoning.project_aliases | has("proj_bnq4zi2wiv") | not' <<< "$CFG" >/dev/null \
  || fail "proj_bnq4zi2wiv (projects/Sylveste) is shared and must not have an alias"

# No profile overrides main-session or lane, and no profile touches the relay
# role coordination.
jq -e '[.reasoning.profiles | to_entries[] | .value.roles | to_entries[] | select(.key == "main-session" or .key == "lane" or .key == "coordination")] | length == 0' <<< "$CFG" >/dev/null \
  || fail "no profile may override main-session, lane or the relay role coordination"

# Tiers and roles.
jq -e '.dispatch.roles["main-session"] == "main-sonnet" and .dispatch.roles.lane == "lane-status-quo" and .dispatch.roles.coordination == "coordination-sonnet" and .dispatch.roles["coordinator-seat"] == "coordinator-seat-sonnet"' <<< "$CFG" >/dev/null \
  || fail "dispatch.roles must map main-session→main-sonnet, lane→lane-status-quo, coordination→coordination-sonnet, coordinator-seat→coordinator-seat-sonnet"
# Rule 6 holds unchanged: every tier of the relay role coordination is Sonnet or Sol.
jq -e '[.dispatch.tiers | to_entries[] | select(.value.role == "coordination") | .value.model] | all(test("sonnet|sol"))' <<< "$CFG" >/dev/null \
  || fail "coordination is the relay role; its tiers admit Sonnet or Sol only (roster rule 6)"
jq -e '.dispatch.tiers | has("coordination-opus") | not' <<< "$CFG" >/dev/null \
  || fail "coordination-opus is replaced by coordinator-seat-opus"

# mk ruling 2026-09-27: no spawn chain (lane, main-session, coordinator-seat,
# or any profile override of them) ever reaches gpt-5.6-sol. Claude exhaustion
# lands on gpt-6-astra medium.
python3 - "$POLICY" <<'NOSOL' || fail "a spawn role chain reaches gpt-5.6-sol"
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
tiers, roles = cfg["dispatch"]["tiers"], cfg["dispatch"]["roles"]
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
    if tier.get("model") == "gpt-5.6-sol":
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

# main-session: Sonnet 5 medium, and Opus is nowhere in its chain.
out="$(route "$TMP_ROOT/plain.json" --role=main-session)"
jq -e '.profile.model_identity == "claude-sonnet-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "main-session must resolve Sonnet 5 medium"
jq -e '[.profile.model_identity, (.fallback_chain[]?.profile.model_identity)] | all(test("opus|fable") | not)' <<< "$out" >/dev/null \
  || fail "main-session fallback chain must never include Opus or Fable"

# lane: the explicit status-quo control arm, Opus 5.5 medium.
out="$(route "$TMP_ROOT/plain.json" --role=lane)"
jq -e '.profile_ref == "lane-status-quo" and .profile.model_identity == "claude-opus-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "lane must resolve lane-status-quo (Opus 5.5 medium)"

# Relay coordination and the unprofiled coordinator seat stay on Sonnet.
out="$(route "$TMP_ROOT/plain.json" --role=coordination)"
jq -e '.profile.model_identity == "claude-sonnet-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "fleet coordination must stay Sonnet 5 medium"
out="$(route "$TMP_ROOT/plain.json" --role=coordinator-seat)"
jq -e '.profile_ref == "coordinator-seat-sonnet" and .profile.model_identity == "claude-sonnet-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "the fleet coordinator seat must be Sonnet 5 medium"

# Every Opus profile resolves coordinator-seat to Opus 5.5 medium under its scope,
# and ic refuses the profile without that scope.
for slug in "${OPUS_SLUGS[@]}"; do
  jq --arg s "project:$slug" '. + {scope: $s}' "$TMP_ROOT/plain.json" > "$TMP_ROOT/$slug.json"
  out="$(route "$TMP_ROOT/$slug.json" --role=coordinator-seat --policy-profile="project-$slug")"
  jq -e --arg p "project-$slug" '.policy_profile == $p and .profile.model_identity == "claude-opus-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
    || fail "project-$slug must resolve coordinator-seat to Opus 5.5 medium"
  out="$(route "$TMP_ROOT/$slug.json" --role=coordination --policy-profile="project-$slug")"
  jq -e '.profile.model_identity == "claude-sonnet-5"' <<< "$out" >/dev/null \
    || fail "project-$slug must leave relay coordination on Sonnet"
  if route "$TMP_ROOT/plain.json" --role=coordinator-seat --policy-profile="project-$slug" >/dev/null 2>&1; then
    fail "project-$slug must require scope project:$slug"
  fi
done

echo "PASS: project profiles"
