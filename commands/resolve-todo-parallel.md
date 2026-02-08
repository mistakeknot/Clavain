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

### 4. Commit

Commit changes. Mark resolved todos as complete by renaming the file status prefix.
