#!/usr/bin/env bash
# Plan/code review is cross-lab first, with a declared same-lab
# capacity fallback. Resolve the worktree policy with real ic; never dispatch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="$ROOT/config/routing.yaml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
command -v ic >/dev/null || { echo "FAIL: real ic required" >&2; exit 1; }
command -v jq >/dev/null || { echo "FAIL: jq required" >&2; exit 1; }
fail() { echo "FAIL: $*" >&2; exit 1; }

printf '%s\n' '{"reasons":[],"rationale":"settled review routing coverage"}' > "$WORK/routine.json"
jq '.reasons = ["foundational-invariants"]' "$WORK/routine.json" > "$WORK/frontier.json"
checks=0
resolve() {
  ic --json route dispatch --policy="$POLICY" --role="$role" \
    --producer-identity="$1" --context-file="$2"
}
check() {
  jq -e "$2" <<< "$1" >/dev/null || fail "$role ($context): $3: $1"
  checks=$((checks + 1))
}

for context in routine frontier; do
  ctx="$WORK/$context.json"
  jq '.available_models = ["claude-opus-5-5", "claude-sonnet-5-5"]' "$ctx" > "$WORK/no-astra.json"
  for role in plan-review; do
    receipt="$(resolve claude-sonnet-5-5 "$ctx")"
    check "$receipt" '
      .profile_ref == "review-astra" and .profile.model_identity == "gpt-6-astra"
      and .fallback_reason == "cross_lab_reorder"
      and .cross_lab_reorder == {from:["review-opus","review-astra"],to:["review-astra","review-opus"]}
      and [.fallback_chain[].profile_ref] == ["review-opus"]
      and .fallback_chain[0].profile.model_identity == "claude-opus-5-5"
    ' 'Sonnet producer must prefer Astra and retain Opus'

    receipt="$(resolve claude-opus-5-5 "$ctx")"
    check "$receipt" '
      .profile_ref == "review-astra" and .fallback_reason == "producer_model_conflict"
      and ((.fallback_chain // []) | length == 0)
      and any(.excluded[]; .profile_ref == "review-opus" and .reason == "producer_model_conflict")
    ' 'Opus producer must exclude itself'

    receipt="$(resolve gpt-6-astra "$ctx")"
    check "$receipt" '
      .profile_ref == "review-opus" and .profile.model_identity == "claude-opus-5-5"
      and .fallback_reason == null and ((.fallback_chain // []) | length == 0)
      and any(.excluded[]; .profile_ref == "review-astra" and .reason == "producer_model_conflict")
    ' 'Astra producer must keep Opus first and exclude itself'

    receipt="$(resolve gpt-6.1-sol "$ctx")"
    check "$receipt" '
      .profile_ref == "review-opus" and .fallback_reason == null
      and [.fallback_chain[].profile_ref] == ["review-astra"]
    ' 'other OpenAI producer must keep Opus first'

    receipt="$(resolve claude-sonnet-5-5 "$WORK/no-astra.json")"
    check "$receipt" '
      .profile_ref == "review-opus" and .profile.model_identity == "claude-opus-5-5"
      and .fallback_reason == "reasoning_contract" and .cross_lab_reorder == null
      and ((.fallback_chain // []) | length == 0)
      and any(.excluded[]; .profile_ref == "review-astra" and .reason == "model_unavailable")
    ' 'Astra unavailable must leave Opus reachable with the capacity exclusion recorded'

    if receipt="$(resolve claude-opus-5-5 "$WORK/no-astra.json" 2>&1)"; then
      fail "$role ($context): Astra unavailable allowed an Opus self-review: $receipt"
    fi
    [[ "$receipt" == *"no eligible model satisfies reasoning contract"* ]] \
      || fail "$role ($context): unexpected refusal: $receipt"
    checks=$((checks + 1))
  done
done
echo "PASS: $checks real-ic plan review order and capacity checks"
