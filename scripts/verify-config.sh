#!/usr/bin/env bash
# verify-config.sh — Verify plugin enabled/disabled state from settings.json
#
# Reads agent-rig.json to determine required/conflict lists, then checks
# ~/.claude/settings.json for actual state. Uses jq (no python3 dependency).
#
# Usage: verify-config.sh [--json]
#   --json: Output JSON instead of human-readable text

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RIG_FILE="${SCRIPT_DIR}/../agent-rig.json"
SETTINGS="${HOME}/.claude/settings.json"
JSON_MODE=false

for arg in "$@"; do
    case "$arg" in
        --json) JSON_MODE=true ;;
    esac
done

if [[ ! -f "$RIG_FILE" ]]; then
    echo "ERROR: agent-rig.json not found at $RIG_FILE" >&2
    exit 1
fi

if ! command -v jq &>/dev/null; then
    echo "ERROR: jq is required but not installed" >&2
    exit 1
fi

if [[ ! -f "$SETTINGS" ]]; then
    echo "ERROR: settings.json not found at $SETTINGS" >&2
    exit 1
fi

# Extract required sources (core + required + recommended) from agent-rig.json
required_sources=$(jq -r '
    [
        (.plugins.core | if type == "object" then [.source] else [.[].source] end),
        [.plugins.required[]?.source],
        [.plugins.recommended[]?.source]
    ] | add | sort | .[]
' "$RIG_FILE")

# Extract conflict sources from agent-rig.json
conflict_sources=$(jq -r '[.plugins.conflicts[]?.source] | sort | .[]' "$RIG_FILE")

# Read enabledPlugins from settings.json (empty object if key absent)
enabled_plugins=$(jq '.enabledPlugins // {}' "$SETTINGS")

req_total=0
req_ok=0
req_results=()

while IFS= read -r source; do
    [[ -z "$source" ]] && continue
    req_total=$((req_total + 1))
    # absent = enabled by default, only explicit false means disabled
    val=$(echo "$enabled_plugins" | jq -r --arg s "$source" '.[$s] // "absent"')
    if [[ "$val" == "false" ]]; then
        req_results+=("$source:DISABLED")
    else
        req_ok=$((req_ok + 1))
        req_results+=("$source:enabled")
    fi
done <<< "$required_sources"

conf_total=0
conf_ok=0
conf_results=()

while IFS= read -r source; do
    [[ -z "$source" ]] && continue
    conf_total=$((conf_total + 1))
    val=$(echo "$enabled_plugins" | jq -r --arg s "$source" '.[$s] // "absent"')
    if [[ "$val" == "false" ]]; then
        conf_ok=$((conf_ok + 1))
        conf_results+=("$source:disabled")
    else
        conf_results+=("$source:STILL ENABLED")
    fi
done <<< "$conflict_sources"

if [[ "$JSON_MODE" == true ]]; then
    # Build JSON output
    req_json="[]"
    for r in "${req_results[@]}"; do
        src="${r%%:*}"
        status="${r#*:}"
        req_json=$(echo "$req_json" | jq --arg s "$src" --arg st "$status" '. + [{"source": $s, "status": $st}]')
    done
    conf_json="[]"
    for r in "${conf_results[@]}"; do
        src="${r%%:*}"
        status="${r#*:}"
        conf_json=$(echo "$conf_json" | jq --arg s "$src" --arg st "$status" '. + [{"source": $s, "status": $st}]')
    done
    jq -n \
        --argjson required "$req_json" \
        --argjson conflicts "$conf_json" \
        --arg req_summary "${req_ok}/${req_total} enabled" \
        --arg conf_summary "${conf_ok}/${conf_total} disabled" \
        '{required: $required, required_summary: $req_summary, conflicts: $conflicts, conflicts_summary: $conf_summary}'
else
    echo "=== Required Plugins ==="
    for r in "${req_results[@]}"; do
        src="${r%%:*}"
        status="${r#*:}"
        echo "  ${src}: ${status}"
    done
    echo "  (${req_ok}/${req_total} enabled)"
    echo ""
    echo "=== Conflicting Plugins ==="
    for r in "${conf_results[@]}"; do
        src="${r%%:*}"
        status="${r#*:}"
        echo "  ${src}: ${status}"
    done
    echo "  (${conf_ok}/${conf_total} disabled)"
fi
