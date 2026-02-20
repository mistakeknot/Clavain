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

# Gate enforcement now uses ic gate check via enforce_gate() → intercore_gate_check.
# lib-gates.sh is deprecated — no longer sourced here.
export GATES_PROJECT_DIR="$SPRINT_LIB_PROJECT_DIR"

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

# Create a sprint bead + ic run. Returns bead ID to stdout.
# The ic run is linked to the bead via --scope-id.
# Caller MUST call sprint_finalize_init() after all setup.
# CORRECTNESS: If any step fails after bead creation, we cancel both bead and
# ic run to prevent zombie state. Callers receive "".
sprint_create() {
    local title="${1:-Sprint}"

    if ! command -v bd &>/dev/null; then
        echo ""
        return 0
    fi

    # Create tracking bead (issue tracking stays in beads)
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

    bd set-state "$sprint_id" "sprint=true" >/dev/null 2>&1 || {
        bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
        echo ""; return 0
    }
    bd update "$sprint_id" --status=in_progress >/dev/null 2>&1 || true

    # Create ic run linked to bead via scope-id
    local phases_json='["brainstorm","brainstorm-reviewed","strategized","planned","plan-reviewed","executing","shipping","reflect","done"]'
    local run_id
    run_id=$(intercore_run_create "$(pwd)" "$title" "$phases_json" "$sprint_id") || run_id=""

    if [[ -z "$run_id" ]]; then
        echo "sprint_create: ic run create failed, cancelling bead $sprint_id" >&2
        bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
        echo ""
        return 0
    fi

    # Store run_id on bead — CRITICAL: this is the join key that makes ic path work.
    # If this write fails, the ic run is unreachable through sprint API.
    bd set-state "$sprint_id" "ic_run_id=$run_id" >/dev/null 2>&1 || {
        echo "sprint_create: failed to write ic_run_id to bead, cancelling" >&2
        "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
        bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
        echo ""
        return 0
    }

    # Verify ic run was created and is at brainstorm phase
    local verify_phase
    verify_phase=$(intercore_run_phase "$run_id") || verify_phase=""
    if [[ "$verify_phase" != "brainstorm" ]]; then
        echo "sprint_create: ic run verification failed, cancelling bead $sprint_id" >&2
        "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
        bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
        echo ""
        return 0
    fi

    echo "$sprint_id"
}

# Mark sprint as fully initialized. Discovery skips uninitialized sprints.
# Sets sprint_initialized on bead (beads discovery compat) and stores
# the bead-run link in ic state for fast lookup.
sprint_finalize_init() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && return 0
    bd set-state "$sprint_id" "sprint_initialized=true" >/dev/null 2>&1 || true
    # NOTE: bead→run link is already stored via ic_run_id on bead + scope_id on run.
    # No redundant sprint_link ic state write needed (YAGNI — removed per arch review).
}

# ─── Sprint Discovery ──────────────────────────────────────────────

