# fd-epistemics-provenance-falsification — round 0

Target: `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md`
Grounding verified in-repo: `internal/evidence/emitter.go`, `internal/agent/agent.go`, `internal/mutations/aggregate.go`,
`internal/mutations/signal.go`, `internal/tool/quality_history.go`, `internal/tool/builtin.go`.
Verified negative: `grep -rni "authority|speculative|provenance"` over `internal/` returns zero hits, and no
expiry/retirement machinery exists outside HTTP caches and file reservations.

Scope note: the *grade ladder and laundering path* are being handled by the authority reviewer in the distant
tier. This lens confines itself to whether the decision can be tested — severity of test, retirement, pilot
discrimination, and null discipline.

## Findings Index

- [P1] pilot-is-a-demonstration-not-a-discrimination-test — the required pilot names no measured quantity, threshold, window, recorder, or outcome that would favor no-S (§Required output)
- [P1] read-only-pilot-perturbs-its-own-instrument — running any candidate inside Skaffen writes the evidence file that Compound aggregates into the exact signal a pilot would measure (§Required output)
- [P1] promotion-gate-rewards-risk-free-predictions — "only successful probes may be Compounded" selects for unfalsifiable analogies and erases the failures that carry the information (§Current leading candidate: Scout)
- [P2] expiration-has-no-clock-observer-or-sweep — the retirement field is emitted by the operation being retired, and nothing consumes it (§Current leading candidate: Scout)
- [P2] no-diagnosticity-pass-so-the-null-cannot-win — six of eight criteria are phrased for an operation, and no output item asks which evidence discriminates between hypotheses (§Tournament criteria, §Required output)

## Findings

### pilot-is-a-demonstration-not-a-discrimination-test

- **Severity:** P1
- **Where:** charter:119 ("A minimal read-only pilot for the top two choices plus the no-S null")
- **What:** The single sentence that carries the entire empirical burden of the review specifies nothing that could settle it. It names no measured quantity, no comparison, no threshold, no number of cycles, no observer, and — most consequential — no outcome that would favor the null. Every other required output (charter:113-118) is argumentative; charter:119 is the only place where the world gets a vote, and as written the pilot can only produce a demonstration that Scout *ran*, which is consistent with Scout being valuable, worthless, or actively harmful.
- **Evidence:** charter:119 in full; contrast charter:94 which scores candidates on "Falsifiability: produces probes whose failure can retire the hypothesis" — the criterion is applied to candidates but never to the decision.
- **Failure scenario:** The review ships with a recommendation at "moderate confidence" and a pilot reading "run Scout for a few cycles and see whether the reports are useful." Three weeks later someone reports the reports were interesting; nobody can say whether the null would have produced the same interest via an Orient-invoked search, because no null arm was measured and no threshold was pre-registered. The confidence figure in charter:117 was never earned, and the letter S is now in the acronym and in every doc, which makes reversal a naming migration rather than a config change.
- **Suggestion:** Replace charter:119 with a discrimination spec: *"For the top two candidates and the no-S null, state: the measured quantity, the pre-registered threshold, the number of cycles, who records the result, and — in advance — the specific observation that would favor no-S."* One concrete instrument already exists: `quality_history` (`internal/tool/quality_history.go:17-31`, Orient-gated at `internal/tool/builtin.go:26-29`) reads recent `QualitySignal` records per task type, so "did Orient turns that consulted a scout report show a different outcome rate than matched Orient turns that used only `web_search`?" is answerable with the runtime as it stands.

### read-only-pilot-perturbs-its-own-instrument

