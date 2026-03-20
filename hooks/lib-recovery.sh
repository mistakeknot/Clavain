#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Failure classification and recovery logic for factory watchdog.
# Sourced by watchdog.go (via shell exec) and lib-dispatch.sh.
#
# Three failure classes (from flux-drive research, 2026-03-20):
#   retriable    — agent crash, timeout, transient env issue. Safe for auto-retry.
#   spec_blocked — ambiguous spec, missing context. Needs human.
#   env_blocked  — infra broken (auth, Dolt, disk). Needs SRE fix.

# Guard against double-sourcing
[[ -n "${_RECOVERY_LOADED:-}" ]] && return 0
_RECOVERY_LOADED=1

_RECOVERY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source dependencies
source "${_RECOVERY_DIR}/lib-intercore.sh" 2>/dev/null || true

# ─── Configuration ────────────────────────────────────────────────
RECOVERY_STALE_TTL="${CLAVAIN_STALE_TTL:-600}"       # seconds before a claim is stale
RECOVERY_HEARTBEAT_RATIO=10                           # TTL / heartbeat interval
RECOVERY_MAX_RETRIES=3                                # max auto-retries before quarantine
RECOVERY_LOG="$HOME/.clavain/recovery-log.jsonl"      # recovery event log

# ─── Failure Classification ──────────────────────────────────────

# Classify a failure based on available signals.
# Args: $1=bead_id
# Reads: intermux pane status, error output from bead state, attempt count
# Outputs: "retriable", "spec_blocked", or "env_blocked"
recovery_classify_failure() {
    local bead_id="$1"
    [[ -z "$bead_id" ]] && echo "retriable" && return 0

    # Gather signals
    local attempt_count error_output pane_status
    attempt_count=$(recovery_get_attempt_count "$bead_id")
    error_output=$(bd state "$bead_id" "last_error" 2>/dev/null) || error_output=""
    pane_status=$(recovery_check_pane "$bead_id")

    # Rule 1: Environment errors — match infra patterns
    if _matches_env_pattern "$error_output"; then
        # Correlated check: 2+ env failures within 120s → definitely env
        local recent_env_failures
        recent_env_failures=$(_count_recent_failures "$bead_id" "env_blocked" 120)
        if [[ "$recent_env_failures" -ge 1 ]]; then
            echo "env_blocked"
            return 0
        fi
        # Single env pattern match — still env_blocked but first occurrence
        echo "env_blocked"
        return 0
    fi

    # Rule 2: Spec-blocked — 2+ failed attempts with no commits, or ambiguous error
    if _matches_spec_pattern "$error_output"; then
        echo "spec_blocked"
        return 0
    fi
    if [[ "$attempt_count" -ge 2 ]]; then
        local has_commits
        has_commits=$(_bead_has_recent_commits "$bead_id")
        if [[ "$has_commits" == "false" ]]; then
            echo "spec_blocked"
            return 0
        fi
    fi

    # Rule 3: Agent crash — pane dead or process gone
    if [[ "$pane_status" == "dead" || "$pane_status" == "crashed" ]]; then
        echo "retriable"
        return 0
    fi

    # Default: retriable (transient)
    echo "retriable"
}

# ─── Signal Helpers ──────────────────────────────────────────────

# Check if error output matches environment/infrastructure patterns.
_matches_env_pattern() {
    local output="$1"
    [[ -z "$output" ]] && return 1
    # Patterns: auth failures, Dolt issues, disk space, network
    echo "$output" | grep -qiE '(ENOSPC|disk full|no space|auth.*fail|permission denied|Dolt.*error|Dolt.*EOF|ECONNREFUSED|connection refused|OOM|out of memory|cannot allocate)' 2>/dev/null
}

# Check if error output matches spec/ambiguity patterns.
_matches_spec_pattern() {
    local output="$1"
    [[ -z "$output" ]] && return 1
    echo "$output" | grep -qiE '(ambiguous|unclear|conflicting|missing context|underspecified|cannot determine|no such file or directory.*spec|unknown requirement)' 2>/dev/null
}

# Get attempt count for a bead from state.
recovery_get_attempt_count() {
    local bead_id="$1"
    local count
    count=$(bd state "$bead_id" "attempt_count" 2>/dev/null) || count=""
    # Strip bd state prefix if present
    count=$(echo "$count" | grep -oE '[0-9]+' | head -1)
    echo "${count:-0}"
}

# Increment attempt count for a bead.
recovery_increment_attempt() {
    local bead_id="$1"
    local current
    current=$(recovery_get_attempt_count "$bead_id")
    local next=$((current + 1))
    bd set-state "$bead_id" "attempt_count=$next" 2>/dev/null || true
}

