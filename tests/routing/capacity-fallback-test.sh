#!/usr/bin/env bash
# capacity-fallback-test.sh — mk-9yyt. Resolves the real packaged policy with the
# real `ic` resolver. No model service is invoked.
#
# Guards three things at once:
#   1. every role the bead names has a reachable non-Codex destination, so a
#      Codex-lane capacity failure degrades instead of stalling;
#   2. a capacity fallback NEVER resolves to the bound producer — reviewer
#      separation stays enforced structurally, below the policy layer;
#   3. the default routes are unchanged while the primaries are up, so the
#      added chains are degradation paths and not a silent re-route.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="$ROOT/config/routing.yaml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

command -v ic >/dev/null || { echo "SKIP: ic not on PATH" >&2; exit 0; }
command -v jq >/dev/null || { echo "FAIL: jq not on PATH" >&2; exit 1; }

fail() { echo "FAIL: $*" >&2; exit 1; }

# A dual-review classification, so plan-review is frontier_required and the
# frontier eligibility gate is actually exercised.
cat > "$WORK/frontier.json" <<'JSON'
{
  "reasons": ["foundational-invariants", "broad-consequences"],
  "rationale": "changes a shared contract consumed by every downstream seat",
  "investigation_active": true
}
JSON
# A routine classification: no frontier gate, so the non-frontier chains show.
cat > "$WORK/routine.json" <<'JSON'
{"reasons": [], "rationale": "routine change with settled constraints"}
JSON

CLAUDE_LANE='["claude-opus-5-5","claude-sonnet-5","kimi-code/k3"]'
NO_ASTRA='["gpt-5.6-sol","claude-opus-5-5","claude-sonnet-5","kimi-code/k3"]'

ctx() { # ctx <base> <available_models-json|-> <out>
  if [[ "$2" == "-" ]]; then cp "$1" "$3"; else
    jq --argjson m "$2" '. + {available_models: $m}' "$1" > "$3"
  fi
}

resolve() { # resolve <policy> <role> <ctx> [producer]
  local policy="$1" role="$2" context="$3" producer="${4:-}"
  local args=(--json route dispatch "--policy=$policy" "--role=$role" "--context-file=$context")
  [[ -n "$producer" ]] && args+=("--producer-identity=$producer")
  ic "${args[@]}" 2>&1
}

# ---------------------------------------------------------------------------
# 1. Default routes are unchanged while the primaries are reachable.
#    A capacity fallback that changes the happy path is a re-route, not a fallback.
# ---------------------------------------------------------------------------
ctx "$WORK/frontier.json" - "$WORK/c-front.json"
ctx "$WORK/routine.json" - "$WORK/c-routine.json"

check_primary() { # check_primary <role> <ctx> <expected-profile_ref> [producer]
  local got
  got="$(resolve "$POLICY" "$1" "$2" "${4:-}")" || fail "$1 did not resolve: $got"
  got="$(echo "$got" | jq -r '.profile_ref')"
  [[ "$got" == "$3" ]] || fail "$1 primary drifted: want $3, got $got"
}
check_primary routine-execution   "$WORK/c-routine.json" routine-sol
check_primary scout               "$WORK/c-routine.json" scout-sol
check_primary release-preparation "$WORK/c-routine.json" release-sol
check_primary deep-execution      "$WORK/c-routine.json" deep-astra
check_primary deep-execution      "$WORK/c-front.json"   deep-astra
check_primary plan-review         "$WORK/c-front.json"   review-opus gpt-6-astra
check_primary plan-review         "$WORK/c-front.json"   review-astra claude-opus-5-5
check_primary validation          "$WORK/c-front.json"   validation-opus gpt-5.6-sol

# ---------------------------------------------------------------------------
# 2. mk-3b8z: Opus 5.5 replaced Fable 5.1 and every Opus seat runs Opus 5.5.
#    No Fable or Opus 5 seat is selectable, and every Claude Opus seat is 5.5.
#    An Opus-authored plan has Astra as its only routed reviewer; with Astra out,
#    routing fails CLOSED rather than admitting the producer (the agent then
#    applies mk's declared adversarial same-model Opus review by hand, mk-2e1e).
# ---------------------------------------------------------------------------
python3 - "$POLICY" <<'PY' || fail "policy still selects Fable or Opus 5"
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
dispatch = cfg.get("dispatch") or {}
aliases = dispatch.get("model_aliases") or {}
models = {aliases.get(t.get("model"), t.get("model")) for t in (dispatch.get("tiers") or {}).values()}
frontier = set((cfg.get("reasoning") or {}).get("frontier_models") or [])
phases = {p.get("model") for p in ((cfg.get("subagents") or {}).get("phases") or {}).values()}
bad = ({"claude-fable-5-1", "claude-opus-5", "fable"} & (models | frontier | phases)) or ("fable" in aliases)
opus = {m for m in models if m.startswith("claude-opus")}
sys.exit(1 if bad or opus != {"claude-opus-5-5"} or "claude-opus-5-5" not in frontier else 0)
PY

