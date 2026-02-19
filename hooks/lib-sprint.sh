#!/usr/bin/env bash
# Sprint-specific state library for Clavain.
# Sprint beads are type=epic beads with sprint=true state.
# All functions are fail-safe (return 0 on error, never block workflow)
# EXCEPT sprint_claim() which returns 1 on conflict (callers must handle).

# Guard against double-sourcing
[[ -n "${_SPRINT_LOADED:-}" ]] && return 0
_SPRINT_LOADED=1

# Source intercore state primitives (cache invalidation, sentinel checks)
source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true

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
    sprint_should_pause() { return 1; }
    sprint_advance() { return 1; }
    sprint_classify_complexity() { echo "medium"; }
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

# Update a single artifact path with intercore locking.
# CORRECTNESS: ALL updates to sprint_artifacts MUST go through this function.
# Direct `bd set-state` calls bypass the lock and cause lost-update races.
# Uses intercore_lock/intercore_unlock (ic lock acquire/release with fallback).
sprint_set_artifact() {
    local sprint_id="$1"
    local artifact_type="$2"
    local artifact_path="$3"

    [[ -z "$sprint_id" || -z "$artifact_type" || -z "$artifact_path" ]] && return 0

    # Acquire lock via intercore (fail-safe: give up silently on timeout)
    intercore_lock "sprint" "$sprint_id" "1s" || return 0

    # Read-modify-write under lock
    local current
    current=$(bd state "$sprint_id" sprint_artifacts 2>/dev/null) || current="{}"
    echo "$current" | jq empty 2>/dev/null || current="{}"

    local updated
    updated=$(echo "$current" | jq --arg type "$artifact_type" --arg path "$artifact_path" \
        '.[$type] = $path')

    bd set-state "$sprint_id" "sprint_artifacts=$updated" 2>/dev/null || true

    # Release lock
    intercore_unlock "sprint" "$sprint_id"
}

# Record phase completion timestamp in phase_history.
# Also invalidates discovery caches so session-start picks up the new phase.
sprint_record_phase_completion() {
    local sprint_id="$1"
    local phase="$2"

    [[ -z "$sprint_id" || -z "$phase" ]] && return 0

    # Acquire lock via intercore (same lock as sprint_set_artifact — both mutate sprint state)
    intercore_lock "sprint" "$sprint_id" "1s" || return 0

    local current
    current=$(bd state "$sprint_id" phase_history 2>/dev/null) || current="{}"
    echo "$current" | jq empty 2>/dev/null || current="{}"

    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local key="${phase}_at"
    local updated
    updated=$(echo "$current" | jq --arg key "$key" --arg ts "$ts" '.[$key] = $ts')

    bd set-state "$sprint_id" "phase_history=$updated" 2>/dev/null || true

    intercore_unlock "sprint" "$sprint_id"

    # Invalidate discovery caches so session-start picks up the new phase
    sprint_invalidate_caches
}

# ─── Session Claim ─────────────────────────────────────────────────

