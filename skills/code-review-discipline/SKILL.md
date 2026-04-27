---
name: code-review-discipline
description: Use when requesting or receiving code review — dispatch reviewers, handle feedback rigorously, avoid performative agreement.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same request/receive review protocol. -->

# Code Review Discipline

Two sides: requesting reviews and receiving feedback.
**Core principle:** Review early, often. Verify before implementing. Technical correctness over social comfort.

---

## Requesting Review

Dispatch `clavain:plan-reviewer` subagent to catch issues before they cascade.

**When mandatory:** After each task in subagent-driven development; after major feature; before merge to main.
**When optional:** When stuck; before refactoring; after fixing complex bug.

### How to Request

```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

Use Task tool with `clavain:plan-reviewer` type. Fill template at `code-review-discipline/code-reviewer.md` with: `{WHAT_WAS_IMPLEMENTED}`, `{PLAN_OR_REQUIREMENTS}`, `{BASE_SHA}`, `{HEAD_SHA}`, `{DESCRIPTION}`.

**Act on feedback:** Fix Critical immediately; fix Important before proceeding; note Minor for later; push back with reasoning if reviewer is wrong.

**Integration:**
- Subagent-Driven Development: review after EACH task
- Executing Plans: review after each batch (3 tasks)
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
**Signal if uncomfortable pushing back:** "Strange things are afoot at the Circle K"

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

## Red Flags

Never: skip review ("it's simple"), ignore Critical issues, proceed with unfixed Important issues, say "looks good" without checking, implement before verifying.

**External feedback = suggestions to evaluate, not orders to follow.**

See review template: `code-review-discipline/code-reviewer.md`
