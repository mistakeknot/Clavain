#!/usr/bin/env bash
# Clavain autopilot gate — PreToolUse hook for Edit/Write/MultiEdit
#
# When autopilot mode is active (flag file exists), denies write-class tool calls
# and instructs Claude to dispatch changes through Codex agents instead.
#
# Input: Tool call JSON on stdin (from Claude Code hook system)
# Output: JSON with permissionDecision on stdout
# Exit: 0 always (hook errors should not block normal operation)

set -euo pipefail

# Determine project directory from Claude Code environment
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$PROJECT_DIR" ]]; then
  # Fallback: not in a Claude Code context, pass through
  exit 0
fi

FLAG_FILE="$PROJECT_DIR/.claude/autopilot.flag"

# If autopilot is off, pass through silently
if [[ ! -f "$FLAG_FILE" ]]; then
  exit 0
fi

# Autopilot is ON — extract file path from tool input for a helpful deny reason
FILE_PATH=""
if command -v jq &>/dev/null; then
  FILE_PATH="$(jq -r '.tool_input.file_path // empty' 2>/dev/null)" || true
fi

# Build deny reason with dispatch instructions
if [[ -n "$FILE_PATH" ]]; then
  FILE_HINT="The target file is: $FILE_PATH"
else
  FILE_HINT="Include the target file path in your dispatch prompt."
fi

DENY_REASON="CODEX-FIRST MODE: Direct file writes are blocked. ${FILE_HINT} Use the codex-first dispatch skill's plan→prompt→dispatch→verify cycle to make this change through a Codex agent."

# Use jq for proper JSON encoding if available, otherwise manual escape
if command -v jq &>/dev/null; then
  jq -n --arg reason "$DENY_REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
else
  # Fallback: static JSON avoids injection from interpolated values
  cat <<'ENDJSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "CODEX-FIRST MODE: Direct file writes are blocked. Use the codex-first dispatch skill to dispatch changes through Codex agents."
  }
}
ENDJSON
fi
