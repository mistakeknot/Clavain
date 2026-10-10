#!/usr/bin/env bash
# The review-packet producer check reads `ic route identity` output. Run the
# real ic, from a directory outside any Clavain tree and with no policy
# selected in the environment, so a stub cannot hide a key mismatch
# (readers used .canonical_identity while ic returns .model_identity) or a
# missing --policy (ic exits 2 without one). Bead mk-6zieh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
command -v ic >/dev/null || { echo "FAIL: real ic required" >&2; exit 1; }
command -v jq >/dev/null || { echo "FAIL: jq required" >&2; exit 1; }
fail() { echo "FAIL: $*" >&2; exit 1; }
cd "$WORK"
clean() { env -u CLAVAIN_ROUTING_POLICY -u CLAVAIN_ROOT "$@"; }

# Without a policy, real ic fails closed: the readers must always pass one.
if clean ic --json route identity --model=opus >/dev/null 2>&1; then
  fail "real ic resolved an identity without a policy; the --policy premise changed"
fi

# The policy dispatch.sh uses by default resolves, and carries .model_identity.
out="$(clean ic --json route identity --policy="$ROOT/scripts/../config/routing.yaml" --model=opus)"
got="$(jq -r '.model_identity // empty' <<< "$out")"
[[ -n "$got" ]] || fail "real ic route identity has no .model_identity: $out"
[[ -z "$(jq -r '.canonical_identity // empty' <<< "$out")" ]] \
  || fail "ic now emits .canonical_identity too; recheck the readers: $out"

# The Python reader builds its command from _routing_policy_path(); run that
# exact policy through the real ic.
policy="$(clean python3 -I - "$ROOT" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("brp", sys.argv[1] + "/scripts/build-review-packet.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m._routing_policy_path())
PY
)"
out="$(clean ic --json route identity --policy="$policy" --model=opus)"
[[ "$(jq -r '.model_identity // empty' <<< "$out")" == "$got" ]] || fail "reader policy gave a different identity: $out"

# Neither reader may use the old key or omit the policy.
! grep -n 'canonical_identity' "$ROOT/scripts/dispatch.sh" "$ROOT/scripts/build-review-packet.py" \
  || fail "a reader still uses .canonical_identity"
[[ "$(grep -c 'route identity --policy=' "$ROOT/scripts/dispatch.sh")" == 2 ]] || fail "dispatch.sh must pass --policy at both calls"
echo "PASS: real ic route identity ($got) works from a foreign cwd with the readers' policy"
