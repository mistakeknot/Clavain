#!/usr/bin/env bash
# Render context only. Maintenance is an explicit startup.py refresh/doctor operation.
set -uo pipefail
trap 'exit 0' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if command -v python3 >/dev/null 2>&1 && [[ -r "${SCRIPT_DIR}/../scripts/startup.py" ]]; then
    if output=$(python3 -B "${SCRIPT_DIR}/../scripts/startup.py" render --project "${CLAUDE_PROJECT_DIR:-$PWD}" --telemetry); then
        printf '%s\n' "$output"
        exit 0
    fi
fi
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Clavain startup unknown: renderer unavailable. Read the selected using-clavain skill; verify task, ownership and acceptance prerequisites before acting."}}'
