---
name: describe-pr
description: Generate PR title and description from current branch commits
argument-hint: "[optional: base branch, default main]"
---

# /describe-pr

Generate a pull request title and body from the commits on the current branch. Works for both branch-based PRs and trunk-based summaries of recent work.

## Arguments

<context> $ARGUMENTS </context>

If arguments specify a base branch, use that. Otherwise default to `main`.

## Steps

### 1. Gather Context

Run these commands to understand the change set:

```bash
# Determine base branch
BASE="${ARGUMENTS:-main}"

# Get branch name (if on a branch)
git branch --show-current

# Commits not on base (if on a feature branch)
git log --oneline "${BASE}..HEAD"

# If on main, use the last commit group (since last push or last 5 commits)
git log --oneline -5

# Full diff summary
git diff "${BASE}...HEAD" --stat

# Full diff for content analysis
git diff "${BASE}...HEAD"
```

### 2. Analyze Changes

From the commits and diff, identify:
- **What changed:** files modified, functions added/removed, patterns used
- **Why:** infer intent from commit messages and code changes
- **Type:** feature, fix, refactor, docs, chore
- **Scope:** which module(s) affected

### 3. Generate PR Description

Format using this template:

```markdown
## Summary
<1-3 bullet points explaining what this PR does and why>

## Changes
<Grouped list of concrete changes — not file-by-file, but logical units>

## Testing
<How the changes were tested, or what testing is needed>

## Notes
<Any reviewer context: design decisions, tradeoffs, follow-up work>
```

### 4. Present to User

Show the generated title and body. Then offer options:

1. **Create PR** — run `gh pr create --title "..." --body "..."` (only if on a feature branch, not main)
2. **Copy to clipboard** — output the description for manual use
3. **Refine** — ask what to change

Keep the title under 70 characters. Lead with the type: `feat:`, `fix:`, `refactor:`, etc.
