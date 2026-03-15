#!/usr/bin/env bash
# lib-compose.sh — Thin shell bridge to clavain-cli compose.
# Sourced by sprint hooks and flux-drive to get dispatch plans.
#
# Usage:
#   source lib-compose.sh
#   plan=$(compose_dispatch "$bead_id" "$stage")
#   echo "$plan" | jq '.agents[]'

_COMPOSE_LIB_SOURCED=1

# compose_dispatch <bead_id> <stage>
# Returns JSON dispatch plan on stdout. Empty string on failure.
# Tries stored ic artifact first (if bead_id provided), falls back to on-demand compose.
compose_dispatch() {
    local bead_id="${1:-}"
    local stage="${2:?compose_dispatch: stage required}"
    local cli=""
    cli=$(_compose_find_cli) || { echo ""; return 1; }

    # Try stored artifact first (if bead_id provided)
    if [[ -n "$bead_id" ]]; then
        local artifact_path=""
        artifact_path=$("$cli" get-artifact "$bead_id" "compose_plan" 2>/dev/null) || artifact_path=""
        if [[ -n "$artifact_path" && -f "$artifact_path" ]]; then
            local plan=""
            plan=$(jq -c --arg s "$stage" '.[] | select(.stage == $s)' "$artifact_path" 2>/dev/null) || plan=""
            if [[ -z "$plan" ]]; then
                # Try single plan format (not array)
                plan=$(jq -c --arg s "$stage" 'select(.stage == $s)' "$artifact_path" 2>/dev/null) || plan=""
            fi
            if [[ -n "$plan" ]]; then
                echo "$plan"
                return 0
            fi
        fi
    fi

    # Fallback: on-demand compose
    local args=(compose --stage="$stage")
    [[ -n "$bead_id" ]] && args+=(--sprint="$bead_id")
    "$cli" "${args[@]}" 2>/dev/null
}

# compose_available — check if compose command is functional
compose_available() {
    local cli=""
    cli=$(_compose_find_cli) || return 1
    "$cli" compose --stage=ship >/dev/null 2>&1
}

# compose_agents_json <plan_json>
# Extracts the agents array from a ComposePlan JSON string.
compose_agents_json() {
    local plan="${1:?compose_agents_json: plan required}"
    echo "$plan" | jq -c '.agents // []'
}

# compose_has_agents <plan_json>
# Returns 0 if the plan has a non-empty agents array.
compose_has_agents() {
    local plan="${1:-}"
    [[ -z "$plan" ]] && return 1
    local count=""
    count=$(echo "$plan" | jq '.agents | length' 2>/dev/null) || return 1
    [[ "$count" -gt 0 ]]
}

# compose_warn_if_expected <error_message>
# If agency-spec exists (user opted into Composer), print warning to stderr.
# If no agency-spec, silently succeed (Composer not configured = expected absence).
# Always returns 0 — this is a side-effect function, not a predicate.
compose_warn_if_expected() {
    local err="${1:-compose failed}"
    if _compose_has_agency_spec; then
        echo "compose: WARNING — $err (agency-spec found, Composer should be functional)" >&2
    fi
    return 0
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

_compose_has_agency_spec() {
    # Check project-local override first (highest priority per lib-spec.sh)
    local project_dir="${SPRINT_LIB_PROJECT_DIR:-.}"
    [[ -f "${project_dir}/.clavain/agency-spec.yaml" ]] && return 0
    # Then check standard config dirs
    for dir in "${CLAVAIN_CONFIG_DIR:-}" "${CLAVAIN_DIR:-}/config" "${CLAVAIN_SOURCE_DIR:-}/config" "${CLAUDE_PLUGIN_ROOT:-}/config"; do
        [[ -z "$dir" ]] && continue
        [[ -f "${dir}/agency-spec.yaml" ]] && return 0
    done
    return 1
}