# Find active sprint runs. Output: JSON array [{id, title, phase, run_id}] or "[]"
# Primary path: ic run list --active (single DB query, no N+1)
# Fallback: beads-based scan (for environments without ic)
sprint_find_active() {
    # Try ic-based discovery first (fast path)
    if intercore_available; then
        local runs_json
        runs_json=$(intercore_run_list "--active") || runs_json="[]"

        # Filter to runs with a scope_id (scope_id = bead_id for sprints)
        local results="[]"
        local count
        count=$(echo "$runs_json" | jq 'length' 2>/dev/null) || count=0

        local i=0
        while [[ $i -lt $count && $i -lt 100 ]]; do
            local run_id scope_id phase goal
            run_id=$(echo "$runs_json" | jq -r ".[$i].id // empty")
            scope_id=$(echo "$runs_json" | jq -r ".[$i].scope_id // empty")
            phase=$(echo "$runs_json" | jq -r ".[$i].phase // empty")
            goal=$(echo "$runs_json" | jq -r ".[$i].goal // empty")

            # Only include runs with a scope_id (bead-linked sprints).
            # A run with scope_id was created by sprint_create → by construction it's a sprint.
            # No per-run bd state checks needed (eliminates N+1 reads — per arch review).
            if [[ -n "$scope_id" ]]; then
                # Use goal from ic run for title (avoids bd show call).
                # Fall back to bd show only if goal is empty.
                local title="$goal"
                if [[ -z "$title" ]]; then
                    title=$(bd show "$scope_id" 2>/dev/null | head -1 | sed 's/^[^·]*· //' | sed 's/ *\[.*$//' 2>/dev/null) || title="Untitled"
                fi
                results=$(echo "$results" | jq \
                    --arg id "$scope_id" \
                    --arg title "$title" \
                    --arg phase "$phase" \
                    --arg run_id "$run_id" \
                    '. + [{id: $id, title: $title, phase: $phase, run_id: $run_id}]')
            fi
            i=$((i + 1))
        done

        echo "$results"
        return 0
    fi

    # Fallback: beads-based scan (no ic available)
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
    echo "$ip_list" | jq 'if type != "array" then error("expected array") else . end' >/dev/null 2>&1 || {
        echo "[]"
        return 0
    }

    local count results="[]" i=0
    count=$(echo "$ip_list" | jq 'length' 2>/dev/null) || count=0
    while [[ $i -lt $count && $i -lt 100 ]]; do
        local bead_id
        bead_id=$(echo "$ip_list" | jq -r ".[$i].id // empty")
        [[ -z "$bead_id" ]] && { i=$((i + 1)); continue; }
        local is_sprint
        is_sprint=$(bd state "$bead_id" sprint 2>/dev/null) || is_sprint=""
        if [[ "$is_sprint" == "true" ]]; then
            local initialized
            initialized=$(bd state "$bead_id" sprint_initialized 2>/dev/null) || initialized=""
            if [[ "$initialized" == "true" ]]; then
                local title phase
                title=$(echo "$ip_list" | jq -r ".[$i].title // \"Untitled\"")
                phase=$(bd state "$bead_id" phase 2>/dev/null) || phase=""
                results=$(echo "$results" | jq \
                    --arg id "$bead_id" --arg title "$title" --arg phase "$phase" \
                    '. + [{id: $id, title: $title, phase: $phase}]')
            fi
        fi
        i=$((i + 1))
    done
    echo "$results"
}

# ─── Sprint State ──────────────────────────────────────────────────

