---
artifact_type: melange-synthesis
method: flux-melange
target: docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md
target_description: >-
  Review charter for a candidate TOURNAMENT deciding what (if anything) the optional S in
  OODARC(+S) should mean. The charter is accepted as given; the work was to RUN the tournament
  it specifies — generate candidate S contracts from five mandatory advocate positions,
  cluster them, adversarially compare survivors against the no-S null, and recommend the
  smallest coherent design.
goal: >-
  Run the candidate tournament, not another charter audit: enforce the mandatory balanced seed
  portfolio, generate and cluster at least twelve S alternatives, adversarially compare
  survivors with no-S, attempt the two required fusions, and recommend the smallest
  semantically distinct, epistemically safe, pace-aware design with independent falsifiable
  pilots.
weights: balanced
rounds_run: 4
halt_reason: BUDGET
total_fusions: 6
emergent_findings: 16
runtime: claude
date: 2026-08-24
---

# OODARC(+S) Tournament v2 — Melange Synthesis

73 findings, 47 clusters, 16 cross-lens convergent clusters, 13 disagreements open at halt.
Scores below are **my re-score of the merged ledger**, not the per-round triage estimates.
Where I moved a score I say so.

## The field, as it stands at halt

The generation requirement was met and overshot. Twenty-plus raw candidates were filed;
after contract-equivalence clustering the field is:

