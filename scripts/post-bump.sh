#!/bin/bash
#
# Clavain post-bump hook — called by interbump before git commit.
# Refreshes skill/agent/command catalog counts in plugin.json description.
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

if command -v python3 &>/dev/null && [ -f "$REPO_ROOT/scripts/gen-catalog.py" ]; then
    if [[ "${1:-}" == "--check" ]] || [[ "${DRY_RUN:-}" == "true" ]]; then
        python3 "$REPO_ROOT/scripts/gen-catalog.py" --check || true
    else
        python3 "$REPO_ROOT/scripts/gen-catalog.py"
    fi
fi

# Sync agent-rig plugin lists into setup.md and doctor.md
if command -v python3 &>/dev/null && [ -f "$REPO_ROOT/scripts/gen-rig-sync.py" ]; then
    if [[ "${1:-}" == "--check" ]] || [[ "${DRY_RUN:-}" == "true" ]]; then
        python3 "$REPO_ROOT/scripts/gen-rig-sync.py" --check || true
    else
        python3 "$REPO_ROOT/scripts/gen-rig-sync.py"
    fi
fi