# Check intermux/tmux pane status for a bead.
# Returns: "alive", "dead", "crashed", or "unknown"
recovery_check_pane() {
    local bead_id="$1"

    # Try intermux first (structured status)
    local claimer
    claimer=$(bd state "$bead_id" "claimed_by" 2>/dev/null) || claimer=""
    claimer=$(echo "$claimer" | sed 's/(no .*//' | xargs)
    [[ -z "$claimer" || "$claimer" == "released" ]] && echo "dead" && return 0

    # Check if tmux session/pane exists for this claimer
    if command -v tmux &>/dev/null; then
        # Look for a pane with this session ID or bead ID in the name
        local pane_count
        pane_count=$(tmux list-panes -a -F '#{pane_title}' 2>/dev/null | grep -c "$bead_id" 2>/dev/null) || pane_count=0
        if [[ "$pane_count" -eq 0 ]]; then
            # Also check by session ID
            pane_count=$(tmux list-panes -a -F '#{pane_title}' 2>/dev/null | grep -c "$claimer" 2>/dev/null) || pane_count=0
        fi
        [[ "$pane_count" -eq 0 ]] && echo "dead" && return 0
        echo "alive"
        return 0
    fi

    echo "unknown"
}

# Count recent failures of a specific class within a time window.
_count_recent_failures() {
    local bead_id="$1" failure_class="$2" window_sec="$3"
    local cutoff_ts
    cutoff_ts=$(($(date +%s) - window_sec))

    if [[ -f "$RECOVERY_LOG" ]]; then
        jq -r --arg bid "$bead_id" --arg fc "$failure_class" --argjson cutoff "$cutoff_ts" \
            '[.[] | select(.bead == $bid and .failure_class == $fc and (.ts_epoch // 0) > $cutoff)] | length' \
            <(tail -100 "$RECOVERY_LOG") 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

# Check if a bead has recent commits (proxy for "agent made progress").
_bead_has_recent_commits() {
    local bead_id="$1"
    # Check git log for commits mentioning this bead in last 30 minutes
    local count
    count=$(git log --since="30 minutes ago" --oneline --grep="$bead_id" 2>/dev/null | wc -l) || count=0
    [[ "$count" -gt 0 ]] && echo "true" || echo "false"
}

# ─── Recovery Actions ────────────────────────────────────────────

# Release a bead with failure classification.
# Args: $1=bead_id $2=failure_class $3=reason (optional)
recovery_release_bead() {
    local bead_id="$1" failure_class="$2" reason="${3:-}"

    # Write failure class to bead state
    bd set-state "$bead_id" "failure_class=$failure_class" 2>/dev/null || true
    bd set-state "$bead_id" "last_recovery=$(date +%s)" 2>/dev/null || true

    # Increment attempt count
    recovery_increment_attempt "$bead_id"

    # Release the claim
    clavain-cli bead-release "$bead_id" 2>/dev/null || {
        # Fallback: direct bd state reset
        bd set-state "$bead_id" "claimed_by=released" 2>/dev/null || true
        bd set-state "$bead_id" "claimed_at=0" 2>/dev/null || true
    }

    # Log recovery event
    recovery_log "$bead_id" "$failure_class" "released" "$reason"
}

# Quarantine a bead (set status=blocked, add label).
# Args: $1=bead_id $2=failure_class $3=reason
recovery_quarantine_bead() {
    local bead_id="$1" failure_class="$2" reason="${3:-}"

    # Release claim first
    recovery_release_bead "$bead_id" "$failure_class" "$reason"

    # Set blocked status
    bd update "$bead_id" --status=blocked 2>/dev/null || true

    # Add quarantine labels
    local label="needs-human"
    [[ "$failure_class" == "env_blocked" ]] && label="needs-infra"
    bd update "$bead_id" --add-label "quarantine:$label" 2>/dev/null || true

    recovery_log "$bead_id" "$failure_class" "quarantined" "$reason"
}

# ─── Logging ─────────────────────────────────────────────────────

recovery_log() {
    local bead_id="$1" failure_class="$2" action="$3" reason="${4:-}"
    mkdir -p "$(dirname "$RECOVERY_LOG")" 2>/dev/null || true
    local ts ts_epoch
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    ts_epoch=$(date +%s)
    printf '{"ts":"%s","ts_epoch":%s,"bead":"%s","failure_class":"%s","action":"%s","reason":"%s"}\n' \
        "$ts" "$ts_epoch" "$bead_id" "$failure_class" "$action" "$reason" \
        >> "$RECOVERY_LOG" 2>/dev/null || true
}
