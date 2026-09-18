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

CLAUDE_LANE='["claude-opus-5","claude-sonnet-5","claude-fable-5-1","kimi-code/k3"]'
NO_ASTRA='["gpt-5.6-sol","claude-opus-5","claude-sonnet-5","claude-fable-5-1","kimi-code/k3"]'

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
check_primary plan-review         "$WORK/c-front.json"   review-fable gpt-6-astra
check_primary plan-review         "$WORK/c-front.json"   review-astra claude-fable-5-1
check_primary validation          "$WORK/c-front.json"   validation-opus gpt-5.6-sol

# ---------------------------------------------------------------------------
# 2. A Fable-authored plan-review resolves to a DISTINCT FRONTIER model under an
#    Astra capacity failure. This is the hole the bead exists to close: before
#    mk-9yyt it resolved planning-astra with an EMPTY fallback_chain, so an Astra
#    outage stopped the gate dead.
# ---------------------------------------------------------------------------
ctx "$WORK/frontier.json" "$CLAUDE_LANE" "$WORK/c-codex-down.json"
receipt="$(resolve "$POLICY" plan-review "$WORK/c-codex-down.json" claude-fable-5-1)" \
  || fail "Fable-authored plan-review has no reviewer under an Astra outage: $receipt"
echo "$receipt" | jq -e '
  .profile.backend == "claude"
  and .profile.model_identity != .producer_model
  and .validator_relationship == "different-model"
  and (.excluded | map(.reason) | index("producer_model_conflict") != null)
' >/dev/null || fail "Fable-authored plan-review capacity route is wrong: $receipt"

frontier_models="$(python3 - "$POLICY" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
print(" ".join((cfg.get("reasoning") or {}).get("frontier_models") or []))
PY
)"
selected="$(echo "$receipt" | jq -r '.profile.model_identity')"
[[ " $frontier_models " == *" $selected "* ]] \
  || fail "plan-review capacity fallback $selected is not frontier-eligible"

# Astra alone down (Sol still up) must reach the same distinct frontier reviewer.
ctx "$WORK/frontier.json" "$NO_ASTRA" "$WORK/c-no-astra.json"
receipt="$(resolve "$POLICY" plan-review "$WORK/c-no-astra.json" claude-fable-5-1)" \
  || fail "Fable-authored plan-review stalled with only Astra down: $receipt"
echo "$receipt" | jq -e '.profile.model_identity != .producer_model' >/dev/null \
  || fail "plan-review resolved to its own producer"

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
#    explicitly SELECTS review-fable with Fable as producer still has to exclude
#    it. If this ever passes, an escape hatch was added below the policy layer.
# ---------------------------------------------------------------------------
sed 's/^    plan-review: .*/    plan-review: review-fable/' "$POLICY" > "$WORK/select-fable.yaml"
receipt="$(resolve "$WORK/select-fable.yaml" plan-review "$WORK/c-front.json" claude-fable-5-1)" \
  || fail "self-review snapshot failed for the wrong reason: $receipt"
echo "$receipt" | jq -e '
  (.excluded | map(select(.profile_ref == "review-fable" and .reason == "producer_model_conflict")) | length == 1)
  and .profile_ref != "review-fable"
' >/dev/null || fail "reviewer separation weakened: Fable was admitted to review Fable"

# ---------------------------------------------------------------------------
# 6. TWO GATES, NOT ONE. Selecting a substitute without frontier eligibility must
#    still be refused: eligibility (reasoning.frontier_models) and selection
#    (dispatch.roles + fallbacks) are separate mechanisms.
# ---------------------------------------------------------------------------
sed 's/^  frontier_models: .*/  frontier_models: [gpt-6-astra, claude-fable-5-1]/' "$POLICY" > "$WORK/no-eligibility.yaml"
if out="$(resolve "$WORK/no-eligibility.yaml" plan-review "$WORK/c-codex-down.json" claude-fable-5-1)"; then
  fail "plan-review resolved without frontier eligibility for the substitute: $out"
fi
[[ "$out" == *"no eligible model satisfies reasoning contract"* ]] \
  || fail "unexpected refusal for a selection-only substitute: $out"

echo "PASS: capacity fallbacks reach a distinct, frontier-appropriate seat and never the producer"
