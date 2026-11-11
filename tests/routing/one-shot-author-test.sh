#!/usr/bin/env bash
# mk-f0z9d: the one-shot-author role routes to Fable 5.2 and nowhere else.
# Fable is frontier-eligible but holds only this seat; a Fable-produced artifact
# is reviewed cross-lab by default. Resolve with real ic; never dispatch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="$ROOT/config/routing.yaml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
command -v ic >/dev/null || { echo "FAIL: real ic required" >&2; exit 1; }
command -v jq >/dev/null || { echo "FAIL: jq required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "FAIL: python3 required" >&2; exit 1; }
fail() { echo "FAIL: $*" >&2; exit 1; }
FABLE=claude-fable-5-2

printf '%s\n' '{"reasons":[],"rationale":"settled one-shot author routing coverage"}' > "$WORK/routine.json"
jq '.reasons = ["foundational-invariants"]' "$WORK/routine.json" > "$WORK/floored.json"
checks=0
resolve() { # role context [producer]
  local args=(--policy="$POLICY" --role="$1" --context-file="$2")
  [[ -n "${3:-}" ]] && args+=(--producer-identity="$3")
  ic --json route dispatch "${args[@]}"
}
check() {
  jq -e "$2" <<< "$1" >/dev/null || fail "$3: $1"
  checks=$((checks + 1))
}

# 1. Policy shape: eligible, one role, Fable only in the one-shot tiers.
python3 - "$POLICY" "$FABLE" <<'PY' || fail "policy shape"
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
fable = sys.argv[2]
assert fable in cfg["reasoning"]["frontier_models"], "fable not frontier-eligible"
d = cfg["dispatch"]
assert d["roles"]["one-shot-author"] == "one-shot-fable"
tiers = d["tiers"]
holders = sorted(n for n, t in tiers.items() if t.get("model") == fable)
assert holders == ["one-shot-fable"], f"fable tiers: {holders}"
assert tiers["one-shot-fable"]["role"] == "one-shot-author"
reachable = {"one-shot-fable"}
for role, head in d["roles"].items():
    if role == "one-shot-author":
        continue
    seen, todo = set(), [head]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        todo += tiers[n].get("fallbacks", [])
    assert not (seen & reachable), f"{role} reaches the one-shot Fable tier"
assert d["roles"]["plan-review"] == "review-opus", "Opus 5.5 must stay the plan-review seat"
PY
checks=$((checks + 1))

# 2. Unelevated context: Fable takes the seat; Opus then Astra are the fallbacks.
r="$(resolve one-shot-author "$WORK/routine.json")"
check "$r" '
  .profile_ref == "one-shot-fable" and .profile.model_identity == "claude-fable-5-2"
  and .profile.reasoning_effort == "high"
  and [.fallback_chain[].profile_ref] == ["one-shot-opus","one-shot-astra"]
' "routine one-shot-author must resolve to Fable 5.2 high"

# 3. Floored context: the seat is never taken by anything but Fable or Opus.
# (Today the intercore effort ladder does not know Fable, so Opus 5.5 takes it.)
r="$(resolve one-shot-author "$WORK/floored.json")"
check "$r" '.profile.model_identity | IN("claude-fable-5-2","claude-opus-5-5")' \
  "floored one-shot-author seat holder"

# 4. A Fable producer is reviewed cross-lab by default, in routine and floored contexts.
for context in routine floored; do
  ctx="$WORK/$context.json"
  r="$(resolve cross-lab-review "$ctx" "$FABLE")"
  check "$r" '.profile.backend == "codex" and .profile.model_identity != "claude-fable-5-2"' \
    "$context: Fable-produced cross-lab-review must go to a non-Claude seat"
  r="$(resolve validation "$ctx" "$FABLE")"
  check "$r" '.profile.backend == "codex" and .fallback_reason == "cross_lab_reorder"' \
    "$context: Fable-produced validation must reorder to a non-Claude seat"
  r="$(resolve plan-review "$ctx" "$FABLE")"
  check "$r" '
    .profile_ref == "review-astra" and .profile.model_identity == "gpt-6-astra"
    and .fallback_reason == "cross_lab_reorder"
    and ([.fallback_chain[].profile_ref] == ["review-opus"])
  ' "$context: Fable-produced plan-review must prefer Astra and retain Opus"
done

# 5. An OpenAI-produced plan still goes to Opus 5.5: it stays the plan-review seat.
r="$(resolve plan-review "$WORK/routine.json" gpt-6.1-sol)"
check "$r" '.profile_ref == "review-opus" and .profile.model_identity == "claude-opus-5-5"' \
  "OpenAI-produced plan-review must stay on Opus 5.5"

echo "PASS: one-shot-author routes to Fable 5.2 only; Fable producers get cross-lab review ($checks checks)"
