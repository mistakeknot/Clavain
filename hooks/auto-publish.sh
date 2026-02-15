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

    # Skip any force pushes (--force, -f, --force-with-lease, --no-verify)
    [[ "$cmd" != *"--force"* && "$cmd" != *"-f "* ]] || exit 0

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
    # This covers both the plugin push and the marketplace push in one window.
    local sentinel="/tmp/clavain-autopub.lock"
    if [[ -f "$sentinel" ]]; then
        local sentinel_age now sentinel_mtime
        now=$(date +%s)
        sentinel_mtime=$(stat -c %Y "$sentinel" 2>/dev/null || stat -f %m "$sentinel" 2>/dev/null || echo "0")
        sentinel_age=$((now - sentinel_mtime))
        if [[ "$sentinel_age" -lt 60 ]]; then
            exit 0
        fi
        # Expired — remove and continue
        rm -f "$sentinel"
    fi

    # Find marketplace
    local marketplace_root="${MARKETPLACE_ROOT:-/root/projects/Interverse/infra/marketplace}"
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

    # Write sentinel BEFORE any push to prevent re-trigger
    touch "$sentinel"

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
            sed -i "s/^version = \"$plugin_version\"/version = \"$new_version\"/" "$cwd/pyproject.toml"
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
