# fd-ontology-naming-distinctness — round 0

Target: `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md`
Grounding verified: `internal/agent/phase.go` (what a *phase* is in this system), `internal/tool/registry.go`
and `internal/tool/builtin.go` (what a *capability* is), `internal/agentloop/types.go`,
`/Users/arouth/projects/interscout/CLAUDE.md` (existing "scout" term in this ecosystem).

Sorting test run before scoring, using the charter's own one-liners:
Orient (charter:21) "interpret evidence in the current context and choose a useful frame";
Reflect (charter:24) "compare outcomes with expectations and identify supported lessons";
Compound (charter:25) "promote validated lessons into durable knowledge or reusable capability";
Scout (charter:31) "search related, lateral, and orthogonal domains for transferable mechanisms."
Vignette A — mid-Orient, the agent reads `quality_history`, notices refactor sessions keep failing, and reads
three outside sources for a different framing. Practitioners split between Orient and Scout, and the charter's
prose is what decides. That is the failure condition of the decision lens.

## Findings Index

- [P1] four-seeds-one-contract — Scout / Search / Speculate / Synthesize share input, output and consumer, so the shortlist can rank one operation three times (§Previously considered alternatives, §Required disagreement probes)
- [P1] phase-claim-contradicted-by-its-own-spec — "conditional, not mandatory each cycle" plus an artifact consumed by another phase is the definition of a capability in this codebase, not a phase (§Current leading candidate: Scout)
- [P2] sensemake-and-select-are-restatements-of-orient-and-compound — two seeds are existing phases with different quantifiers, inflating the apparent diversity of the longlist (§Previously considered alternatives)
- [P2] letter-first-search-with-no-substitution-disclosure — six required source domains, and nothing requires the mechanism-first name or a declared cost when the S-word replaces it (§Required adversarial review, §Required output)
- [P3] scout-search-select-collide-with-live-terms-in-this-ecosystem — the three leading names are already taken by a plugin, a built-in tool, and the router's model selection [t]

## Findings

### four-seeds-one-contract

