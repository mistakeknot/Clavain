#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Self-dispatch logic for autonomous bead selection and claiming.
# Sourced by auto-stop-actions.sh when CLAVAIN_SELF_DISPATCH=true.
#
# Architecture (from flux-drive review, 2026-03-20):
#   - Dispatch-specific scoring lives HERE, not in interphase's shared score_bead()
#   - Only emits a dispatch reason after confirmed bead_claim() success
#   - Circuit breaker counts infrastructure failures only, not claim races
#   - Per-session dispatch cap prevents runaway throughput

# Guard against double-sourcing
[[ -n "${_DISPATCH_LOADED:-}" ]] && return 0
_DISPATCH_LOADED=1

_DISPATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source dependencies
source "${_DISPATCH_DIR}/lib-intercore.sh" 2>/dev/null || true
source "${_DISPATCH_DIR}/lib-discovery.sh" 2>/dev/null || true
source "${_DISPATCH_DIR}/lib-sprint.sh" 2>/dev/null || true

# ─── Configuration ────────────────────────────────────────────────
DISPATCH_CAP="${CLAVAIN_DISPATCH_CAP:-5}"       # max dispatches per session
DISPATCH_CIRCUIT_THRESHOLD=3                     # consecutive infra failures to trip breaker
DISPATCH_COOLDOWN_SEC=20                         # seconds between dispatch attempts
DISPATCH_LOG="$HOME/.clavain/dispatch-log.jsonl" # telemetry log path
DISPATCH_REVIEW_PRESSURE_THRESHOLD="${CLAVAIN_REVIEW_PRESSURE_THRESHOLD:-3}"  # pending reviews before backpressure kicks in

# ─── Dispatch Cap ─────────────────────────────────────────────────
# NOTE: Read-modify-write on intercore state is not atomic, but dispatch cap
# is scoped to SESSION_ID which is unique per Claude Code process. Two hooks
# in the same session cannot run concurrently (Stop hooks are sequential),
# so the race window does not exist in practice.

# Check if session has reached dispatch cap.
# Returns: 0 if under cap, 1 if at/over cap
dispatch_cap_check() {
    local session_id="$1"
    local count
    count=$(intercore_state_get "dispatch_count" "$session_id" 2>/dev/null) || count=""
    # Parse — state may be JSON or raw string
    count=$(echo "$count" | jq -r '.count // empty' 2>/dev/null || echo "$count")
    count="${count:-0}"
    [[ "$count" =~ ^[0-9]+$ ]] || count=0
    [[ "$count" -lt "$DISPATCH_CAP" ]]
}

# Increment dispatch count for session.
_dispatch_cap_increment() {
    local session_id="$1"
    local count
    count=$(intercore_state_get "dispatch_count" "$session_id" 2>/dev/null) || count=""
    count=$(echo "$count" | jq -r '.count // empty' 2>/dev/null || echo "$count")
    count="${count:-0}"
    [[ "$count" =~ ^[0-9]+$ ]] || count=0
    count=$((count + 1))
    intercore_state_set "dispatch_count" "$session_id" "{\"count\":$count}" 2>/dev/null || true
}

# ─── Circuit Breaker ──────────────────────────────────────────────

# Check if circuit breaker is tripped (infrastructure failures only).
# Returns: 0 if OK, 1 if tripped
dispatch_circuit_check() {
    local session_id="$1"
    local failures
    failures=$(intercore_state_get "dispatch_failures" "$session_id" 2>/dev/null) || failures=""
    failures=$(echo "$failures" | jq -r '.count // empty' 2>/dev/null || echo "$failures")
    failures="${failures:-0}"
    [[ "$failures" =~ ^[0-9]+$ ]] || failures=0
    [[ "$failures" -lt "$DISPATCH_CIRCUIT_THRESHOLD" ]]
}