ctx "$WORK/frontier.json" "$CLAUDE_LANE" "$WORK/c-codex-down.json"
ctx "$WORK/frontier.json" "$NO_ASTRA" "$WORK/c-no-astra.json"
frontier_models="$(python3 - "$POLICY" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
print(" ".join((cfg.get("reasoning") or {}).get("frontier_models") or []))
PY
)"
if out="$(resolve "$POLICY" plan-review "$WORK/c-codex-down.json" claude-opus-5-5)"; then
  fail "Opus-authored plan-review found a routed reviewer with Astra out: $out"
fi
[[ "$out" == *"no eligible model satisfies reasoning contract"* ]] \
  || fail "Opus-authored plan-review refused for the wrong reason: $out"
# ic's refusal is generic, so pin its cause: the same context with a
# non-Opus producer still routes to Opus 5.5.
out="$(resolve "$POLICY" plan-review "$WORK/c-codex-down.json" claude-sonnet-5)" \
  || fail "Astra-out context refuses every producer, not just Opus: $out"
[[ "$(jq -r .profile.model <<< "$out")" == claude-opus-5-5 ]] || fail "Sonnet-authored plan, Astra out: expected Opus 5.5, got: $out"

# An Astra-authored plan is reviewed by Opus 5.5, a distinct frontier model.
receipt="$(resolve "$POLICY" plan-review "$WORK/c-codex-down.json" gpt-6-astra)" \
  || fail "Astra-authored plan-review has no reviewer: $receipt"
echo "$receipt" | jq -e '
  .profile_ref == "review-opus"
  and .profile.model_identity == "claude-opus-5-5"
  and .validator_relationship == "different-model"
' >/dev/null || fail "Astra-authored plan-review route is wrong: $receipt"

# ---------------------------------------------------------------------------
# 3. Every role the bead names reaches a non-Codex seat when the whole Codex lane
#    is recorded unavailable.
#    main-integrator and release-authority are deliberately excluded: those are
#    the running main session's own orchestration and release authority, not
#    delegable capacity. See docs/canon/reasoning-routing.md.
# ---------------------------------------------------------------------------
ctx "$WORK/routine.json" "$CLAUDE_LANE" "$WORK/c-routine-down.json"
for role in routine-execution scout release-preparation deep-execution; do
  for context in "$WORK/c-routine-down.json" "$WORK/c-codex-down.json"; do
    receipt="$(resolve "$POLICY" "$role" "$context")" \
      || fail "$role has no destination outside the Codex lane ($(basename "$context")): $receipt"
    echo "$receipt" | jq -e '.profile.backend != "codex"' >/dev/null \
      || fail "$role capacity fallback is still Codex-backed: $receipt"
    echo "$receipt" | jq -e '[.excluded[]? | select(.reason == "model_unavailable")] | length > 0' >/dev/null \
      || fail "$role receipt does not record the observed capacity failure: $receipt"
  done
done

# The frontier-required roles must not quietly drop below the frontier tier.
for context in "$WORK/c-codex-down.json" "$WORK/c-no-astra.json"; do
  receipt="$(resolve "$POLICY" deep-execution "$context")" || fail "deep-execution: $receipt"
  selected="$(echo "$receipt" | jq -r '.profile.model_identity')"
  echo "$receipt" | jq -e '.frontier_required' >/dev/null \
    && { [[ " $frontier_models " == *" $selected "* ]] \
         || fail "frontier-required deep-execution degraded to non-frontier $selected"; }
done