- **Severity:** P1
- **Where:** charter:119 ("minimal **read-only** pilot"); `internal/evidence/emitter.go:37-48`, `internal/agent/agent.go:246-253`, `internal/mutations/aggregate.go:28-68`
- **What:** "Read-only" is not achievable in this runtime for any candidate implemented as a phase or a tool. Every turn emits an `agent.Evidence` record to the per-session JSONL and best-effort bridges the same record to intercore for Interspect (`emitter.go:37-48`, `BridgeArgs` at `emitter.go:85-105`). If the session reaches Compound, `mutations.Aggregate` reads **every** line of that file and folds it into the session's `QualitySignal`, which is then written to the durable store (`agent.go:246-253`, `aggregate.go:28-68`). Token efficiency, turn count and tool-error rate are computed over all records indiscriminately. So the pilot's treatment writes into the store that any sensible pilot would use as its outcome measure — a confounded design, not merely an untidy one.
- **Evidence:** `emitter.go:37-48`; `emitter.go:85-105` (bridge to `ic events record` under `agent_name: skaffen`, feeding routing calibration); `agent.go:246-253`; `aggregate.go:13-24` (the lightweight `evidenceRecord` decoder ignores unknown fields, so any tag a scout turn carried is dropped before aggregation) and `aggregate.go:62-68`.
- **Failure scenario:** The pilot runs Scout for twenty sessions. Scout turns are cheap and produce no tool errors, so token-efficiency and tool-error-rate improve in the treatment arm; the pilot concludes Scout improved session quality when it only diluted the denominator. In the opposite direction, exploratory `web_fetch` failures inflate `Soft.ToolErrorRate`, and Interspect — which consumes the bridged events — down-weights the agent for exploration it was instructed to perform.
- **Suggestion:** Add to charter:119: *"The pilot must state its write surface. If a candidate is exercised inside Skaffen, run it with an isolated `--evidence-dir` (or a session that never reaches Compound) so that `mutations.Aggregate` cannot fold pilot turns into the durable `QualitySignal` that the pilot measures; otherwise run the pilot out-of-band as a paper exercise over recorded transcripts."*

### promotion-gate-rewards-risk-free-predictions

- **Severity:** P1
- **Where:** charter:41 ("only successful probes may be Compounded"); charter:37-38 (emitted "falsifiable prediction", "reversible probe"); charter:94 (Falsifiability criterion)
- **What:** The gate is stated as a safety property but it is also a selection rule, and the selection is on the wrong variable. A prediction's value is its severity — the prior probability that it fails. A gate that admits only successful probes makes the optimal strategy obvious to any agent (or human) whose output is counted: emit predictions that were nearly certain anyway, whose "correspondence mapping" restates a mechanism the team already believed. Those probes pass, get Compounded, and the durable store fills with confirmations that were never at risk. Symmetrically, failed probes are the observations that carry information — this source domain is barren, this class of analogy does not transfer — and the gate discards them, so the system can never learn a base rate for transfer success or attribute failure to a source domain. Note the shape is already present in the repo: `ExperimentEvent.Decision` and `Delta` (`internal/agent/deps.go:88-96`) record accept/reject for autoresearch mutations, i.e. Skaffen already keeps negative results in one subsystem and would be discarding them in another.
- **Evidence:** charter:37-41; charter:94; `internal/agent/deps.go:88-96` (`ExperimentEvent` retains `Decision`/`Delta` for rejected experiments); `internal/mutations/best.go:8-20` (`BestApproach` reasons over accumulated signals, so base rates are the unit this system already thinks in).
- **Failure scenario:** After a quarter, the Compound store holds forty transfer lessons, all successful, none surprising. A reader computes a 100% probe success rate and concludes the S phase is highly productive; in fact the informative half of the record was never written, and no one can answer "which source domains have we tried and found barren?" — the single question that would tell you whether to keep the operation.
- **Suggestion:** Two clauses. In charter:41: *"Failed probes are Compounded as retired-hypothesis records carrying source domain, prediction, and observed disconfirmation; only *supported* mechanisms are Compounded as capability."* In charter:74-83 (per-candidate spec): *"State the prior on the falsifiable prediction — a prediction the team already expected to hold is not a probe."*

### expiration-has-no-clock-observer-or-sweep