# Read all sprint state fields at once. Output: JSON object.
# Primary: ic run status (single call). Fallback: beads.
sprint_read_state() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && { echo "{}"; return 0; }

    # Resolve run_id from bead
    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        local run_json
        run_json=$(intercore_run_status "$run_id") || run_json=""

        if [[ -n "$run_json" ]]; then
            # Map ic run fields to sprint state format
            local phase complexity auto_advance
            phase=$(echo "$run_json" | jq -r '.phase // ""')
            complexity=$(echo "$run_json" | jq -r '.complexity // 3')
            auto_advance=$(echo "$run_json" | jq -r '.auto_advance // true')

            # Artifacts from ic run artifact list
            local artifacts="{}"
            local artifact_json
            artifact_json=$("$INTERCORE_BIN" run artifact list "$run_id" --json 2>/dev/null) || artifact_json="[]"
            if [[ "$artifact_json" != "[]" ]]; then
                artifacts=$(echo "$artifact_json" | jq '[.[] | {(.type): .path}] | add // {}')
            fi

            # Phase history from ic run events (bounded, phase-events only)
            local history="{}"
            local events_json
            events_json=$("$INTERCORE_BIN" run events "$run_id" --json 2>/dev/null) || events_json=""
            if [[ -n "$events_json" ]]; then
                # NOTE: timestamp may be ISO-8601 string — use directly, not todate
                history=$(echo "$events_json" | jq -s '
                    [.[] | select(.source == "phase" and .type == "advance") |
                     {((.to_state // "") + "_at"): (.timestamp // "")}] | add // {}' 2>/dev/null) || history="{}"
            fi

            # Active session (agent tracking)
            local active_session=""
            local agents_json
            agents_json=$("$INTERCORE_BIN" run agent list "$run_id" --json 2>/dev/null) || agents_json="[]"
            if [[ "$agents_json" != "[]" ]]; then
                active_session=$(echo "$agents_json" | jq -r '[.[] | select(.status == "active")] | .[0].name // ""')
            fi

            jq -n -c \
                --arg id "$sprint_id" \
                --arg phase "$phase" \
                --argjson artifacts "$artifacts" \
                --argjson history "$history" \
                --arg complexity "$complexity" \
                --arg auto_advance "$auto_advance" \
                --arg active_session "$active_session" \
                '{id: $id, phase: $phase, artifacts: $artifacts, history: $history,
                  complexity: $complexity, auto_advance: $auto_advance, active_session: $active_session}'
            return 0
        fi
    fi

    # Fallback: beads-based read
    local phase sprint_artifacts phase_history complexity auto_advance active_session
    phase=$(bd state "$sprint_id" phase 2>/dev/null) || phase=""
    sprint_artifacts=$(bd state "$sprint_id" sprint_artifacts 2>/dev/null) || sprint_artifacts="{}"
    phase_history=$(bd state "$sprint_id" phase_history 2>/dev/null) || phase_history="{}"
    complexity=$(bd state "$sprint_id" complexity 2>/dev/null) || complexity=""
    auto_advance=$(bd state "$sprint_id" auto_advance 2>/dev/null) || auto_advance="true"
    active_session=$(bd state "$sprint_id" active_session 2>/dev/null) || active_session=""
    echo "$sprint_artifacts" | jq empty 2>/dev/null || sprint_artifacts="{}"
    echo "$phase_history" | jq empty 2>/dev/null || phase_history="{}"
    jq -n -c \
        --arg id "$sprint_id" --arg phase "$phase" \
        --argjson artifacts "$sprint_artifacts" --argjson history "$phase_history" \
        --arg complexity "$complexity" --arg auto_advance "$auto_advance" \
        --arg active_session "$active_session" \
        '{id: $id, phase: $phase, artifacts: $artifacts, history: $history,
          complexity: $complexity, auto_advance: $auto_advance, active_session: $active_session}'
}

# Record an artifact for the current phase. Uses ic run artifact add (atomic).
sprint_set_artifact() {
    local sprint_id="$1"
    local artifact_type="$2"
    local artifact_path="$3"

    [[ -z "$sprint_id" || -z "$artifact_type" || -z "$artifact_path" ]] && return 0

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        local phase
        phase=$(intercore_run_phase "$run_id") || phase="unknown"
        intercore_run_artifact_add "$run_id" "$phase" "$artifact_path" "$artifact_type" >/dev/null 2>&1 || true
        return 0
    fi

    # Fallback: beads-based (legacy sprints)
    intercore_lock "sprint" "$sprint_id" "1s" || return 0
    local current
    current=$(bd state "$sprint_id" sprint_artifacts 2>/dev/null) || current="{}"
    echo "$current" | jq empty 2>/dev/null || current="{}"
    local updated
    updated=$(echo "$current" | jq --arg type "$artifact_type" --arg path "$artifact_path" '.[$type] = $path')
    bd set-state "$sprint_id" "sprint_artifacts=$updated" >/dev/null 2>&1 || true
    intercore_unlock "sprint" "$sprint_id"
}

# Record phase completion. With ic, this is a no-op (events are auto-recorded).
# Still invalidates discovery caches.
sprint_record_phase_completion() {
    local sprint_id="$1"
    local phase="$2"

    [[ -z "$sprint_id" || -z "$phase" ]] && return 0

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # Phase events are auto-recorded by ic run advance — no manual write needed
        sprint_invalidate_caches
        return 0
    fi

    # Fallback: beads-based
    intercore_lock "sprint" "$sprint_id" "1s" || return 0
    local current
    current=$(bd state "$sprint_id" phase_history 2>/dev/null) || current="{}"
    echo "$current" | jq empty 2>/dev/null || current="{}"
    local ts key updated
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    key="${phase}_at"
    updated=$(echo "$current" | jq --arg key "$key" --arg ts "$ts" '.[$key] = $ts')
    bd set-state "$sprint_id" "phase_history=$updated" >/dev/null 2>&1 || true
    intercore_unlock "sprint" "$sprint_id"
    sprint_invalidate_caches
}

# ─── Session Claim ─────────────────────────────────────────────────

# Claim a sprint for this session. Returns 0 if claimed, 1 if conflict.
# Primary: ic run agent registration. Fallback: beads-based claim.
# CORRECTNESS: Serialized via intercore_lock to prevent TOCTOU race
# (per correctness review Finding 1).
sprint_claim() {
    local sprint_id="$1"
    local session_id="$2"

    [[ -z "$sprint_id" || -z "$session_id" ]] && return 0

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # CRITICAL: Serialize the check-then-register sequence to prevent TOCTOU race.
        # Two sessions evaluating simultaneously could both see zero agents and both claim.
        intercore_lock "sprint-claim" "$sprint_id" "500ms" || return 1

        local agents_json
        agents_json=$(intercore_run_agent_list "$run_id") || agents_json="[]"
        local active_agents
        active_agents=$(echo "$agents_json" | jq '[.[] | select(.status == "active" and .agent_type == "session")]')
        local active_count
        active_count=$(echo "$active_agents" | jq 'length')

        if [[ "$active_count" -gt 0 ]]; then
            local existing_name
            existing_name=$(echo "$active_agents" | jq -r '.[0].name // "unknown"')
            if [[ "$existing_name" == "$session_id" ]]; then
                intercore_unlock "sprint-claim" "$sprint_id"
                return 0  # Already claimed by us
            fi
            # Check staleness (created >60 min ago)
            # NOTE: created_at may be ISO-8601 string — convert via date -d
            local created_at_str now_epoch created_at age_minutes
            created_at_str=$(echo "$active_agents" | jq -r '.[0].created_at // "1970-01-01T00:00:00Z"')
            created_at=$(date -d "$created_at_str" +%s 2>/dev/null) || created_at=0
            now_epoch=$(date +%s)
            age_minutes=$(( (now_epoch - created_at) / 60 ))
            if [[ $age_minutes -lt 60 ]]; then
                echo "Sprint $sprint_id is active in session ${existing_name:0:8} (${age_minutes}m ago)" >&2
                intercore_unlock "sprint-claim" "$sprint_id"
                return 1
            fi
            # Stale — mark old agent as failed, then claim
            local old_agent_id
            old_agent_id=$(echo "$active_agents" | jq -r '.[0].id')
            intercore_run_agent_update "$old_agent_id" "failed" >/dev/null 2>&1 || true
        fi

        # Register this session as an agent — failure must not silently succeed
        if ! intercore_run_agent_add "$run_id" "session" "$session_id" >/dev/null 2>&1; then
            echo "sprint_claim: failed to register session agent for $sprint_id" >&2
            intercore_unlock "sprint-claim" "$sprint_id"
            return 1
        fi
        intercore_unlock "sprint-claim" "$sprint_id"
        return 0
    fi

    # Fallback: beads-based claim (legacy)
    if ! intercore_lock "sprint-claim" "$sprint_id" "500ms"; then
        sleep 0.3
        local current_claim
        current_claim=$(bd state "$sprint_id" active_session 2>/dev/null) || current_claim=""
        if [[ "$current_claim" == "$session_id" ]]; then return 0; fi
        echo "Sprint $sprint_id is being claimed by another session" >&2
        return 1
    fi
    local current_claim claim_ts
    current_claim=$(bd state "$sprint_id" active_session 2>/dev/null) || current_claim=""
    claim_ts=$(bd state "$sprint_id" claim_timestamp 2>/dev/null) || claim_ts=""
    if [[ -n "$current_claim" && "$current_claim" != "$session_id" ]]; then
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
        fi
    fi
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    bd set-state "$sprint_id" "active_session=$session_id" >/dev/null 2>&1 || true
    bd set-state "$sprint_id" "claim_timestamp=$ts" >/dev/null 2>&1 || true
    local verify
    verify=$(bd state "$sprint_id" active_session 2>/dev/null) || verify=""
    intercore_unlock "sprint-claim" "$sprint_id"
    if [[ "$verify" != "$session_id" ]]; then
        echo "Failed to claim sprint $sprint_id (write verification failed)" >&2
        return 1
    fi
    return 0
}

# Release sprint claim.
sprint_release() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && return 0

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # Mark all active session agents as completed.
        # NOTE: release failure is recoverable via the 60-minute staleness TTL in sprint_claim.
        local agents_json agent_ids
        agents_json=$(intercore_run_agent_list "$run_id") || agents_json="[]"
        agent_ids=$(echo "$agents_json" | jq -r '.[] | select(.status == "active" and .agent_type == "session") | .id' 2>/dev/null) || agent_ids=""
        while read -r agent_id; do
            [[ -z "$agent_id" ]] && continue
            intercore_run_agent_update "$agent_id" "completed" >/dev/null 2>&1 || true
        done <<< "$agent_ids"
        return 0
    fi

    # Fallback: beads-based
    bd set-state "$sprint_id" "active_session=" >/dev/null 2>&1 || true
    bd set-state "$sprint_id" "claim_timestamp=" >/dev/null 2>&1 || true
}

# ─── Agent Tracking ──────────────────────────────────────────────

# Track an agent dispatch against the current sprint run.
# Called by skills when spawning subagents (work, quality-gates).
# Args: $1=sprint_id, $2=agent_name, $3=agent_type (default "claude"), $4=dispatch_id (optional)
# Returns: agent_id on stdout, or empty on failure
sprint_track_agent() {
    local sprint_id="$1"
    local agent_name="$2"
    local agent_type="${3:-claude}"
    local dispatch_id="${4:-}"

    [[ -z "$sprint_id" || -z "$agent_name" ]] && return 0

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        intercore_run_agent_add "$run_id" "$agent_type" "$agent_name" "$dispatch_id"
        return $?
    fi

    return 0
}

# Mark an agent as completed.
# Args: $1=agent_id, $2=status (default "completed")
sprint_complete_agent() {
    local agent_id="$1"
    local status="${2:-completed}"

    [[ -z "$agent_id" ]] && return 0

    if intercore_available; then
        intercore_run_agent_update "$agent_id" "$status" >/dev/null 2>&1 || true
    fi
}

# ─── Gate Wrapper ──────────────────────────────────────────────────

# Gate enforcement. Returns 0 if gate passes, 1 if blocked.
# Primary: ic gate check on run. Fallback: interphase shim.
enforce_gate() {
    local bead_id="$1"
    local target_phase="$2"
    local artifact_path="${3:-}"

    # Resolve run_id
    local run_id
    run_id=$(bd state "$bead_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # ic gate check evaluates the run's current next transition internally.
        # target_phase is used only by the beads fallback; ic determines the applicable
        # phase transition from the run's state machine.
        intercore_gate_check "$run_id"
        return $?
    fi

    # Fallback: interphase shim
    if type check_phase_gate &>/dev/null; then
        check_phase_gate "$bead_id" "$target_phase" "$artifact_path"
    else
        return 0
    fi
}

# ─── Auto-Advance (Phase 2) ──────────────────────────────────────

# DEPRECATED: Fallback transition table for beads-only mode (no intercore).
# Primary path: ic run advance (kernel walks the phase chain stored on the run).
# This table is only used by sprint_advance()'s beads fallback and sprint_next_required_phase().
# When intercore is available, sprint_advance() delegates to intercore_run_advance() and
# this table is never consulted.
# Strict phase transition table. Returns the NEXT phase given the CURRENT phase.
# Every phase has exactly one successor. No skip paths.
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
        shipping)            echo "reflect" ;;
        reflect)             echo "done" ;;
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
        reflect)             echo "reflect" ;;
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

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # ic run advance handles pause internally (auto_advance field on run)
        # But we still check here for pre-flight gate validation
        if ! intercore_gate_check "$run_id" 2>/dev/null; then
            echo "gate_blocked|$target_phase|Gate prerequisites not met"
            return 0
        fi
        return 1
    fi

    # Fallback: beads-based
    local auto_advance
    auto_advance=$(bd state "$sprint_id" auto_advance 2>/dev/null) || auto_advance="true"
    if [[ "$auto_advance" == "false" ]]; then
        echo "manual_pause|$target_phase|auto_advance=false"
        return 0
    fi
    if ! enforce_gate "$sprint_id" "$target_phase" "" 2>/dev/null; then
        echo "gate_blocked|$target_phase|Gate prerequisites not met"
        return 0
    fi
    return 1
}

