#!/usr/bin/env bash
# Git pre-push helper — extracts bead IDs from commits being pushed and saves
# them to .git/bead-push-pending for the PostToolUse hook to consume.
#
# Called from the git pre-push hook. Reads ref info from stdin (git protocol).
# Stdin format: <local ref> <local sha> <remote ref> <remote sha>
#
# The marker file format is one line per bead: BEAD_ID\tCOMMIT_SHA
# Multiple refs in a single push are handled (all beads merged into one marker).
#
# This script MUST NOT fail the push — all errors are swallowed.

set -euo pipefail

main() {
    command -v git &>/dev/null || exit 0

    local git_dir
    git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
    [[ -n "$git_dir" ]] || exit 0

    local marker="$git_dir/bead-push-pending"
    local found_any=false

    # Read ref lines from stdin (git pre-push protocol)
    while IFS=' ' read -r local_ref local_sha remote_ref remote_sha; do
        [[ -n "$local_sha" ]] || continue

        # Skip branch deletions
        if [[ "$local_sha" == "0000000000000000000000000000000000000000" ]]; then
            continue
        fi

        # Determine commit range
        local range
        if [[ "$remote_sha" == "0000000000000000000000000000000000000000" ]]; then
            # New branch — scan all commits reachable from local that aren't on remote
            # Use --not --remotes to avoid scanning the entire history
            range="$local_sha --not --remotes"
        else
            range="${remote_sha}..${local_sha}"
        fi

        # Extract bead IDs from commit messages in this range, paired with their commit SHA
        # Format: COMMIT_SHA BEAD_ID (one per match)
        while IFS= read -r line; do
            [[ -n "$line" ]] || continue
            local sha msg_bead_id
            sha="${line%% *}"
            msg_bead_id="${line#* }"
            echo -e "${msg_bead_id}\t${sha}" >> "$marker"
            found_any=true
        done < <(git log --format='%H %s%n%H %b' $range 2>/dev/null \
            | grep -E '^[0-9a-f]+ .*\biv-[a-z0-9]+' \
            | while IFS= read -r log_line; do
                local commit_sha="${log_line%% *}"
                local msg="${log_line#* }"
                echo "$msg" | grep -oE '\biv-[a-z0-9]+\b' | while IFS= read -r bid; do
                    echo "$commit_sha $bid"
                done
            done 2>/dev/null || true)
    done

    # Deduplicate marker file (same bead from multiple commits — keep first occurrence)
    if [[ -f "$marker" ]]; then
        local tmp="${marker}.tmp"
        sort -t$'\t' -k1,1 -u "$marker" > "$tmp" 2>/dev/null && mv "$tmp" "$marker" || true
    fi
}

main "$@" || true
exit 0
