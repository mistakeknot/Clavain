#!/usr/bin/env bash
# Shared gate library for Clavain lifecycle phase transitions.
# Provides validation, dual persistence (beads + artifact headers), and fallback reading.
# This is a library only — no enforcement (that's F7).
#
# Sources lib-phase.sh internally (reuses phase_set, phase_get, CLAVAIN_PHASES).
# All public functions are fail-safe: return 0 on error, never block workflow.

# Guard against double-sourcing
[[ -n "${_GATES_LOADED:-}" ]] && return 0
_GATES_LOADED=1

GATES_PROJECT_DIR="${GATES_PROJECT_DIR:-.}"

# Source lib-phase.sh for phase_set, phase_get, phase_infer_bead, CLAVAIN_PHASES
_GATES_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHASE_PROJECT_DIR="$GATES_PROJECT_DIR" source "${_GATES_SCRIPT_DIR}/lib-phase.sh"

# ─── Phase Graph ─────────────────────────────────────────────────────

# Valid transitions as "from:to" strings. Empty from = first touch.
VALID_TRANSITIONS=(
    ":brainstorm"
    "brainstorm:brainstorm-reviewed"
    "brainstorm-reviewed:strategized"
    "strategized:planned"
    "planned:plan-reviewed"
    "plan-reviewed:executing"
    "executing:shipping"
    "shipping:done"
    # Skip paths (common in practice)
    ":brainstorm-reviewed"
    ":strategized"
    ":planned"
    ":plan-reviewed"
    ":executing"
    "brainstorm:strategized"
    "brainstorm-reviewed:planned"
    "strategized:plan-reviewed"
    "planned:executing"
    "plan-reviewed:shipping"
    "executing:done"
)

# Directories whose artifacts get **Phase:** headers.
# PRDs excluded — they are shared across beads.
ARTIFACT_PHASE_DIRS=("docs/brainstorms" "docs/plans")

# ─── Public Functions ────────────────────────────────────────────────

# Check if a transition from one phase to another is valid.
# Args: $1 = from (empty string for first touch), $2 = to
# Returns: 0 if valid, 1 if invalid
is_valid_transition() {
    local from="${1:-}"
    local to="${2:-}"

    if [[ -z "$to" ]]; then
        return 1
    fi

    local entry
    for entry in "${VALID_TRANSITIONS[@]}"; do
        if [[ "$entry" == "${from}:${to}" ]]; then
            return 0
        fi
    done
    return 1
}

# Check whether a phase gate allows transition to the target phase.
# Reads current phase via phase_get_with_fallback, checks is_valid_transition.
# Returns 0 on valid (or on error — fail-safe). Returns 1 on invalid, with stderr warning.
#
# Args: $1 = bead_id, $2 = target phase, $3 = artifact_path (optional)
check_phase_gate() {
    local bead_id="${1:-}"
    local target="${2:-}"
    local artifact_path="${3:-}"

    # Fail-safe: if inputs are missing, allow
    if [[ -z "$bead_id" || -z "$target" ]]; then
        return 0
    fi

    local current
    current=$(phase_get_with_fallback "$bead_id" "$artifact_path" 2>/dev/null) || true

    if is_valid_transition "$current" "$target"; then
        _gate_log_check "$bead_id" "$current" "$target" "pass"
        return 0
    else
        echo "WARNING: phase gate blocked $current → $target for $bead_id" >&2
        _gate_log_check "$bead_id" "$current" "$target" "blocked"
        return 1
    fi
}

# Advance the phase: set on bead (via phase_set) and write to artifact header.
# Fail-safe: never blocks workflow.
#
# Args: $1 = bead_id, $2 = target phase, $3 = reason, $4 = artifact_path (optional)
advance_phase() {
    local bead_id="${1:-}"
    local target="${2:-}"
    local reason="${3:-}"
    local artifact_path="${4:-}"

    # Guard: need bead_id and target
    if [[ -z "$bead_id" || -z "$target" ]]; then
        return 0
    fi

    # Write to beads (primary persistence)
    phase_set "$bead_id" "$target" "$reason"

    # Write to artifact header (secondary persistence)
    if [[ -n "$artifact_path" ]]; then
        _gate_write_artifact_phase "$artifact_path" "$target"
    fi

    _gate_log_advance "$bead_id" "$target" "$reason" "$artifact_path"

    # Update statusline state file (read by ~/.claude/statusline.sh)
    _gate_update_statusline "$bead_id" "$target" "$reason"
}

# Get the current phase with fallback: beads first, then artifact header.
# Warns on desync (beads != artifact).
#
# Args: $1 = bead_id, $2 = artifact_path (optional)
# Output: phase value to stdout, or empty string
phase_get_with_fallback() {
    local bead_id="${1:-}"
    local artifact_path="${2:-}"

    local bead_phase=""
    local artifact_phase=""

    # Read from beads (primary)
    if [[ -n "$bead_id" ]]; then
        bead_phase=$(phase_get "$bead_id" 2>/dev/null) || true
    fi

    # Read from artifact header (secondary)
    if [[ -n "$artifact_path" ]]; then
        artifact_phase=$(_gate_read_artifact_phase "$artifact_path" 2>/dev/null) || true
    fi

    # Return beads phase if available
    if [[ -n "$bead_phase" ]]; then
        # Warn on desync
        if [[ -n "$artifact_phase" && "$bead_phase" != "$artifact_phase" ]]; then
            _gate_log_desync "$bead_id" "$bead_phase" "$artifact_phase" "$artifact_path"
            echo "WARNING: phase desync for $bead_id — beads=$bead_phase, artifact=$artifact_phase" >&2
        fi
        echo "$bead_phase"
        return 0
    fi

    # Fallback to artifact
    if [[ -n "$artifact_phase" ]]; then
        echo "$artifact_phase"
        return 0
    fi

    echo ""
}

