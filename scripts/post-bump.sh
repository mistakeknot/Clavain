#!/bin/bash
#
# Clavain post-bump hook — called by interbump before git commit.
# Refreshes skill/agent/command catalog counts in plugin.json description.
#
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TARGET_VERSION="${1:-}"

# Intercore invokes this hook before writing plugin.json, but passes the target
# version as argv[1]. Keep the human-facing PRD in the same atomic publish
# commit so a successful patch bump cannot leave the structural suite stale.
if [[ -n "$TARGET_VERSION" && "$TARGET_VERSION" != "--check" && "${DRY_RUN:-}" != "true" ]]; then
    PRD="$REPO_ROOT/docs/PRD.md"
    if [[ -f "$PRD" ]]; then
        TMP="${PRD}.tmp.$$"
        trap 'rm -f "$TMP"' EXIT
        sed -E "s/^\*\*Version:\*\*[[:space:]]+[^[:space:]]+/**Version:** ${TARGET_VERSION}/" "$PRD" > "$TMP"
        mv -f "$TMP" "$PRD"
        trap - EXIT
    fi
fi

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
