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

# Guard: if another Stop hook already fired this cycle, don't cascade
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
# Write sentinel NOW — before signal analysis — to minimize TOCTOU window
touch "$STOP_SENTINEL"

# Guard: only fire once per session (sentinel in /tmp)
SENTINEL="/tmp/clavain-handoff-${SESSION_ID}"
if [[ -f "$SENTINEL" ]]; then
    exit 0
fi

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

# No signals — clean exit, no handoff needed
if [[ -z "$SIGNALS" ]]; then
    exit 0
fi

# Write sentinel so we don't fire again this session
touch "$SENTINEL"

SIGNALS="${SIGNALS%,}"

# Build the handoff prompt
REASON="Session handoff check: detected incomplete work signals [${SIGNALS}]. Before stopping, you MUST:

1. Write a brief HANDOFF.md in the project root with:
   - **Done**: What was accomplished this session (bullet points)
   - **Pending**: What's still in progress or unfinished
   - **Next**: Concrete next steps for the next session
   - **Context**: Any gotchas or decisions the next session needs to know

2. Update any in-progress beads with current status:
   \`bd update <id> --notes=\"<current status>\"\`

3. Run \`bd sync --from-main\` to sync beads state

4. Stage and commit your work (even if incomplete):
   \`git add <files> && git commit -m \"wip: <what was done>\"\`

Keep it brief — HANDOFF.md should be 10-20 lines, not a report."

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
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true

exit 0
