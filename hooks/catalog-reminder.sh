#!/usr/bin/env bash
# PostToolUse hook: remind to run gen-catalog.py when component files change.
# Fires once per session via a sentinel lock file.
set -uo pipefail
trap 'exit 0' ERR

INPUT="$(cat)"

FILE_PATH="$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.edits[0].file_path // empty' 2>/dev/null)" || true
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
# shellcheck source=hooks/lib.sh
source "${BASH_SOURCE[0]%/*}/lib.sh" 2>/dev/null || true

# One reminder per session (intercore sentinel or temp file fallback)
# The stdin session_id first (mk-rd9f): CLAUDE_SESSION_ID is absent when the
# start hook did not fire, and "unknown" would make every such session share
# one sentinel.
_SID="$(clavain_session_id "$INPUT" 2>/dev/null)" || _SID=""
[[ -n "$_SID" ]] || _SID="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown}}"
intercore_check_or_die "catalog_remind" "$_SID" 0

BASENAME="$(basename "$FILE_PATH")"
DIRNAME="$(basename "$(dirname "$FILE_PATH")")"

cat <<EOF
{"additionalContext": "Component file changed (${DIRNAME}/${BASENAME}). Run \`python3 scripts/gen-catalog.py\` to update doc counts."}
EOF