- **Severity:** P2
- **Where:** charter:39 ("expiration or review condition") as an emitted field of the scout report
- **What:** Retirement is specified as a property the artifact carries about itself, with no actor, clock, or sweep that consumes it. Verified: nothing in `internal/` implements expiry or retirement of a claim (the only `ttl`/`expire` hits are the 15-minute web-search cache at `internal/tool/web_search.go:288` and interlock file reservations at `internal/subagent/reservation.go:34-79`). An expiration that nothing reads is a comment. The charter also compounds this by using one grade for everything: `authority: speculative` (charter:38) collapses "mechanism validated in an adjacent domain with a working correspondence map" and "surface analogy noticed once" into the same rung, so there is no defined transition to raise or lower an artifact and therefore nothing for a sweep to write even if one existed.
- **Evidence:** charter:38-39; verified grep over `internal/` for authority/speculative/provenance (zero hits) and for expire/retire (only cache and reservation TTLs); `internal/tool/web_search.go:288`; `internal/subagent/reservation.go:34-79`.
- **Failure scenario:** Over months, scout reports accumulate as epistemic debt: each is individually marked speculative, none is ever retired, and a later reader searching the workspace finds a two-year-old correspondence mapping with a confident prediction and no indication that its review condition passed unobserved. The charter's stated goal of avoiding "a competing truth channel" (charter:121) fails not through mislabeling but through arrears.
- **Suggestion:** Amend the per-candidate spec (charter:74-83) item 2 to require *"the act that lowers or retires the grade, the actor that performs it, the clock or condition that triggers it, and the record the retirement is written to"* — and require a two-axis grade (source strength × correspondence confidence) so that raising and lowering have somewhere to move.

### no-diagnosticity-pass-so-the-null-cannot-win

- **Severity:** P2
- **Where:** charter:89-96 (§Tournament criteria); charter:113-119 (§Required output)
- **What:** The null is procedurally present and structurally disadvantaged. Six of the eight criteria — semantic distinctness, operational crispness, generativity, falsifiability, mnemonic/taste, pace fit — are phrased as properties *of an operation*; "no S" has no operation, so it scores N/A or zero on most of the matrix and wins only "complexity cost." No rule is given for scoring it, so the ranking mechanically favors any candidate that exists. Separately, the required outputs ask for steelmen, attacks, pairwise outcomes, and a confidence figure, but never ask which observations would *discriminate* between the hypotheses. Most of the evidence likely to be cited — "cross-domain transfer sometimes produces good ideas," "Orient does not currently search laterally on purpose" — is consistent with Scout, with Speculate, with a capability, and with the null, and is therefore worth nothing to the decision while reading as support.
- **Evidence:** charter:89-96; charter:113-119; contrast charter:14, which explicitly holds no-S and S-as-capability as live nulls, and charter:100 which records that the prior run "over-steered wide and performed no actual fusions."
- **Failure scenario:** The matrix is produced, the null scores 1/8 criteria, the winner scores 6/8, and the recommendation reports high confidence — a result that was determined by criterion phrasing before any evidence was considered. The team adopts a seventh letter on a scoring artifact.
- **Suggestion:** Two small amendments. (a) Add to charter:96: *"The no-S null is scored as a concrete candidate — 'lateral search as an Orient-invoked capability, with `web_search` at the `deep` tier and a scout-report artifact type' — with the same input/output contract fields as any other entry."* (b) Add output item 4b: *"A diagnosticity table: for each piece of evidence cited, mark which hypotheses it is consistent with; evidence consistent with all hypotheses may not be used to support the recommendation."*

## Verdict

The charter is strong on labelling discipline and weak on testability: it asks eight questions of every
candidate and one under-specified sentence of the world. As written the tournament cannot lose — the null is
scored on criteria that presuppose an operation, the pilot names no null-favoring outcome, and the promotion
gate at charter:41 quietly selects for predictions that were never at risk. Fixing charter:119 into a
pre-registered discrimination test with an isolated write surface, and admitting failed probes to Compound as
retired-hypothesis records, would make the recommendation's confidence figure something the review actually
earned.