- **Severity:** P1
- **Where:** charter:53-58 (Synthesize, Speculate, Stress-test, Sensemake, Search), charter:29-41 (Scout), charter:102-103 (probes "Scout vs Speculate", "Scout/Speculate vs Stress-test")
- **What:** Write the contract triple — input, output, consumer — for Scout, Search, Speculate and Synthesize and they land on the same row. Input: a validated mechanism or an anomaly. Output: a lower-authority transfer hypothesis with a correspondence mapping. Consumer: a later Observe/Orient turn that decides whether to probe it. What differs is connotation, and each names a different *facet* of the same act: Search names the behavior, Scout names the behavior plus its report artifact, Speculate names the epistemic status of the output, Synthesize names the output's shape. A facet is not a rival. The charter's own probe list presupposes otherwise — "Scout vs Speculate" is framed as a substantive disagreement, but if the contracts are identical the probe can only return a naming preference dressed as a finding, which is precisely the failure the charter is trying to avoid after the prior run (charter:100).
- **Evidence:** charter:31-40 (Scout's seven emitted fields) against charter:53-57; charter:102-103.
- **Failure scenario:** The shortlist comes back as Scout, Speculate, Synthesize plus the null. Three of four slots hold one operation, so the tournament's diversity requirement is met nominally while the actual candidate space — a retirement operation, a pre-action counterfactual, a cross-agent propagation — is never scored. The winner is then chosen on connotation, and the review reports it as the survivor of a competitive field.
- **Suggestion:** One added step before charter:87 (§Tournament criteria): *"Contract-identity merge pass: write the (input, output, consumer) triple for every longlist entry; any two entries with the same triple merge into a single candidate, and the naming question is deferred to the mnemonic criterion. Report the merges."* Then the "Scout vs Speculate" probe is re-scoped to what it can actually settle — which name to give one merged candidate.

### phase-claim-contradicted-by-its-own-spec

- **Severity:** P1
- **Where:** charter:12 ("the optional **S** in OODARC(+S)"), charter:47 ("Scout is conditional, not mandatory each cycle"), charter:41 (output re-enters Observe), charter:83 (spec item 8)
- **What:** In this codebase the two categories have concrete definitions and the candidate matches the wrong one. A *phase* is a member of `phaseOrder` that the FSM walks through and a key in `defaultGates` that scopes tool authority (`internal/agent/phase.go:9-16`, `internal/tool/registry.go:49-72`, `registry.go:165-177`) — its defining property is that it is *positional and unconditional*. A *capability* is a tool bound to one or more phases by `RegisterForPhases` and invoked at the agent's discretion (`registry.go:136-153`, `builtin.go:19-29`) — its defining property is that it fires conditionally and emits an artifact for another phase to consume. Scout is described as conditional, has no mandatory position, and emits an artifact consumed elsewhere: three for three on capability, zero for three on phase. Charter:83 does ask each candidate for its category, but the framing question at charter:12 has already fixed the answer as a letter in an acronym, and no criterion in charter:89-96 checks the category claim against the contract.
- **Evidence:** charter:12, charter:41, charter:47, charter:83; `phase.go:9-16`; `registry.go:49-72`, `registry.go:136-153`, `registry.go:165-177`; `builtin.go:19-29`. Organizational-learning research points the same way as the code: absorptive capacity and transfer-of-practice are consistently modelled as capabilities exercised *within* existing stages by the receiving unit, not as a stage of their own — the default is capability, and it takes local evidence to overturn.
- **Failure scenario:** The phase claim materially changes what gets built. As a capability the change is one `RegisterForPhases` call, a prompt, and an artifact type — reversible in an afternoon. As a phase it means a new `phaseOrder` member, new `defaultGates` entry, Intercore role-map changes, TUI phase rendering, the acronym in every doc, and a migration to undo. Adopting the phase framing costs an order of magnitude more and is much harder to retire when the pilot disappoints.
- **Suggestion:** Move the category verdict *before* the tournament: *"Each candidate states its category with the property that decides it — mandatory position (phase), conditional firing with an emitted artifact (capability), sparse escalation off a named trigger (side-loop), or a record shape alone (artifact type). Treat 'conditional, not mandatory each cycle' as decisive evidence against phase. Only phase-category candidates are scored on phase criteria."* What evidence would overturn the capability default? A demonstration that the operation needs authority the invoking phase must not have.

### sensemake-and-select-are-restatements-of-orient-and-compound

- **Severity:** P2
- **Where:** charter:56 (Sensemake) against charter:21 (Orient); charter:60 (Select) against charter:25 (Compound)
- **What:** "Sensemake — build a broader frame from accumulated evidence" and Orient's "interpret evidence in the current context and choose a useful frame" are the same sentence with a widened quantifier; "Select — choose what deserves promotion, transfer, or further investigation" is the admission test that Compound's "promote *validated* lessons" already contains. Neither can be sorted from its neighbour by a practitioner given only the one-liners — the boundary requires the charter's prose to adjudicate, which is the definition of an uncarved concept. Their presence is not harmless: they pad a longlist whose diversity is the review's stated deliverable (charter:113).
- **Evidence:** charter:21, charter:25, charter:56, charter:60, charter:113.
- **Failure scenario:** The longlist is reported as nine-plus candidates and reads as a thorough search; in fact two entries are existing phases renamed, four are one operation (see `four-seeds-one-contract`), and the genuinely distinct entries number two or three. The reviewer's confidence in coverage is calibrated to the count.
- **Suggestion:** In charter:51-61, re-file these two in place rather than deleting them: *"Sensemake — a widened Orient, listed to be excluded; Select — Compound's admission test, listed to be excluded"* — and require the longlist count to report distinct contracts, not distinct words.

### letter-first-search-with-no-substitution-disclosure

- **Severity:** P2
- **Where:** charter:65-72 (six required source domains), charter:95 (Mnemonic/taste criterion), charter:111-119 (§Required output)
- **What:** The charter asks six domains for candidates but supplies only S-words as seeds, scores "concise, verb-shaped, pronounceable" as a ranking criterion, and never asks anywhere in the required output for the operation's best name irrespective of letter. That combination silently converts a mechanism search into a word search. Concretely, the mechanisms those domains actually yield do not start with S: control theory offers *dither / probe injection / model-reference adaptation*; ecology offers *forage / drift / disperse*; intelligence tradecraft offers *collection tasking / RFI / requirements management*; falsification offers *severe test / refute*; organizational learning offers *absorb / boundary-object exchange*. Every one of those will arrive at the tournament wearing an S-word costume (Search, Scan, Simulate, Sample), and the substitution — which is a real cost, since the S-name usually names a *different* facet than the mechanism — goes undeclared. Note that charter:14 explicitly authorizes dropping S; the machinery just never makes that easy.
- **Evidence:** charter:14, charter:65-72, charter:95, charter:111-119.
- **Failure scenario:** The control-theory slot returns "Sample" and the ecology slot returns "Scan," both of which read as thin variants of Search and score poorly on distinctness — so the two domains most likely to produce a structurally different operation are eliminated on a naming artifact, and the review reports that no domain beat Scout.
- **Suggestion:** Add one output item after charter:114: *"For each shortlisted candidate, give the mechanism-first name (chosen before any letter constraint) alongside the S-word substitution, and state what the substitution costs in precision. If no S-word fits the winning mechanism, say so — that is a result, not a failure."*

### scout-search-select-collide-with-live-terms-in-this-ecosystem

- **Severity:** P3 [t]
- **Where:** charter:31 (Scout), charter:58 (Search), charter:60 (Select)
- **What:** All three leading names are already occupied in the surrounding system, which is where the mnemonic criterion at charter:95 should be tested — status lines, log verbs, artifact filenames, and sentences said out loud mid-cycle. **Scout** is `interscout`, a live plugin in this workspace ("Pre-session UXR participant research plugin. Dispatches parallel research agents…", `/Users/arouth/projects/interscout/CLAUDE.md:1-3`), so "scout report" and "run a scout" are already spoken phrases meaning something else. **Search** is the built-in `web_search` tool (`internal/tool/builtin.go:21`), so "the Search phase used search" is a sentence a practitioner would have to say. **Select** is the router's job — `SelectionHints` drives per-turn model selection (`internal/agentloop/types.go:12-16`), so "selection" already denotes model routing in this codebase.
- **Evidence:** `/Users/arouth/projects/interscout/CLAUDE.md:1-3`; `internal/tool/builtin.go:21`; `internal/agentloop/types.go:12-16`; charter:95.
- **Failure scenario:** Slow rather than sharp: months of ambiguous log lines and docs where "scout" means two different things depending on which repo you are in, and a phase name that has to be disambiguated in conversation every time it is used. Cheap to avoid now, expensive to rename once the letter is in the acronym.
- **Suggestion:** One clause on charter:95: *"Mnemonic/taste — including a collision check against existing terms in this ecosystem (plugin names, built-in tool names, router vocabulary); a name already bound to another concept loses points regardless of its aesthetic merit."*

## Verdict

Constrained by the letter S, the seed set is not nine candidates but roughly three: one outward-transfer
operation wearing four names, two existing phases restated, and a handful of genuinely distinct ideas
(Simulate, Share, and the retirement operation nobody listed). The sharper problem is categorical: Scout's own
specification — conditional, unpositioned, artifact-emitting — matches this codebase's definition of a
capability on every property that distinguishes it from a phase, and the phase claim is being carried by the
acronym rather than by the contract. Force the contract-identity merge and the category verdict before
scoring, and the tournament will be ranking operations instead of words.
