#!/usr/bin/env bash
# Cross-compile clavain-cli-go for all release targets.
# Produces: bin/clavain-cli-go-{os}-{arch} for each target platform.
# These binaries are checked into git and ship with the published plugin.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/cmd/clavain-cli"
OUT_DIR="$REPO_ROOT/bin"
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/clavain-build-release.XXXXXX")"
LOCK_DIR=""
LOCK_HELD=0

cleanup() {
    if [[ "$LOCK_HELD" -eq 1 ]]; then
        rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
    fi
    rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

die() {
    echo "build-release: $*" >&2
    exit 1
}

hash_file() {
    local path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$path" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$path" | awk '{print $1}'
    else
        die "sha256sum or shasum is required"
    fi
}

resolve_intercore_root() {
    local root
    root="$(GOWORK=off GOFLAGS='' go -C "$SRC_DIR" list -m -f '{{with .Replace}}{{.Dir}}{{end}}' github.com/mistakeknot/intercore)" ||
        die "cannot resolve the Intercore module replacement"
    [[ -n "$root" && -d "$root" ]] ||
        die "github.com/mistakeknot/intercore must use a local module replacement"
    (cd "$root" && pwd)
}

# Validate build environment
if ! command -v go &>/dev/null; then
    die "Go not found"
fi
command -v git >/dev/null 2>&1 || die "git is required"
command -v jq >/dev/null 2>&1 || die "jq is required"

if [[ ! -d "$SRC_DIR" ]]; then
    die "source dir not found at $SRC_DIR"
fi

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "source is not a Git worktree"
fi
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal)" ]]; then
    die "source worktree is not clean"
fi

