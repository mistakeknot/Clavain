#!/usr/bin/env bash
# lib-log.sh — Structured JSON logging for Clavain hooks and plugins.
# Source this file to get log_debug, log_info, log_warn, log_error.
# Output: JSON lines to stderr.
# Env vars:
#   IC_LOG_LEVEL      — debug|info|warn|error (default: info)
#   IC_TRACE_ID       — trace correlation ID
#   IC_SPAN_ID        — span ID for this operation
#   IC_LOG_COMPONENT  — component name (default: basename of caller)

[[ -n "${_LIB_LOG_LOADED:-}" ]] && return 0
_LIB_LOG_LOADED=1

_LOG_COMPONENT="${IC_LOG_COMPONENT:-$(basename "${BASH_SOURCE[1]:-unknown}" .sh)}"

# Level integers: debug=0, info=1, warn=2, error=3
_log_level_int() {
    case "${1:-info}" in
        debug) echo 0 ;;
        info)  echo 1 ;;
        warn)  echo 2 ;;
        error) echo 3 ;;
        *)     echo 1 ;;
    esac
}

_LOG_THRESHOLD_DEFAULT=$(_log_level_int "${IC_LOG_LEVEL:-info}")

# Core log function. Usage: _log_emit LEVEL "message" [key=value ...]
_log_emit() {
    local level="$1" msg="$2"
    shift 2

    # Evaluate threshold dynamically — IC_LOG_LEVEL may be set per-command
    local threshold
    if [[ -n "${IC_LOG_LEVEL:-}" ]]; then
        threshold=$(_log_level_int "$IC_LOG_LEVEL")
    else
        threshold=$_LOG_THRESHOLD_DEFAULT
    fi

    local level_int
    level_int=$(_log_level_int "$level")
    if (( level_int < threshold )); then
        return 0
    fi

    # Build JSON with jq for safety (no injection from msg or extra fields)
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%S" 2>/dev/null)

    local extra_args=()
    extra_args+=(--arg level "$level" --arg msg "$msg" --arg ts "$ts" --arg component "$_LOG_COMPONENT")

    if [[ -n "${IC_TRACE_ID:-}" ]]; then
        extra_args+=(--arg trace_id "$IC_TRACE_ID")
    fi
    if [[ -n "${IC_SPAN_ID:-}" ]]; then
        extra_args+=(--arg span_id "$IC_SPAN_ID")
    fi

    # Build extra key=value pairs
    local kv_expr=""
    local idx=0
    for pair in "$@"; do
        local key="${pair%%=*}"
        local val="${pair#*=}"
        extra_args+=(--arg "kv_${idx}" "$key" --arg "vv_${idx}" "$val")
        kv_expr="${kv_expr} | .[\"\\(\$kv_${idx})\"] = \$vv_${idx}"
        idx=$((idx + 1))
    done

    local jq_filter='{level: $level, msg: $msg, ts: $ts, component: $component}'
    if [[ -n "${IC_TRACE_ID:-}" ]]; then
        jq_filter="${jq_filter} | .trace_id = \$trace_id"
    fi
    if [[ -n "${IC_SPAN_ID:-}" ]]; then
        jq_filter="${jq_filter} | .span_id = \$span_id"
    fi
    jq_filter="${jq_filter}${kv_expr}"

    jq -nc "${extra_args[@]}" "$jq_filter" >&2
}

log_debug() { _log_emit debug "$@"; }
log_info()  { _log_emit info "$@"; }
log_warn()  { _log_emit warn "$@"; }
log_error() { _log_emit error "$@"; }

# Generate a 32-char hex trace ID
generate_trace_id() {
    od -An -tx1 -N16 /dev/urandom 2>/dev/null | tr -d ' \n' || printf '%032x' "$$$(date +%s%N)"
}

# Generate a 16-char hex span ID
generate_span_id() {
    od -An -tx1 -N8 /dev/urandom 2>/dev/null | tr -d ' \n' || printf '%016x' "$$$(date +%s%N)"
}
