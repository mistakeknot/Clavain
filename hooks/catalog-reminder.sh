#!/usr/bin/env bash
# PostToolUse hook: remind to run gen-catalog.py when component files change.
# Fires once per session via a sentinel lock file.
set -euo pipefail

INPUT="$(cat)"

FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)" || true
[ -z "$FILE_PATH" ] && exit 0

# Match component file patterns
case "$FILE_PATH" in
  */commands/*.md|*/agents/review/*.md|*/agents/research/*.md|*/agents/workflow/*.md|*/skills/*/SKILL.md|*/hooks/hooks.json)
    ;;
  *)
    exit 0
    ;;
esac

# One reminder per session
SENTINEL="/tmp/clavain-catalog-remind-${CLAUDE_SESSION_ID:-unknown}.lock"
[ -f "$SENTINEL" ] && exit 0
touch "$SENTINEL"

BASENAME="$(basename "$FILE_PATH")"
DIRNAME="$(basename "$(dirname "$FILE_PATH")")"

cat <<EOF
{"additionalContext": "Component file changed (${DIRNAME}/${BASENAME}). Run \`python3 scripts/gen-catalog.py\` to update doc counts."}
EOF