# Claim a sprint for this session. Prevents concurrent resume.
# Returns 0 if claimed, 1 if another session holds it.
# NOT fail-safe — returns 1 on conflict so callers can handle gracefully.
# CORRECTNESS: This uses intercore lock + write-then-verify to serialize claims.
# Two sessions can pass the TTL check simultaneously and race on the write.
# The lock + verify detects the loser, but callers MUST handle claim failure.
sprint_claim() {
    local sprint_id="$1"
    local session_id="$2"

    [[ -z "$sprint_id" || -z "$session_id" ]] && return 0

    # Acquire claim lock to serialize concurrent claim attempts (NOT fail-safe — returns 1 on conflict)
    if ! intercore_lock "sprint-claim" "$sprint_id" "500ms"; then
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
        if [[ -n "$claim_ts" && "$claim_ts" != "null" ]]; then
            local claim_epoch now_epoch age_minutes
            claim_epoch=$(date -d "$claim_ts" +%s 2>/dev/null) || claim_epoch=0
            if [[ $claim_epoch -gt 0 ]]; then
                now_epoch=$(date +%s)
                age_minutes=$(( (now_epoch - claim_epoch) / 60 ))
                if [[ $age_minutes -lt 60 ]]; then
                    echo "Sprint $sprint_id is active in session ${current_claim:0:8} (${age_minutes}m ago)" >&2
                    intercore_unlock "sprint-claim" "$sprint_id"
                    return 1
                fi
            fi
            # Expired or unparseable — take over
        else
            # No timestamp or null — might be stale. Allow takeover.
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
    intercore_unlock "sprint-claim" "$sprint_id"

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

# ─── Auto-Advance (Phase 2) ──────────────────────────────────────

# Strict phase transition table. Returns the NEXT phase given the CURRENT phase.
# Every phase has exactly one successor. No skip paths.
# CORRECTNESS: This is the single source of truth for phase sequencing.
# sprint_next_step() derives from this table — do NOT maintain phase order elsewhere.
_sprint_transition_table() {
    local current="$1"
    case "$current" in
        brainstorm)          echo "brainstorm-reviewed" ;;
        brainstorm-reviewed) echo "strategized" ;;
        strategized)         echo "planned" ;;
        planned)             echo "plan-reviewed" ;;
        plan-reviewed)       echo "executing" ;;
        executing)           echo "shipping" ;;
        shipping)            echo "done" ;;
        done)                echo "done" ;;
        *)                   echo "" ;;
    esac
}

# Determine the next command for a sprint based on its current phase.
# Output: command name (e.g., "brainstorm", "write-plan", "work")
# CORRECTNESS: Derives from _sprint_transition_table so the phase
# sequence is defined in one place. If phases change, update only the table.
sprint_next_step() {
    local phase="$1"
    local next_phase
    next_phase=$(_sprint_transition_table "$phase")

    # Map next-phase to the command that PRODUCES that phase.
    # brainstorm-reviewed is produced by review-doc (optional), but the
    # primary command is strategy (which also produces strategized).
    # So both brainstorm-reviewed and strategized map to strategy.
    case "$next_phase" in
        brainstorm-reviewed|strategized) echo "strategy" ;;
        planned)             echo "write-plan" ;;
        plan-reviewed)       echo "flux-drive" ;;
        executing)           echo "work" ;;
        shipping)            echo "ship" ;;
        done)                echo "done" ;;
        *)                   echo "brainstorm" ;;  # Handles "" and unknown
    esac
}

# Check if sprint should pause before advancing to target_phase.
# RETURN CONVENTION (intentionally inverted for ergonomic reason-reporting):
#   Returns 0 WITH STRUCTURED PAUSE REASON ON STDOUT if pause trigger found.
#   Returns 1 (no output) if should continue.
# Reason format: type|phase|detail
# Usage: pause_reason=$(sprint_should_pause ...) && { handle pause }
# Pause triggers: manual override (auto_advance=false), gate failure.
sprint_should_pause() {
    local sprint_id="$1"
    local target_phase="$2"

    [[ -z "$sprint_id" || -z "$target_phase" ]] && return 1

    # Manual override: auto_advance=false pauses at every transition
    local auto_advance
    auto_advance=$(bd state "$sprint_id" auto_advance 2>/dev/null) || auto_advance="true"
    if [[ "$auto_advance" == "false" ]]; then
        echo "manual_pause|$target_phase|auto_advance=false"
        return 0
    fi

    # Gate failure check: if enforce_gate would block, pause
    if ! enforce_gate "$sprint_id" "$target_phase" "" 2>/dev/null; then
        echo "gate_blocked|$target_phase|Gate prerequisites not met"
        return 0
    fi

    # No pause trigger — continue
    return 1
}

