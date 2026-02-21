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

# ─── ic availability guard ──────────────────────────────────────
# Sprint operations require intercore. Non-sprint beads workflows are unaffected.
declare -A _SPRINT_RUN_ID_CACHE  # bead_id → run_id

sprint_require_ic() {
    if ! intercore_available; then
        echo "Sprint requires intercore (ic). Install ic or use beads directly for task tracking." >&2
        return 1
    fi
    return 0
}

# Resolve bead_id → ic run_id. Caches result in _SPRINT_RUN_ID_CACHE.
# Call once at sprint_claim or sprint_create. All subsequent functions use the cache.
# Args: $1=bead_id
# Output: run_id on stdout, or "" on failure
_sprint_resolve_run_id() {
    local bead_id="$1"
    [[ -z "$bead_id" ]] && { echo ""; return 1; }

    # Cache hit
    if [[ -n "${_SPRINT_RUN_ID_CACHE[$bead_id]:-}" ]]; then
        echo "${_SPRINT_RUN_ID_CACHE[$bead_id]}"
        return 0
    fi

    # Resolve from bead
    local run_id
    run_id=$(bd state "$bead_id" ic_run_id 2>/dev/null) || run_id=""
    if [[ -z "$run_id" || "$run_id" == "null" ]]; then
        echo ""
        return 1
    fi

    _SPRINT_RUN_ID_CACHE["$bead_id"]="$run_id"
    echo "$run_id"
}

# ─── jq dependency check ─────────────────────────────────────────
# jq is required for all JSON operations. Stub out functions if missing.
if ! command -v jq &>/dev/null; then
    sprint_require_ic() { return 1; }
    sprint_create() { echo ""; return 1; }
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
    sprint_classify_complexity() { echo "3"; }
    sprint_budget_remaining() { echo "0"; }
    checkpoint_write() { return 0; }
    checkpoint_read() { echo "{}"; }
    return 0
fi

# ─── Sprint CRUD ────────────────────────────────────────────────────

# Default token budgets by complexity tier (billing tokens: input + output).
# Override per-sprint with: bd set-state <sprint> token_budget=N
_sprint_default_budget() {
    local complexity="${1:-3}"
    case "$complexity" in
        1) echo "50000" ;;
        2) echo "100000" ;;
        3) echo "250000" ;;
        4) echo "500000" ;;
        5|*) echo "1000000" ;;
    esac
}

# Create a sprint: ic run (required) + bead (tracking, fatal if bd available).
# Returns bead ID to stdout (for CLAVAIN_BEAD_ID).
# REQUIRES: intercore available. Bead creation failure is fatal (when bd installed).
sprint_create() {
    local title="${1:-Sprint}"

    sprint_require_ic || { echo ""; return 1; }

    # Create bead for tracking (fatal when bd is available)
    local sprint_id=""
    if command -v bd &>/dev/null; then
        sprint_id=$(bd create --title="$title" --type=epic --priority=2 2>/dev/null \
            | awk 'match($0, /[A-Za-z]+-[a-z0-9]+/) { print substr($0, RSTART, RLENGTH); exit }') || sprint_id=""
        if [[ -z "$sprint_id" ]]; then
            echo "sprint_create: bead creation failed" >&2
            echo ""
            return 1
        fi
        bd set-state "$sprint_id" "sprint=true" >/dev/null 2>&1 || true
        bd update "$sprint_id" --status=in_progress >/dev/null 2>&1 || true
    fi

    # Use bead ID as scope_id if available, otherwise generate a placeholder
    local scope_id="${sprint_id:-sprint-$(date +%s)}"

    # Create ic run (required — this is the state backend)
    local phases_json='["brainstorm","brainstorm-reviewed","strategized","planned","plan-reviewed","executing","shipping","reflect","done"]'
    local complexity="${2:-3}"
    local token_budget
    token_budget=$(_sprint_default_budget "$complexity")
    local run_id
    run_id=$(intercore_run_create "$(pwd)" "$title" "$phases_json" "$scope_id" "$complexity" "$token_budget") || run_id=""

    if [[ -z "$run_id" ]]; then
        echo "sprint_create: ic run create failed" >&2
        [[ -n "$sprint_id" ]] && bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
        echo ""
        return 1
    fi

    # Verify ic run is at brainstorm phase
    local verify_phase
    verify_phase=$(intercore_run_phase "$run_id") || verify_phase=""
    if [[ "$verify_phase" != "brainstorm" ]]; then
        echo "sprint_create: ic run verification failed (phase=$verify_phase)" >&2
        "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
        [[ -n "$sprint_id" ]] && bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
        echo ""
        return 1
    fi

    # Store run_id on bead AFTER verification (Amendment D)
    if [[ -n "$sprint_id" ]]; then
        bd set-state "$sprint_id" "ic_run_id=$run_id" >/dev/null 2>&1 || {
            echo "sprint_create: failed to write ic_run_id to bead" >&2
            "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
            bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
            echo ""
            return 1
        }
        bd set-state "$sprint_id" "token_budget=$token_budget" >/dev/null 2>&1 || true
    fi

    # Cache the run ID for this session
    _SPRINT_RUN_ID_CACHE["$scope_id"]="$run_id"

    echo "$sprint_id"
}

