#!/usr/bin/env bash
# Agency spec loader library for Clavain.
# Loads, validates, and queries the agency-spec.yaml configuration.
#
# Public prefix: spec_*    Private prefix: _spec_*
#
# Must NOT use set -euo pipefail — sourced by hook entry points.
# All functions fail-safe: return 0 on error, never block workflow.
# Warnings use "spec: <message>" prefix to stderr for greppability.

# Guard against double-sourcing (separate from _SPEC_LOADED cache state)
[[ -n "${_SPEC_LIB_SOURCED:-}" ]] && return 0
_SPEC_LIB_SOURCED=1

# ─── Cache state machine ────────────────────────────────────────────
# _SPEC_LOADED=""         → never loaded
# _SPEC_LOADED="ok"       → loaded successfully, _SPEC_JSON is valid
# _SPEC_LOADED="failed"   → load attempted, failed. _SPEC_JSON is empty
# _SPEC_LOADED="fallback" → no spec file found. Functions return hardcoded defaults
#
# "failed" and "fallback" are sticky for the session — spec_load() won't retry.
# Call spec_invalidate_cache() to reset and force a reload.
#
# Critical invariant: set _SPEC_JSON first, then _SPEC_LOADED="ok".
# If Python call fails, set _SPEC_LOADED="failed". Never set guard before data.

_SPEC_LOADED=""  # Cache state: "" | "ok" | "failed" | "fallback"
_SPEC_JSON=""
_SPEC_MTIME=""
_SPEC_PATH=""

# ─── Path resolution ────────────────────────────────────────────────

_SPEC_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_SPEC_CLAVAIN_DIR="$(cd "$_SPEC_LIB_DIR/.." && pwd)"
_SPEC_SCHEMA_PATH="${_SPEC_CLAVAIN_DIR}/config/agency-spec.schema.json"
_SPEC_HELPER="${_SPEC_CLAVAIN_DIR}/scripts/agency-spec-helper.py"

# ─── Public API ──────────────────────────────────────────────────────

# Load + validate + cache the agency spec as JSON.
# Resolution order:
#   1. Project override: ${PROJECT_DIR}/.clavain/agency-spec.yaml
#   2. Default: ${CLAVAIN_DIR}/config/agency-spec.yaml
#   3. Neither: _SPEC_LOADED=fallback
spec_load() {
    # Already loaded — check mtime for staleness
    if [[ "$_SPEC_LOADED" == "ok" && -n "$_SPEC_PATH" && -n "$_SPEC_MTIME" ]]; then
        local current_mtime
        current_mtime=$(stat -c %Y "$_SPEC_PATH" 2>/dev/null) || current_mtime=""
        if [[ "$current_mtime" == "$_SPEC_MTIME" ]]; then
            return 0  # Still fresh
        fi
        # Stale — force reload
        _SPEC_LOADED=""
        _SPEC_JSON=""
    fi

    # Skip if we already tried and failed (or fell back)
    [[ "$_SPEC_LOADED" == "failed" || "$_SPEC_LOADED" == "fallback" ]] && return 0

    local project_dir="${SPRINT_LIB_PROJECT_DIR:-.}"
    local default_spec="${_SPEC_CLAVAIN_DIR}/config/agency-spec.yaml"
    local override_spec="${project_dir}/.clavain/agency-spec.yaml"

    # Find the base spec
    local spec_path=""
    if [[ -f "$default_spec" ]]; then
        spec_path="$default_spec"
    fi

    if [[ -z "$spec_path" ]]; then
        _SPEC_LOADED="fallback"
        echo "spec: no agency-spec.yaml found, using hardcoded defaults" >&2
        return 0
    fi

    # Check Python + PyYAML availability
    if ! python3 -c "import yaml" 2>/dev/null; then
        echo "spec: python3 + PyYAML not available, cannot load spec" >&2
        _SPEC_LOADED="failed"
        return 0
    fi

    # Load via Python helper (handles YAML parse + merge + budget normalization)
    local load_args=("$spec_path")
    if [[ -f "$override_spec" ]]; then
        load_args+=("$override_spec")
    fi

    local json_output
    json_output=$(python3 "$_SPEC_HELPER" load "${load_args[@]}") || {
        echo "spec: helper load failed" >&2
        _SPEC_LOADED="failed"
        return 0
    }

    # Validate JSON is parseable
    if ! echo "$json_output" | jq empty 2>/dev/null; then
        echo "spec: helper produced invalid JSON" >&2
        _SPEC_LOADED="failed"
        return 0
    fi

    # Set data FIRST, then guard
    _SPEC_JSON="$json_output"
    _SPEC_PATH="$spec_path"
    _SPEC_MTIME=$(stat -c %Y "$spec_path" 2>/dev/null) || _SPEC_MTIME=""
    _SPEC_LOADED="ok"

    # Validate against schema (non-blocking — warn only)
    if [[ -f "$_SPEC_SCHEMA_PATH" ]]; then
        if ! python3 "$_SPEC_HELPER" validate "$spec_path" "$_SPEC_SCHEMA_PATH"; then
            echo "spec: schema validation failed (continuing with loaded spec)" >&2
        fi
    fi

    return 0
}

