# fd-transfer-propagation-contracts — round 0

Seed position 4 (learning-transfer advocate). Transfer, teaching, and propagation contracts,
with the topology-versus-operation split and a trace-level duplication test against Compound and
Orient run on committed code rather than on the charter's description of them.

## Findings Index

- [P0] compound-carries-no-lesson-content — the duplication test against Compound *fails on the trace*: Compound's durable output is a rates-only aggregate plus an unconstrained doc write, so a transfer candidate duplicates nothing (§Mandatory disagreement / Synthesize vs Orient/Compound)
- [P0] contract-transplant-with-preconditions — Transplant: named in neither charter; takes a mechanism plus a target-context descriptor, performs structure mapping, and refuses when absorptive-capacity preconditions are absent (§Candidate-generation requirement)
- [P1] share-is-plumbing-verdict — Share fails phasehood: the cross-agent channel already exists as the intercore bridge and performs no re-contextualization; the topology question and the phasehood question answered separately (§Baseline, agent orchestration is orthogonal)
- [P1] select-is-the-reflect-compound-edge — Select's transformation is the existing Reflect→Compound promotion predicate; as an operation it does no re-contextualization work (§Mandatory disagreement)
- [P2] contract-worked-example-artifact — Template: a reusable procedure rather than a claim; writable today under Compound's manifest globs, but nothing in the runtime ever reads such an artifact back (§Per-candidate contract field 3)

## Findings

### compound-carries-no-lesson-content

- **Severity:** P0
- **Where:** §Mandatory disagreement and fusion work (target line 128, "Synthesize vs Orient/Compound: direct duplication test"); runtime anchors `internal/agent/agent.go:248`, `internal/mutations/signal.go:17-46`, `internal/mutations/aggregate.go:28-57`, `internal/tool/registry.go:44-46,67-70`
- **What:** The charter's baseline says Compound "promotes validated lessons into durable knowledge or reusable capability", and the duplication test is supposed to ask whether a transfer candidate repeats that. On the trace, Compound produces **no lesson content at all**:
  - Compound's one durable write is `mutations.Aggregate` (`agent.go:248`), which reduces a session's evidence lines to counts and rates and emits a `QualitySignal` whose fields are session id, timestamp, phase, task type, tests-passed, build-success, token efficiency, turn count, complexity tier, tool error/denial rates, approval rate, outcome (`signal.go:17-46`, `aggregate.go:28-57`). There is no field for a mechanism, a lesson, a context, or a claim.
  - Compound's tool gate allows `edit` and `write` only under `manifestGlobs` — `*.md`, `CHANGELOG*`, `VERSION*`, `*.json`, `*.yaml`, `*.yml`, `*.toml`, `*.txt` (`registry.go:44-46,67-70`) — so any actual lesson content is free-form prose in a markdown file with no schema, no index, and no reader.
- **Consequence for the tournament:** the duplication objection that would otherwise eliminate every transfer candidate ("Compound already does this") is false as stated. Transfer candidates should be tested against the *implemented* Compound — a rates aggregator plus an unindexed doc write — not against its description. Symmetrically, this indicts the incumbent: on the charter's own criteria, Compound's transformation is thin enough to warrant its own examination.
- **Failure scenario if unexamined:** the tournament eliminates Synthesize/Transplant as redundant with Compound, and Skaffen ships a loop where the only cross-session carrier of knowledge is a token-efficiency ratio.
- **Suggestion:** make the duplication test trace-based: require the eliminating party to name the field or file where the incumbent's equivalent output lives. "Compound does this" without a field name should not eliminate a candidate.

### contract-transplant-with-preconditions

- **Severity:** P0
- **Where:** §Candidate-generation requirement (target line 60, "at least three candidates not named in either charter"); runtime anchors `internal/mutations/inspire.go:21-60`, `internal/mutations/best.go:20-40`
- **What:** Contract for **Transplant** — absent from both charters, and not a synonym of Synthesize (which the charters use for "generate new frames") because its input includes a *target context descriptor* and its most common correct output is a refusal.
  1. *Input:* a validated mechanism plus a description of the destination context (its stack, constraints, and existing capabilities).
  2. *Transformation:* structure mapping — align the source mechanism's roles to the destination's entities, then identify the breakpoint: the structural assumption present in the source and absent in the destination.
  3. *Output/consumer:* a transplant record with mapping, breakpoint, and **preconditions**; the consumer is Decide in the destination context.
  4. *Authority:* speculative until the destination probe succeeds; retained on failure as base-rate evidence about this source-destination pair.
  5. *Trigger/pace:* slow layer, on entry to a new context, not per turn.
  6. *Re-entry:* through ordinary Observe/Decide in the destination.
  7. *Runtime delta:* needs a destination-context descriptor that does not exist today.
  8. *Overlap:* near-transfer overlap with `Inspire`, discussed below, but `Inspire` performs no mapping.
  9. *Failure/Goodhart:* transplant volume as a metric; false transfer is the dominant cost.
  10. *Losing condition:* on the corpus's tempting-false-analogy bucket, Transplant loses if its false-transfer cost exceeds the no-S null's.
  11. *Classification:* capability with an artifact output; phasehood only if the refusal is enforced at a gate.
