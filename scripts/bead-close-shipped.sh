#!/usr/bin/env bash
# Auto-close beads that have artifact_implementation state but are still open.
#
# The common failure mode: code ships, artifact state is set, session ends
# before the canonical close gate runs. This script catches those "phantom" beads.
#
# Usage:
#   bead-close-shipped.sh [--dry-run] [--session-id ID]
#
# --dry-run: print what would be closed, don't close
# --session-id: only check beads claimed by this session (SessionEnd mode)
#               omit to check all open beads (SessionStart mode)
#
# Exit: 0 always (fail-open — never block session lifecycle)

set -uo pipefail

DRY_RUN=false
SESSION_FILTER=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Canonical repository route: scripts/gates/bead-close.sh
CLOSE_GATE="${SCRIPT_DIR}/gates/bead-close.sh"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --session-id) SESSION_FILTER="$2"; shift 2 ;;
        *) shift ;;
    esac
done

command -v bd &>/dev/null || exit 0
command -v jq &>/dev/null || exit 0
[[ -x "$CLOSE_GATE" ]] || { echo "CLOSE_GATE_MISSING:${CLOSE_GATE}" >&2; exit 0; }

# Get open + in_progress beads as JSON
beads_json=$(bd list --status=open --limit 0 --json 2>/dev/null) || exit 0
in_progress_json=$(bd list --status=in_progress --limit 0 --json 2>/dev/null) || true
if [[ -n "$in_progress_json" ]]; then
    beads_json=$(echo "$beads_json $in_progress_json" | jq -s 'add // []')
fi

count=$(echo "$beads_json" | jq 'length' 2>/dev/null) || count=0
[[ "$count" -eq 0 ]] && exit 0

closed=0
skipped=0
phantoms=""

while IFS= read -r bead_id; do
    [[ -z "$bead_id" ]] && continue

    # Check if artifact_implementation state exists
    artifact=$(bd state "$bead_id" artifact_implementation 2>/dev/null) || artifact=""
    [[ -z "$artifact" || "$artifact" == *"no artifact_implementation"* ]] && continue

    # If session filter set, only close beads claimed by this session
    if [[ -n "$SESSION_FILTER" ]]; then
        claimed_by=$(bd state "$bead_id" claimed_by 2>/dev/null) || claimed_by=""
        [[ "$claimed_by" != "$SESSION_FILTER" ]] && continue
    fi

    # Verify the artifact commit exists in git
    commit_sha="${artifact%%,*}"  # Take first commit if comma-separated
    if ! git rev-parse --verify "$commit_sha" &>/dev/null 2>&1; then
        # Try in subproject repos
        found=false
        for repo_dir in os/Clavain os/Skaffen core/intercore interverse/interspect; do
            if [[ -d "$repo_dir/.git" ]] && git -C "$repo_dir" rev-parse --verify "$commit_sha" &>/dev/null 2>&1; then
                found=true
                break
            fi
        done
        $found || continue
    fi

    title=$(echo "$beads_json" | jq -r --arg id "$bead_id" '.[] | select(.id == $id) | .title // "unknown"' 2>/dev/null)
    phantoms="${phantoms}${bead_id} (${artifact}): ${title}\n"

    if $DRY_RUN; then
        continue
    fi

    if "$CLOSE_GATE" "$bead_id" "Artifact implementation verified at $commit_sha" >/dev/null 2>&1; then
        closed=$((closed + 1))
    else
        skipped=$((skipped + 1))
    fi

done < <(echo "$beads_json" | jq -r '.[].id' 2>/dev/null)

if [[ -n "$phantoms" ]]; then
    if $DRY_RUN; then
        echo "PHANTOM_BEADS"
        echo -e "$phantoms"
    else
        echo "AUTO_CLOSED:${closed} SKIPPED:${skipped}"
        echo -e "$phantoms"
    fi
fi

exit 0
