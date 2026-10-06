---
module: Clavain hooks (auto-push.sh)
date: 2026-10-06
problem_type: workflow_issue
component: development_workflow
symptoms:
  - "Commits reached a shared team repo's PR branch without anyone running git push"
  - "origin reflog shows 'update by push' at the minute a Claude Code session ended"
root_cause: missing_validation
framework_version: Clavain 0.6.326
resolution_type: code_fix
severity: high
tags: [auto-push, session-end, hooks, shared-repos, git-push, safety]
lastConfirmed: 2026-10-06
provenance: independent
review_count: 0
---

# Troubleshooting: SessionEnd auto-push pushed commits in shared team repos

## Problem
Clavain's SessionEnd hook `hooks/auto-push.sh` pushes whatever branch a session leaves unpushed, in whatever repo the session's working directory belongs to. It had no notion of whose repo it was in, so it pushed to a shared West Monroe repo's PR branch (and would have pushed `main` if that was checked out).

## Environment
- Module: Clavain hooks, `hooks/auto-push.sh` (registered on `SessionEnd` in `hooks/hooks.json`)
- Framework Version: Clavain 0.6.326 (installed cache), identical on GitHub `main`
- Affected Component: session-end git automation
- Date: 2026-10-06

## Symptoms
- A teammate-reviewed PR branch (`WM-Gen-AI-CoE/asset-astrolab`, `astrolab-v2`) received six commits nobody pushed.
- `git reflog show origin/<branch> --date=iso` showed `update by push` at 13:57:22, the minute the desktop app quit and the session ended.

## What Didn't Work

**Looking for repo-level automation first:** no `.git/hooks`, no `core.hooksPath`, no `.git-autosync` marker, no push refspecs; LaunchAgents and `~/.local/bin` sync scripts only fetch or report (their comments say pushing is deliberately excluded).
- **Why it failed:** the push came from the Claude Code harness, not git or launchd.

## Solution

The timestamp match pointed at a session-lifecycle hook. `grep -rl "git push"` across `~/.claude/plugins/cache/*/*/*/hooks` found `auto-push.sh`. The fix is a guard before any push:

```bash
autopush_allowed() {
    local override me others owner
    override=$(git config --get clavain.autopush 2>/dev/null || true)
    [[ "$override" == "true" ]] && return 0
    [[ "$override" == "false" ]] && return 1
    me=$(git config --get clavain.autopushIdentities 2>/dev/null || true)
    [[ -n "$me" ]] || me='mistakeknot|demarch\.local|codex@local|noreply@anthropic\.com|\[bot\]'
    others=$(git log --remotes --format='%ae' 2>/dev/null | sort -u | grep -v -E "$me" | head -1)
    [[ -z "$others" ]] || return 1
    if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
        owner=$(git remote get-url origin 2>/dev/null | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#/.*##')
        [[ "$owner" == "mistakeknot" ]] || return 1
    fi
    return 0
}
autopush_allowed || exit 0
```

- A repo is "solo" when every author email on any remote ref matches `clavain.autopushIdentities` (global git config; the user's GitHub, agent, work, and personal addresses, plus bots).
- Even solo repos never auto-push `main`/`master` unless they live under the personal GitHub account.
- `git config clavain.autopush true|false` overrides per repo.

Dry-run (the hook with the push replaced by an echo) across real repos: shared repo skipped; personal solo repos on `main` pushed; solo repos in a work org skipped on `main`; overrides worked both ways. Of 103 local repos, 55 classify as shared.

Landed: patched the installed cache copy (effective immediately) and pushed branch `mk/autopush-solo-only` on `mistakeknot/Clavain` for the canonical source on zklw.

## Why This Works
"Who else has committed here" is the observable signal that a push is a team decision. Owner alone is wrong in both directions: a work org can hold repos only one person touches, and a personal fork can carry other people's history. The `main` rule keeps the existing policy of never pushing shared repos' trunk without being asked.

## Prevention
- Any hook that writes to a remote (push, publish, release) needs an explicit allow condition, not just a "has unpushed commits" condition.
- Patching the plugin cache is temporary: a plugin update overwrites it. Land the change in the plugin source and release it.
- When something reaches a remote unexpectedly, compare the remote ref's reflog timestamp with session start/end and app quit times before searching git config.

## Related Issues
No related issues documented yet.
