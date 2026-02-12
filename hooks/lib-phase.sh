#!/usr/bin/env bash
# Phase state tracking library for Clavain.
# Sourced by workflow commands to record lifecycle phase transitions on beads.
# Phase tracking is observability only — functions never block or error.
#
# Phase model:
#   brainstorm → brainstorm-reviewed → strategized → planned →
#   plan-reviewed → executing → shipping → done
#
# CONCURRENCY ASSUMPTION: Commands run sequentially in a single Claude Code
# conversation. Parallel execution of commands on the same bead is NOT supported.
# bd set-state is atomic so no data corruption occurs, but duplicate phase events
# may be created if two commands set the same phase concurrently.

# Guard against double-sourcing
[[ -n "${_PHASE_LOADED:-}" ]] && return 0
_PHASE_LOADED=1

PHASE_PROJECT_DIR="${PHASE_PROJECT_DIR:-.}"

# Valid phases in lifecycle order. Used for validation and by future F6 gate library.
CLAVAIN_PHASES=(
    brainstorm
    brainstorm-reviewed
    strategized
    planned
    plan-reviewed
    executing
    shipping
    done
)

# ─── Core Functions ──────────────────────────────────────────────────

# Set the phase on a bead. Silent on failure — phase tracking must never block workflow.
# Logs transitions to ~/.clavain/telemetry.jsonl for observability.
#
# Args: $1 = bead_id, $2 = phase, $3 = reason (optional)
# Returns: 0 always (never fails the caller)
phase_set() {
    local bead_id="$1"
    local phase="$2"
    local reason="${3:-}"

    # Guard: need both bead_id and phase
    if [[ -z "$bead_id" || -z "$phase" ]]; then
        return 0
    fi

    # Guard: bd must be installed
    if ! command -v bd &>/dev/null; then
        return 0
    fi

    local cmd=(bd set-state "$bead_id" "phase=$phase")
    if [[ -n "$reason" ]]; then
        cmd+=(--reason "$reason")
    fi

    "${cmd[@]}" 2>/dev/null || true

    # Telemetry: log phase transition (append-only JSONL, never blocks)
    _phase_log_transition "$bead_id" "$phase" "$reason"
}

# Get the current phase of a bead. Returns empty string if not set or on error.
#
# Args: $1 = bead_id
# Output: phase value to stdout, or empty string
phase_get() {
    local bead_id="$1"

    if [[ -z "$bead_id" ]]; then
        echo ""
        return 0
    fi

    if ! command -v bd &>/dev/null; then
        echo ""
        return 0
    fi

    bd state "$bead_id" phase 2>/dev/null || echo ""
}

# ─── Bead ID Resolution ─────────────────────────────────────────────

# Infer the bead ID for the current command run.
# Resolution order:
#   1. CLAVAIN_BEAD_ID env var (set by /lfg discovery routing)
#   2. Grep target file for **Bead:** pattern (first match only)
#   3. Empty string (no bead tracking for this run)
#
# Multi-bead artifacts: if the file references multiple beads, a warning is
# logged to stderr and the first match is returned. For multi-bead plans,
# callers should set CLAVAIN_BEAD_ID explicitly.
#
# Args: $1 = file path to search for bead reference (optional)
# Output: bead ID to stdout, or empty string
phase_infer_bead() {
    local target_file="${1:-}"

    # Strategy 1: explicit env var (authoritative, handles multi-bead plans)
    if [[ -n "${CLAVAIN_BEAD_ID:-}" ]]; then
        echo "$CLAVAIN_BEAD_ID"
        return 0
    fi

    # Strategy 2: grep target file for bead reference
    if [[ -n "$target_file" && -f "$target_file" ]]; then
        local matches match_count bead_id
        # Match: **Bead:** Clavain-XXXX or Bead: Clavain-XXXX
        # Note: markdown bold wraps like **Bead:** so colon may be inside or outside the **
        matches=$(grep -oP '\*{0,2}Bead\*{0,2}:\*{0,2}\s*\K[A-Za-z]+-[A-Za-z0-9]+' "$target_file" 2>/dev/null || true)

        if [[ -n "$matches" ]]; then
            match_count=$(echo "$matches" | wc -l)
            bead_id=$(echo "$matches" | head -1)

            if [[ "$match_count" -gt 1 ]]; then
                echo "WARNING: multiple bead IDs in $target_file — using first ($bead_id). Set CLAVAIN_BEAD_ID for explicit control." >&2
            fi

            echo "$bead_id"
            return 0
        fi
    fi

    # Strategy 3: no bead found
    echo ""
}

# ─── Telemetry ───────────────────────────────────────────────────────

# Log a phase transition event. Append-only JSONL, fails silently.
# Uses jq for safe JSON construction — no injection from user data.
#
# Args: $1 = bead_id, $2 = phase, $3 = reason
_phase_log_transition() {
    local bead_id="$1"
    local phase="$2"
    local reason="${3:-}"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"

    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0

    jq -n -c \
        --arg event "phase_transition" \
        --arg bead "$bead_id" \
        --arg phase "$phase" \
        --arg reason "$reason" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, bead: $bead, phase: $phase, reason: $reason, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}
