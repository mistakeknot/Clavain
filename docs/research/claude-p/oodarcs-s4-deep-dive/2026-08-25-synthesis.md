# Stipulate–Substantiate–Score–Sunset Deep-Dive Synthesis

**Date:** 2026-08-25
**Method:** two independent read-only Claude Code Opus 5 passes, followed by parent source verification.
**Inputs:** focused charter, prior Flux/Opus research, Skaffen source.
**Empirical limitation:** `~/.skaffen/evidence`, `mutations`, and `experiments` do not exist on this machine, so the proposed live-corpus census could not run.

## Executive result

The four candidates are not peers.

- **Stipulate** is the strongest candidate for a distinct semantic operation, but only as the opening half of a warrant lifecycle. A write-only stipulation is worse than no stipulation.
- **Substantiate** contains two different functions:
  - **process substantiation** records machine/human facts already available during execution and is independently valuable;
  - **claim substantiation** redeems a pre-registered warrant and is inseparable from Stipulate.
- **Score** is two homonyms, not one operation:
  - outcome scoring is adjudication/reduction from warrant plus observations to a per-plan verdict;
  - learning scoring is the existing `QualitySignal.Scores`/Pareto path and needs a type/basis repair, not a phase.
- **Sunset** is real but operates on two authority levels: local derived-cache invalidation and Intercore-owned claim retirement. It belongs on a slower loop and should not be first while the input corpus is absent/degenerate.
- **No seventh runtime phase is justified.** Use existing FSM edges and make their outputs material.

Short form: **Stipulate wins semantic distinctness; Substantiate-process wins implementation priority; Sunset wins the slow-loop maintenance gap; Score wins as a scorecard artifact, not as an S phase.**

## Candidate anatomy

| Candidate | Exact transformation | Classification | Main collapse target | Verdict |
|---|---|---|---|---|
| **Stipulate** | plan → pre-result acceptance warrant | Semantic operation/capability | stronger Decide contract | Distinct because temporal separation and omission are material; incomplete alone |
| **Substantiate-process** | execution event → durable process observation | Evidence capability | emitter/middleware contract | Ship early; no self-grading exposure |
| **Substantiate-claim** | warrant + bindings → warranted/unwarranted outcome | Completion half of Stipulate | Reflect/Compound contract | Inseparable from Stipulate |
| **Score-outcome** | many turn bindings + one warrant → one plan verdict | Reduction/adjudication | Reflect materialization + Aggregate | Valuable, but not a distinct S; call it **Redeem** or **Adjudicate** |
| **Score-learning** | partially observed quality rows → consumer-specific comparison | Type/basis policy | existing `Scores`/`Dominates`/`ParetoFront` | Repair and **Calibrate**; not an operation |
| **Sunset-cache** | derived row + validity predicate → excluded/active cache state | Local read policy | storage/read filter | Skaffen-local, mechanical, reversible |
| **Sunset-claim** | adjudicated claim + retirement proposal/decision → retired claim | Slow semantic maintenance | none | Skaffen proposes; Intercore records authority decision |

## What “Score” gets right

Score identifies a real missing material output. Reflect currently instructs the model to inspect diffs and tests but emits no structured result. A useful artifact is a **scorecard**:

```text
Scorecard {
  session_id
  plan_digest
  warrant_ref
  predicate_results[] {
    predicate
    evidence_refs[]
    result: pass | fail | unsubstantiated | unevaluable
  }
  overall_verdict
  aborted
  generated_at
}
```

Expected cardinality is one scorecard per completed plan, so omission is countable. Compound may derive a `QualitySignal` from it. A redeemed scorecard may be emitted to Intercore as a typed event.

That does **not** make Score a new phase:

1. Per-run Score is what Reflect should materialize and what Aggregate should reduce across turns.
2. Cross-run Score already exists under `QualitySignal.Scores`, `Dominates`, and `ParetoFront`.
3. The two meanings have different subjects, clocks, truth conditions, and missing-data policies.
4. The cross-run function currently cannot represent unknown: `[]float64` coerces absence into a number, while `TestsPassed` and `BuildSuccess` are not included at all.

Recommended vocabulary:

- **Redeem/Adjudicate** — evaluate one warrant against observations.
- **Scorecard** — the material per-plan artifact.
- **Calibrate** — validate the cross-session comparison basis and missing-data policy.
- Keep `Scores()` as the lower-level projection only after its type is repaired.

## The composed lifecycle

The useful architecture is a protocol, not four independent features:

```text
Decide
  → Stipulate: pre-register warrant
  → Act: produce tool/process observations
  → Substantiate: bind observations
  → Redeem: reduce all bindings to one scorecard
  → Compound: derive cacheable QualitySignal

Slow loop:
  provenance/age/contradiction checks
  → Sunset proposal
  → Intercore retirement decision for authority-bearing claims
  → Skaffen read filter/cache refresh
```

Minimum per-plan states:

- `unknown`: no warrant exists;
- `vacuous`: a `none` predicate was stipulated;
- `unevaluable`: a predicate exists but cannot be executed;
- `unsubstantiated`: predicate exists but no binding observation was recovered;
- `pass` / `fail`: predicate evaluated;
- `aborted`: run errored or hit limits before adjudication.

Slow-loop states must remain typed:

- `provenance_stale` versus `age_stale`;
- `contested` for contradictory rows;
- `retired`, with a reason distinguishing exclusion from falsification.

