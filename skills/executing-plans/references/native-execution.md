# Native execution

Native execution (Step 2B, the default) implements every task in this session:
no implementer or reviewer per task, one independent review of the whole branch
at the end. The brief is the spec, the ledger is your memory, test-first work is
the per-task gate and the final reviewer is the second pair of eyes. A fully
specified plan runs well on a mid-tier session model. Prefer
`clavain:subagent-driven-development` when a review gate per task is wanted or
the plan is long enough that later tasks would run on a compacted context.

## Setup

- Run `bash ../subagent-driven-development/scripts/sdd-workspace PLAN_FILE`
  (paths relative to this skill). It prints this plan's git-ignored directory,
  `<repo-root>/.clavain/sdd/<plan-basename>/`, which holds the ledger, briefs,
  test logs and review packages. Another plan's directory is never yours. The
  workspace and ledger format are shared with subagent-driven-development, so a
  plan can change executors mid-flight.
- The ledger is `<workspace>/progress.md`; its first line is
  `# SDD ledger — plan: <plan file path>`. If that line names your plan, every
  `Task <N>: complete` task is done: trust the ledger and `git log` over your own
  recollection after compaction and resume at the first unrecorded task. A ledger
  naming a different plan belongs to that plan; leave it and start fresh.
  `git clean -fdx` destroys the workspace; recover from `git log`.
- Read the plan once, its Global Constraints and its Spec. Plan conflicts resolve
  against the spec; with no reachable spec, ledger that rulings are provisional.
- Pre-flight scan: for each task that consumes what an earlier task produces
  (see the Interfaces blocks), write one ledger row comparing the two and rule
  on any conflict. A plan whose tasks share nothing gets
  `Pre-flight: no shared interfaces`.

## Task loop

1. `bash scripts/task-start PLAN_FILE N` prints the brief path and BASE in one
   call. Read the brief every time; memory is a summary, the brief has the
   values. Mark the task in progress in the project tracker.
2. Work the steps in order under `intertest:test-driven-development`. Run every
   command and compare its output with the plan's `Expected:` line. Code wrong:
   use `intertest:systematic-debugging`; never patch the symptom. Plan wrong:
   rule on the smallest change that satisfies the spec and ledger
   `Task <N>: Ruling: <finding> — <decision and why> — <cost if wrong>`. Commit as
   the plan says; the review range is BASE..HEAD, never `HEAD~1`.
3. Completion contract, with evidence from this session: every named test exists
   and ran, the final run passed, every `Expected:` line and `<verify>` block was
   checked against real output, and every deviation has a ledgered ruling.
   `intertest:verification-before-completion` governs the claim.
4. `bash scripts/task-done PLAN_FILE N BASE -- <test command>` runs the full
   suite (or the plan's declared gate), keeps the full log in the workspace and, only on success, appends
   `Task <N>: complete (commits <base7>..<head7>, tests: <command> → <result>)`.
   A failing run records nothing.

Redirect long output to the workspace and read its tail. Append ledger lines in
the same call as the work they record.

## Final review

Run `bash ../subagent-driven-development/scripts/review-package PLAN_FILE MERGE_BASE HEAD`
(MERGE_BASE is Task 1's recorded BASE, else the merge base with the default
branch). Resolve
the review role through routing with `--producer-identity` and dispatch it with
`code-review-discipline/code-reviewer.md`, the package path, plan and spec paths,
the plan's Review Focus verbatim and a pointer to the ledger's `Ruling:` lines.
Your own read of the diff does not replace it. If no independent reviewer can
run, ledger `Final review: blocked (<reason>)` and keep the gate open.

Re-grade findings by effect: what a reasonable user gets if it ships, not whether
the spec named the input. Each item on the reviewer's "Declined to judge" list is
a ruling you ledger. Then:

- **Critical and Important:** fix them in one pass. Each fix gets a test that
  fails first, then passes, then a green suite; ledger
  `Final: fixed <finding> — <test> RED→GREEN, suite <N>/<N>`. A finding you
  leave is a `Final: Ruling:`. Then dispatch one scoped re-review of the fix
  range with `../subagent-driven-development/re-review-prompt.md` on the same
  seat, passing the plan as the brief, the ledger's `Final:` lines as the
  report and the final Critical/Important findings; it may not be you. No further rounds: its open findings become
  `Final: Ruling:` lines.
- **Minor:** ledger `Final: minor (deferred): <one-liner>`; do not fix it.

## Finish

List every `Ruling:` line (with its cost if wrong) and every deferred minor in
the final report. Once every Critical and Important finding is fixed and
re-reviewed or ruled on, and the fixes are committed, delete
this plan's workspace directory, then use `clavain:landing-a-change`.

| Excuse | Reality |
|--------|---------|
| "I remember what Task N says" | You remember a summary. Read the brief. |
| "The plan is wrong, I'll just do the right thing" | Do it and ledger the ruling; an unledgered deviation is a secret decision. |
| "I'll write the ledger after a few tasks" | Compaction does not wait. One line per task, with its commit. |
| "I read my diff carefully; the final review is redundant" | Same author, same blind spots. |
| "The reviewer said Minor" | The label may grade the spec's silence. Grade the effect. |
