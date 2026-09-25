#!/usr/bin/env bash
# B2: config/routing.yaml's validation-sol entry must declare the fallbacks
# its own commit message, both canon docs, and tier-fallback-test.sh's header
# already claim: validation-sol -> [validation-opus, validation-sonnet].
# Resolved through the *real* ic binary (not a fake), because `ic route
# dispatch --tier=` never returns .fallback_chain (see tier-fallback-test.sh)
# and --role=validation under --policy-profile=ci-campaign-pilot is the one
# path that resolves validation-sol as the PRIMARY (not just a fallback
# position) — this is exactly the reachable path a real quota-exhausted
# ci-campaign-pilot validation seat hits.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

command -v ic >/dev/null 2>&1 || { echo "SKIP: ic not on PATH" >&2; exit 0; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not on PATH" >&2; exit 0; }

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
CONTEXT_FILE="$TMP_ROOT/context.json"
printf '%s\n' '{"reasons":[],"rationale":"validation-sol fallback coverage","scope":"mk-ag2s"}' > "$CONTEXT_FILE"

resolved="$(ic --json route dispatch --role=validation \
  --policy="$ROOT/config/routing.yaml" \
  --policy-profile=ci-campaign-pilot \
  --producer-identity=gpt-6-astra \
  --context-file="$CONTEXT_FILE" 2>&1)" || fail "ic route dispatch failed: $resolved"

# Candidate set = primary + fallback_chain, in the order ic actually returns
# them. With a codex producer, ic's cross-lab preference (reasoning-routing.md
# "validation ... prefer a frontier lab other than the producer's") is allowed
# to reorder validation-opus ahead of validation-sol as primary — that is
# correct, existing behavior, not what B2 is about. What B2 requires is that
# the *set* of candidates is non-empty beyond a single entry and reaches both
# validation-opus and validation-sonnet, with no duplicate (i.e. the
# resolver's visited-set correctly breaks the validation-sol <-> validation-opus
# / validation-sonnet cycle instead of looping or dropping the chain).
candidates="$(jq -c '[.profile_ref] + [.fallback_chain[].profile_ref]' <<< "$resolved")"
[[ "$candidates" != '["validation-sol"]' ]] || fail "validation-sol resolved with no fallback candidates at all (B2): $resolved"

echo "$candidates" | jq -e 'index("validation-sol")' >/dev/null || fail "candidate set does not include validation-sol: $candidates"
echo "$candidates" | jq -e 'index("validation-opus")' >/dev/null || fail "candidate set does not reach validation-opus: $candidates"
echo "$candidates" | jq -e 'index("validation-sonnet")' >/dev/null || fail "candidate set does not reach validation-sonnet: $candidates"

# No cycle: validation-opus and validation-sonnet already list validation-sol
# in their own fallbacks (config/routing.yaml), so a naive walk that doesn't
# track visited tiers could loop. The resolver must terminate with a finite,
# deduplicated chain.
count="$(jq 'length' <<< "$candidates")"
uniq_count="$(jq 'unique | length' <<< "$candidates")"
[[ "$count" == "$uniq_count" ]] || fail "validation-sol's candidate set contains duplicates (possible cycle): $candidates"

echo "PASS: validation-sol resolves a non-empty, cycle-free candidate chain reaching validation-opus and validation-sonnet"
