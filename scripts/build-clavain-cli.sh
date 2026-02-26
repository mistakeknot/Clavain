#!/usr/bin/env bash
# Build the Go clavain-cli binary.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../cmd/clavain-cli"
OUT_DIR="$SCRIPT_DIR/../bin"

if ! command -v go &>/dev/null; then
    echo "clavain-cli: Go not found — using Bash fallback" >&2
    exit 0
fi

echo "Building clavain-cli Go binary..." >&2
go build -C "$SRC_DIR" -mod=readonly -o "$OUT_DIR/clavain-cli-go" .
echo "clavain-cli-go built at $OUT_DIR/clavain-cli-go" >&2
