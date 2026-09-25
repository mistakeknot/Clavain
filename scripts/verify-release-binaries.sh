#!/usr/bin/env bash
# Verify shipped platform binaries against their tracked source manifest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/bin/release-manifest.json"

# Two failure classes, two exit codes, because they mean opposite things.
#
#   die (exit 1)         the verifier LOOKED and the artifacts do not match.
#   unavailable (exit 3) the verifier could not look at all — a missing tool,
#                        an unresolvable module replacement. Says nothing about
#                        the artifacts.
#
# Collapsing these told operators "release artifacts are stale" on machines that
# had simply never been able to check (mk-cg3z). Exit 3 is the reserved code
# intercore's internal/publish/release.go maps to ErrReleaseVerifierUnavailable;
# keep the two in step if either moves.
die() {
    echo "verify-release-binaries: $*" >&2
    exit 1
}

unavailable() {
    echo "verify-release-binaries: $*" >&2
    exit 3
}

hash_file() {
    local path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$path" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$path" | awk '{print $1}'
    else
        unavailable "sha256sum or shasum is required"
    fi
}

resolve_intercore_root() {
    local root
    # Environment, not staleness: a checkout laid out so the replacement cannot
    # resolve (a worktree outside the tree, say) has told us nothing about the
    # binaries.
    root="$(GOENV=off GOWORK=off GOFLAGS='' go -C "$REPO_ROOT/cmd/clavain-cli" list -m -f '{{with .Replace}}{{.Dir}}{{end}}' github.com/mistakeknot/intercore)" ||
        unavailable "cannot resolve the Intercore module replacement"
    [[ -n "$root" && -d "$root" ]] ||
        unavailable "github.com/mistakeknot/intercore must use a local module replacement"
    (cd "$root" && pwd)
}

command -v git >/dev/null 2>&1 || unavailable "git is required"
command -v go >/dev/null 2>&1 || unavailable "go is required"
command -v jq >/dev/null 2>&1 || unavailable "jq is required"
[[ -f "$MANIFEST" ]] || die "manifest is missing"

jq -e '
  def valid_artifact($key; $path; $goos; $goarch):
    .artifacts[$key] as $artifact |
    ($artifact | type) == "object" and
    ($artifact | keys | sort) == ["goarch", "goos", "path", "sha256"] and
    $artifact.path == $path and
    $artifact.goos == $goos and
    $artifact.goarch == $goarch and
    ($artifact.sha256 | type) == "string" and
    ($artifact.sha256 | test("^[0-9a-f]{64}$"));

  type == "object" and
  .schema_version == 1 and
  (.source_revision | type) == "string" and
  (.source_revision | test("^[0-9a-f]{40}$")) and
  (.intercore_revision | type) == "string" and
  (.intercore_revision | test("^[0-9a-f]{40}$")) and
  (.go_version | type) == "string" and
  (.go_version | startswith("go")) and
  (.artifacts | type) == "object" and
  (.artifacts | keys | sort) == ["darwin-arm64", "linux-amd64", "windows-amd64"] and
  valid_artifact("darwin-arm64"; "bin/clavain-cli-go-darwin-arm64"; "darwin"; "arm64") and
  valid_artifact("linux-amd64"; "bin/clavain-cli-go-linux-amd64"; "linux"; "amd64") and
  valid_artifact("windows-amd64"; "bin/clavain-cli-go-windows-amd64"; "windows"; "amd64")
' "$MANIFEST" >/dev/null || die "manifest schema is invalid"

source_revision="$(jq -r '.source_revision' "$MANIFEST")"
intercore_revision="$(jq -r '.intercore_revision' "$MANIFEST")"
go_version="$(jq -r '.go_version' "$MANIFEST")"
git -C "$REPO_ROOT" cat-file -e "${source_revision}^{commit}" 2>/dev/null ||
    die "source revision is not present"
git -C "$REPO_ROOT" merge-base --is-ancestor "$source_revision" HEAD ||
    die "source revision is not an ancestor of HEAD"
git -C "$REPO_ROOT" diff --quiet "$source_revision"..HEAD -- cmd/clavain-cli ||
    die "CLI source changed after release build"

intercore_root="$(resolve_intercore_root)"
git -C "$intercore_root" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    unavailable "Intercore replacement is not a Git worktree"
git -C "$intercore_root" cat-file -e "${intercore_revision}^{commit}" 2>/dev/null ||
    die "Intercore pinned revision is not present in the checkout"
[[ -z "$(git -C "$intercore_root" status --porcelain=v1 --untracked-files=normal)" ]] ||
    die "Intercore worktree is not clean"

