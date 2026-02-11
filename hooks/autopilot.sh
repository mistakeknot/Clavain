#!/usr/bin/env bash
# Clavain clodex gate — PreToolUse hook for Edit/Write/MultiEdit
#
# When clodex-toggle mode is active (flag file exists), denies write-class tool
# calls to SOURCE CODE files and instructs Claude to dispatch changes through
# Codex agents instead.
#
# Non-code files and temp files are always allowed through, so the
# plan→prompt→dispatch→verify cycle works without disabling the hook.
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

FLAG_FILE="$PROJECT_DIR/.claude/clodex-toggle.flag"

# If clodex mode is off, pass through silently
if [[ ! -f "$FLAG_FILE" ]]; then
  exit 0
fi

# Clodex mode is ON — extract file path from tool input
FILE_PATH=""
if command -v jq &>/dev/null; then
  FILE_PATH="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)" || true
fi

# ─────────────────────────────────────────────
# Path-based exceptions: allow non-code files through
# ─────────────────────────────────────────────

if [[ -n "$FILE_PATH" ]]; then
  # Allow writes to /tmp/ (needed for dispatch prompt files)
  if [[ "$FILE_PATH" == /tmp/* ]]; then
    exit 0
  fi

  # Allow non-code file extensions (documentation, config, data)
  case "${FILE_PATH##*.}" in
    md|json|yaml|yml|toml|txt|csv|xml|html|css|svg|lock|cfg|ini|conf|env)
      exit 0
      ;;
  esac

  # Allow dotfiles and hidden config
  case "$(basename "$FILE_PATH")" in
    .*)
      exit 0
      ;;
  esac
fi

# This is a source code file — deny with dispatch instructions
if [[ -n "$FILE_PATH" ]]; then
  FILE_HINT="The target file is: $FILE_PATH"
else
  FILE_HINT="Include the target file path in your dispatch prompt."
fi

DENY_REASON="CLODEX MODE: Direct source code writes are blocked. ${FILE_HINT} Use the /clodex dispatch skill's plan→prompt→dispatch→verify cycle to make this change through a Codex agent. Non-code files (.md, .json, .yaml, etc.) and /tmp/ are still writable."

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
  cat <<'ENDJSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "CLODEX MODE: Direct source code writes are blocked. Use the /clodex dispatch skill to make changes through Codex agents. Non-code files and /tmp/ are still writable."
  }
}
ENDJSON
fi
