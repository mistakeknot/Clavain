---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same workspace, per-task dispatch, review and fix-loop protocol. -->

# Subagent-Driven Development

Execute a plan by dispatching a fresh implementer per task, one task review
(spec compliance, then quality) after each, and one independent whole-branch
review at the end. You coordinate; subagents write and review the code.

**Core principle:** fresh subagent per task + task review + final review, with a
ledger that survives compaction.

**Continuous execution.** Do not pause between tasks for check-ins or progress
summaries. Decide conflicts, ambiguities and plan defects yourself: the spec is
the binding authority, the plan is its argument. Ledger each decision as
`Ruling: <decision> — <why> — <cost if wrong>` and keep going. Four things stop
you: an irreversible or destructive operation, a security-sensitive action, an
external side effect that norms say you ask about (merge, shared push, publish),
or a plan so broken that every path forward is a guess.

## When to Use

Have a plan with mostly independent tasks and a subagent tool? Use this skill.
Tightly coupled tasks: brainstorm or work manually. **vs. executing-plans
(Native):** a fresh context and a review gate per task instead of one context and
one final review. It costs more seats but survives long plans. Both share the
same workspace and ledger, so a plan can change executor mid-flight.

## Setup

- Work in an isolated worktree; never start on main/master without explicit
  consent.
- `bash scripts/sdd-workspace PLAN_FILE` prints this plan's git-ignored
  directory, `<repo-root>/.clavain/sdd/<plan-basename>/`, holding the ledger,
  briefs, reports and review packages. Another plan's directory is never yours.
- The ledger is `<workspace>/progress.md`, first line
  `# SDD ledger — plan: <plan file path>`. If it names your plan, tasks with a
  `Task <N>: complete` line are done; resume at the first without one, or at the
  next fix round of a task mid-loop. After compaction trust the ledger and
  `git log` over recollection. A ledger naming another plan is not yours.
- Read the plan once, its Global Constraints and its `Spec:`. With no reachable
  spec, ledger that rulings are provisional. Track tasks in the project tracker.
- **Pre-flight scan** before Task 1: write a ledger table with one row per pair
  of tasks sharing a file or interface (what one produces against what the other
  consumes) and one row per task (its tests against its code, its files against
  later tasks). Include anything the plan mandates that the review rubric calls
  a defect. Rule on every finding beside its row. "Clean" without rows is not a
  scan.

## Roles and models

Resolve every seat through Clavain routing (`docs/canon/reasoning-routing.md`)
and dispatch with an explicit model; an omitted model silently inherits the
session's. Implementers: `routine-execution` when the brief fully specifies the
change, `deep-execution` when it needs design judgment. Task reviewers and
re-reviewers: `validation` with `--producer-identity`. Fix rounds 4–5 and the
final review take the more capable seat. Turn count beats token price: the
cheapest model often costs more on multi-step work.

Implementers and reviewers never dispatch subagents; every review seat already
exists. Never run implementers in parallel. Hand artifacts over as files: what
you paste stays in your context for the rest of the session.

## Per task

1. **Dispatch.** Record `BASE=$(git rev-parse HEAD)`. `bash scripts/task-brief
   PLAN_FILE N` prints the brief path. Dispatch
   [implementer-prompt.md](implementer-prompt.md) with one line on where the task
   fits, the brief path ("read first; its values are verbatim"), interfaces and
   rulings from earlier tasks, your resolution of any ambiguity, and the report
   path (`task-N-report.md` beside the brief). Never paste prior-task history or
   make the implementer read the whole plan. **Batch** several small same-shape
   edits into one brief, one dispatch and one review.
2. **Handle the status.** DONE: review. DONE_WITH_CONCERNS: address correctness
   or scope concerns first. NEEDS_CONTEXT: supply it and re-dispatch. BLOCKED:
   add context, move to a more capable seat, split the task, or rule on the plan
   defect. Never retry unchanged. Answer questions fully before work proceeds.