GIT_COMMON_DIR="$(git -C "$REPO_ROOT" rev-parse --git-common-dir)"
if [[ "$GIT_COMMON_DIR" != /* ]]; then
    GIT_COMMON_DIR="$REPO_ROOT/$GIT_COMMON_DIR"
fi
GIT_COMMON_DIR="$(cd "$GIT_COMMON_DIR" && pwd)"
LOCK_DIR="$GIT_COMMON_DIR/clavain-build-release.lock"
mkdir "$LOCK_DIR" 2>/dev/null ||
    die "another release build holds $LOCK_DIR"
LOCK_HELD=1

INTERCORE_ROOT="$(resolve_intercore_root)"
if ! git -C "$INTERCORE_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Intercore replacement is not a Git worktree"
fi
if [[ -n "$(git -C "$INTERCORE_ROOT" status --porcelain=v1 --untracked-files=normal)" ]]; then
    die "Intercore worktree is not clean"
fi

SOURCE_REVISION="$(git -C "$REPO_ROOT" rev-parse HEAD)"
INTERCORE_REVISION="$(git -C "$INTERCORE_ROOT" rev-parse HEAD)"
GO_VERSION="$(GOWORK=off GOFLAGS='' go version | awk '{print $3}')"
[[ "$SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]] || die "invalid source revision"
[[ "$INTERCORE_REVISION" =~ ^[0-9a-f]{40}$ ]] || die "invalid Intercore revision"
[[ "$GO_VERSION" == go* ]] || die "invalid Go version"
INTERCORE_BUILD_TAG="intercore_rev_$INTERCORE_REVISION"

# Compile from detached local clones so concurrent edits to either live checkout
# cannot enter an artifact carrying the captured commit attestations.
CLAVAIN_SNAPSHOT="$STAGE_DIR/source/os/Clavain"
INTERCORE_SNAPSHOT="$STAGE_DIR/source/core/intercore"
mkdir -p "$(dirname "$CLAVAIN_SNAPSHOT")" "$(dirname "$INTERCORE_SNAPSHOT")"
git clone --quiet --shared --no-checkout "$REPO_ROOT" "$CLAVAIN_SNAPSHOT" ||
    die "cannot create immutable source snapshot"
git -C "$CLAVAIN_SNAPSHOT" checkout --quiet --detach "$SOURCE_REVISION" ||
    die "cannot select immutable source revision"
git clone --quiet --shared --no-checkout "$INTERCORE_ROOT" "$INTERCORE_SNAPSHOT" ||
    die "cannot create immutable Intercore snapshot"
git -C "$INTERCORE_SNAPSHOT" checkout --quiet --detach "$INTERCORE_REVISION" ||
    die "cannot select immutable Intercore revision"
BUILD_SRC_DIR="$CLAVAIN_SNAPSHOT/cmd/clavain-cli"
[[ -d "$BUILD_SRC_DIR" ]] || die "snapshot source dir is missing"

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
    GOWORK=off GOFLAGS='' CGO_ENABLED=0 GOOS="$os" GOARCH="$arch" \
        go -C "$BUILD_SRC_DIR" build -trimpath -tags "$INTERCORE_BUILD_TAG" -o "$out" .
    artifacts+=("$artifact")
    built=$((built + 1))
done

# Also build native binary for local use
echo "Building native binary..." >&2
GOWORK=off GOFLAGS='' go -C "$BUILD_SRC_DIR" build -trimpath -tags "$INTERCORE_BUILD_TAG" -o "$STAGE_DIR/clavain-cli-go" .
artifacts+=("clavain-cli-go")

# A compiler invocation must not race source edits after the preflight. The
# manifest records the exact commits that produced the staged artifacts.
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$SOURCE_REVISION" ]] ||
    die "source revision changed during build"
[[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] ||
    die "source worktree changed during build"
[[ "$(git -C "$INTERCORE_ROOT" rev-parse HEAD)" == "$INTERCORE_REVISION" ]] ||
    die "Intercore revision changed during build"
[[ -z "$(git -C "$INTERCORE_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] ||
    die "Intercore worktree changed during build"

DARWIN_SHA="$(hash_file "$STAGE_DIR/clavain-cli-go-darwin-arm64")" ||
    die "cannot hash darwin-arm64 artifact"
LINUX_SHA="$(hash_file "$STAGE_DIR/clavain-cli-go-linux-amd64")" ||
    die "cannot hash linux-amd64 artifact"
WINDOWS_SHA="$(hash_file "$STAGE_DIR/clavain-cli-go-windows-amd64")" ||
    die "cannot hash windows-amd64 artifact"
for digest in "$DARWIN_SHA" "$LINUX_SHA" "$WINDOWS_SHA"; do
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || die "invalid artifact digest"
done

jq -n \
    --arg source_revision "$SOURCE_REVISION" \
    --arg intercore_revision "$INTERCORE_REVISION" \
    --arg go_version "$GO_VERSION" \
    --arg darwin_sha "$DARWIN_SHA" \
    --arg linux_sha "$LINUX_SHA" \
    --arg windows_sha "$WINDOWS_SHA" \
    '{
      schema_version: 1,
      source_revision: $source_revision,
      intercore_revision: $intercore_revision,
      go_version: $go_version,
      artifacts: {
        "darwin-arm64": {
          path: "bin/clavain-cli-go-darwin-arm64",
          sha256: $darwin_sha,
          goos: "darwin",
          goarch: "arm64"
        },
        "linux-amd64": {
          path: "bin/clavain-cli-go-linux-amd64",
          sha256: $linux_sha,
          goos: "linux",
          goarch: "amd64"
        },
        "windows-amd64": {
          path: "bin/clavain-cli-go-windows-amd64",
          sha256: $windows_sha,
          goos: "windows",
          goarch: "amd64"
        }
      }
    }' >"$STAGE_DIR/release-manifest.json"

# Promote only after every build succeeds. Building directly into the tracked
# bin directory makes later targets embed vcs.modified=true.
mkdir -p "$OUT_DIR"
for artifact in "${artifacts[@]}"; do
    install -m 0755 "$STAGE_DIR/$artifact" "$OUT_DIR/$artifact"
    echo "  → $OUT_DIR/$artifact ($(du -h "$OUT_DIR/$artifact" | cut -f1))" >&2
done
install -m 0644 "$STAGE_DIR/release-manifest.json" "$OUT_DIR/release-manifest.json"

echo "build-release: $built platform binaries + native binary built" >&2
