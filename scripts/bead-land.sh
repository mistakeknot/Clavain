#!/usr/bin/env bash
# Close orphaned beads — beads referenced in pushed commits that are still open.
#
# Uses `bd orphans` to find candidates, then filters out parents with open
# children before closing. Parents auto-close only when all children are done.
#
# Usage:
#   bead-land.sh              # close orphans (interactive)
#   bead-land.sh --dry-run    # show what would be closed
#   bead-land.sh --yes        # skip confirmation
#
# Intended to be called from the session close protocol:
#   git push → bead-land.sh → bd sync

set -euo pipefail

DRY_RUN=false
AUTO_YES=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --yes|-y) AUTO_YES=true ;;
        --help|-h)
            echo "Usage: bead-land.sh [--dry-run] [--yes]"
            echo "Close orphaned beads (referenced in commits but still open)."
            echo "Parents with open children are skipped."
            exit 0
            ;;
    esac
done

command -v bd &>/dev/null || { echo "bd not found" >&2; exit 1; }
command -v jq &>/dev/null || { echo "jq not found" >&2; exit 1; }

# Get orphaned beads from bd
orphans_json="$(bd orphans --json 2>/dev/null || echo "null")"
if [[ "$orphans_json" == "null" || "$orphans_json" == "[]" || -z "$orphans_json" ]]; then
    echo "No orphaned beads found."
    exit 0
fi

# Filter: skip beads with open children
to_close=()
skipped=()

while IFS= read -r bead_id; do
    [[ -n "$bead_id" ]] || continue

    # Check for open children
    children_json="$(bd children "$bead_id" --json 2>/dev/null || echo "null")"
    if [[ -n "$children_json" && "$children_json" != "null" && "$children_json" != "[]" ]]; then
        open_count="$(echo "$children_json" | jq '[.[] | select(.status | test("closed") | not)] | length' 2>/dev/null || echo "0")"
        if [[ "$open_count" -gt 0 ]]; then
            title="$(bd show "$bead_id" --json 2>/dev/null | jq -r '.title // empty' 2>/dev/null || true)"
            skipped+=("$bead_id ($open_count open children): $title")
            continue
        fi
    fi

    to_close+=("$bead_id")
done < <(echo "$orphans_json" | jq -r '.[].id // empty' 2>/dev/null)

# Report skipped parents
if [[ ${#skipped[@]} -gt 0 ]]; then
    echo "Skipped ${#skipped[@]} parent(s) with open children:"
    for s in "${skipped[@]}"; do
        echo "  - $s"
    done
    echo ""
fi

# Nothing to close after filtering
if [[ ${#to_close[@]} -eq 0 ]]; then
    echo "No beads to close (all orphans are parents with open children)."
    exit 0
fi

# Show what will be closed
echo "Will close ${#to_close[@]} orphaned bead(s):"
for bid in "${to_close[@]}"; do
    title="$(bd show "$bid" --json 2>/dev/null | jq -r '.title // empty' 2>/dev/null || true)"
    echo "  - $bid: $title"
done

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "(dry run — no changes made)"
    exit 0
fi

# Confirm unless --yes
if [[ "$AUTO_YES" != "true" ]]; then
    echo ""
    read -rp "Close these beads? [Y/n] " confirm
    if [[ "$confirm" =~ ^[Nn] ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Close them
bd close "${to_close[@]}" --reason="Landed: referenced in pushed commits" 2>&1
