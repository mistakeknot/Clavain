#!/usr/bin/env bash
# Sprint-specific state library for Clavain.
# Sprint beads are type=epic beads with sprint=true state.
# All functions are fail-safe (return 0 on error, never block workflow)
# EXCEPT sprint_claim() which returns 1 on conflict (callers must handle).

# Guard against double-sourcing
[[ -n "${_SPRINT_LOADED:-}" ]] && return 0
_SPRINT_LOADED=1

SPRINT_LIB_PROJECT_DIR="${SPRINT_LIB_PROJECT_DIR:-.}"

# Source interphase phase primitives (via Clavain shim)
_SPRINT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_SPRINT_LIB_DIR}/lib.sh" 2>/dev/null || true

# Source gates for advance_phase (via shim → interphase)
export GATES_PROJECT_DIR="$SPRINT_LIB_PROJECT_DIR"
source "${_SPRINT_LIB_DIR}/lib-gates.sh" 2>/dev/null || true

# ─── jq dependency check ─────────────────────────────────────────
# jq is required for all JSON operations. Stub out functions if missing.
if ! command -v jq &>/dev/null; then
    sprint_create() { echo ""; }
    sprint_finalize_init() { return 0; }
    sprint_find_active() { echo "[]"; }
    sprint_read_state() { echo "{}"; }
    sprint_set_artifact() { return 0; }
    sprint_record_phase_completion() { return 0; }
    sprint_claim() { return 0; }
    sprint_release() { return 0; }
    sprint_next_step() { echo "brainstorm"; }
    sprint_invalidate_caches() { return 0; }
    return 0
fi

# ─── Sprint CRUD ────────────────────────────────────────────────────

# Create a sprint bead. Returns bead ID to stdout.
# Sets sprint=true, phase=brainstorm, sprint_initialized=false.
# Caller MUST call sprint_finalize_init() after all setup.
# CORRECTNESS: If any set-state call fails after bd create succeeds, the bead
# is cancelled to prevent zombie state. Callers receive "".
sprint_create() {
    local title="${1:-Sprint}"

    if ! command -v bd &>/dev/null; then
        echo ""
        return 0
    fi

    local sprint_id
    sprint_id=$(bd create --title="$title" --type=epic --priority=2 2>/dev/null \
        | awk 'match($0, /[A-Za-z]+-[a-z0-9]+/) { print substr($0, RSTART, RLENGTH); exit }') || {
        echo ""
        return 0
    }

    if [[ -z "$sprint_id" ]]; then
        echo ""
        return 0
    fi

    # Initialize critical state fields (fail early if any write fails)
    bd set-state "$sprint_id" "sprint=true" 2>/dev/null || {
        bd update "$sprint_id" --status=cancelled 2>/dev/null || true
        echo ""; return 0
    }
    bd set-state "$sprint_id" "phase=brainstorm" 2>/dev/null || {
        bd update "$sprint_id" --status=cancelled 2>/dev/null || true
        echo ""; return 0
    }
    bd set-state "$sprint_id" "sprint_artifacts={}" 2>/dev/null || true
    bd set-state "$sprint_id" "sprint_initialized=false" 2>/dev/null || true
    bd set-state "$sprint_id" "phase_history={}" 2>/dev/null || true
    bd update "$sprint_id" --status=in_progress 2>/dev/null || true

    # Verify critical state was written
    local verify_phase
    verify_phase=$(bd state "$sprint_id" phase 2>/dev/null)
    if [[ "$verify_phase" != "brainstorm" ]]; then
        echo "sprint_create: initialization failed, cancelling bead $sprint_id" >&2
        bd update "$sprint_id" --status=cancelled 2>/dev/null || true
        echo ""
        return 0
    fi

    echo "$sprint_id"
}

# Mark sprint as fully initialized. Discovery skips uninitialized sprints.
sprint_finalize_init() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && return 0
    bd set-state "$sprint_id" "sprint_initialized=true" 2>/dev/null || true
}

