# fd-fused-allocator-regress — round 3

Fused lens: fd-foraging-exploration-generator (patch depletion, giving-up density, dwell,
trigger predicates, regret) × fd-fused-grading-arm-allocation (cost of setting/re-setting the
probe:grade split, regress termination, one-pool premise vs pace layers, corpus as depleting stock).
Every finding below names both parents' contributions; findings either parent could file alone
were discarded.

## Findings Index

- [P0] orient-allocator-restrikes-on-turn-clock-against-session-clock-stock — Skaffen's incumbent exploration allocator re-strikes every Orient turn against a stock that only changes once per session, so its entire cost is provably zero-information regret and no candidate contract prices it (§Lessons item 7 (43), §Per-candidate contract field 5 (80))
- [P1] stint-contract-frozen-allocation-with-declared-dwell-and-priced-regret — fused candidate contract filling the charter's explicitly under-filled "changes exploration/exploitation policy rather than emitting a report" slot; it terminates the regress by declaring a stationary ratio and buying its regret, and concedes it is a capability, not a letter (§Candidate-generation requirement (71))
- [P1] two-windows-one-name-and-a-non-depleting-front — Orient's allocator reads two unreconciled recency windows (global n=5, per-type n=50) four lines apart, both count-denominated so the forgetting rate is endogenous to arm throughput, and the Pareto "front" never depletes because two of its six objectives are structurally constant (§Lessons item 7 (43), §Comparative criteria (108-116))
- [P2] corpus-reserve-and-run-order-unspecified — the pilot corpus is stock consumed by assaying, its two falsifying classes are the scarcest, and the charter freezes size/reserve/run-order silently at "small" (§Pilot contract (142-147))

## Findings

### orient-allocator-restrikes-on-turn-clock-against-session-clock-stock

- **Severity:** P0
- **Where:** target §Lessons item 7 (:43), §Per-candidate contract field 5 (:80), §Pilot contract (:140-157);
  `internal/session/session.go:78-91`, `internal/agentloop/loop.go:189-195`, `internal/agent/agent.go:345-348`,
  `internal/agent/agent.go:246-253`, `internal/mutations/inspire.go:20-38`, `internal/mutations/best.go:8-17`.
- **What:** The charter asks (lesson 7) what implicitly sets today's probe:grade ratio in the no-S null.
  The answer is on the trace: `Inspire` → `BestSummary` + `Suggest` + `cassSearch`, injected into Orient's
  system prompt. But `JSONLSession.SystemPrompt(phase tool.Phase, _ int)` is called from **inside the
  per-turn loop** (`loop.go:189`), and the adapter (`agent.go:348`) forwards only `hints.Budget` — it
  discards `hints.TurnCount`. So the allocator re-runs on **every Orient turn**: two full re-reads of the
  per-type JSONL plus two O(n²) Pareto recomputations (`inspire.go:25` and `inspire.go:30` each reach
  `BestApproach`), one global re-read (`session.go:82`), and one `cass` subprocess exec (`inspire.go:35`).
  Meanwhile the only thing that can *change* that stock is `mutations.Aggregate` + `WriteForType`, which
  fires exactly once per session at Compound (`agent.go:246-253`). The re-strike clock is O(turns);
  the evidence clock is O(sessions). Every re-strike after the first in a session is therefore
  guaranteed to read byte-identical input and produce byte-identical output. This is not "possibly
  wasteful" — it is a closed proof that 100% of the incumbent allocator's recurring cost is regret.
  It also silently decides the tension the charter refuses to resolve: the null is not "no allocation
  policy", it is a policy that pays a per-turn survey tax and buys nothing with it.
- **Evidence:** `loop.go:189` calls `l.session.SystemPrompt(PromptHints{... TurnCount: turn})` once per
  loop iteration; `agent.go:348` drops `TurnCount`; `session.go:78` signature is `(phase tool.Phase, _ int)`
  — the turn index is discarded at the receiver too. No memoization exists between `Inspire` calls
  (`inspire.go:20-41` constructs a fresh `Inspiration` each call; `store.go:133-137` re-opens the file
  each call). Write side: `agent.go:247` is guarded by `phase == tool.PhaseCompound`.
- **Consequence for the tournament:** the pilot (§140-157) compares arms at equal budget on
  turn-denominated meters. Any S candidate that shortens Orient — including one that does no exploration
  at all — removes this tax and will beat the null for a reason that has nothing to do with exploration.
  Conversely a candidate that adds Orient turns pays the tax k times. The tournament would rank
  candidates on incumbent thrash, not on the capability under test.
