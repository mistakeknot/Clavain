#!/usr/bin/env bash
# The review-packet producer check reads `ic route identity` output. Run the
# real ic so a stub cannot hide a key mismatch (mk-6zieh: readers used
# .canonical_identity while ic returns .model_identity).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CLAVAIN_ROUTING_POLICY="$ROOT/config/routing.yaml"
command -v ic >/dev/null || { echo "FAIL: real ic required" >&2; exit 1; }
command -v jq >/dev/null || { echo "FAIL: jq required" >&2; exit 1; }
fail() { echo "FAIL: $*" >&2; exit 1; }

out="$(ic --json route identity --model=opus)"
got="$(jq -r '.model_identity // empty' <<< "$out")"
[[ -n "$got" ]] || fail "real ic route identity has no .model_identity: $out"
[[ "$(jq -r '.canonical_identity // empty' <<< "$out")" == "" ]] \
  || fail "ic now emits .canonical_identity; update the readers: $out"

# Every reader must use the key the real ic emits.
if grep -n 'canonical_identity' "$ROOT/scripts/dispatch.sh" "$ROOT/scripts/build-review-packet.py"; then
  fail "a reader still uses .canonical_identity"
fi
grep -q '\.model_identity // empty' "$ROOT/scripts/dispatch.sh" || fail "dispatch.sh does not read .model_identity"
grep -q 'identity.get("model_identity")' "$ROOT/scripts/build-review-packet.py" || fail "build-review-packet.py does not read model_identity"
echo "PASS: real ic route identity shape ($got) matches the review-packet readers"
