#!/usr/bin/env bash
# Stop hook: auto-compound non-trivial problem-solving after each turn
#
# Uses shared signal detection from lib-signals.sh with these signals:
#   - Git commits (weight 1)
#   - Debugging resolutions (weight 2)
#   - Investigation language (weight 2)
#   - Bead closures (weight 1)
#   - Insight blocks (weight 1)
#   - Build/test recovery (weight 2)
#   - Version bumps (weight 2)
#
# Compound triggers when total signal weight >= 3.
# See hooks/lib-signals.sh for signal pattern definitions.
#
# Guards: stop_hook_active, shared sentinel, per-repo opt-out, 5-min throttle.
# Returns JSON with decision:"block" + reason when compound is warranted,
# causing Claude to evaluate and automatically run /compound with a brief notice.
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
if [[ -f ".claude/clavain.no-autocompound" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Guard: if another Stop hook already fired this cycle, don't cascade
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
# Write sentinel NOW — before transcript analysis — to minimize TOCTOU window
touch "$STOP_SENTINEL"

# Guard: throttle — at most once per 5 minutes
THROTTLE_SENTINEL="/tmp/clavain-compound-last-${SESSION_ID}"
if [[ -f "$THROTTLE_SENTINEL" ]]; then
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
    THROTTLE_NOW=$(date +%s)
    if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 300 ]]; then
        exit 0
    fi
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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib-signals.sh"
detect_signals "$RECENT"

# Threshold: need weight >= 3 to trigger compound
# commit (1) + bead-close (1) = 2, not enough alone.
# Needs real investigation/resolution/recovery signal.
if [[ "$CLAVAIN_SIGNAL_WEIGHT" -lt 3 ]]; then
    exit 0
fi

SIGNALS="$CLAVAIN_SIGNALS"
WEIGHT="$CLAVAIN_SIGNAL_WEIGHT"

# Build the reason prompt — this is what Claude sees
REASON="Auto-compound check: detected compoundable signals [${SIGNALS}] (weight ${WEIGHT}) in this turn. Evaluate whether the work just completed contains non-trivial problem-solving worth documenting. If YES (multiple investigation steps, non-obvious solution, or reusable insight): briefly tell the user what you are documenting (one sentence), then immediately run /clavain:compound using the Skill tool. If NO (trivial fix, routine commit, or already documented), say nothing and stop."

# Write throttle sentinel
touch "$THROTTLE_SENTINEL"

# Return block decision to inject the evaluation prompt
if command -v jq &>/dev/null; then
    jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
else
    # Fallback: REASON contains only hardcoded strings, safe for interpolation
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
