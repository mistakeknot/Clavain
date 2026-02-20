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

# Resolve active ic run for this project (fail-open)
RUN_ID=""
if command -v ic &>/dev/null; then
    PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    RUN_ID=$(ic run current --project="$PROJECT_ROOT" 2>/dev/null) || RUN_ID=""
fi

# Store run_id if available (UPDATE is harmless if empty)
if [[ -n "$RUN_ID" ]]; then
    E_RUN_ID="${RUN_ID//\'/\'\'}"
    sqlite3 "$_INTERSPECT_DB" \
        "UPDATE sessions SET run_id = '${E_RUN_ID}' WHERE session_id = '${E_SID}';" \
        2>/dev/null || true
fi

# Consume kernel events (catch up since last session)
_interspect_consume_kernel_events "$SESSION_ID" 2>/dev/null || true

# Check for canary alerts — evaluate completed canaries first
_interspect_check_canaries >/dev/null 2>&1 || true

# If any canaries are in alert state, inject warning into session context
ALERT_COUNT=$(sqlite3 "$_INTERSPECT_DB" "SELECT COUNT(*) FROM canary WHERE status = 'alert';" 2>/dev/null || echo "0")

if (( ALERT_COUNT > 0 )); then
    ALERT_AGENTS=$(sqlite3 -separator ', ' "$_INTERSPECT_DB" "SELECT group_id FROM canary WHERE status = 'alert';" 2>/dev/null || echo "")
    ALERT_MSG="WARNING: Canary alert: routing override(s) for ${ALERT_AGENTS} may have degraded review quality. Run /interspect:status for details or /interspect:revert <agent> to undo."
    # Output as additionalContext JSON for session-start injection (safe via jq — prevents JSON injection from agent names)
    jq -n --arg ctx "$ALERT_MSG" '{"additionalContext":$ctx}'
fi

exit 0
