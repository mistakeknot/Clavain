---
name: resolve-todo-parallel
description: Resolve all pending CLI todos using parallel processing
argument-hint: "[optional: specific todo ID or pattern]"
---

Resolve all pending todos from the `todos/*.md` directory using parallel processing.

## Source

Get unresolved TODOs from `todos/*.md`. If any todo recommends deleting files in `docs/plans/` or `docs/solutions/`, skip it and mark as `wont_fix` — those are intentional pipeline artifacts.

## Workflow

### 1. Analyze

Read all pending todo files. Group by type and dependency.

### 2. Plan

Create a TodoWrite list of all items. Check for dependencies — if one fix requires another to land first, note the order. Output a brief mermaid diagram showing the parallel/sequential flow.

### 3. Implement (PARALLEL)

Spawn a `pr-comment-resolver` agent for each independent item in parallel. Wait for sequential dependencies to complete before spawning dependent items.

**Clodex mode:** If `.claude/autopilot.flag` exists, agents cannot use Edit/Write directly. For code-modifying resolutions:
1. Write a megaprompt describing the fix to a temp file
2. Dispatch through `clavain:clodex` (Codex Delegation mode)
3. If a todo only requires read-only actions (documentation, beads updates), resolve directly

For todos that require complex multi-file edits under clodex mode, flag them for manual resolution rather than attempting automated dispatch.

### 4. Commit

Commit changes. Mark resolved todos as complete by renaming the file status prefix.
