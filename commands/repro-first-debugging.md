---
name: repro-first-debugging
description: Disciplined bug investigation that enforces "reproduce first, then diagnose" — composes debugging agents into a structured workflow
argument-hint: "[bug description or error message]"
---

# Repro-First Debugging

Enforce "reproduce it or it didn't happen" — then systematically diagnose.

## Bug Description

<bug_description> #$ARGUMENTS </bug_description>

**If empty:** Ask the user: "What's the bug? Include: what happened, what was expected, and any error messages."

## Execution Flow

### Phase 1: Reproduce

**Load the `systematic-debugging` skill** for the full debugging methodology.

First, establish a reliable reproduction:

1. **Spawn `bug-reproduction-validator` agent:**
   ```
   Task(bug-reproduction-validator): "Reproduce this bug: <bug_description>. Find minimal steps to trigger it reliably."
   ```

2. **If reproduction succeeds:** Capture the exact steps and continue to Phase 2.

3. **If reproduction fails:** Report to user:
   ```
   Could not reproduce the bug with the information provided.

   Tried: [what was tried]
   Result: [what happened]

   Need more information:
   - Exact steps to trigger?
   - Environment/configuration?
   - Does it happen every time or intermittently?
   ```
   Stop here until user provides more context.

### Phase 2: Find the Cause

With a reliable reproduction established:

1. **Check if it's a regression** — spawn `git-history-analyzer`:
   ```
   Task(git-history-analyzer): "This bug: <description>. When did it start? Find the most likely commit that introduced it. Focus on recent changes to: <affected files>"
   ```

2. **If regression identified:** The suspect commit narrows the search dramatically. Focus debugging on that change.

3. **If not a regression:** Follow the `systematic-debugging` skill's evidence collection process:
   - Form hypotheses
   - Gather evidence for each
   - Eliminate hypotheses based on evidence
   - Test the remaining hypothesis

### Phase 3: Fix and Verify

1. Implement the fix
2. Verify the reproduction steps no longer trigger the bug
3. Add a regression test that would catch this bug
4. Run the full test suite to confirm no side effects

### Phase 4: Document

Produce a structured summary:

```markdown
## Bug Report

**Symptom:** [what the user observed]
**Root Cause:** [what was actually wrong]
**Regression:** [yes/no, if yes: introduced in commit <hash>]
**Fix:** [what was changed]
**Test:** [regression test added]
**Prevention:** [what would prevent similar bugs]
```

If the root cause reveals a systemic issue, suggest capturing it via `/clavain:compound`.

## Key Agents Used

| Agent | Purpose |
|-------|---------|
| `bug-reproduction-validator` | Phase 1 — establish reliable reproduction |
| `git-history-analyzer` | Phase 2 — find suspect commits for regressions |
| `systematic-debugging` skill | Phase 2 — structured evidence collection |
| `repo-research-analyst` | Phase 2 — understand unfamiliar code areas |

## Important

- **Never skip reproduction.** "It just broke" is not a reproduction.
- **Regressions are the easy case.** If git-history-analyzer finds the suspect commit, the fix is usually straightforward.
- **Add a regression test.** Every bug fix should include a test that would have caught it.
