# fd-fused-grading-arm-allocation — round 2

Fused lens: fd-foraging-exploration-generator (patch depletion, arms, budgets, regret,
non-stationarity) × fd-fused-assay-limited-foraging (grading capacity, probe ladder,
the mark, melt-vs-delete, arm-indexed failure records). Intersection-only: every
finding below dies if either parent is removed.

## Findings Index

- [P0] stint-split-setting-candidate — the charter's line-71 slot (a candidate that changes exploration/exploitation POLICY and emits no report) is still unfilled; file **Stint**, whose whole output is next cycle's probes-per-punch rate (§Candidate-generation requirement (71), §Per-candidate contract (75-89))
- [P1] probe-budget-meter-is-a-dead-ratchet — `ResetRateCounts` has zero production callers, so the only runtime probe meter never renews and is charged at dispatch; every candidate's field-7 "bounded budget" is either unenforceable or an absorbing barrier (§Hard gates (100), §Per-candidate contract item 7 (85))
- [P1] write-key-read-key-censoring — probe-shaped sessions are graded into a bucket no allocating phase reads, because the write key is `inferTaskType`(tool calls) and the read key is `ClassifyTask`(description); the exploration arm is never assayed and its absence reads as a graded negative (§Per-candidate contract item 4 (82), §Lessons item 5 (41))
- [P2] pareto-front-has-no-discovery-axis-and-no-floor — the grading scale is six cost dimensions, so a probe-heavy arm is Pareto-dominated a priori and drops out of `BestApproach` with no sampling floor to readmit it (§Comparative criteria (109,116), §Pilot contract (150))

## Findings

### stint-split-setting-candidate

