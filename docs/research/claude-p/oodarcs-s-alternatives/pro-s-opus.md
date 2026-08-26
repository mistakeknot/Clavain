I verified the decisive claims in source before arguing. Everything below is read-only; no files changed.

`★ Insight ─────────────────────────────────────`
Two checks reshaped this brief. (1) `internal/tool/builtin.go:20` registers `web_search`/`web_fetch` for `{Orient, Decide, Act}` — so the "Observe and Decide are byte-identical / the gate space has three signatures" findings read the `defaultGates` *literal* and missed `RegisterBuiltins`. Effectively all six phases have distinct signatures. (2) `QualitySignal` already carries `TestsPassed`, `BuildSuccess`, `ToolDenialRate`, `ApprovalRate` — and nothing in the repo ever assigns any of them. The clause-shaped remedy the skeptic recommends has already shipped here, four times, and is 0-for-4.
`─────────────────────────────────────────────────`

# Pro-S Advocacy — OODARC(+S)

## 1. Promotion criteria

**Clause → semantic operation. The non-discharge observability test.** Promote a cross-cutting duty exactly when *skipping it is unobservable at the seat where it lives as a clause, but countable if it is an operation*. Supporting conditions: (a) its output inhabits a type no incumbent emits; (b) it is not obtainable by re-parameterising an incumbent; (c) omission produces a distinct failure mode whose remedy is not "do R harder."

The test's teeth: a clause is discharged by the same actor that benefits from skipping it, and produces no record of the skip. An operation produces an artifact whose *absence* is a countable event.

**Operation → runtime phase. The unimplied-ordering test.** Promote further only when correctness depends on a *relation between seats* — what must be true before, what must be unreachable from where — that no single seat can check, **and** the relation is not already implied by an existing FSM edge. Plus: a distinguishable enforcement signature at ≥2 seats, and omission detectable from the run record.

Both criteria are about observability of omission and relations between seats. Neither invokes the letter.

## 2. Seven new candidates from verified gaps

