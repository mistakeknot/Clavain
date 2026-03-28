#!/usr/bin/env bash
# Temple: continuous invariant checker alongside bead execution (rsj.1.10).
# Runs as PostToolUse on Edit|Write|MultiEdit — checks invariants after each file change.
# Only active during sprint execution (CLAVAIN_BEAD_ID set).
# Lightweight: syntax-only checks, <100ms budget per invocation.
set -euo pipefail

# Skip if not in a sprint
[[ -z "${CLAVAIN_BEAD_ID:-}" ]] && exit 0

# Parse tool input to find the file path
file_path=""
if [[ -n "${TOOL_INPUT:-}" ]]; then
    file_path=$(echo "$TOOL_INPUT" | jq -r '.file_path // empty' 2>/dev/null) || file_path=""
fi
[[ -z "$file_path" ]] && exit 0
[[ ! -f "$file_path" ]] && exit 0

warnings=()

# Invariant 1: Syntax validity by file type
case "$file_path" in
    *.sh)
        if ! bash -n "$file_path" 2>/dev/null; then
            warnings+=("Shell syntax error in $(basename "$file_path")")
        fi
        ;;
    *.py)
        if ! python3 -c "import ast; ast.parse(open('$file_path').read())" 2>/dev/null; then
            warnings+=("Python syntax error in $(basename "$file_path")")
        fi
        ;;
    *.json)
        if ! python3 -c "import json; json.load(open('$file_path'))" 2>/dev/null; then
            warnings+=("Invalid JSON in $(basename "$file_path")")
        fi
        ;;
    *.go)
        # Only check if go is available and file is in a Go module
        if command -v go &>/dev/null; then
            dir=$(dirname "$file_path")
            if [[ -f "$dir/go.mod" ]] || [[ -f "$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)/go.mod" ]]; then
                # gofmt check (fast, catches syntax)
                if ! gofmt -e "$file_path" >/dev/null 2>&1; then
                    warnings+=("Go syntax error in $(basename "$file_path")")
                fi
            fi
        fi
        ;;
    *.yaml|*.yml)
        if command -v python3 &>/dev/null; then
            if ! python3 -c "import yaml; yaml.safe_load(open('$file_path'))" 2>/dev/null; then
                warnings+=("Invalid YAML in $(basename "$file_path")")
            fi
        fi
        ;;
esac

# Invariant 2: No secrets in source files (quick heuristic)
if [[ "$file_path" != *".env"* ]] && [[ "$file_path" != *"credentials"* ]]; then
    # Check for common secret patterns (API keys, passwords in plain text)
    if grep -qP '(?:password|api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*["\x27][^"\x27]{8,}' "$file_path" 2>/dev/null; then
        warnings+=("Possible hardcoded secret in $(basename "$file_path")")
    fi
fi

# Invariant 3: plugin.json validity (if that's what was edited)
if [[ "$(basename "$file_path")" == "plugin.json" ]]; then
    # Check required fields
    if ! python3 -c "
import json, sys
d = json.load(open('$file_path'))
assert 'name' in d, 'missing name'
assert 'description' in d, 'missing description'
" 2>/dev/null; then
        warnings+=("plugin.json missing required fields")
    fi
fi

# Emit warnings if any
if [[ ${#warnings[@]} -gt 0 ]]; then
    for w in "${warnings[@]}"; do
        echo "temple: $w" >&2
    done
    # Return non-zero to surface as hook warning (does not block)
    exit 0
fi

exit 0
