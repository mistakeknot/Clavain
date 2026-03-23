#!/usr/bin/env bash
# Cross-compile clavain-cli-go for all release targets.
# Produces: bin/clavain-cli-go-{os}-{arch} for each target platform.
# These binaries are checked into git and ship with the published plugin.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../cmd/clavain-cli"
OUT_DIR="$SCRIPT_DIR/../bin"

# Validate build environment
if ! command -v go &>/dev/null; then
    echo "build-release: Go not found" >&2
    exit 1
fi

if [[ ! -d "$SRC_DIR" ]]; then
    echo "build-release: source dir not found at $SRC_DIR" >&2
    exit 1
fi

# Target platforms (binaries ship with plugin for users without Go)
TARGETS=(
    "darwin:arm64"
    "linux:amd64"
    "windows:amd64"
)

built=0
for target in "${TARGETS[@]}"; do
    os="${target%%:*}"
    arch="${target##*:}"
    out="$OUT_DIR/clavain-cli-go-${os}-${arch}"
    echo "Building ${os}/${arch}..." >&2
    CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" go build -C "$SRC_DIR" -o "$out" .
    chmod +x "$out"
    echo "  → $out ($(du -h "$out" | cut -f1))" >&2
    built=$((built + 1))
done

# Also build native binary for local use
echo "Building native binary..." >&2
go build -C "$SRC_DIR" -o "$OUT_DIR/clavain-cli-go" .
echo "  → $OUT_DIR/clavain-cli-go" >&2

echo "build-release: $built platform binaries + native binary built" >&2
