#!/usr/bin/env bash
# PostToolUse hook: auto-publish plugin after git push
#
# Detects `git push` in plugin repos, auto-increments patch version if the
# developer forgot to bump, syncs marketplace, and pushes marketplace.
#
# Loop prevention: sentinel file with 60s TTL prevents re-trigger when this
# hook itself pushes (the amended commit or the marketplace push).
# Uses a global sentinel (not per-plugin) to prevent cascade triggers
# across plugin → marketplace push chains.
#
# Input: PostToolUse JSON on stdin (tool_input.command, cwd)
# Output: JSON with additionalContext on success, empty on skip
# Exit: 0 always (fail-open)

set -euo pipefail

main() {
    # Guard: jq required for JSON parsing
    command -v jq &>/dev/null || exit 0

    # Source intercore sentinel wrappers (fail-open if unavailable)
    source "${BASH_SOURCE[0]%/*}/lib-intercore.sh" 2>/dev/null || true

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

    # Skip if the original push failed
    local exit_code
    exit_code="$(jq -r '.tool_result.exit_code // "0"' <<<"$payload" 2>/dev/null || true)"
    [[ "$exit_code" == "0" ]] || exit 0

    # Skip any force pushes (--force, -f, --force-with-lease, --no-verify)
    [[ "$cmd" != *"--force"* && "$cmd" != *"-f "* && "$cmd" != *"--no-verify"* ]] || exit 0

    # Skip non-main branch pushes
    local branch
    branch="$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [[ "$branch" == "main" || "$branch" == "master" ]] || exit 0

    # Check if this is a plugin repo
    local plugin_json="$cwd/.claude-plugin/plugin.json"
    [[ -f "$plugin_json" ]] || exit 0

    # Read plugin name and version
    local plugin_name plugin_version
    plugin_name="$(jq -r '.name // empty' "$plugin_json" 2>/dev/null || true)"
    plugin_version="$(jq -r '.version // empty' "$plugin_json" 2>/dev/null || true)"
    [[ -n "$plugin_name" && -n "$plugin_version" ]] || exit 0

    # Global sentinel: prevent ALL auto-publish re-triggers within 60s.
    intercore_check_or_die "autopub" "global" 60

    # Find marketplace — walk up from plugin looking for core/marketplace/ (monorepo layout)
    local marketplace_root="${MARKETPLACE_ROOT:-}"
    if [[ -z "$marketplace_root" ]]; then
        local search_dir="$cwd"
        for _ in 1 2 3 4; do
            search_dir="$(dirname "$search_dir")"
            if [[ -f "$search_dir/core/marketplace/.claude-plugin/marketplace.json" ]]; then
                marketplace_root="$search_dir/core/marketplace"
                break
            fi
        done
    fi
    # Fall back to Claude Code's own marketplace checkout
    if [[ -z "$marketplace_root" ]]; then
        local cc_marketplace="$HOME/.claude/plugins/marketplaces/interagency-marketplace"
        if [[ -f "$cc_marketplace/.claude-plugin/marketplace.json" ]]; then
            marketplace_root="$cc_marketplace"
        fi
    fi
    [[ -n "$marketplace_root" ]] || exit 0
    local marketplace_json="$marketplace_root/.claude-plugin/marketplace.json"
    [[ -f "$marketplace_json" ]] || exit 0

    # Find this plugin's marketplace version
    local marketplace_version
    marketplace_version="$(jq -r --arg name "$plugin_name" \
        '.plugins[] | select(.name == $name) | .version // empty' \
        "$marketplace_json" 2>/dev/null || true)"
    # Plugin not in marketplace — needs manual first-time add
    [[ -n "$marketplace_version" ]] || exit 0

    # Compare versions — determine if we need to auto-bump
    local action="sync"  # default: just sync marketplace
    if [[ "$marketplace_version" == "$plugin_version" ]]; then
        # Developer didn't bump — auto-increment patch
        action="bump"
    fi

    local new_version="$plugin_version"

    if [[ "$action" == "bump" ]]; then
        # Auto-increment patch: X.Y.Z → X.Y.(Z+1)
        local major minor patch
        IFS='.' read -r major minor patch <<<"$plugin_version"
        patch=$((patch + 1))
        new_version="${major}.${minor}.${patch}"

        # Update plugin.json
        local tmp_file
        tmp_file="$(mktemp)"
        jq --arg v "$new_version" '.version = $v' "$plugin_json" > "$tmp_file" && \
            mv "$tmp_file" "$plugin_json"
        git -C "$cwd" add .claude-plugin/plugin.json

        # Update all discovered version files (same discovery as interbump.sh)
        for vf in package.json server/package.json; do
            if [[ -f "$cwd/$vf" ]]; then
                tmp_file="$(mktemp)"
                jq --arg v "$new_version" '.version = $v' "$cwd/$vf" > "$tmp_file" && \
                    mv "$tmp_file" "$cwd/$vf"
                git -C "$cwd" add "$vf" 2>/dev/null || true
            fi
        done

        if [[ -f "$cwd/pyproject.toml" ]]; then
            # Match any version string, not just $plugin_version — pyproject.toml
            # may already be out of sync with plugin.json.
            sed -i 's/^version = "[0-9][0-9.]*"/version = "'"$new_version"'"/' "$cwd/pyproject.toml"
            git -C "$cwd" add pyproject.toml 2>/dev/null || true
        fi

        if [[ -f "$cwd/agent-rig.json" ]]; then
            tmp_file="$(mktemp)"
            jq --arg v "$new_version" '.version = $v' "$cwd/agent-rig.json" > "$tmp_file" && \
                mv "$tmp_file" "$cwd/agent-rig.json"
            git -C "$cwd" add agent-rig.json 2>/dev/null || true
        fi

        # Amend last commit with version bump, push
        git -C "$cwd" commit --amend --no-edit --quiet 2>/dev/null || true
        git -C "$cwd" push --force-with-lease --quiet 2>/dev/null || true
    fi

    # Sync marketplace: update version for this plugin
    local tmp_mkt
    tmp_mkt="$(mktemp)"
    jq --arg name "$plugin_name" --arg v "$new_version" \
        '(.plugins[] | select(.name == $name)).version = $v' \
        "$marketplace_json" > "$tmp_mkt" && \
        mv "$tmp_mkt" "$marketplace_json"

    # Commit and push marketplace
    git -C "$marketplace_root" add .claude-plugin/marketplace.json
    git -C "$marketplace_root" commit -m "chore: bump $plugin_name to v$new_version" --quiet 2>/dev/null || true
    git -C "$marketplace_root" push --quiet 2>/dev/null || true

    # Sync Claude Code's own marketplace checkout if it differs from monorepo copy
    local cc_marketplace="$HOME/.claude/plugins/marketplaces/interagency-marketplace"
    if [[ "$marketplace_root" != "$cc_marketplace" && -f "$cc_marketplace/.claude-plugin/marketplace.json" ]]; then
        local cc_ver
        cc_ver="$(jq -r --arg name "$plugin_name" \
            '.plugins[] | select(.name == $name) | .version // empty' \
            "$cc_marketplace/.claude-plugin/marketplace.json" 2>/dev/null || true)"
        if [[ "$cc_ver" != "$new_version" ]]; then
            local tmp_cc
            tmp_cc="$(mktemp)"
            jq --arg name "$plugin_name" --arg v "$new_version" \
                '(.plugins[] | select(.name == $name)).version = $v' \
                "$cc_marketplace/.claude-plugin/marketplace.json" > "$tmp_cc" && \
                mv "$tmp_cc" "$cc_marketplace/.claude-plugin/marketplace.json"
            git -C "$cc_marketplace" add .claude-plugin/marketplace.json 2>/dev/null || true
            git -C "$cc_marketplace" commit -m "chore: bump $plugin_name to v$new_version" --quiet 2>/dev/null || true
            git -C "$cc_marketplace" push --quiet 2>/dev/null || true
        fi
    fi

    # Rebuild plugin cache so next session picks up the new version immediately
    local cache_dir="$HOME/.claude/plugins/cache/interagency-marketplace/$plugin_name/$new_version"
    if [[ ! -d "$cache_dir" ]]; then
        cp -a "$cwd" "$cache_dir" 2>/dev/null || true
    fi

    # Update installed_plugins.json to point at the new cache
    local installed_json="$HOME/.claude/plugins/installed_plugins.json"
    if [[ -f "$installed_json" ]]; then
        local tmp_inst
        tmp_inst="$(mktemp)"
        local plugin_key="${plugin_name}@interagency-marketplace"
        jq --arg key "$plugin_key" --arg v "$new_version" \
            --arg path "$cache_dir" \
            '(.plugins[$key][0].version = $v) | (.plugins[$key][0].installPath = $path)' \
            "$installed_json" > "$tmp_inst" 2>/dev/null && \
            mv "$tmp_inst" "$installed_json" || true
    fi

    # Report what happened
    local msg
    if [[ "$action" == "bump" ]]; then
        msg="Auto-published ${plugin_name} v${new_version} (patch bump from v${plugin_version}). Amended last commit with version bump and synced marketplace."
    else
        msg="Synced marketplace for ${plugin_name} v${new_version} (version was already bumped)."
    fi

    jq -n --arg msg "$msg" '{"additionalContext": $msg}'
}

main "$@" || true
exit 0