# ─── Internal Functions ──────────────────────────────────────────────

# Write or update **Phase:** header in an artifact file.
# Only writes to files in ARTIFACT_PHASE_DIRS. Skips silently otherwise.
#
# Args: $1 = file path, $2 = phase
_gate_write_artifact_phase() {
    local filepath="${1:-}"
    local phase="${2:-}"

    if [[ -z "$filepath" || -z "$phase" || ! -f "$filepath" ]]; then
        return 0
    fi

    # Check if file is in an allowed directory
    local allowed=false
    local dir
    for dir in "${ARTIFACT_PHASE_DIRS[@]}"; do
        if [[ "$filepath" == *"$dir"* ]]; then
            allowed=true
            break
        fi
    done
    if [[ "$allowed" != "true" ]]; then
        return 0
    fi

    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "unknown")
    local phase_line="**Phase:** ${phase} (as of ${timestamp})"
    local escaped_phase_line
    escaped_phase_line=$(_gate_sed_escape "$phase_line")

    # Strategy 1: Update existing **Phase:** line
    if grep -q '^\*\*Phase:\*\*' "$filepath" 2>/dev/null; then
        sed -i "s|^\*\*Phase:\*\*.*|${escaped_phase_line}|" "$filepath" 2>/dev/null || true
        return 0
    fi

    # Strategy 2: Insert after **Bead:** line
    if grep -q '^\*\*Bead:\*\*' "$filepath" 2>/dev/null; then
        sed -i "/^\*\*Bead:\*\*/a\\${escaped_phase_line}" "$filepath" 2>/dev/null || true
        return 0
    fi

    # Strategy 3: Insert after first # heading
    if grep -q '^# ' "$filepath" 2>/dev/null; then
        sed -i "0,/^# /{/^# /a\\${escaped_phase_line}
}" "$filepath" 2>/dev/null || true
        return 0
    fi
}

# Read phase value from **Phase:** line in an artifact file.
# Args: $1 = file path
# Output: phase value to stdout, or empty string
_gate_read_artifact_phase() {
    local filepath="${1:-}"

    if [[ -z "$filepath" || ! -f "$filepath" ]]; then
        echo ""
        return 0
    fi

    local line
    line=$(grep '^\*\*Phase:\*\*' "$filepath" 2>/dev/null | head -1) || true

    if [[ -z "$line" ]]; then
        echo ""
        return 0
    fi

    # Extract: **Phase:** <value> (as of <timestamp>)
    # Strip "**Phase:** " prefix and optional " (as of ...)" suffix
    local phase
    phase=$(echo "$line" | sed 's/^\*\*Phase:\*\*\s*//' | sed 's/\s*(as of .*)$//')
    echo "$phase"
}

# Escape a string for safe use in sed replacement.
# Handles backslash, forward slash, and ampersand.
_gate_sed_escape() {
    local str="$1"
    str="${str//\\/\\\\}"
    str="${str//\//\\/}"
    str="${str//&/\\&}"
    echo "$str"
}

# Write bead context to a session-keyed state file for the statusline.
# The statusline script runs as a subprocess and can't see in-conversation
# state, so we use /tmp/clavain-bead-<session_id>.json as a sideband channel.
#
# Args: $1 = bead_id, $2 = phase, $3 = reason (optional)
_gate_update_statusline() {
    local bead_id="$1" phase="$2" reason="${3:-}"
    local session_id="${CLAUDE_SESSION_ID:-}"
    [ -z "$session_id" ] && return 0
    local state_file="/tmp/clavain-bead-${session_id}.json"
    jq -n -c \
        --arg id "$bead_id" --arg phase "$phase" \
        --arg reason "$reason" --arg ts "$(date +%s)" \
        '{id:$id, phase:$phase, reason:$reason, ts:($ts|tonumber)}' \
        > "$state_file" 2>/dev/null || true
}

# ─── Telemetry ───────────────────────────────────────────────────────

_gate_log_check() {
    local bead_id="$1"
    local from="${2:-}"
    local to="$3"
    local result="$4"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"

    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0

    jq -n -c \
        --arg event "gate_check" \
        --arg bead "$bead_id" \
        --arg from "$from" \
        --arg to "$to" \
        --arg result "$result" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, bead: $bead, from: $from, to: $to, result: $result, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}

_gate_log_advance() {
    local bead_id="$1"
    local phase="$2"
    local reason="${3:-}"
    local artifact="${4:-}"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"

    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0

    jq -n -c \
        --arg event "phase_advance" \
        --arg bead "$bead_id" \
        --arg phase "$phase" \
        --arg reason "$reason" \
        --arg artifact "$artifact" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, bead: $bead, phase: $phase, reason: $reason, artifact: $artifact, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}

_gate_log_desync() {
    local bead_id="$1"
    local bead_phase="$2"
    local artifact_phase="$3"
    local artifact_path="${4:-}"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"

    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0

    jq -n -c \
        --arg event "phase_desync" \
        --arg bead "$bead_id" \
        --arg bead_phase "$bead_phase" \
        --arg artifact_phase "$artifact_phase" \
        --arg artifact "$artifact_path" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, bead: $bead, bead_phase: $bead_phase, artifact_phase: $artifact_phase, artifact: $artifact, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}
