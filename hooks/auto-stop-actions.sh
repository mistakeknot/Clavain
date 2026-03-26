#!/usr/bin/env bash
# Stop hook: unified post-turn actions (compound + dispatch + drift check)
#
# Detects work signals once using lib-signals.sh, then applies tiered thresholds:
#   - weight >= 4 → trigger /clavain:compound (non-trivial problem-solving)
#   - bead-closed + CLAVAIN_SELF_DISPATCH=true → self-dispatch (autonomous bead pickup)
#   - weight >= 3 → trigger /interwatch:watch (doc drift check)
#
# Merged from auto-compound.sh + auto-drift-check.sh (iv-rn81).
# Self-dispatch tier added in ysxe.3 (2026-03-20): merged here per flux-drive
# review to avoid sentinel conflict with separate hook file.
#
# Guards: stop_hook_active, shared sentinel, per-repo opt-out, per-action throttle.
# Returns JSON with decision:"block" + reason when action is warranted.
#
# Input: Hook JSON on stdin (session_id, transcript_path, stop_hook_active)
# Output: JSON on stdout
# Exit: 0 always

set -uo pipefail
trap 'exit 0' ERR
source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true
source "${BASH_SOURCE[0]%/*}/lib-shadow-tracker.sh" 2>/dev/null || true

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

