#!/usr/bin/env bash
# Cross-compile clavain-cli-go for all release targets.
# Produces: bin/clavain-cli-go-{os}-{arch} for each target platform.
# These binaries are checked into git and ship with the published plugin.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."
SRC_DIR="$SCRIPT_DIR/../cmd/clavain-cli"
OUT_DIR="$SCRIPT_DIR/../bin"
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/clavain-build-release.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT

# Validate build environment
if ! command -v go &>/dev/null; then
    echo "build-release: Go not found" >&2
    exit 1
fi

if [[ ! -d "$SRC_DIR" ]]; then
    echo "build-release: source dir not found at $SRC_DIR" >&2
    exit 1
fi

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "build-release: source is not a Git worktree" >&2
    exit 1
fi
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal)" ]]; then
    echo "build-release: source worktree is not clean" >&2
    exit 1
fi

# Target platforms (binaries ship with plugin for users without Go)
TARGETS=(
    "darwin:arm64"
    "linux:amd64"
    "windows:amd64"
)

built=0
artifacts=()
for target in "${TARGETS[@]}"; do
    os="${target%%:*}"
    arch="${target##*:}"
    artifact="clavain-cli-go-${os}-${arch}"
    out="$STAGE_DIR/$artifact"
    echo "Building ${os}/${arch}..." >&2
    CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" go -C "$SRC_DIR" build -trimpath -o "$out" .
    artifacts+=("$artifact")
    built=$((built + 1))
done

# Also build native binary for local use
echo "Building native binary..." >&2
go -C "$SRC_DIR" build -trimpath -o "$STAGE_DIR/clavain-cli-go" .
artifacts+=("clavain-cli-go")

# Promote only after every build succeeds. Building directly into the tracked
# bin directory makes later targets embed vcs.modified=true.
mkdir -p "$OUT_DIR"
for artifact in "${artifacts[@]}"; do
    install -m 0755 "$STAGE_DIR/$artifact" "$OUT_DIR/$artifact"
    echo "  → $OUT_DIR/$artifact ($(du -h "$OUT_DIR/$artifact" | cut -f1))" >&2
done

echo "build-release: $built platform binaries + native binary built" >&2