# ---------------------------------------------------------------------------
# 4. INVARIANT: no fallback ever equals the producer, for any role, any producer,
#    any capacity state. Checked across the primary AND the whole chain.
# ---------------------------------------------------------------------------
mapfile -t POLICY_MODELS < <(python3 - "$POLICY" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
dispatch = cfg.get("dispatch") or {}
aliases = dispatch.get("model_aliases") or {}
seen = []
for tier in (dispatch.get("tiers") or {}).values():
    model = (tier or {}).get("model")
    if model:
        model = aliases.get(model, model)
        if model not in seen:
            seen.append(model)
print("\n".join(seen))
PY
)
[[ ${#POLICY_MODELS[@]} -gt 0 ]] || fail "policy declares no dispatch models"

for role in plan-review validation cross-lab-review; do
  for producer in "${POLICY_MODELS[@]}"; do
    for context in "$WORK/c-front.json" "$WORK/c-routine.json" "$WORK/c-codex-down.json" "$WORK/c-no-astra.json"; do
      if ! receipt="$(resolve "$POLICY" "$role" "$context" "$producer")"; then
        # The only acceptable refusal is "nothing distinct from the producer is
        # reachable". Any other error is a policy defect, not independence.
        [[ "$receipt" == *"no model distinct from producer"* \
           || "$receipt" == *"no eligible model satisfies reasoning contract"* ]] \
          || fail "$role with producer $producer failed unexpectedly: $receipt"
        continue
      fi
      echo "$receipt" | jq -e '. as $r
        | ($r.producer_model | length > 0)
        and ($r.profile.model_identity != $r.producer_model)
        and ([$r.fallback_chain[]?.profile.model_identity] | index($r.producer_model) == null)
      ' >/dev/null || fail "$role with producer $producer admitted the producer as a candidate: $receipt"
    done
  done
done

# ---------------------------------------------------------------------------
# 5. The producer_model_conflict check must stay unweakened. A snapshot that
#    SELECTS review-opus with Opus 5.5 as producer still has to exclude it. If
#    this ever passes, an escape hatch was added below the policy layer.
# ---------------------------------------------------------------------------
receipt="$(resolve "$POLICY" plan-review "$WORK/c-front.json" claude-opus-5-5)" \
  || fail "self-review snapshot failed for the wrong reason: $receipt"
echo "$receipt" | jq -e '
  (.excluded | map(select(.profile_ref == "review-opus" and .reason == "producer_model_conflict")) | length == 1)
  and .profile_ref != "review-opus"
' >/dev/null || fail "reviewer separation weakened: Opus was admitted to review Opus"

# ---------------------------------------------------------------------------
# 6. TWO GATES, NOT ONE. Selecting a substitute without frontier eligibility must
#    still be refused: eligibility (reasoning.frontier_models) and selection
#    (dispatch.roles + fallbacks) are separate mechanisms.
# ---------------------------------------------------------------------------
sed 's/^  frontier_models: .*/  frontier_models: [gpt-6-astra]/' "$POLICY" > "$WORK/no-eligibility.yaml"
if out="$(resolve "$WORK/no-eligibility.yaml" plan-review "$WORK/c-codex-down.json" gpt-6-astra)"; then
  fail "plan-review resolved without frontier eligibility for the substitute: $out"
fi
[[ "$out" == *"no eligible model satisfies reasoning contract"* ]] \
  || fail "unexpected refusal for a selection-only substitute: $out"

# ---------------------------------------------------------------------------
# 7. FRONTIER AUTHORING falls back from Astra to Opus 5.5 (planning-opus, which
#    replaced planning-fable in mk-3b8z). A reachable Astra must still author
#    every plan, so the fallback can never become preferred.
# ---------------------------------------------------------------------------
receipt="$(resolve "$POLICY" planning "$WORK/c-front.json")" \
  || fail "frontier authoring refused while Astra is reachable: $receipt"
echo "$receipt" | jq -e '.profile.model_identity == "gpt-6-astra"' >/dev/null \
  || fail "frontier authoring no longer prefers Astra while it is reachable: $receipt"

ctx "$WORK/frontier.json" '["claude-opus-5-5"]' "$WORK/c-opus-only.json"
receipt="$(resolve "$POLICY" planning "$WORK/c-opus-only.json")" \
  || fail "frontier authoring has no seat when neither frontier lab is reachable: $receipt"
echo "$receipt" | jq -e '
  .profile_ref == "planning-opus"
  and .profile.role == "frontier-planning"
  and .frontier_required
' >/dev/null || fail "frontier authoring capacity route is wrong: $receipt"

# Mutation check: dropping the seat must restore the old fail-closed behaviour,
# so a silent revert of the ruling cannot pass this suite.
python3 - "$POLICY" "$WORK/no-authoring-seat.yaml" <<'PYMUT'
import sys
t = open(sys.argv[1]).read()
assert t.count("      fallbacks: [planning-opus]\n") == 1
t = t.replace("      fallbacks: [planning-opus]\n", "      fallbacks: []\n")
open(sys.argv[2], "w").write(t)
PYMUT
if out="$(resolve "$WORK/no-authoring-seat.yaml" planning "$WORK/c-opus-only.json")"; then
  fail "authoring-seat mutation still resolved; the test does not detect a revert: $out"
fi

echo "PASS: capacity fallbacks reach a distinct, frontier-appropriate seat and never the producer"
