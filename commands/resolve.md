---
name: resolve
description: Resolve findings from any source — auto-detects TODOs, PR comments, or todo files, then resolves in parallel
argument-hint: "[optional: 'todos', 'pr', 'code', PR number, or specific pattern]"
---

Resolve findings from any source using parallel processing. Auto-detects the source or accepts an explicit hint.

## Source Detection

<resolve_target> #$ARGUMENTS </resolve_target>

**Auto-detect** (no arguments or ambiguous input):

```bash
# Check for todo files first (most specific)
TODO_FILES=$(ls todos/*.md 2>/dev/null | head -1)

# Check for PR context
PR_NUMBER=$(gh pr status --json number -q '.currentBranch.number' 2>/dev/null || echo "")

# Check for TODO comments in code
TODO_COMMENTS=$(grep -r "TODO" --include="*.go" --include="*.py" --include="*.ts" --include="*.sh" --include="*.rs" -l . 2>/dev/null | head -1)
```

| Priority | Condition | Source |
|----------|-----------|--------|
| 1 | Argument is a number or `pr` | PR comments via `gh pr view` |
| 2 | Argument is `todos` or `todos/*.md` exist | Todo files in `todos/` directory |
| 3 | Argument is `code` | TODO comments in codebase via grep |
| 4 | No argument, todo files exist | Todo files (default) |
| 5 | No argument, on PR branch | PR comments |
| 6 | Fallback | TODO comments in code |

### Source: Todo Files
```bash
# Read all pending todo files
ls todos/*.md
```
If any todo recommends deleting files in `docs/plans/` or `docs/solutions/`, skip it and mark as `wont_fix` — those are intentional pipeline artifacts.

### Source: PR Comments
```bash
gh pr status
gh pr view PR_NUMBER --comments
```

### Source: Code TODOs
```bash
grep -r "TODO" --include="*.go" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.sh" --include="*.rs" .
```

## Workflow

### 1. Analyze

Gather all findings from the detected source. Group by type and dependency.

### 2. Plan

Create a TodoWrite list of all items. Check for dependencies — if one fix requires another to land first, note the order. Output a brief mermaid diagram showing the parallel/sequential flow.

### 3. Implement (PARALLEL)

Spawn a `pr-comment-resolver` agent for each independent item in parallel. Wait for sequential dependencies to complete before spawning dependent items.

**Clodex mode:** If `.claude/autopilot.flag` exists, agents cannot use Edit/Write directly. For code-modifying resolutions:
1. Write a megaprompt describing the fix to a temp file
2. Dispatch through `clavain:clodex` (Codex Delegation mode)
3. If a finding only requires read-only actions (documentation, beads updates), resolve directly

For findings that require complex multi-file edits under clodex mode, flag them for manual resolution rather than attempting automated dispatch.

### 4. Commit

Commit changes. For each source type:
- **Todo files**: Mark resolved todos as complete by renaming the file status prefix
- **PR comments**: Use `gh api` to resolve PR review threads. Verify with `gh pr view --comments`. If unresolved remain, repeat from step 1
- **Code TODOs**: Verify the TODO comment was removed. Commit with conventional message
