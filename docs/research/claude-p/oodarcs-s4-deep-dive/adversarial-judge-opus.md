# Adversarial Judgment — Stipulate / Substantiate / Score / Sunset / no‑S

**Mode:** read-only, fresh judge. **Source reads/searches used:** 10 (7 files, 3 greps). **Verdict inheritance:** none.

---

## 1. Verification of the report's five decisive code claims

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Success is fabricated | **CONFIRMED, and understated** | `loop.go:246-249` sets `outcome="success"` unless `StopReason=="tool_use"`. The loop returns only on `end_turn` (`loop.go:301`); any other terminal path returns an error, so `agent.go:242-244` bails before Compound. Therefore **every** signal that reaches the store has `Human.Outcome=="success"` → `Scores()[5]==1.0` (`signal.go:55-58`). |
| 2a | `Failure` dropped before disk | **CONFIRMED** | `classifyFailure` (`loop.go:752-797`) → `Evidence.Failure` (`loop.go:273`). `emitterAdapter.Emit` (`agent.go:374-399`) enumerates 22 fields; `Failure` is not among them, and `agent.Evidence` (`deps.go:61-87`) has no such field. |
| 2b | `FileActivity` dropped | **CONFIRMED, but at a different site than the report's headline** | It *survives* the adapter (`agent.go:380`) and JSONL (`deps.go:67`). It dies at `aggregate.go:14-24` — `evidenceRecord` has no `file_activity` key. Same for `model`, `model_reason`, `stop_reason`-adjacent provenance. |
| 3 | Score axes permanently empty | **CONFIRMED** | `Scores()` (`signal.go:54-67`) returns 6 values. `Aggregate` never assigns `Soft.ToolDenialRate` or `Human.ApprovalRate` at all. `Soft.ToolErrorRate` counts `r.Outcome=="error"` (`aggregate.go:81`) — a value `loop.go:246-249` cannot emit. Grep confirms `TestsPassed`/`BuildSuccess`/`ToolDenialRate`/`ApprovalRate` have **zero** non-test writers. `Dominates` therefore ranks on `TokenEfficiency` and `-TurnCount` only. |
| 4 | Gate constraints bypassed via `toolBridge` | **CONFIRMED, and larger than reported** | `buildLoopRegistry` (`agent.go:267-276`) wraps tools in `toolBridge`, whose `Execute` (`agent.go:286-289`) calls `b.inner.Execute` directly. `agentloop.Registry.Execute` (`agentloop/registry.go:67-76`) does no gating. `tool.Registry.Execute` (`registry.go:199-279`) is the sole enforcer. |
| 5 | Compound-only selection bias | **CONFIRMED, and sharper** | `agent.go:247` gates the write on `phase==PhaseCompound`; `agent.go:242-244` returns early on any loop error. `main.go:55,216-221` runs **one** phase per headless invocation and its help text + validation enumerate five phases — `observe` is rejected. |

### Three corrections and one addition the report got wrong or missed

**(i) `RequirePrompt` is not enforced anywhere — including on the path the report proposes to restore.** The report says the three constraint kinds are "enforced only in `tool.Registry.Execute` (`registry.go:224-259`)." Read that block: it handles `AllowedGlobs` and `RateLimit` only. `RequirePrompt` is read by no production code — `Registry.Constraint()` (`registry.go:188`) is its only accessor and has zero production callers (`registry_test.go:94,130` only). So `builtin.go:41-45`'s `run_experiment{RequirePrompt:true}` and Reflect's `edit{RequirePrompt:true}` stay dead *after* the report's §7A fix. The null bundle as written does not deliver what it claims.

**(ii) `ResetRateCounts` has no production caller — so restoring `Execute` converts a per-phase limit into a per-process one.** Grep: only `registry_test.go:484`. Reflect's `edit{RateLimit:3}` would become 3 edits per *process lifetime*, silently starving long TUI sessions. That is a regression risk the report files as a "downstream symptom."

