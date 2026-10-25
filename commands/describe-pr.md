---
name: describe-pr
description: Generate PR title and description from current branch commits
argument-hint: "[optional: base branch, default main]"
disable-model-invocation: true
---

# /describe-pr

<context> $ARGUMENTS </context>

Base branch: `$ARGUMENTS` or `main`.

## Step 1: Gather Context

```bash
BASE="${ARGUMENTS:-main}"
git branch --show-current
git log --oneline "${BASE}..HEAD"   # commits not on base (feature branch)
git log --oneline -5                # fallback: last 5 commits (trunk)
git diff "${BASE}...HEAD" --stat
git diff "${BASE}...HEAD"
```

## Step 2: Analyze

From commits and diff identify: what changed, why (infer from messages), type (feature/fix/refactor/docs/chore), scope (which modules).

## Step 3: Generate

```markdown
## Summary
<1-3 bullets: what and why>

## Changes
<Logical groupings — not file-by-file>

## Testing
<How tested or what testing is needed>

## Notes
<Design decisions, tradeoffs, follow-up work>

## Merge Danger
- Door: <one-way: data-migration | external-message | signing-or-production | deploy-timer, plus why / two-way: one clause on how to undo it>
- Blast Radius: <one line, 1-200 characters: what else a bad merge would touch>
- Evidence: <one line: before -> after, taken from a command you ran, a test or a screenshot>
```

### Merge Danger rules

- **One-way** means undoing the merge does not undo its effects: a data
  migration, an external message (email, post, webhook, notification), a
  signing or production path, or a repo with an automatic deploy timer. Name the one
  matching reason (`data-migration`, `external-message`, `signing-or-production`
  or `deploy-timer`) and say why in a few words. If an irreversible effect
  fits none of the four, it is still one-way: give the nearest code and name
  the mismatch in the why. Everything reversible is **two-way**.
- Blast Radius is one line. If a blast-radius report for this change already
  exists, summarise it; do not start one just for this line, since it can
  dispatch a paid model review.
- Evidence is one before/after line you actually observed. If you did not
  observe it, write `none observed` rather than inventing one.
- The block only orders reviewer attention. A two-way door never waives a
  required review, receipt or approval, and a one-way door adds none by itself.

Title: under 70 chars, prefixed with type (`feat:`, `fix:`, `refactor:`, etc.).

## Step 4: Present

Show title and body. Offer:
1. **Create PR** → `gh pr create --title "..." --body "..."` (feature branch only, not main)
2. **Copy** — output for manual use
3. **Refine** — ask what to change