| Candidate | Class | Origin finding | Named in either charter? |
|---|---|---|---|
| **Fallow** | policy / withheld-tasking baseline | f-063 | no |
| **Survey** | policy / untriggered fixed-effort sampling | f-064 | no |
| **Slacken** | policy / clock-only pace arm | f-071 | no |
| **Stint** | policy / adaptive probe:grade rate | f-067 (repairs the refuted f-052) | no |
| **Season** | policy / pre-committed cohort rate | f-057 | no |
| **Divert** | policy / marginal-value patch-leaving | f-034 (f-001 refuted) | no |
| **Widen** | policy / sampling modulator | f-002 | no |
| **Reprove** | subtractive / staleness-triggered demotion | f-030 | no |
| **Melt** | subtractive / defacement-not-deletion | f-029 | no |
| **Retire** | subtractive / status transition | f-006 | no |
| **Assay** | capability / re-marking material it did not produce | f-026 | no |
| **Warrant** | capability / graded expiring licence to spend | f-042 | no |
| **Trace** | capability / pre-registered budgeted probe | f-031 | no (absorbs Scout's search half) |
| **Frontier** | artifact / addressable null-lead ledger | f-032 | no |
| **Sweep** | capability / bounded mechanism-space variation | f-003 | no (already shipped in `internal/experiment`) |
| **Register** | capability / loop-position read filter | f-073 | no |
| **Ash** | artifact / unretained elaboration | f-072 | no |
| Scout | — | absorbed into Trace by f-060 | yes |
| Stress-test | — | gate-delta claim refuted (f-007); never re-contracted | yes |
| Share / Select / Template / Transplant | — | failed phasehood (f-018, f-019, f-020, f-017) | no |
| **no-S null** | — | f-021 (capability map), f-034 (allocation-side null) | yes |

Fifteen candidates named in neither charter (requirement: three). Three subtractive
(requirement: one). Seven that change allocation policy rather than emitting a report
(requirement: one). The charter's own five named S-verbs contributed one survivor between
them, and it survived only by being absorbed into a non-S-named contract.

---

## 1. Novelty × Risk Frontier

Risk saturates at 9 (blast 3 × likelihood 3), so the strict Pareto front collapses to a
five-point ridge. I report the ridge, then the two adjacent contours — the **shoulders** —
because that is where the max-novelty/mid-risk and mid-novelty/max-risk leads actually live.
Both shoulders lead alongside the ridge.

### Lead — max novelty × max risk (the knee): f-070

**The runtime strips each probe's evidence and keeps its assertion.**
`microCompact` (internal/agentloop/autocompact.go:149) branches on
`block.Type == "tool_result" && len(block.ResultContent) > 200` — that is the *only*
content-elision branch. The stub at :157 keeps `ToolUseID`/`IsError` and drops the payload.
Assistant text blocks are never stubbed; they survive until `snip` deletes the whole message.
No compensating durable write exists — `agent.Evidence` records tool *names* only
(internal/agent/deps.go:61-86) and `ReplaceMessages` is in-memory.

Lens: **fd-gamelan-irama-stratification** (round-3 STEER-WIDE distant lens, no parents).

Consequence for the tournament: **any candidate that satisfies hard gate 3 (epistemic
separation) with an in-band grade, citation, or namespace annotation fails it mechanically.**
Over a long session the context converts from evidence-plus-interpretation to interpretation
alone, in one undifferentiated register. This directly contradicts the annotation-based
remedies proposed in f-043 and f-058 — the run's own most-cited fixes.

Risk decomposition: blast 3 (invalidates a remedy class shared by most of the field, and
rewrites the gate itself), likelihood 3 (the branch is deterministic and code-verified).
Novelty 3 — no seed lens reached it; it was found by a lens the controller added at round 3
because widening was still paying.
Severity, for reference only: P0.

**Design implication:** amend the hard gate to require that separation be carried by
**material** — a distinct store, tool, or message role — never by annotation. If in-band
carriage is kept, the stub at autocompact.go:157 must be made self-warranting (carry
`block.Name` plus an evidence-store ref written at elision time).

### Lead — mid novelty × max risk: f-022

**Applied symmetrically, the runtime-enforcement gate indicts Decide, not the S candidates.**
`defaultGates` gives Observe, Orient and Decide a byte-identical unconstrained
`read/glob/grep/ls` (internal/tool/registry.go:49-58); `phaseDefaults` routes all six phases
to `ModelOpus` (internal/router/router.go:20-27); every transition is the same human
`/advance` keystroke (internal/tui/commands.go:196-215). Orient's sole delta is one read-only
tool (`quality_history`, builtin.go:26-29) plus the prompt-level Inspire block. **Decide has
no tool, constraint, prompt clause, or routing difference of any kind.**

Lens: **fd-cybernetics-parsimony-adversary** (the mandated parsimony adversary), corroborated
on the underlying three-signature fact by **runtime-enforcement-adjudicator** (f-036) and
**fd-gamelan-irama-stratification**'s sibling (f-061).

Risk decomposition: blast 3 (this is a claim about the OODARC design itself, not about a
candidate), likelihood 3 (verified in four files). Novelty 2 — the fact is checkable and
several lenses touched it; the *symmetric application* is the move.
Severity, for reference only: P0.

This is the single strongest argument against a seventh letter that does not depend on any
candidate's weakness: a runtime in which one existing phase is already enforcement-vacuous
cannot coherently charge a new candidate for failing an enforcement test.

### Lead — max novelty × mid risk: f-064

**Survey — untriggered fixed-effort sampling, and the 2×2 that saves it from the clustering
rule.** Every trigger-conditioned candidate in the field (Scout, Trace, Stress-test) is
*fishery-dependent by construction*: it observes the environment only where its own trigger
fired. Survey samples on a fixed cadence against a frame chosen independently of any trigger,
producing prevalence rather than leads. Paired with Fallow (f-063) it forms an identification
2×2 that no other pair in the field can produce:

| | Survey high | Survey zero |
|---|---|---|
| **Fallow high** | rich patch, working trigger | — |
| **Fallow zero** | rich patch, exhausted/broken loop | genuinely empty field |

Lens: fusion **fd-fused-quota-blinded-foraging** (foraging × fd-fused-warranted-variation);
emergent=true, neither parent reported the trigger-conditioning cause.

Risk decomposition: blast 3 (without it "the loop stopped exploring" and "the patch went
empty" are inseparable in the headline comparison), likelihood 2 (bites only once the pilot
runs). Novelty 3.
Severity, for reference only: P1.

Runtime delta is real and large: Skaffen has no untriggered cross-session scheduler at all —
every phase entry is manual (commands.go:196-201) and every incumbent read path is
task-conditioned (inspire.go:20-40).

### Rest of the ridge (novelty 3 × risk 9)

| ID | Claim | Lens | Blast × Likelihood |
|---|---|---|---|
| f-066 | The incumbent exploration allocator re-strikes on **every Orient turn** against a stock that changes **once per session** at Compound, so every re-strike after the first is provably zero-information; the no-S null carries an unpriced per-turn survey tax that contaminates every turn-denominated arm comparison. `loop.go:189` passes `TurnCount`; `agent.go:349` forwards only `hints.Budget`; `session.go:78` discards it as `_ int`. | fusion **fd-fused-allocator-regress** (foraging × grading-arm-allocation) | 3 × 3 |
| f-050 | Compound's manifest-globbed `*.md` write is **not** unindexed: `*.md` covers CLAUDE.md/AGENTS.md, which `contextfiles.Load` prepends to every future session's system prompt at top precedence, byte-indistinguishable from human-authored text. Transfer *is* carried — by a carrier that fails all four of the charter's own epistemic-safety clauses. | **epistemic-provenance-forensics** (transfer × parsimony adjudicator) | 3 × 3 |
| f-028 | The no-S null self-certifies by throughput (TokenEfficiency, TurnCount) with maker and office identical; and because the charter mandates *identical recording paths* against a single global store, arm A's rows enter arm B's Orient prompt. The contamination is directional and adverse to S. | **fd-assay-hallmark-grading** (distant) | 3 × 3 |
| f-042 | The epistemic-separation hard gate grades **products**, so a candidate whose output is an allocation change clears it by emitting nothing — **the gate ranks candidates in inverse order of governability.** Skaffen already runs an unwarranted allocation channel of exactly that shape (`shouldEscalate` → model upgrade, with the authorizing estimate destroyed at costrouter.go:75 before the spend is evaluated). Fix: the **Warrant** contract plus a fourth gate clause. | fusion **fd-fused-graded-allocation** (required fusion 1) | 3 × 3 |

### Shoulders

**Mid-novelty / max-risk (N2 R9), beyond f-022:**

- **f-061** — Skaffen's gate space contains only three distinguishable signatures
  (read-only / read+web / write-capable), so contract item 7 read as "name the capability
  delta" **false-negatives every candidate whose novelty is temporal or authority-shaped** —
  Trace, Assay, Reprove — while rewarding any candidate that merely re-labels Decide's tool
  set. Twelve candidates cannot be separated in a 3-valued space.
  (probe-disagreement-scout-disposition, raw.)
- **f-031 / f-037** — `ResetRateCounts` is documented "call on phase transition" and has
  **zero production callers**; every `RateLimit` is a per-process-forever budget. Any
  candidate whose stop rule reads "N probes per S visit" silently gets N per *session* and
  starves on later loops. (karst distant lens; runtime-enforcement-adjudicator.) I moved
  f-031's novelty 3→2: the Trace contract is close to the charter's own Scout description at
  :29; the load-bearing content is the dead-reset fact, which converged three ways.

**Max-novelty / mid-risk (N3 R6):**

| ID | Claim | Lens |
|---|---|---|
| f-046 | No contract field denominates probe rate in units of **grading capacity**, and Skaffen's is a hard constant of one punch per session (`Aggregate` emits exactly one QualitySignal) while probe production is O(k). A winning S at ~5 reports/session leaves ~50 unmarked reports after ten sessions, all recoverable by `cass` and injected verbatim into Orient. | fusion fd-fused-assay-limited-foraging |
| f-047 | The pilot equalizes arms in turns/tokens but grades "validated mechanism discoveries" **outside** that budget, so validation is free to the arm that generated the lead. Concrete: A emits twelve cheap touchstone analogies, validates none in-loop, scores 4; B cupels two to dispositive grade, scores 2; A wins having consumed four units of an office with no budget line. | fusion fd-fused-assay-limited-foraging |
| f-055 | **The grading scale itself retires the exploration arm.** `QualitySignal.Scores()` is five cost axes plus a binary outcome; a probe-heavy session is Pareto-dominated on three and can win on none, and `ParetoFront` has no epsilon, recency term, or sampling floor to readmit it. `Suggest` then injects "Break into smaller steps" / "Reduce context" — literal instructions to explore less — into the next Orient prompt. Minimal remedy is a **floor**, not a metric. | fusion fd-fused-grading-arm-allocation |
| f-063 | **Fallow** — the missing zero point. An S whose entire output is one number: the incumbent loop's spontaneous exploration rate, measured by withholding S-tasking for a pre-registered window. Countable today from existing evidence `tool_calls` with zero new instrumentation. Losing condition: if spontaneous exploration already meets the proposed quota, :43 resolves for the null **and takes every S candidate with it**. | fusion fd-fused-quota-blinded-foraging |
| f-071 | **Slacken** — compaction schedule is an uncontrolled covariate that fires *earlier* in the arm that explores more (`calculateTokenPressure` at `effectiveWindow - 13000`), so "disconfirmed hypotheses retained" is anti-correlated with the treatment by construction. `acCfg` is built once per Run, so the pace candidate has a real enforcement seat that Decide entirely lacks. | fd-gamelan-irama-stratification |
| f-043 | Contract field 4 asks for a **single expiry policy over two different objects** — the speculative claim (must lapse) and the failed-probe cost record (must persist to make the stop rule computable). Both horns are live in the repo. Every contract must either kill its own trigger or launder retained negatives into Orient. | fusion fd-fused-graded-allocation |
| f-072 | The **survival test**: what crosses Skaffen's compaction boundary is only `{first 200 chars of goal, ≤10 read/write/edit paths, phase string}` — probe/search tools contribute *zero* residue. Scout/Speculate/Synthesize/Trace therefore have identical (zero) persistence and are one operation under a persistence-based clustering rule. Taste +1. | fd-gamelan-irama-stratification |
| f-026 | **Assay** — an S whose only transformation is re-marking material it did not produce, with a touchstone (cheap, indicative) / cupellation (costly, dispositive) probe ladder. Discriminator against Scout: charter:29 collapses the two by attaching "falsifiable prediction" and "reversible probe" to one emitted report without naming who pays for cupellation. | fd-assay-hallmark-grading |
| f-030 | **Reprove** — required fusion 2 (cybernetic control × organizational transfer) yields staleness-as-trigger and knowledge-decay-rate as the control variable: the only candidate in the field that **removes** authority. Fires when the recorded source artifact's commit no longer matches current state, not on human hunch. | fd-assay-hallmark-grading (in-lens fusion) |

**Near-front candidate contracts (N2 R6)** — off the ridge on novelty but carrying full
eleven-field contracts, so they rank ahead of most higher-scored critiques for tournament
purposes: **f-029 (Melt** — retirement built as defacement rather than deletion, with the read
filter, not the move, as the actual retirement, and an explicit prohibition on `os.Remove`);
**f-032 (Frontier** — an addressable lead ledger where a null is a first-class row, implemented
as an `if frontier.IsExhausted(fingerprint) { skip }` guard inside `Store.Inspire`, which today
re-surfaces and re-pays for a lead probed to null last week); **f-003 (Sweep** — bounded
variation in *mechanism* space reusing `internal/experiment`'s `ExpandMutations` machinery,
capped at 24 permutations. Neither charter mentions that Skaffen already ships an exploration
subsystem, which is a hole in the affirmative-null specification the charter demands at :43).

---

## 2. Top Fusions

Six fusion lenses were dispatched (rounds 1–3), plus two in-lens fusions filed by distant
lenses in round 0. Sixteen findings passed the emergence gate; the assayers demoted nine
others to convergence and refuted two — the negative results are reported below, because a
fusion that reproduces its parents is the most useful thing a fusion can tell you.

Ranked by novelty × risk of the pair's best emergent finding.

### 1. fd-fused-allocator-regress (foraging × fd-fused-grading-arm-allocation) — heat 27

Best emergent: **f-066**. Intersection justification: the foraging parent supplies dwell,
hysteresis and the congestion-vs-shear trigger distinction — without it the per-turn re-run
reads as a mere efficiency nit. The meta-allocation parent supplies the frame that the
split-setter is *itself a spend from the pool it governs*, running on a clock that may differ
from its stock's clock. Only the cross term yields the load-bearing claim: **the re-strike
cadence strictly dominates the evidence cadence, so the survey's recurring cost is provably
100% regret.**

Evidence: `loop.go:189` calls `SystemPrompt(PromptHints{... TurnCount: turn})` every
iteration; `agent.go:348` forwards only `hints.Budget`; `session.go:78` is
`SystemPrompt(phase tool.Phase, _ int)`. Inside, `formatQualityHistory` re-reads the global
JSONL, `Inspire` reaches `BestApproach` twice (each a full file re-read plus an O(n²)
`ParetoFront`) and execs a `cass` subprocess. No memoization anywhere. The only writer of
that stock is Compound-gated. One-hunk fix: thread `TurnCount` and gate on `turn == 0`.

Independently corroborated the same round by **fd-gamelan-irama-stratification** (f-073)
arriving at the same dropped-`TurnCount` plumbing from positional admissibility — same
cluster, different consequence. Cross-tier corroboration is why I keep this at likelihood 3.

Second emergent from this pair: **f-069** (the pilot corpus is stock consumed by being
assayed, and the two classes the losing condition depends on — no-benefit cases and tempting
false analogies — are the scarcest and least likely to be stocked). The finding concedes
either parent alone yields a generic "specify the corpus" note; I moved its novelty 3→2 for
exactly that reason.

### 2. fd-fused-graded-allocation (foraging × reconnaissance) — heat 27 — **required fusion 1**

Best emergent: **f-042**. Intersection justification: foraging contributes the primitive that
an allocation change is *itself the product*; reconnaissance contributes tasking, grading and
expiry. Without foraging the gate looks fine — it correctly grades reports. Without
reconnaissance you would only ask that exploration be bounded, not that the licence be issued,
graded, and readable after it lapses. The inversion — unmarkable candidates passing the
strictest gate most easily — is visible only where the two meet.

Evidence is an existing production instance: `shouldEscalate()` turns three ungraded counters
into a model upgrade; `costrouter.go:74-75` calls `tracker.reset()` **at the moment of
escalation** (contradicting the doc comment at complexity.go:129-130 claiming reset on
successful completion), so the estimate that authorized the spend is destroyed before the
spend is evaluated. The reason string survives one hop into `Evidence.ModelReason` and is
dropped by `aggregate.go:56-93`.

Also emergent from this pair: f-043 (field 4 governs two objects), f-044 (the pilot equalizes
a currency it never names — `BudgetTracker.Record` meters either `billing` or `context`,
defaulting to `billing`, and the S-arms differ from the null precisely by parking speculative
material in cached context, so "equal budget" hands the exploration arm either a subsidy or a
tax; I raised f-044's likelihood 2→3 because the default is in the code), and f-045 (the
clustering predicate merges on contract/trigger/output/authority but **never on spend**, so a
cheap screen and a costly dispositive test collapse into one candidate before scoring).

### 3. epistemic-provenance-forensics (transfer × parsimony) — heat 27

Best emergent: **f-050**, above. Its intersection justification is the cleanest in the run:
*both parents touched this location and neither connected the causes* — one concluded
"carried, therefore no gap" (f-021), the other "unindexed, therefore thin" (f-016). Only the
connection — the carrier exists **and** is ungoverned — refutes both.

Corollary f-051 (demoted to convergence): Skaffen's knowledge plumbing has writers and readers
at both ends and **no remover at either**, which retargets the mandated subtractive candidate
from the mutations store (rates-only, fenced read path) to the **context-file channel**
(arbitrary prose, top precedence, all phases) — and falsifies the charter's closing goal at
:172, because a competing truth channel already exists in the incumbent at higher authority
than any candidate could propose.

### 4. fd-fused-assay-limited-foraging (foraging × assay) — heat 18

Emergent: f-046, f-047, f-049. The pair's signature move is finding **missing exchange rates**
rather than missing fields. f-049 is the elegant one: lesson 5 grounds failed-probe retention
in "durable evidence about source-domain base rates," but the store has no source-domain
dimension — the only index is `TaskType` from substring-matching "fix/refactor/optimize/doc/add".
A failed transfer borrowed from immunology is filed under "feature"; the next probe into
immunology is drawn with an unchanged prior. **The retention is keyed to the wrong noun,
making the preserved record allocationally inert.**

Negative result: f-048 (the equivalence key is output-shaped so the policy candidate collapses
into the null) was **demoted to convergence and then refuted** — the foraging parent had
already filed the cause (f-005), and f-038 showed the fold does not go through because the
policy candidate differs on outputs, consumer, and authority simultaneously.

### 5. fd-fused-quota-blinded-foraging (foraging × fd-fused-warranted-variation) — heat 18

Emergent: **f-063 (Fallow)** and **f-064 (Survey)** — the run's only two genuinely new
*candidates* produced by a fusion rather than by a base lens. Two of four findings demoted:
f-062 and f-065 both landed on locations the ledger already held.

f-062's demoted increment is nonetheless the sharpest checkable fact in the run:
`inferTaskType` (write side) can return only docs/feature/refactor/bugfix/general, while
`ClassifyTask` (read side) *can* return `TaskOptimization` — so **`optimization.jsonl` is
provably unwritable**, a permanently empty logbook Orient consults on every "optimize/perf/
faster" task. The no-S null's strongest incumbent is being credited with a compounding
capability whose evidence channel has never functioned.

### 6. fd-fused-grading-arm-allocation (foraging × fd-fused-assay-limited-foraging) — heat 18

**Largely independent here.** Four findings: one refuted (f-052, the first Stint filing, whose
enforcement mechanism was `GateConstraint.RateLimit` — broken in both directions per f-053),
two demoted to convergence (f-053, f-054), one emergent (**f-055**). This was the run's
weakest fusion by yield and the controller correctly stopped re-fusing this branch.

f-053's demoted increment is worth keeping: the rate counter is incremented **before** the
sandbox check, so probes the runtime itself refuses burn budget identically to productive
ones — an absorbing barrier that manufactures false negatives.

### 7. fd-fused-warranted-variation (foraging × fd-fused-graded-allocation) — heat 12

**Mostly independent here.** Three of four demoted (f-056, f-057, f-059); one emergent
(**f-058**: Frontier's fingerprint guard is a *spend-side* economy that lowers the marginal
cost of minting a lead, while no contract field issues a **mint quota** — so the lead ledger
ratchets upward and drains into a fixed-length Orient prompt through a path bounded only by
recency, not by grade). f-057 (Season) is a real candidate but its field 7 asserts
`ResetRateCounts` zeroes the counter on phase transition, which f-031/f-037/f-053 establish
is false; its runtime-delta half must be re-derived before scoring.

### 8. In-lens fusions filed at round 0

- **fd-assay-hallmark-grading** filed **f-030 (Reprove)** as the charter's *required fusion 2*
  (cybernetic control × organizational transfer) — staleness-as-trigger, decay-rate as control
  variable. Both required fusions were therefore attempted and both produced contracts.
- **fd-karst-tracer-conduit-probing** filed **f-034** as a half of required fusion 1, yielding
  the emergent allocation rule: **charge probe budget to the lead, not the session**, making
  the stop rule cumulative-cost-per-lead and checkable against the Frontier ledger. It also
  filed the honest allocation-side null: *no operation allocates probing effort today* — the
  only bound on exploration in the runtime is `maxTurns:100`, a crash guard.

---

## 3. Taste Calls

The taste dimension was badly under-exercised: 4 of 73 findings carry any taste score, all
positive, none negative. That is itself a caveat (see below), not a finding that the design
has no smells.

**+taste to preserve**

- **f-072 — taste_kind: simplicity (+1).** The survival test as a clustering rule: *same
  persistence ⇒ same candidate*. It collapses four emitter candidates at once — the cheapest
  shortlist reduction in the run — and it is consistent with f-060's independent absorption of
  Scout into Trace. Adopt it into Required-output item 1 alongside the existing
  contract-equivalence predicate.
- **f-067 — taste_kind: simplicity (+1).** The repaired Stint contract argues *for* an
  allocator and *against* an S letter in the same document, and classifies itself out of
  phasehood in field 11 ("capability plus control state, explicitly NOT a phase"). A candidate
  that refuses its own promotion is the correct shape for this tournament.
- **f-025 / f-041 — taste_kind: naming (+1 each), and they disagree on the remedy.** Each of
  O/O/D/A/R/C names one operation; S currently names eight or more, so the letter carries no
  mnemonic load (f-025). f-041 sharpens it into a procedural objection: the initial letter S
  constrains generation at :13 and re-enters at scoring time as "mnemonic/taste" at :115 — an
  **undeclared gate applied after the declared ones**, against a field (Trace, Assay, Reprove,
  Frontier, Divert, Fallow, Survey, Slacken) that contains zero S-names. See §5 for the open
  split on remedy.

**−taste smells to fix**

None were scored. On my re-read the run left one unscored smell on the table: the charter's
`§Mandatory disagreement` list (:124-130) is written as six verb-pairs, and four of the six
were adjudicated only by dissolving one side of the pair (Scout into Trace, Share into
plumbing, Select into an edge predicate, Synthesize into a refuted duplication claim). A
disagreement list whose items resolve by dissolution is a taxonomy smell, not an adjudication
schedule. I flag it rather than score it, because no lens filed it.

---

## 4. Convergence Spine

Sixteen clusters drew findings from more than one lens. These are commodity: high confidence,
low novelty. Trust them; do not lead with them.

**Settled facts about the runtime** (each independently reached by 3+ agents):

- **Nothing in Skaffen expires, demotes, retires or prunes anything.** All stores are
  `O_APPEND`; `QualitySignal` has no TTL/status/validity field; the only forgetting is
  `ReadRecent(n)`, a recency window. Retirement is the null's one provable capability gap.
  (f-006 falsification, f-029 assay, f-040 falsification-probe, f-051 provenance-forensics.)
- **An ungraded, unexpiring speculative channel already runs in production.** External `cass`
  output is shelled out on a truncated keyword query and injected verbatim into the Orient
  system prompt with no source, grade, timestamp or expiry; four unconditional hops carry any
  turn's footprint into a cross-session aggregate Orient reads back, and no hop carries or
  checks a grade. (f-012, f-013 reconnaissance; f-027 assay.)
- **`ResetRateCounts` has zero production callers**, so every `RateLimit` is a per-process
  lifetime budget, and the increment precedes the sandbox check. (f-031 karst, f-037
  adjudicator, f-053 fusion.)
- **Scout's proposed gate signature is Decide's shipped gate set verbatim.** read+web,
  no write/bash = `{read, glob, grep, ls, web_search, web_fetch}` = Decide. Orient differs by
  one read-only tool. The genuinely distinct half — "forbidden to conclude" — has no
  expression in `GateConstraint`, which carries only AllowedGlobs/RateLimit/RequirePrompt.
  (f-011 refuted → f-023 parsimony, f-036 adjudicator, f-060 R3 adjudicator. **Resolved:
  Scout is absorbed into Trace.**)
- **The phase FSM is forward-only.** `phaseOrder` is a fixed six-element slice; `Advance` only
  increments and errors past Compound; the sole caller is the human `/advance` command. The
  charter's "optional side-loop" outcome therefore **has no runtime expression**, and every
  side-loop candidate fails the explicit-re-entry-path hard gate unless field 7 names the FSM
  change. (f-015 reconnaissance, f-033 karst.)
- **The pilot's arms are uninstrumented.** No automatic trigger exists, so the S arm fires
  only on a human keystroke; `agent.go:247` is the sole QualitySignal write trigger and is
  Compound-gated, so abandoned sessions leave no trace. (f-024 parsimony, f-065 fusion;
  f-004's stronger claim — unobservable *in principle* — was refuted by f-063.)
- **Write key ≠ read key.** `WriteForType` files by `inferTaskType(tool calls)`; `Inspire`
  draws by `ClassifyTask(description)`; probe-class tools match no case in `inferTaskType` at
  all. (f-054 fusion, f-062 fusion.)
- **Field 4 needs a typed schema, and `internal/experiment` already contains the pattern.**
  `ExperimentRecord` carries Hypothesis/Status/MetricBefore/After/Delta/AgentDecision-vs-
  effective-Decision/OverrideReason/GitSHA — exactly the anti-laundering structure, implemented
  once and not reused by the evidence stream. (f-008, f-014, f-043, f-049.)
- **The grading scale is cost-only.** `Scores()` returns five cost axes plus a binary outcome
  with no discovery, transfer, or retained-disconfirmation term; two of the six objectives
  (`ToolDenialRate`, `ApprovalRate`) are constant zero on every row ever written. (f-055,
  f-068.)
- **`TurnCount` is computed every turn and discarded before prompt assembly.** (f-066, f-073.)
- **The letter S is an undeclared gate.** (f-025, f-041.)
- **The equivalence key is incomplete** — it omits spend (f-045) and issuing authority
  (f-059).
- **The policy-class slot is genuinely under-filled by the charter's own seed design**, though
  not at the 10:1 ratio first alleged: 5 named report-emitters, 2 nulls, 3 untyped free slots,
  1 subtractive, 1 policy. The surviving bias is that the three free slots carry a *novelty*
  quota with no *class* quota, so they anchor report-shaped by example. (f-038 refuting f-005;
  f-034.)

---

## 5. Live Disagreements

Thirteen contradictions were open at halt. These are the primary signal — several are
unresolved taste calls that decide the tournament's shape, not its details.

**D1 — Can epistemic separation be carried in-band at all?**
f-070 (gamelan) says no: compaction strips evidence and keeps assertions, so grade/namespace/
expiry *fields* are unreliable by construction. f-043 and f-058 (both fusion-emergent) propose
exactly such in-band annotations as their remedies. **This is the highest-stakes open
disagreement in the run**: if f-070 holds, the remedy class most of the field relies on is
void and separation must be material. Unresolved because f-070 arrived in round 3 and the
verification pass was budget-clamped.

**D2 — Is there an exploration variable in the incumbent at all?**
f-002 (foraging): the runtime is pure exploitation — `phaseDefaults` maps all six phases to
one model, and the only history channel is a philopatry bias with no exploratory counterweight.
f-021 (parsimony): exploration *is* carried, by `web_search`/`web_fetch` in Orient/Decide/Act.
f-066 (fusion) reframes both: there **is** an allocator — the Orient injection — and it
re-strikes every turn against a once-per-session stock. Three readings of the same code, and
the affirmative-null specification the charter demands at :43 depends on which is right.

**D3 — Which candidate occupies the single mandated policy-class slot?**
Five exclusive claimants: Fallow (f-063), Stint (f-067), Slacken (f-071), Season (f-057),
Divert (f-034/f-001-refuted). They are not contract-equivalent — Fallow measures by
withholding, Stint re-strikes an adaptive ratio, Slacken changes the base clock, Season fixes a
pre-committed cohort rate, Divert reallocates on a stagnation signal — but the charter mandates
"at least one," and the tournament never ranked them. **This is the largest unfinished piece of
the tournament proper.**

**D4 — Is Compound thin, or is it the most dangerous write in the system?**
f-016 and f-020 (transfer): Compound's durable output is a rates-only QualitySignal plus an
unindexed markdown write, so transfer candidates duplicate nothing. f-021 (parsimony): transfer
is carried, therefore no gap. f-050 (forensics adjudicator): **both lose** — the markdown write
lands in CLAUDE.md/AGENTS.md and is read back at top precedence. I score f-050 as having won on
a checkable fact, and I moved f-016's likelihood 3→2 accordingly; but the ledger records it as
open, and the consequence (Compound itself may need the same knife the S candidates get) was
never worked through.

**D5 — Remedy for the letter: rename the winner into an S, or drop the letter?**
f-025 (parsimony): a capability-class winner should keep its verb and take no letter. f-041
(falsification): names are placeholders; score mnemonic only after contract ranking and rename
the winner if needed (Reprove→Sunset, Assay→Screen, Trace→Sound, Frontier→Salient,
Divert→Shunt). Both are +1 taste; they cannot both be executed. This is an irreducible taste
call for the human.

**D6 — Is Season's entry rule (pre-committed rate) or Stint's (adaptive) the right policy
shape?** f-057 vs f-052/f-067. Season's identification argument is strong — with a fixed rate,
a doubled yield distinguishes a richer patch from a looser licence — but its field 7 rests on
the false `ResetRateCounts` premise. Stint's repaired contract (f-067) sidesteps the broken
mechanism with a strike store, but is adaptive and therefore cannot support Season's
identification. Open.

**D7 — Frontier: spend economy or mint accelerant?**
f-032 files the fingerprint guard as the mechanism that stops paying twice for the same probe;
f-058 shows the same guard lowers the marginal cost of minting leads while nothing bounds the
mint rate, so the ledger ratchets and drains into a fixed-length prompt. Both are true; the
contract needs a mint quota on the same clock as the spend warrant, which neither filing
supplies.

**Also open, briefly:** whether Scout's gate signature is a runtime-enforcement delta (f-036 /
f-011 / f-023 — I score this as **resolved against Scout** by f-060, but the ledger did not
close it); whether the policy candidate folds into Scout or the null under clustering (f-038 vs
the refuted f-005/f-048 — resolved against the fold); whether the null's spontaneous
exploration is countable today (f-063 vs the refuted f-004 — resolved in favour of countable);
and the `ResetRateCounts` lifecycle claim inside f-057's contract (f-053/f-037/f-031 — resolved
against f-057).

