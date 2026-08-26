# Stipulate–Substantiate–Score–Sunset Deep-Dive Charter

**Date:** 2026-08-25
**Repository:** Skaffen
**Question:** Do Stipulate, Substantiate, Score, or Sunset deserve recognition as distinct semantic operations, runtime phases, or harness capabilities—and are they rivals or stages of one lifecycle?

## Candidate contracts under test

### Stipulate
Before Act, transform a plan into a durable, mechanically evaluable acceptance warrant authored before results are known and stored where the acting turn cannot rewrite it.

### Substantiate
After action, bind an outcome assertion to recoverable observations such as test/build results. Unsupported outcomes remain explicitly unsubstantiated.

### Score: outcome sense
Compare a pre-stipulated warrant with substantiated observations and emit a scorecard/verdict, including unknown and indeterminate states rather than coercing missing evidence to success or failure.

### Score: learning sense
Evaluate durable outcomes across sessions, validate each ranking axis, and emit a calibrated comparison suitable for selecting or rejecting future approaches.

### Sunset
On expiry, provenance change, contradiction, or repeated warrant failure, transition a durable record to a reversible retired state and exclude it from future guidance without deleting history.

### Null hypotheses

- **No semantic S:** all four are stronger contracts inside Decide, Reflect, Compound, storage, or policy.
- **No runtime S:** even valuable operations should use existing phase edges/hooks rather than a seventh FSM state.
- **Pipeline null:** the candidates are not rivals: Stipulate → Act → Substantiate → Score → Compound, with Sunset on a slower maintenance loop.
- **Score null:** Score collapses entirely into Reflect for per-run evaluation and `QualitySignal.Scores`/Pareto logic for cross-run evaluation.

## Required tests

For every candidate and both Score senses, determine:

1. Exact input, trigger, transformation, material output, consumer, cadence, expiry, and authority tier.
2. What information is unavailable before the operation but available after it.
3. Whether omission is materially observable and countable.
4. Whether an incumbent OODARC operation, hook, schema field, or middleware seat can discharge the duty without losing an invariant.
5. Whether phasehood adds an enforcement relationship unavailable at an existing edge.
6. Whether the operation introduces a competing truth channel relative to Intercore. Intercore remains durable authority; Skaffen may emit evidence and proposals but not independent authoritative state.
7. Epistemic behavior under missing evidence, failed tools, compaction, stale provenance, and self-grading pressure.
8. Pace/shear behavior: turn, plan, session, and cross-session clocks must not be conflated.
9. Smallest falsifiable pilot, kill criterion, reversal condition, and evidence tier.

## Code-grounding targets

- `internal/agentloop/loop.go`
- `internal/agent/agent.go`
- `internal/agent/phase.go`
- `internal/agent/deps.go`
- `internal/evidence/`
- `internal/mutations/aggregate.go`
- `internal/mutations/signal.go`
- `internal/mutations/store.go`
- `internal/mutations/best.go`
- `internal/mutations/mutate.go`
- `internal/session/session.go`
- `internal/hooks/`
- `internal/tool/registry.go`
- `internal/tool/builtin.go`
- `internal/experiment/`

## Decision output

Produce separate verdicts for:

1. Best semantic operation, if any.
2. Best runtime phase, if any.
3. Proper classification of both Score senses.
4. Whether the four form a coherent lifecycle.
5. First implementation and pilot order.
6. Confidence, unresolved disagreements, and reversal conditions.