# Returns 0 if spec loaded successfully, 1 otherwise.
spec_available() {
    spec_load  # Ensure loaded
    [[ "$_SPEC_LOADED" == "ok" ]]
}

# Force reload on next spec_load call.
spec_invalidate_cache() {
    _SPEC_LOADED=""
    _SPEC_JSON=""
    _SPEC_MTIME=""
    _SPEC_PATH=""
}

# Get a stage's full config as JSON.
spec_get_stage() {
    local stage="$1"
    [[ -z "$stage" ]] && { echo "{}"; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo "{}"; return 1; }
    echo "$_SPEC_JSON" | jq -c --arg s "$stage" '.stages[$s] // {}' 2>/dev/null || { echo "{}"; return 1; }
}

# Get a specific gate's config.
spec_get_gate() {
    local stage="$1" gate_name="$2"
    [[ -z "$stage" || -z "$gate_name" ]] && { echo "{}"; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo "{}"; return 1; }
    echo "$_SPEC_JSON" | jq -c --arg s "$stage" --arg g "$gate_name" '.stages[$s].gates[$g] // {}' 2>/dev/null || { echo "{}"; return 1; }
}

# Get all gates for a stage as JSON object.
spec_get_stage_gates() {
    local stage="$1"
    [[ -z "$stage" ]] && { echo "{}"; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo "{}"; return 1; }
    echo "$_SPEC_JSON" | jq -c --arg s "$stage" '.stages[$s].gates // {}' 2>/dev/null || { echo "{}"; return 1; }
}

# Get a top-level defaults value.
spec_get_default() {
    local key="$1"
    [[ -z "$key" ]] && { echo ""; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo ""; return 1; }
    echo "$_SPEC_JSON" | jq -r --arg k "$key" '.defaults[$k] // ""' 2>/dev/null || { echo ""; return 1; }
}

# Get budget config for a stage: {share, min_tokens, model_tier_hint}.
spec_get_budget() {
    local stage="$1"
    [[ -z "$stage" ]] && { echo "{}"; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo "{}"; return 1; }
    echo "$_SPEC_JSON" | jq -c --arg s "$stage" '.stages[$s].budget // {}' 2>/dev/null || { echo "{}"; return 1; }
}

# Get agent roster for a stage: {required: [...], optional: [...]}.
spec_get_agents() {
    local stage="$1"
    [[ -z "$stage" ]] && { echo '{"required":[],"optional":[]}'; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo '{"required":[],"optional":[]}'; return 1; }
    echo "$_SPEC_JSON" | jq -c --arg s "$stage" '.stages[$s].agents // {"required":[],"optional":[]}' 2>/dev/null || { echo '{"required":[],"optional":[]}'; return 1; }
}

# Get companion config.
spec_get_companion() {
    local name="$1"
    [[ -z "$name" ]] && { echo "{}"; return 1; }
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && { echo "{}"; return 1; }
    echo "$_SPEC_JSON" | jq -c --arg n "$name" '.companions[$n] // {}' 2>/dev/null || { echo "{}"; return 1; }
}

# Shadow-mode dispatch validation: log warning if agent not in spec roster.
# Does not block — stderr only.
spec_validate_dispatch() {
    local stage="$1" agent_role="$2"
    [[ -z "$stage" || -z "$agent_role" ]] && return 0
    spec_load
    [[ "$_SPEC_LOADED" != "ok" ]] && return 0

    local cap_mode
    cap_mode=$(spec_get_default "capability_mode") || cap_mode="shadow"
    [[ "$cap_mode" == "off" ]] && return 0

    local agents_json
    agents_json=$(spec_get_agents "$stage") || return 0

    local in_roster
    in_roster=$(echo "$agents_json" | jq --arg r "$agent_role" '
        (.required // [] | map(.role) | index($r) != null) or
        (.optional // [] | map(.role) | index($r) != null)
    ' 2>/dev/null) || in_roster="true"

    if [[ "$in_roster" != "true" ]]; then
        echo "spec: agent '$agent_role' not in roster for stage '$stage' (capability_mode=$cap_mode)" >&2
    fi
}