# ─── Sprint Discovery ──────────────────────────────────────────────

# Find active sprint runs. Output: JSON array [{id, title, phase, run_id}] or "[]"
# REQUIRES: intercore available.
sprint_find_active() {
    sprint_require_ic || { echo "[]"; return 0; }

    local runs_json
    runs_json=$(intercore_run_list "--active") || { echo "[]"; return 0; }

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

        if [[ -n "$scope_id" ]]; then
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
}

# ─── Sprint State ──────────────────────────────────────────────────

# Read all sprint state fields at once. Output: JSON object.
# REQUIRES: intercore available + run ID cached.
sprint_read_state() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && { echo "{}"; return 0; }

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || { echo "{}"; return 0; }

    local run_json
    run_json=$(intercore_run_status "$run_id") || { echo "{}"; return 0; }

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

    # Phase history from ic run events (Amendment E: correct field names)
    local history="{}"
    local events_json
    events_json=$("$INTERCORE_BIN" run events "$run_id" --json 2>/dev/null) || events_json=""
    if [[ -n "$events_json" ]]; then
        history=$(echo "$events_json" | jq '
            [.[] | select(.event_type == "advance") |
             {((.to_phase // "") + "_at"): (.created_at // "")}] | add // {}' 2>/dev/null) || history="{}"
    fi

    # Active session (agent tracking)
    local active_session=""
    local agents_json
    agents_json=$(intercore_run_agent_list "$run_id") || agents_json="[]"
    if [[ "$agents_json" != "[]" ]]; then
        active_session=$(echo "$agents_json" | jq -r '[.[] | select(.status == "active")] | .[0].name // ""')
    fi

    # Token budget and spend (Amendment E: correct field names)
    local token_budget tokens_spent
    token_budget=$(echo "$run_json" | jq -r '.token_budget // 0')
    local token_agg
    token_agg=$("$INTERCORE_BIN" run tokens "$run_id" --json 2>/dev/null) || token_agg=""
    if [[ -n "$token_agg" ]]; then
        tokens_spent=$(echo "$token_agg" | jq -r '(.input_tokens // 0) + (.output_tokens // 0)')
    else
        tokens_spent="0"
    fi

    jq -n -c \
        --arg id "$sprint_id" \
        --arg phase "$phase" \
        --argjson artifacts "$artifacts" \
        --argjson history "$history" \
        --arg complexity "$complexity" \
        --arg auto_advance "$auto_advance" \
        --arg active_session "$active_session" \
        --arg token_budget "$token_budget" \
        --arg tokens_spent "$tokens_spent" \
        '{id: $id, phase: $phase, artifacts: $artifacts, history: $history,
          complexity: $complexity, auto_advance: $auto_advance, active_session: $active_session,
          token_budget: ($token_budget | tonumber), tokens_spent: ($tokens_spent | tonumber)}'
}

# Record an artifact for the current phase.
sprint_set_artifact() {
    local sprint_id="$1"
    local artifact_type="$2"
    local artifact_path="$3"
    [[ -z "$sprint_id" || -z "$artifact_type" || -z "$artifact_path" ]] && return 0

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || return 0

    local phase
    phase=$(intercore_run_phase "$run_id") || phase="unknown"
    intercore_run_artifact_add "$run_id" "$phase" "$artifact_path" "$artifact_type" >/dev/null 2>&1 || true
}

# Record phase completion. With ic, events are auto-recorded.
# Just invalidates discovery caches.
sprint_record_phase_completion() {
    local sprint_id="$1"
    local phase="$2"
    [[ -z "$sprint_id" || -z "$phase" ]] && return 0
    sprint_invalidate_caches
}

# ─── Token Budget ──────────────────────────────────────────────────

# Estimated billing tokens per phase (used when interstat actuals unavailable).
_sprint_phase_cost_estimate() {
    local phase="${1:-}"
    case "$phase" in
        brainstorm)          echo "30000" ;;
        brainstorm-reviewed) echo "15000" ;;
        strategized)         echo "25000" ;;
        planned)             echo "35000" ;;
        plan-reviewed)       echo "50000" ;;
        executing)           echo "150000" ;;
        shipping)            echo "100000" ;;
        reflect)             echo "10000" ;;
        done)                echo "5000" ;;
        *)                   echo "30000" ;;
    esac
}