**(iii) The bypass also kills sandbox validation and `PhasedTool` dispatch.** `registry.go:263-272` is the only `sandbox.CheckPath` call for file tools; `registry.go:275-277` is the only `ExecuteWithPhase` dispatch. Both are off the agent path. This is a security-relevant finding the report does not name, and it makes the fix higher-priority than "reviving declared constraints."

**(iv) `Evidence.ExperimentEvent` is a consumer with no producer.** `deps.go:86` declares it; `evidence/emitter.go:103-111` branches on it to type Intercore events. `emitterAdapter` never sets it and `agentloop.Evidence` has no such field. The entire experiment→Intercore bridge is unreachable. The report's field ledger misses this, and it matters — see §5.

**(v) Provenance note.** `docs/sprints/Demarch-6i0.11-transcript.json:158980` records the removed line `- result := a.registry.Execute(ctx, a.fsm.Current(), tc.Name, tc.Input)`. The bypass is a **regression introduced by the agentloop extraction**, not an original design. That reframes it from "architecture gap" to "restore a deleted call site" — cheaper than the report implies, and it makes test #5 in §8.2 a regression test, not a new invariant.

---

## 2. Symmetric collapse test against the incumbents

The report applies three tests (information gain, omission observability, enforcement delta) and kills Score with them. Applied symmetrically:

| Incumbent | Durable material output | Omission countable? | Enforcement delta | Survives its own test? |
|---|---|---|---|---|
| **Observe** | none | no | tool membership only — and it is **unreachable headless** (`main.go:221`) | **No** |
| **Orient** | none (reads store, injects prompt) | no | identical gate set to Observe/Decide (`registry.go:50-58`) | **No** |
| **Decide** | none — router picks a model, prompt gets a clause | no | identical to Observe/Orient | **No** |
| **Act** | files on disk | yes (via git) | widest membership | Yes |
| **Reflect** | none — `reflectPhaseGuidance` is prose | no | `bash` in, `edit` rate-limited (**dead**) | **No** |
| **Compound** | `QualitySignal` row (`agent.go:247-253`) | yes | manifest globs (**dead**) | Yes, on output alone |
| **hooks** | external process only; `PostToolUse` is `go` on `context.Background()` (`loop.go:399-403`); `PreToolUse` denial text goes into the message stream (`loop.go:414-424`) | no — **no return channel into `Evidence`** | real (`deny`/`ask` are honored) | Partial |
| **middleware** | **does not exist** in this tree | n/a | n/a | The charter's "middleware seat" is empty. The adapters *are* the de facto middleware, and they are the loss sites. |
| **schemas** | `agent.Evidence` has 26 fields; `ComplexityTier`, `ComplexityOverride`, `ExperimentEvent` are structurally unfillable | by unit test | none | **The least reliable remedy in the repo** — a ~12% dead-field rate |
| **`QualitySignal.Scores()`** | per-read ranking | no — degeneracy is silent | none | **No** |
| **Intercore** | `ic events record`, fire-and-forget, errors discarded, skipped when `ic` absent (`emitter.go:30-32,136`) | no | none | "Durable authority" is **aspirational, not operative** |
| **experiment subsystem** | `ExperimentRecord{Hypothesis, GitSHA, Decision, Delta}` in its own store | no | Act-gated + `RequirePrompt` (**dead**) | Yes on output, **zero** on connection |

**Conclusion.** The report's criteria are not a legitimacy test for phasehood — they eliminate four of six incumbent phases. Phasehood in Skaffen confers exactly two things: (a) tool membership via `Tools(phase)` (`registry.go:165-184`), and (b) a system-prompt clause. Anything else attributed to a phase is currently fiction. **Compound is the only phase whose identity is a mechanical side effect**, and it achieves that at an *edge* (`agent.go:247`), not through the FSM. That is the template.

