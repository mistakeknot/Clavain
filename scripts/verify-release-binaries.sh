#!/usr/bin/env bash
# Verify shipped platform binaries against their tracked source manifest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/bin/release-manifest.json"

die() {
    echo "verify-release-binaries: $*" >&2
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

command -v git >/dev/null 2>&1 || die "git is required"
command -v go >/dev/null 2>&1 || die "go is required"
command -v jq >/dev/null 2>&1 || die "jq is required"
[[ -f "$MANIFEST" ]] || die "manifest is missing"

jq -e '
  .schema_version == 1 and
  (.source_revision | test("^[0-9a-f]{40}$")) and
  (.intercore_revision | test("^[0-9a-f]{40}$")) and
  (.go_version | type == "string" and startswith("go")) and
  (.artifacts | keys | sort) == ["darwin-arm64", "linux-amd64", "windows-amd64"]
' "$MANIFEST" >/dev/null || die "manifest schema is invalid"

source_revision="$(jq -r '.source_revision' "$MANIFEST")"
intercore_revision="$(jq -r '.intercore_revision' "$MANIFEST")"
git -C "$REPO_ROOT" cat-file -e "${source_revision}^{commit}" 2>/dev/null ||
    die "source revision is not present"
git -C "$REPO_ROOT" merge-base --is-ancestor "$source_revision" HEAD ||
    die "source revision is not an ancestor of HEAD"

while IFS=$'\t' read -r platform path expected_digest goos goarch; do
    case "$path" in
        "bin/clavain-cli-go-$platform") ;;
        *) die "unsafe or mismatched artifact path for $platform" ;;
    esac
    artifact="$REPO_ROOT/$path"
    [[ -f "$artifact" && -x "$artifact" ]] || die "$platform artifact is missing or not executable"
    actual_digest="$(hash_file "$artifact")"
    [[ "$actual_digest" == "$expected_digest" ]] || die "$platform digest mismatch"

    metadata="$(go version -m "$artifact")" || die "$platform build metadata is unreadable"
    [[ "$metadata" == *$'\tbuild\tvcs.revision='"$source_revision"* ]] ||
        die "$platform source revision mismatch"
    [[ "$metadata" == *$'\tbuild\tvcs.modified=false'* ]] ||
        die "$platform was built from a modified worktree"
    [[ "$metadata" == *$'\tbuild\t-trimpath=true'* ]] ||
        die "$platform is missing trimpath"
    [[ "$metadata" == *$'\tbuild\tGOOS='"$goos"* ]] || die "$platform GOOS mismatch"
    [[ "$metadata" == *$'\tbuild\tGOARCH='"$goarch"* ]] || die "$platform GOARCH mismatch"
done < <(jq -r '.artifacts | to_entries[] | [.key, .value.path, .value.sha256, .value.goos, .value.goarch] | @tsv' "$MANIFEST")

jq -cn \
    --arg source_revision "$source_revision" \
    --arg intercore_revision "$intercore_revision" \
    '{schema_version:1,verified:true,source_revision:$source_revision,intercore_revision:$intercore_revision,artifact_count:3}'
