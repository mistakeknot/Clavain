---
name: beads-workflow
description: Use when tracking work across sessions with Beads issue tracking — guides the bd CLI workflow for creating, managing, and closing issues with dependencies
---

# Beads Workflow

## Overview

Beads (`bd`) is a git-native issue tracker for persistent task tracking across sessions. Use it for work that spans multiple sessions or has dependencies. For simple single-session tasks, use in-memory `TaskCreate` instead.

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
bd show <id>                      # Detailed view with dependencies
```

### Creating Issues
```bash
bd create --title="..." --type=task|bug|feature --priority=2
```

**Priority scale:** 0-4 or P0-P4 (0=critical, 2=medium, 4=backlog). NOT "high"/"medium"/"low".

### Updating Issues
```bash
bd update <id> --status=in_progress    # Claim work
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
bd update <id> --status=in_progress   # Claim it
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

## Integration

**Pairs with:**
- `file-todos` — Beads for cross-session, file-todos for within-session
- `landing-a-change` — Session close protocol ensures beads are synced
- `triage` command — Categorize and prioritize beads issues
