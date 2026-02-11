#!/usr/bin/env bash
# Stop hook: auto-compound non-trivial problem-solving after each turn
#
# Analyzes the recent conversation for compoundable signals:
#   - Git commits (suggests documenting what was solved)
#   - Debugging resolutions ("that worked", "it's fixed", etc.)
#   - Non-trivial problem-solving patterns
#   - Insight blocks (★ Insight markers in explanatory mode)
#   - Bead closures (completed work items)
#   - Build/test recovery (passing after failure)
#   - High tool activity (many bash commands = non-trivial session)
#
# Signals are weighted. Compound triggers when total weight >= 2,
# so a single commit alone won't fire, but commit + resolution will.
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

# Extract recent transcript (last 80 lines for broader context)
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# Weighted signal detection
SIGNALS=""
WEIGHT=0

# 1. Git commit detected (Claude ran git commit) — weight 1
if echo "$RECENT" | grep -q '"git commit\|"git add.*&&.*git commit'; then
    SIGNALS="${SIGNALS}commit,"
    WEIGHT=$((WEIGHT + 1))
fi

# 2. Debugging resolution phrases — weight 2 (strong signal)
if echo "$RECENT" | grep -iq '"that worked\|"it'\''s fixed\|"working now\|"problem solved\|"that did it\|"bug fixed\|"issue resolved'; then
    SIGNALS="${SIGNALS}resolution,"
    WEIGHT=$((WEIGHT + 2))
fi

# 3. Non-trivial fix patterns (investigation language) — weight 2
if echo "$RECENT" | grep -iq '"root cause\|"the issue was\|"the problem was\|"turned out\|"the fix is\|"solved by'; then
    SIGNALS="${SIGNALS}investigation,"
    WEIGHT=$((WEIGHT + 2))
fi

# 4. Bead closed (completed work item) — weight 1
if echo "$RECENT" | grep -q '"bd close\|"bd update.*completed'; then
    SIGNALS="${SIGNALS}bead-closed,"
    WEIGHT=$((WEIGHT + 1))
fi

# 5. Insight block emitted (★ Insight marker from explanatory mode) — weight 1
if echo "$RECENT" | grep -q 'Insight ─'; then
    SIGNALS="${SIGNALS}insight,"
    WEIGHT=$((WEIGHT + 1))
fi

# 6. Build/test recovery: passing after earlier failure — weight 2
# Detect patterns like "FAILED" followed by "passed" or "BUILD SUCCESSFUL"
if echo "$RECENT" | grep -iq 'FAIL\|FAILED\|ERROR.*build\|error.*compile\|test.*failed'; then
    if echo "$RECENT" | grep -iq 'passed\|BUILD SUCCESSFUL\|build succeeded\|tests pass\|all.*pass'; then
        SIGNALS="${SIGNALS}recovery,"
        WEIGHT=$((WEIGHT + 2))
    fi
fi

# 7. High bash activity (>8 bash tool calls = non-trivial session) — weight 1
BASH_COUNT=$(echo "$RECENT" | grep -Ec '"Bash"|"command":' || true)
if [[ "$BASH_COUNT" -gt 8 ]]; then
    SIGNALS="${SIGNALS}high-activity,"
    WEIGHT=$((WEIGHT + 1))
fi

# 8. Error→fix cycle (error message followed by edit/write) — weight 1
if echo "$RECENT" | grep -iq 'error\|exception\|traceback\|panic'; then
    if echo "$RECENT" | grep -q '"Edit"\|"Write"\|replace_content\|replace_symbol'; then
        SIGNALS="${SIGNALS}error-fix-cycle,"
        WEIGHT=$((WEIGHT + 1))
    fi
fi

# Threshold: need weight >= 2 to trigger compound
# This means a single commit or single bead-close won't fire alone,
# but commit + bead-close, or any investigation/resolution/recovery will.
if [[ "$WEIGHT" -lt 2 ]]; then
    exit 0
fi

# Remove trailing comma
SIGNALS="${SIGNALS%,}"

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
