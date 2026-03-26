#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# lib-shadow-tracker.sh — detect shadow work-tracking files
# Used by: auto-stop-actions.sh (Stop hook), doctor.md (manual)
#
# Shadow trackers are files that duplicate beads' work-tracking responsibility.
# They drift silently and cause duplicate effort. Three detection categories:
#   1. todos/*.md with status: frontmatter (pending|open|done|complete|ready|in_progress)
#   2. pending-beads*.md files anywhere
#   3. *.md files with type: task|todo|tracker frontmatter (tightened from doctor.md)
#
# Excluded directories: .git/, node_modules/, docs/brainstorms/, docs/plans/,
# docs/prds/, docs/research/, docs/solutions/

[[ -n "${_LIB_SHADOW_TRACKER_LOADED:-}" ]] && return 0
_LIB_SHADOW_TRACKER_LOADED=1

# detect_shadow_trackers [dir]
# Outputs: one line per detected file. Returns count via exit code (0=none, N=count capped at 125).
detect_shadow_trackers() {
    local dir="${1:-.}"
    local count=0
    local files=()

    # Category 1: todos/*.md with status frontmatter
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        if head -10 "$f" 2>/dev/null | grep -qE '^status:\s*(pending|open|done|complete|ready|in_progress)'; then
            files+=("$f")
            ((count++))
        fi
    done < <(find "$dir" -path '*/todos/*.md' -not -path '*/.git/*' -not -path '*/node_modules/*' 2>/dev/null)

    # Category 2: pending-beads*.md files
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        files+=("$f")
        ((count++))
    done < <(find "$dir" -name 'pending-beads*.md' -not -path '*/.git/*' 2>/dev/null)

    # Category 3: *.md files with type:task/todo/tracker frontmatter
    # Tightened from doctor.md: requires type:task|todo|tracker, not just any status: key
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        if head -10 "$f" 2>/dev/null | grep -qE '^type:\s*(task|todo|tracker)'; then
            files+=("$f")
            ((count++))
        fi
    done < <(find "$dir" -maxdepth 3 -name '*.md' \
        -not -path '*/.git/*' \
        -not -path '*/node_modules/*' \
        -not -path '*/docs/brainstorms/*' \
        -not -path '*/docs/plans/*' \
        -not -path '*/docs/prds/*' \
        -not -path '*/docs/research/*' \
        -not -path '*/docs/solutions/*' 2>/dev/null | head -50)

    # Output detected files
    for f in "${files[@]}"; do
        echo "$f"
    done

    # Return count (capped at 125 for bash exit code safety)
    [[ $count -gt 125 ]] && count=125
    return "$count"
}
