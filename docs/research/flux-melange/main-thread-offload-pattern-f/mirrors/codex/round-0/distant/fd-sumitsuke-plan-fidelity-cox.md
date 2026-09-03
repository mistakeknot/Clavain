# fd-sumitsuke-plan-fidelity-cox — round 0
## Findings Index
- [P0] shared-checkout-erases-task-datums — Parallel executors and reviewers operate on one changing checkout, so per-task PASS is not evidence that the final assembly fits. (§The shape)
- [P1] plan-has-no-frozen-execution-datum — A fresh executor receives no base revision, plan digest, dirty-state contract, or precondition probe with which to reject a stale plan. (§What makes it enforceable rather than aspirational)
- [P2] verbatim-reports-reimport-execution-context — The proposed verbatim verify-report handoff discards the bounded artifact pattern already present in the orchestrator and rebuilds context in validators and the main thread. (§The shape)
- [P2] q-e-mistakes-amplification-for-novelty — Plan drift already exists in the baseline; Pattern F makes missing-context and asynchronous-state failures more likely and less detectable. (§Open questions the review should attack)

## Findings
### shared-checkout-erases-task-datums
- Severity: P0
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:15-19`; `skills/writing-plans/SKILL.md:148-176,214`; `scripts/orchestrate.py:531-564,753-818,945-957,1096-1118,1521-1529,1595-1597`
- What: The shape assigns each item to a fresh executor and validator but never gives each item an isolated repository datum or requires an integration check after the wave. The live orchestrator dispatches all ready tasks through a `ThreadPoolExecutor` into the same `project_dir`; every executor gets `workspace-write`, and each review diff is “everything changed since this task started.” A sibling task or fix round can therefore enter another task's evidence and can change the checkout after that task has passed.
- Evidence: `writing-plans` recommends `all-parallel` for tasks judged independent, but neither its manifest schema nor `validate_graph` checks file overlap or repository isolation. `dispatch_task` passes the same `-C project_dir` to every worker. `task_diff` is computed from the shared `head0`, not from a task-owned commit, and orchestration ends with `_print_summary` rather than a post-wave integration verify. Concrete failure: task A changes an interface while task B updates its caller; B verifies and is approved while A's later fix round rewrites the interface. Both task receipts can be PASS at their observation times, yet the final caller/interface pair is broken for the person landing the wave.
- Suggestion: Give every concurrent item its own worktree at a declared base revision, require a single task commit, and merge/cherry-pick only after a post-assembly verify block runs on the composed candidate. If shared-checkout execution remains, mechanically reject overlapping declared files and serialize every fix/review cycle; do not label that mode independent execution.

### plan-has-no-frozen-execution-datum
- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:16,25,34`; `skills/writing-plans/SKILL.md:50-76,144-176`; `scripts/orchestrate.py:90-127,1362-1420,1443-1456`
- What: Does a fresh executor have any datum that lets it distinguish “the planned material” from a plausible newer checkout? Today it does not. Exact paths and code snippets locate work, but they do not establish that the symbol, dependency graph, or test meaning is the one the plan author observed.
- Evidence: The plan header records bead, stage, requirements, goal, architecture, and stack; the execution manifest records scheduling data and paths. Neither records `base_revision`, a plan/criteria digest, expected dirty paths, or precondition assertions. `orchestrate()` loads the current manifest and plan and records only their paths in `run_start`; `_git_head()` is sampled later per task solely to construct a retrospective diff. Concrete failure: a dependency update changes a function contract after planning; Sonnet follows the old exact snippet at a still-valid path, adapts just enough to make the obsolete task-local verify pass, commits, and the stale instruction is first discovered at landing.
- Suggestion: Freeze the smallest useful datum before dispatch: repository identity plus base commit, plan and criteria SHA-256 digests, and `dirty = none` or an explicit dirty-path allowlist. Add task-local preconditions for unstable anchors (for example, symbol signature or fixture hash), and abort before the first edit on any mismatch.

### verbatim-reports-reimport-execution-context
- Severity: P2
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:15-17,31`; `scripts/orchestrate.py:298-318,475-512,689-697,930-947`; `skills/executing-plans/SKILL.md:60-64,83-85`
- What: The brainstorm requires the executor to return verify output verbatim, gives that report to the validator, and has the orchestrator read reports. That is an unbounded transcript channel precisely where Pattern F needs a receipt channel.
- Evidence: The current orchestrator already has better bounding primitives: passing verify commands emit one status line, failure evidence is capped to the last 15 lines, executor self-report is capped to 30 lines for review, and dependency context is capped to 50 lines. `executing-plans` tells the main thread to read the summary on PASS and drill into artifacts only on non-PASS. Replacing these with verbatim output makes a verbose test suite or repeated warning log consume validator input and, if surfaced for landing, main-thread context without adding a new decision datum.
- Suggestion: Specify a fixed receipt: plan digest, base and result commit, criterion ID, command digest, exit status, duration, artifact path, and a bounded failure tail. The validator and orchestrator should read only the receipt index by default and open the full log on mismatch or failure.

### q-e-mistakes-amplification-for-novelty
- Severity: P2
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:34`; `commands/work.md:46-67`; `skills/executing-plans/SKILL.md:14-18,129-131`
- What: Q-E's candidate treats stale-plan execution as a failure introduced by Pattern F. The baseline already loads plans against mutable repositories and relies on a qualitative critical review; no baseline contract binds a plan to a revision. Offload changes the probability and detectability of that old failure, while introducing a different boundary: facts known only to the accumulated main-thread context are no longer available to repair or question the plan.
- Evidence: `/work` reads the plan and then runs `git pull`; `executing-plans` asks the current agent to review the plan critically. Neither establishes a frozen base. A fresh executor is less able to compensate from conversational history, but the stale-state hazard itself predates offload. The novel failure class is context-discontinuity: an omitted invariant appears nowhere in the plan and therefore cannot trigger the executor's stop condition.
- Suggestion: Rewrite Q-E as a comparative test: “Which failure classes become more frequent or less detectable under fresh-context offload than under same-thread execution?” Measure stale-state detection separately from omitted-context questions, shared-checkout interference, and post-assembly regressions.

## Verdict
Pattern F is not execution-grade while concurrent tasks share a mutable checkout and plans carry no frozen datum. Q-E's candidate is an existing stale-plan risk made more visible by offload; the genuinely new risk is silent loss of contextual invariants at the handoff boundary.
