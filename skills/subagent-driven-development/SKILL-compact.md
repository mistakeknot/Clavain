# Subagent-Driven Development (compact)

Execute a plan with a fresh implementer per task, one task review (spec, then
quality) after each, and one independent final review. Run continuously: rule on
conflicts and ledger `Ruling: <decision> — <why> — <cost if wrong>`. Stop only for
destructive, security-sensitive or externally visible actions, or a plan with no
non-guess path forward.

## Setup

- Isolated worktree; `bash scripts/sdd-workspace PLAN_FILE` prints this plan's
  `.clavain/sdd/<plan>/` directory. Ledger `progress.md`, first line
  `# SDD ledger — plan: <path>`; `Task <N>: complete` tasks are done.
- Read the plan, Global Constraints and Spec once. Write the pre-flight scan table
  (shared files/interfaces, per-task self-consistency) and rule on each row.
- Resolve every seat through routing with an explicit model: implementers
  `routine-execution` or `deep-execution`; reviewers `validation`.

## Per task

1. Record BASE. `bash scripts/task-brief PLAN_FILE N`; dispatch
   `implementer-prompt.md` with the brief path, report path, interfaces and
   rulings. Batch small same-shape edits. No pasted history, no parallel
   implementers, no subagents spawned by subagents.
2. Handle DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED; never retry
   unchanged.
3. `bash scripts/review-package PLAN_FILE BASE HEAD`; dispatch
   `task-reviewer-prompt.md` with brief, report, package and Global Constraints.
   Resolve ⚠️ items yourself.
4. Fix loop (spec ❌, Critical, Important): minors deferred to the ledger;
   plan-mandated findings get a ruling first. Rounds 1–3 resume the implementer;
   rounds 4–5 use a fresh, more capable one. Each round ends with a scoped
   `re-review-prompt.md` over FIX_BASE..HEAD and a ledger line. After round 5,
   adjudicate: park with a ruling, or rule on load-bearing findings.
5. Ledger `Task <N>: complete (commits <base7>..<head7>, …)`.

## Finish

Final review package from the merge base; dispatch
`../code-review-discipline/code-reviewer.md` on the most capable independent seat
(blocked if none: ledger it, keep the gate open). One fix dispatch, one scoped
re-review, adjudicate residuals. Report every `Ruling:` line, delete this plan's
workspace, then use `clavain:landing-a-change`.

---

*For the full protocol and rationalizations, read SKILL.md.*
