---
name: resolve-pr-parallel
description: Resolve all PR comments using parallel processing
argument-hint: "[optional: PR number or current PR]"
---

Resolve all unresolved PR comments using parallel processing.

## Source

Get unresolved comments from the PR:

```bash
gh pr status
gh pr view PR_NUMBER --comments
```

## Workflow

### 1. Analyze

Fetch all unresolved comments. Group by type and dependency.

### 2. Plan

Create a TodoWrite list of all items. Check for dependencies — if one fix requires another to land first, note the order. Output a brief mermaid diagram showing the parallel/sequential flow.

### 3. Implement (PARALLEL)

Spawn a `pr-comment-resolver` agent for each independent item in parallel. Wait for sequential dependencies to complete before spawning dependent items.

### 4. Commit & Resolve

Commit changes. Use `gh api` to resolve PR review threads if applicable. Verify with `gh pr view PR_NUMBER --comments` that all comments are resolved. If not, repeat from step 1.
