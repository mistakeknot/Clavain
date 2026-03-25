#!/usr/bin/env bash
# SessionEnd hook: auto-push unpushed commits
#
# Checks if there are local commits not yet pushed to origin and pushes them.
# Also runs beads push if .beads/ exists. Runs async so it doesn't block.
#
# Input: Hook JSON on stdin
# Output: none (async, fire-and-forget)
# Exit: 0 always

set -uo pipefail
trap 'exit 0' ERR

# Find git root
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$GIT_ROOT"

# Check for unpushed commits on current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
UPSTREAM=$(git rev-parse --abbrev-ref "@{upstream}" 2>/dev/null) || exit 0

AHEAD=$(git rev-list --count "${UPSTREAM}..HEAD" 2>/dev/null) || exit 0
if [[ "$AHEAD" -gt 0 ]]; then
    git push 2>/dev/null || true
fi

# Push beads if present
if [[ -f ".beads/push.sh" ]]; then
    bash .beads/push.sh 2>/dev/null || true
    # Push again for beads sync commit
    AHEAD2=$(git rev-list --count "${UPSTREAM}..HEAD" 2>/dev/null) || AHEAD2=0
    if [[ "$AHEAD2" -gt 0 ]]; then
        git push 2>/dev/null || true
    fi
fi

exit 0