- **Suggestion:** one hunk — thread `TurnCount` through `agent.go:348` into `Session.SystemPrompt`, and gate
  the `Inspire`/`formatQualityHistory` injection in `session.go:79-91` on `turn == 0` (or on a cached
  `Inspiration` invalidated by a `WriteForType`). That makes the null's allocator cadence match its
  evidence cadence and makes the pilot's turn meters mean what the charter thinks they mean.
- **Target amendment (remediation):** Amend §Per-candidate contract field 5 to require each contract to
  state its **re-strike cadence separately from its probe cadence**, plus the evidence-arrival predicate
  that licenses a re-strike, and disqualify at the bounded-trigger hard gate any contract whose allocation
  updates faster than the evidence that could change it.
- **Intersection justification:** Parent A supplies dwell/hysteresis and the trigger-predicate distinction
  (congestion vs shear) — without it the per-turn re-run is just an efficiency nit. Parent B supplies the
  meta-allocation frame: the split-setter is itself a spend from the pool it governs, on a clock that may
  differ from the stock's clock. Only the cross term yields the load-bearing claim — that the re-strike
  cadence strictly dominates the evidence cadence, so the survey's cost is *provably* pure regret and the
  no-S null carries an unpriced per-turn allocator tax that biases every arm comparison.

### stint-contract-frozen-allocation-with-declared-dwell-and-priced-regret

- **Severity:** P1
- **Where:** target §Candidate-generation requirement (:71) — "at least one candidate that changes the
  exploration/exploitation policy rather than emitting a report"; §Per-candidate contract (:75-89).
- **What:** GENERATION FIRST. Filing **Stint** — the operation whose entire output is a *held* allocation.
  A stint is a miner's allotted shift-work; to stint is to hold back. Eleven fields:
  1. **Input/preconditions.** The current Strike record `{ratio, struck_at, dwell_until, band}` plus a
     shear statistic computed only over QualitySignal rows that arrived *since* `struck_at`. Precondition:
     `dwell_until` elapsed AND shear exceeds `band`. No task input, no corpus, no probe.
  2. **Transformation.** Converts evidence-of-non-stationarity into a new frozen probe:grade:exploit split
     for the next stint, and states the regret that freezing buys. It is the only candidate in the field
     whose transformation operates on *budget* rather than on claims.
  3. **Output/consumer.** A Strike record in `~/.skaffen/mutations/strike.jsonl`. Consumer: the phase
     budgeter and the Orient injection gate — **not the model**. Emits no prose.
  4. **Authority/storage/read filter/expiry/negative retention.** Grade: `policy`, explicitly not
     knowledge. Namespace: separate file, and the read filter is *numeric-only* — the ratio may be read,
     the record may never be text-injected into a system prompt (this is the clause that keeps Stint from
     becoming another `cass`-style truth channel). Expiry: `dwell_until`; past it the ratio persists but is
     marked `unstruck`. Superseded strikes are retained with their realized regret, so a bad strike is
     durable evidence about the shear statistic's own calibration.
  5. **Trigger and pace layer.** Shear only, never congestion — backlog depth means the furnace is busy,
     not that the world moved. Dwell floor is denominated in **completed Compound writes**, never in turns
     and never in wall-clock, so the allocator is structurally slower than its stock.
  6. **Re-entry.** None into the epistemic loop. Re-entry is into the allocator: the next Orient reads the
     ratio and the loop's per-phase budget respects it.
  7. **Runtime delta.** A strike store, a read-only accessor, a per-stint budget counter in
     `agentloop.Loop`, and a gate on `session.go:86-90` so inspiration is rebuilt only on strike change.
     Enforceable: no phase other than Stint may write a Strike.
  8. **Overlap.** None with Observe/Orient/Reflect/Compound, which transform claims. Distinct from the
     field's existing contracts: Reprove removes authority from stale *claims*; Warrant authorizes a
     *spend*; Trace *is* a spend; Assay re-marks material. Stint sets how much spend exists.
  9. **Failure/Goodhart.** Shear-gaming: an arm that makes the world *look* non-stationary to buy itself
     probe budget. Mitigation: the shear statistic is computed over held-back rows the arms cannot see.
     Second failure: dwell as an alibi for ignoring genuine regime change.
  10. **Cheapest pilot / losing condition.** Offline replay of existing `~/.skaffen/mutations/*.jsonl`; no
      new corpus needed. Arm 1 = today (re-strike per Orient turn); Arm 2 = Stint, dwell = 5 Compound
      writes. Primary meter: **fraction of allocation changes that occur with zero new QualitySignal rows
      in between**. Losing condition: if that fraction is under ~10% in real traces, or if the held ratio
      underperforms the churning ratio on the same replayed stream, Stint is unmotivated and should be
      dropped rather than promoted.
  11. **Classification.** **Capability plus control state — explicitly NOT a phase.** Stint performs no
      epistemic transformation, so by the charter's own lesson 1 it fails semantic phasehood. I file it
      and concede it. This is the point: the under-filled "policy-changing" slot, once filled honestly,
      produces a capability, not a letter — which is affirmative evidence for the smallest-design goal.
