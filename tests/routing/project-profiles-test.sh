#!/usr/bin/env bash
# Per-project coordination profiles and the unpinned-default roles (mk-42j9.25
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
# maps only coordination to coordination-opus.
for slug in "${OPUS_SLUGS[@]}"; do
  jq -e --arg s "$slug" '.reasoning.project_profiles[$s] == ("project-" + $s)' <<< "$CFG" >/dev/null \
    || fail "project_profiles.$slug must name project-$slug"
  jq -e --arg s "$slug" '.reasoning.profiles["project-" + $s] == {scope: ("project:" + $s), roles: {coordination: "coordination-opus"}}' <<< "$CFG" >/dev/null \
    || fail "profile project-$slug must be {scope: project:$slug, roles: {coordination: coordination-opus}}"
done
for slug in "${SONNET_SLUGS[@]}"; do
  jq -e --arg s "$slug" '(.reasoning.project_profiles[$s] // null) == null' <<< "$CFG" >/dev/null \
    || fail "$slug is a Sonnet coordinator and must not have a project profile"
done
jq -e '(.reasoning.project_profiles | length) == 9' <<< "$CFG" >/dev/null \
  || fail "project_profiles must list exactly the 9 Opus coordinators"

# Every alias targets a table slug; shared bb projects have no alias.
jq -e --argjson slugs "$(printf '%s\n' "${OPUS_SLUGS[@]}" "${SONNET_SLUGS[@]}" | jq -R . | jq -s .)" \
  '.reasoning.project_aliases | to_entries | all(.value as $v | $slugs | index($v))' <<< "$CFG" >/dev/null \
  || fail "every project alias must target a table slug"
jq -e '.reasoning.project_aliases | has("proj_personal") | not' <<< "$CFG" >/dev/null \
  || fail "proj_personal is shared and must not have an alias"
jq -e '.reasoning.project_aliases | has("proj_bnq4zi2wiv") | not' <<< "$CFG" >/dev/null \
  || fail "proj_bnq4zi2wiv (projects/Sylveste) is shared and must not have an alias"

# No profile routes main-session or lane to Astra, and no project profile
# touches any role except coordination.
jq -e '[.reasoning.profiles | to_entries[] | .value.roles | to_entries[] | select(.key == "main-session" or .key == "lane")] | length == 0' <<< "$CFG" >/dev/null \
  || fail "no profile may override main-session or lane"

# Tiers and roles.
jq -e '.dispatch.roles["main-session"] == "main-sonnet" and .dispatch.roles.lane == "lane-status-quo" and .dispatch.roles.coordination == "coordination-sonnet"' <<< "$CFG" >/dev/null \
  || fail "dispatch.roles must map main-session→main-sonnet, lane→lane-status-quo, coordination→coordination-sonnet"

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

# coordination without a profile stays on the fleet Sonnet default.
out="$(route "$TMP_ROOT/plain.json" --role=coordination)"
jq -e '.profile.model_identity == "claude-sonnet-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
  || fail "fleet coordination must stay Sonnet 5 medium"

# Every Opus profile resolves coordination to Opus 5.5 medium under its scope,
# and ic refuses the profile without that scope.
for slug in "${OPUS_SLUGS[@]}"; do
  jq --arg s "project:$slug" '. + {scope: $s}' "$TMP_ROOT/plain.json" > "$TMP_ROOT/$slug.json"
  out="$(route "$TMP_ROOT/$slug.json" --role=coordination --policy-profile="project-$slug")"
  jq -e --arg p "project-$slug" '.policy_profile == $p and .profile.model_identity == "claude-opus-5-5" and .profile.reasoning_effort == "medium"' <<< "$out" >/dev/null \
    || fail "project-$slug must resolve coordination to Opus 5.5 medium"
  if route "$TMP_ROOT/plain.json" --role=coordination --policy-profile="project-$slug" >/dev/null 2>&1; then
    fail "project-$slug must require scope project:$slug"
  fi
done

echo "PASS: project profiles"