---

## Where the tournament actually stands

Not a ranking — the tournament was budget-halted before comparative scoring — but the
evidence supports four conclusions strongly enough to act on:

1. **No new letter, on evidence rather than taste.** The FSM is forward-only so "side-loop" has
   no runtime expression (f-015, f-033); the enforcement vocabulary has cardinality 3 so item 7
   cannot separate the field (f-061); and one incumbent phase is already enforcement-vacuous
   (f-022). Adding a seventh phase to that runtime is unwarranted regardless of which candidate
   wins.
2. **The one uncontested capability gap is subtraction**, and after f-050 its correct target is
   the **context-file channel**, not the mutations store. Reprove (f-030) is the strongest
   contract for it because its trigger is mechanical (source-commit staleness), not a hunch;
   Melt (f-029) supplies the retention discipline (deface, never `os.Remove`).
3. **Epistemic separation must be material, not annotated** (f-070) — a distinct store, tool,
   or message role, unreachable from `SystemPrompt`/`Inspire`.
4. **The pilot as specified is uninterpretable and must be repaired before any arm runs.**
   Six independent defects: shared store contaminates arms (f-028), budget currency unspecified
   (f-044), probe rate unpre-registered (f-056), compaction is an uncontrolled covariate
   (f-071), landings are recorded but catch is not (f-065), and validation cost sits outside the
   arm budget (f-047). The cheapest first pilot is **Fallow** (f-063): it needs no new
   instrumentation, and a high reading resolves :43 for the null and retires the whole field.

