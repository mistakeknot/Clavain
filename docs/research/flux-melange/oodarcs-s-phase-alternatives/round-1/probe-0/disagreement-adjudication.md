# disagreement-adjudication — round 1

## Findings Index
- [P1] pilot-underspecification-precedes-confounding — Claim (1) holds as the defect of record; claim (2) is demoted from rival defect to binding runtime constraint, and its strongest form holds under *both* readings of "read-only" (§Required output item 7)
- [P1] pilot-arms-land-in-different-signal-buckets — A minimal read-only pilot session is by construction no-write/no-edit/read-heavy, so `inferTaskType` routes it to `docs.jsonl` while the no-S null arm routes to feature/bug-fix/refactor — the arms are never compared to each other (§Required output item 7)

## Findings

### pilot-underspecification-precedes-confounding
- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md:119` (§Required output, item 7)
- **What:** The two prior findings are not rivals. They stand in a specification-then-feasibility order, and the order is decidable, not a taste call.

  Claim (1) — the sentence names no measured quantity, threshold, cycle count, recorder, or outcome — is literally true on the text: item 7 is *"A minimal read-only pilot for the top two choices plus the no-S null."* Eleven words, no dependent variable.

  Claim (2) — "read-only is unachievable because every turn writes the evidence file Compound aggregates" — **presupposes an outcome measure that (1) correctly observes is not named.** It reaches its conclusion by imputing `QualitySignal` as the pilot's outcome, because that is the only aggregate the runtime produces. That imputation is reasonable, but it makes (2) *conditional on a repair of (1)*. An unspecified pilot has no measure to confound.

  **Verdict: (1) holds as the defect of record.** It is strictly upstream. (2) is not falsified — it is demoted from *defect* to *constraint*: it is the binding fact about this runtime that any repair of (1) must satisfy, and it pre-emptively rules out the first repair a reader would reach for ("just use the quality signal").

  (2)'s stated form is, however, *weaker than it needs to be*, and the contradiction is what exposes that. As written it depends on the operational reading of "read-only" (no writes to disk). The charter never disambiguates the word, and there are two readings — the charter's own §41 ("scout reports cannot become evidence directly") invites the *epistemic* reading (no promotion to durable knowledge). **Both readings fail, for different code reasons:**
  - *Operational reading fails* at `internal/agentloop/loop.go:286` — `l.emitter.Emit(ev)` is unconditional per turn inside the loop body, gated on nothing. A Scout turn that only reads still appends a record.
  - *Epistemic reading fails* at `internal/agent/agent.go:246-253` — `mutations.Aggregate` runs on the Compound phase over the **whole session file**, so a scout turn that is never "promoted" still moves `Hard.TurnCount` (`aggregate.go:73`), `Hard.TokenEfficiency` (`:66-72`), `Soft.ToolErrorRate` (`:85`), and the persisted bucket. The signal is then read back by Orient (`internal/mutations/signal.go:17-18`). The scout turn reaches durable, Orient-visible state **without ever being promoted** — which is precisely what the epistemic reading of "read-only" promises cannot happen.

  So the correct merged position: item 7's fatal flaw is the missing dependent variable (1); "read-only" is additionally a word the charter cannot honor under either of its two available meanings, and it must either be defined or dropped.
- **Evidence:** charter:119 (full text of item 7); charter:41 (competing epistemic sense of "cannot become evidence directly"); `internal/agentloop/loop.go:286` (unconditional per-turn `Emit`); `internal/agent/agent.go:246-253` (Compound aggregates the whole session file); `internal/mutations/aggregate.go:66-95`; `internal/mutations/signal.go:17-18` ("Written by the Compound phase, read by Orient on subsequent sessions").
- **Suggestion:** Replace item 7 with a pilot spec that names, per arm: the dependent variable and where it is recorded; the decision threshold and direction; the number of cycles; and at least one outcome pattern that would favor the no-S null. Do not name `QualitySignal` as that variable without first adding a scout-turn exclusion to `Aggregate`.
- **Remediation:** Amend item 7 to require each pilot to name its dependent variable, recorder, threshold, cycle count, and a stated result that would favor the no-S null, and to define "read-only" as *epistemic* (no durable-store mutation attributable to the scout turn) — since operational read-only is unachievable in this runtime.

### pilot-arms-land-in-different-signal-buckets
- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md:119`; mechanism at `internal/mutations/aggregate.go:99-135` and `internal/mutations/store.go:89-129`
- **What:** New insight the contradiction exposes. If the charter repairs item 7 the obvious way and uses the quality signal as the outcome, the pilot fails in a way *neither* prior finding names: the two arms' results are written to **different files** and never compared.

  `inferTaskType` (`aggregate.go:99-135`) classifies a session from its tool-call mix, and its first branch is `case !hasWrite && !hasEdit && hasGrep: return TaskDocs`. **A "minimal read-only pilot" session is by construction a session with no writes, no edits, and heavy reads/greps** — it matches that branch exactly. `WriteForType` (`store.go:97-129`) then appends the signal to `docs.jsonl`. The no-S null arm, run on real work, returns `TaskFeature`/`TaskBugFix`/`TaskRefactor` and lands in a different bucket file. Orient reads per-type. The S arm and the null arm therefore accumulate in separate per-type histories and are never scored against one another — the comparison item 7 exists to make cannot occur.

  Compounding it, the metric is **mechanically responsive to phase count, independent of learning quality**: `Scores()` (`signal.go:~58-80`) penalizes turn count and rewards `tokens_out/tokens_in`. Adding an S phase strictly adds turns, and scout turns are read-heavy (large tool results in, short reasoning out), so token efficiency falls too. Any S candidate loses on both axes for reasons unrelated to whether it improved transfer.

  That is the exact mirror of settled finding (1): **item 7 as written cannot lose; item 7 as a reader would implement it cannot win.** Both failures trace to the same absence — no named, phase-count-invariant outcome variable — which is the strongest joint argument that (1) is the root defect.
- **Evidence:** `internal/mutations/aggregate.go:133` (`case !hasWrite && !hasEdit && hasGrep: return TaskDocs`); `internal/mutations/store.go:89-95` (`taskTypeFile`), `:97-129` (`WriteForType` appends to the per-type file); `internal/mutations/signal.go:17-18` (signals read by Orient), `Scores()` penalizing turn count; charter:119.
- **Suggestion:** Require the pilot to hold task type fixed across arms (or record arm identity as an explicit field rather than inferring it from tool mix), and to use a per-turn or per-outcome normalized measure rather than raw turn count and token efficiency, which are monotone in phase count by construction.
- **Remediation:** Add to item 7 the requirement that the pilot's outcome measure be invariant to added phase count and that both arms be recorded under the same task-type bucket, or the comparison is void.

## Verdict
Claim (1) holds and is the defect of record: item 7's missing dependent variable is strictly upstream of claim (2), which presupposes an outcome measure the charter never names. (2) survives as a binding runtime constraint rather than a rival defect, and is stronger than stated — "read-only" fails under both its operational and epistemic readings, at `loop.go:286` and `agent.go:246-253` respectively. This is not an irreducible taste call; the only genuine ambiguity is which sense of "read-only" the charter meant, and the charter must simply say.
