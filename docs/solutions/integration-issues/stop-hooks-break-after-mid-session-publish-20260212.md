---
module: plugin-infrastructure
date: 2026-02-12
problem_type: integration_issue
component: plugin-cache
symptoms:
  - "Stop hook error: Failed with non-blocking status code: bash: /home/claude-user/.claude/plugins/cache/interagency-marketplace/clavain/0.4.45/hooks/auto-compound.sh: No such file or directory"
  - "Stop hook error: session-handoff.sh: No such file or directory"
  - Stop hooks fail after every tool call for the rest of the session
root_cause: cache_invalidation
resolution_type: fix
severity: medium
tags: [hooks, stop-hooks, plugin-cache, bump-version, publish, symlink, session-lifecycle]
---

# Stop Hooks Break After Mid-Session Plugin Publish

## Problem
When `bump-version.sh` publishes a new plugin version during a Claude Code session, all Stop hooks fail with "No such file or directory" for the rest of the session. The hooks reference the old version's cache path, which no longer exists.

## Environment
- Module: plugin-infrastructure (bump-version.sh, session-start.sh)
- Affected Components: Stop hooks (auto-compound.sh, session-handoff.sh, dotfiles-sync.sh)
- Date: 2026-02-12

## Symptoms
- After running `bump-version.sh` (which pushes to the marketplace), every subsequent tool call shows:
  ```
  Stop hook error: bash: .../clavain/0.4.45/hooks/auto-compound.sh: No such file or directory
  Stop hook error: bash: .../clavain/0.4.45/hooks/session-handoff.sh: No such file or directory
  ```
- The error is non-blocking (session continues) but the hooks don't run
- Persists until the session is restarted

## Root Cause
Three-step chain:

1. **Claude Code bakes hook paths at session start.** When the session starts, it resolves `CLAUDE_PLUGIN_ROOT` to the current cache directory (e.g., `~/.claude/plugins/cache/.../clavain/0.4.45/`) and hardcodes this path for all hook invocations. This path is immutable for the session's lifetime.

2. **Marketplace push triggers cache update.** When `bump-version.sh` pushes to the interagency-marketplace repo, Claude Code detects the new version and downloads it to a new cache directory (e.g., `.../clavain/0.4.46/`).

3. **Claude Code's plugin installer deletes the old cache directory.** The old `0.4.45/` directory is removed, but the session still has `0.4.45/` hardcoded in its hook configuration. All subsequent hook invocations fail.

**Key insight:** This is NOT caused by `bump-version.sh` — the script already had a comment saying it doesn't delete old cache (lines 122-125). The deletion happens at the Claude Code platform level during plugin installation.

## Investigation Steps
1. Checked `bump-version.sh` — confirmed it does NOT delete old cache (comment on lines 122-125)
2. Checked `session-start.sh` — confirmed cleanup only runs on next session start
3. Listed cache directory — only new version present, old version gone
4. Confirmed Claude Code's installer is the one deleting the old directory

## Resolution

### Layer 1: `bump-version.sh` (v0.4.47)
After pushing to the marketplace, creates a compatibility symlink from old→new version:
```
~/.claude/plugins/cache/.../clavain/0.4.48 → 0.4.49
```

### Layer 2: `session-start.sh` (v0.4.49) — multi-hop gap fix
The bump-version symlink only bridges ONE version gap (immediate predecessor). But if a session was loaded from 0.4.45 and three publishes happened (→0.4.47→0.4.48→0.4.49), the 0.4.45 dir is gone with no symlink.

**Fix:** `session-start.sh` now replaces old real directories with symlinks to current version (instead of deleting them). This means any still-running session's Stop hooks resolve through the symlink, regardless of how many versions behind they are. On the *next* session start, the symlinks get cleaned up (they're lightweight).

**Lifecycle:**
1. Session A starts on 0.4.45 (real dir)
2. Publish 0.4.49 — bump-version creates `0.4.48 → 0.4.49` symlink
3. Session B starts on 0.4.49 — session-start replaces 0.4.45 dir with `0.4.45 → 0.4.49` symlink, removes the `0.4.48 → 0.4.49` symlink (it's stale)
4. Session A's Stop hooks fire — path `.../0.4.45/hooks/auto-compound.sh` resolves through symlink to `.../0.4.49/hooks/auto-compound.sh`
5. Session C starts — cleans up the `0.4.45` symlink

**For immediate healing of a broken session:**
```bash
ln -sf <new_version> ~/.claude/plugins/cache/interagency-marketplace/clavain/<old_version>
```

## Prevention
Both layers are automatic. `bump-version.sh` bridges the immediate predecessor, `session-start.sh` bridges all older versions.

## Related
- `scripts/bump-version.sh` lines 109-140 — symlink creation logic
- `hooks/session-start.sh` lines 13-28 — stale symlink cleanup
- Memory: "bump-version.sh auto-clears stale plugin cache on publish" (MEMORY.md) — this note was misleading; updated understanding is that Claude Code's installer does the deletion, not our scripts
