#!/usr/bin/env bash
# PostToolUse hook: validate plugin.json after edits.
# Fires on Edit|Write|MultiEdit targeting */.claude-plugin/plugin.json.
# Fail-open: always exits 0 — reports via additionalContext.
set -euo pipefail

INPUT="$(cat)"

FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.edits[0].file_path // empty' 2>/dev/null)" || true
[ -z "$FILE_PATH" ] && exit 0

# Fast-exit if not a plugin.json edit
case "$FILE_PATH" in
  */.claude-plugin/plugin.json) ;;
  *) exit 0 ;;
esac

# Derive plugin root (two levels up from .claude-plugin/plugin.json)
PLUGIN_ROOT="$(dirname "$(dirname "$FILE_PATH")")"
[ -d "$PLUGIN_ROOT" ] || exit 0

# Find validate-plugin.sh — walk up from plugin root looking for scripts/
VALIDATOR=""
DIR="$PLUGIN_ROOT"
for _ in 1 2 3 4 5; do
  if [ -f "$DIR/scripts/validate-plugin.sh" ]; then
    VALIDATOR="$DIR/scripts/validate-plugin.sh"
    break
  fi
  DIR="$(dirname "$DIR")"
done

[ -z "$VALIDATOR" ] && exit 0

# Run validator, capture output
OUTPUT="$(cd "$PLUGIN_ROOT" && bash "$VALIDATOR" 2>&1)" || true
EXIT_CODE="${PIPESTATUS[0]:-0}"

# Extract error/warning counts from last line
ERRORS="$(echo "$OUTPUT" | grep -oP '\d+ errors' | head -1 || echo "0 errors")"
WARNINGS="$(echo "$OUTPUT" | grep -oP '\d+ warnings' | head -1 || echo "0 warnings")"

if echo "$OUTPUT" | grep -q '\[ERROR\]'; then
  # Report errors via additionalContext
  # Escape output for JSON
  ESCAPED="$(echo "$OUTPUT" | grep '\[ERROR\]\|\[WARN\]' | head -10 | sed 's/"/\\"/g' | tr '\n' ' ')"
  cat <<EOF
{"additionalContext": "Plugin validation: ${ERRORS}, ${WARNINGS}. ${ESCAPED}"}
EOF
fi

exit 0
