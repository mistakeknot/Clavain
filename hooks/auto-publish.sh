#!/usr/bin/env bash
# PostToolUse hook: auto-publish plugin after git push
#
# Detects `git push` in plugin repos, delegates to `ic publish --auto`
# which handles: patch bump if needed, marketplace sync, cache rebuild,
# installed_plugins.json update, per-plugin sentinel, and never amends
# or force-pushes.
#
# Also syncs the GitHub repo description with current skill/agent/command
# counts to prevent drift (e.g. "16 skills, 4 agents, 45 commands").
#
# Input: PostToolUse JSON on stdin (tool_input.command, cwd)
# Output: JSON with additionalContext on success, empty on skip
# Exit: 0 always (fail-open)

set -euo pipefail

# Manual publish fallback when ic publish is locked.
# Bumps patch version, updates marketplace.json, syncs cache.
_manual_publish() {
    local cwd="$1" plugin_name="$2"
    command -v python3 &>/dev/null || return 1

    local plugin_json="$cwd/.claude-plugin/plugin.json"
    [[ -f "$plugin_json" ]] || return 1

    # Find marketplace.json
    local marketplace=""
    local git_root
    git_root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)"
    # Plugin might be nested in a monorepo — walk up to find marketplace
    local search_dir="$cwd"
    for _ in 1 2 3 4 5; do
        search_dir="$(dirname "$search_dir")"
        [[ -f "$search_dir/core/marketplace/.claude-plugin/marketplace.json" ]] && {
            marketplace="$search_dir/core/marketplace/.claude-plugin/marketplace.json"
            break
        }
    done
    [[ -n "$marketplace" ]] || return 1

    # Bump patch version
    local new_ver
    new_ver="$(python3 -c "
import json
with open('$plugin_json') as f:
    d = json.load(f)
parts = d['version'].split('.')
parts[-1] = str(int(parts[-1]) + 1)
d['version'] = '.'.join(parts)
with open('$plugin_json', 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
print('.'.join(parts))
" 2>/dev/null)" || return 1

    # Commit + push version bump
    git -C "$cwd" add .claude-plugin/plugin.json 2>/dev/null || true
    git -C "$cwd" -c user.name="mistakeknot" -c user.email="mistakeknot@users.noreply.github.com" \
        commit -m "chore: bump to v${new_ver}" >/dev/null 2>&1 || true
    git -C "$cwd" push >/dev/null 2>&1 || true

    # Update marketplace.json
    python3 -c "
import json
with open('$marketplace') as f:
    m = json.load(f)
plugins = m if isinstance(m, list) else m.get('plugins', [])
for p in plugins:
    if p['name'] == '$plugin_name':
        p['version'] = '$new_ver'
        break
with open('$marketplace', 'w') as f:
    json.dump(m, f, indent=2)
    f.write('\n')
" 2>/dev/null || true

    # Sync cache
    local cache_root="$HOME/.claude/plugins/cache/interagency-marketplace"
    if [[ -d "$cache_root" ]]; then
        mkdir -p "$cache_root/$plugin_name/$new_ver"
        rsync -a --delete \
            --exclude='.git' --exclude='.clavain' --exclude='.tldrs' \
            --exclude='node_modules' --exclude='__pycache__' --exclude='.venv' \
            "$cwd/" "$cache_root/$plugin_name/$new_ver/" 2>/dev/null || true
        # Clean old versions
        for old in "$cache_root/$plugin_name"/*/; do
            [[ "$(basename "$old")" != "$new_ver" ]] && rm -rf "$old"
        done
    fi

    echo "${plugin_name} v${new_ver} published (manual fallback)"
}

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
    [[ -n "$plugin_name" ]] || plugin_name="$(basename "$cwd")"

    if [[ -n "$output" && "$output" == *"Published"* ]]; then
        _sync_github_description "$cwd" || true
        jq -n --arg msg "$output" '{"additionalContext": $msg}'
    elif [[ -n "$output" && "$output" == *"Synced"* ]]; then
        _sync_github_description "$cwd" || true
        jq -n --arg msg "$output" '{"additionalContext": $msg}'
    elif [[ -n "$output" && "$output" == *"in progress"* ]]; then
        # ic publish lock stuck — try manual fallback
        local fallback_result
        fallback_result="$(_manual_publish "$cwd" "$plugin_name" 2>&1 || true)"
        if [[ -n "$fallback_result" && "$fallback_result" == *"published"* ]]; then
            _sync_github_description "$cwd" || true
            jq -n --arg msg "$fallback_result" '{"additionalContext": $msg}'
        else
            jq -n --arg msg "Publish stale: ${plugin_name} pushed but not published (ic lock stuck). Run /interpub:sweep to sync." \
                '{"additionalContext": $msg}'
        fi
    fi
}

# Sync GitHub repo description with current skill/agent/command counts.
# Derives repo from git remote; only updates if counts changed.
_sync_github_description() {
    local cwd="$1"
    command -v gh &>/dev/null || return 0

    # Derive GitHub repo (owner/name) from git remote
    local remote_url repo
    remote_url="$(git -C "$cwd" remote get-url origin 2>/dev/null || true)"
    [[ -n "$remote_url" ]] || return 0
    # Handle both SSH and HTTPS remotes
    repo="$(echo "$remote_url" | sed -E 's#^(https?://github\.com/|git@github\.com:)##; s#\.git$##')"
    [[ -n "$repo" && "$repo" == *"/"* ]] || return 0

    # Count from filesystem
    local skills agents commands
    skills="$(find "$cwd/skills" -name "SKILL.md" -mindepth 2 -maxdepth 2 2>/dev/null | wc -l)"
    agents="$(find "$cwd/agents" -name "*.md" -mindepth 2 -maxdepth 2 2>/dev/null | wc -l)"
    commands="$(find "$cwd/commands" -name "*.md" -maxdepth 1 2>/dev/null | wc -l)"
    skills="${skills// /}"; agents="${agents// /}"; commands="${commands// /}"

    # Build new description
    local new_desc="General-purpose engineering discipline plugin for Claude Code. ${skills} skills, ${agents} agents, ${commands} commands."

    # Compare with current GitHub description (cached read, ~200ms)
    local current_desc
    current_desc="$(gh repo view "$repo" --json description -q '.description' 2>/dev/null || true)"
    [[ "$current_desc" != "$new_desc" ]] || return 0

    # Update
    gh repo edit "$repo" --description "$new_desc" 2>/dev/null || true
}

main "$@" || true
exit 0
