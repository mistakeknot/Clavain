# Code Review Discipline (compact)

Two sides: requesting reviews and receiving feedback. Technical correctness over social comfort.

## Requesting Review

**When:** After major features, before merge, and as SDD's final review (SDD reviews each task with its own `task-reviewer-prompt.md`).

1. Get git SHAs: `BASE_SHA=$(git merge-base origin/main HEAD)` (or the commit before the work; never assume `HEAD~1`), `HEAD_SHA=$(git rev-parse HEAD)`
2. Dispatch `clavain:plan-reviewer` subagent with template from `code-reviewer.md`
3. Act on feedback: fix Critical immediately, fix Important before proceeding, note Minor for later
4. Re-review after fixes is scoped, for every reviewer including cross-lab. Record each round's `REVIEWED_SHA` and `REVIEWED_BASE`. Send the previous round's open findings verbatim, `git diff REVIEWED_SHA HEAD` (the fix range, not the whole branch) and the requirements the findings cite. Ask for a verdict per finding plus breakage in the range; the reviewer may read callers and dependencies, and a Critical or Important defect anywhere still blocks. Template: `subagent-driven-development/re-review-prompt.md`. A `validation` dispatch still runs every acceptance check and evidence gate its contract mandates. After a rebase, send `git range-diff REVIEWED_BASE..REVIEWED_SHA NEW_BASE..HEAD` plus `git diff REVIEWED_BASE NEW_BASE` on the touched paths and what they depend on (callers, interfaces, configuration, manifests); if the base moved under any of those or conflicts were resolved, review in full. Full re-review also if the fixes rewrite most of the change or the last verdict rejected the design; name the reason in the brief.

## Receiving Feedback

**Response pattern:** READ → UNDERSTAND (restate requirement) → VERIFY (check codebase) → EVALUATE → RESPOND → IMPLEMENT (one at a time, test each)

**Forbidden:** "You're absolutely right!", "Great point!", any gratitude expression, implementing before verification.

**Instead:** Restate technical requirement, ask clarifying questions, push back with reasoning if wrong, or just start working.

**External feedback** (including agent and cross-lab reviewers): Before implementing, check: technically correct for THIS codebase? Breaks existing? Reason for current approach? Conflicts with partner's decisions? → Stop and discuss. Can't verify? Say so and ask for direction.

**Implementation order:** Clarify unclear items FIRST, then: blocking issues → simple fixes → complex fixes. Test each individually.

**Push back when:** Breaks existing functionality, reviewer lacks context, violates YAGNI, technically incorrect, conflicts with architectural decisions.

**Rationalizations to reject:** reviewing the diff yourself instead of dispatching a reviewer; giving the reviewer your session history; assuming the reviewer is right; batching fixes before testing; starting on the items you understood; proceeding on what you can't verify. If pushing back feels uncomfortable, name the tension and raise the issue anyway.

**Acknowledge correctly:** "Fixed. [description]" or "Good catch - [issue]. Fixed in [location]." Never "Great point!"

---

*For full review template or GitHub thread reply protocol, read SKILL.md and code-reviewer.md.*
