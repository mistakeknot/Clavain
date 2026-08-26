# fd-karst-tracer-conduit-probing — round 0

Tournament role: probing-and-allocation side. Contracts filed before elimination, against the
charter's eleven fields (`docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:75-89`).
Four contracts here — Trace, Frontier, Divert, and the allocation-side no-S null — of which
Divert is the charter's mandated policy-changing candidate (charter:71) and Frontier carries
the negative-result retention requirement (charter:41).

## Findings Index

- [P0] contract-trace-bounded-probe-with-fixed-detector — Trace: a pre-registered, budgeted probe whose detector and window are fixed before injection; absorbs Sound/Scout-as-search by cluster (§Per-candidate contract; §Candidate-generation requirement)
- [P0] contract-frontier-durable-null-register — Frontier: an addressable lead ledger where a null is a first-class row that provably prevents paying for the same probe twice (§Hard gates; charter lesson 5)
- [P1] verdict-no-reentry-path-eliminates-side-loop-candidates — the loop is forward-only and cannot return, so every side-loop candidate fails the "explicit re-entry path" gate unless field 7 names the FSM change (§Hard gates; §Mandatory disagreement)
- [P1] contract-divert-allocation-policy-and-the-allocation-null — Divert: changes where the next unit of effort goes and emits no document; plus the honest no-S null, which allocates nothing and bounds nothing (§Candidate-generation requirement; §Baseline)
- [P2] verdict-report-emitting-candidates-shear-into-a-slower-layer — fast speculative artifacts write into the slow cross-session store; report-emitters must justify an artifact over a state change (§Comparative criteria)

## Findings

### contract-trace-bounded-probe-with-fixed-detector

- **Severity**: P0 — the charter's hard gate requires a bounded trigger/stop rule
  (charter:100); no candidate now in the field states its probe cost, its detector, or what
  was fixed before the probe ran, so the gate is currently unenforceable against anyone.
- **Where**: charter `:75-89`, `:95-101`; runtime surface
  `internal/tool/registry.go:20-22, 63-65, 116-119, 242-258`.
- **What**: Candidate **Trace**. 1. *Input/preconditions*: a named lead (a specific
  source→target mechanism hypothesis), plus a **detector fixed before injection**: the file,
  test, or measurement that will be read for a hit, written down first. 2. *Transformation*:
  spend a bounded probe budget against that lead and record hit or **non-detection** with
  equal care. 3. *Output/consumer*: not a report — a Frontier row (below); the consumer is the
  allocation policy, not a reader. 4. *Grade/store/read filter/expiry/nulls*: rows are written
  to the speculative namespace with `outcome ∈ {hit, null, aborted}`, read-filtered out of
  Orient's default set, expiring on the source's staleness, nulls retained permanently.
  5. *Trigger/pace*: fires on a stagnation or contradiction signal; **fast layer** — the
  fastest thing in the design. 6. *Re-entry*: a hit becomes an ordinary Observe/Act item; a
  null re-enters only as suppression. 7. *Runtime delta*: expressible today as
  `GateConstraint{RateLimit: N}` on a `probe` tool — the same mechanism that limits Reflect's
  `edit` to 3 calls (`registry.go:63-65`, enforced at `:242-258`). 8. *Overlap*: Observe
  collects what is already in view; Trace pays to find out whether an unvisited passage goes
  at all. 9. *Failure/Goodhart*: probe count as a metric; probing where detection is cheap
  rather than where information is valuable. 10. *Pilot/losing condition*: on the corpus's
  no-benefit tasks, Trace loses if probe budget is spent at the same rate as on
  hidden-mechanism tasks. 11. *Classification*: capability with a runtime-enforced budget;
  not a phase.
- **Evidence** (grounded, and it changes the contract): `ResetRateCounts()` is documented
  "call on phase transition" (`registry.go:116`) but **has no caller in non-test code** — a
  repo-wide grep finds the definition and the internal counter uses only. So a `RateLimit`
  budget is in practice a per-process lifetime budget, not a per-phase-entry one. For a probe
  budget that is the *correct* semantics and should be adopted deliberately; but any candidate
  whose stop rule assumes "N probes per S visit" would silently get N per session and starve
  on later loops. This is the concrete pre-registration point: fix the budget's reset
  semantics before the probe runs, not after reading the result.
- **Suggestion**: adopt Trace's field-7 answer as the template — a probe tool with an explicit
  `RateLimit` — and require the tournament to record, for each survivor, whether its stop rule
  is per-session or per-visit. Cluster **Sound** (cheap does-it-go check) and the
  search-behavior reading of **Scout** into Trace: same probe, same stop rule, same allocation
  effect; the verbs differ, the contracts do not.