Observations about past events do not become false with age; only their retention changes. Derived cache rows can be invalidated locally. Authority-bearing claim retirement belongs in Intercore.

## Verified current-code defects that precede the S decision

1. **Fabricated success:** `internal/agentloop/loop.go` assigns `success` to every non-tool terminal turn; Compound selects the last record, so every stored normal run is successful by construction.
2. **Failure loss:** `classifyFailure` computes `agentloop.Evidence.Failure`, but `emitterAdapter` and `agent.Evidence` drop it before disk.
3. **Provenance loss:** `FileActivity`, model, and model reason reach evidence JSONL but are silently dropped by `mutations.evidenceRecord` during aggregation.
4. **Degenerate axes:** denial and approval have no writers; error checks an unreachable outcome value; tests/build have no production writers. The current frontier is effectively token efficiency versus turn count.
5. **Inert hard fields:** `TestsPassed`, `BuildSuccess`, and `ComplexityTier` are not part of `Scores()`.
6. **Wrong reduction:** Aggregate uses the last turn's outcome instead of reducing failures and bindings across all turns.
7. **Constraint bypass:** phase membership is applied when building the flat registry, but `toolBridge.Execute` calls the inner tool directly. `AllowedGlobs`, rate limits, sandbox path validation, and `PhasedTool.ExecuteWithPhase` in `tool.Registry.Execute` are bypassed.
8. **Still-dead constraints after simple restoration:** `RequirePrompt` has no production enforcement, and `ResetRateCounts` has no production caller.
9. **Selection bias:** only successful Compound invocations write signals; aborted/error runs have no durable terminal state. Headless mode executes one phase and currently omits Observe from validation.
10. **Disconnected experiment path:** experiment records already carry hypothesis/Git SHA/decision/delta and the evidence bridge understands `ExperimentEvent`, but the agent-loop evidence path has no producer/copy path for it.

These are correctness/security prerequisites, not candidate features.

## Architecture decision

### Semantic operation

**Provisional winner: Stipulate as the name of the complete warrant protocol, not a write-only step.** Its distinct invariant is that acceptance criteria are recorded before results are available and their omission is countable. Claim substantiation and redemption are its required completion.

If the name is interpreted narrowly as “write a predicate,” it is not sufficient and should not ship.

### Runtime phase

**None.** The Decide→Act edge already supplies the required ordering. A new phase would add enumerations without adding a new enforced relationship. Reconsider only if mid-run replanning introduces a back-edge requiring repeated warrant minting and phase-scoped enforcement is repaired.

### Score

**Keep the idea, split the meanings, reject it as a phase.** Make a scorecard the durable output of Reflect/reduction. Repair cross-run scoring as a typed comparison policy. Do not let one S-word hide the boundary between correspondence judgment and population ranking.

### Sunset

**Keep as a slow-loop capability.** Local cache invalidation must not depend on Intercore availability. Retirement of authority-bearing claims is proposed by Skaffen and recorded by Intercore. Sunset should follow, not precede, trustworthy evidence and scoring.

## Implementation order

1. **Correct the evidence and enforcement floor.** Restore phase-aware execution without regressing rate limits; enforce or remove `RequirePrompt`; preserve `Failure`, denials, approvals, file/model provenance, experiment events; aggregate across turns; represent aborted runs; add adapter round-trip tests.
2. **Ship Substantiate-process.** Populate process facts already observable without any warrant: denial, approval, tool error, exit status. This is the smallest falsifiable improvement.
3. **Pilot Stipulate + Substantiate-claim + scorecard together.** Prefer extending/reusing the experiment record/event path over creating a competing warrant store, but preserve pre-result timing and tamper evidence.
4. **Repair learning Score.** Represent unknown explicitly, reject invalid/empty rows, include only supported axes, and make missing-data policy consumer-specific.
5. **Add Sunset after useful durable data exists.** Local cache filter first; Intercore proposal/decision path for claim retirement.

## Falsifiable pilots

### Retrospective

A live-store census was attempted but no Skaffen evidence/mutation/experiment stores exist on this machine. Therefore no value ranking can currently be based on observed operational data.

When data exists, measure:

- per-axis variance;
- orphan evidence sessions without Compound rows;
- normal-success fraction;
- zero/empty-signal rows admitted to Pareto fronts;
- task-type key disagreement;
- outcomes with process failure evidence.

### Live

For each plan:

1. mint one pre-result predicate;
2. record process observations;
3. redeem across all turns into one scorecard;
4. log legacy success beside scorecard verdict without changing guidance;
5. measure predicate authorability, redemption rate, legacy/verdict disagreement, aborted rate, and missing scorecards.

Kill the warrant protocol if predicates are mostly vacuous, redemption is near zero, or legacy success already agrees with verified verdicts. Kill an axis if it remains constant or has no decision consumer. Reverse Sunset by changing status/read filtering; never delete source observations.

## Validation notes

- Both independent reports used `claude-opus-5` according to Claude Code JSON output.
- Parent inspection confirmed the key adapter, aggregation, scoring, and registry paths.
- The focused Go test attempt was not a clean validation run: agent-related packages could not resolve the local `../../masaq` replacement; `TestInspireWithHistory` hung in external `cass` until the Go test timeout; several experiment worktree tests also failed. The spawned `cass` process was terminated. No source files were modified.
