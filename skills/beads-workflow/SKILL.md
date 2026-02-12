---
name: beads-workflow
description: Use when tracking work across sessions with Beads issue tracking — guides the bd CLI workflow for creating, managing, and closing issues with dependencies
---

# Beads Workflow

## Overview

Beads (`bd`) is a git-native issue tracker for persistent task tracking across sessions. Issues stored as JSONL in `.beads/`, synced via git, with hash-based IDs that prevent merge conflicts. Use it for work that spans multiple sessions or has dependencies. For simple single-session tasks, use in-memory `TaskCreate` instead.

**Backend:** Dolt (version-controlled SQL with cell-level merge) is the default. `.beads/dolt/` contains the database (gitignored). `.beads/issues.jsonl` is the git-portable sync layer. If Dolt issues surface, rebuild from JSONL: `bd doctor --fix --source=jsonl`.

## When to Use Beads vs TaskCreate

| Use Beads (`bd`) when... | Use TaskCreate when... |
|--------------------------|------------------------|
| Work spans multiple sessions | Single session task |
| Tasks have dependencies | Independent tasks |
| Need persistent tracking | Temporary tracking is fine |
| Collaborating across agents | Solo execution |
| Want git-synced state | Ephemeral state is fine |

## Essential Commands

### Finding Work
```bash
bd ready                          # Show issues ready to work (no blockers)
bd list --status=open             # All open issues
bd list --status=in_progress      # Active work
bd blocked                        # Show all blocked issues
bd show <id>                      # Detailed view with dependencies
```

### Creating Issues
```bash
bd create --title="..." --type=task|bug|feature --priority=2
```

**Priority scale:** 0-4 or P0-P4 (0=critical, 2=medium, 4=backlog). NOT "high"/"medium"/"low".

### Hierarchical Issues

Use dot notation for epic → task → sub-task hierarchies:
```bash
bd create --title="Auth overhaul" --type=feature --priority=1
# Creates bd-a3f8

bd create --title="JWT middleware" --parent=bd-a3f8 --priority=2
# Creates bd-a3f8.1

bd create --title="Token refresh logic" --parent=bd-a3f8.1 --priority=2
# Creates bd-a3f8.1.1
```

### Updating Issues
```bash
bd update <id> --status=in_progress    # Claim work
bd update <id> --claim                 # Atomically assign + mark in-progress
bd update <id> --assignee=username     # Assign
bd close <id>                          # Mark complete
bd close <id1> <id2> ...              # Close multiple at once
bd close <id> --reason="explanation"   # Close with reason
```

### Dependencies
```bash
bd dep add <issue> <depends-on>    # issue depends on depends-on
bd blocked                         # Show all blocked issues
```

### Sync
```bash
bd sync                  # Sync with git remote
bd sync --status         # Check sync status
```

## Workflow Modes

### Stealth Mode
Local-only tracking, nothing committed to the main repo:
```bash
bd init --stealth
```

Use for: experimental planning, personal task tracking, throwaway exploration.

### Contributor Mode
Routes planning to a separate repo, keeping experimental work out of PRs:
```bash
bd init --contributor
```

Planning state stored in `~/.beads-planning` instead of the project's `.beads/`.

### Maintainer Mode
Full read-write access. Auto-detected via SSH or authenticated HTTPS:
```bash
git config beads.role maintainer    # Force maintainer mode
```

## Beads Viewer

`bv` provides AI-friendly analytics on your task graph:
```bash
bv                    # Open viewer with PageRank, critical path, parallel tracks
```

Surfaces: task recommendations, execution order, blocking chains, parallel execution opportunities. Use before dispatching parallel agents to identify independent work streams.

## Memory Compaction

Closed tasks are semantically summarized to preserve context while reducing token cost. Beads handles this automatically — old completed tasks are compacted so agents get the gist without reading full histories.

## Daily Maintenance

Beads databases grow over time. Keep them healthy:

- **`bd doctor --fix --yes`** — runs daily via systemd timer; fixes common issues automatically
- **`bd admin cleanup --older-than 30 --force`** — prunes closed issues older than 30 days (always recoverable from git history)
- **`bd sync`** — commits hygiene changes to git
- **Manual upgrade**: Run `bd upgrade` periodically to get latest fixes (not automated — requires binary install)

If you see "issues.jsonl too large" or agents failing to parse beads, run `bd admin cleanup --older-than 7 --force` for aggressive cleanup.

The daily hygiene runs at 6:15 AM Pacific across all projects in `/root/projects/`. Check logs: `journalctl -u clavain-beads-hygiene.service --since today`

## Session Close Protocol

**CRITICAL**: Before saying "done" or "complete", run this checklist:

```bash
git status              # Check what changed
git add <files>         # Stage code changes
bd sync                 # Commit beads changes
git commit -m "..."     # Commit code
bd sync                 # Commit any new beads changes
git push                # Push to remote
```

**NEVER skip this.** Work is not done until pushed.

## Common Workflows

**Starting work:**
```bash
bd ready                              # Find available work
bd show <id>                          # Review details
bd update <id> --claim                # Atomically claim it
```

**Completing work:**
```bash
bd close <id1> <id2> ...    # Close completed issues
bd sync                     # Push to remote
```

**Creating dependent work:**
```bash
bd create --title="Implement feature X" --type=feature --priority=2
bd create --title="Write tests for X" --type=task --priority=2
bd dep add <tests-id> <feature-id>    # Tests depend on feature
```

**After batch creation (reviews, audits, planning):**

Whenever you create 5+ beads in a session — especially from reviews, audits, or brainstorming — run a consolidation pass before moving on:

```bash
bd list --status=open    # Review the full backlog
```

Look for:
1. **Same-file edits** — Multiple beads that touch the same file can often merge into one with combined acceptance criteria
2. **Parent-child absorption** — Small beads whose scope is entirely contained within a larger bead should become acceptance criteria on the parent, then close with `--reason="absorbed into <parent-id>"`
3. **Duplicate intent** — Beads phrased differently but targeting the same outcome — close the weaker one
4. **Missing dependencies** — Beads that implicitly depend on each other (e.g., a schema change that a downstream consumer needs) should have explicit `bd dep add`
5. **Missing descriptions** — Every bead should have a description with concrete acceptance criteria, not just a title

```bash
# Absorb child into parent
bd update <parent-id> --description="...add child's criteria..."
bd close <child-id> --force --reason="absorbed into <parent-id>"

# Add missing dependency
bd dep add <downstream-id> <upstream-id>
```

This typically reduces batch-created backlogs by 30-40% and prevents fragmented work.

## Integration

**Pairs with:**
- `file-todos` — Beads for cross-session, file-todos for within-session
- `landing-a-change` — Session close protocol ensures beads are synced
- `triage` command — Categorize and prioritize beads issues
- `dispatching-parallel-agents` — Use `bv` to identify independent work streams before dispatching
