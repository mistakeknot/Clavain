#!/usr/bin/env bash
# SessionStart hook: record session start in Interspect evidence store.
#
# Inserts a row into the sessions table. Silent — no output, no context injection.
# Runs async alongside the main session-start.sh hook.
#
# Input: Hook JSON on stdin (session_id)
# Output: None
# Exit: 0 always (fail-open)

set -euo pipefail

# Guard: fail-open if dependencies unavailable
command -v jq &>/dev/null || exit 0
command -v sqlite3 &>/dev/null || exit 0

# Read hook input
INPUT=$(cat)

# Extract session_id
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty') || exit 0
[[ -z "$SESSION_ID" ]] && exit 0

# Source shared library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib-interspect.sh"

# Ensure DB exists
_interspect_ensure_db || exit 0

# Record session start
PROJECT=$(_interspect_project_name)
TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# SQL-escape
E_SID="${SESSION_ID//\'/\'\'}"
E_PROJECT="${PROJECT//\'/\'\'}"

sqlite3 "$_INTERSPECT_DB" \
    "INSERT OR IGNORE INTO sessions (session_id, start_ts, project) VALUES ('${E_SID}', '${TS}', '${E_PROJECT}');" \
    2>/dev/null || true

exit 0
