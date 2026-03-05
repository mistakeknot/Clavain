#!/bin/bash
# Pre-commit hook: auto-fix catalog drift (version, component counts).
# Install: cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
#
# Runs gen-catalog.py and gen-rig-sync.py before each commit.
# If they update files, those changes are staged automatically.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

run_generator() {
    local script="$1"
    [ -f "$script" ] || return 0

    local output
    output=$(python3 "$script" 2>&1) || {
        echo "pre-commit: $(basename "$script") failed:" >&2
        echo "$output" >&2
        exit 1
    }

    if echo "$output" | grep -q "^Updated files:"; then
        echo "$output" | sed -n '/^- /s/^- //p' | while read -r file; do
            git add "$file"
        done
        echo "pre-commit: auto-staged updates from $(basename "$script")"
    fi
}

run_generator "$ROOT/scripts/gen-catalog.py"
run_generator "$ROOT/scripts/gen-rig-sync.py"