# Advance sprint to the next phase.
# Returns 0 on success, 1 on pause/error (structured reason on stdout).
sprint_advance() {
    local sprint_id="$1"
    local current_phase="$2"
    local artifact_path="${3:-}"

    [[ -z "$sprint_id" || -z "$current_phase" ]] && return 1

    local run_id
    run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # ic run advance handles: phase chain, gate checks, optimistic concurrency,
        # auto_advance, phase skipping (via force_full + complexity on run)
        local result
        result=$(intercore_run_advance "$run_id") || {
            local rc=$?
            # Parse JSON error for structured pause reason
            local event_type from_phase to_phase
            event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
            from_phase=$(echo "$result" | jq -r '.from_phase // ""' 2>/dev/null) || from_phase=""
            to_phase=$(echo "$result" | jq -r '.to_phase // ""' 2>/dev/null) || to_phase=""

            case "$event_type" in
                block)
                    echo "gate_blocked|$to_phase|Gate prerequisites not met"
                    ;;
                pause)
                    echo "manual_pause|$to_phase|auto_advance=false"
                    ;;
                *)
                    # JSON parse failed or unknown event type — log raw result for debugging
                    if [[ -z "$event_type" && -z "$from_phase" ]]; then
                        echo "sprint_advance: ic run advance returned unexpected result: ${result:-<empty>}" >&2
                    fi
                    local actual_phase
                    actual_phase=$(intercore_run_phase "$run_id") || actual_phase=""
                    if [[ -n "$actual_phase" && "$actual_phase" != "$current_phase" ]]; then
                        echo "stale_phase|$current_phase|Phase already advanced to $actual_phase"
                    fi
                    ;;
            esac
            return 1
        }

        # Success — parse result
        local from_phase to_phase
        from_phase=$(echo "$result" | jq -r '.from_phase // ""' 2>/dev/null) || from_phase="$current_phase"
        to_phase=$(echo "$result" | jq -r '.to_phase // ""' 2>/dev/null) || to_phase=""

        sprint_invalidate_caches
        echo "Phase: $from_phase → $to_phase (auto-advancing)" >&2
        return 0
    fi

    # Fallback: beads-based advance (original logic)
    local next_phase
    next_phase=$(_sprint_transition_table "$current_phase")
    [[ -z "$next_phase" || "$next_phase" == "$current_phase" ]] && return 1

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

    intercore_lock "sprint-advance" "$sprint_id" "1s" || return 1
    local pause_reason
    pause_reason=$(sprint_should_pause "$sprint_id" "$next_phase" 2>/dev/null) && {
        intercore_unlock "sprint-advance" "$sprint_id"
        echo "$pause_reason"
        return 1
    }
    local actual_phase
    actual_phase=$(bd state "$sprint_id" phase 2>/dev/null) || actual_phase=""
    if [[ -n "$actual_phase" && "$actual_phase" != "$current_phase" ]]; then
        intercore_unlock "sprint-advance" "$sprint_id"
        echo "stale_phase|$current_phase|Phase already advanced to $actual_phase"
        return 1
    fi
    bd set-state "$sprint_id" "phase=$next_phase" >/dev/null 2>&1 || true
    sprint_record_phase_completion "$sprint_id" "$next_phase"
    intercore_unlock "sprint-advance" "$sprint_id"
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

    # Check for manual override — try ic run first, then beads
    if [[ -n "$sprint_id" ]]; then
        local override=""
        local run_id
        run_id=$(bd state "$sprint_id" ic_run_id 2>/dev/null) || run_id=""
        if [[ -n "$run_id" ]] && intercore_available; then
            override=$(intercore_run_status "$run_id" | jq -r '.complexity // empty' 2>/dev/null) || override=""
        fi
        if [[ -z "$override" || "$override" == "null" ]]; then
            override=$(bd state "$sprint_id" complexity 2>/dev/null) || override=""
        fi
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

