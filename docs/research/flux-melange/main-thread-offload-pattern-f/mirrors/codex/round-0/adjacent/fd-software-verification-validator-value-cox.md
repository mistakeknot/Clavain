# fd-software-verification-validator-value-cox — round 0

## Findings Index

- [P0] frozen-criteria-can-pass-vacuously — The repository does not enforce the complete criteria that Pattern F assumes (§The shape)
- [P1] validator-intervention-is-undefined — Re-running the same command is not an independent fault-detection role (§The shape)
- [P1] pilots-cannot-measure-unique-catches — Existing evidence records cannot distinguish validator information gain from duplicate work (§Open questions the review should attack)
- [P1] strike-channel-corrupts-diagnosis — Gauge, environment, implementation, and validator failures enter the same repair loop (§Escalation)

## Findings

### frozen-criteria-can-pass-vacuously

- Severity: P0
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:15-19`; `skills/writing-plans/SKILL-compact.md:19-31`; `skills/executing-plans/SKILL-compact.md:23-37`; `scripts/orchestrate.py:446-484`
- What: Pattern F's assurance case assumes that `writing-plans` already supplies complete machine-checkable criteria, then confines the validator to those frozen criteria. The actual contract makes `<verify>` optional, makes Must-Haves optional, and reports Must-Have failures without blocking completion. A plan can therefore omit the load-bearing goal property; the executor and validator can agree on an empty or incomplete oracle and falsely validate the architecture across all three pilots.
- Evidence: The plan skill explicitly labels the verify block optional (`skills/writing-plans/SKILL-compact.md:31`) and allows Must-Haves to be omitted (`:19-23`). Execution skips absent verify blocks and does not block on Must-Haves (`skills/executing-plans/SKILL-compact.md:23-37`). The orchestrator treats an empty verify list as success (`scripts/orchestrate.py:475-484`) and permits missing/unparseable plans to yield no task criteria (`:446-466`).
- Suggestion: Add a pre-pilot freeze gate requiring every goal-level Truth/Artifact/Key Link to map to at least one task criterion, with each criterion typed `mechanical` or `semantic`. Reject zero-criterion tasks and make final Must-Have validation blocking. Keep requirement completeness review outside the executor-validator agreement loop.

### validator-intervention-is-undefined

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:17,30`; `scripts/orchestrate.py:582-629`
- What: The proposed Opus validator receives the same plan, reruns the same verify block, and may judge only the same frozen criteria. On deterministic checks this is repetition, not new information; on omitted criteria both roles share the same blindness. Conversely, the current orchestrator already asks its reviewer to inspect the diff, probe implied edge cases, check over-scope, and distrust the executor report. The memo does not say whether the pilots preserve that distinct semantic observation or replace it with duplicate command execution, so Q-A has no stable treatment to evaluate.
- Evidence: Pattern F defines only same-command replay (`docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:17`). The implemented review prompt uses a different evidence channel and fault model: repository/diff inspection, implied edge cases, scope, and report divergence (`scripts/orchestrate.py:590-629`). Those are materially different validators.
- Suggestion: Split validation into (1) deterministic replay by the orchestrator or a cheap runner and (2) an optional semantic validator with a declared distinct observation. Seed one fault the replay must miss—for example, a happy-path `exit 0` check while the implementation clobbers an existing artifact before an error return; the semantic criterion requires preservation on failure and the diff exposes the wrong operation order.

### pilots-cannot-measure-unique-catches

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:28-33`; `commands/work.md:160-169`; `commands/execute-plan.md:41-50`; `scripts/orchestrate.py:1174-1188`
- What: The proposed three pilots have no predeclared counterfactual or unique-catch log. Current evidence can say that criteria passed, how many failed, and how many fix rounds occurred, but not whether the validator uniquely caught a defect, falsely rejected correct work, overturned an executor failure, or merely repeated a machine result. After the pilots, Q-A would still be answered by anecdotes.
- Evidence: `/work` records only author/executor/validator model, aggregate criterion counts, pass, escalation count, and path (`commands/work.md:160-169`); `/execute-plan` records the same shape (`commands/execute-plan.md:41-50`). The orchestrator journal adds status, rounds, a verdict path, and post-task HEAD but no fault class, first-observer, counterfactual result, or adjudicated truth (`scripts/orchestrate.py:1174-1188`).
- Suggestion: For every seeded or naturally found fault, record `{fault_class, criterion_type, executor_result, mechanical_replay_result, validator_result, adjudicated_truth, first_observer, unique_catch, false_reject, latency, cost}`. Pair comparable tasks with no-validator or cheaper-validator arms. Keep Opus only where it produces unique true catches at acceptable false-reject and latency rates; narrow by criterion type otherwise, and remove it if it only duplicates replay.

### strike-channel-corrupts-diagnosis

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:19`; `commands/model-routing.md:108-113`; `scripts/orchestrate.py:667-745,792-847`
- What: PASS/FAIL and the two-strikes rule do not preserve why evidence failed. A flaky command, stale artifact, reviewer timeout, malformed verdict, plan defect, implementation defect, or interpretation defect can all cause another code-fix attempt. In the concrete timeout path, the validator supplies no defect information, yet the executor is told to fix the task and a strike is consumed; correct code can be changed twice and escalated to the most expensive model.
- Evidence: The doctrine says sandbox, auth, rate, and infrastructure failures are not strikes (`commands/model-routing.md:108-113`). `dispatch_review()` nevertheless returns ordinary non-approval on timeout or dispatch error (`scripts/orchestrate.py:716-729`), and `run_task_pipeline()` feeds any non-approval into `build_fix_prompt()` until the shared round budget is exhausted (`:792-847`). Machine-gauge failures and semantic-review failures also share that same counter.
- Suggestion: Replace binary rejection with `{requirement_omission, plan_defect, implementation_defect, gauge_defect, environment_defect, validator_interpretation_defect, infrastructure_error}` plus confidence and evidence. Only implementation/capability failures should consume executor strikes; retry flaky/environment checks under a separate budget, and return plan/gauge defects to the author without modifying code.

## Verdict

The validator is not yet a measurable assurance intervention, and incomplete criteria can make agreement vacuous. Q-A has the wrong binary premise: validator value is criterion- and fault-class-specific, so deterministic replay, semantic review, and requirement-completeness review need separate treatments and keep/narrow/remove thresholds.
