#!/usr/bin/env bash
# SessionEnd hook: auto-push unpushed commits
#
# Pushes commits the session left unpushed. Handles three branch shapes
# (mk-667 — the old version exited silently when @{upstream} was missing,
# stranding every worktree branch's commits):
#   1. Branch with a same-name upstream: plain `git push`.
#   2. Branch tracking a DIFFERENT ref (e.g. a worktree branch tracking
#      origin/main): bare `git push` refuses under push.default=simple —
#      publish under the branch's own name and adopt that as upstream.
#   3. No upstream at all: push -u origin <branch>, but only when the
#      branch carries commits that exist on no remote ref (avoids minting
#      pointless remote branches for unmodified checkouts).
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

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
[[ "$BRANCH" == "HEAD" ]] && exit 0 # detached — nothing safe to push

push_current() {
    local upstream ahead remote unpushed
    upstream=$(git rev-parse --abbrev-ref "@{upstream}" 2>/dev/null) || upstream=""

    if [[ -z "$upstream" ]]; then
        git remote get-url origin >/dev/null 2>&1 || return 0
        unpushed=$(git rev-list --count HEAD --not --remotes 2>/dev/null) || return 0
        if [[ "${unpushed:-0}" -gt 0 ]]; then
            git push -u origin "$BRANCH" 2>/dev/null || true
        fi
        return 0
    fi

    ahead=$(git rev-list --count "${upstream}..HEAD" 2>/dev/null) || return 0
    [[ "${ahead:-0}" -gt 0 ]] || return 0
    remote="${upstream%%/*}"
    if [[ "${upstream#*/}" == "$BRANCH" ]]; then
        git push 2>/dev/null || true
    else
        # Tracking a foreign ref (origin/main): publish the branch under
        # its own name; -u moves the upstream so future counts are sane.
        git push -u "$remote" "$BRANCH" 2>/dev/null || true
    fi
}

push_current

# Push beads if present (may create a sync commit — push again)
if [[ -f ".beads/push.sh" ]]; then
    bash .beads/push.sh 2>/dev/null || true
    push_current
fi

exit 0