# Record an infrastructure failure (NOT a claim race).
_dispatch_circuit_increment() {
    local session_id="$1"
    local failures
    failures=$(intercore_state_get "dispatch_failures" "$session_id" 2>/dev/null) || failures=""
    failures=$(echo "$failures" | jq -r '.count // empty' 2>/dev/null || echo "$failures")
    failures="${failures:-0}"
    [[ "$failures" =~ ^[0-9]+$ ]] || failures=0
    failures=$((failures + 1))
    intercore_state_set "dispatch_failures" "$session_id" "{\"count\":$failures}" 2>/dev/null || true
}

# Reset circuit breaker on success.
_dispatch_circuit_reset() {
    local session_id="$1"
    intercore_state_set "dispatch_failures" "$session_id" '{"count":0}' 2>/dev/null || true
}

# ─── Logging ──────────────────────────────────────────────────────

dispatch_log() {
    local session_id="$1" bead_id="$2" score="$3" outcome="$4"
    mkdir -p "$(dirname "$DISPATCH_LOG")" 2>/dev/null || true
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf '{"ts":"%s","session":"%s","bead":"%s","score":%s,"outcome":"%s"}\n' \
        "$ts" "$session_id" "$bead_id" "${score:-0}" "$outcome" \
        >> "$DISPATCH_LOG" 2>/dev/null || true
}

# ─── Review Backpressure (rsj.1.3) ───────────────────────────────
# Count pending reviews. When review queue exceeds threshold, dispatch
# scores are penalized proportionally. At 2x threshold, dispatch cap
# drops to 1 ("in the weeds" protocol from cuisine agent).

# Returns: count of beads awaiting review on stdout
_dispatch_review_pressure() {
    local pending=0
    if command -v bd &>/dev/null; then
        # Count beads that are shipped/closed but need review (needs-review label)
        # OR beads in quality-gates/shipping phase (pending quality check)
        pending=$(bd list --status=open --label=needs-review 2>/dev/null | grep -c '○\|◐\|●' 2>/dev/null) || pending=0
        # Also count beads in shipping phase (awaiting quality gates)
        local shipping
        shipping=$(bd list --status=in_progress 2>/dev/null | grep -c 'shipping\|quality' 2>/dev/null) || shipping=0
        pending=$(( pending + shipping ))
    fi
    [[ "$pending" =~ ^[0-9]+$ ]] || pending=0
    echo "$pending"
}

# ─── Scoring & Filtering ─────────────────────────────────────────

