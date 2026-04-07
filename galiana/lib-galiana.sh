#!/usr/bin/env bash
# Galiana analytics event library for Clavain.
#
# Writes structured telemetry events to ~/.clavain/telemetry.jsonl
# for analysis by galiana/analyze.py.
#
# Usage:
#   source galiana/lib-galiana.sh
#   galiana_log_signals "$SESSION_ID" "$SIGNALS" "$WEIGHT" "true"
#
# All functions are fail-safe: return 0 on error, never block workflow.

[[ -n "${_GALIANA_LOADED:-}" ]] && return 0
_GALIANA_LOADED=1

# _galiana_log <event_name> <jq_filter> <jq_args...>
# Handles mkdir, timestamp, append-to-JSONL boilerplate.
_galiana_log() {
    local event_name="$1"; shift
    local jq_filter="$1"; shift
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0
    local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    jq -n -c --arg event "$event_name" --arg ts "$ts" "$@" \
        "$jq_filter + {event: \$event, timestamp: \$ts}" \
        >> "$telemetry_file" 2>/dev/null || true
}

galiana_log_signals() {
    _galiana_log "signal_persist" \
        '{session_id: $session_id, signals: $signals, weight: $weight, compound_triggered: $compound_triggered}' \
        --arg session_id "$1" --arg signals "${2:-}" --argjson weight "${3:-0}" --arg compound_triggered "${4:-false}"
}

galiana_log_workflow_start() {
    _galiana_log "workflow_start" \
        '{session_id: $session_id, bead: $bead, command: $command, project: $project}' \
        --arg session_id "$1" --arg bead "$2" --arg command "$3" --arg project "$4"
}

galiana_log_workflow_end() {
    _galiana_log "workflow_end" \
        '{session_id: $session_id, bead: $bead, command: $command, project: $project, duration_s: $duration_s}' \
        --arg session_id "$1" --arg bead "$2" --arg command "$3" --arg project "$4" --argjson duration_s "${5:-0}"
}

galiana_log_defect() {
    _galiana_log "defect_report" \
        '{bead: $bead, defect_type: $defect_type, severity: $severity, escaped_gate: $escaped_gate, agents_reviewed: $agents_reviewed, agents_missed: $agents_missed}' \
        --arg bead "$1" --arg defect_type "$2" --arg severity "$3" --arg escaped_gate "$4" --arg agents_reviewed "$5" --arg agents_missed "$6"
}
