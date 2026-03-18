#!/usr/bin/env bash
# Build the Go clavain-cli binary.
# Must be run from the monorepo source tree (not plugin cache) because
# go.mod replace directives use monorepo-relative paths.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../cmd/clavain-cli"
OUT_DIR="$SCRIPT_DIR/../bin"

if ! command -v go &>/dev/null; then
    echo "clavain-cli: Go not found — using Bash fallback" >&2
    exit 0
fi

if [[ ! -d "$SRC_DIR" ]]; then
    echo "clavain-cli: source dir not found at $SRC_DIR" >&2
    exit 1
fi

# Verify replace directive targets exist (they won't in plugin cache)
if ! grep -q '^replace' "$SRC_DIR/go.mod" 2>/dev/null; then
    echo "Building clavain-cli Go binary..." >&2
    go build -C "$SRC_DIR" -o "$OUT_DIR/clavain-cli-go" .
    echo "clavain-cli-go built at $OUT_DIR/clavain-cli-go" >&2
    exit 0
fi

# Check that replace targets resolve from the source tree
local_ok=true
while IFS= read -r line; do
    target="${line##*=> }"
    # Resolve relative path from go.mod directory
    resolved="$SRC_DIR/$target"
    if [[ ! -d "$resolved" ]]; then
        echo "clavain-cli: replace target missing: $target (resolved: $resolved)" >&2
        local_ok=false
    fi
done < <(grep '^replace ' "$SRC_DIR/go.mod" | grep '=>')

if [[ "$local_ok" != "true" ]]; then
    echo "clavain-cli: cannot build — replace directive targets missing (run from monorepo)" >&2
    exit 1
fi

echo "Building clavain-cli Go binary..." >&2
go build -C "$SRC_DIR" -o "$OUT_DIR/clavain-cli-go" .
echo "clavain-cli-go built at $OUT_DIR/clavain-cli-go" >&2