# ─── Sprint Discovery ──────────────────────────────────────────────

# Find active sprint beads (in_progress with sprint=true).
# Output: JSON array [{id, title, phase, ...}] or "[]"
sprint_find_active() {
    if ! command -v bd &>/dev/null; then
        echo "[]"
        return 0
    fi

    if [[ ! -d "${SPRINT_LIB_PROJECT_DIR}/.beads" ]]; then
        echo "[]"
        return 0
    fi

    local ip_list
    ip_list=$(bd list --status=in_progress --json 2>/dev/null) || {
        echo "[]"
        return 0
    }

    # Validate JSON — must be an array
    echo "$ip_list" | jq 'if type != "array" then error("expected array") else . end' >/dev/null 2>&1 || {
        echo "[]"
        return 0
    }

    # Filter for sprint=true beads that are initialized
    local count
    count=$(echo "$ip_list" | jq 'length' 2>/dev/null) || count=0

    local results="[]"
    local i=0
    local max_iterations=100  # Safety limit
    while [[ $i -lt $count && $i -lt $max_iterations ]]; do
        local bead_id
        bead_id=$(echo "$ip_list" | jq -r ".[$i].id // empty")
        [[ -z "$bead_id" ]] && { i=$((i + 1)); continue; }

        # Check sprint=true state
        local is_sprint
        is_sprint=$(bd state "$bead_id" sprint 2>/dev/null) || is_sprint=""
        if [[ "$is_sprint" != "true" ]]; then
            i=$((i + 1))
            continue
        fi

        # Check initialized
        local initialized
        initialized=$(bd state "$bead_id" sprint_initialized 2>/dev/null) || initialized=""
        if [[ "$initialized" != "true" ]]; then
            i=$((i + 1))
            continue
        fi

        local title phase
        title=$(echo "$ip_list" | jq -r ".[$i].title // \"Untitled\"")
        phase=$(bd state "$bead_id" phase 2>/dev/null) || phase=""

        results=$(echo "$results" | jq \
            --arg id "$bead_id" \
            --arg title "$title" \
            --arg phase "$phase" \
            '. + [{id: $id, title: $title, phase: $phase}]')

        i=$((i + 1))
    done

    echo "$results"
}

# ─── Sprint State ──────────────────────────────────────────────────

# Read all sprint state fields at once. Output: JSON object.
sprint_read_state() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && { echo "{}"; return 0; }

    local phase sprint_artifacts phase_history complexity auto_advance active_session
    phase=$(bd state "$sprint_id" phase 2>/dev/null) || phase=""
    sprint_artifacts=$(bd state "$sprint_id" sprint_artifacts 2>/dev/null) || sprint_artifacts="{}"
    phase_history=$(bd state "$sprint_id" phase_history 2>/dev/null) || phase_history="{}"
    complexity=$(bd state "$sprint_id" complexity 2>/dev/null) || complexity=""
    auto_advance=$(bd state "$sprint_id" auto_advance 2>/dev/null) || auto_advance="true"
    active_session=$(bd state "$sprint_id" active_session 2>/dev/null) || active_session=""

    # Validate JSON fields (fall back to defaults if corrupt)
    echo "$sprint_artifacts" | jq empty 2>/dev/null || sprint_artifacts="{}"
    echo "$phase_history" | jq empty 2>/dev/null || phase_history="{}"

    jq -n -c \
        --arg id "$sprint_id" \
        --arg phase "$phase" \
        --argjson artifacts "$sprint_artifacts" \
        --argjson history "$phase_history" \
        --arg complexity "$complexity" \
        --arg auto_advance "$auto_advance" \
        --arg active_session "$active_session" \
        '{id: $id, phase: $phase, artifacts: $artifacts, history: $history,
          complexity: $complexity, auto_advance: $auto_advance, active_session: $active_session}'
}