| # | Name | Gap (verified) | Class |
|---|---|---|---|
| 1 | **Stipulate** | `experiment/store.go:33-50` ships `Hypothesis`/`Status`/`MetricBefore`/`After`/`AgentDecision`-vs-`Decision`/`GitSHA` — a full pre-registration schema, gated Act+Reflect — and the main evidence/quality stream reuses none of it. Acceptance is authored *after* the result is known, by the actor being graded. | **SEM** |
| 2 | **Spread** | `Scores()` returns six objectives; `ToolErrorRate` is provably constant 0 (`loop.go:246-249` emits only `"success"`/`"tool_use"`, so `aggregate.go:81`'s `== "error"` never fires); `ToolDenialRate` and `ApprovalRate` have no writer at all. The fourth, `outcomeScore`, encodes termination mode. `Dominates` is a 2-D cost frontier plus a completion bit, and nothing says so. | **SEM/CAP** |
| 3 | **Strand** | `Evidence.FileActivity` is captured (`loop.go:265`) and then **structurally discarded**: `aggregate.go:14-24`'s `evidenceRecord` has no `file_activity` field, so it is dropped at unmarshal. The one field that could bind a durable row to a source domain dies at the Compound boundary. | **SEM/CAP** |
| 4 | **Second** | `ParetoFront` returns the input unchanged when `len ≤ 1` (`signal.go:91-93`), so `BestApproach`/`BestSummary` promote an **n=1** row to "best approach" and `Suggest` templates it into Orient. | CAP |
| 5 | **Subordinate** | `session.go:82-91` concatenates three independent summaries of the same store (`formatQualityHistory`, `BestSummary`, `Suggest`) with no arbiter. They can and do disagree. | POL |
| 6 | **Sample** | `Aggregate` is Compound-gated (`agent.go:247`), so abandoned sessions write nothing; every recorded session walked the full FSM. The store is selection-biased by construction. | CAP |
| 7 | **Signal** | `ResetRateCounts` is documented "call on phase transition" with zero callers, and `hooks/types.go:8-13` has no `PhaseTransition` event. The FSM edge is unhooked, unobserved, and side-effect-free. | CAP |

### Full contracts — the best three

**Stipulate (SEM).** *Input:* the plan Decide committed to. *Trigger:* mechanical, once, at the Decide→Act edge, before the first Act turn. *Transformation:* `plan → (plan, acceptance predicate)` where the predicate is mechanically evaluable (named test, build command, exit status, file-state assertion) and is written to `~/.skaffen/warrants/<session>.jsonl`, a namespace **Act cannot write**. A plan admitting no predicate is stipulated `acceptance: none` — itself a grade. *Output:* a warrant row `{session, plan_digest, predicate_kind, predicate_arg, minted_at_turn}`. *Consumers:* Reflect (redeems it — its prompt at `session.go:159-169` already runs tests and discards the verdict); Compound (writes `TestsPassed`/`BuildSuccess` from it); Sunset (lapses rows whose warrant later fails). *Pace:* per-plan — between the turn clock and the session clock. *Expiry:* redeemed or void at session end; unredeemed warrants are a countable defect. *Does not collapse into:* Decide has no durable output of any kind; the hypothesis-formation instruction is injected into **Act**, not Decide (`session.go:96-97,111`). Reflect judges post-hoc. Compound emits rates.

**Spread (SEM/CAP).** *Input:* the ranking basis + the read window. *Trigger:* before any `Dominates` comparison that will reach a prompt. *Transformation:* `scale → validated scale + degeneracy report`; axes with zero variance across the window are excluded from dominance and named. *Output:* an axis-health row. *Consumer:* `ParetoFront`, `BestApproach`, `Suggest`. *Pace:* per read. *Does not collapse into:* a unit test — a test asserts a fixed expectation; this asserts a property of live data whose violation is the normal case here.

**Strand (SEM/CAP).** *Input:* a durable row + the source domains its session touched. *Trigger:* at Compound (bind) and at Orient read (check). *Transformation:* `row → row + source-domain binding`, and at read, `binding no longer resolves → row is stranded and read-gated`. *Output:* a domain binding + a strand status. *Consumer:* the Orient injection; Sunset. *Does not collapse into:* `TaskType`, which is a five-way substring bucket on either the prompt (`inspire.go:43-59`) or tool names (`aggregate.go:101`) — neither is a source domain.

## 3. The semantic S — attacking the collapse, then the case

### The skeptical collapse, at full strength
For any duty D, find a seat S ∈ {gate table, router entry, prompt injection, evidence trigger, hook event, schema field} discharging D. Skaffen has all six seats; `SKAFFEN_PHASE` reaches hooks (`executor.go:248-252`), so even phase-scoped duties are hook-dischargeable. Since D is by construction expressible in code, such an S always exists. Therefore no D is ever an operation.

### Three attacks

**A1 — the test is unfalsifiable and eliminates the incumbents.** Apply it symmetrically: Observe is a prompt clause; Orient *is* a prompt injection (`session.go:80-91`); Decide has no durable output, no unique constraint, no router entry; Reflect is a string constant (`reflectPhaseGuidance`); Compound is one `if` at `agent.go:247`. **Every existing letter fails.** A criterion that deletes the incumbents is not a criterion for admitting candidates — it is a criterion for having no architecture. The skeptic notices the premise ("a runtime that cannot enforce its sixth phase…") and indicts the runtime; the correct inference is that the test has no failure case.

**A2 — the factual base is wrong where it matters most.** `builtin.go:20-22` registers web tools for `{Orient, Decide, Act}`. Effective signatures: Observe `{read,glob,grep,ls}`; Orient `+web +quality_history`; Decide `+web`; Act `+write/edit/bash +experiment`; Reflect `+bash, edit{RateLimit:3,RequirePrompt}, log_experiment`; Compound `+bash, edit/write{AllowedGlobs}, −grep`. **Six phases, six distinguishable signatures, three constraint kinds in live use.** "Observe and Decide are byte-identical" and "cardinality 3" are artifacts of reading `defaultGates` before `RegisterBuiltins` runs. This does not win phasehood — but it removes the argument the skeptic called decisive.

**A3 — the decomposition-of-invariants fallacy, and the experiment already ran here.** Collapsing an invariant into its enforcement points and declaring it redundant is a general fallacy; every invariant decomposes that way. Whether the pieces cohere when nobody owns them is an empirical question, and **this repo already answered it**: the warrant duty shipped as a clause — `TestsPassed`, `BuildSuccess` (`signal.go:29-30`), `ToolDenialRate`, `ApprovalRate` (`:39,:44`), with `Scores()` already ranking on the last two — and all four are permanently unwritten. The consequence is not cosmetic: three of six Pareto objectives are constant, the fourth is a termination flag, so `Dominates` silently reduces to cost, and `Suggest` returns "Break into smaller steps / reduce context" to Orient as *quality*. **The loop compounds thrift and calls it learning.** The skeptic's recommendation — "ship the field before the check" — proposes a fifth iteration of the thing that is 0-for-4.

### The positive case: **Stipulate**

The one thing a schema field provably cannot carry is an **information-set ordering**. A clause "record a warrant" at Compound cannot distinguish a predicate authored before the result was known from one authored after — the row is byte-identical either way, written by one actor. Only material separation in time *and* store makes the difference observable. That is a relation between seats, and it is the exact defect that makes `Human.Outcome` worthless today: `loop.go:246-249` emits only `"success"`/`"tool_use"`, and `aggregate.go:89-90` takes the **last** turn — which is by construction the turn that stopped calling tools. Every normally-terminating session is a success.

Stipulate meets the §1 test: skipping it today is invisible (there is no artifact whose absence you could count); as an operation, the unminted warrant is a countable defect. Its output type — a pre-registered refutation condition — is emitted by no incumbent. And `internal/experiment` proves the shape works in this codebase; it simply was never wired to the loop that learns.

## 4. The runtime S, under a repaired substrate — and the answer is still no

**Contract.** Stipulate-as-phase, seated between Decide and Act. Gate signature: write to the warrant namespace, **no** repo write; and — genuinely new — a *negative* constraint on Act, which today has `"write": nil` (`registry.go:60`), i.e. unconstrained, and can therefore overwrite its own acceptance criteria. `GateConstraint.AllowedGlobs` can express that. That is a non-empty delta at three seats: gate table, FSM ordering, evidence trigger.

**Add it now? No — for a better reason than the skeptic's.** Not because the runtime cannot express phases (§A2 shows it can), but because **the ordering is already implied by an existing edge**. The FSM is forward-only (`phase.go:40-47`), so "after Decide, before Act" is guaranteed by the sequence; minting at the Decide→Act edge gets the invariant for zero letters. A phase earns its keep only when the operation must recur or interleave, and Stipulate is once-per-plan.

**Re-ask when** the FSM gains a back-edge (mid-run re-planning), because then the mint must recur and needs its own seat — *and* when `Act`'s `write` gate carries a non-`nil` constraint, without which the warrant store is not actually protected from the actor it grades.

## 5. Comparison

| | **Stipulate** | Substantiate | Sunset | Scout/Trace | no-S |
|---|---|---|---|---|---|
| New object type | Yes — pre-registered refutation condition | No — a value on an existing field | No — a status flag | A report | — |
| Resists Goodhart | **Yes** — grader's information set is restricted by ordering | **No** — same actor, post-hoc, self-attested | n/a | No | n/a |
| Omission countable | **Yes** — unminted warrant | No — an empty field, exactly like the four already empty | Yes | No | No |
| Enforcement delta | Warrant namespace + negative Act constraint (both absent) | One branch | Two filters | ∅ (Decide's set) | ∅ |
| Epistemic safety | **Strongly +** — only candidate that *removes* information from the grader; adds no reader-facing writer | + | + (the missing remover) | − (writer, no grade) | − (false-warrant generator is the null's) |
| Pace / shear | Per-plan — mints on the plan clock, redeems on the turn clock, lapses on the session clock; the clock split is what makes redemption informative | Per-turn | Operator cadence | Undefined | — |
| Cost | One store, one edge hook, two consumers | One field | ~30 lines | Cheap, shouldn't ship | 0 |
| Shippable today | Yes, in two stages | Yes | Yes | Yes | — |

Stipulate **strictly contains** Substantiate (Substantiate is the redeem half, minus the ordering) and **enables** Sunset (a lapsed warrant is a mechanical retirement trigger; Sunset alone has only recency). It is not a rival to either — it is the half without which both are self-graded. Against no-S: no-S still wins the *letter* question outright, and my champion concedes it — Stipulate ships as an operation with a seat at an existing edge, not as a seventh letter.

## 6. Minimal pilot

**Stage 0 — retrospective, runs today, zero instrumentation.** Compute per-axis variance of `Scores()` across `~/.skaffen/mutations/*.jsonl`. **Predicted:** three axes at exactly zero variance, `outcomeScore` ≈ 1 for every normally-terminating session. Also count `BestApproach` calls resolving on `len(signals) == 1`. *This measures the false-warrant regime's size before spending anything.* Stated limitation: `Evidence.ToolCalls` records tool **names** only, so "did a test actually run" is **not recoverable** from the existing store — which is itself the finding.

**Stage 1 — live, one edge.** At the Decide→Act transition, write one warrant row. Reflect redeems it against its existing test run. Compound writes `TestsPassed`/`BuildSuccess` from the redemption.

**Measurable outcome:** the **disagreement rate** — sessions where `Human.Outcome == "success"` and the redeemed warrant says fail. Today that number is unmeasurable and unbounded; it is the quantity the entire compounding loop rides on.

**Kill criterion:** disagreement rate ≈ 0 (termination already coincides with verification — keep only the honest default), **or** a hand-graded sample in which >⅔ of minted predicates are unfalsifiable ("it compiles", `acceptance: none`) — in which case the mint is theatre and expiry-by-age is cheaper.

**Reversal condition:** if `Human.Outcome` is removed from `Scores()` and `Suggest`, Stipulate loses its consumer and should be deleted. Secondarily: if `Act`'s `write` gate is never constrained, the warrant store is writable by the graded actor and the ordering guarantee is nominal — ship the constraint or drop the claim.

---

## Advocate verdict

**A genuinely distinct semantic S exists: Stipulate** — pre-registration of a mechanically evaluable acceptance predicate at the Decide→Act edge, into a store the acting turn cannot write. It is distinct because its content is an *ordering of information sets*, which no schema field can carry; it is warranted because the clause-shaped alternative has already been tried in this repo four times and produced four permanently empty fields and a ranking basis that is three-quarters constant. Ship it as an operation seated at an existing edge.

**A runtime S: no, not now** — but on the ground that the forward-only FSM already implies the ordering, not on the ground that the runtime cannot express phases. It can: six phases, six distinct effective gate signatures, three constraint kinds.

## What the skeptic still gets right

- The seat inventory is real and I confirmed the part I most wanted to refute: hooks do receive `SKAFFEN_PHASE`.
- Compound writes no propositions, so Sentinel's subject term is genuinely empty. Stipulate's subject — a plan — exists only as untyped model text; it needs one new durable object too, smaller than Sentinel's but not free.
- The letter costs seven enumerations and two are already out of sync for the *sixth* member. Charging a candidate with phasehood there is a promotion with no duties attached.
- Nothing in any of the four passes, including this one, is measured. My ordering is reasoned over code facts.
- Substantiate and Sunset are both worth doing regardless. My disagreement is about sequence and shape, not merit.

## What evidence would settle this

1. **Per-axis variance of `Scores()` over the live store.** If three axes are non-degenerate, my central empirical claim is wrong and the clause-remedy case strengthens sharply.
2. **The disagreement rate** between a redeemed warrant and `Human.Outcome`. Near zero → the whole S question is decoration.
3. **Predicate authorability**, hand-graded: what fraction of real plans admit a falsifiable acceptance predicate. Low → Stipulate is age-based expiry in costume.
4. **Whether a field can be made to fill itself.** Ship `TestsPassed` as a clause on Compound with no operation owning it, and measure the write rate after ten sessions. If it fills, the collapse argument wins outright and I withdraw. That is the cleanest single experiment in this entire corpus, it costs almost nothing, and nobody has run it.
