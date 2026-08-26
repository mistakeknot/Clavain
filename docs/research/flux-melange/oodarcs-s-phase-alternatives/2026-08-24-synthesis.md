---
artifact_type: melange-synthesis
method: flux-melange
target: docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md
target_description: >-
  Review charter deciding what (if anything) the optional S in OODARC(+S) should mean —
  Scout is the leading candidate, with no-S and S-as-capability as live nulls
goal: >-
  Generate genuinely distinct S-phase alternatives, adversarially test Scout and every serious
  rival against the no-S null, force productive disagreement probes and fused-lens reasoning,
  and recommend the smallest operationally crisp, pace-aware, epistemically safe design with
  falsifiable pilots
weights: balanced
rounds_run: 3
halt_reason: DRY
total_fusions: 0
emergent_findings: 2
runtime: claude
date: 2026-08-24
---

# OODARC(+S) — Melange Synthesis

Three rounds, 33 findings, 28 upheld, 5 refuted, 22 clusters, 13 slots of 24 spent, halted DRY.

## Re-scoring note

The per-round scores were fast triage. I re-scored the merged ledger against fixed rubrics
before building the views:

- **novelty** — 0: restates what a careful reader of the charter already sees. 1: requires
  reading the runtime, but is the standard-issue objection from that lens. 2: reframes the
  decision or finds a non-obvious mechanism. 3: inverts the question; no lens-free reading
  produces it.
- **risk.blast** — 1: local to one line or artifact. 2: distorts the review's output.
  3: distorts a shipped architecture decision, or corrupts durable state outside Skaffen.
- **risk.likelihood** — 1: needs several things to go wrong. 2: likely on the current path.
  3: already true in the runtime, or mechanically certain once the charter is executed.
- **taste** — signed, on the *design under review*, not on the finding's prose.

Twelve findings moved. The systematic moves: (a) likelihood raised to 3 wherever the finding
was verified against committed code rather than predicted — most round-0 findings are
*already-true* facts about `internal/`, not forecasts; (b) novelty raised on findings whose
lens supplied a discriminator the charter lacks (f-018, f-016, f-023, f-028) and lowered on
adjudications whose job was to settle, not to discover (f-026, f-032); (c) blast raised to 3
on f-007 because the evidence bridge carries the confound into Interspect routing calibration,
which is outside this repo.

One likelihood call is load-bearing and I want it auditable rather than convenient. **f-027 and
f-029 both fail only if the pilot's outcome measure is `QualitySignal`.** I scored those at
likelihood 2, not 3, because charter:119 currently names *no* dependent variable (f-006), so the
instrument is still undetermined and a hand-scored transfer measure remains available. If item 7
is repaired the obvious way — using the only aggregate the runtime produces — likelihood goes to
3, f-027 becomes the run's sole argmax at heat 27, and the Pareto front collapses to one point.
That conditional is the highest-leverage thing a reader can resolve.

---

## 1. Novelty × Risk Frontier

The front is 13 points at two tiers: `(novelty 3, risk 6)` and `(novelty 2, risk 9)`. Nothing
reached `(3, 9)`. Two leads.

### LEAD — max novelty (3), mid risk (6) · f-027 · heat 18 · severity P1 *(reference only)*

**The two pilot arms are written to different files and never compared.**
Lens: `disagreement-adjudication` (parent: `fd-epistemics-provenance-falsification`). Emergent.

A minimal read-only pilot session is by construction no-write / no-edit / read-heavy — which is
exactly the first branch of `inferTaskType` (`internal/mutations/aggregate.go:133`:
`case !hasWrite && !hasEdit && hasGrep: return TaskDocs`). `store.go:89-95` then routes the
signal to `<tasktype>.jsonl`, and Orient reads *per type*. So the S arm accumulates in
`docs.jsonl` while the no-S null arm accumulates in `feature.jsonl` / `bug-fix.jsonl` /
`refactor.jsonl`. The arms never share a file, and nothing scores them against one another.

Risk decomposition: **blast 3** — this is the review's only empirical instrument, and its
failure is silent; the pilot will produce numbers, they will simply not be a comparison.
**likelihood 2** — requires item 7 to be repaired using `QualitySignal` (see the re-scoring
note; the repair is the obvious one but not yet forced).