Independently actionable runtime bugs surfaced along the way, all verified and none dependent
on the S decision: dead `ResetRateCounts` (f-031/f-037/f-053), discarded `TurnCount`
(f-066/f-073), unwritable `optimization.jsonl` (f-062), two constant-zero `Scores()` objectives
(f-068), write-key/read-key mismatch (f-054).

---

## If you read one thing

**f-070** — `microCompact` stubs only `tool_result` blocks and never assistant text, so the
runtime itself strips each probe's evidence while preserving its assertion. argmax(heat) at
3 × 9 = 27, and it is the only finding in the run that invalidates a *remedy class* rather than
a candidate. Every contract in the field whose field-4 answer is "carries a grade" is answering
a question the runtime will erase.

---

## Appendix — Spice Trail

**Round 0 — seed.** 2 agent waves, 35 findings, yield 25, novel_cluster_rate **0.77**.
Seven lenses: the five mandated advocates (foraging/exploration, falsification, reconnaissance,
transfer, parsimony) plus two distant lenses the controller added for range —
**fd-assay-hallmark-grading** (metallurgical assaying: touchstone, cupellation, hallmark, melt)
and **fd-karst-tracer-conduit-probing** (dye-tracer hydrogeology: injection, detector, detection
window). The mandated portfolio held: the exploration advocate generated three distinct
contracts (Divert, Widen, Sweep) before criticizing anything, and the parsimony adversary's
eliminations came after the other four had filed operational contracts. The two distant lenses
outperformed four of the five mandated ones on novelty, producing Assay, Melt, Reprove, Trace
and Frontier — five of the field's fifteen non-charter candidates.

