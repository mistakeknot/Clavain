#!/usr/bin/env bash
# SessionEnd hook: lightweight backup handoff when Stop hook didn't fire
#
# Belt-and-suspenders safety net. The primary handoff runs on Stop
# (session-handoff.sh — blocks Claude, gets a thoughtful narrative).
# This backup runs async on SessionEnd and writes a machine-generated
# handoff with git diff, active beads, and recent commits.
#
# Skips if the Stop hook already fired (sentinel file exists).
#
# Input: Hook JSON on stdin (session_id)
# Output: None (async, fire-and-forget)
# Exit: 0 always

set -euo pipefail

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Check if Stop handoff already fired — if so, nothing to do.
# Check both temp file (legacy) and IC sentinel (when available).
if [[ -f "/tmp/clavain-handoff-${SESSION_ID}" ]]; then
    exit 0
fi
# shellcheck source=hooks/lib-intercore.sh
source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true
if intercore_available 2>/dev/null; then
    # IC sentinel was claimed by session-handoff.sh — check if it exists
    if ! intercore_sentinel_check_or_legacy "handoff" "$SESSION_ID" 0 "/tmp/clavain-handoff-${SESSION_ID}" 2>/dev/null; then
        # Sentinel exists (throttled) — Stop handoff already ran
        exit 0
    fi
    # If we got here, sentinel didn't exist — Stop handoff didn't fire.
    # Reset the sentinel we just claimed so this check doesn't interfere.
    intercore_sentinel_reset_or_legacy "handoff" "$SESSION_ID" "/tmp/clavain-handoff-${SESSION_ID}" 2>/dev/null || true
fi

# Check if .clavain directory exists (we're in a Clavain-aware project)
if [[ ! -d ".clavain" ]]; then
    exit 0
fi

mkdir -p ".clavain/scratch" 2>/dev/null || true

TIMESTAMP=$(date +%Y-%m-%dT%H%M)
SESSION_SHORT="${SESSION_ID:0:8}"
HANDOFF_PATH=".clavain/scratch/handoff-${TIMESTAMP}-${SESSION_SHORT}.md"

# Gather signals
DIFF_STAT=""
STAGED_STAT=""
RECENT_COMMITS=""
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    DIFF_STAT=$(git diff --stat 2>/dev/null || true)
    STAGED_STAT=$(git diff --cached --stat 2>/dev/null || true)
    RECENT_COMMITS=$(git log --oneline -5 2>/dev/null || true)
fi

IN_PROGRESS_BEADS=""
if command -v bd &>/dev/null; then
    IN_PROGRESS_BEADS=$(bd list --status=in_progress 2>/dev/null || true)
fi

# Only write handoff if there are signals worth saving
if [[ -z "$DIFF_STAT" && -z "$STAGED_STAT" && -z "$IN_PROGRESS_BEADS" ]]; then
    exit 0
fi

# Write minimal machine-generated handoff
{
    echo "# Session Handoff (auto-generated backup)"
    echo ""
    echo "**Session:** ${SESSION_SHORT}"
    echo "**Generated:** $(date -Iseconds)"
    echo "**Note:** Stop hook did not fire — this is an automated backup."
    echo ""
    if [[ -n "$DIFF_STAT" ]]; then
        echo "## Unstaged Changes"
        echo '```'
        echo "$DIFF_STAT"
        echo '```'
        echo ""
    fi
    if [[ -n "$STAGED_STAT" ]]; then
        echo "## Staged Changes"
        echo '```'
        echo "$STAGED_STAT"
        echo '```'
        echo ""
    fi
    if [[ -n "$IN_PROGRESS_BEADS" ]]; then
        echo "## In-Progress Beads"
        echo '```'
        echo "$IN_PROGRESS_BEADS"
        echo '```'
        echo ""
    fi
    if [[ -n "$RECENT_COMMITS" ]]; then
        echo "## Recent Commits"
        echo '```'
        echo "$RECENT_COMMITS"
        echo '```'
    fi
} > "$HANDOFF_PATH"

# Update latest symlink
ln -sf "$(basename "$HANDOFF_PATH")" ".clavain/scratch/handoff-latest.md" 2>/dev/null || true

# Prune old handoffs: keep last 10
# shellcheck disable=SC2012
ls -1t .clavain/scratch/handoff-*.md 2>/dev/null | tail -n +11 | xargs -r rm -f 2>/dev/null || true

# Release any bead claims held by this session
if [[ -n "${CLAVAIN_BEAD_ID:-}" ]] && command -v bd &>/dev/null; then
    source "${BASH_SOURCE[0]%/*}/lib-sprint.sh" 2>/dev/null || true
    bead_release "$CLAVAIN_BEAD_ID" 2>/dev/null || true
fi

# Sync beads if available
if command -v bd &>/dev/null; then
    bd sync 2>/dev/null || true
fi

exit 0
