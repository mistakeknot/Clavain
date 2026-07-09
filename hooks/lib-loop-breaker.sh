#!/usr/bin/env bash
# Loop breaker for Stop-hook block reasons (mk-ax8).
#
# A Stop hook that re-demands the SAME reason forever while no work happens
# is blocked on something outside the model's control (usually a human
# gate) — and every re-fire burns full model turns (killed sessions
# 7740ea4b: 1M+ tokens of identical loops; 77311be1: Touch ID gate).
# Time-based sentinels can't catch this: over a multi-hour session the
# throttle expires and the identical demand re-fires. This library
# classifies the blocked state by progress, not time:
#
#   first fire of a reason          → pass through, record fingerprint
#   same reason, work happened      → pass through (progress resets state)
#   same reason, NO work happened   → replace with one BLOCKED message,
#                                     mark suppressed, log a galiana KPI
#   further identical fires         → suppress silently for the session
#
# "Work happened" = HEAD moved or `git status --porcelain` changed since
# the previous fire (both cheap and already available to every hook).
#
# Usage (from a Stop hook, after composing $REASON):
#   source "${SCRIPT_DIR}/lib-loop-breaker.sh"
#   if REASON=$(loop_breaker_filter "$SESSION_ID" "$REASON"); then
#       ... emit {"decision":"block","reason":$REASON} ...
#   else
#       exit 0   # suppressed — session is parked on a human gate
#   fi

_lb_hash() {
    if command -v sha256sum &>/dev/null; then
        sha256sum | cut -d' ' -f1
    else
        shasum -a 256 | cut -d' ' -f1
    fi
}

# loop_breaker_filter <session_id> <reason>
# stdout: the reason to emit (possibly replaced by the BLOCKED message)
# return: 0 = emit stdout as the block reason; 1 = suppress silently
loop_breaker_filter() {
    local session_id="$1" reason="$2"
    local state_dir="${CLAVAIN_LOOP_BREAKER_DIR:-$HOME/.clavain/stop-loop-breaker}"
    mkdir -p "$state_dir" 2>/dev/null || { printf '%s' "$reason"; return 0; }
    local state_file
    state_file="$state_dir/$(echo "$session_id" | tr '/:' '__').json"

    local rhash head porcelain fp
    rhash=$(printf '%s' "$reason" | _lb_hash)
    head=$(git rev-parse HEAD 2>/dev/null) || head="nogit"
    porcelain=$(git status --porcelain 2>/dev/null | _lb_hash)
    fp="${head}:${porcelain}"

    local prev_hash="" prev_fp="" suppressed="false"
    if [[ -f "$state_file" ]] && command -v jq &>/dev/null; then
        prev_hash=$(jq -r '.hash // ""' "$state_file" 2>/dev/null) || prev_hash=""
        prev_fp=$(jq -r '.fp // ""' "$state_file" 2>/dev/null) || prev_fp=""
        suppressed=$(jq -r '.suppressed // false | tostring' "$state_file" 2>/dev/null) || suppressed="false"
    fi

    if [[ "$rhash" == "$prev_hash" && "$fp" == "$prev_fp" ]]; then
        if [[ "$suppressed" == "true" ]]; then
            # Third+ identical fire: stay silent, count it.
            type galiana_log_stop_suppression &>/dev/null \
                && galiana_log_stop_suppression "$session_id" "$rhash" "silent" || true
            return 1
        fi
        # Second identical fire with zero progress: park the session.
        printf '{"hash":"%s","fp":"%s","suppressed":true}' "$rhash" "$fp" \
            > "$state_file" 2>/dev/null || true
        type galiana_log_stop_suppression &>/dev/null \
            && galiana_log_stop_suppression "$session_id" "$rhash" "blocked_message" || true
        printf '%s' "BLOCKED — awaiting a human gate. This exact stop-hook demand already fired this session and no commits or file changes have happened since, so repeating it cannot succeed. Do NOT retry the demanded action. Tell the user in one short message what you are blocked on (list the outstanding manual steps), then stop. Further identical demands will be suppressed for this session."
        return 0
    fi

    # New reason, or real progress since the last fire: reset state.
    printf '{"hash":"%s","fp":"%s","suppressed":false}' "$rhash" "$fp" \
        > "$state_file" 2>/dev/null || true
    printf '%s' "$reason"
    return 0
}