**Round 1 — 4 directives, 14 findings, yield 4, novel_cluster_rate 0.36.**
- `PROBE-DISAGREEMENT` → **runtime-enforcement-adjudicator**, sent at the open Scout-gate
  contradiction (f-011 vs f-023). It adjudicated against Scout (f-036) and produced f-037, the
  budget-namespace finding, as a by-product.
- `DEEPEN` → fd-falsification-disconfirmation-contracts, "risk 6, unconfirmed." It refuted its
  own round-0 f-005 (the 10:1 seed ratio) with f-038, and refuted the seed's Stress-test gate
  delta at f-007 — the falsification advocate falsified itself twice, which is the correct
  behaviour and also why Stress-test has no surviving contract.
- Two `FUSE` directives (shared_heat 0, complementarity 2, redundancy 0) created
  **fd-fused-graded-allocation** (required fusion 1) and **fd-fused-assay-limited-foraging**.
  Both were productive: 7 emergent findings between them, including f-042 and f-046.

The novel_cluster_rate halving from 0.77 to 0.36 is the seed lenses saturating — correctly
diagnosed, since rounds 2 and 3 shifted almost entirely to fusion and adjudication.

**Round 2 — 3 directives, 10 findings, yield 5, novel_cluster_rate 0.60.**
- `PROBE-DISAGREEMENT` → **epistemic-provenance-forensics**, sent at the Compound-manifest-glob
  contradiction. It refuted both sides and produced f-050, one of the run's three heat-27
  findings. **The highest-value directive of the run**: an adjudicator dispatched at a
  disagreement returned the finding neither disputant could reach.
