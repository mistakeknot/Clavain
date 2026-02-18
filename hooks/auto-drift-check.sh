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
if [[ -f ".claude/clavain.no-driftcheck" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Claim stop sentinel FIRST (before throttle check)
intercore_check_or_die "$INTERCORE_STOP_DEDUP_SENTINEL" "$SESSION_ID" 0 "/tmp/clavain-stop-${SESSION_ID}"

# THEN check throttle (10-min cooldown specific to this hook)
intercore_check_or_die "drift_throttle" "$SESSION_ID" 600 "/tmp/clavain-drift-last-${SESSION_ID}"

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