Corollary that damages the report's own reasoning: it uses "no durable output → not an operation" against Score-outcome while accepting Decide, whose output is *nothing at all*, as the natural home for Stipulate. Either output-bearing is the criterion (then Decide must earn it too) or it isn't (then Score-outcome isn't disqualified by it).

---

## 3. Steelman of Score, then the attack

### 3.1 The strongest available contract

Not "validate axes before ranking" — that is a guard, and the report is right that a guard is not an operation. The strongest contract is this:

> **Score-learning owns the comparison semantics of a partially-observed objective vector.** `Dominates` (`signal.go:71-86`) requires a total order on every axis. The moment Substantiate populates `HardSignals.TestsPassed *bool`, the basis contains a genuine three-valued axis (`true`/`false`/`nil`). Pareto dominance over `nil` is **undefined**, not merely unguarded: "at least as good as unknown" has no truth value. Score-learning is the operation that decides — per read, per consumer — whether unknown orders pessimistically, optimistically, or incomparably, and emits the decision alongside the ranking.

This is strong because it is not reachable by repair. `Scores()` today returns `[]float64` — a type that **cannot represent unknown**. Note that `TestsPassed`, `BuildSuccess`, and `ComplexityTier` are not in `Scores()` at all: the report's own pilot (§8.2 step 3 writes them, step 4 says "do not change `Scores()` yet") therefore produces values that are **inert to the frontier**. That is a live defect in the report's recommended pilot, and it is exactly the gap this contract fills.

Second, genuinely-new fact under this contract: the empty-signal degeneracy. `Aggregate` returns a zero `QualitySignal` when a session has no evidence rows (`aggregate.go:49-55`). Its scores are `[0, 0, 0, 0, 0, 0]`. Against a real session `[0.3, -5, 0, 0, 0, 1.0]`, **neither dominates** — the empty row is better on `-TurnCount`. An empty row therefore enters the Pareto front and is eligible to be templated into the next Orient prompt as "best approach." No axis guard catches this; only a validity/provenance judgment does.

### 3.2 The attack

The unknown-ordering decision is a **three-line policy**, not a seat: define `nil → worst`, document it, add a `valid []bool` mask return. It has no trigger of its own (it fires on read), no durable output (the report is correct that rankings must not be persisted), no consumer other than the three functions already in `mutations`, and no cadence distinct from the read. It never becomes observable-if-skipped except through the mask it itself produces — which is circular.

**Where the attack fails:** the policy is not consumer-uniform. `BestApproach` wants pessimistic (never promote an unverified row); `Suggest` wants incomparable-and-say-so (advice from a degenerate basis should be withheld, not inverted). A single constant cannot serve both. So the honest form is `Scores() (values []float64, valid []bool)` plus a per-call-site policy argument — a **type change plus a documented policy**, which is more than a guard and less than an operation.

**Verdict: Score-learning is a signature change with a policy, not a phase and not an operation. Its correct name is the repair itself; adding an "S" launders a type error into an architecture.**

### 3.3 Must outcome-Score and learning-Score split?

**Yes — and the split is sharper than the report's table.** The report grounds it in subject/basis/clock/reversibility. The decisive ground is narrower and mechanical: **outcome-Score is truth-functional over two fixed inputs; learning-Score is policy-functional over a mutable population.** One admits a unit test with a fixed expected value; the other's correct output depends on a choice nobody has made. Types that differ in whether their output is *derivable* must not share a name.

But the report's remedy is wrong in one respect: it says outcome-Score "owns no state transition of its own." It owns exactly one that Substantiate cannot: the transition from *many per-turn bindings* to *one per-plan verdict* — a reduction over turns. And `Aggregate`'s current reduction rule is **provably wrong** for this: it takes the *last* record (`aggregate.go:89-90`), and `classifyFailure` is only invoked when `StopReason=="tool_use"` (`loop.go:253`), so the terminal turn **structurally never carries a failure verdict**. Carrying `Failure` through the adapter therefore does not fix outcome; the reduction rule must change from last-record to any-failure-across-turns. The report's null bundle does not include that, and without it the plumbing fix produces the same constant.

---

## 4. Stipulate and Substantiate: separable, or two halves?

Neither. **Substantiate is two operations wearing one name, and only one of them needs Stipulate.**

- **Substantiate-process** — bind machine-observed process facts to the record: hook/user denial (`loop.go:428-438`), approval (`loop.go:436`), tool error (`block.IsError`), bash exit status. **No warrant required, no self-grading possible**: the human or the hook denies, and the loop merely observes. Omission is countable *today by audit*, because denial text is persisted into the session message stream via `session.Save` (`loop.go:293-298`). This is separately meaningful and it is the cheapest path to a non-constant axis in the entire repo.
- **Substantiate-claim** — bind an *outcome assertion* to an observation. Inseparable from Stipulate: absent a pre-registered predicate, the actor being graded selects its own bar, and "substantiated" is self-attestation with extra steps.

**Self-grading.** The real exposure is not that the model writes the verdict; it is that the model writes the *predicate* after seeing results. Stipulate's product is a **temporal write separation**: predicate authored at turn *n*, evidence at turn *n+k*, both timestamped. Note what the code says about enforcing this: with the gate bypass live, `~/.skaffen/warrants/` is writable by Act's unconstrained `write` (`registry.go:60`). But `MatchesPath` matches on **basename only** (`registry.go:34`) — so `AllowedGlobs` cannot express a directory-scoped denial *even when restored*. The report's proposed namespace invariant is not expressible in the existing constraint type. Either the ordering claim needs append-only/tamper-evident storage (timestamps + a hash chain), or it must be dropped. Tamper-evidence is sufficient and cheap; tamper-proofness is not available from `GateConstraint` as typed.

**Verdict:** Stipulate + Substantiate-claim = **one operation with two halves**, joined by a write/read separation over one durable object. Substantiate-process = **separately meaningful, ships independently, first**.

---

## 5. What Sunset acts on, and who owns it

The report gives one answer ("authority tier, Intercore-owned"). That is wrong for the object it names.

| Object | What Sunset means | Owner | Cadence |
|---|---|---|---|
| **Observations** (`~/.skaffen/evidence/*.jsonl`) | Nothing. An observation about a past turn does not expire. Retention/rotation only. | Skaffen, `O_APPEND` + rotation | size/age job |
| **Derived cache** (`QualitySignal` rows) | **Cache invalidation.** These are a projection over evidence — regenerable in principle. Retiring one is a read-filter decision, not a truth claim. | **Skaffen-local, mechanical** | **At read time — a filter, not a job** |
| **Claims** (adjudicated warrant verdicts) | Genuine retirement of a judgment about work performed. Reversible, authored, reasoned. | **Skaffen proposes, Intercore records** | slow loop |
| **Authority decisions** (trust scope, promotions) | Out of scope here, but same rule: proposal path only. | Intercore | slow loop |

**Why the report's single verdict breaks the runtime:** `ic` absence is an explicit graceful-degradation path (`emitter.go:30-32,47`; errors discarded at `:136`). If retirement status for `QualitySignal` rows lives in Intercore, then Skaffen's **read path** — `ReadRecent` → `formatQualityHistory` → system prompt — acquires a hard dependency on `ic`. Without `ic`, Skaffen cannot know which of its own cache rows to trust, and the honest fallback is "trust none," i.e. the compounding loop silently disables itself on every machine without `ic`. Cache eviction must be local. Only claim retirement crosses.

**The decisive argument against Sunset-first (contra the report's §9e ordering):** with four of six axes constant and `outcomeScore` pinned at 1.0, **every row in the corpus scores identically on everything that varies except thrift.** Retiring rows from such a corpus changes `BestApproach` only by changing which thrift-optimal row is selected. Sunset's pilot has **no measurable outcome today** — it is unfalsifiable until the axes move. The report calls Sunset "the one uncontested gap" and "cheapest"; both are true and neither makes it first, because a cheap unfalsifiable change is worse than a cheap falsifiable one.

---

## 6. The six-state lifecycle: what's missing and what's conflated

**Missing:**

1. **`aborted` / `incomplete`.** A run that hit `maxTurns` (`loop.go:317`) or errored writes nothing (`agent.go:242-244`). "The actor never finished" ≠ "the question wasn't answered." Both are countable defects with different remedies, and the first is the one currently producing the selection bias. This is the most damaging omission — the state machine has no representation for the failure mode the code most reliably produces.
2. **`unevaluable`.** The report maps a malformed predicate to `unknown`, conflating *absence of a question* with *an unanswerable question*. Different counters, different owners (mint-quality vs. binder-quality).
3. **`vacuous`.** The report permits `predicate_kind: none` and records it — but a `none` warrant redeems to *what*? If it can reach `pass`, the fabricated-success bug is reconstituted one layer up, with `authorability` laundered into the pass rate. `none` must be terminal and separately counted.
4. **No representation of contradiction.** Sunset's trigger list includes "contradiction," but contradiction is a *relation between rows*, not a property of one. The six states cannot express `contested`; the machine jumps straight to `retired`, which pre-judges which row is wrong.

**Conflated:**

5. **`stale` fuses two different things.** *Provenance moved* (cited path/commit changed) is a mechanical fact, cheap, precise, reversible by re-substantiation. *Age exceeded* is a policy guess with an arbitrary window and no reversal semantics. Different owners. Also: `ReadRecent(n)` is **positional**, and no wall-clock policy exists anywhere in the runtime (`time.Now()` appears only for stamping, `loop.go:205,220,260`) — so age-stale requires machinery that provenance-stale does not.
6. **`retired` fuses "excluded from guidance" with "judged false."** A redundant or noisy row can be retired without being wrong. Without a *typed* reason, the read filter cannot distinguish "don't cite this" from "this is false," and the reversal path (`retired → active`) means different things in each case.

**Verdict: eight to nine states, not six** — minimally add `aborted`, `vacuous`, and split `stale` into `provenance-stale` / `age-stale`. `unevaluable` can fold into `unknown` **only** if the defect counter is separate.

---

## 7. Five architectures, qualitative

**A. Null / contract fixes only.** Cheapest, unit-testable, and the only option with a *demonstrated* precedent — the gate bypass is a git-recoverable deleted call site, not a design problem. Ceiling is real: it cannot produce `TestsPassed` because nothing observes tests. As specified in the report it is also **incomplete in three ways** (§1: `RequirePrompt` still dead; `ResetRateCounts` uncalled → per-process rate limits; `Aggregate`'s last-record reduction still yields constant `success`). Fix those and it is a genuine floor. **Necessary, insufficient, and mis-specified as written.**

**B. Stipulate only.** Write-only store. The report is right that a minted-never-redeemed warrant is worse than none because it *looks* like rigor. Additionally: the invariant it sells is not expressible — `MatchesPath` is basename-only (`registry.go:34`), so no glob can protect a warrant directory. **Rejected as terminal; viable only as stage 1.**

**C. Substantiate only.** The report rejects this via the "0-for-4" precedent. That inference is unsound (§9). Substantiate-*process* requires no warrant, is immune to self-grading, has in-process data being actively discarded at two known lines, and is the only change that makes any axis non-constant. Substantiate-*claim* alone is indeed self-attestation. **Split verdict: process-half is the strongest single move in the field; claim-half is rejected alone.**

**D. Sunset only.** Uncontested gap, ~30 lines, inherently reversible. But unfalsifiable on a degenerate corpus (§5), and its natural implementation invites the exact Intercore read-path dependency that breaks `ic`-absent degradation. **Real, correctly last.**

**E. Composed protocol.** Best end state. Two conditions the report does not state: (i) it must include the `Aggregate` reduction-rule change, without which the plumbing fix yields the same constant; (ii) it must change `Scores()`'s signature, without which every substantiated hard signal is inert to the frontier. With both, it is the only architecture where each stage's omission is countable. **Best, conditional on two unstated prerequisites plus predicate authorability.**

---

## 8. Verdicts

**(a) Best semantic operation — Substantiate, split; process-half first.**
*Confidence: high on the split, moderate-high on the ordering.* Bind process facts (denial, approval, tool error, exit status) to the durable record. Warrant-free, self-grading-immune, data already computed and discarded at `loop.go:428-438` and `:436`. Stipulate + Substantiate-claim follow as one shipment.
**Kill:** if denial and approval rates come back near-constant across a real corpus, the axis was never informative — stop, and the case for outcome machinery weakens sharply.
**Reversal:** if `Human.Outcome` is removed from `Scores()` (`signal.go:65`) and from `Suggest`, the claim-half loses its only consumer; delete it and keep the process-half.

**(b) Best runtime phase — none.**
*Confidence: high, on stronger grounds than the report's.* Phasehood confers only tool membership and a prompt clause; four of six incumbent phases fail the report's own tests; the runtime cannot express its sixth phase headless (`main.go:55,221`). Use the **Compound pattern** — a mechanical side effect at an FSM edge (`agent.go:247`) — which needs no new `tool.Phase` constant, no `defaultGates` row, no router entry, and no TUI change.
**Reversal:** re-ask only if the FSM gains a back-edge for mid-run replanning (the mint must then recur and needs a seat) **and** `tool.Registry.Execute` is back on the execution path with directory-scoped globs.

**(c) Score — reject the name; split the senses; neither is a phase.**
*Confidence: high.* Outcome sense = adjudication, folds into Substantiate-claim, but **owns one reduction** (many turn-bindings → one plan verdict) that today is `aggregate.go:89-90`'s provably-wrong last-record rule. Learning sense = a **signature change plus a per-consumer unknown-ordering policy** on `Scores()`, not a guard and not an operation. The two must not share a name: one is truth-functional, the other policy-functional.
**Kill:** if a corpus census shows ≥4 of 6 axes with real variance, the learning-sense case collapses to the existing function untouched.

**(d) Sunset ownership — two objects, two owners; reject the single authority verdict.**
*Confidence: moderate-high.* Derived-cache eviction is Skaffen-local and applied **at read time as a filter**, never dependent on `ic`. Claim retirement is proposed by Skaffen and recorded by Intercore, on a slow loop, with a **typed** reason. Never `os.Remove`.
**Kill:** if `ic` cannot record a retirement proposal without becoming a read-path dependency, keep retirement entirely local and downgrade it to documented cache policy.

**(e) First implementation — corrected null fixes → Substantiate-process → connect the experiment subsystem as Stipulate → Sunset.**
*Confidence: high on 1, moderate-high on 2, high on 3's cost advantage.*

1. **Null fixes, correctly specified.** Restore the deleted `a.registry.Execute(ctx, phase, …)` call site (recoverable from `docs/sprints/Demarch-6i0.11-transcript.json:158980`) — this revives globs, rate limits, **sandbox path validation**, and `PhasedTool` dispatch. Simultaneously: call `ResetRateCounts` on phase transition, or Reflect's limit becomes per-process. Carry `Failure`. Add `file_activity`/`model` to `evidenceRecord`. **Change `Aggregate`'s reduction from last-record to any-failure.** Assign `ComplexityTier` or delete the field. Wire `RequirePrompt` into the trust evaluator or delete it. Guard `ParetoFront` at n≤1 **and** reject the zero-signal row (`aggregate.go:49-55`).
2. **Substantiate-process.** Two `Evidence` fields, two adapter lines, two `Aggregate` accumulators. First non-constant axis in the repo's history.
3. **Stipulate — do not build a new warrant store.** `experiment.ExperimentRecord` already carries `Hypothesis` + `GitSHA` + `Decision` + `Delta` (`experiment/store.go:37,46`), and `evidence/emitter.go:103-111` already consumes `ExperimentEvent` to type Intercore events — **with no producer**, because `emitterAdapter` never sets it and `agentloop.Evidence` lacks the field. Stipulate is 80% built and disconnected. Connecting a live consumer to an existing record beats minting a new store, and it converts the authorability question from a design guess into a query over records that already exist.
4. **Sunset**, once the axes move and retirement is falsifiable.

---

## 9. The strongest finding in the anatomy report that should be rejected

> **§3.2 / §7B / §9e: "This repo has run this experiment four times and lost four times" — therefore Substantiate-without-Stipulate is the fifth iteration of a 0-for-4 pattern, and the omission-observability asymmetry "decides the sequencing question."**

**Reject the inference; keep the observation.** The four empty fields are real. But they have **two unrelated causes**, and the report's argument requires them to share one:

- `HumanSignals.ApprovalRate` — the value is computed at `loop.go:436` (`l.approver` returns a bool) and thrown away. **Plumbing.**
- `SoftSignals.ToolDenialRate` — denial is decided at `loop.go:428-438` and persisted into the message stream. **Plumbing.**
- `SoftSignals.ToolErrorRate` — a value-domain bug: `aggregate.go:81` tests `Outcome=="error"`, unreachable from `loop.go:246-249`. **Wrong constant, not a missing observer.**
- `HardSignals.TestsPassed` / `BuildSuccess` — genuinely unobserved. **Missing observer.**

Only the last is evidence that "a field without a warrant stays empty." Denial and approval are **third-party observations** — a human or a hook refuses, and the loop merely records it. There is no self-grading exposure to protect against, and no warrant is relevant. They are empty because two adapter boundaries drop them, which is the *plumbing* thesis the report itself proves elsewhere.

This matters because 0-for-4 is load-bearing in three places: it grades Substantiate "weak alone" in §3.2, it is the "fatal flaw" that rejects architecture B in §7, and it is the stated reason for putting Sunset ahead of Substantiate in §9e — the report's explicit disagreement with the red team. Recount it as **0-for-2 on missing observers, 0-for-2 on dropped plumbing**, and the asymmetry no longer decides sequencing. Substantiate-process becomes the cheapest falsifiable move in the field, and Sunset — which cannot be falsified on a degenerate corpus at all — moves last.

**Also downgrade (not reject):** §5.2's "`Scores()` *is* the learning scorer, and what's missing is a validity guard." `Scores()` returns `[]float64` and **excludes `TestsPassed`, `BuildSuccess`, and `ComplexityTier` entirely**. Every hard signal the report's own pilot would populate is invisible to `Dominates`. That is a type-and-basis defect, not a guard's absence — and it silently voids §8.2's measurement plan.

`★ Insight ─────────────────────────────────────`
The generalizable pattern: **adapter layers between two typed boundaries are where invariants go to die silently, because each side's tests pass.** `emitterAdapter` (22 explicit field copies) and `evidenceRecord` (9 of ~26 JSON keys) are both *correct in isolation* and *lossy in composition* — and Go's `json.Unmarshal` makes the second loss completely silent. The cheap structural defense is a round-trip table test per adapter that enumerates fields reflectively and fails on any uncopied one; that single test class would have caught `Failure`, `FileActivity`, `Model`, and the producerless `ExperimentEvent` at once.
`─────────────────────────────────────────────────`

**Residual uncertainty, stated plainly:** nothing here is measured either. Every ordering above is reasoned over code. The corpus census remains the cheapest thing that would move any of it, and it has still not been run — but note that two of its predicted metrics (task-type disagreement, false-warrant lower bound) are now *less* informative than a third the report doesn't propose: **the count of sessions that reached `maxTurns` or errored and therefore wrote nothing.** That number bounds the selection bias, and it is recoverable from `~/.skaffen/evidence/*.jsonl` orphans — session files with no corresponding `quality-signals.jsonl` row.
