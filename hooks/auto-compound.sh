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
source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true

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

# Claim stop sentinel FIRST (before throttle check) to prevent other hooks
# from analyzing the transcript, even if this hook exits due to throttle.
intercore_check_or_die "$INTERCORE_STOP_DEDUP_SENTINEL" "$SESSION_ID" 0 "/tmp/clavain-stop-${SESSION_ID}"

# THEN check throttle (5-min cooldown specific to this hook)
intercore_check_or_die "compound_throttle" "$SESSION_ID" 300 "/tmp/clavain-compound-last-${SESSION_ID}"

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

# Persist signals for Galiana analytics
source "${SCRIPT_DIR}/../galiana/lib-galiana.sh" 2>/dev/null || true
galiana_log_signals "$SESSION_ID" "$CLAVAIN_SIGNALS" "$CLAVAIN_SIGNAL_WEIGHT" \
    "$([[ "$CLAVAIN_SIGNAL_WEIGHT" -ge 3 ]] && echo true || echo false)" 2>/dev/null || true

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

exit 0
