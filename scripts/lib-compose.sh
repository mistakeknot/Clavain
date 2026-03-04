#!/usr/bin/env bash
# lib-compose.sh — Thin shell bridge to clavain-cli compose.
# Sourced by sprint hooks and flux-drive to get dispatch plans.
#
# Usage:
#   source lib-compose.sh
#   plan=$(compose_dispatch "$sprint_id" "$stage")
#   echo "$plan" | jq '.agents[]'

_COMPOSE_LIB_SOURCED=1

# compose_dispatch <sprint_id> <stage>
# Returns JSON dispatch plan on stdout. Empty string on failure.
compose_dispatch() {
    local sprint_id="${1:-}"
    local stage="${2:?compose_dispatch: stage required}"
    local cli=""

    # Resolve clavain-cli binary
    cli=$(_compose_find_cli) || {
        echo "" # Fail silently — callers check for empty
        return 1
    }

    local args=(compose --stage="$stage")
    [[ -n "$sprint_id" ]] && args+=(--sprint="$sprint_id")

    "$cli" "${args[@]}" 2>/dev/null
}

# compose_available — check if compose command is functional
compose_available() {
    local cli=""
    cli=$(_compose_find_cli) || return 1
    "$cli" compose --stage=ship >/dev/null 2>&1
}

_compose_find_cli() {
    # 1. Plugin cache (Claude Code sessions)
    local candidate="${CLAUDE_PLUGIN_ROOT:-}/bin/clavain-cli-go"
    [[ -x "$candidate" ]] && { echo "$candidate"; return 0; }

    # 2. CLAVAIN_DIR (installed)
    candidate="${CLAVAIN_DIR:-}/bin/clavain-cli-go"
    [[ -x "$candidate" ]] && { echo "$candidate"; return 0; }

    # 3. CLAVAIN_SOURCE_DIR (dev)
    candidate="${CLAVAIN_SOURCE_DIR:-}/bin/clavain-cli-go"
    [[ -x "$candidate" ]] && { echo "$candidate"; return 0; }

    # 4. PATH
    command -v clavain-cli-go 2>/dev/null && return 0

    return 1
}