# Advance sprint to the next phase. Uses strict transition table.
# If should_pause triggers, returns 1 with structured pause reason on stdout.
# Otherwise advances and returns 0. Status messages go to stderr.
# CORRECTNESS: ALL phase transitions MUST go through this function.
# Direct `bd set-state sprint_id phase=X` calls bypass the lock and can cause
# inconsistent state (phase field doesn't match phase_history timestamps).
# Uses intercore lock to serialize concurrent advance attempts.
# Also verifies current phase hasn't changed (guards against stale-phase races).
sprint_advance() {
    local sprint_id="$1"
    local current_phase="$2"
    local artifact_path="${3:-}"

    [[ -z "$sprint_id" || -z "$current_phase" ]] && return 1

    local next_phase
    next_phase=$(_sprint_transition_table "$current_phase")
    [[ -z "$next_phase" || "$next_phase" == "$current_phase" ]] && return 1

    # Phase skipping: check if next_phase should be skipped for this complexity
    local complexity
    complexity=$(bd state "$sprint_id" complexity 2>/dev/null) || complexity="3"
    [[ -z "$complexity" || "$complexity" == "null" ]] && complexity="3"

    local force_full
    force_full=$(bd state "$sprint_id" force_full_chain 2>/dev/null) || force_full="false"

    if [[ "$force_full" != "true" ]] && sprint_should_skip "$next_phase" "$complexity"; then
        next_phase=$(sprint_next_required_phase "$current_phase" "$complexity")
        [[ -z "$next_phase" ]] && next_phase="done"
        echo "Phase: skipping to $next_phase (complexity $complexity)" >&2
    fi

    # Acquire lock for atomic read-check-write (NOT fail-safe — returns 1 on conflict)
    intercore_lock "sprint-advance" "$sprint_id" "1s" || return 1

    # Check pause triggers (under lock)
    local pause_reason
    pause_reason=$(sprint_should_pause "$sprint_id" "$next_phase" 2>/dev/null) && {
        intercore_unlock "sprint-advance" "$sprint_id"
        echo "$pause_reason"
        return 1
    }

    # Verify current phase hasn't changed (guard against concurrent advance)
    local actual_phase
    actual_phase=$(bd state "$sprint_id" phase 2>/dev/null) || actual_phase=""
    if [[ -n "$actual_phase" && "$actual_phase" != "$current_phase" ]]; then
        intercore_unlock "sprint-advance" "$sprint_id"
        echo "stale_phase|$current_phase|Phase already advanced to $actual_phase"
        return 1
    fi

    # Advance: set phase on bead, record completion, invalidate caches
    # NOTE: sprint_record_phase_completion acquires "sprint" lock inside this "sprint-advance" lock.
    # Lock ordering: sprint-advance > sprint. Do not reverse.
    bd set-state "$sprint_id" "phase=$next_phase" 2>/dev/null || true
    sprint_record_phase_completion "$sprint_id" "$next_phase"

    intercore_unlock "sprint-advance" "$sprint_id"

    # Log transition (stderr — stdout reserved for data/error reasons)
    echo "Phase: $current_phase → $next_phase (auto-advancing)" >&2
    return 0
}

# ─── Tiered Brainstorming ────────────────────────────────────────