# Write token usage for a completed phase to intercore state.
# Tries interstat for actual data first, falls back to estimates.
# Amendment G: uses ic state set (not dispatch create/update which don't exist).
sprint_record_phase_tokens() {
    local sprint_id="$1" phase="$2"
    [[ -z "$sprint_id" || -z "$phase" ]] && return 0

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || return 0

    # Try actual data from interstat (session-scoped billing tokens)
    local actual_tokens=""
    if command -v sqlite3 &>/dev/null; then
        local db_path="${HOME}/.claude/interstat/metrics.db"
        if [[ -f "$db_path" ]]; then
            actual_tokens=$(sqlite3 "$db_path" \
                "SELECT COALESCE(SUM(COALESCE(input_tokens,0) + COALESCE(output_tokens,0)), 0) FROM agent_runs WHERE session_id='${CLAUDE_SESSION_ID:-none}'" 2>/dev/null) || actual_tokens=""
        fi
    fi

    local in_tokens out_tokens
    if [[ -n "$actual_tokens" && "$actual_tokens" != "0" ]]; then
        in_tokens=$(( actual_tokens * 60 / 100 ))
        out_tokens=$(( actual_tokens - in_tokens ))
    else
        local estimate
        estimate=$(_sprint_phase_cost_estimate "$phase")
        in_tokens=$(( estimate * 60 / 100 ))
        out_tokens=$(( estimate - in_tokens ))
    fi

    # Record phase tokens via ic state (keyed by run_id + phase)
    local existing_tokens
    existing_tokens=$(intercore_state_get "phase_tokens" "$run_id" 2>/dev/null) || existing_tokens="{}"
    [[ -z "$existing_tokens" ]] && existing_tokens="{}"
    local updated
    updated=$(echo "$existing_tokens" | jq \
        --arg phase "$phase" \
        --argjson in_tok "$in_tokens" \
        --argjson out_tok "$out_tokens" \
        '.[$phase] = {input_tokens: $in_tok, output_tokens: $out_tok}' 2>/dev/null) || updated="$existing_tokens"
    intercore_state_set "phase_tokens" "$run_id" "$updated" 2>/dev/null || true
}

# Get remaining token budget for a sprint.
# Output: integer (0 if no budget set or beads-only without budget)
sprint_budget_remaining() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && { echo "0"; return 0; }

    local state
    state=$(sprint_read_state "$sprint_id") || { echo "0"; return 0; }

    local budget spent
    budget=$(echo "$state" | jq -r '.token_budget // 0' 2>/dev/null) || budget="0"
    spent=$(echo "$state" | jq -r '.tokens_spent // 0' 2>/dev/null) || spent="0"
    [[ "$budget" == "0" || "$budget" == "null" ]] && { echo "0"; return 0; }

    local remaining=$(( budget - spent ))
    [[ $remaining -lt 0 ]] && remaining=0
    echo "$remaining"
}

