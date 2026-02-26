#!/usr/bin/env bash
# PostToolUse:Bash hook — auto-close beads after a successful git push.
#
# Two-phase design:
#   Phase 1 (git pre-push hook): saves bead IDs from commit messages to a
#           marker file at .git/bead-push-pending. This runs in the correct
#           repo CWD with reliable ref ranges from git's stdin.
#   Phase 2 (this hook): after a successful `git push`, reads the marker file,
#           closes eligible beads, and deletes the marker. If push failed, the
#           marker is also deleted (no stale close on retry).
#
# Protections:
#   - Beads with open children are never auto-closed — parent containers
#     (epics, features with subtasks, etc.) should only close when all
#     children are done. If all children are already closed, the parent
#     is safe to auto-close.
#   - Only beads in open/in_progress status are closed.
#   - Marker file is always cleaned up (success or failure).
#   - Falls back to HEAD~5 scan for repos without the pre-push helper.
#
# Input: PostToolUse JSON on stdin (tool_input.command, tool_result, cwd)
# Output: JSON with additionalContext listing closed beads, or empty on skip
# Exit: 0 always (fail-open)

set -euo pipefail

main() {
    # Guard: jq + bd required
    command -v jq &>/dev/null || exit 0
    command -v bd &>/dev/null || exit 0

    # Read hook input
    local payload
    payload="$(cat || true)"
    [[ -n "$payload" ]] || exit 0

    # Extract command and cwd
    local cmd cwd
    cmd="$(jq -r '.tool_input.command // empty' <<<"$payload" 2>/dev/null || true)"
    cwd="$(jq -r '.cwd // empty' <<<"$payload" 2>/dev/null || true)"
    [[ -n "$cmd" ]] || exit 0
    [[ -n "$cwd" ]] || exit 0

    # Fast exit: not a git push (~5ms path for 99% of Bash calls)
    [[ "$cmd" == *"git push"* || "$cmd" == *"git -C "*" push"* ]] || exit 0

    # Determine which repo(s) were pushed — handle both `git push` and `git -C <dir> push`
    local repo_dirs=()
    if [[ "$cmd" == *"git -C "* && "$cmd" == *" push"* ]]; then
        # Extract the -C argument: git -C <path> push ...
        local git_c_dir
        git_c_dir="$(echo "$cmd" | sed -n 's/.*git -C \([^ ]*\).*/\1/p' || true)"
        if [[ -n "$git_c_dir" ]]; then
            # Resolve relative to cwd
            if [[ "$git_c_dir" == /* ]]; then
                repo_dirs+=("$git_c_dir")
            else
                repo_dirs+=("$cwd/$git_c_dir")
            fi
        fi
    fi
    if [[ "$cmd" == *"git push"* && "$cmd" != *"git -C "* ]]; then
        repo_dirs+=("$cwd")
    fi
    # Also catch chained pushes: `git push && git -C foo push`
    # The above logic handles both patterns; for chained commands we may have both

    [[ ${#repo_dirs[@]} -gt 0 ]] || exit 0

    # Check if the push succeeded
    local exit_code
    exit_code="$(jq -r '.tool_result.exit_code // "0"' <<<"$payload" 2>/dev/null || true)"

    local closed=()
    local skipped_parents=()

    for repo_dir in "${repo_dirs[@]}"; do
        # Resolve to git toplevel
        local git_dir
        git_dir="$(git -C "$repo_dir" rev-parse --show-toplevel 2>/dev/null || true)"
        [[ -n "$git_dir" ]] || continue

        local marker="$git_dir/.git/bead-push-pending"

        # If no marker file, the pre-push hook wasn't installed in this repo.
        # Fall back to scanning recent commits (less precise but still works).
        if [[ ! -f "$marker" ]]; then
            if [[ "$exit_code" != "0" ]]; then
                continue
            fi
            # Generate marker from last 5 commits (conservative fallback)
            local tracking
            tracking="$(git -C "$git_dir" rev-parse --abbrev-ref '@{u}' 2>/dev/null || true)"
            if [[ -n "$tracking" ]]; then
                git -C "$git_dir" log --format='%H %s%n%H %b' HEAD~5..HEAD 2>/dev/null \
                    | grep -oE '\biv-[a-z0-9]+\b' \
                    | sort -u \
                    | while IFS= read -r bid; do
                        local head_sha
                        head_sha="$(git -C "$git_dir" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
                        echo -e "${bid}\t${head_sha}"
                    done > "$marker" 2>/dev/null || true
                [[ -s "$marker" ]] || { rm -f "$marker"; continue; }
            else
                continue
            fi
        fi

        if [[ "$exit_code" != "0" ]]; then
            # Push failed — clean up marker without closing
            rm -f "$marker"
            continue
        fi

        # Find .beads directory — walk up from git toplevel
        local beads_dir=""
        local search_dir="$git_dir"
        while [[ "$search_dir" != "/" ]]; do
            if [[ -d "$search_dir/.beads" ]]; then
                beads_dir="$search_dir/.beads"
                break
            fi
            search_dir="$(dirname "$search_dir")"
        done

        if [[ -z "$beads_dir" ]]; then
            rm -f "$marker"
            continue
        fi

        # Read bead IDs from marker and close eligible ones
        while IFS=$'\t' read -r bead_id commit_sha || [[ -n "$bead_id" ]]; do
            [[ -n "$bead_id" ]] || continue

            # Query bead status and type
            local bead_json
            bead_json="$(BEADS_DIR="$beads_dir" bd show "$bead_id" --json 2>/dev/null || true)"
            [[ -n "$bead_json" ]] || continue

            local status bead_type
            status="$(jq -r '.status // empty' <<<"$bead_json" 2>/dev/null || true)"
            bead_type="$(jq -r '.type // empty' <<<"$bead_json" 2>/dev/null || true)"

            # Skip beads with open children — parent containers should only
            # close when all children are done, regardless of type (epic, feature, etc.)
            local children_json open_children
            children_json="$(BEADS_DIR="$beads_dir" bd children "$bead_id" --json 2>/dev/null || true)"
            if [[ -n "$children_json" && "$children_json" != "[]" && "$children_json" != "null" ]]; then
                open_children="$(jq '[.[] | select(.status | test("closed") | not)] | length' <<<"$children_json" 2>/dev/null || echo "0")"
                if [[ "$open_children" -gt 0 ]]; then
                    skipped_parents+=("$bead_id")
                    continue
                fi
                # All children closed — safe to auto-close the parent too
            fi

            # Only close open or in-progress beads
            if [[ "$status" == "open" || "$status" == "in_progress" ]]; then
                local short_sha="${commit_sha:0:7}"
                if BEADS_DIR="$beads_dir" bd close "$bead_id" --reason="Auto-closed: pushed in ${short_sha:-commit}" 2>/dev/null; then
                    closed+=("$bead_id")
                fi
            fi
        done < "$marker"

        rm -f "$marker"
    done

    # Report
    local parts=()
    if [[ ${#closed[@]} -gt 0 ]]; then
        parts+=("Auto-closed ${#closed[@]} bead(s): ${closed[*]}")
    fi
    if [[ ${#skipped_parents[@]} -gt 0 ]]; then
        parts+=("Skipped ${#skipped_parents[@]} parent(s) with open children: ${skipped_parents[*]}")
    fi
    if [[ ${#parts[@]} -gt 0 ]]; then
        local msg
        msg="$(IFS='. '; echo "${parts[*]}")"
        jq -n --arg msg "$msg" '{"additionalContext": $msg}'
    fi
}

main "$@" || true
exit 0
