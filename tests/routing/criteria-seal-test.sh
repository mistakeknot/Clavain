#!/usr/bin/env bash
# fc5.3 acceptance: write-once seal + tamper detection via clavain-cli.
set -euo pipefail
CLI="${CLAVAIN_CLI:-$(cd "$(dirname "$0")/../.." && pwd)/bin/clavain-cli}"
command -v "$CLI" >/dev/null || CLI="clavain-cli"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
f="$tmp/plan.criteria.md"
echo "1. thing holds" > "$f"

# Build a throwaway binary if bin/ is stale: prefer `go run`.
# go.mod for this module lives at cmd/clavain-cli/go.mod (not the repo root),
# so `go run` must be invoked from that directory.
run_cli() { (cd "$(dirname "$0")/../../cmd/clavain-cli" && go run . "$@"); }

run_cli set-artifact test-bead-fc53 acceptance-criteria "$f" || { echo "FAIL: first seal errored"; exit 1; }
[[ -f "$f.seal" ]] || { echo "FAIL: no seal sidecar"; exit 1; }
run_cli verify-seal "$f" || { echo "FAIL: fresh seal does not verify"; exit 1; }

echo "2. sneaky edit" >> "$f"
if run_cli set-artifact test-bead-fc53 acceptance-criteria "$f" 2>/dev/null; then
  echo "FAIL: re-register after edit should refuse"; exit 1
fi
run_cli verify-seal "$f" 2>/dev/null && { echo "FAIL: tamper not detected"; exit 1; }
CLAVAIN_RESEAL=1 run_cli set-artifact test-bead-fc53 acceptance-criteria "$f" || { echo "FAIL: explicit reseal refused"; exit 1; }
run_cli verify-seal "$f" || { echo "FAIL: reseal does not verify"; exit 1; }
echo "PASS: criteria seal suite"
