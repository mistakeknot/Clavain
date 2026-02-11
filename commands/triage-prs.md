---
name: triage-prs
description: Triage all open PRs — batch by theme, review with parallel agents, generate report, walk through decisions
disable-model-invocation: true
---

# /triage-prs

Triage a repository's open PR backlog. Batches PRs by theme, reviews with parallel fd-* agents, and walks through merge/comment/close decisions.

Complements `/triage` (internal findings) and `/resolve` (fix review feedback).

## Step 1: Gather Context (parallel)

Run these in parallel:

```bash
gh repo view --json name,owner,defaultBranch
gh pr list --state open --limit 50 --json number,title,author,labels,createdAt,updatedAt,headRefName,body
gh issue list --state open --limit 30 --json number,title,labels
gh label list --json name,description
```

Report: "Found N open PRs across the repo."

## Step 2: Batch PRs by Theme

Group PRs into 3-6 batches based on:
- **Labels** (bug, feature, docs, chore, dependencies)
- **Branch prefix** (fix/, feat/, docs/, chore/)
- **Title keywords** if no labels/prefix

Example batches: Bug Fixes, Features, Documentation, Dependencies, Stale (>30 days no activity).

Show the batching and ask for approval before proceeding.

## Step 3: Parallel Agent Review

For each batch, spawn a review agent using the Task tool (all batches in one message for parallelism):

- **Bug fix batches** → fd-correctness agent: check for regression risk, test coverage
- **Feature batches** → fd-architecture agent: check for design alignment, scope creep
- **All batches** → fd-quality agent: naming, conventions, test approach

Each agent receives the PR list with `gh pr diff <number>` for each PR in its batch. Agent output: markdown table with columns: PR#, Summary, Risk, Recommendation (merge/revise/close).

## Step 4: Cross-Reference Issues

For each PR, check:
- `Fixes #X` / `Closes #X` in body → link to issue
- PRs with no linked issue → flag as "needs issue"
- Issues with no PR → flag as "needs implementation"

## Step 5: Generate Triage Report

Compile agent outputs into a single report:

```markdown
# PR Triage Report — <repo> (<date>)

## Summary
- Total open PRs: N
- Ready to merge: N
- Needs revision: N
- Recommend close: N
- Stale (>30 days): N

## By Category

### Bug Fixes (N PRs)
| PR | Title | Author | Age | Risk | Action |
|----|-------|--------|-----|------|--------|
| #123 | Fix auth timeout | @user | 3d | Low | Merge |

### Features (N PRs)
...
```

## Step 6: Walk Through Decisions

For each PR in the report, present the recommendation and ask:

- **Merge** → `gh pr merge <number> --squash`
- **Comment** → compose review comment, post with `gh pr comment <number> --body "..."`
- **Close** → `gh pr close <number> --comment "..."`
- **Skip** → move to next

## Step 7: Apply Labels

Bulk-apply labels based on triage decisions:
```bash
gh pr edit <number> --add-label "triaged,priority-high"
```

## Notes

- Max 50 PRs per triage session — for larger backlogs, use `--limit` or filter by label
- Stale threshold: 30 days with no activity
- Agent review is optional for small backlogs (<5 PRs) — go straight to walk-through