# Write delegation summary to interband (informational, non-blocking)
# Statusline and session-start can read this later.
if command -v sqlite3 &>/dev/null; then
    _INTERSPECT_DB="${CLAUDE_PROJECT_DIR:-.}/.clavain/interspect/interspect.db"
    if [[ -f "$_INTERSPECT_DB" ]]; then
        _DEL_STATS=$(sqlite3 "$_INTERSPECT_DB" \
            "SELECT COUNT(*) || '|' ||
                    COALESCE(SUM(CASE WHEN json_extract(context,'\$.verdict') IN ('pass','CLEAN') THEN 1 ELSE 0 END),0) || '|' ||
                    COALESCE(SUM(CASE WHEN json_extract(context,'\$.retry_needed') IN (1,'true') THEN 1 ELSE 0 END),0)
             FROM evidence
             WHERE event='delegation_outcome' AND source='codex-delegate'
               AND session_id='${SESSION_ID}'" 2>/dev/null || true)
        if [[ -n "$_DEL_STATS" ]]; then
            _DEL_TOTAL="${_DEL_STATS%%|*}"
            _DEL_REST="${_DEL_STATS#*|}"
            _DEL_PASS="${_DEL_REST%%|*}"
            _DEL_RETRY="${_DEL_REST#*|}"
            if [[ "$_DEL_TOTAL" -gt 0 ]] 2>/dev/null; then
                _DEL_RATE=$(( (_DEL_PASS * 100) / _DEL_TOTAL ))
                _INTERBAND_DIR="$HOME/.interband/interspect/delegation"
                mkdir -p "$_INTERBAND_DIR" 2>/dev/null || true
                cat > "$_INTERBAND_DIR/${SESSION_ID}.json" <<EOF
{
  "version": "1.0",
  "source": "interspect",
  "payload": {
    "total": $_DEL_TOTAL,
    "pass": $_DEL_PASS,
    "retry": $_DEL_RETRY,
    "pass_rate": $_DEL_RATE
  }
}
EOF
            fi
        fi
    fi
fi

# Shadow tracker detection — orthogonal to tier waterfall
# Runs independently; emits warning always, blocks only if no other tier claimed the cycle
SHADOW_WARNING=""
if [[ ! -f ".claude/clavain.no-shadow-enforce" ]]; then
    shadow_files=$(detect_shadow_trackers "." 2>/dev/null)
    shadow_count=$?
    if [[ $shadow_count -gt 0 ]]; then
        SHADOW_WARNING="Shadow tracker detected: ${shadow_count} file(s) found using work-tracking outside beads:\n${shadow_files}\n\nThese drift silently and cause duplicate work. Run /bead-sweep to migrate to beads, or delete if already tracked."
    fi
fi

# Tiered decision: compound > dispatch > drift check
# Weight >= 4: non-trivial problem-solving → compound (raised from 3)
# bead-closed + opt-in: autonomous dispatch → claim next bead
# Weight >= 3: shipped work → drift check (raised from 2)
# Weight < 3: nothing to do
#
# Dispatch is between compound and drift: completing the next bead is more
# valuable than checking doc staleness. Compound takes priority because it
# captures knowledge that would otherwise be lost.

REASON=""

if [[ "$WEIGHT" -ge 4 ]]; then
    # Check per-repo opt-out for compound
    if [[ ! -f ".claude/clavain.no-autocompound" ]]; then
        # Check compound-specific throttle (5-min cooldown)
        if intercore_sentinel_check_or_legacy "compound_throttle" "$SESSION_ID" 300; then
            REASON="Auto-compound check: detected compoundable signals [${SIGNALS}] (weight ${WEIGHT}) in this turn. Evaluate whether the work just completed contains non-trivial problem-solving worth documenting. If YES (multiple investigation steps, non-obvious solution, or reusable insight): briefly tell the user what you are documenting (one sentence), then immediately run /clavain:compound using the Skill tool. If NO (trivial fix, routine commit, or already documented), say nothing and stop."
        fi
    fi
fi

# Self-dispatch tier: requires bead-closed signal + explicit opt-in.
# Only fires if compound didn't claim this cycle (REASON still empty).
# Uses sentinel_check_or_legacy (returns 1 if throttled) instead of
# check_or_die (which would exit the entire script and block drift check).
if [[ -z "$REASON" && "${CLAVAIN_SELF_DISPATCH:-}" == "true" ]]; then
    if [[ "$SIGNALS" == *"bead-closed"* ]]; then
        if [[ ! -f ".claude/clavain.no-selfdispatch" ]]; then
            source "${SCRIPT_DIR}/lib-dispatch.sh" 2>/dev/null || true
            if intercore_sentinel_check_or_legacy "dispatch_cooldown" "$SESSION_ID" "${DISPATCH_COOLDOWN_SEC:-20}"; then
                if type dispatch_cap_check &>/dev/null && type dispatch_circuit_check &>/dev/null; then
                    # Watchdog pause checks: factory-level and agent-level
                    if [[ -f "$HOME/.clavain/factory-paused.json" ]]; then
                        : # Factory paused by watchdog tier 4 — skip dispatch
                    elif [[ -n "$SESSION_ID" && -f "$HOME/.clavain/paused-agents/$(echo "$SESSION_ID" | tr '/:' '__').json" ]]; then
                        : # Agent paused by watchdog tier 3 — skip dispatch
                    elif dispatch_cap_check "$SESSION_ID" && dispatch_circuit_check "$SESSION_ID"; then
                        # WIP check (advisory — atomic claim is the real guard)
                        _wip_count=0
                        if command -v bd &>/dev/null; then
                            _wip_count=$(bd list --status=in_progress --json 2>/dev/null \
                                | jq --arg sid "$SESSION_ID" \
                                    '[.[] | select(.assignee == $sid or .assignee == "unknown")] | length' \
                                    2>/dev/null) || _wip_count=0
                        fi
                        if [[ "${_wip_count:-0}" -eq 0 ]]; then
                            _dispatch_result=""
                            _dispatch_result=$(dispatch_attempt_claim "$SESSION_ID" 2>/dev/null) || _dispatch_result=""
                            if [[ -n "$_dispatch_result" ]]; then
                                _d_bead="${_dispatch_result%%|*}"
                                _d_score="${_dispatch_result#*|}"
                                REASON="Self-dispatch: claimed ${_d_bead} (score ${_d_score}). Run /clavain:route ${_d_bead}"
                            fi
                        fi
                    fi
                fi
            fi
        fi
    fi
fi

# Drift check tier: fires if neither compound nor dispatch claimed this cycle.
if [[ -z "$REASON" && "$WEIGHT" -ge 3 ]]; then
    if [[ ! -f ".claude/clavain.no-driftcheck" ]]; then
        if intercore_sentinel_check_or_legacy "drift_throttle" "$SESSION_ID" 600; then
            # Guard: interwatch must be installed
            source "${SCRIPT_DIR}/lib.sh" 2>/dev/null || true
            INTERWATCH_ROOT=$(_discover_interwatch_plugin)
            if [[ -n "$INTERWATCH_ROOT" ]]; then
                REASON="Auto-drift-check: detected shipped-work signals [${SIGNALS}] (weight ${WEIGHT}). Documentation may be stale. Run /interwatch:watch using the Skill tool to scan for doc drift. If interwatch finds drift, follow its recommendations (auto-refresh for Certain/High confidence, suggest for Medium)."
            fi
        fi
    fi
fi

# If no tier claimed the cycle AND shadow trackers were found, block
if [[ -z "$REASON" && -n "$SHADOW_WARNING" ]]; then
    REASON="$SHADOW_WARNING"
fi

# No tier matched — nothing to do
if [[ -z "$REASON" ]]; then
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