### contract-frontier-durable-null-register

- **Severity**: P0 — charter lesson 5 (`:41`) forbids erasing failed probes, and no candidate
  including Scout says *where* a null lives or *how* it is addressed. Retention that cannot be
  looked up is decorative.
- **Where**: charter `:41`, `:82`; `internal/mutations/inspire.go:21-40` and `:63-80`; `internal/session/session.go:86-91`.
- **What**: Candidate **Frontier**. 1. *Input*: the outcome of any Trace. 2. *Transformation*:
  append a row keyed by a **lead fingerprint** (normalized source→target pair), carrying
  `probe`, `unit_cost`, `detector`, `window`, `outcome`, `probed_at`. 3. *Output/consumer*:
  the ledger's consumer is the *next* allocation decision — specifically a lookup inserted
  into `Inspire`. 4. *Grade/store/filter/expiry/nulls*: its own store, never merged into the
  quality-signal store; nulls never expire (they are the cheapest durable knowledge the loop
  owns); hits expire on source staleness. 5. *Trigger/pace*: written at fast pace, read at the
  start of every session — the one place a fast writer legitimately feeds a slow reader,
  because it only ever *subtracts* options. 6. *Re-entry*: suppression, not proposal.
  7. *Delta*: a lookup in `Inspire` before its three sources are assembled. 8. *Overlap*: none
  with Compound, which stores what worked; Frontier stores what was tried and did not.
  9. *Failure/Goodhart*: fingerprint too narrow → no suppression ever fires; too broad →
  legitimate re-probes blocked after upstream change. 10. *Pilot*: seed the corpus with one
  lead that recurs in three tasks; Frontier loses if the second and third occurrences are
  probed at full cost. 11. *Classification*: artifact + capability.
- **Evidence**: the mechanism by which a retained null prevents a future probe must be shown,
  not asserted — here it is. `Store.Inspire` (`inspire.go:21-40`) assembles Orient's
  pre-session context from `BestSummary`, `Suggest`, and `cassSearch`, and `cassSearch` shells
  out to `cass search <task> --robot --limit 3` (`:63-80`), returning the top three by
  relevance **every session with no memory of prior outcomes**, and
  `JSONLSession.SystemPrompt` pastes the formatted result into the Orient system prompt
  unconditionally (`internal/session/session.go:86-91`). A lead that was probed and
  came back null last week is therefore re-surfaced verbatim next week, at full cost. Frontier
  is a `if frontier.IsExhausted(fingerprint) { skip }` guard in exactly that function.
- **Suggestion**: make "names its null store and the lookup that consumes it" a hard-gate
  question at charter:100, and let it eliminate any candidate — Scout included — whose
  negative-result answer is a prose promise.

### verdict-no-reentry-path-eliminates-side-loop-candidates

- **Severity**: P1 — the charter offers "optional side-loop" as a first-class outcome
  (charter:17) and requires an explicit re-entry path as a hard gate (charter:101). Today the
  runtime cannot express either, so the side-loop branch of the tournament would recommend
  something with no implementation path.
- **Where**: charter `:13-21`, `:101`, `:127`; `internal/agent/phase.go:10-51`;
  `internal/agent/agent.go:97-99`.
- **What**: `phaseOrder` is a fixed six-element slice and `phaseFSM.Advance()` only
  increments, returning `cannot advance past %s` at the end; `Agent.AdvancePhase()` exposes
  nothing else. There is no jump, no return, no stack. A side-loop S — enter from Orient,
  probe, return to Orient — has **zero** runtime surface, and a candidate that inserts S into
  `phaseOrder` is not a side-loop at all but a seventh mandatory step executed once per loop,
  which is precisely the "ornamental seventh step" the charter's closing line rejects.
- **Evidence**: concrete failure scenario for the tournament, not the code: candidate B is
  recommended as a side-loop, field 6 says "returns to Orient", and implementation discovers
  that the cheapest honest options are (a) make S a tool callable from Orient — i.e. it was a
  capability, not a phase — or (b) add a return transition to the FSM, which changes the
  meaning of `IsTerminal()` and of every per-phase counter keyed on phase, including the rate
  counters at `registry.go:245-248`. Neither is stated in any field-7 today.
- **Suggestion**: add one required sub-answer to field 7 for every side-loop candidate: "the
  FSM transition this needs, or the admission that this is a capability". Candidates that
  cannot answer should be reclassified to capability under charter:103 rather than eliminated.

### contract-divert-allocation-policy-and-the-allocation-null

- **Severity**: P1 — charter:71 mandates at least one candidate that changes the
  exploration/exploitation policy rather than emitting a report; without it the tournament
  compares only document-producers and will conclude, unsurprisingly, that S is a document.
