#!/usr/bin/env bash
# Stop hook: unified post-turn actions (compound + drift check)
#
# Detects work signals once using lib-signals.sh, then applies tiered thresholds:
#   - weight >= 3 → trigger /clavain:compound (non-trivial problem-solving)
#   - weight >= 2 → trigger /interwatch:watch (doc drift check)
#
# Merged from auto-compound.sh + auto-drift-check.sh (iv-rn81).
# Previously these were separate hooks competing for the same stop sentinel,
# meaning only one could ever fire per stop cycle.
#
# Guards: stop_hook_active, shared sentinel, per-repo opt-out, per-action throttle.
# Returns JSON with decision:"block" + reason when action is warranted.
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

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Claim stop sentinel FIRST — prevents other Stop hooks from duplicate work
intercore_check_or_die "$INTERCORE_STOP_DEDUP_SENTINEL" "$SESSION_ID" 0

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    exit 0
fi

# Extract recent transcript (last 80 lines for broader context)
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# Detect signals ONCE using shared library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib-signals.sh"
detect_signals "$RECENT"

# Persist signals for Galiana analytics (regardless of threshold)
source "${SCRIPT_DIR}/../galiana/lib-galiana.sh" 2>/dev/null || true
galiana_log_signals "$SESSION_ID" "$CLAVAIN_SIGNALS" "$CLAVAIN_SIGNAL_WEIGHT" \
    "$([[ "$CLAVAIN_SIGNAL_WEIGHT" -ge 3 ]] && echo true || echo false)" 2>/dev/null || true

SIGNALS="$CLAVAIN_SIGNALS"
WEIGHT="$CLAVAIN_SIGNAL_WEIGHT"

# Tiered decision: compound > drift check
# Weight >= 4: non-trivial problem-solving → compound (raised from 3)
# Weight >= 3: shipped work → drift check (raised from 2)
# Weight < 3: nothing to do

if [[ "$WEIGHT" -ge 4 ]]; then
    # Check per-repo opt-out for compound
    if [[ -f ".claude/clavain.no-autocompound" ]]; then
        exit 0
    fi
    # Check compound-specific throttle (5-min cooldown)
    intercore_check_or_die "compound_throttle" "$SESSION_ID" 300

    REASON="Auto-compound check: detected compoundable signals [${SIGNALS}] (weight ${WEIGHT}) in this turn. Evaluate whether the work just completed contains non-trivial problem-solving worth documenting. If YES (multiple investigation steps, non-obvious solution, or reusable insight): briefly tell the user what you are documenting (one sentence), then immediately run /clavain:compound using the Skill tool. If NO (trivial fix, routine commit, or already documented), say nothing and stop."

elif [[ "$WEIGHT" -ge 3 ]]; then
    # Check per-repo opt-out for drift check
    if [[ -f ".claude/clavain.no-driftcheck" ]]; then
        exit 0
    fi
    # Check drift-specific throttle (10-min cooldown)
    intercore_check_or_die "drift_throttle" "$SESSION_ID" 600

    # Guard: interwatch must be installed
    source "${SCRIPT_DIR}/lib.sh" 2>/dev/null || true
    INTERWATCH_ROOT=$(_discover_interwatch_plugin)
    if [[ -z "$INTERWATCH_ROOT" ]]; then
        exit 0
    fi

    REASON="Auto-drift-check: detected shipped-work signals [${SIGNALS}] (weight ${WEIGHT}). Documentation may be stale. Run /interwatch:watch using the Skill tool to scan for doc drift. If interwatch finds drift, follow its recommendations (auto-refresh for Certain/High confidence, suggest for Medium)."
else
    exit 0
fi

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

exit 0
