# fd-fused-warranted-variation — round 2

Fused lens: fd-foraging-exploration-generator (variation rate, patch depletion, search
budget, regret, trigger/stop rules) × fd-fused-graded-allocation (issuing authority,
grade, expiry, dual licence to mint vs to spend). Only cross-term findings admitted.
Generation before criticism: one new contract filed first, then two verdicts and one
clustering-criterion refinement.

## Findings Index

- [P0] pilot-single-rate-confound — the pilot runs each candidate at exactly one unpre-registered rate, so a losing arm cannot be told from a mis-tuned licence (§Pilot contract 142-157)
- [P1] season-cohort-warrant-contract — new contract: an S whose unit is a cohort minted at a pre-committed rate under an epoch warrant; the only design in the field where doubled yield distinguishes a richer patch from a looser licence (§Candidate-generation requirement 71, §Per-candidate contract 75-89)
- [P1] frontier-dedup-is-a-mint-accelerant — Frontier's fingerprint guard cheapens minting while no contract field issues a mint quota, so the lead ledger grows monotonically into a fixed-length Orient prompt (§Hard gates 100, §Per-candidate contract 82)
- [P2] cluster-by-minting-authority-not-verb — Scout vs Speculate is adjudicated on the wrong axis; the deciding difference is issued vs self-tasked minting authority, not search behavior vs epistemic status (§Mandatory disagreement 124, §Candidate-generation requirement 73)

## Findings

### pilot-single-rate-confound