# zklw autosync auto-commits into the linked Intercore checkout on its own
# schedule, including docs-only and internal/-only commits that no Clavain
# binary imports. Requiring HEAD == intercore_revision (mk-y5de, 2026-09-25)
# meant every such commit re-broke Clavain publication even though the
# binaries embed a build tag pinning the exact revision (checked below) and
# nothing they actually import had changed. Fall through to a content check
# over clavain-cli's real Intercore dependency tree instead of HEAD equality:
# a commit outside that tree changes nothing this release ships.
actual_intercore_revision="$(git -C "$intercore_root" rev-parse HEAD)"
if [[ "$actual_intercore_revision" != "$intercore_revision" ]]; then
    git -C "$intercore_root" merge-base --is-ancestor "$intercore_revision" "$actual_intercore_revision" 2>/dev/null ||
        die "Intercore pinned revision is not an ancestor of the checkout HEAD"

    # Module files sit outside every package directory but still decide which
    # third-party versions the release links.
    git -C "$intercore_root" diff --quiet "$intercore_revision".."$actual_intercore_revision" -- go.mod go.sum ||
        die "Intercore go.mod/go.sum changed between the pinned revision and checkout HEAD"

    # Resolve imports per shipped platform with the release build tag: a
    # host-only listing would miss darwin- or windows-only Intercore imports.
    imported_pkgs=""
    for target in linux/amd64 darwin/arm64 windows/amd64; do
        target_pkgs="$(GOENV=off GOWORK=off GOFLAGS='' GOOS="${target%/*}" GOARCH="${target#*/}" \
            go -C "$REPO_ROOT/cmd/clavain-cli" list -deps -tags="intercore_rev_$intercore_revision" . 2>/dev/null)" ||
            unavailable "cannot resolve Clavain's Intercore package imports for $target"
        imported_pkgs+="$(printf '%s\n' "$target_pkgs" | grep '^github.com/mistakeknot/intercore/' || true)"$'\n'
    done
    imported_pkgs="$(printf '%s' "$imported_pkgs" | sort -u | sed '/^$/d')"
    [[ -n "$imported_pkgs" ]] || unavailable "clavain-cli imports no Intercore packages to diff"

    while IFS= read -r pkg; do
        [[ -n "$pkg" ]] || continue
        pkg_dir="$(GOENV=off GOWORK=off GOFLAGS='' go -C "$REPO_ROOT/cmd/clavain-cli" list -f '{{.Dir}}' -e "$pkg" 2>/dev/null)" ||
            unavailable "cannot resolve directory for $pkg"
        pkg_dir="$(cd "$pkg_dir" 2>/dev/null && pwd)" || unavailable "$pkg directory does not exist"
        rel_dir="${pkg_dir#"$intercore_root"/}"
        [[ "$rel_dir" != "$pkg_dir" ]] ||
            unavailable "$pkg resolved outside the pinned Intercore checkout"
        git -C "$intercore_root" diff --quiet "$intercore_revision".."$actual_intercore_revision" -- "$rel_dir" ||
            die "Intercore package $pkg changed between the pinned revision and checkout HEAD"
    done <<<"$imported_pkgs"
fi

artifact_rows="$(jq -er '.artifacts | to_entries[] | [.key, .value.path, .value.sha256, .value.goos, .value.goarch] | @tsv' "$MANIFEST")" ||
    die "cannot read artifact manifest entries"
artifact_count="$(printf '%s\n' "$artifact_rows" | awk 'NF { count++ } END { print count + 0 }')"
[[ "$artifact_count" -eq 3 ]] || die "manifest must contain exactly 3 artifacts"

verified_count=0
while IFS=$'\t' read -r platform path expected_digest goos goarch; do
    case "$path" in
        "bin/clavain-cli-go-$platform") ;;
        *) die "unsafe or mismatched artifact path for $platform" ;;
    esac
    artifact="$REPO_ROOT/$path"
    [[ -f "$artifact" && -x "$artifact" ]] || die "$platform artifact is missing or not executable"
    actual_digest="$(hash_file "$artifact")"
    [[ "$actual_digest" == "$expected_digest" ]] || die "$platform digest mismatch"

    metadata="$(GOENV=off GOWORK=off GOFLAGS='' go version -m "$artifact")" || die "$platform build metadata is unreadable"
    binary_go_version="$(printf '%s\n' "$metadata" | awk 'NR == 1 { print $2 }')"
    [[ "$binary_go_version" == "$go_version" ]] || die "$platform Go version mismatch"
    [[ "$metadata" == *$'\tbuild\tvcs.revision='"$source_revision"* ]] ||
        die "$platform source revision mismatch"
    [[ "$metadata" == *$'\tbuild\tvcs.modified=false'* ]] ||
        die "$platform was built from a modified worktree"
    [[ "$metadata" == *$'\tbuild\t-trimpath=true'* ]] ||
        die "$platform is missing trimpath"
    [[ $'\n'"$metadata"$'\n' == *$'\n\tbuild\t-tags=intercore_rev_'"$intercore_revision"$'\n'* ]] ||
        die "$platform Intercore revision mismatch"
    [[ $'\n'"$metadata"$'\n' == *$'\n\tbuild\tGOOS='"$goos"$'\n'* ]] || die "$platform GOOS mismatch"
    [[ $'\n'"$metadata"$'\n' == *$'\n\tbuild\tGOARCH='"$goarch"$'\n'* ]] || die "$platform GOARCH mismatch"
    verified_count=$((verified_count + 1))
done <<<"$artifact_rows"
[[ "$verified_count" -eq 3 ]] || die "verified artifact count mismatch"

jq -cn \
    --arg source_revision "$source_revision" \
    --arg intercore_revision "$intercore_revision" \
    '{schema_version:1,verified:true,source_revision:$source_revision,intercore_revision:$intercore_revision,artifact_count:3}'