# Update a single artifact path with filesystem locking.
# CORRECTNESS: ALL updates to sprint_artifacts MUST go through this function.
# Direct `bd set-state` calls bypass the lock and cause lost-update races.
# Lock cleanup: Stale locks (>5s old) are force-broken. If process is killed
# while holding lock, next caller after timeout will take over. During timeout
# window, updates fail silently (fail-safe design).
sprint_set_artifact() {
    local sprint_id="$1"
    local artifact_type="$2"
    local artifact_path="$3"

    [[ -z "$sprint_id" || -z "$artifact_type" || -z "$artifact_path" ]] && return 0

    local lock_dir="/tmp/sprint-lock-${sprint_id}"

    # Acquire lock (mkdir is atomic on all POSIX systems)
    local retries=0
    while ! mkdir "$lock_dir" 2>/dev/null; do
        retries=$((retries + 1))
        [[ $retries -gt 10 ]] && {
            # Force-break stale lock (older than 5 seconds — artifact updates are <1s)
            local lock_mtime
            lock_mtime=$(stat -c %Y "$lock_dir" 2>/dev/null)
            if [[ -z "$lock_mtime" ]]; then
                echo "sprint_set_artifact: lock stat failed for $lock_dir" >&2
                return 0
            fi
            local now
            now=$(date +%s)
            if [[ $((now - lock_mtime)) -gt 5 ]]; then
                rmdir "$lock_dir" 2>/dev/null || rm -rf "$lock_dir" 2>/dev/null || true
                mkdir "$lock_dir" 2>/dev/null || return 0
                break
            fi
            return 0  # Give up — fail-safe
        }
        sleep 0.1
    done

    # Read-modify-write under lock
    local current
    current=$(bd state "$sprint_id" sprint_artifacts 2>/dev/null) || current="{}"
    echo "$current" | jq empty 2>/dev/null || current="{}"

    local updated
    updated=$(echo "$current" | jq --arg type "$artifact_type" --arg path "$artifact_path" \
        '.[$type] = $path')

    bd set-state "$sprint_id" "sprint_artifacts=$updated" 2>/dev/null || true

    # Release lock
    rmdir "$lock_dir" 2>/dev/null || true
}

# Record phase completion timestamp in phase_history.
# Also invalidates discovery caches so session-start picks up the new phase.
sprint_record_phase_completion() {
    local sprint_id="$1"
    local phase="$2"

    [[ -z "$sprint_id" || -z "$phase" ]] && return 0

    local lock_dir="/tmp/sprint-lock-${sprint_id}"
    local retries=0
    while ! mkdir "$lock_dir" 2>/dev/null; do
        retries=$((retries + 1))
        [[ $retries -gt 10 ]] && return 0
        sleep 0.1
    done

    local current
    current=$(bd state "$sprint_id" phase_history 2>/dev/null) || current="{}"
    echo "$current" | jq empty 2>/dev/null || current="{}"

    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local key="${phase}_at"
    local updated
    updated=$(echo "$current" | jq --arg key "$key" --arg ts "$ts" '.[$key] = $ts')

    bd set-state "$sprint_id" "phase_history=$updated" 2>/dev/null || true

    rmdir "$lock_dir" 2>/dev/null || true

    # Invalidate discovery caches so session-start picks up the new phase
    sprint_invalidate_caches
}

# ─── Session Claim ─────────────────────────────────────────────────