# ─── Session Claim ─────────────────────────────────────────────────

# Claim a sprint for this session. Returns 0 if claimed, 1 if conflict.
# REQUIRES: intercore available.
# CORRECTNESS: Serialized via intercore_lock to prevent TOCTOU race.
sprint_claim() {
    local sprint_id="$1"
    local session_id="$2"
    [[ -z "$sprint_id" || -z "$session_id" ]] && return 0

    sprint_require_ic || return 1

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || {
        echo "sprint_claim: no ic run found for $sprint_id" >&2
        return 1
    }

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
        local old_agent_id
        old_agent_id=$(echo "$active_agents" | jq -r '.[0].id')
        intercore_run_agent_update "$old_agent_id" "failed" >/dev/null 2>&1 || true
    fi

    if ! intercore_run_agent_add "$run_id" "session" "$session_id" >/dev/null 2>&1; then
        echo "sprint_claim: failed to register session agent for $sprint_id" >&2
        intercore_unlock "sprint-claim" "$sprint_id"
        return 1
    fi
    intercore_unlock "sprint-claim" "$sprint_id"
    return 0
}

# Release sprint claim.
sprint_release() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && return 0

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || return 0

    local agents_json agent_ids
    agents_json=$(intercore_run_agent_list "$run_id") || agents_json="[]"
    agent_ids=$(echo "$agents_json" | jq -r '.[] | select(.status == "active" and .agent_type == "session") | .id' 2>/dev/null) || agent_ids=""
    while read -r agent_id; do
        [[ -z "$agent_id" ]] && continue
        intercore_run_agent_update "$agent_id" "completed" >/dev/null 2>&1 || true
    done <<< "$agent_ids"
}

# ─── Agent Tracking ──────────────────────────────────────────────

# Track an agent dispatch against the current sprint run.
sprint_track_agent() {
    local sprint_id="$1"
    local agent_name="$2"
    local agent_type="${3:-claude}"
    local dispatch_id="${4:-}"
    [[ -z "$sprint_id" || -z "$agent_name" ]] && return 0

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || return 0
    intercore_run_agent_add "$run_id" "$agent_type" "$agent_name" "$dispatch_id"
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
enforce_gate() {
    local bead_id="$1"
    local target_phase="$2"
    local artifact_path="${3:-}"

    local run_id
    run_id=$(_sprint_resolve_run_id "$bead_id") || return 0
    intercore_gate_check "$run_id"
}

# ─── Auto-Advance (Phase 2) ──────────────────────────────────────

# Determine the next command for a sprint based on its current phase.
# Maps current phase → command that handles the next action.
# Phase chain lives in ic (passed at creation time). This just maps phases to commands.
sprint_next_step() {
    local phase="$1"
    case "$phase" in
        brainstorm)          echo "strategy" ;;
        brainstorm-reviewed) echo "strategy" ;;
        strategized)         echo "write-plan" ;;
        planned)             echo "flux-drive" ;;
        plan-reviewed)       echo "work" ;;
        executing)           echo "quality-gates" ;;
        shipping)            echo "reflect" ;;
        reflect)             echo "done" ;;
        done)                echo "done" ;;
        *)                   echo "brainstorm" ;;
    esac
}