- **Severity:** P0
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:71`, `:75-89`;
  runtime seat at `internal/tool/registry.go:20-22,63-65,116-120,242-258`.
- **What:** The charter makes two candidate classes mandatory (line 70 subtractive,
  line 71 policy-changing). Round 1 filled the subtractive slot several times over —
  Reprove removes authority, Assay re-marks, Frontier retains nulls, Trace and Warrant
  are artifact/contract candidates. Every one of them *emits something*. Not one of
  them changes what the loop does with its next unit of attention. The field is about
  to be scored with the line-71 class empty, which guarantees an artifact-class winner
  by construction rather than by comparison — and the settled epistemic-separation
  result already showed that grading products ranks candidates in inverse order of
  governability. So the missing class is exactly the class the tournament is least
  equipped to notice it is missing.

  **Contract — Stint** (the shift's allotted measure at the furnace):

  1. *Input/preconditions.* Last cycle's ledger: probes issued (count of probe-class
     tool calls), probes graded (rows that received a mark), and graded-stock age.
     Precondition: at least one completed cycle exists.
  2. *Transformation.* Compute one number — the probes-per-punch exchange rate for the
     next cycle — and install it. Nothing else. Stint reads no domain material and
     forms no belief about the task.
  3. *Output and consumer.* Not a document: a mutation of the gate matrix. Consumer is
     `Registry.Execute`, which enforces it as `GateConstraint.RateLimit` on probe-class
     tools (`web_search`, `web_fetch`, and any candidate's probe tool), plus the
     re-arm call on phase transition.
  4. *Authority/store/read filter/expiry/failed-probe retention.* Authority: none —
     Stint asserts no claim about the world, so it cannot launder authority and is
     unmarkable by construction (this is the whole point of a policy candidate).
     Store: the gate matrix + a rate ledger, never the signal store, so it can never be
     read as evidence by Orient. Read filter: n/a; there is no proposition to filter.
     Expiry: the rate expires at the end of the cycle it was computed for — a rate that
     outlives its cycle is the stationary-ratio failure. Failed probes: a burnt,
     ungraded budget is retained as a *rate* input (it lowers next cycle's allowance),
     not as a claim.
  5. *Trigger and pace layer.* Once per cycle boundary, slow layer. Off-cycle trigger:
     graded-stock age crosses a threshold (the furnace is behind) or the ungraded pile
     exceeds the rate — both are the assay half acting as the patch-depletion signal.
  6. *Re-entry.* There is no re-entry, because there is no artifact to re-validate.
     Stint's effect appears only as a different tool allowance in the next Orient/Act.
  7. *Runtime delta.* Real and small: `GateConstraint.RateLimit` already exists
     (`registry.go:20-22`) and is already enforced (`registry.go:242-258`); Stint needs
     (a) a write path that sets RateLimit per cycle, and (b) the `ResetRateCounts` call
     that today does not exist (see next finding). This is the only candidate in the
     field whose field-7 answer is a *use* of existing enforcement rather than a
     request for new machinery.
  8. *Overlap.* None with Observe/Orient/Reflect/Compound — all four transform
     material; Stint transforms the allowance to acquire material. It overlaps only
     with the costrouter, which sets model spend but never probe count.
  9. *Failure mode / Goodhart.* Grading-throughput gaming: the office grades fast and
     shallow to buy a bigger probe allowance. Countered by keying the rate on *marked*
     stock at a declared tier, not on rows written.
  10. *Cheapest pilot / losing condition.* Two arms on the corpus, identical turn
      budget, differing only in whether the probe allowance is fixed or Stint-set.
      Stint loses if validated-discovery-per-graded-unit does not beat the fixed-rate
      arm, or if it produces a monotone allowance (a rate that only moves one way is a
      ratchet wearing a policy costume).
  11. *Classification.* Not a phase. A **policy capability** on the cycle boundary —
      and the charter's own goal ("smallest coherent design", line 173) is better served
      by a capability that emits nothing than by a seventh letter that emits reports.

- **Evidence:** `registry.go:63-65` shows the project already ships exactly one
  allocation-shaped gate (`"edit": {RateLimit: 3, RequirePrompt: true}` in Reflect) —
  so the primitive Stint needs is present, exercised, and currently used for precisely
  one hand-tuned constant that nothing recomputes.
- **Suggestion:** Admit Stint to the shortlist as the line-71 entry and score the field
  with it present; if it is eliminated, eliminate it explicitly rather than by absence.
- **Intersection:** Foraging contributes the object (the allocation policy is the thing
  under review, not the report). Assaying contributes the denominator that makes the
  policy computable — probes-per-*punch*, where the punch is a graded mark at a declared
  tier, not a row written. Foraging alone yields a bandit with an invented budget;
  assaying alone yields a mark with no consequence for the next unit of attention.

### probe-budget-meter-is-a-dead-ratchet

- **Severity:** P1
- **Where:** `internal/tool/registry.go:116-120` (`ResetRateCounts`, zero production
  callers — `grep -rn ResetRateCounts --include="*.go" .` returns only `registry.go`
  itself and `registry_test.go:484`), `registry.go:242-258` (charge site),
  `registry.go:63-65` (the sole live RateLimit).
- **What:** The charter's fourth hard gate is "a bounded trigger/stop rule"
  (`:100`), and field 7 asks each candidate for the runtime delta that enforces it.
  Skaffen has exactly one primitive that can bound a probe count, and it is broken in
  both directions at once:
  1. **No renewal clock.** The comment at `registry.go:116` says "call on phase
     transition"; nothing calls it. OODARC is explicitly "coupled loops at multiple pace
     layers, not a mandatory linear sequence" (`:27`), so a phase is re-entered many
     times per session — but the counter is keyed by `Phase` and never cleared, so the
     allowance is spent once per process and never renews. Reflect's three edits are
     three edits *for the session*, not per Reflect.
  2. **Charged at dispatch, before any outcome.** The increment at `registry.go:256`
     happens before the sandbox check (`registry.go:262-272`) and before the tool
     runs. A probe rejected by the sandbox, or one that returns nothing, burns the same
     allowance as a probe that yields a graded discovery. There is no refund and no tier
     distinction — a cheap touchstone screen and a costly dispositive probe cost one
     unit each.
- **Concrete failure:** Candidate Trace declares "a pre-registered, budgeted probe" and
  passes the bounded-trigger gate on the strength of RateLimit. In a real session the
  loop enters Orient, spends its k probes in the first pass (several on sandbox-rejected
  or empty fetches), re-enters Orient after Act reveals a contradiction — the moment
  non-stationarity actually justifies exploring — and the gate refuses every probe for
  the remainder of the session. The ledger afterwards is indistinguishable from a
  ledger in which the domain was probed and found barren: the arm was retired by
  exhaustion, not by evidence. That is absence-of-assay wearing a graded negative's
  clothes, and it will be read by the next cycle's prior as a real negative.
- **Suggestion:** Two lines. Call `ResetRateCounts()` on every phase entry in the agent's
  phase dispatch (`internal/agent/agent.go` around the `LoopConfig` construction at
  `:235-240`), and move the increment at `registry.go:256` to after the sandbox check at
  `:262-272` so a probe the runtime refuses to run is not charged. Then the gate is a
  renewing per-entry allowance rather than a session-lifetime ratchet.
- **Intersection:** Foraging contributes patch renewal and non-stationarity — an
  allowance that cannot renew is an absorbing barrier, and the environment shifts most
  exactly when the budget is already spent. Assaying contributes the discrimination that
  makes it a *lie* rather than merely a limit: exhausted-and-unprobed must be
  distinguishable from probed-and-graded-barren, and the charge-at-dispatch site
  guarantees it is not. Foraging alone files "no stop rule"; assaying alone files "no
  expiry on the retirement record"; only the product notices that Skaffen's one stop
  rule *manufactures* false negatives.

### write-key-read-key-censoring

- **Severity:** P1
- **Where:** write key `internal/mutations/aggregate.go:93,101-136` (`inferTaskType`),
  read key `internal/mutations/inspire.go:20-25,43-59` (`ClassifyTask`), routing
  `internal/mutations/store.go:99-131` (`WriteForType`) and `best.go:8-17`
  (`ReadRecentForType`), injection `internal/session/session.go:86-91`, sole call site
  `internal/agent/agent.go:246-253`.
- **What:** Stock is filed under one key and drawn under another. `WriteForType` files
  the session's single signal into `<taskType>.jsonl` where the type is inferred from
  the *tool calls actually made*; `Inspire` draws from the bucket named by classifying
  the *task description string*. The two functions share no code and cannot agree.
  Worse, `inferTaskType`'s switch (`aggregate.go:107-118`) recognises only
  write/edit/bash/grep/glob/read — the probe-class tools registered for Orient at
  `internal/tool/builtin.go:20-22` (`web_search`, `web_fetch`) match no case at all.
- **Concrete failure:** A session opened as "add cross-domain retry backoff" →
  `ClassifyTask` sees "add" → reads `feature.jsonl`. The session runs a Scout-shaped
  Orient: mostly `web_search`/`web_fetch`, a few reads, no writes. At Compound,
  `inferTaskType` sees no write, no edit, some read → returns `TaskDocs`
  (`aggregate.go:126`); a purer probe session with no reads at all falls through to
  `TaskGeneral` (`:135`). The row is filed in `docs.jsonl` or `general.jsonl`. No
  feature-described task will ever read it. Therefore `feature.jsonl` — the bucket that
  actually conditions the next feature session's Orient prompt — contains *only sessions
  that wrote code*, i.e. only sessions that exploited. The prior over "what works on
  feature tasks" is computed from a sample selected for having exploited, and the
  exploratory arm's rows, including its retained negatives, are structurally unreachable.
  Any candidate whose field-4 answer is "retention of failed probes: written to the
  signal store" satisfies the contract on paper while being provably unreadable — the
  charter's lesson 5 ("do not erase failed probes", `:41`) is honoured in the write and
  voided in the read.
- **Suggestion:** Smallest fix that makes retention mean something: have
  `Aggregate` carry the `ClassifyTask(taskDesc)` value that opened the session on the
  `QualitySignal` (a `RequestedType` field alongside `TaskType` in `signal.go:17-25`) and
  have `WriteForType` file under the requested key, keeping the inferred key as a second
  index. Read and write then share one key, and a probe-only session lands in the bucket
  that asked for it.
- **Intersection:** Foraging contributes the queue and the censored prior — which stock
  ever reaches the furnace, and the regret of the row never drawn. Assaying contributes
  the mark-key discipline: a punch is worthless if the ledger indexes it under a
  different key than the one the reader uses, and a bucket that contains only
  successfully-exploited sessions is a maker grading its own output. Foraging alone
  files "no arm-indexed failure record"; assaying alone files "no read filter"; the
  cross term is that the record *exists*, is *indexed*, and is *unreachable from the
  allocation path* — which neither parent's checklist has a slot for.

### pareto-front-has-no-discovery-axis-and-no-floor

- **Severity:** P2
- **Where:** `internal/mutations/signal.go:54-67` (`Scores`), `:71-86` (`Dominates`),
  `:90-107` (`ParetoFront`), consumed at `best.go:8-17` and surfaced to Orient via
  `best.go:20-39` → `inspire.go:25-27` → `session.go:86-91`.
- **What:** Even if the previous finding's key mismatch were fixed, the grading scale
  itself retires the exploration arm. `Scores()` returns six dimensions:
  token efficiency, negative turn count, negative error rate, negative denial rate,
  approval rate, outcome. Five are costs and one is a binary outcome; none measures
  discovery, transfer, or retained disconfirmation. A probe-heavy session has *more*
  turns, *lower* output-to-input ratio (fetched pages inflate input), and *higher*
  tool error rate (dead links, sandbox refusals) — it is dominated on three axes and can
  win on none. `ParetoFront` (`:90-107`) has no epsilon, no recency term, and no
  sampling floor, so once an exploit-shaped session dominates it, no exploratory row
  ever reappears in `BestSummary`, and `Suggest` then emits "Break into smaller steps"
  and "Reduce context" (`mutate.go:46-62`) — literal instructions to explore less —
  into the next Orient prompt.
- **Concrete failure:** The charter's own pilot proposes to blind-score "validated
  mechanism discoveries" and "disconfirmed hypotheses retained" (`:150-151`). The
  runtime that would carry a promoted S candidate can represent neither, and its
  standing advice channel actively penalises the behaviour the pilot is trying to
  measure. Ship any S without touching this and the loop grades it barren within a
  handful of cycles regardless of what it found.
- **Suggestion:** Add a floor rather than a metric: reserve one slot in
  `ParetoFront`'s output for the most recent row from an under-sampled arm
  (a `withFloor(front, all)` wrapper in `best.go:8-17`), so a dominated exploration row
  is re-presented periodically instead of permanently melted. A floor is cheaper and
  less gameable than inventing a discovery score.
- **Intersection:** Foraging contributes the sampling floor and the non-stationarity
  argument for readmitting a down-weighted arm. Assaying contributes the observation
  that Pareto dominance over cost axes *is* the office's grading scale, and that an
  office with no assay for gold will certify every gold sample as slag — retirement by
  scale rather than by evidence. Foraging alone files "no discovery-rate metric";
  assaying alone files "self-certification by throughput" (already settled); neither
  alone reaches the specific claim that the *dominance relation* is the retirement
  mechanism and that a floor, not a metric, is the minimal remedy.

## Verdict

The tournament is about to score a field in which every filed candidate emits an
artifact, leaving the charter's mandatory policy-changing class (line 71) empty — file
**Stint**, whose entire output is next cycle's probes-per-punch rate and whose runtime
delta is a *use* of `GateConstraint.RateLimit` rather than new machinery. Underneath
that, the three mechanisms Skaffen would use to enforce any winning S all fail in the
same direction: the one probe meter never renews and is charged before the probe runs,
exploratory sessions are filed under a key no allocating phase reads, and the grading
scale is six cost axes with no floor — so exploration is retired by exhaustion, by
routing, and by dominance, three times over, without a single negative ever being
graded. Fix the two-line renewal and the key mismatch before any pilot, or the pilot
will measure the runtime's censorship rather than the candidate.