# Claim a sprint for this session. Prevents concurrent resume.
# Returns 0 if claimed, 1 if another session holds it.
# NOT fail-safe — returns 1 on conflict so callers can handle gracefully.
# CORRECTNESS: This uses mkdir lock + write-then-verify to serialize claims.
# Two sessions can pass the TTL check simultaneously and race on the write.
# The lock + verify detects the loser, but callers MUST handle claim failure.
sprint_claim() {
    local sprint_id="$1"
    local session_id="$2"

    [[ -z "$sprint_id" || -z "$session_id" ]] && return 0

    # Acquire claim lock to serialize concurrent claim attempts
    local claim_lock="/tmp/sprint-claim-lock-${sprint_id}"
    if ! mkdir "$claim_lock" 2>/dev/null; then
        # Another session is claiming right now — wait briefly then check
        sleep 0.3
        local current_claim
        current_claim=$(bd state "$sprint_id" active_session 2>/dev/null) || current_claim=""
        if [[ "$current_claim" == "$session_id" ]]; then
            return 0  # We already own it
        fi
        echo "Sprint $sprint_id is being claimed by another session" >&2
        return 1
    fi

    # Check for existing claim (under lock)
    local current_claim claim_ts
    current_claim=$(bd state "$sprint_id" active_session 2>/dev/null) || current_claim=""
    claim_ts=$(bd state "$sprint_id" claim_timestamp 2>/dev/null) || claim_ts=""

    if [[ -n "$current_claim" && "$current_claim" != "$session_id" ]]; then
        # Check TTL (60 minutes)
        if [[ -n "$claim_ts" ]]; then
            local claim_epoch now_epoch age_minutes
            claim_epoch=$(date -d "$claim_ts" +%s 2>/dev/null || echo 0)
            now_epoch=$(date +%s)
            age_minutes=$(( (now_epoch - claim_epoch) / 60 ))
            if [[ $age_minutes -lt 60 ]]; then
                echo "Sprint $sprint_id is active in session ${current_claim:0:8} (${age_minutes}m ago)" >&2
                rmdir "$claim_lock" 2>/dev/null || true
                return 1
            fi
            # Expired — take over
        else
            # No timestamp — might be stale. Allow takeover.
            true
        fi
    fi

    # Write claim (under lock — no race possible now)
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    bd set-state "$sprint_id" "active_session=$session_id" 2>/dev/null || true
    bd set-state "$sprint_id" "claim_timestamp=$ts" 2>/dev/null || true

    # Verify claim
    local verify
    verify=$(bd state "$sprint_id" active_session 2>/dev/null) || verify=""
    rmdir "$claim_lock" 2>/dev/null || true

    if [[ "$verify" != "$session_id" ]]; then
        echo "Failed to claim sprint $sprint_id (write verification failed)" >&2
        return 1
    fi

    return 0
}

# Release sprint claim. Used for manual cleanup or session-end hooks.
sprint_release() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && return 0
    bd set-state "$sprint_id" "active_session=" 2>/dev/null || true
    bd set-state "$sprint_id" "claim_timestamp=" 2>/dev/null || true
}

# ─── Gate Wrapper ──────────────────────────────────────────────────

# Wrapper for check_phase_gate (interphase). Provides enforce_gate API
# that sprint.md references. Returns 0 if gate passes, 1 if blocked.
enforce_gate() {
    local bead_id="$1"
    local target_phase="$2"
    local artifact_path="${3:-}"
    if type check_phase_gate &>/dev/null; then
        check_phase_gate "$bead_id" "$target_phase" "$artifact_path"
    else
        return 0  # No gate library — pass through
    fi
}

# ─── Phase Routing ─────────────────────────────────────────────────

# Determine the next command for a sprint based on its current phase.
# Output: command name (e.g., "brainstorm", "write-plan", "work")
sprint_next_step() {
    local phase="$1"

    case "$phase" in
        ""|brainstorm)           echo "brainstorm" ;;
        brainstorm-reviewed)     echo "strategy" ;;
        strategized)             echo "write-plan" ;;
        planned)                 echo "flux-drive" ;;
        plan-reviewed)           echo "work" ;;
        executing)               echo "work" ;;
        shipping)                echo "ship" ;;
        done)                    echo "done" ;;
        *)                       echo "brainstorm" ;;
    esac
}

# ─── Invalidation ─────────────────────────────────────────────────

# Invalidate discovery caches. Called automatically by sprint_record_phase_completion.
sprint_invalidate_caches() {
    rm -f /tmp/clavain-discovery-brief-*.cache 2>/dev/null || true
}
