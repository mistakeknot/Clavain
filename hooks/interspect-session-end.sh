#!/usr/bin/env bash
# Stop hook: record session end in Interspect evidence store.
#
# Updates the sessions table with end_ts. Does NOT output JSON —
# does not participate in the sentinel protocol or block.
#
# Input: Hook JSON on stdin (session_id, stop_hook_active)
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

# Ensure DB exists (might be first hook to run if session-start was skipped)
_interspect_ensure_db || exit 0

# Record session end
TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
E_SID="${SESSION_ID//\'/\'\'}"

sqlite3 "$_INTERSPECT_DB" \
    "UPDATE sessions SET end_ts = '${TS}' WHERE session_id = '${E_SID}' AND end_ts IS NULL;" \
    2>/dev/null || true

# Record canary samples (if any active canaries exist)
# Fail-open: errors here must not block session teardown
_interspect_record_canary_sample "$SESSION_ID" 2>/dev/null || true

# Evaluate any canaries whose window has completed
_interspect_check_canaries >/dev/null 2>&1 || true

exit 0
