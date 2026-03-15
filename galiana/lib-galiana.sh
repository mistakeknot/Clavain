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

galiana_log_signals() {
    local session_id="$1"
    local signals="${2:-}"
    local weight="${3:-0}"
    local compound_triggered="${4:-false}"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0
    jq -n -c \
        --arg event "signal_persist" \
        --arg session_id "$session_id" \
        --arg signals "$signals" \
        --argjson weight "$weight" \
        --arg compound_triggered "$compound_triggered" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, session_id: $session_id, signals: $signals, weight: $weight, compound_triggered: $compound_triggered, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}

galiana_log_workflow_start() {
    local session_id="$1"
    local bead_id="$2"
    local command="$3"
    local project="$4"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0
    jq -n -c \
        --arg event "workflow_start" \
        --arg session_id "$session_id" \
        --arg bead "$bead_id" \
        --arg command "$command" \
        --arg project "$project" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, session_id: $session_id, bead: $bead, command: $command, project: $project, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}

galiana_log_workflow_end() {
    local session_id="$1"
    local bead_id="$2"
    local command="$3"
    local project="$4"
    local duration_s="${5:-0}"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0
    jq -n -c \
        --arg event "workflow_end" \
        --arg session_id "$session_id" \
        --arg bead "$bead_id" \
        --arg command "$command" \
        --arg project "$project" \
        --argjson duration_s "$duration_s" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, session_id: $session_id, bead: $bead, command: $command, project: $project, duration_s: $duration_s, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}

galiana_log_defect() {
    local bead_id="$1"
    local defect_type="$2"
    local severity="$3"
    local escaped_gate="$4"
    local agents_reviewed="$5"
    local agents_missed="$6"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0
    jq -n -c \
        --arg event "defect_report" \
        --arg bead "$bead_id" \
        --arg defect_type "$defect_type" \
        --arg severity "$severity" \
        --arg escaped_gate "$escaped_gate" \
        --arg agents_reviewed "$agents_reviewed" \
        --arg agents_missed "$agents_missed" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, bead: $bead, defect_type: $defect_type, severity: $severity, escaped_gate: $escaped_gate, agents_reviewed: $agents_reviewed, agents_missed: $agents_missed, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}
