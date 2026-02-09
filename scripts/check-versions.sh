#!/bin/bash
#
# Verify plugin.json version is in sync with marketplace
# Called by pre-commit hook and can be run manually

set -e

if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
else
    RED=''; GREEN=''; NC=''
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

PLUGIN_VERSION=$(grep -E '"version"' .claude-plugin/plugin.json | sed 's/.*"\([0-9][^"]*\)".*/\1/')

if [ -z "$PLUGIN_VERSION" ]; then
    echo -e "${RED}Error: Could not extract version from .claude-plugin/plugin.json${NC}" >&2
    exit 1
fi

MARKETPLACE="$REPO_ROOT/../interagency-marketplace/.claude-plugin/marketplace.json"
if [ -f "$MARKETPLACE" ]; then
    MARKETPLACE_VERSION=$(grep -A10 '"clavain"' "$MARKETPLACE" | grep '"version"' | sed 's/.*"\([0-9][^"]*\)".*/\1/')
    if [ -n "$MARKETPLACE_VERSION" ] && [ "$MARKETPLACE_VERSION" != "$PLUGIN_VERSION" ]; then
        echo -e "${RED}Marketplace version drift!${NC}" >&2
        echo "" >&2
        echo "  .claude-plugin/plugin.json:  $PLUGIN_VERSION" >&2
        echo "  interagency-marketplace:     $MARKETPLACE_VERSION" >&2
        echo "" >&2
        echo "Run: scripts/bump-version.sh $PLUGIN_VERSION" >&2
        exit 1
    fi
fi

if [ "${1:-}" = "--verbose" ] || [ "${1:-}" = "-v" ]; then
    echo -e "${GREEN}✓ Versions in sync: $PLUGIN_VERSION${NC}"
fi

exit 0
