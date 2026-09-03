# fd-isnad-validation-provenance-cox — round 0
## Findings Index
- [P0] q-a-confuses-replay-with-independent-validation — The proposed Opus validator repeats the same criterion chain, so Q-A asks it to discover omissions it is forbidden to judge. (§Open questions the review should attack)
- [P1] pass-is-not-bound-to-an-evidence-tuple — No immutable chain binds a PASS to the exact plan, criteria, commit, environment, and observation that produced it. (§The shape)
- [P1] q-b-is-unidentifiable-from-lane-aggregates — The cited meter cannot distinguish main-thread planning from report-reading, so the pilot cannot answer Q-B as written. (§What makes it enforceable rather than aspirational)
- [P2] output-share-rewards-denominator-inflation — The ≤50% lane-share gate can improve while total tokens, context traffic, latency, retries, and cost all worsen. (§The shape)

## Findings
### q-a-confuses-replay-with-independent-validation
- Severity: P0
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:17,30`; `commands/model-routing.md:66,99,102,114-130`; `scripts/orchestrate.py:582-629,753-818`
- What: Q-A has the wrong premise. The proposed validator is limited to re-running the executor's verify block and judging only the same frozen criteria, yet the question expects Opus to catch something the verify block missed. That check is deterministic replay, not an independent observation or semantic audit; agreement descends from one criterion set and is one claim, not two.
- Evidence: The doctrine records the observed common-mode defect directly: six defective gauges, five caused by the plan's emitted text also being input to a checker written by the same author, and an omission that “passes every downstream check.” Pattern F then gives both executor and validator that same gauge. Concrete failure: the plan omits an authorization invariant and its verify block tests only the happy-path response; executor and Opus validator both return PASS while the shipped endpoint permits an unauthorized mutation. By contrast, the current `orchestrate.py` separates machine replay from a semantic reviewer that inspects the task-scoped diff/repository, probes implied edge cases, and distrusts the executor report. The brainstorm would collapse that independent seat back into replay.
- Suggestion: Run the verify block once as an engine-neutral machine gate. Spend a model validator only on a predeclared independent observation or semantic audit (for example, re-derive tests from Must-Haves and inspect the exact candidate diff without the executor's framing). Rewrite Q-A as: “By failure class, what incremental defects does an independent semantic audit catch beyond deterministic replay, at what cost?”

### pass-is-not-bound-to-an-evidence-tuple
- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:16-19,25`; `scripts/orchestrate.py:582-612,667-745,1174-1189,1412-1456`
- What: The design names reports and frozen criteria but not the provenance tuple that makes a PASS reproducible. A later reader cannot prove which bytes of the plan and criteria were used, which candidate commit was observed, or whether executor and validator ran in equivalent environments.
- Evidence: The current run journal records plan and manifest paths at run start, then records the checkout's current `HEAD` after a task; it does not record content digests, the task's isolated result commit, command/environment fingerprints, or criterion version. The reviewer prompt tells the reviewer to read the criteria from a mutable path at review time. Concrete failure: criteria or the checkout changes between executor completion and validation; the validator returns PASS against newer bytes, while the landing decision attributes that PASS to the executor's older result. The receipt exists, but the chain it claims to attest does not.
- Suggestion: Make PASS attest one immutable tuple: run/item ID, plan and criteria digests, base and result commit, verify-command digest, relevant environment/toolchain fingerprint, validator identity, timestamps, and artifact digests. Reject a validation result whose tuple differs from the executor receipt instead of treating it as corroboration.

### q-b-is-unidentifiable-from-lane-aggregates
- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:23,31`; `/Users/sma/projects/Sylveste/interverse/interstat/scripts/profile.py:38-88,103-123`
- What: Q-B asks whether main-thread context is consumed by planning or by reading executor reports, but `profile.py` aggregates usage only by `(lane, model)`. It has no goal, phase, role, parent dispatch, artifact-read, or turn-purpose dimension.
- Evidence: `collect()` classifies every assistant message as `main` or `subagent` and accumulates tokens into `(lane, model)` counters. The report derives one `ctx_per_msg` average and lane-level output/cost shares. Two pilots with identical aggregates—one with a huge initial planning turn, another with dozens of report-reading turns—are observationally indistinguishable. A pilot can therefore clear the meter while leaving Q-B unanswered, blocking the choice between improving plan compaction and report compaction.
- Suggestion: Before pilots, tag turns or usage records with goal/run ID and role/phase (`plan`, `dispatch`, `receipt-read`, `exception-drilldown`, `landing`, `escalation`) plus parent item. Report absolute input/cache/output tokens and turn counts by those tags; otherwise recast Q-B as a qualitative transcript audit rather than a measured question.

### output-share-rewards-denominator-inflation
- Severity: P2
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:15,23,33`; `/Users/sma/projects/Sylveste/interverse/interstat/scripts/profile.py:103-123,127-138`
- What: Main-thread output share is a lane ratio, not a resource-to-outcome measure. It can fall below 50% because subagents produce more text, even if the main thread does not shrink and the system becomes slower and more expensive.
- Evidence: The gate is `main output / (main output + subagent output)`. `profile.py` also reports total output, API-equivalent cost, cache traffic, and average context, but the brainstorm gates only on the ratio; it does not gate absolute main input/cache tokens, total effective context, validator tokens, attempts, escalations, latency, or delivered outcome quality. Example: keep main output at 100K and add 120K of redundant executor/validator prose; share improves from 100% to 45% while total output more than doubles. This also weakens Q-D's claim that the shape is robust to either pool-accounting regime.
- Suggestion: Treat ≤50% as a diagnostic, not a pass gate. Require non-regression (or explicit budgets) for absolute main-thread context, total input/cache/output and equivalent cost, wall time, retry/escalation counts, and an outcome measure such as post-landing defects; report validator marginal catches by failure class.

## Verdict
The validator role is presently redundant attestation at frontier cost, and Q-A is the open question with the wrong premise: the proposed protocol forbids the independent observation needed to answer it. The pilots also need immutable evidence tuples and phase-level telemetry before their PASS and context-allocation conclusions are attributable.