# Classify feature complexity from description text.
# Output: integer 1-5 (or legacy string if override is a string)
# Scale: 1=trivial, 2=simple, 3=moderate, 4=complex, 5=research
# Heuristics:
#   - Word count: <5 = 3 (too short to classify), <30 = 2, 30-100 = 3, >100 = 4
#   - Ambiguity signals: "or", "vs", "alternative", "tradeoff" → bump up
#   - Simplicity signals: "like", "similar", "existing", "just" → bump down
#   - Trivial keywords: "rename", "format", "typo", "bump", "fix typo" → floor at 1
#   - Research keywords: "explore", "investigate", "research", "brainstorm" → bump to 5
#   - File count: 0-1 → lower, 10+ → higher
#   - Override: if sprint has complexity state set, use that
sprint_classify_complexity() {
    local sprint_id="${1:-}"
    local description="${2:-}"
    local file_count="${3:-0}"

    # Check for manual override on sprint bead
    if [[ -n "$sprint_id" ]]; then
        local override
        override=$(bd state "$sprint_id" complexity 2>/dev/null) || override=""
        if [[ -n "$override" && "$override" != "null" ]]; then
            echo "$override"
            return 0
        fi
    fi

    [[ -z "$description" ]] && { echo "3"; return 0; }

    # Word count
    local word_count
    word_count=$(echo "$description" | wc -w | tr -d ' ')

    # Vacuous descriptions (<5 words) are too short to classify
    if [[ $word_count -lt 5 ]]; then
        echo "3"
        return 0
    fi

    # Trivial keywords — floor at 1
    local trivial_count
    trivial_count=$(echo "$description" | awk -v IGNORECASE=1 '
        BEGIN { count=0 }
        {
            for (i=1; i<=NF; i++) {
                word = $i
                gsub(/[^a-zA-Z-]/, "", word)
                if (word ~ /^(rename|format|typo|bump|reformat|formatting)$/) count++
            }
        }
        END { print count }
    ')

    if [[ $trivial_count -gt 0 && $word_count -lt 20 ]]; then
        echo "1"
        return 0
    fi

    # Research keywords — ceiling at 5
    local research_count
    research_count=$(echo "$description" | awk -v IGNORECASE=1 '
        BEGIN { count=0 }
        {
            for (i=1; i<=NF; i++) {
                word = $i
                gsub(/[^a-zA-Z-]/, "", word)
                if (word ~ /^(explore|investigate|research|brainstorm|evaluate|survey|analyze)$/) count++
            }
        }
        END { print count }
    ')

    if [[ $research_count -gt 1 ]]; then
        echo "5"
        return 0
    fi

    # Ambiguity signals (awk for POSIX portability — no GNU grep \b needed)
    local ambiguity_count
    ambiguity_count=$(echo "$description" | awk -v IGNORECASE=1 '
        BEGIN { count=0 }
        {
            for (i=1; i<=NF; i++) {
                word = $i
                gsub(/[^a-zA-Z-]/, "", word)
                if (word ~ /^(or|vs|versus|alternative|tradeoff|trade-off|either|approach|option)$/) count++
            }
        }
        END { print count }
    ')

    # Simplicity signals
    local simplicity_count
    simplicity_count=$(echo "$description" | awk -v IGNORECASE=1 '
        BEGIN { count=0 }
        {
            for (i=1; i<=NF; i++) {
                word = $i
                gsub(/[^a-zA-Z-]/, "", word)
                if (word ~ /^(like|similar|existing|just|simple|straightforward)$/) count++
            }
        }
        END { print count }
    ')

    # Score: start with word-count tier, adjust with signals
    local score=0
    if [[ $word_count -lt 30 ]]; then
        score=2  # simple
    elif [[ $word_count -lt 100 ]]; then
        score=3  # moderate
    else
        score=4  # complex
    fi

    # Adjust: >2 signals indicates a real pattern, not noise from common words
    if [[ $ambiguity_count -gt 2 ]]; then
        score=$((score + 1))
    fi
    if [[ $simplicity_count -gt 2 ]]; then
        score=$((score - 1))
    fi

    # File count adjustment
    if [[ $file_count -gt 0 ]]; then
        if [[ $file_count -le 1 ]]; then
            score=$((score - 1))
        elif [[ $file_count -ge 10 ]]; then
            score=$((score + 1))
        fi
    fi

    # Clamp to 1-5
    [[ $score -lt 1 ]] && score=1
    [[ $score -gt 5 ]] && score=5
    echo "$score"
}

# Human-readable label for complexity score.
sprint_complexity_label() {
    local score="${1:-3}"
    case "$score" in
        1) echo "trivial" ;;
        2) echo "simple" ;;
        3) echo "moderate" ;;
        4) echo "complex" ;;
        5) echo "research" ;;
        # Legacy string values
        simple) echo "simple" ;;
        medium) echo "moderate" ;;
        complex) echo "complex" ;;
        *) echo "moderate" ;;
    esac
}

