---
module: System
date: 2026-02-10
problem_type: workflow_issue
component: development_workflow
symptoms:
  - "git commit fails with 'Error: Failed to flush bd changes to JSONL'"
  - "bd sync --flush-only returns 'permission denied' on issues.jsonl"
  - ".beads/issues.jsonl has -rw------- mask despite POSIX ACL entries"
root_cause: missing_permission
resolution_type: workflow_improvement
severity: medium
tags: [beads, git-hooks, pre-commit, acl, permissions, claude-user]
---

# Troubleshooting: Beads Pre-Commit Hook Blocks Git Commits Due to JSONL Permission Mask

## Problem
When running as `claude-user` (via the `cc` function), `git commit` fails because the beads pre-commit hook cannot read `.beads/issues.jsonl`. The file has POSIX ACL entries for claude-user but the ACL mask is `---`, which overrides the user-specific entry.

## Environment
- Module: System-wide (beads + git hooks)
- Affected Component: `.git/hooks/pre-commit` (beads flush hook)
- Date: 2026-02-10

## Symptoms
- `git commit` exits with: `Error: Failed to flush bd changes to JSONL`
- `bd sync --flush-only` returns: `open /root/projects/Clavain/.beads/issues.jsonl: permission denied`
- `ls -la .beads/issues.jsonl` shows `-rw-------+` — the `+` indicates ACL entries exist, but the mask blocks them
- `getfacl .beads/issues.jsonl` shows `mask::---` overriding `user:claude-user:rw-`

## What Didn't Work

**Attempted Solution 1:** Directory-level default ACLs (`setfacl -R -m d:u:claude-user:rwX .beads/`)
- **Why it failed:** Default ACLs only apply to *newly created* files. SQLite WAL mode creates `.db-shm` and `.db-wal` with restrictive permissions, and the beads daemon creates/rewrites JSONL files with root's umask, which sets the mask to `---`.

**Attempted Solution 2:** `--no-db` mode for beads (`bd --no-db sync --flush-only`)
- **Why it failed:** Still needs to read `issues.jsonl`, which has the same permission problem.

## Solution

Two approaches, depending on urgency:

**Immediate workaround** — skip the hook for the current commit:
```bash
git commit --no-verify -m "commit message"
```
This is safe because the beads flush hook is a convenience (ensures JSONL is up-to-date), not a safety check.

**Proper fix** — fix the ACL mask on the specific files:
```bash
# Run as root:
setfacl -m u:claude-user:rw,m::rw /root/projects/Clavain/.beads/issues.jsonl
setfacl -m u:claude-user:rw,m::rw /root/projects/Clavain/.beads/interactions.jsonl
setfacl -m u:claude-user:rw,m::rw /root/projects/Clavain/.beads/beads.db-shm
setfacl -m u:claude-user:rw,m::rw /root/projects/Clavain/.beads/beads.db-wal
```

The key is `m::rw` — this sets the ACL **mask** to allow read/write, which is required for named user entries to take effect.

## Why This Works

POSIX ACLs use a **mask entry** that acts as an upper bound on permissions granted to named users and groups. When SQLite or the beads daemon creates a file with mode `0600`, the ACL mask is set to `---` (no permissions for anyone except owner). Even though `setfacl -R -m u:claude-user:rwX` adds an ACL entry, the mask blocks it from being effective.

The `m::rw` parameter explicitly sets the mask to `rw-`, which allows the named user entry to grant its full permissions.

This is a recurring pattern with any file created by root processes that use restrictive umasks — the directory default ACL sets the *user entry* correctly but the *mask* gets constrained by the creating process's umask.

## Prevention

- After any beads daemon restart or database operation, re-run the `setfacl` commands with explicit mask settings
- Consider adding a maintenance script that periodically fixes `.beads/` file permissions
- The `setfacl` commands in CLAUDE.md's "Required ACLs" section should include explicit `m::rw` for `.beads/` files
- When using `--no-verify` as a workaround, remember to manually run `bd sync --flush-only` from root later

## Related Issues

- See also: [settings-heredoc-permission-bloat-20260210.md](./settings-heredoc-permission-bloat-20260210.md) — another claude-user permission issue
