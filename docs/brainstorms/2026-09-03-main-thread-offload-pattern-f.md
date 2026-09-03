# Main-thread offload (Pattern F): the orchestrator stays thin, execution leaves the context

Status: design for review, 2026-09-03. Goal 1b53da77. Owner of this pattern once it lands: the `/work` and `/execute-plan` command authors (Clavain), with mk as the doctrine owner in `commands/model-routing.md`.

## The measured problem

Thirty days of transcripts on Clavain (2026-08-04..09-03, 87K assistant messages, ~$13.9K API-equivalent): the main thread is 85% of spend and 95% of generated tokens. About 85% of main-thread cost is context (cache read + cache write) re-sent every turn at 220–320K tokens per turn. The routing table (`config/routing.yaml` phases) and the doctrine (§ Routing-table v2) route execution to Sonnet, but they only bind subagent spawns. Sonnet subagents generated 2.1M tokens; the main thread generated 51.7M. The doctrine's Pattern F (execution routing overlay) requires a named integration owner and has none.

Fable 5.1 changes one input: cache reads are $0.25/MTok (Opus 5: $0.50, Fable 5: $1.00). Normalized to the same turn shape, a Fable-5.1 main turn costs ~1.4–1.9× an Opus-5 main turn and less than a Fable-5 turn did. So the lever is not "swap the main model" — it is fewer, smaller main-thread turns.

## The shape

Three roles, three context sizes:

1. **Orchestrator (Fable, main thread).** Reads the goal, writes execution-grade plans (exact paths, complete code, machine-checkable verify blocks — `writing-plans` already enforces this), spawns executors and validators, reads their reports, lands. It does not run test suites, does not sed files, does not paginate through bd output. Target: the orchestrator's own turns generate ≤50% of the goal's output tokens.
2. **Executor (Sonnet, fresh subagent; or the codex lane for classes with parity).** Receives one plan file path and the repo path. Starts at ~20–40K context, not 300K. Applies the plan, runs the plan's verify block, commits with the plan's message file, reports the verify output verbatim. Never expands scope; a plan defect is reported, not repaired.
3. **Validator (Opus, fresh subagent).** Receives the same plan and the executor's report. Re-runs the verify block itself. Judges ONLY against the frozen criteria in the plan (never its own taste). Output: PASS / FAIL with the failing criterion quoted.

Escalation: two-strikes per the doctrine — an executor that fails a plan twice, or a validator that rejects twice, returns the item to the orchestrator, which fixes the plan (usual case: the verify block was wrong, per pilot-1's 6/6 gauge defects) or takes the item frontier-in-the-loop and says so.

## What makes it enforceable rather than aspirational

- **A meter that sees lanes.** `interstat/scripts/profile.py` reports main vs subagent by model, context per turn, and the main-thread share of generated tokens for a session or time window. The gate is a number on that report, not a feeling.
- **Inheritance closed.** `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` in settings makes every unpinned spawn (48 command/skill sites, 25 doc-shaped agents) resolve to Sonnet instead of the main model. Deliberate frontier-in-the-loop spawns name `model: inherit` explicitly.
- **Plans live where the executor can read them without the orchestrator's context.** One file per item; the executor's prompt is the path, not the plan body.
- **The small-task lane stays.** Under ~30 minutes of agent time, one model end-to-end (doctrine rule 4). The offload shape is for goals, not for one-line fixes.

## Open questions the review should attack

- Q-A: Does the validator add information, or only cost, when the plan's verify block is already executed by the executor? (Doctrine says verification asymmetry pays only if criteria exist; the pilots will show whether Opus catches anything the verify block missed.)
- Q-B: Where does the orchestrator's context actually go — reading executor reports, or its own planning? If reports dominate, cap report size in the executor contract.
- Q-C: The codex lane is cost-free relative to the Claude pool but sandboxed and slower. Which pilot classes should go there first (Sylveste-d3m phase 1 builds the shadow corpus)?
- Q-D: Pool accounting is unpublished. If the pool weights cache reads at full input rate, context volume matters even more; if it ignores them, output/thinking dominates and effort becomes the lever. The shape above is robust to both, but the *ordering* of follow-ups is not.
- Q-E: What is the failure mode this shape introduces that the 30-day baseline did not have? (Candidate: plan drift — a plan written against stale repo state that a fresh executor cannot notice.)

## Review disposition (melange 2026-09-03, after the pilots)

Upheld prescriptions and where each goes. Adopted = changed in this goal; successor = epic bead filed at close.

| id | prescription (short) | disposition |
|---|---|---|
| f-006 | gate must carry a context-volume / cost companion, same instrument | adopted — proposed gate in model-routing.md amendment |
| f-008, f-013 | validator gets a second, non-blocking channel: "criteria plausibly defective / underspecified" | practiced as "beyond the gauge" in all five validations; successor formalizes it in the validator prompt contract |
| f-041 | wire Pattern F verdicts into `_interspect_insert_evidence`; make the write fail-loud; schema must distinguish replay from independent confirmation | successor (corner finding) |
| f-021 | `plan-gauge-lint.py` as a precondition for any plan entering Pattern F | successor — two of five runs were blocked by gauge defects the linter's class replays |
| f-004 | idempotent verify blocks, or validator re-runs on a fresh clone at the executor's commit | successor |
| f-003 | explicit attempts / validator_rejections store per item | successor |
| f-011 | orchestrator scored on executor-strike rate per plan it authored | successor |
| f-012 | executor can attach "proceeded under interpretation X" to a PASS without a strike | successor |
| f-014 | log the fix-plan-vs-escalate reason durably | successor |
| f-015 | named owner or audit for `inherit` usage | successor |
| f-019 | writing-plans: no silent narrowing; multi-task halt at K reports committed tasks | successor |
| f-023 | strike taxonomy: exclude validator-observed non-determinism and precondition-unrelated failures | successor |
| f-024 | state that the validator's re-run cannot substitute for a pre-freeze gauge | successor (doc edit) |

Open questions after the review: Q-A wrong premise (replay vs second channel); Q-B answered by the run — the orchestrator's context is its own 344K working set, not executor reports; Q-C untouched (codex lane latency never measured); Q-D no findings (pool accounting still unmeasured beyond one /usage reading); Q-E confirmed live (pilot 1's stale branch premise) and refined — the amplified risk is context discontinuity, not only stale plans.
