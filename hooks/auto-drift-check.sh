#!/usr/bin/env bash
# Stop hook: auto-trigger /interwatch:watch after shipped work
#
# Detects work signals (commits, bead closures, version bumps, etc.)
# using the shared lib-signals.sh library. When total weight >= 2,
# outputs a block+reason JSON telling Claude to run /interwatch:watch.
#
# Lower threshold than auto-compound (>= 2 vs >= 3) because doc drift
# checking is cheap and important to trigger early.
#
# Guards: stop_hook_active, shared sentinel, per-repo opt-out, 10-min throttle,
#         interwatch discovery (graceful degradation if not installed).
#
# Input: Hook JSON on stdin (session_id, transcript_path, stop_hook_active)
# Output: JSON on stdout
# Exit: 0 always

set -euo pipefail

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat)

# Guard: if stop hook is already active, don't re-trigger (prevents infinite loop)
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

# Guard: per-repo opt-out
if [[ -f ".claude/clavain.no-driftcheck" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Guard: shared sentinel — only one Stop hook returns "block" per cycle
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"

# Guard: throttle — at most once per 10 minutes
THROTTLE_SENTINEL="/tmp/clavain-drift-last-${SESSION_ID}"
if [[ -f "$THROTTLE_SENTINEL" ]]; then
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
    THROTTLE_NOW=$(date +%s)
    if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 600 ]]; then
        exit 0
    fi
fi

# Guard: interwatch must be installed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
INTERWATCH_ROOT=$(_discover_interwatch_plugin)
if [[ -z "$INTERWATCH_ROOT" ]]; then
    exit 0
fi

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    exit 0
fi

# Extract recent transcript (last 80 lines for broader context)
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# Detect signals using shared library
source "${SCRIPT_DIR}/lib-signals.sh"
detect_signals "$RECENT"

# Threshold: need weight >= 2 to trigger drift check
# commit (1) + bead-close (1) = 2, enough for drift check
if [[ "$CLAVAIN_SIGNAL_WEIGHT" -lt 2 ]]; then
    exit 0
fi

SIGNALS="$CLAVAIN_SIGNALS"
WEIGHT="$CLAVAIN_SIGNAL_WEIGHT"

# Build the reason prompt
REASON="Auto-drift-check: detected shipped-work signals [${SIGNALS}] (weight ${WEIGHT}). Documentation may be stale. Run /interwatch:watch using the Skill tool to scan for doc drift. If interwatch finds drift, follow its recommendations (auto-refresh for Certain/High confidence, suggest for Medium)."

# Write throttle sentinel
touch "$THROTTLE_SENTINEL"

# Return block decision
if command -v jq &>/dev/null; then
    jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
else
    cat <<ENDJSON
{
  "decision": "block",
  "reason": "${REASON}"
}
ENDJSON
fi

# Clean up stale sentinels from previous sessions (>1 hour old)
# Covers shared stop sentinel, per-hook throttle sentinels from all hooks
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-drift-last-*' -o -name 'clavain-compound-last-*' \) -mmin +60 -delete 2>/dev/null || true

exit 0