# Check if sprint should pause before advancing to target_phase.
# Returns 0 WITH STRUCTURED PAUSE REASON ON STDOUT if pause trigger found.
# Returns 1 (no output) if should continue.
sprint_should_pause() {
    local sprint_id="$1"
    local target_phase="$2"
    [[ -z "$sprint_id" || -z "$target_phase" ]] && return 1

    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || return 1
    if ! intercore_gate_check "$run_id" 2>/dev/null; then
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
    run_id=$(_sprint_resolve_run_id "$sprint_id") || return 1

    # Budget check (skip with CLAVAIN_SKIP_BUDGET)
    if [[ -z "${CLAVAIN_SKIP_BUDGET:-}" ]]; then
        "$INTERCORE_BIN" run budget "$run_id" 2>/dev/null
        local budget_rc=$?
        if [[ $budget_rc -eq 1 ]]; then
            local token_json spent budget_val
            token_json=$("$INTERCORE_BIN" run tokens "$run_id" --json 2>/dev/null) || token_json="{}"
            spent=$(echo "$token_json" | jq -r '(.input_tokens // 0) + (.output_tokens // 0)' 2>/dev/null) || spent="?"
            budget_val=$(intercore_run_status "$run_id" | jq -r '.token_budget // "?"' 2>/dev/null) || budget_val="?"
            echo "budget_exceeded|$current_phase|${spent}/${budget_val} billing tokens"
            return 1
        fi
    fi

    # Amendment F: handle advance result robustly
    local result
    result=$(intercore_run_advance "$run_id") || true
    local advanced
    advanced=$(echo "$result" | jq -r '.advanced // false' 2>/dev/null) || advanced="false"

    if [[ "$advanced" == "false" || "$advanced" == "null" ]]; then
        local event_type to_phase
        event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
        to_phase=$(echo "$result" | jq -r '.to_phase // ""' 2>/dev/null) || to_phase=""

        case "$event_type" in
            block)
                echo "gate_blocked|$to_phase|Gate prerequisites not met"
                ;;
            pause)
                echo "manual_pause|$to_phase|auto_advance=false"
                ;;
            *)
                if [[ -z "$event_type" ]]; then
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
    fi

    local from_phase to_phase
    from_phase=$(echo "$result" | jq -r '.from_phase // ""' 2>/dev/null) || from_phase="$current_phase"
    to_phase=$(echo "$result" | jq -r '.to_phase // ""' 2>/dev/null) || to_phase=""

    sprint_invalidate_caches
    sprint_record_phase_tokens "$sprint_id" "$current_phase" 2>/dev/null || true
    echo "Phase: $from_phase → $to_phase (auto-advancing)" >&2
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
        run_id=$(_sprint_resolve_run_id "$sprint_id") || run_id=""
        if [[ -n "$run_id" ]]; then
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

# ─── Checkpointing ───────────────────────────────────────────────

# Write or update a checkpoint after a sprint step completes.
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
    run_id=$(_sprint_resolve_run_id "$bead") || return 0

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
}

# Read the current checkpoint. Output: JSON or "{}"
checkpoint_read() {
    local bead_id="${1:-}"

    if ! intercore_available; then
        echo "{}"
        return 0
    fi

    local run_id=""
    if [[ -n "$bead_id" ]]; then
        run_id=$(_sprint_resolve_run_id "$bead_id") || run_id=""
    fi
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
    echo "{}"
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
    # Clean up legacy file-based checkpoints if present
    rm -f "${CLAVAIN_CHECKPOINT_FILE:-.clavain/checkpoint.json}" 2>/dev/null || true
}

# ─── Close Sweep ──────────────────────────────────────────────────

# Auto-close open beads that are blocked by a completed epic.
# Prevents the "bulk audit→bead" anti-pattern where child beads stay
# open after the parent epic ships them as part of its plan.
# Usage: sprint_close_children <epic_id> [reason]
# Returns: count of closed beads to stdout
sprint_close_children() {
    local epic_id="${1:?epic_id required}"
    local reason="${2:-Auto-closed: parent epic $epic_id shipped}"
    command -v bd &>/dev/null || { echo "0"; return 0; }

    # Parse BLOCKS section from bd show — only open beads (← ○)
    local blocked_ids
    blocked_ids=$(bd show "$epic_id" 2>/dev/null \
        | awk '/^BLOCKS$/,/^(DEPENDS ON|CHILDREN|LABELS|NOTES|DESCRIPTION|$)/' \
        | grep '← ○' \
        | sed 's/.*← ○ //' \
        | cut -d: -f1 \
        | tr -d ' ' \
        | grep -E '^[A-Za-z]+-[A-Za-z0-9]+$') || blocked_ids=""

    [[ -z "$blocked_ids" ]] && { echo "0"; return 0; }

    local closed=0
    while IFS= read -r child_id; do
        [[ -z "$child_id" ]] && continue
        bd close "$child_id" --reason="$reason" >/dev/null 2>&1 && closed=$((closed + 1))
    done <<< "$blocked_ids"

    echo "$closed"
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