- **Where**: charter `:71`, `:43`, `:105-116`; `internal/agent/agent.go:33,40,89`;
  `internal/costrouter/complexity.go:101-114`.
- **What**: Two contracts. **Divert** (the policy candidate): 1. *Input*: a stagnation signal
  — repeated tool errors, or N turns without a state change. 2. *Transformation*: reallocate
  the next *k* turns from exploitation to probing; emits **no artifact**. 3. *Output/consumer*:
  a changed allocation state read by the loop itself. 4. *Grade/store*: no speculative content
  is produced, so hard gate 4 (charter:99) is satisfied trivially — this is Divert's strongest
  comparative claim, and the reason it should be a shortlist survivor even if it loses on
  generativity. 5. *Trigger/pace*: fast; bounded by *k* and by a single fire per session.
  6. *Re-entry*: none needed — it never leaves the loop. 7. *Delta*: a budget counter beside
  `maxTurns` (`agent.go:33,89`); the cheap-turn counter in `costrouter/complexity.go:101-114`
  is the existing pattern to copy. 9. *Failure*: thrashing between modes; Goodhart on the
  stagnation signal. 10. *Pilot*: losing condition = on no-benefit corpus tasks Divert fires as
  often as on hidden-mechanism tasks. 11. *Classification*: policy/capability — explicitly not
  a phase, and the field's best test of whether S needs a letter at all.
  **The allocation-side no-S null**: which existing operation allocates probing effort today?
  None. `Inspire` gathers context once, pre-session; web tools are open in Orient/Decide/Act
  (`internal/tool/builtin.go:20-22`) with no budget; the only bound on exploration anywhere in
  the runtime is `maxTurns: 100`, a crash guard. A retained null today looks like nothing —
  there is no store, and `cass` re-offers the same three sessions next time. That is the null's
  honest contract, and it is what any S must beat.
- **Evidence**: this is this lens's half of fusion 1 (foraging × epistemic provenance,
  charter:133). The emergent discriminator neither parent gives: **charge the probe budget to
  the lead, not to the session** — provenance of *spend* rather than provenance of *claims*.
  Foraging alone says how much to explore; provenance alone says how to mark output; together
  they say a lead that has already consumed budget across sessions is a lead with a recorded
  price, and the stop rule becomes cumulative-cost-per-lead instead of turns-per-session. That
  is a rule neither Trace nor Assay-style grading produces on its own, and it is checkable
  against the Frontier ledger.
- **Suggestion**: enter Divert into the longlist as the mandated policy candidate and score it
  head-to-head with Scout under "value relative to the no-S null" — the adjudication the
  charter asks for at `:126` is decided by whether a state change or a document is what the
  loop actually consumes.

### verdict-report-emitting-candidates-shear-into-a-slower-layer

- **Severity**: P2 — degrades ranking quality rather than corrupting it, but the charter makes
  pace/shear a scored criterion (`:110`) and nothing in the field currently assigns a layer.
- **Where**: charter `:105-116`, `:27`; `internal/evidence/emitter.go:36-50`;
  `internal/mutations/store.go:12,26`.
- **What**: Pace layers for the field, made checkable. Fast: Trace, Divert (per-turn, per-
  session). Medium: Scout/Speculate/Synthesize reports (per-task). Slow: the cross-session
  quality-signal store and anything Compound writes. The shear failure: report-emitting
  candidates write at medium pace into a store read at slow pace by later sessions' Orient,
  so a single session's speculation persistently reshapes the priors of every later session
  with no decay term anywhere — `ReadRecent(n)` is age-blind (`store.go:56`).
- **Evidence**: Trace and Divert have no shear because their durable state is either a null
  (subtractive) or an in-session counter; the report-emitters have shear because their durable
  state is additive text in a shared store. That asymmetry is the concrete content of the
  charter's "pace/shear coherence" criterion and should be scored that way rather than
  impressionistically.
- **Suggestion**: require each survivor to declare its layer and the slower structure it may
  write to; a fast operation that may write to a slow structure must name the decay or the
  filter that contains it.

## Verdict

Filed four contracts — Trace, Frontier, Divert, and the allocation-side no-S null — and can
show, not assert, the mechanism by which a retained null saves a probe: a fingerprint guard in
`Store.Inspire`, which today re-offers the same three `cass` hits every session. The strongest
S this lens can construct emits **no document at all**: Divert changes where the next unit of
effort goes and therefore passes the epistemic-separation gate trivially, which is the sharpest
available test of whether the tournament's document-producers are earning their letter. The
finding most likely to change the outcome is structural: the phase FSM is forward-only, so the
"side-loop" option in charter:17 has no runtime expression, and every candidate claiming it is
really claiming a capability.