- Two second-order `FUSE`s (fusing a fusion with a parent): **fd-fused-grading-arm-allocation**
  and **fd-fused-warranted-variation**. Both were thin — 2 emergent out of 8 — which is the
  expected cost of fusing overlapping parents, and the assayers correctly demoted rather than
  inflating.

**Round 3 — 4 directives, 14 findings, yield 0, novel_cluster_rate 0.57.**
- `PROBE-DISAGREEMENT` → **probe-disagreement-scout-disposition**, which closed the Scout
  question on a checkable fact (f-060: the claimed signature is Decide's verbatim) and filed
  f-061 as a by-product.
- Two more second-order `FUSE`s: **fd-fused-quota-blinded-foraging** (produced Fallow and
  Survey — the run's only fusion-born candidates) and **fd-fused-allocator-regress** (produced
  f-066, the run's highest-confidence emergent finding).
- `STEER-WIDE` at novel_cluster_rate 0.60 ≥ 0.6 → **fd-gamelan-irama-stratification** (Javanese
  gamelan irama: nested pace strata, a fixed colotomic frame, density doubling). This was the
  best single call in the run. Widening still paid, and the widened lens produced f-070, f-071,
  f-072 and f-073 — including the argmax-heat finding and the only structural argument that
  in-band epistemic separation cannot work.

Yield 0 with novel_cluster_rate 0.57 is the budget clamp, not saturation: all fourteen round-3
findings remain `status: raw` because the verification pass never ran. The loop was still
producing novel clusters at better than one in two when it stopped.

**Halt: BUDGET.** Not convergence. The controller was widening productively and had four
directives' worth of unspent leads.

---

## Caveats

1. **The top of the frontier is unverified.** All fourteen round-3 findings are `status: raw` —
   the assay/verification pass was budget-clamped. That is **14 of the 58 findings I surface**
   (f-060 through f-073), including the argmax-heat finding f-070, the highest-confidence
   emergent finding f-066, and the run's only fusion-born candidates, f-063 and f-064. Each carries a lens self-attestation
   ("VERIFIED on the trace" with file:line), and I spot-checked the file/line citations for
   internal consistency, but none received independent adjudication. Treat them as high-value
   leads requiring one confirmation pass, not as settled.
2. **No comparative scoring ever ran.** The charter's `§Comparative criteria` (eight criteria
   with uncertainty), `Required output` items 4, 5, 7 and 10 (comparison matrix, per-survivor
   steelman/attack, conditional recommendation, reversal conditions) were not produced. What
   exists is a generated and clustered field with hard-gate evidence — the tournament's first
   half, done thoroughly, and its second half not started.
3. **Four of the six mandated disagreements resolved by dissolution, one is unadjudicated.**
   "Generative candidates vs Stress-test" was never settled: f-007 (Stress-test's Reflect gate
   delta) was refuted in round 1 and Stress-test was never re-contracted. **The falsification
   advocate's flagship candidate left the field without a contract** — a real hole in the
   balanced portfolio the charter mandated, and the reason the generativity-vs-error-correction
   comparison at :126 is currently unanswerable on evidence as well as by design (f-010).
4. **Simulate never received an eleven-field contract.** The charter names it at :64; the field
   covers it only obliquely via Sweep (f-003), which points out that `internal/experiment`
   already ships a mechanism-space variation subsystem neither charter mentions. Whether
   Simulate is a distinct candidate or is Sweep is untested.
5. **The taste dimension is nearly unexercised** — 4 of 73 findings scored, all positive, no
   `-taste` findings at all. The mnemonic/linguistic position the parsimony adversary was
   supposed to hold was argued mostly on economy (f-025) and procedure (f-041), not on
   language. A dedicated naming/mnemonic pass never ran.
6. **No probes failed** — 0 failed dispatches across 13 agent-dispatches in 4 rounds. Every
   directive returned findings.
7. **Regions never reached:** the human-factors/cognitive-load position (the charter's
   "cognitive cost" criterion at :113 was scored by nobody); multi-agent topology, which the
   charter explicitly declares orthogonal at :27 and which no lens tested for interaction with
   any candidate; and any position arguing that OODARC's *existing* letters should be
   re-sequenced or renamed rather than consolidated — f-022's indictment of Decide is the only
   incumbent-facing finding and nothing followed it.
8. **Twelve findings were refuted** (f-001, f-004, f-005, f-007, f-011, f-014, f-017, f-018,
   f-019, f-039, f-048, f-052) and by convention do not appear in `surfaced.jsonl`. Several are
   named in this report where the adjudication is load-bearing — notably f-052, whose refutation
   is what f-067 repairs, and f-004, whose refutation is what makes Fallow (f-063) buildable.
