#!/usr/bin/env bash
# Stop hook: auto-handoff when session ends with incomplete work
#
# Detects when Claude is about to stop with:
#   - Uncommitted changes in the working tree
#   - In-progress beads issues
#   - Unstaged files that look like work products
#
# When detected, blocks and asks Claude to write HANDOFF.md and sync beads.
# Only triggers once per session (uses a sentinel file).
#
# Input: Hook JSON on stdin (session_id, transcript_path, stop_hook_active)
# Output: JSON on stdout
# Exit: 0 always

set -euo pipefail

# shellcheck source=hooks/lib-intercore.sh
source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat)

# Guard: if stop hook is already active, don't re-trigger
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# CRITICAL: Stop sentinel must be written unconditionally to prevent hook cascade.
# The wrapper handles DB-vs-file internally, but if the wrapper is unavailable
# (e.g., lib-intercore.sh failed to source), intercore_check_or_die falls back
# to inline temp file logic.
intercore_check_or_die "$INTERCORE_STOP_DEDUP_SENTINEL" "$SESSION_ID" 0 "/tmp/clavain-stop-${SESSION_ID}"

# Guard: only fire once per session
intercore_check_or_die "handoff" "$SESSION_ID" 0 "/tmp/clavain-handoff-${SESSION_ID}"

# Write in-flight agent manifest (before signal analysis — runs even if no signals)
# shellcheck source=hooks/lib.sh
source "${BASH_SOURCE[0]%/*}/lib.sh" 2>/dev/null || true
_write_inflight_manifest "$SESSION_ID" 2>/dev/null || true

# Check for signals that work is incomplete
SIGNALS=""

# 1. Uncommitted changes
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    DIRTY=$(git status --porcelain 2>/dev/null | grep -v '^\?\?' | head -1 || true)
    if [[ -n "$DIRTY" ]]; then
        SIGNALS="${SIGNALS}uncommitted-changes,"
    fi
fi

# 2. In-progress beads
if command -v bd &>/dev/null; then
    IN_PROGRESS=$(bd list --status=in_progress 2>/dev/null | grep -c '●' || true)
    if [[ "$IN_PROGRESS" -gt 0 ]]; then
        SIGNALS="${SIGNALS}in-progress-beads(${IN_PROGRESS}),"
    fi
fi

# 3. In-flight background agents (from manifest just written)
if [[ -f ".clavain/scratch/inflight-agents.json" ]]; then
    INFLIGHT_COUNT=$(jq '.agents | length' ".clavain/scratch/inflight-agents.json" 2>/dev/null) || INFLIGHT_COUNT=0
    if [[ "$INFLIGHT_COUNT" -gt 0 ]]; then
        SIGNALS="${SIGNALS}inflight-agents(${INFLIGHT_COUNT}),"
    fi
fi

# No signals — clean exit, no handoff needed
if [[ -z "$SIGNALS" ]]; then
    exit 0
fi

SIGNALS="${SIGNALS%,}"

# Determine handoff target: .clavain/scratch/ if available, else project root.
# Hooks run from project root (set by Claude Code), so relative paths are safe.
# Uses timestamped filenames so handoffs from concurrent/sequential sessions
# don't overwrite each other. A symlink (handoff-latest.md) points to the newest.
HANDOFF_PATH="HANDOFF.md"
if [[ -d ".clavain" ]]; then
    mkdir -p ".clavain/scratch" 2>/dev/null || true
    TIMESTAMP=$(date +%Y-%m-%dT%H%M)
    SESSION_SHORT="${SESSION_ID:0:8}"
    HANDOFF_PATH=".clavain/scratch/handoff-${TIMESTAMP}-${SESSION_SHORT}.md"
    # Prune old handoffs: keep last 10 timestamped files
    # shellcheck disable=SC2012
    ls -1t .clavain/scratch/handoff-*.md 2>/dev/null | tail -n +11 | xargs -r rm -f 2>/dev/null || true
fi

# Build the handoff prompt
REASON="Session handoff check: detected incomplete work signals [${SIGNALS}]. Before stopping, you MUST:

1. Write a brief handoff file to ${HANDOFF_PATH} with:
   - **Done**: What was accomplished this session (bullet points)
   - **Pending**: What's still in progress or unfinished
   - **Next**: Concrete next steps for the next session
   - **Context**: Any gotchas or decisions the next session needs to know

2. Update the latest-handoff symlink so session-start finds it:
   \`ln -sf \"\$(basename '${HANDOFF_PATH}')\" .clavain/scratch/handoff-latest.md\`

3. Update any in-progress beads with current status:
   \`bd update <id> --notes=\"<current status>\"\`

4. Run \`bd sync\` to flush beads state (compatibility no-op on beads >=0.51)

5. Stage and commit your work (even if incomplete):
   \`git add <files> && git commit -m \"wip: <what was done>\"\`

Keep it brief — the handoff file should be 10-20 lines, not a report."

# Return block decision
if command -v jq &>/dev/null; then
    jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
else
    cat <<ENDJSON
{
  "decision": "block",
  "reason": "${REASON}"
}
ENDJSON
fi

# Clean up stale sentinels from previous sessions
if type intercore_cleanup_stale &>/dev/null; then
    intercore_cleanup_stale
else
    find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
fi

exit 0