# ─── Phase Skipping ──────────────────────────────────────────────

# Return the list of required phases for a given complexity tier.
# Phases not in this list should be skipped by the sprint orchestrator.
# Output: space-separated phase names (whitelist)
sprint_phase_whitelist() {
    local complexity="${1:-3}"
    case "$complexity" in
        1) echo "planned executing shipping done" ;;
        2) echo "planned plan-reviewed executing shipping done" ;;
        3|4|5) echo "brainstorm brainstorm-reviewed strategized planned plan-reviewed executing shipping done" ;;
        *) echo "brainstorm brainstorm-reviewed strategized planned plan-reviewed executing shipping done" ;;
    esac
}

# Check if a phase should be skipped for the given complexity tier.
# Returns 0 if phase should be SKIPPED, 1 if it should be executed.
# (Convention: 0 = skip, 1 = execute — mnemonic: "0 = yes, skip")
sprint_should_skip() {
    local phase="${1:?phase required}"
    local complexity="${2:-3}"

    local whitelist
    whitelist=$(sprint_phase_whitelist "$complexity")

    # Check if phase is in whitelist
    case " $whitelist " in
        *" $phase "*) return 1 ;;  # In whitelist → don't skip
        *) return 0 ;;             # Not in whitelist → skip
    esac
}

# Find the next non-skipped phase from current_phase for the given complexity.
# Walks the transition table, skipping phases not in the whitelist.
# Output: the next phase that IS in the whitelist (or "done" if none remain)
sprint_next_required_phase() {
    local current_phase="${1:?current phase required}"
    local complexity="${2:-3}"

    local phase="$current_phase"
    local next_phase
    local steps=0

    # Walk forward through the transition table until we find a whitelisted phase
    while true; do
        next_phase=$(_sprint_transition_table "$phase")
        [[ -z "$next_phase" || "$next_phase" == "$phase" ]] && { echo "done"; return 0; }

        # Hard cap to prevent infinite loops (transition table has ~9 phases)
        steps=$((steps + 1))
        [[ $steps -gt 20 ]] && { echo "done"; return 0; }

        if ! sprint_should_skip "$next_phase" "$complexity"; then
            # Phase is in whitelist — this is the next required phase
            echo "$next_phase"
            return 0
        fi

        # Phase should be skipped — keep walking
        phase="$next_phase"
    done
}

# ─── Checkpointing ───────────────────────────────────────────────

CHECKPOINT_FILE="${CLAVAIN_CHECKPOINT_FILE:-.clavain/checkpoint.json}"

