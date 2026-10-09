---
name: code-review-discipline
description: Request code review, and assess received feedback from people, PR comments, or agent and cross-lab reviewers; verify findings before implementing and preserve required review gates.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same request/receive review protocol. -->

# Code Review Discipline

Two sides: requesting reviews and receiving feedback.
**Core principle:** Review early, often. Verify before implementing. Technical correctness over social comfort.

---

## Requesting Review

Dispatch `clavain:plan-reviewer` subagent to catch issues before they cascade. Give it precisely crafted context, never your session history.

**When mandatory:** After major feature; before merge to main. (Subagent-driven development runs its own per-task review loop; see Integration.)
**When optional:** When stuck; before refactoring; after fixing complex bug.

### How to Request

```bash
BASE_SHA=$(git merge-base origin/main HEAD)  # or the commit before the work started; never assume HEAD~1
HEAD_SHA=$(git rev-parse HEAD)
```

Use Task tool with `clavain:plan-reviewer` type. Fill template at `code-review-discipline/code-reviewer.md` with: `{WHAT_WAS_IMPLEMENTED}`, `{PLAN_OR_REQUIREMENTS}`, `{BASE_SHA}`, `{HEAD_SHA}`, `{DESCRIPTION}`.

**Act on feedback:** Fix Critical immediately; fix Important before proceeding; note Minor for later; push back with reasoning if reviewer is wrong.

### Re-review After Fixes

A review round after fixes is scoped, not a fresh review, for every reviewer, cross-lab (`--role cross-lab-review`) included. Record the head and base each round saw as `REVIEWED_SHA` and `REVIEWED_BASE`. The next round's brief carries:

- the previous round's open findings, verbatim;
- the fix range only: `git diff REVIEWED_SHA HEAD`, not the whole branch diff (this also shows anything merged in from main);
- the plan or requirements the findings cite.

Ask the reviewer to verdict each finding (ADDRESSED / NOT ADDRESSED, with file:line) and flag breakage the fix range introduced. The reviewer may read callers and dependencies of the changed code. A Critical or Important defect found anywhere still blocks or needs an accountable ruling, wherever it sits; only lesser issues outside the range are non-blocking observations. Use the Inputs, Scope and Output sections of `subagent-driven-development/re-review-prompt.md` as the brief. The scoped round's verdict is the review of record for the new head; earlier rounds cover the rest of the branch.

Scoping narrows what is re-read, not what is required. A `validation` dispatch still runs every acceptance check and evidence gate its contract mandates against the resulting checkout (for example Pattern F's frozen acceptance replay), even where the re-review template says not to re-run the suite.

After a rebase moves `REVIEWED_SHA` off the branch, give the reviewer `git range-diff REVIEWED_BASE..REVIEWED_SHA NEW_BASE..HEAD` plus `git diff REVIEWED_BASE NEW_BASE` limited to the paths the change touches. If the base moved under those paths, or the rebase resolved conflicts or merges, that counts as a rebase that changed the reviewed code: review in full. A rebase that touched none of them is not a reason for a full pass.

Run a full review again only when the fix range rewrites most of the change, a rebase changed the reviewed code, or the previous verdict rejected the design rather than listing fixable findings. Name the reason in the brief.

**Integration:**
- Subagent-Driven Development: per task, its own `task-reviewer-prompt.md` over BASE..HEAD via `review-package`; this template for the final review only
- Executing Plans: one whole-branch review after the last task
- Ad-Hoc: review before merge or when stuck

---

## Receiving Feedback

### Response Pattern

```
1. READ: Complete feedback without reacting
2. UNDERSTAND: Restate requirement in own words (or ask)
3. VERIFY: Check against codebase reality
4. EVALUATE: Technically sound for THIS codebase?
5. RESPOND: Technical acknowledgment or reasoned pushback
6. IMPLEMENT: One item at a time, test each
```

### Forbidden Responses

Never: "You're absolutely right!" / "Great point!" / "Let me implement that now" (before verification).
Instead: restate the technical requirement, ask clarifying questions, push back with technical reasoning, or just start working.

### Unclear Feedback

STOP — do not implement anything. Ask for clarification first. Items may be related; partial understanding → wrong implementation.

### Source-Specific Handling

**Human partner:** Trusted — implement after understanding. No performative agreement. Skip to action.

**External reviewers:** Before implementing:
1. Technically correct for THIS codebase?
2. Breaks existing functionality?
3. Reason for current implementation?
4. Works on all platforms/versions?
5. Does reviewer understand full context?

Push back with technical reasoning if wrong. If conflicts with human partner's decisions, stop and discuss with them first.

**Agent and cross-lab reviewers** (subagents, Codex, Oracle, flux-drive) count as external: verify each finding against the code before acting on it.

**Can't easily verify?** Say so instead of proceeding: "I can't verify this without [X]. Should I investigate, ask, or proceed?"

### YAGNI Check

```bash
# If reviewer suggests "implementing properly":
grep -r "endpoint_name" .   # Check actual usage
# If unused: "This endpoint isn't called. Remove it (YAGNI)?"
```

### Implementation Order (multi-item feedback)

1. Clarify anything unclear FIRST
2. Blocking issues (breaks, security)
3. Simple fixes (typos, imports)
4. Complex fixes (refactoring, logic)
5. Test each fix individually, verify no regressions

### When to Push Back

- Suggestion breaks existing functionality
- Reviewer lacks full context
- Violates YAGNI
- Technically incorrect for this stack
- Legacy/compatibility reasons exist
- Conflicts with human partner's architectural decisions

Push back with technical reasoning, not defensiveness. Reference working tests/code.
**If uncomfortable pushing back out loud:** name that tension, then tell your partner about the issue you've seen.

### Acknowledging Correct Feedback

```
✅ "Fixed. [Brief description of what changed]"
✅ "Good catch - [specific issue]. Fixed in [location]."
✅ Just fix it and show in code

❌ "You're absolutely right!" / "Great point!" / any gratitude expression
```

### Correcting Your Own Pushback

```
✅ "You were right - I checked [X] and it does [Y]. Implementing now."
❌ Long apology or defending why you pushed back
```

### GitHub Thread Replies

Reply inline in the comment thread: `gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies` — not as a top-level PR comment.

---

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "I'll just review the diff myself instead of dispatching a reviewer" | You're the coordinator; reading the diff inline burns the context you need to drive the work. Dispatch a reviewer so only findings come back. |
| "The reviewer needs my whole session history" | Hand it precisely crafted context. History pulls it onto your reasoning instead of the work product. |
| "The reviewer is probably right, I'll just apply it" | Check whether it breaks things before implementing. |
| "I'll apply all the fixes, then test" | One item at a time, test each. |
| "I understood most items; I'll start on those" | Clarify every unclear item first; items may be related. |
| "I can't check this, but it sounds right" | State the limitation and ask for direction. |
| "Pushing back will look defensive" | Technical correctness over comfort; cite the code or test. |

## Red Flags

Never: skip review ("it's simple"), ignore Critical issues, proceed with unfixed Important issues, say "looks good" without checking, implement before verifying.

**External feedback = suggestions to evaluate, not orders to follow.**

See review template: `code-review-discipline/code-reviewer.md`