Why it leads: it is the exact mirror of the settled defect. f-006 says item 7 as written
*cannot lose*. f-027 says item 7 as a reader would implement it *cannot win* — `Scores()`
penalizes turn count and rewards `tokens_out/tokens_in`, so an S phase strictly adds turns and
its read-heavy turns depress efficiency, for reasons unrelated to transfer quality. Both signs
of the instrument's bias are fatal, which is a stronger conclusion than either parent reached.

### LEAD — mid novelty (2), max risk (9) · f-021 · heat 18 · severity P0 *(reference only)*

**"Scout reports cannot become evidence directly" is enforced by nothing, and the runtime has
one ungraded store whose aggregate is read back by Orient.**
Lens: `fd-usulfiqh-authority` (graded reliability / isnad).

Four automatic hops, all verified: (1) `agent.Evidence` has 25 fields, none a grade, authority,
or record id (`deps.go:61-96`), and `JSONLEmitter` appends every event to one per-session file
plus a best-effort intercore bridge (`emitter.go:38-74`). (2) Compound calls `mutations.Aggregate`
(`agent.go:246-253`), which reads every line and silently `continue`s past records it cannot
unmarshal (`aggregate.go:36-47`). (3) The output `QualitySignal` retains session id, timestamp,
phase, task type, and rates (`signal.go:16-46`). (4) A later Orient turn reads it back through
`quality_history` (`quality_history.go:17-31`).

Risk decomposition: **blast 3** — a speculative turn's footprint reaches durable cross-session
state *and* the intercore evidence stream under `agent_name: skaffen`; **likelihood 3** — every
hop is unconditional committed code, not a forecast. The charter's central safety claim is the
one claim with no implementation anywhere.

The generalization is the operative part: **any candidate that adds a writer without adding a
grade field is net-negative against the no-S null.** That is a scoring rule the tournament
does not have.

### Rest of the front

`(3, 6)` tier — max-novelty:

