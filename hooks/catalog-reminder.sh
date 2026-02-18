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

# Source intercore wrappers (fail-safe: falls back to temp files)
source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true

# One reminder per session (intercore sentinel or temp file fallback)
_SID="${CLAUDE_SESSION_ID:-unknown}"
intercore_check_or_die "catalog_remind" "$_SID" 0 "/tmp/clavain-catalog-remind-${_SID}.lock"

BASENAME="$(basename "$FILE_PATH")"
DIRNAME="$(basename "$(dirname "$FILE_PATH")")"

cat <<EOF
{"additionalContext": "Component file changed (${DIRNAME}/${BASENAME}). Run \`python3 scripts/gen-catalog.py\` to update doc counts."}
EOF
