# fd-observability-token-gate-cox — round 0

## Findings Index

- [P0] output-share-rewards-denominator-inflation — The sole gate can improve while total context, cost, latency, and failures worsen (§What makes it enforceable rather than aspirational)
- [P1] codex-lane-is-outside-the-meter — The profiler cannot see a named execution lane in Pattern F (§What makes it enforceable rather than aspirational)
- [P1] q-b-is-unanswerable-with-current-attribution — Session-level lane totals cannot separate planning from report ingestion (§Open questions the review should attack)
- [P2] pilot-scorecard-lacks-outcome-and-labor-guards — The three pilots are not specified as comparable resource-to-outcome experiments (§Open questions the review should attack)
- [P2] q-d-assumes-topology-robustness — Different accounting regimes can change the preferred validation and execution topology (§Open questions the review should attack)

## Findings

### output-share-rewards-denominator-inflation

- Severity: P0
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:7,15,21-23`; `/Users/sma/projects/Sylveste/interverse/interstat/scripts/profile.py:103-123,127-138`
- What: The gate optimizes `main output / (main output + subagent output)`, although the measured problem is 220–320K tokens of context resent on main-thread turns. The main thread can remain at the same context cost while emitting terse prompts, or the denominator can be inflated by verbose executor reports and extra validators. All pilots can pass ≤50% while total context traffic, API-equivalent cost, wall time, retries, and landable quality get worse.
- Evidence: `profile.py` computes `main_output_share` solely from lane output tokens (`:103-123`). It separately computes cache reads, cache creation, average context, and total cost (`:107-122,127-138`), but Pattern F promotes only generated-token share to the gate. Adding 100K unnecessary validator output to a goal with 90K main and 20K executor output changes the gate from 81.8% to 42.9% without saving one main token.
- Suggestion: Keep share as a diagnostic, not a gate. Gate on a scorecard per accepted item: main effective-context tokens, total input/output/cache traffic, API-equivalent cost under declared pricing, wall/queue time, attempts, human touches, and an adjudicated quality outcome. Require no regression in absolute main context and total resource per landable result.

### codex-lane-is-outside-the-meter

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:16,23,32`; `/Users/sma/projects/Sylveste/interverse/interstat/scripts/profile.py:25,38-52,71-87`; `config/routing.yaml:22-32`; `scripts/dispatch.sh:951-992`
- What: The memo says the meter “sees lanes” and explicitly includes Codex execution, but the cited profiler reads only Claude Code JSONL and classifies records as `main` or `subagent`. Codex output, context, attempts, latency, and failures never enter either side of the share. Moving a task from Sonnet to Codex can therefore make the reported share worse despite successful offload, while moving expensive work among unobserved Codex attempts is invisible.
- Evidence: `profile.py` scans only `~/.claude/projects/**/*.jsonl` (`:25,42-52`) and derives two lanes from Claude file paths/`isSidechain` (`:38-39,71-87`). The enforced executor router defaults unmapped classes to Codex (`config/routing.yaml:22-32`), and `dispatch.sh` can try one or more external backends while logging only routing metadata, not token/resource use (`scripts/dispatch.sh:951-992`).
- Suggestion: Give every dispatch the same `{goal_id, run_id, task_id, attempt_id, phase}` and ingest Codex dispatch start/end, model, token usage when available, wall/queue time, result, and fallback chain into the scorecard. Until then, report Claude share and Codex utilization separately and forbid a cross-lane aggregate gate.

### q-b-is-unanswerable-with-current-attribution

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:15,23,31`; `/Users/sma/projects/Sylveste/interverse/interstat/scripts/profile.py:42-50,91-123`; `scripts/orchestrate.py:1037-1045,1174-1188`
- What: The target is per goal and Q-B asks whether planning or report ingestion bloats the orchestrator, but the profiler's finest boundary is session/time window and its grouping is only lane/model. A main session can contain multiple goals, planning, dispatch, report reading, repair, landing, and unrelated conversation. Session splitting can lower apparent per-session totals; goal splitting can move expensive planning outside the attribution window. The pilots cannot identify which main-thread phase to change.
- Evidence: The profiler accepts only days, session, since, and until, then aggregates by `(lane, model)` (`profile.py:42-50,91-123`). The orchestrator has task duration/status metadata and journal rounds/HEAD (`scripts/orchestrate.py:1037-1045,1174-1188`), but no token event links those artifacts to main-thread phases or a goal.
- Suggestion: Emit phase-tagged spans for `plan`, `dispatch`, `report_ingest`, `repair`, `landing`, and `frontier_escalation`, carrying goal/session/run/task/attempt IDs plus artifact bytes or estimated tokens. Available now: Claude input/output/cache tokens, message count, model, average context, aggregate cost, task duration, and rounds. Needed before pilot one: phase and goal attribution, artifact sizes, Codex lane events, queue time, human touches, and outcome labels.

### pilot-scorecard-lacks-outcome-and-labor-guards

- Severity: P2
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:28-34`; `/Users/sma/projects/Sylveste/interverse/interstat/scripts/profile.py:117-138`
- What: “The pilots will show” is not an experimental design. The memo does not define the three workloads, matched baselines, repetitions, acceptance-quality guardrails, or how retries and human recovery count. A Codex-heavy pilot can look cheap only because the lane is unpriced, while taking longer and requiring more intervention; a harder task can make one topology look worse solely from task mix.
- Evidence: The cited profiler reports aggregate token/cost totals but no accepted-item count, failure/retry count, queue/wall time, human action, or adjudicated quality (`profile.py:117-138`). No pilot protocol or normalization appears in the target's open questions.
- Suggestion: Pre-register a compact row per pilot arm: `{workload_class, baseline_or_pattern_f, accepted, escaped_defects, main_input, main_output, cache_read, cache_write, executor_input/output, validator_input/output, wall_time, queue_time, attempts, human_touches, cost_regime}`. Use matched tasks or replayable seeded faults and repeat enough times to avoid treating task mix as routing effect.

### q-d-assumes-topology-robustness

- Severity: P2
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:33`; `commands/model-routing.md:93-106`
- What: Q-D states that Pattern F's shape is robust whether cache reads are fully weighted or ignored. That premise is unsupported: when cache traffic binds, minimizing main turns/context favors aggressive offload; when output/thinking binds, an Opus validator that duplicates checks can dominate; when Codex is nominally free but slow, latency and human recovery can dominate. The optimal order—and potentially whether every item should have a validator—can change, not merely the follow-up order.
- Evidence: The doctrine's role table already makes validator dose “per plan” and execution routing heterogeneous (`commands/model-routing.md:93-106`), so changing the priced resource changes the marginal cost of roles differently. The target provides no measurements showing the same topology stays Pareto-efficient across these regimes.
- Suggestion: Evaluate at least three declared regimes—full cache pricing, cache ignored/output charged, and pool-dollar cost with latency/human shadow prices. Select topology per workload and criterion class; do not claim robustness unless Pattern F remains nondominated on quality-adjusted total resource in each regime.

## Verdict

The ≤50% generated-token share is not a decision-worthy gate: it has the wrong system boundary and can be improved by adding work. Q-D has the wrong robustness premise; accounting changes can alter not only follow-up order but the preferred executor/validator topology.
