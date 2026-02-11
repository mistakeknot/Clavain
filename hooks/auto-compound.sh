#!/usr/bin/env bash
# Stop hook: auto-compound non-trivial problem-solving after each turn
#
# Analyzes the recent conversation for compoundable signals:
#   - Git commits (suggests documenting what was solved)
#   - Debugging resolutions ("that worked", "it's fixed", etc.)
#   - Non-trivial problem-solving patterns
#   - Insight blocks (★ Insight markers in explanatory mode)
#
# Uses stop_hook_active to prevent infinite re-triggering.
# Returns JSON with decision:"block" + reason when compound is warranted,
# causing Claude to evaluate and automatically run /compound with a brief notice.
#
# Input: Hook JSON on stdin (session_id, transcript_path, stop_hook_active)
# Output: JSON on stdout
# Exit: 0 always

set -euo pipefail

# Read hook input
INPUT=$(cat)

# Guard: if stop hook is already active, don't re-trigger (prevents infinite loop)
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    exit 0
fi

# Extract recent assistant messages (last 20 lines of transcript, looking for signals)
# The transcript is JSONL — each line is a JSON object
RECENT=$(tail -40 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# Signal detection: look for compoundable patterns in recent conversation
SIGNALS=""

# 1. Git commit detected (Claude ran git commit)
if echo "$RECENT" | grep -q '"git commit\|"git add.*&&.*git commit'; then
    SIGNALS="${SIGNALS}commit,"
fi

# 2. Debugging resolution phrases
if echo "$RECENT" | grep -iq '"that worked\|"it'\''s fixed\|"working now\|"problem solved\|"that did it\|"bug fixed\|"issue resolved'; then
    SIGNALS="${SIGNALS}resolution,"
fi

# 3. Non-trivial fix patterns (multiple investigation steps)
if echo "$RECENT" | grep -iq '"root cause\|"the issue was\|"the problem was\|"turned out\|"the fix is\|"solved by'; then
    SIGNALS="${SIGNALS}investigation,"
fi

# 4. Bead closed (indicates completed work)
if echo "$RECENT" | grep -q '"bd close\|"bd update.*completed'; then
    SIGNALS="${SIGNALS}bead-closed,"
fi

# 5. Insight block emitted (★ Insight marker from explanatory mode)
if echo "$RECENT" | grep -q 'Insight ─'; then
    SIGNALS="${SIGNALS}insight,"
fi

# No signals found — let Claude stop normally
if [[ -z "$SIGNALS" ]]; then
    exit 0
fi

# Remove trailing comma
SIGNALS="${SIGNALS%,}"

# Build the reason prompt — this is what Claude sees
REASON="Auto-compound check: detected compoundable signals [${SIGNALS}] in this turn. Evaluate whether the work just completed contains non-trivial problem-solving worth documenting. If YES (multiple investigation steps, non-obvious solution, or reusable insight): briefly tell the user what you are documenting (one sentence), then immediately run /clavain:compound using the Skill tool. If NO (trivial fix, routine commit, or already documented), say nothing and stop."

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
