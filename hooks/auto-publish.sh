#!/usr/bin/env bash
# PostToolUse hook: auto-publish plugin after git push
#
# Detects `git push` in plugin repos, delegates to `ic publish --auto`
# which handles: patch bump if needed, marketplace sync, cache rebuild,
# installed_plugins.json update, per-plugin sentinel, and never amends
# or force-pushes.
#
# Input: PostToolUse JSON on stdin (tool_input.command, cwd)
# Output: JSON with additionalContext on success, empty on skip
# Exit: 0 always (fail-open)

set -euo pipefail

main() {
    command -v jq &>/dev/null || exit 0

    local payload
    payload="$(cat || true)"
    [[ -n "$payload" ]] || exit 0

    local cmd cwd
    cmd="$(jq -r '.tool_input.command // empty' <<<"$payload" 2>/dev/null || true)"
    cwd="$(jq -r '.cwd // empty' <<<"$payload" 2>/dev/null || true)"
    [[ -n "$cmd" ]] || exit 0
    [[ -n "$cwd" ]] || exit 0

    # Fast exit: not a git push (~5ms path for 99% of Bash calls)
    [[ "$cmd" == *"git push"* ]] || exit 0

    # Skip if the original push failed
    local exit_code
    exit_code="$(jq -r '.tool_result.exit_code // "0"' <<<"$payload" 2>/dev/null || true)"
    [[ "$exit_code" == "0" ]] || exit 0

    # Skip force pushes
    [[ "$cmd" != *"--force"* && "$cmd" != *"-f "* && "$cmd" != *"--no-verify"* ]] || exit 0

    # Skip non-main branch pushes
    local branch
    branch="$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [[ "$branch" == "main" || "$branch" == "master" ]] || exit 0

    # Check if this is a plugin repo
    [[ -f "$cwd/.claude-plugin/plugin.json" ]] || exit 0

    # Delegate to ic publish --auto
    local ic_bin
    ic_bin="$(command -v ic 2>/dev/null || true)"
    [[ -n "$ic_bin" ]] || exit 0

    local output
    output="$("$ic_bin" publish --auto --cwd="$cwd" 2>&1 || true)"

    # Extract plugin name for the report
    local plugin_name
    plugin_name="$(jq -r '.name // empty' "$cwd/.claude-plugin/plugin.json" 2>/dev/null || true)"

    if [[ -n "$output" && "$output" == *"Published"* ]]; then
        jq -n --arg msg "$output" '{"additionalContext": $msg}'
    elif [[ -n "$output" && "$output" == *"Synced"* ]]; then
        jq -n --arg msg "$output" '{"additionalContext": $msg}'
    fi
}

main "$@" || true
exit 0