3. **Review.** `bash scripts/review-package PLAN_FILE BASE HEAD` (never
   `HEAD~1`) prints a package path. Dispatch
   [task-reviewer-prompt.md](task-reviewer-prompt.md) with the brief, report and
   package paths and the plan's Global Constraints copied verbatim. Never tell a
   reviewer what not to flag. Resolve each "⚠️ Cannot verify from diff" item
   yourself; a real gap is a spec failure.
4. **Fix loop.** Triggered by spec ❌, any Critical or Important finding, or a
   confirmed ⚠️ gap. Minors go to the ledger as
   `Task <N>: minor (deferred): <one-liner>`. A plan-mandated finding gets a
   ledgered ruling before any fix. A round is one fix dispatch plus one scoped
   re-review, five rounds at most:
   - Rounds 1–3 resume the original implementer with the findings verbatim (or
     dispatch a fresh one with the brief, report and findings).
   - Rounds 4–5 dispatch a fresh implementer on a more capable seat: "A prior
     implementer attempted this task [N] times; you own it now."
   - The fix report must name the covering tests, command and output. Then run
     `review-package PLAN_FILE FIX_BASE HEAD` and dispatch
     [re-review-prompt.md](re-review-prompt.md). Out-of-scope observations
     become deferred minors.
   - Ledger `Task <N>: fix round <R>/5 (<X> addressed, <Y> open — <one-liners>;
     commits <a7>..<b7>)`. Never fix code yourself.
   - **Breaker:** after round 5, adjudicate each open finding. Wrong, contestable
     or real-but-isolated: `Task <N>: parked — <finding> — Ruling: <why>`.
     Load-bearing: rule on the smallest unblocking change and carry it into the
     next dispatch. Adjudicate only at the cap.
5. **Complete.** Ledger `Task <N>: complete (commits <base7>..<head7>, review
   clean)` or `…, <K> parked)`, then close the tracker item. Never advance with
   an open Critical or Important finding that is neither fixed nor parked.

## Final review and finish

`bash scripts/review-package PLAN_FILE $(git merge-base origin/main HEAD) HEAD`,
then dispatch `clavain:code-review-discipline`'s
[code-reviewer.md](../code-review-discipline/code-reviewer.md) on the most
capable independent seat with the package, plan, spec, Review Focus and the
ledger's deferred-minor, parked and `Ruling:` lines. If no independent reviewer
can run, ledger `Final review: blocked (<reason>)` and keep the gate open.
Findings get ONE fix dispatch with the whole list, one scoped re-review, and
breaker-style adjudication of residuals; there is no second wave. Each item on
the reviewer's "Declined to judge" list is a ruling you ledger.

Report every ledger `Ruling:` line with its cost if wrong under "Rulings I made";
a ruling that dies with the workspace was made in secret. Once the review is
clean and fixes are committed, delete this plan's workspace (not its siblings)
and use `clavain:landing-a-change`.

## Red Flags

| Excuse | Reality |
|--------|---------|
| "Close enough on spec" | Spec gaps mean not done. Fix, or reach the cap and adjudicate. |
| "I'll fix it myself" | Controller fixes pollute your context and skip review. |
| "One more round will converge" | Past the cap the failure is structural. Adjudicate. |
| "This finding is obviously wrong" | Adjudicate only at the cap, and ledger it. |
| "The fix was small, skip re-review" | Unreviewed fixes are how regressions land. |
| "The ledger is overhead" | Controllers without one re-dispatched finished tasks after compaction. |
| "The implementer's own reviewer is extra assurance" | A duplicate seat; flag it as a defect. |

## Integration

- **clavain:writing-plans** creates the plan this skill executes
- **clavain:executing-plans** runs the same plan natively in one context
- **clavain:code-review-discipline** supplies the final review template
- **intertest:test-driven-development** governs each implementer's work
- **clavain:landing-a-change** finishes the branch
- **clavain:interserve** routes Codex implementers while Claude orchestrates