- **Severity:** P0 — corrupts the tournament outcome.
- **Where:** target §Pilot contract independent of current Skaffen quality aggregation,
  lines 142-157 ("Compare equal-budget traces under: baseline OODARC/no-S; top candidate
  A; top candidate B", and the losing condition at 157).
- **What:** Every candidate now in the field (Trace, Assay, Frontier, Reprove, Scout,
  Season below) is a *rate-bearing* operation: it fires some number of times per epoch.
  The pilot fixes total budget equal across arms but never fixes or pre-registers the
  rate at which the S arm converts that budget into probes. Arm A therefore differs from
  arm B in two ways simultaneously — which operation, and how often it fires — and the
  losing condition at line 157 fires on the conjunction. A candidate that is right in
  kind and wrong in cadence is recorded as a dead operation and eliminated permanently.
  This is the tournament's terminal evidence, so the recommendation ("smallest coherent
  design") ends up decided by an untuned, unstated hyperparameter.
- **Evidence:** The charter's own comparative criteria include "pace/shear coherence"
  (line 112) and the hard gates require "a bounded trigger/stop rule" (line 100) — both
  are rate properties — yet the pilot's outcome list (148-155) contains no rate term and
  no per-unit denominator; "time/turns to useful probe" (152) is a latency, not a rate.
  Skaffen shows the failure concretely: `complexityTracker.shouldEscalate()`
  (internal/costrouter/complexity.go:100-127) issues an escalation on ungraded behavioral
  counters, and `reset()` (complexity.go:131-135) zeroes `cheapTurns`, `uniqueFiles`, and
  `consecFailures` immediately after, so the issuance rate is unrecoverable after the
  fact. Any pilot run against a single unrecorded rate reproduces exactly this: a yield
  number with no denominator.
- **Suggestion:** Pre-register a **rate ladder**, not a single setting: run each of the
  two candidate arms at two pre-committed rates (k and 2k probes per epoch, k declared
  before the corpus is opened), and record probes-issued per arm as a first-class pilot
  output alongside the six blind-scored measures. A candidate loses only if it fails at
  its *best* pre-registered rate. The ladder also buys the discriminator the whole
  tournament lacks: yield that doubles when the rate doubles is a looser licence
  (constant marginal value, exploration is not paying); yield that rises at fixed rate is
  a richer patch. One extra arm per candidate, four arms total plus the null.
- **Intersection:** Foraging supplies the marginal-value reading — yield as a function of
  search rate, and the fact that a single point on that curve is uninterpretable.
  Graded-allocation supplies the pre-registration and the issuing discipline — the rate
  must be *declared by an authority before the corpus opens*, or the arm self-tasks its
  own denominator. Remove foraging and you pre-register a rate with no reason to vary it;
  remove the warrant half and you tune the rate adaptively during the run, which is
  precisely what makes the yield uninterpretable.

### season-cohort-warrant-contract

- **Severity:** P1 — files the charter's mandatory policy-changing candidate (line 71)
  and supplies the field's only rate/licence discriminator.
- **Where:** target §Candidate-generation requirement line 71 ("at least one candidate
  that changes the exploration/exploitation policy rather than emitting a report"), filled
  against §Per-candidate contract lines 79-89.
- **What — contract for `Season`:**
  1. **Input/preconditions:** the epoch boundary itself (N sessions, or a release/sprint
     tick). No task-state precondition; explicitly *not* entered by a state estimate.
  2. **Transformation:** issues a fixed-size cohort of k exploration warrants for the
     epoch and binds them to a declared patch list (domains/corpora to sample). The
     transformation is on *allocation*, not on knowledge: the epoch's exploration share
     is set once and cannot be revised inside the epoch.
  3. **Output/consumer:** a cohort warrant record (epoch id, k, patch list, issuer,
     expiry) consumed by the router/tool gate as an allocation constraint, and by the
     epoch-end review as the denominator for yield.
  4. **Authority/storage/read filter/expiry/failed probes:** issued by the same authority
     that sets the budget (config-level, not agent-level); stored in the allocation
     register, not the knowledge store; read filter is trivially satisfied because the
     cohort record carries no claims — it is a licence, not evidence; expires at the
     epoch boundary with no rollover (unspent warrants lapse, they do not bank); failed
     probes stay in the yield denominator by construction, since k is fixed ex ante.
  5. **Trigger/pace layer:** none — a pre-committed rate on the slow layer. This is the
     contract's whole point and the field's only non-trigger entry.
  6. **Re-entry:** each spent warrant re-enters as an ordinary probe under whichever
     probe contract survives (Trace); Season governs how many, not what.
  7. **Runtime enforcement delta:** a per-epoch counter that gates the exploration tool
     set — the first enforceable delta in the field that is a *quantity*, not a tool
     list. Skaffen has the hook and lacks the counter: `defaultGates`
     (internal/tool/registry.go:49-72) enumerates tools per phase, and `GateConstraint`
     already carries `RateLimit` with a per-phase counter
     (registry.go:242-258) — but the counter resets on phase transition
     (`ResetRateCounts`, registry.go:117-121), so no rate survives a phase change. Season
     needs one counter whose lifetime is the epoch, not the phase.
  8. **Overlap:** none with Observe/Orient/Reflect/Compound — they transform content;
     Season transforms the exploration share and emits no content.
  9. **Failure/Goodhart:** k becomes a quota to be filled with junk to prove the licence
     was used. Mitigation is that k is *fixed*, so quota-filling shows up as falling
     yield-per-warrant rather than as rising volume — the inflation is visible in the
     numerator instead of hidden in the denominator.
  10. **Cheapest falsifiable pilot / losing condition:** the rate ladder above run with
      Season as the rate-setter; Season loses if yield-per-warrant is flat across k and
      2k *and* across stable and shifted corpus segments — flat in both directions means
      the rate is doing no work and a trigger-entered candidate is strictly better.
  11. **Classification:** allocation policy — a side-loop at epoch cadence, not a
      semantic phase. It cannot pass semantic distinctness (it performs no epistemic
      transformation) and should not be asked to.
- **Evidence for the gap it fills:** every other contract in the field enters on a
  trigger computed from the agent's own state, which makes its generativity claim
  unfalsifiable: if yield doubles you cannot tell whether the world got weirder (richer
  patch) or the entry predicate drifted (looser licence), because the predicate is
  endogenous. Skaffen already runs the pathological version — `shouldEscalate()`
  (complexity.go:100-127) is a self-issued licence whose predicate is ungraded turn
  counters, and the charter's field 5 (line 83, "Trigger and natural pace layer")
  presupposes trigger entry, so the tournament as written cannot produce a
  constant-rate candidate unless one is filed explicitly.
- **Suggestion:** Admit Season into the shortlist as the field's policy arm and let it be
  the rate-setter for the pilot's ladder; do not let it compete for phasehood.
- **Intersection:** Foraging supplies the constant-rate design as an *identification
  strategy* — hold the search rate fixed and yield changes become patch-richness
  estimates. Graded-allocation supplies the cohort as the graded, issued, expiring unit
  and the no-rollover rule that stops an unspent licence from becoming a banked one.
  Parent A alone proposes an *adaptive* rate (yield-maximizing), which destroys exactly
  the identifiability the fused lens needs; parent B alone issues per-probe warrants
  whose count is endogenous to the agent, so the denominator floats.

### frontier-dedup-is-a-mint-accelerant

- **Severity:** P1 — adversarial verdict; decides Frontier's rank, and the cross term is
  what decides it.
- **Where:** the Frontier contract (settled: addressable lead ledger, nulls as first-class
  rows, fingerprint guard in `Store.Inspire`), against target §Per-candidate contract
  field 4 (line 82) and §Hard gates line 100.
- **What:** Frontier's fingerprint guard is a *spend*-side economy — it stops paying twice
  for the same probe. Its second-order effect is on the *mint* side: once each lead is
  deduplicated and cheap to retain, there is no cost to minting one, and no field in the
  eleven-field contract asks for a mint quota. Field 4 asks for grade, boundary, read
  filter, expiry, and retention of failed probes — every one of those governs what
  happens to a row *after* it exists. So Frontier as contracted grows monotonically:
  spend is bounded, mint is not, and a retained-null policy converts the ledger into a
  ratchet. The failure lands on the read side, which is fixed-length: leads enter Orient
  by the same path as `Inspiration`, and that path has no bound at all.
- **Evidence:** `Store.Inspire` (internal/mutations/inspire.go:20-40) concatenates
  `BestHistory` + all `Suggestions` + cass output with no cap, and `FormatInspiration`
  (inspire.go:88-108) joins them unbounded into the Orient system prompt
  (internal/session/session.go:80-92). The only bound anywhere in this path is
  `ReadRecentForType(tt, 50)` (internal/mutations/best.go:9) — a recency *window*, not a
  budget, and note `readJSONL` (store.go:135-165) applies no timestamp filter even though
  `QualitySignal.Timestamp` exists (signal.go:19), so a 50-row window can be arbitrarily
  old. Selection into that window is by `ParetoFront` on throughput axes
  (signal.go:54-67: `TokenEfficiency`, `-TurnCount`, error/denial rates), so the surviving
  rows are the fast ones, not the graded ones. A Frontier ledger reading through this path
  inherits: unbounded mint, recency-not-grade retention, throughput-ordered selection.
- **Suggestion:** One field addition to Frontier's contract, not a redesign — a **mint
  quota issued by the same authority and on the same clock as the spend warrant** (leads
  per epoch), plus grade-ordered eviction when the quota is exceeded, so the ledger is a
  fixed-size register whose yield is denominated per unit of ledger capacity rather than
  per lead. Concretely: cap the rows `Inspire` may surface and evict lowest-grade first,
  rather than newest-50.
- **Intersection:** Foraging supplies patch memory and stock-versus-flow — a memory of
  visited patches only helps while it is small enough to read, and dedup lowers the
  marginal cost of minting. Graded-allocation supplies the dual licence and grade-ordered
  eviction — the mint quota must come from the *same* issuer as the spend warrant, or the
  two licences drift apart on different clocks. Parent A alone says "cap the ledger" (a
  size bound, evicting by recency, which is what the code already does wrong); parent B
  alone says "grade the rows" (provenance without a budget, so grading a growing pile).
  Only the cross term yields "the dedup guard is a mint accelerant, so mint needs its own
  warrant and eviction must be by grade."

### cluster-by-minting-authority-not-verb

- **Severity:** P2 — refines the clustering criterion and the adjudication axis.
- **Where:** target §Mandatory disagreement line 124 ("Scout vs Speculate: outward search
  behavior versus epistemic status") and §Candidate-generation requirement line 73 ("Do
  not score until the raw candidates have been clustered into genuinely different
  operations").
- **What:** The charter's clustering rule is contract-equivalence and its Scout/Speculate
  axis is behavior-versus-status. Both are verb tests, and both mis-sort here. The
  residual Scout (after Trace absorbs the search-behavior reading) and Speculate produce
  output of the *same* grade, into the *same* namespace, under the *same* read filter —
  identical on fields 3 and 4, which is what contract-equivalence checks — and are
  nonetheless different operations, because Scout mints under an *issued tasking* (someone
  named the domain to search) while Speculate mints under *self-tasking* (the agent's own
  patch-depletion estimate). Different issuer, different accountability, different
  gaming profile, same product. A contract-equivalence test merges them; a licence test
  splits them.
- **Evidence:** the charter has no field that records *who authorized* a probe — field 4
  (line 82) records the grade the output carries, not the issuer of the licence to
  produce it. Skaffen shows why that omission bites: the escalation licence at
  `costrouter.go:74-80` is self-issued from `shouldEscalate()` and the authorizing state
  is destroyed at `costrouter.go:75` / `complexity.go:131-135`, so after the fact a
  self-tasked spend and an issued one are indistinguishable in the record — exactly the
  merge error, realized in code.
- **Suggestion:** State the clustering rule as: two names merge only when they share a
  *minting authority*, a *rate*, and a *grade*; they split when one mints and the other
  only re-marks (which is what correctly separates Assay from Trace), and when one is
  issued and the other self-tasked (which is what separates Scout from Speculate). Add
  "issuing authority (issued vs self-tasked)" as a sub-field of field 4.
- **Intersection:** Foraging supplies self-tasking as a real, non-pathological mode — a
  forager *should* leave a depleted patch on its own state estimate, so self-tasking
  cannot simply be banned. Graded-allocation supplies the issuer as an identity that must
  be recorded and audited. Parent A alone treats the issuer as irrelevant (only the rate
  matters); parent B alone treats self-tasking as a defect to eliminate rather than a
  clustering axis. Only together does "issued vs self-tasked" become a *splitting
  criterion* for two operations that are otherwise contract-identical.

## Verdict

The field is well stocked with probe-unit, trigger-entered candidates and has no
rate-unit, licence-entered one; `Season` fills that hole and is the only contract in the
field on which the fused lens's own question — if yield doubled, richer patch or looser
licence? — has an answer. The tournament's terminal evidence cannot answer that question
either, because the pilot runs each candidate at one unrecorded rate; a two-rung rate
ladder is the smallest change that makes the pilot's verdict about the candidate rather
than about its cadence. Frontier survives with one added field (a mint quota on the spend
warrant's clock, grade-ordered eviction), and the Scout/Speculate adjudication should be
re-axed onto issued-versus-self-tasked minting authority before it is scored.