# DEPRECATED: Beads-only fallback. Primary path uses ic run skip + short --phases chains.
# Return the list of required phases for a given complexity tier.
# Phases not in this list should be skipped by the sprint orchestrator.
# Output: space-separated phase names (whitelist)
sprint_phase_whitelist() {
    local complexity="${1:-3}"
    case "$complexity" in
        1) echo "planned executing shipping reflect done" ;;
        2) echo "planned plan-reviewed executing shipping reflect done" ;;
        3|4|5) echo "brainstorm brainstorm-reviewed strategized planned plan-reviewed executing shipping reflect done" ;;
        *) echo "brainstorm brainstorm-reviewed strategized planned plan-reviewed executing shipping reflect done" ;;
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
# Primary: ic state set. Fallback: file-based.
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

    local run_id
    run_id=$(bd state "$bead" ic_run_id 2>/dev/null) || run_id=""

    if [[ -n "$run_id" ]] && intercore_available; then
        # Read existing checkpoint from ic state
        local existing
        existing=$(intercore_state_get "checkpoint" "$run_id") || existing="{}"
        [[ -z "$existing" ]] && existing="{}"

        local checkpoint_json
        checkpoint_json=$(echo "$existing" | jq \
            --arg bead "$bead" --arg phase "$phase" --arg step "$step" \
            --arg plan_path "$plan_path" --arg git_sha "$git_sha" \
            --arg timestamp "$timestamp" --arg key_decision "$key_decision" \
            '
            .bead = $bead | .phase = $phase |
            .plan_path = (if $plan_path != "" then $plan_path else (.plan_path // "") end) |
            .git_sha = $git_sha | .updated_at = $timestamp |
            .completed_steps = ((.completed_steps // []) + [$step] | unique) |
            .key_decisions = (if $key_decision != "" then ((.key_decisions // []) + [$key_decision] | unique | .[-5:]) else (.key_decisions // []) end)
            ')

        intercore_state_set "checkpoint" "$run_id" "$checkpoint_json" 2>/dev/null || true
        return 0
    fi

    # Fallback: file-based checkpoint
    mkdir -p "$(dirname "$CHECKPOINT_FILE")" 2>/dev/null || true
    local _ckpt_scope
    _ckpt_scope=$(echo "$CHECKPOINT_FILE" | tr '/' '-')
    intercore_lock "checkpoint" "$_ckpt_scope" "1s" || return 0
    local existing="{}"
    [[ -f "$CHECKPOINT_FILE" ]] && existing=$(cat "$CHECKPOINT_FILE" 2>/dev/null) || existing="{}"
    local tmp="${CHECKPOINT_FILE}.tmp"
    echo "$existing" | jq \
        --arg bead "$bead" --arg phase "$phase" --arg step "$step" \
        --arg plan_path "$plan_path" --arg git_sha "$git_sha" \
        --arg timestamp "$timestamp" --arg key_decision "$key_decision" \
        '
        .bead = $bead | .phase = $phase |
        .plan_path = (if $plan_path != "" then $plan_path else (.plan_path // "") end) |
        .git_sha = $git_sha | .updated_at = $timestamp |
        .completed_steps = ((.completed_steps // []) + [$step] | unique) |
        .key_decisions = (if $key_decision != "" then ((.key_decisions // []) + [$key_decision] | unique | .[-5:]) else (.key_decisions // []) end)
        ' > "$tmp" 2>/dev/null && mv "$tmp" "$CHECKPOINT_FILE" 2>/dev/null || true
    intercore_unlock "checkpoint" "$_ckpt_scope"
}

# Read the current checkpoint. Output: JSON or "{}"
# Args: $1=bead_id (optional — used to resolve the correct run_id)
# When bead_id is provided, resolves run via bead's ic_run_id (sprint-scoped).
# Without bead_id, falls back to ic run current (project-scoped, may be wrong
# with multiple active runs — per arch/correctness review).
checkpoint_read() {
    local bead_id="${1:-}"
    if intercore_available; then
        local run_id=""
        # Prefer bead-scoped lookup when available
        if [[ -n "$bead_id" ]]; then
            run_id=$(bd state "$bead_id" ic_run_id 2>/dev/null) || run_id=""
        fi
        # Fall back to project-scoped lookup
        if [[ -z "$run_id" ]]; then
            run_id=$(intercore_run_current "$(pwd)") || run_id=""
        fi
        if [[ -n "$run_id" ]]; then
            local ckpt
            ckpt=$(intercore_state_get "checkpoint" "$run_id") || ckpt=""
            if [[ -n "$ckpt" ]]; then
                echo "$ckpt"
                return 0
            fi
        fi
    fi
    # Fallback: file-based
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