# Re-score discovery_scan_beads output with dispatch-specific filters.
# Filters OUT: orphans (id null), beads with unsatisfied deps, already-claimed beads.
# Adds: random perturbation for tie-breaking.
# Args: $1 = JSON array from discovery_scan_beads
# Output: JSON array sorted by adjusted score DESC, or "[]"
dispatch_rescore() {
    local scan_json="$1"

    # Validate input
    if [[ -z "$scan_json" ]] || ! echo "$scan_json" | jq empty 2>/dev/null; then
        echo "[]"
        return 0
    fi

    # Filter out orphans (id: null) and already-claimed beads
    local filtered
    filtered=$(echo "$scan_json" | jq '[.[] | select(.id != null and .id != "" and (.status != "in_progress"))]' 2>/dev/null) || {
        echo "[]"
        return 0
    }

    local count
    count=$(echo "$filtered" | jq 'length' 2>/dev/null) || count=0
    if [[ "$count" -eq 0 ]]; then
        echo "[]"
        return 0
    fi

    # Review backpressure: compute penalty once for all candidates (rsj.1.3)
    local review_depth pressure_penalty
    review_depth=$(_dispatch_review_pressure)
    pressure_penalty=0
    if [[ "$review_depth" -gt "$DISPATCH_REVIEW_PRESSURE_THRESHOLD" ]]; then
        # 5 points per excess review — proportional, not binary
        pressure_penalty=$(( (review_depth - DISPATCH_REVIEW_PRESSURE_THRESHOLD) * 5 ))
    fi

    # Bulk-fetch Ockham offsets once per dispatch cycle (not per-bead)
    declare -A _ockham_offsets
    if intercore_available 2>/dev/null; then
        local _ock_scope _ock_val
        while IFS= read -r _ock_scope; do
            [[ -z "$_ock_scope" ]] && continue
            _ock_val=$(intercore_state_get "ockham_offset" "$_ock_scope") || continue
            # Extract numeric offset — may be bare int or JSON {"offset":N}
            if [[ "$_ock_val" =~ ^-?[0-9]+$ ]]; then
                : # already numeric
            else
                _ock_val=$(echo "$_ock_val" | jq -r '.offset // 0' 2>/dev/null) || _ock_val=0
            fi
            [[ "$_ock_val" =~ ^-?[0-9]+$ ]] || _ock_val=0
            # Clamp to [-6, +6] (defense in depth — Ockham clamps at write, dispatch clamps at read)
            (( _ock_val > 6 )) && _ock_val=6
            (( _ock_val < -6 )) && _ock_val=-6
            _ockham_offsets["$_ock_scope"]=$_ock_val
        done < <("$INTERCORE_BIN" state list ockham_offset 2>/dev/null || true)
    fi

    # Check deps for each bead and add perturbation
    local result="[]"
    local i bead_id score deps_ok deps_json perturbation adjusted_score _ock_off
    for (( i=0; i<count; i++ )); do
        bead_id=$(echo "$filtered" | jq -r ".[$i].id" 2>/dev/null) || continue
        score=$(echo "$filtered" | jq -r ".[$i].score // 0" 2>/dev/null) || score=0
        # Guard: ensure score is numeric (failed jq returns empty/non-numeric)
        [[ "$score" =~ ^[0-9]+$ ]] || score=0

        # Validate bead_id format (security: prevent shell injection)
        if [[ ! "$bead_id" =~ ^[A-Za-z0-9._-]+$ ]]; then
            continue
        fi

        # Deps check: skip beads with unsatisfied dependencies
        deps_ok=true
        if command -v bd &>/dev/null; then
            deps_json=$(bd dep list "$bead_id" --direction=down --json 2>/dev/null) || deps_json="[]"
            if echo "$deps_json" | jq -e '.[] | select(.status != "closed")' &>/dev/null; then
                deps_ok=false
            fi
        fi
        [[ "$deps_ok" == "false" ]] && continue

        # Lane pause check (rsj.1.5): skip beads in paused lanes
        if command -v bd &>/dev/null; then
            local _bead_labels _bead_lane _lane_paused
            _bead_labels=$(bd show "$bead_id" --json 2>/dev/null | jq -r '.labels[]? // empty' 2>/dev/null) || _bead_labels=""
            _bead_lane=$(echo "$_bead_labels" | grep -oP '^lane:\K.*' | head -1) || _bead_lane=""
            if [[ -n "$_bead_lane" ]]; then
                _lane_paused=$(ic lane status "$_bead_lane" --json 2>/dev/null | jq -r '.metadata.paused // empty' 2>/dev/null) || _lane_paused=""
                if [[ "$_lane_paused" == "true" ]]; then
                    dispatch_log "$session_id" "$bead_id" "0" "lane_paused:$_bead_lane"
                    continue
                fi
            fi
        fi

        # Ockham offset: apply governor weight adjustment (missing → 0, fail-open)
        _ock_off=${_ockham_offsets[$bead_id]:-0}

        # Add random perturbation (0-5) for tie-breaking, subtract review pressure
        perturbation=$(( RANDOM % 6 ))
        adjusted_score=$(( score + _ock_off + perturbation - pressure_penalty ))
        # Floor at 1 — still claimable, just deprioritized
        (( adjusted_score < 1 )) && adjusted_score=1

        # Log scoring breakdown per bead (raw_score, ockham_offset, final_score)
        dispatch_log "$session_id" "$bead_id" "$adjusted_score" "scored:raw=$score,offset=$_ock_off,final=$adjusted_score"

        result=$(echo "$result" | jq \
            --arg id "$bead_id" \
            --argjson score "$adjusted_score" \
            --argjson orig "$score" \
            --argjson offset "$_ock_off" \
            '. + [{"id": $id, "score": $score, "orig_score": $orig, "ockham_offset": $offset}]' 2>/dev/null) || continue
    done

    # Sort by score DESC
    echo "$result" | jq 'sort_by(-.score)' 2>/dev/null || echo "[]"
}

