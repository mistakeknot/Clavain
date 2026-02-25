#!/usr/bin/env bash
# PostToolUse:Bash hook — auto-close beads mentioned in pushed commits.
#
# After a successful `git push`, extracts bead IDs (iv-xxxxx pattern) from
# the commit messages that were just pushed, checks which are still open,
# and closes them. Reports what was closed via additionalContext.
#
# This eliminates the need to manually `bd close` after pushing work.
# Bead IDs are already embedded in commit messages by convention.
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
    [[ "$cmd" == *"git push"* ]] || exit 0

    # Skip if the push failed
    local exit_code
    exit_code="$(jq -r '.tool_result.exit_code // "0"' <<<"$payload" 2>/dev/null || true)"
    [[ "$exit_code" == "0" ]] || exit 0

    # Find .beads directory — walk up from cwd
    local beads_dir=""
    local search_dir="$cwd"
    while [[ "$search_dir" != "/" ]]; do
        if [[ -d "$search_dir/.beads" ]]; then
            beads_dir="$search_dir/.beads"
            break
        fi
        search_dir="$(dirname "$search_dir")"
    done
    [[ -n "$beads_dir" ]] || exit 0

    # Get the push output to find the commit range (e.g., "abc1234..def5678")
    # Fallback: use reflog to find what was just pushed
    local push_stdout
    push_stdout="$(jq -r '.tool_result.stdout // empty' <<<"$payload" 2>/dev/null || true)"
    local push_stderr
    push_stderr="$(jq -r '.tool_result.stderr // empty' <<<"$payload" 2>/dev/null || true)"
    local push_output="${push_stdout}${push_stderr}"

    # Extract commit range from push output (format: "oldsha..newsha branch -> branch")
    local commit_range=""
    commit_range="$(echo "$push_output" | grep -oE '[0-9a-f]+\.\.[0-9a-f]+' | head -1 || true)"

    # Fallback: get commits between remote tracking and HEAD
    if [[ -z "$commit_range" ]]; then
        local tracking
        tracking="$(git -C "$cwd" rev-parse --abbrev-ref '@{u}' 2>/dev/null || true)"
        if [[ -n "$tracking" ]]; then
            # After push, remote should equal HEAD. Use reflog to find pre-push state.
            # @{1} is HEAD before the push operation that just updated the tracking ref.
            # Safer: just scan last 10 commits — any bead mentioned gets closed.
            commit_range="HEAD~10..HEAD"
        fi
    fi
    [[ -n "$commit_range" ]] || exit 0

    # Extract bead IDs from commit messages in the range
    local bead_ids
    bead_ids="$(git -C "$cwd" log --format='%s%n%b' "$commit_range" 2>/dev/null \
        | grep -oE '\biv-[a-z0-9]+\b' \
        | sort -u || true)"
    [[ -n "$bead_ids" ]] || exit 0

    # Close open beads
    local closed=()
    local already_closed=()
    while IFS= read -r bead_id; do
        [[ -n "$bead_id" ]] || continue
        # Check if bead exists and is open
        local status
        status="$(BEADS_DIR="$beads_dir" bd list --id "$bead_id" --all --json 2>/dev/null \
            | jq -r '.[0].status // empty' 2>/dev/null || true)"
        if [[ "$status" == "open" || "$status" == "in_progress" ]]; then
            if BEADS_DIR="$beads_dir" bd close "$bead_id" --reason="Auto-closed: pushed in $(git -C "$cwd" rev-parse --short HEAD 2>/dev/null || echo 'commit')" 2>/dev/null; then
                closed+=("$bead_id")
            fi
        elif [[ "$status" == "closed" ]]; then
            already_closed+=("$bead_id")
        fi
    done <<<"$bead_ids"

    # Report
    if [[ ${#closed[@]} -gt 0 ]]; then
        local msg="Auto-closed ${#closed[@]} bead(s) mentioned in pushed commits: ${closed[*]}"
        jq -n --arg msg "$msg" '{"additionalContext": $msg}'
    fi
}

main "$@" || true
exit 0