- **Evidence that the slot is genuinely empty today:** no file under `internal/` holds an allocation ratio,
  a dwell, or a strike date. `best.go:9` hardcodes `50`; `session.go:179` hardcodes `5`; there is no
  hysteresis, no trigger predicate, and no stop rule anywhere in `internal/mutations/`.
- **Suggestion:** admit Stint to the shortlist as the field's policy-changing entry and let its field-11
  self-classification stand as the tournament's answer to "does the policy slot deserve a letter" — no.
- **Intersection justification:** Parent A supplies dwell, hysteresis band, trigger predicate and the
  congestion/shear distinction — the machinery of *when to stop re-deciding*. Parent B supplies the
  regress-termination requirement: a contract must declare which level it freezes, at what stationary
  ratio, and what regret it buys, rather than pushing the date letter up a floor. Neither parent alone
  produces field 4's numeric-only read filter (parent A has no provenance apparatus) nor field 11's
  self-refusal of phasehood (parent B does not generate candidates). The fused product is a contract that
  argues *for* an allocator and *against* an S letter in the same document.

### two-windows-one-name-and-a-non-depleting-front

- **Severity:** P1
- **Where:** `internal/session/session.go:79-91` and `:178-182`; `internal/mutations/best.go:8-17`;
  `internal/mutations/signal.go:54-66, 71-88, 90-106`; `internal/mutations/aggregate.go:56-93`.
  Target §Lessons item 7 (:43), §Comparative criteria (:108-116).
- **What:** Three fused defects in the incumbent allocator's stock, all invisible to either parent alone.
  (a) **Two exchange rates wearing one name.** `formatQualityHistory` reads the **global** file at
  `n=5` across all task types (`session.go:179`); four lines later `Inspire`→`BestApproach` reads the
  **per-type** file at `n=50` (`best.go:9`). Both are appended to the same Orient prompt in the same
  function; neither is reconciled with the other; both are hardcoded constants with no owner. The Orient
  model therefore sees two different pasts and no rule for which governs.
  (b) **Count-denominated windows make forgetting endogenous to throughput.** Both windows are denominated
  in *records*, and records are produced by the arms themselves (`agent.go:251` `WriteForType` once per
  session, bucketed by `inferTaskType`, `aggregate.go:96-137`). A hot bucket (`bug-fix`) rolls its 50-row
  window in days; a cold bucket (`optimization`, `docs`) never rolls it at all, so its earliest row is
  immortal. The same named parameter is several different decay rates, set not by any policy but by how
  often each arm happens to write.
  (c) **The front never depletes.** `Scores()` returns six objectives, but `Aggregate` never populates
  `Soft.ToolDenialRate` or `Human.ApprovalRate` (`aggregate.go:56-93` sets only `TokenEfficiency`,
  `TurnCount`, `ComplexityTier`, `ToolErrorRate`, `Human.Outcome`), so two of six dimensions are constant
  zero for every row ever written. `Dominates` requires being no-worse on *all* six and strictly better on
  one; with four live objectives over up to 50 rows, `ParetoFront` returns nearly the whole window. There
  is no giving-up density, no expiry, and no exit path from the "best approach" set except strict
  domination that almost never occurs. `BestSummary` then prints every front member into the Orient
  prompt, every turn. `ComplexityTier` is recorded but excluded from `Scores()`, so an easy task and a
  hard one compete on the same front with no difficulty normalization.