# ─── Claim Attempt ────────────────────────────────────────────────

# Attempt to claim the top bead from a rescored list.
# On race loss: re-scan fresh, rescore, try next candidate (max 2 attempts total).
# Args: $1 = session_id
# Output: "bead_id|score" on success, empty string on failure
# Returns: 0 on success, 1 on failure
dispatch_attempt_claim() {
    local session_id="$1"
    local attempt

    # "In the weeds" protocol (rsj.1.3): when review queue is deeply backed up,
    # reduce dispatch cap to 1 — recover flow before producing more work.
    local _review_depth
    _review_depth=$(_dispatch_review_pressure)
    if [[ "$_review_depth" -gt $(( DISPATCH_REVIEW_PRESSURE_THRESHOLD * 2 )) ]]; then
        DISPATCH_CAP=1
        dispatch_log "$session_id" "" "0" "in_the_weeds"
    fi

    for (( attempt=0; attempt<2; attempt++ )); do
        # Get fresh scan on each attempt (critical: don't use stale data on retry)
        local scan_json
        scan_json=$(discovery_scan_beads 2>/dev/null) || scan_json=""

        # Check for infrastructure failure
        case "$scan_json" in
            DISCOVERY_UNAVAILABLE|DISCOVERY_ERROR|"")
                _dispatch_circuit_increment "$session_id"
                dispatch_log "$session_id" "" "0" "infra_error"
                return 1
                ;;
        esac

        local rescored
        rescored=$(dispatch_rescore "$scan_json")
        local candidate_count
        candidate_count=$(echo "$rescored" | jq 'length' 2>/dev/null) || candidate_count=0

        if [[ "$candidate_count" -eq 0 ]]; then
            if [[ "$attempt" -gt 0 ]]; then
                # Empty on retry suggests infra degradation (e.g., Dolt restart),
                # not genuinely empty backlog. Count toward circuit breaker.
                _dispatch_circuit_increment "$session_id"
                dispatch_log "$session_id" "" "0" "empty_on_retry"
            else
                dispatch_log "$session_id" "" "0" "no_candidates"
            fi
            return 1
        fi

        # Try candidates in score order
        local j bead_id score
        for (( j=0; j<candidate_count && j<3; j++ )); do
            bead_id=$(echo "$rescored" | jq -r ".[$j].id" 2>/dev/null) || continue
            score=$(echo "$rescored" | jq -r ".[$j].score // 0" 2>/dev/null) || score=0

            # Add jitter to desynchronize multi-agent races
            # Use BASHPID modulo to avoid 32-bit signed overflow (BASHPID*31337 wraps negative)
            local jitter=$(( (RANDOM + (BASHPID % 1000)) % 400 + 100 ))
            sleep "0.$jitter" 2>/dev/null || true

            # Attempt atomic claim — only emit result on confirmed success
            if bead_claim "$bead_id" "$session_id" 2>/dev/null; then
                _dispatch_circuit_reset "$session_id"
                _dispatch_cap_increment "$session_id"
                dispatch_log "$session_id" "$bead_id" "$score" "claimed"
                echo "${bead_id}|${score}"
                return 0
            fi

            # Claim race loss — NOT an infrastructure failure, don't count toward breaker
            dispatch_log "$session_id" "$bead_id" "$score" "race_lost"
        done

        # All candidates in this scan were race-lost; loop will re-scan fresh
    done

    dispatch_log "$session_id" "" "0" "exhausted"
    return 1
}
