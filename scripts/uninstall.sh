#!/usr/bin/env bash
# uninstall.sh -- Remove Clavain and companion plugins from Claude Code
#
# Usage:
#   bash uninstall.sh [--dry-run] [--keep-companions]
#
# This removes the Clavain plugin and optionally its companion plugins.
# It does NOT remove the ic kernel, Beads data, or Codex/Gemini skills.
# For full platform uninstall, use: bash install.sh --uninstall (from Demarch repo)

set -euo pipefail

DRY_RUN=false
KEEP_COMPANIONS=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --keep-companions) KEEP_COMPANIONS=true ;;
        --help|-h)
            echo "Usage: bash uninstall.sh [--dry-run] [--keep-companions]"
            echo ""
            echo "Removes Clavain and companion plugins from Claude Code."
            echo "  --dry-run          Show what would be removed without removing"
            echo "  --keep-companions  Only remove Clavain, keep companion plugins"
            exit 0
            ;;
        *)
            echo "Unknown flag: $arg"
            exit 1
            ;;
    esac
done

CACHE_DIR="${HOME}/.claude/plugins/cache"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAVAIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

run() {
    if [[ "$DRY_RUN" == true ]]; then
        echo "  [DRY RUN] $*"
        return 0
    fi
    "$@"
}

if ! command -v claude &>/dev/null; then
    echo "Error: claude CLI not found. Nothing to uninstall."
    exit 1
fi

echo "Removing Clavain from Claude Code..."

# Remove companion plugins first (they depend on Clavain)
if [[ "$KEEP_COMPANIONS" != true ]] && [[ -f "$CLAVAIN_DIR/agent-rig.json" ]] && command -v jq &>/dev/null; then
    echo "  Removing companion plugins..."
    jq -r '.plugins.recommended[]?.source // empty, .plugins.required[]?.source // empty' "$CLAVAIN_DIR/agent-rig.json" 2>/dev/null | while IFS= read -r plugin_src; do
        [[ -n "$plugin_src" ]] || continue
        if run claude plugin uninstall "$plugin_src" 2>/dev/null; then
            echo "  ✓ Removed $plugin_src"
        fi
    done
fi

# Remove Clavain
if run claude plugin uninstall clavain@interagency-marketplace 2>/dev/null; then
    echo "  ✓ Clavain plugin removed"
else
    echo "  ! Clavain not found or already removed"
fi

# Remove clavain-cli symlink
if [[ -L "${HOME}/.local/bin/clavain-cli" ]]; then
    run rm -f "${HOME}/.local/bin/clavain-cli"
    echo "  ✓ clavain-cli symlink removed"
fi

echo ""
echo "✓ Clavain uninstalled from Claude Code."
echo ""
echo "  Not removed (use Demarch install.sh --uninstall for full cleanup):"
echo "  - ic kernel (~/.local/bin/ic)"
echo "  - Codex/Gemini skills"
echo "  - Beads data (.beads/)"
echo "  - interagency-marketplace (other plugins may use it)"
echo ""