- **Evidence that the absorptive-capacity precondition is the load-bearing field:** the runtime's existing near-transfer mechanism assumes a perfect receiver. `Inspire` matches prior sessions by `ClassifyTask`, a substring test over the task description (`inspire.go:43-60`), and surfaces Pareto-best sessions by token efficiency and turn count (`best.go:20-40`). Nothing checks that the current context resembles the source context in any way beyond the keyword. That is far transfer presented as near transfer.
- **Suggestion:** add "receiving-context preconditions and the behaviour when they are absent" as a required contract field for every transfer-class candidate; a contract whose answer is "the receiver will figure it out" is untestable and should fail the gate.

### share-is-plumbing-verdict

- **Severity:** P1
- **Where:** §Baseline (target line 27, "agent orchestration is an orthogonal topology") and §Candidate-generation requirement; runtime anchors `internal/evidence/emitter.go:38-74,76-95`, `internal/evidence/cascade.go:23-40`
- **What:** Both questions, answered separately as the charter requires.
  *Phasehood:* Share fails. Its transformation is identity — the same record, moved. There is no re-contextualization, so there is no epistemic operation, so there is no candidate.
  *Topology:* the channel already exists and is already cross-process. `JSONLEmitter` bridges each evidence event to intercore when `ic` is on PATH (`emitter.go:38-74,76-95`), and `CascadeEmitter` writes a single shared cross-session file explicitly because the telemetry is cross-cutting (`cascade.go:23-40`). Propagation across agents is an emitter target and a namespace, not a letter.
- **Failure scenario if conflated:** Share wins a slot on the strength of a real need (cross-agent propagation), and Skaffen adds a phase to the loop to solve a plumbing problem the emitter already solves — while the actual gap, that the bridged records carry no grade, stays open.
- **Suggestion:** record Share as a settled elimination with its cheaper mechanism named (an emitter target plus a namespace), and move the genuine requirement to the provenance work rather than the phase tournament.

### select-is-the-reflect-compound-edge

- **Severity:** P1
- **Where:** §Mandatory disagreement and fusion work (target lines 124-130); runtime anchors `internal/tool/registry.go:63-70`, `internal/agent/agent.go:248`
- **What:** Select ("choose what deserves promotion, transfer, or further investigation") describes the predicate on the Reflect→Compound edge, not a new operation. Its input is Reflect's output; its output is Compound's input; the re-contextualization work it performs is nil. In the runtime the edge is currently *unconditional* — Compound simply aggregates whatever the session emitted (`agent.go:248`), and the phase difference between Reflect and Compound is a gate swap: Reflect gets rate-limited `edit`, Compound gets manifest-globbed `edit`/`write` (`registry.go:63-70`). So Select's real content is "make the promotion edge conditional", which is a predicate on an existing edge.
- **Suggestion:** carry Select forward as a promotion-predicate proposal attached to the Reflect→Compound edge, explicitly not as a candidate operation, and let the parsimony position rule on whether an edge predicate is worth specifying. This lens's verdict is only that it does no transfer work.

### contract-worked-example-artifact

- **Severity:** P2
- **Where:** §Per-candidate contract field 3 (target line 81, output artifact and consumer); runtime anchors `internal/tool/registry.go:44-46,67-70`, `internal/session/session.go:80-101`
- **What:** Contract for **Template** — a teaching/worked-example candidate whose output is a reusable procedure for future loops rather than a claim. It is writable today: `*.md` is inside Compound's manifest globs (`registry.go:44-46,67-70`), so producing the artifact needs no new capability. Its problem is the *consumer* field, and it is fatal for phasehood: the only things injected into a future session's context are the phase prompt, the quality-history summary, and `Inspire` (`session.go:80-101`). No code path reads a worked-example document back. An artifact with no reader is a file, not an operation.
- **Suggestion:** classify Template as an artifact type and pair it with the one-line reader it needs (an `Inspire` source that surfaces matching templates by context descriptor). If that reader is not built, the candidate should be eliminated on the consumer field, not on parsimony grounds.

## Verdict

The duplication test against Compound fails on the trace, which reverses the charter's default
expectation: Compound's implemented output is a rates-only `QualitySignal` plus an unindexed
markdown write, so transfer candidates are not redundant with it and Compound itself is thin
enough to deserve the same knife. Transplant, with its absorptive-capacity precondition and its
licence to refuse, is the one transfer-class candidate that performs work no existing leg does;
`Inspire`'s substring-matched, precondition-free surfacing of past sessions is the concrete
proof that transfer without preconditions is already misfiring in this runtime. Share and Select
are plumbing and an edge predicate respectively — both real needs, neither an operation.