# Write or update a checkpoint after a sprint step completes.
# Uses filesystem lock to prevent concurrent write races (lost-update problem).
# Usage: checkpoint_write <bead_id> <phase> <step_name> [plan_path] [key_decision]
checkpoint_write() {
    local bead="${1:?bead_id required}"
    local phase="${2:?phase required}"
    local step="${3:?step_name required}"
    local plan_path="${4:-}"
    local key_decision="${5:-}"

    local git_sha
    git_sha=$(git rev-parse HEAD 2>/dev/null) || git_sha="unknown"
    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    mkdir -p "$(dirname "$CHECKPOINT_FILE")" 2>/dev/null || true

    # Acquire lock via intercore (fail-safe: give up silently on timeout)
    local _ckpt_scope
    _ckpt_scope=$(echo "$CHECKPOINT_FILE" | tr '/' '-')
    intercore_lock "checkpoint" "$_ckpt_scope" "1s" || return 0

    # Read existing or create new (under lock)
    local existing="{}"
    [[ -f "$CHECKPOINT_FILE" ]] && existing=$(cat "$CHECKPOINT_FILE" 2>/dev/null) || existing="{}"

    # Build updated checkpoint with jq
    local tmp="${CHECKPOINT_FILE}.tmp"
    echo "$existing" | jq \
        --arg bead "$bead" \
        --arg phase "$phase" \
        --arg step "$step" \
        --arg plan_path "$plan_path" \
        --arg git_sha "$git_sha" \
        --arg timestamp "$timestamp" \
        --arg key_decision "$key_decision" \
        '
        .bead = $bead |
        .phase = $phase |
        .plan_path = (if $plan_path != "" then $plan_path else (.plan_path // "") end) |
        .git_sha = $git_sha |
        .updated_at = $timestamp |
        .completed_steps = ((.completed_steps // []) + [$step] | unique) |
        .key_decisions = (if $key_decision != "" then ((.key_decisions // []) + [$key_decision] | unique | .[-5:]) else (.key_decisions // []) end)
        ' > "$tmp" 2>/dev/null && mv "$tmp" "$CHECKPOINT_FILE" 2>/dev/null || true

    intercore_unlock "checkpoint" "$_ckpt_scope"
}

# Read the current checkpoint.
# Output: JSON checkpoint or "{}" (empty object, never empty string — avoids jq null-slice errors)
checkpoint_read() {
    [[ -f "$CHECKPOINT_FILE" ]] && cat "$CHECKPOINT_FILE" 2>/dev/null || echo "{}"
}

# Validate checkpoint git SHA matches current HEAD.
# Returns: 0 if match (or no checkpoint), 1 if mismatch (prints warning)
checkpoint_validate() {
    local checkpoint
    checkpoint=$(checkpoint_read)
    [[ "$checkpoint" == "{}" ]] && return 0

    local saved_sha
    saved_sha=$(echo "$checkpoint" | jq -r '.git_sha // ""' 2>/dev/null) || saved_sha=""
    [[ -z "$saved_sha" || "$saved_sha" == "unknown" ]] && return 0

    local current_sha
    current_sha=$(git rev-parse HEAD 2>/dev/null) || current_sha="unknown"

    if [[ "$saved_sha" != "$current_sha" ]]; then
        echo "WARNING: Code changed since checkpoint (was ${saved_sha:0:8}, now ${current_sha:0:8})"
        return 1
    fi
    return 0
}

# Get completed steps from checkpoint.
# Output: JSON array of step names, or "[]"
checkpoint_completed_steps() {
    local checkpoint
    checkpoint=$(checkpoint_read)
    [[ "$checkpoint" == "{}" ]] && { echo "[]"; return 0; }
    echo "$checkpoint" | jq -r '(.completed_steps // [])' 2>/dev/null || echo "[]"
}

# Check if a specific step is completed in the checkpoint.
# Usage: checkpoint_step_done <step_name>
# Returns: 0 if done, 1 if not
checkpoint_step_done() {
    local step="${1:?step_name required}"
    local checkpoint
    checkpoint=$(checkpoint_read)
    [[ "$checkpoint" == "{}" ]] && return 1
    echo "$checkpoint" | jq -e --arg s "$step" '(.completed_steps // []) | index($s) != null' &>/dev/null
}

# Clear checkpoint (at sprint start or after shipping).
checkpoint_clear() {
    rm -f "$CHECKPOINT_FILE" "${CHECKPOINT_FILE}.tmp" 2>/dev/null || true
}

# ─── Invalidation ─────────────────────────────────────────────────

# Invalidate discovery caches. Called automatically by sprint_record_phase_completion.
sprint_invalidate_caches() {
    if type intercore_state_delete_all &>/dev/null; then
        intercore_state_delete_all "discovery_brief" "/tmp/clavain-discovery-brief-*.cache"
    else
        rm -f /tmp/clavain-discovery-brief-*.cache 2>/dev/null || true
    fi
}
