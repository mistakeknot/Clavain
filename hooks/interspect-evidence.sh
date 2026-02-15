#!/usr/bin/env bash
# PostToolUse hook: collect evidence from agent dispatch (Task tool).
#
# Fires on Task tool calls. Records agent_dispatch events in the
# Interspect evidence store for pattern analysis.
#
# Input: Hook JSON on stdin (session_id, tool_name, tool_input, tool_output)
# Output: None (silent hook)
# Exit: 0 always (fail-open)

set -euo pipefail

# Guard: fail-open if dependencies unavailable
command -v jq &>/dev/null || exit 0
command -v sqlite3 &>/dev/null || exit 0

# Read hook input
INPUT=$(cat)

# Extract fields
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty') || exit 0
[[ -z "$SESSION_ID" ]] && exit 0

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty') || exit 0

# Only process Task tool (agent dispatch)
[[ "$TOOL_NAME" == "Task" ]] || exit 0

# Source shared library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib-interspect.sh"

# Ensure DB exists
_interspect_ensure_db || exit 0

# Extract agent dispatch details from tool input
SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // "unknown"') || SUBAGENT_TYPE="unknown"
DESCRIPTION=$(echo "$INPUT" | jq -r '.tool_input.description // ""') || DESCRIPTION=""

# Build context JSON
CONTEXT=$(jq -n \
    --arg subagent "$SUBAGENT_TYPE" \
    --arg desc "$DESCRIPTION" \
    '{subagent_type: $subagent, description: $desc}') || CONTEXT="{}"

# Insert evidence
_interspect_insert_evidence \
    "$SESSION_ID" \
    "$SUBAGENT_TYPE" \
    "agent_dispatch" \
    "" \
    "$CONTEXT" \
    "interspect-evidence" 2>/dev/null || true

exit 0