- **Failure scenario:** one early `optimization` session that happened to finish in 3 turns with high
  token efficiency becomes a permanent, never-expiring "best approach" injected into every future
  `optimization` Orient prompt — precisely the authority-laundering the charter's hard gate (:99) rejects
  in candidates, running unchallenged in the incumbent. In the pilot, arms that write more rows in a
  bucket roll their own window faster, so "identical recording paths" (:157) does not give identical
  memory age at read time.
- **Suggestion:** smallest viable fix is two hunks — drop `ToolDenialRate` and `ApprovalRate` from
  `Scores()` (or populate them in `Aggregate`) so domination can actually occur, and denominate at least
  one of the two windows in time rather than count. Longer term this is the empirical case for Reprove's
  decay clock applying to the incumbent, not only to candidates.
- **Target amendment (remediation):** Amend §Comparative criteria to require, for the no-S null and every
  survivor alike, a stated **denomination** for each recency/decay parameter (records vs sessions vs
  wall-clock) and a stated exit rule from the "best known approach" set, and score
  resistance-to-authority-laundering against the incumbent's answer, not only against candidates'.
- **Intersection justification:** Parent A owns patch depletion and giving-up density — it alone would say
  "there is no exit rule from the front" and stop. Parent B owns the frozen-level/date-letter question —
  it alone would say "n=50 and n=5 are unowned constants". Neither alone reaches the fused claim, which is
  that the frozen level is denominated *in the same units the arms compete in*, so the incumbent's decay
  rate is set by the throughput of the very arms the pilot is trying to compare — the allocator's clock is
  paid in the shifts it allocates. That cross term is what turns a code nit into a pilot-validity defect.

### corpus-reserve-and-run-order-unspecified

- **Severity:** P2
- **Where:** target §Pilot contract (:142-147, :157).
- **What:** The charter specifies a "small pre-registered, read-only evaluation corpus" with four item
  classes (hidden cross-domain mechanisms, tempting false analogies, unresolved contradictions,
  no-benefit cases), three arms, and six blind-scored outcomes — but never states corpus size, per-class
  stock, per-class reserve, or run order. Treated as a depleting instrument, the corpus is not uniform
  stock: the losing condition (:157) turns almost entirely on two classes — **no-benefit cases** (which
  falsify the S candidates) and **tempting false analogies** (which price false-transfer cost). Those are
  the two classes a "small" corpus is most likely to under-stock, because they are the least interesting
  to author. Meanwhile "hidden mechanism" items are single-use per arm in a stronger sense than the others:
  once assayed they carry no further discriminating power for the same maker.
- **Failure scenario:** the pilot runs, the discovery classes produce a signal, the no-benefit class has
  three items, and the losing condition — "added exploration fails to improve validated discovery after
  false-transfer and attention costs" — cannot be evaluated at any useful power. The tournament then
  reports an unfalsified winner that was never at risk.
- **Suggestion:** state a per-class floor (no-benefit and false-analogy classes each at least as large as
  the hidden-mechanism class), fix run order in advance, and reserve a named holdout slice untouched by
  arms 1 and 2 so the losing condition remains falsifiable at the third arm.
- **Target amendment (remediation):** Amend §Pilot contract to state corpus size, a per-class item floor
  weighted toward the falsifying classes (no-benefit and tempting-false-analogy), a pre-registered arm run
  order, and a reserved holdout slice, so the losing condition retains power after the corpus is depleted
  by the first arms.
- **Intersection justification:** Parent A supplies the depleting-patch frame — corpus items are consumed
  by being assayed and their yield is non-renewable. Parent B supplies the observation that reserve size is
  itself an allocation decision struck once, before the effect size is known, and therefore a frozen level
  the charter must own rather than leave to the word "small". Either parent alone produces a generic
  "specify the corpus" note; the cross term identifies *which* classes must be over-stocked (the falsifying
  ones) and *why* (they are the scarce reserve on which the losing condition's power depends).

## Verdict

The tournament's most consequential fact is not about any candidate: Skaffen's incumbent exploration
allocator re-strikes on the turn clock against a stock that moves on the session clock, so the no-S null
runs a provably zero-information survey tax that will contaminate every turn-denominated comparison the
pilot makes. Fill the charter's empty policy slot honestly and it yields **Stint** — a control-state
capability with a declared dwell and a priced regret — which classifies itself out of phasehood, adding
affirmative weight to the smallest-design goal. The incumbent's own stock (two unreconciled count-
denominated windows, a Pareto front that cannot deplete because two of six objectives are structurally
constant) fails the same authority-laundering standard the hard gate applies only to candidates.
