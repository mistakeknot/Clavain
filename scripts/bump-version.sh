#!/bin/bash
#
# Bump version across plugin.json and marketplace, commit, push.
#
# Usage:
#   scripts/bump-version.sh 0.5.0
#   scripts/bump-version.sh 0.5.0 --dry-run

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
# Marketplace location: try Interverse monorepo first, fall back to sibling dir
if [ -f "$REPO_ROOT/../../infra/marketplace/.claude-plugin/marketplace.json" ]; then
    MARKETPLACE_ROOT="$REPO_ROOT/../../infra/marketplace"
elif [ -f "$REPO_ROOT/../interagency-marketplace/.claude-plugin/marketplace.json" ]; then
    MARKETPLACE_ROOT="$REPO_ROOT/../interagency-marketplace"
else
    MARKETPLACE_ROOT="${MARKETPLACE_ROOT:-$REPO_ROOT/../interagency-marketplace}"
fi
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

if $DRY_RUN; then
    if ! python3 "$REPO_ROOT/scripts/gen-catalog.py" --check; then
        echo -e "${YELLOW}[dry-run] Catalog drift detected. Run python3 scripts/gen-catalog.py to refresh.${NC}"
    fi
else
    python3 "$REPO_ROOT/scripts/gen-catalog.py"
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

update_file \
    "$REPO_ROOT/docs/PRD.md" \
    "^\*\*Version:\*\* $CURRENT" \
    "**Version:** $VERSION" \
    "docs/PRD.md"

RIG_CURRENT=$(grep -E '"version"' "$REPO_ROOT/agent-rig.json" 2>/dev/null | head -1 | sed 's/.*"\([0-9][^"]*\)".*/\1/')
if [ -n "$RIG_CURRENT" ]; then
    update_file \
        "$REPO_ROOT/agent-rig.json" \
        "\"version\": \"$RIG_CURRENT\"" \
        "\"version\": \"$VERSION\"" \
        "agent-rig.json"
fi

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
git add .claude-plugin/plugin.json agent-rig.json docs/PRD.md
git commit -m "chore: bump version to $VERSION"
git push
echo -e "${GREEN}Pushed Clavain${NC}"

cd "$MARKETPLACE_ROOT"
git add .claude-plugin/marketplace.json
git commit -m "chore: bump clavain to v$VERSION"
git push
echo -e "${GREEN}Pushed interagency-marketplace${NC}"

# Symlink old cache versions → real dir so running sessions' Stop hooks still work.
# Problem: sessions may be on ANY older version (not just $CURRENT), because sessions
# can outlive multiple publish cycles. We find the one real directory and symlink
# everything else to it. session-start.sh cleans up stale symlinks on next session.
CACHE_DIR="$HOME/.claude/plugins/cache/interagency-marketplace/clavain"
if [[ -d "$CACHE_DIR" ]]; then
    # Find the real (non-symlink) directory — that's the one with actual files
    REAL_DIR=""
    for candidate in "$CACHE_DIR"/*/; do
        [[ -d "$candidate" ]] || continue
        [[ -L "${candidate%/}" ]] && continue
        REAL_DIR="$(basename "$candidate")"
        break
    done

    if [[ -n "$REAL_DIR" ]]; then
        # Symlink $CURRENT if it's missing (the version we just bumped away from)
        if [[ -n "$CURRENT" && "$CURRENT" != "$REAL_DIR" && ! -e "$CACHE_DIR/$CURRENT" ]]; then
            ln -sf "$REAL_DIR" "$CACHE_DIR/$CURRENT"
            echo -e "  ${GREEN}Symlinked${NC} cache/$CURRENT → $REAL_DIR"
        fi
        # Also ensure $VERSION points somewhere (may not be downloaded yet)
        if [[ "$VERSION" != "$REAL_DIR" && ! -e "$CACHE_DIR/$VERSION" ]]; then
            ln -sf "$REAL_DIR" "$CACHE_DIR/$VERSION"
            echo -e "  ${GREEN}Symlinked${NC} cache/$VERSION → $REAL_DIR (pre-download bridge)"
        fi
        echo -e "  Running sessions' Stop hooks bridged via $REAL_DIR"
    else
        echo -e "  ${YELLOW}Note:${NC} No real cache dir found. Stop hooks may fail until next session."
    fi
else
    echo -e "  ${YELLOW}Note:${NC} No cache dir at $CACHE_DIR. Plugin not installed locally."
fi

echo ""
echo -e "${GREEN}Done!${NC} clavain v$VERSION"
echo ""
echo "Next: restart Claude Code sessions to pick up the new plugin version."
echo "  (Stale symlinks cleaned up automatically on next session start.)"