| id | claim | lens | blast × lik |
|---|---|---|---|
| f-033 | Pointed symmetrically, the gate-delta discriminator indicts the incumbents: `Observe ⊂ Decide ⊂ Orient` is a strict 1–2 tool nesting under identical Opus routing with no enforceable transition, so three of six existing phases fail the criteria applied to challengers — the honest recommendation space must include *merge existing phases*. | `control-flow-archaeology` (emergent) | 3 × 2 |
| f-028 | The mechanism-to-word substitution is enforced by the *box-shaped per-candidate spec*, not just the S seeds: the cybernetics primitives are edge modifiers (dead-band on the Reflect→Compound gate, variety amplifier on Orient's input, the literal `ReadRecent(5)` window) and none has an input/output contract or a re-entry path, so the mandated control-theory class can only be entered by impersonating a phase. | `fd-cybernetics-loop-topology` (DEEPEN) | 3 × 2 |
| f-011 | Scout, Search, Speculate and Synthesize share one (input, output, consumer) contract and differ only in which facet they name, so the shortlist ranks one operation three times while calling it a competitive field. | `fd-ontology-naming-distinctness` | 3 × 2 |
| f-023 | The chain terminates at promotion: `Aggregate` reduces N records to sums and rates, so a compounded lesson keeps no link to probe, report, or source domain, and discrediting a link can never trigger re-grading. | `fd-usulfiqh-authority` | 2 × 3 |

`(2, 9)` tier — max-risk:

| id | claim | lens | blast × lik |
|---|---|---|---|
| f-018 | In Skaffen a phase *is* a capability gate, so the phase/side-loop/capability question is mechanical: compute the gate delta. Scout's delta against Orient is ∅. | `fd-miyadaiku-loadpath` | 3 × 3 |
| f-032 | `phaseFSM` carries no control flow at all — the only non-test caller of `AdvancePhase()` is the `/advance` TUI command — so phase-hood reduces to a capability profile, and declaring `PhaseScout` without editing `phaseDefaults` silently downgrades the charter's most generative phase to Sonnet. | `control-flow-archaeology` | 3 × 3 |
| f-016 | The tournament scores candidates against phase *names*, not against the members that already carry the load; three of Scout's seven emitted fields have named carriers today (web tools in Orient/Decide/Act, the `init_experiment`/`run_experiment`/`log_experiment` trio, `Hypothesis`/`Decision`/`Delta`). | `fd-miyadaiku-loadpath` | 3 × 3 |
| f-006 | The one sentence carrying the review's entire empirical burden names no measured quantity, threshold, cycle count, recorder, or outcome favoring the null — the tournament cannot lose. | `fd-epistemics-provenance-falsification` | 3 × 3 |
| f-010 | Six of eight criteria presuppose an operation, so no-S scores N/A on most of the matrix; and no output item asks which evidence *discriminates*, so non-diagnostic evidence reads as support. | `fd-epistemics-provenance-falsification` | 3 × 3 |
| f-007 | Every candidate turn writes the evidence file Compound aggregates into the very signal a pilot would use as its outcome — and unknown tags are dropped by the decoder before aggregation. | `fd-epistemics-provenance-falsification` | 3 × 3 |
| f-002 | Scout's trigger — "unresolved contradiction, or detected shear" — has no referent in any state record the loop carries; `shear` appears nowhere in the repo outside the charter, so a missed Scout is indistinguishable from a correctly skipped one. | `fd-cybernetics-loop-topology` | 3 × 3 |

---

## 2. Top Fusions

Scheduled fusions: **0**. Emergent findings: **2**. Both arrived through `PROBE-DISAGREEMENT`
lenses, which are fusions in effect but were never dispatched as `FUSE` directives — the
charter at :107 asked for at least two productive lens pairs, and the loop satisfied that
accidentally rather than by design (same failure mode the charter records from the prior run at
:100, one level up).

### f-027 — `fd-epistemics-provenance-falsification` × charter:119 · heat 18

Parent pair: f-006 (the pilot cannot lose) × f-007 (the pilot confounds its instrument).
`intersection_justification`: *"Exposed only by adjudicating the two claims together: (1)'s
'cannot lose' and (2)'s confounding turn out to be two faces of one missing dependent variable,
and tracing (2)'s mechanism into store.go revealed the arms never share a file at all."*

Evidence: `aggregate.go:133`, `store.go:89-129`, `signal.go:17-18`, `signal.go:52-70`. Both
parents sit at charter:119; neither connected the missing outcome variable to task-type
bucketing, and the per-type file split appears in neither. Full write-up above.

### f-033 — `fd-cybernetics-loop-topology` × `fd-miyadaiku-loadpath` · heat 18

`intersection_justification`: *"Accepting (2)'s discriminator obliges turning it on the
baseline, which neither original finding did, and the result inverts the charter's
addition-only framing."*

Evidence: `registry.go:50-58` + `builtin.go:19-22,27` give strict set nesting
`Observe {read,glob,grep,ls} ⊂ Decide (+web_search,web_fetch) ⊂ Orient (+quality_history)`. The
entire runtime content of "Orient vs Decide" is one tool plus one Exa tier string
(`web_search.go:76-86`). `router.go:20-26` routes all six phases to Opus — zero routing delta.
`tui/commands.go:196` is the sole transition mechanism. So Orient and Decide score near-zero on
"minimal overlap with O/O/R/C" and zero on "enforceable input/output and state transition" —
the exact grounds on which any S candidate would be rejected.

This is the only finding in the run that changes what the *answer* can be, rather than what the
review must fix before answering. It is also the one flagged by its own lens's declared failure
mode ("can produce a demolition finding out of the charter's scope"), so treat it as a scope
question for a human, not a verdict.

### Negative results — pairs never attempted

- **`fd-usulfiqh-authority` × `fd-cybernetics-loop-topology`: never run.** This is the highest-value
  unrun pair. It would have tested whether the retirement sweep (f-009, f-022) is expressible as a
  control element — a decay term or dead-band on the promotion gate — which is exactly the
  edge-modifier class f-028 shows the charter cannot express. Both parents were live at halt;
  the loop went DRY before pairing them.
- **`fd-ontology-naming-distinctness` × anything: never re-entered after round 0.** No probe
  tested whether the naming defect (f-011, f-013) interacts with the gate-delta defect (f-018) —
  i.e. whether four synonymous seeds and an empty gate delta are the same fact seen twice.
- **No ecology / exploration-exploitation lens existed to pair with.** See caveats.

---

## 3. Taste Calls

### Preserve

**f-018 · taste +2 · `mechanical-discriminator`.** "In Skaffen a phase *is* a capability gate,
so the discriminator is the gate delta." One sentence converts the charter's fuzziest and most
consequential question (:83, phase vs side-loop vs capability vs artifact type) from a
rhetorical contest into a set difference an implementer can compute in an afternoon. It is the
only thing produced in three rounds that makes the tournament decidable. Whatever else changes,
this belongs in the criteria as gate zero: *name the capability the candidate needs that no
existing phase grants; if the set is empty, it is a capability.*

**f-016 · taste +1 · `load-path-framing`.** Restating the null from "absence of a phase" to
"these five members already carry the load" is the move that makes the null scorable at all —
it converts a negative into an affirmative claim with named carriers (`builtin.go:19-22`,
`builtin.go:33-51`, `deps.go:90-96`, `builtin.go:25-29`). Directly repairs f-010.

### Fix

**f-008 · taste −2 · `survivorship-gate`.** "Only successful probes may be Compounded" reads as
epistemic hygiene and is a Goodhart trap: it selects on the wrong variable, makes the optimal
strategy a near-certain prediction restating what the team already believed, and erases the
failed probes that carry the information. The runtime already knows better — `ExperimentEvent`
retains `Decision`/`Delta` for *rejected* mutations. The charter's own store would be strictly
worse than the one next to it.

**f-025 · taste −2 · `rigor-theater`.** The two fields that make Scout look rigorous —
correspondence mapping and where-the-analogy-breaks — carry no validity test. No shared
effective cause need be named, and nothing bars transferring from a source claim that is itself
ungraded, so a mechanism read off a blog post and a mechanism established in the system's own
compounded record enter on identical terms and leave carrying the same `authority: speculative`.
The grade attaches to the *act of scouting*, not to the strength of the chain.

**f-011 · taste −1 · `false-diversity`.** A nine-entry longlist whose diversity is the review's
stated deliverable, where four entries are one operation and two are existing phases renamed.
Confidence in coverage calibrated to a word count.

**f-005 · taste −1 · `self-sealing-axiom`.** The charter asserts orchestration topology is
orthogonal to phase structure (:27), then seeds Share (:59) — a candidate whose entire content
is a change to that topology. Either Share is out of scope by construction, or the axiom is
false; the charter scores Share on O/O/R/C-relative criteria and eliminates the one candidate
that could have falsified its own premise.

---

## 4. Convergence Spine

High cross-lens agreement, low novelty. Trust these; do not lead with them.

**`c-phase-vs-capability-no-mechanical-test` — 5 findings, 4 lenses (f-003, f-012, f-016, f-018,
f-032).** The largest convergent cluster in the run, and the closest thing to a settled verdict.
Cybernetics ("no criterion asks which edge disappears when the box is deleted"), ontology
("conditional, unpositioned, artifact-emitting — three for three on capability"), miyadaiku
("the gate delta is the discriminator"), and control-flow-archaeology ("delta = ∅") converge
independently: **Scout's required capability set is a strict subset of Orient's, and the phase
claim is carried by the acronym rather than the contract.** Cost asymmetry, verified: capability
form is one `RegisterForPhases` call; phase form is a `phaseOrder` member, a `defaultGates`
entry, a `phaseDefaults` entry, router and shadow maps, four `cmd/skaffen/main.go` sites,
per-phase prompt guidance, the Intercore role map, the TUI, the acronym in every doc, and a
migration to undo.

**`c-null-cannot-win` — f-006, f-010, f-026.** Two base lenses plus the round-1 adjudication.
Item 7 is eleven words with no dependent variable; six of eight criteria presuppose an
operation; the adjudication ordered the two claims (specification before feasibility) rather
than splitting them, and added that "read-only" fails under *both* its operational reading
(`agentloop/loop.go:286`, `Emit` unconditional in the turn body) and its epistemic one
(`agent.go:246-253`, `Aggregate` over the whole session file).

**`c-reentry-edge-unimplementable` — f-001, f-017.** Cybernetics and miyadaiku independently:
`Advance()` only increments; there is no `Goto`, no `Reset`; and `cmd/skaffen/main.go:216-221`
rejects `--phase observe` outright, so the arrow's target is the one phase the CLI refuses to
start. **Demoted at round 2** by f-032: with no automatic forward edge either, a missing
backward edge is a category error, and the objection is contingent on ~10 lines. Keep as a
build note, not a design objection.

**`c-retirement-unenforceable` — f-009, f-022.** `grep -rni 'authority|speculative|provenance'`
over `internal/` returns zero hits; the only TTL machinery is a 15-minute web-search cache and
interlock reservations. `appendJSONL` opens `O_APPEND|O_CREATE|O_WRONLY`, and `Evidence` has no
id, so a compensating re-grade record would have nothing to point at.

**`c-no-source-domain-base-rate` — f-008, f-024.** A success-only promotion gate plus an
`ExperimentEvent` with no origin field means a source domain's tenth failed borrowing is
indistinguishable from its first.

**`c-scout-placement-vs-trigger-site` — f-004, f-019.** Triggers surface in Orient; the gate
sits after Compound, which has no web tools at all and is where the durable artifact is cut.
One full cycle of deadtime on every contradiction-triggered case.

**`c-letter-first-generation-constraint` — f-014 (refuted), f-028 (upheld).** Ledger anomaly:
the round-1 DEEPEN finding opens "CONFIRMED, and wider than claimed" and lists f-014 in its
convergence refs, while f-014 carries `status: refuted`. The substance survives in f-028, which
is upheld and independently evidenced; the disposition of f-014 itself is unresolved. Flagged
in caveats.

---

## 5. Live Disagreements

Four open at halt. These are the primary signal — three of the four are unresolved taste calls
about what the review is *for*, not factual disputes.

### D1 — charter:119 · the **sign** of the pilot's bias · f-007 vs f-029 (with f-027)

A direct contradiction, and neither side is careless.

- **f-007** (`fd-epistemics-provenance-falsification`): cheap, error-free scout turns *inflate*
  `TokenEfficiency` and *dilute* the tool-error denominator → the pilot concludes S improved
  quality when it only changed the mix. **False positive for S.**
- **f-029** (`fd-cybernetics-loop-topology`): `TokenEfficiency` is `totalOut/totalIn` across the
  whole session (`aggregate.go:63-70`) and scout turns are read-heavy, so they *dilute* it;
  `Scores()` is monotone against exploration on every axis (`signal.go:52-70`); Orient reads a
  five-session moving average and `best.go:9` Pareto-selects over the same one-sided vector.
  **False negative for S — the pilot reports "Scout degrades quality" for a Scout that worked
  perfectly.**

Unresolved because it turns on an unmeasured empirical quantity: the token profile of a scout
turn. A scout turn that generates a long structured report from short prompts moves the ratio
one way; one that fetches five web pages moves it the other. Both are called "Scout." f-027
makes it worse — under the task-type split the two arms may never be compared at all, in which
case the sign is moot and the instrument is simply void. **Resolvable in an afternoon: emit ten
scout-shaped turns and read the ratio.** Until then, no pilot design built on `QualitySignal`
should be trusted in either direction.

### D2 — charter:38-41 · does Scout's *residue* earn a member? · f-016 vs f-021/f-022

- **f-016** (miyadaiku): three of Scout's seven fields have named carriers today; a member
  carrying no unique load is ornament. Implied verdict: no member.
- **f-021/f-022** (usul al-fiqh): the two fields *without* carriers — `authority: speculative`
  and the expiration/review condition — are exactly the ones the runtime cannot express, and
  that is the argument *for* a graded write path, not against it.

Neither lens can adjudicate this alone, and their declared failure modes are precisely
complementary: miyadaiku is "blind to record integrity — cannot see contamination, authority
drift, provenance loss"; usul al-fiqh "cannot judge structural or implementation cost —
indifferent to whether enforcing a grade ladder requires re-cutting the phase machine."
The live question they jointly pose is the sharpest one in the run: **is the residual an
argument for a seventh phase, or an argument for a `grade` field on `agent.Evidence`?** Note
that the second answer satisfies both lenses and costs one schema change.

### D3 — charter:119 item 7 · rival defect or downstream constraint? · f-006 vs f-007, via f-026

f-026 adjudicated it — the claims are *ordered* (specification, then feasibility), not in
tension; f-007 reaches its conclusion only by imputing `QualitySignal` as the outcome, which is
itself a repair of f-006. The controller still shows the disagreement open because f-007 was
never restated under the adjudication. Substantively settled; bookkeeping-open. Consequence for
the reader: fix the dependent variable *first*, then re-ask whether it is confoundable.

### D4 — charter:41-47 · does the runtime get to define "phase"? · f-032 vs f-001/f-017

f-032 declares f-001 dissolved: the missing backward edge is a category error because no
automatic forward edge exists either. That verdict rests on an axiom the adjudicating lens
states openly — *"a phase is whatever the runtime makes it"* — and on its own declared failure
mode, *"reading the runtime as the arbiter of 'phase' privileges what is built over what should
be built, biasing toward the incumbent frame."* The charter is a document about what OODARC
*should* mean; it is entitled to reject that axiom, in which case f-001 and f-017 revive intact
and the topology at :44 is an unbuilt specification rather than a category error.

**This is the run's deepest unresolved taste call**, and it propagates: if the runtime is not
the arbiter, then f-018's gate-delta discriminator, f-032's ∅ result, and f-033's demolition of
Observe/Decide/Orient all lose their force at once, because all three are runtime-grounded. The
entire convergence spine hangs on one axiom no human has ratified.

---

## If you read one thing

**f-018** — argmax(heat) is a 13-way tie at 18; |taste| = 2 breaks it.

> In Skaffen a phase *is* a capability gate, so the phase/side-loop/capability question is
> mechanical: compute the gate delta. Scout's delta against Orient is ∅.

Read it with its adjudicated form (f-032: delta is ∅ *and* the FSM has no automation, so
declaring `PhaseScout` silently downgrades it to Sonnet via `router.go:78-84` fallback) and its
symmetric application (f-033: the same discriminator fails Observe, Decide and Orient). Then
read D4, which is the one argument that could take all three away.

---

## Appendix — Spice Trail

**Round 0 · assay · 2 agents · 25 findings · yield 20 · novel_cluster_rate 0.64**

Two tiers dispatched: adjacent (`fd-cybernetics-loop-topology`,
`fd-epistemics-provenance-falsification`, `fd-ontology-naming-distinctness`) and distant
(`fd-miyadaiku-loadpath` — kigumi joinery / kiwari module / shikinen sengu cadence;
`fd-usulfiqh-authority` — qiyas, graded reliability, isnad). The distant tier earned its slot:
miyadaiku produced the gate-delta discriminator (f-018) and the load-path reframe of the null
(f-016); usul al-fiqh produced the four-hop laundering path (f-021) and the terminated-chain
finding (f-023). Three refutations in this round (f-014, f-015, f-020), all in the
naming/complexity-cost region.

**Round 1 · probe · 2 directives · 6 findings · yield 2 · novel_cluster_rate 0.67**

- `PROBE-DISAGREEMENT` — *"open contradiction — adjudicate."* Steered at the f-006/f-007
  collision on charter:119, the run's only two-lens contradiction at a single line. Spawned the
  `disagreement-adjudication` lens (axiom: order the claims, do not split them; ground the
  disputed term under every reading). Returned f-026 (settlement) and **f-027 (emergent)** — the
  probe's payoff was not the adjudication but the trace into `store.go` that the adjudication
  forced.
- `DEEPEN` on `fd-cybernetics-loop-topology` — *"risk 6, unconfirmed — confirm or refute."*
  Returned f-028 (confirmed and widened: the box-shaped spec, not just the S seeds, excludes the
  edge-modifier class) and f-029 (the outcome measure is monotone against exploration), plus two
  refutations (f-030 pace-criterion, f-031 recommendation-has-no-expiry).

Yield dropped 20 → 2 while novel_cluster_rate *rose* 0.64 → 0.67: the round found few findings
but they landed in new clusters. Correct signal to probe again rather than assay wide.

**Round 2 · probe · 1 directive · 2 findings · yield 1 · novel_cluster_rate 0.5**

- `PROBE-DISAGREEMENT` — *"open contradiction — adjudicate."* Steered at the f-001 (code-shaped:
  no backward edge) vs f-018 (semantics-shaped: a phase is a gate) collision at charter:41-47.
  Spawned `control-flow-archaeology` with `fd-cybernetics-loop-topology` ×
  `fd-miyadaiku-loadpath` as parents. Returned f-032 (adjudication: (2) holds, (1) dissolves)
  and **f-033 (emergent: point the discriminator at the incumbents)**. Both from finding the
  single non-test caller of `AdvancePhase()`.

**Halt: DRY.** novel_cluster_rate 0.5 and yield 1 on round 2. Note the tension flagged in
caveats: the round that triggered DRY still produced a novelty-3 finding that inverts the
charter's framing, and 11 of 24 budget slots were unspent.

**Steering summary.** Every round-1 and round-2 slot went to `PROBE-DISAGREEMENT` (plus one
`DEEPEN`); zero went to `FUSE` or `STEER-WIDE`. That produced both emergent findings — the
disagreement probes were the only place fused reasoning happened — but it also means the
candidate space was never widened after round 0. The loop got sharper, not broader.

---

## Caveats

1. **Every lens in this run carries a declared anti-S bias.** All five base lenses name it in
   their own `failure_mode`: miyadaiku — *"biased toward the no-S null and against Scout,
   Speculate, and any exploration-shaped candidate"*; epistemics — *"will happily recommend the
   design that never produces a wrong idea because it never produces an idea"*; usul al-fiqh —
   *"will systematically prefer restrictive contracts and the no-S null"*; ontology — *"can talk
   itself out of every candidate on parsimony grounds"*; cybernetics — *"prone to rejecting a
   fuzzy-but-generative practice because its trigger cannot be written as a predicate."* No lens
   with the opposite bias was ever dispatched. **The ledger's unanimity against Scout is
   partly constructed by lens selection.** The individual findings remain sound — most are
   verified facts about committed code — but the *absence* of pro-S findings is non-diagnostic,
   which is f-010's own defect reproduced one level up.
2. **Two of the six charter-mandated source domains never became lenses.** Ecology / evolution /
   exploration-exploitation (:71) got no lens at all, and rhetoric / linguistics (:72) was only
   partially covered by `fd-ontology-naming-distinctness`. The bandit / optimal-foraging /
   Lévy-flight frame is the one most likely to produce a defensible affirmative case for a
   sparse exploration operation, and it never reviewed the charter.
3. **Zero scheduled fusions.** `fusion_stats: {attempted: 0, emergent: 2}`. The charter at :107
   required at least two productive lens pairs; both emergent findings came from
   `PROBE-DISAGREEMENT` lenses instead. The highest-value unrun pair is
   `fd-usulfiqh-authority` × `fd-cybernetics-loop-topology` (retirement as a control element).
4. **Halted DRY with 11 of 24 slots unspent** while round 2 was still returning novelty-3
   findings (f-033). The DRY criterion measures cluster novelty, not finding novelty; on this
   run those diverged.
5. **Ledger status anomaly.** f-014 and f-020 carry `status: refuted`, yet f-028 (upheld) opens
   *"CONFIRMED, and wider than claimed"* and lists both in its convergence refs. Refuted
   findings are excluded from all five views per protocol, so the letter-first constraint is
   represented only by f-028. The disposition of f-014/f-020 is unresolved from the ledger alone.
6. **No independent verification pass.** `status` flags came from the round agents; risk
   likelihoods here are my judgment against the rubric above, not measured. All code citations
   are the lenses' own, re-read from the ledger but not re-executed against the tree in this
   synthesis pass.
7. **Clusters and disagreement sets are from controller state**, not recomputed from the on-disk
   rows.
8. **Regions never reached:** no candidate was ever *scored* — the run produced 28 findings
   about the charter's machinery and zero comparative evaluations of Speculate, Stress-test,
   Simulate, Share or Select against Scout. The tournament the charter asks for has not been
   run; this synthesis says only that, as specified, it could not have produced a trustworthy
   result.
