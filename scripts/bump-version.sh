#!/bin/bash
#
# Bump version across plugin.json and marketplace, commit, push.
#
# Usage:
#   scripts/bump-version.sh 0.5.0
#   scripts/bump-version.sh 0.5.0 --dry-run

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
MARKETPLACE_ROOT="$REPO_ROOT/../interagency-marketplace"
DRY_RUN=false

if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; NC=''
fi

usage() {
    echo "Usage: $0 <version> [--dry-run]"
    echo "  version   Semver string, e.g. 0.5.0"
    echo "  --dry-run Show what would change without writing"
    exit 1
}

VERSION=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage ;;
        *) VERSION="$arg" ;;
    esac
done

[ -z "$VERSION" ] && usage

if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
    echo -e "${RED}Error: '$VERSION' doesn't look like a valid version (expected X.Y.Z)${NC}" >&2
    exit 1
fi

CURRENT=$(grep -E '"version"' "$REPO_ROOT/.claude-plugin/plugin.json" | sed 's/.*"\([0-9][^"]*\)".*/\1/')
echo "Current version: $CURRENT"
echo "New version:     $VERSION"

if [ "$CURRENT" = "$VERSION" ]; then
    echo -e "${YELLOW}Already at $VERSION — nothing to do.${NC}"
    exit 0
fi

if [ ! -f "$MARKETPLACE_ROOT/.claude-plugin/marketplace.json" ]; then
    echo -e "${RED}Error: Marketplace repo not found at $MARKETPLACE_ROOT${NC}" >&2
    exit 1
fi

echo ""

update_file() {
    local file="$1" pattern="$2" replacement="$3" label="$4"
    if $DRY_RUN; then
        echo -e "  ${YELLOW}[dry-run]${NC} $label"
    else
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|$pattern|$replacement|" "$file"
        else
            sed -i "s|$pattern|$replacement|" "$file"
        fi
        echo -e "  ${GREEN}Updated${NC} $label"
    fi
}

update_file \
    "$REPO_ROOT/.claude-plugin/plugin.json" \
    "\"version\": \"$CURRENT\"" \
    "\"version\": \"$VERSION\"" \
    ".claude-plugin/plugin.json"

MARKETPLACE_CURRENT=$(grep -A10 '"clavain"' "$MARKETPLACE_ROOT/.claude-plugin/marketplace.json" | grep '"version"' | sed 's/.*"\([0-9][^"]*\)".*/\1/')
update_file \
    "$MARKETPLACE_ROOT/.claude-plugin/marketplace.json" \
    "\"version\": \"$MARKETPLACE_CURRENT\"" \
    "\"version\": \"$VERSION\"" \
    "interagency-marketplace/marketplace.json (clavain entry)"

if $DRY_RUN; then
    echo -e "\n${YELLOW}Dry run complete. No files changed.${NC}"
    exit 0
fi

echo ""
cd "$REPO_ROOT"
git add .claude-plugin/plugin.json
git commit -m "chore: bump version to $VERSION"
git push
echo -e "${GREEN}Pushed Clavain${NC}"

cd "$MARKETPLACE_ROOT"
git add .claude-plugin/marketplace.json
git commit -m "chore: bump clavain to v$VERSION"
git push
echo -e "${GREEN}Pushed interagency-marketplace${NC}"

# Invalidate stale plugin cache versions so next session loads the new one.
# Claude Code caches each version in ~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/.
# Old versions linger and can be loaded instead of the new one.
CACHE_DIR="$HOME/.claude/plugins/cache/interagency-marketplace/clavain"
if [ -d "$CACHE_DIR" ]; then
    stale=0
    for dir in "$CACHE_DIR"/*/; do
        [ -d "$dir" ] || continue
        dirname="$(basename "$dir")"
        if [ "$dirname" != "$VERSION" ]; then
            rm -rf "$dir"
            stale=$((stale + 1))
        fi
    done
    if [ "$stale" -gt 0 ]; then
        echo -e "  ${GREEN}Cleared${NC} $stale stale cache version(s) from $CACHE_DIR"
    fi
fi

echo ""
echo -e "${GREEN}Done!${NC} clavain v$VERSION"
echo ""
echo "Next: restart Claude Code sessions to pick up the new plugin version."
