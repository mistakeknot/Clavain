#!/usr/bin/env bash
# PostToolUse(Bash) hook: detect structural changes after git commit
# and remind to refresh AGENTS.md
#
# Detects: new files, deleted files, renamed files in the commit.
# If structural changes are found, returns a block suggestion to run /interdoc.
#
# Input: Hook JSON on stdin (tool_input, tool_output)
# Output: JSON on stdout (decision: block/allow)
# Exit: 0 always

set -euo pipefail

INPUT=$(cat)

# Only trigger on git commit commands
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null) || exit 0
if ! echo "$TOOL_INPUT" | grep -qE 'git commit'; then
    exit 0
fi

# Check tool output for success (committed)
TOOL_OUTPUT=$(echo "$INPUT" | jq -r '.tool_output.stdout // ""' 2>/dev/null) || exit 0
if ! echo "$TOOL_OUTPUT" | grep -qiE 'create mode|delete mode|rename'; then
    exit 0
fi

# Count structural changes in the commit
CREATES=$(echo "$TOOL_OUTPUT" | grep -c 'create mode' 2>/dev/null || echo 0)
DELETES=$(echo "$TOOL_OUTPUT" | grep -c 'delete mode' 2>/dev/null || echo 0)
RENAMES=$(echo "$TOOL_OUTPUT" | grep -c 'rename' 2>/dev/null || echo 0)
TOTAL=$((CREATES + DELETES + RENAMES))

if [[ "$TOTAL" -lt 2 ]]; then
    exit 0
fi

# Throttle: don't fire more than once per 10 minutes
THROTTLE_FILE="/tmp/clavain-agents-md-refresh-${CLAUDE_SESSION_ID:-default}"
if [[ -f "$THROTTLE_FILE" ]]; then
    LAST=$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [[ $((NOW - LAST)) -lt 600 ]]; then
        exit 0
    fi
fi
date +%s > "$THROTTLE_FILE" 2>/dev/null || true

REASON="Structural changes detected in commit (${CREATES} created, ${DELETES} deleted, ${RENAMES} renamed). AGENTS.md may need updating. Run /interdoc to refresh, or skip if the changes are internal."

jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
exit 0
