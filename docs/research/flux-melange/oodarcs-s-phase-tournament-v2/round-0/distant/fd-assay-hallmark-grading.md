# fd-assay-hallmark-grading — round 0

Tournament role: grading-and-certification side. Generation precedes criticism — three
candidate contracts (one subtractive, one fusion-derived) are filed before any elimination.
Contracts are filled against the charter's eleven-field "Per-candidate contract"
(`docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:75-89`).

## Findings Index

- [P0] contract-assay-regrade-capability — Assay: an S whose only transformation is re-marking material it did not produce; supplies the touchstone/cupellation probe ladder for the whole field (§Per-candidate contract)
- [P0] verdict-evidence-to-orient-laundering-conduit — every generative candidate that emits ordinary evidence is re-read as validated input to the next Orient, so "separate store" claims fail hard gate 4 in practice (§Hard gates)
- [P0] verdict-null-already-grades-and-pilot-arms-share-its-store — the no-S null is self-grading by throughput, and the charter's "identical recording paths" makes arm A poison arm B (§Pilot contract; §Baseline)
- [P1] contract-melt-retirement-subtractive — Melt: the charter's mandated subtractive candidate, defacement-not-deletion, with a read filter that is what actually stops re-proposal (§Candidate-generation requirement)
- [P1] contract-reprove-retrial-decay-fusion — Reprove: fusion 2 (cybernetic control × organizational transfer) yields staleness-as-trigger, the only candidate in the field that removes authority (§Mandatory disagreement and fusion work)

## Findings

### contract-assay-regrade-capability

- **Severity**: P0 — without a grading office distinct from the maker, every generative
  candidate in the tournament is scored on a criterion ("resistance to authority
  laundering", charter:115) that no candidate can actually satisfy, and the ranking is void.
- **Where**: `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:75-89` (contract),
  `:95-101` (hard gates); runtime surface `internal/tool/registry.go:49-72`.
- **What**: Candidate **Assay**. Eleven fields:
  1. *Input/preconditions*: an artifact carrying `grade=speculative` and an unexpired date
     letter, produced by an office other than the one invoking Assay (session/subagent id
     must differ).
  2. *Transformation*: assign, confirm, or demote an authority grade. Assay may emit **no
     new claims** — it can only move a mark on existing material.
  3. *Output/consumer*: mutated `grade` **on the artifact**, plus an append-only assay
     record; consumer is the read filter that Orient/Compound apply, not a human reader.
  4. *Mark / store / read filter / expiry / failed-probe retention*: mark = a `grade` field
     carried by the record itself (not a property of a directory the reader must remember to
     respect); office = an `assay` tool gated to Reflect and forbidden in Act; tolerance =
     the dispositive test named in field 10; date letter = `graded_at` + `expires_at`;
     failures are defaced, never unlinked (see Melt).
  5. *Trigger / pace*: fires when an artifact crosses a read boundary with grade≠validated;
     Reflect/Compound cadence, never per-turn.
  6. *Re-entry*: pass → enters Orient's default read set; fail → stays speculative,
     reachable only by explicit query.
  7. *Runtime delta*: real and cheap —
     `RegisterForPhasesWithConstraint(assay, []Phase{PhaseReflect}, &GateConstraint{RequirePrompt:true})`
     plus an `AllowedGlobs` write restriction to the speculative namespace. Both mechanisms
     already exist (`internal/tool/registry.go:63-71`, which uses `RateLimit`+`RequirePrompt`
     for Reflect `edit` and `AllowedGlobs` for Compound `edit`/`write`).
  8. *Overlap*: Reflect reviews **this session's actions**; Assay grades **material's
     authority**, including material from earlier sessions. Overlap with Compound is the
     genuine risk, because Compound performs the only grading that exists today.
  9. *Failure mode / Goodhart*: rubber-stamping to unblock; assay-count becomes a
     productivity metric.
  10. *Pilot / losing condition*: on the pre-registered corpus, seed five false-analogy
      artifacts; Assay loses if it passes ≥2 of them, or if its overall pass rate ≥95%.
  11. *Classification*: **capability with runtime enforcement**, not a semantic phase — it
      is a re-trial of existing material, not a new transformation over the task.
- **Evidence**: the probe ladder this lens owes the field, made concrete against the repo.
  *Touchstone* (cheap, indicative): read-only consistency check of the speculative claim
  against repo facts — one `grep`/`read`, allowed in Observe/Orient where the gate matrix
  already permits exactly `read/glob/grep/ls` (`internal/tool/registry.go:50-58`).
  *Cupellation* (costly, dispositive): actually running the transferred mechanism in the
  target repo, which in Skaffen means the sandboxed experiment path with
  `GateConstraint{RequirePrompt:true}` (`internal/tool/builtin.go:37-46`). The discriminator
  for the whole tournament: **a candidate that attaches "falsifiable prediction" and
  "reversible probe" to the same emitted report has collapsed the ladder** unless it names
  who pays for the cupellation and in which phase. Scout as stated in charter:29 currently
  collapses them.
- **Suggestion**: adopt Assay as the grading office and require every other survivor's field
  4 to name Assay (or a rival office) explicitly; reject any contract whose field 4 answer is
  "a separate directory".

### verdict-evidence-to-orient-laundering-conduit

- **Severity**: P0 — this is a constructed laundering path, not a risk assertion: it names
  the store, the reader, and the turn on which speculation is re-read as evidence.
- **Where**: `internal/evidence/emitter.go:36-50`; `internal/mutations/aggregate.go:12-24`
  and `:28`; `internal/mutations/signal.go:15-25`; `internal/mutations/store.go:12,26`;
  `internal/tool/quality_history.go:46-78`; `internal/tool/builtin.go:26-29`;
  `internal/session/session.go:78-91`; `internal/mutations/inspire.go:21-40`.
- **What**: Any generative S that emits ordinary evidence events is promoted to validated
  input to the next Orient with no grade surviving the trip. `JSONLEmitter.Emit` appends to
  `~/.skaffen/evidence/<session>.jsonl` and bridges to `ic events record --source=interspect`;
  `Aggregate` deserializes **every** record via `evidenceRecord`, which has no grade,
  provenance, or expiry field; the resulting `QualitySignal` likewise has none; Compound
  writes it to the single global `~/.skaffen/mutations/quality-signals.jsonl`; the
  `quality_history` tool is gated to `PhaseOrient` and hands the rows straight back — and
  worse, `JSONLSession.SystemPrompt` appends both the quality history **and** the inspiration
  block directly into the Orient system prompt (`internal/session/session.go:78-91`), so the
  re-read is automatic: the model never chooses to look.
  `Inspire` widens the same channel by pasting `cass search --robot --limit 3` free text into
  Orient with no provenance at all.
- **Evidence**: the turn is nameable. Session *n*: S emits 4 speculative turns → those turns
  raise `TurnCount` and lower `TokenEfficiency` in `Aggregate`. Session *n+1*, Orient turn 0: those rows are already
  in the system prompt via `formatQualityHistory`, before the model has taken any action.
  The speculative material has been re-read as evidence, and the *only* thing the loop learns
  from it is that exploration made the numbers worse. This disqualifies at hard gate 4
  (charter:99) every candidate — Scout included — whose field 4 says "separate store" while
  its output still flows through `agent.Evidence`.
- **Suggestion**: smallest viable fix, two filters and one field. Add `grade` and `expires_at`
  to the evidence record (`internal/mutations/aggregate.go:14-24` plus the emitter's event
  shape), have `Aggregate` skip records whose grade ≠ `validated`, and have
  `QualityHistoryTool.Execute` and `formatQualityHistory` drop rows lacking a validated grade. Make passing that filter
  a hard-gate precondition for every generative candidate in the shortlist.

### verdict-null-already-grades-and-pilot-arms-share-its-store

- **Severity**: P0 — corrupts the arbiter. The charter makes the pilot decide the tournament
  (charter:138-157); if the arms contaminate each other the verdict is unreadable.
- **Where**: charter `:140` (do not use QualitySignal as outcome), `:157` ("identical task
  buckets and recording paths"); `internal/mutations/store.go:12,26,56`;
  `internal/mutations/aggregate.go:62-84`.
- **What**: Two joined claims. (a) The **no-S null's grading contract**, stated affirmatively
  as the charter demands (charter:43): mark = `TokenEfficiency` (`totalOut/totalIn`) and
  `TurnCount`, struck by `Aggregate`; office = the same process that produced the turns, so
  maker and office are identical; tolerance = none declared; date letter = none —
  `ReadRecent(n)` returns the last *n* rows regardless of age; melt rule = none, the JSONL is
  append-only and nothing in the tree deletes, expires, retires, or prunes (a repo-wide grep
  for expiry/retire/prune finds only web-cache TTLs and file reservations). The null is
  therefore not "ungraded"; it is **self-certification by throughput**. (b) Because that store
  is a single global path and the charter mandates identical recording paths, arm A's
  speculative rows land in the same `quality-signals.jsonl` that arm B's Orient reads.
- **Evidence**: run baseline, then candidate A, then candidate B against the corpus in that
  order on one machine: B's Orient calls `quality_history`, receives A's rows, and B's trace
  is no longer an independent arm. The measured effect is directional and adverse to S — the
  extra speculative turns depress exactly the two hard signals — so the pilot has a built-in
  bias toward the null that is invisible in the scoring rubric (charter:148-155).
- **Suggestion**: add one line to the pilot contract requiring each arm to run with a
  per-arm `~/.skaffen/<arm>/mutations/` store (the `Store` already takes `dir`, so this is a
  constructor argument, not new machinery), and freeze the store between arms. "Identical
  recording paths" should be read as *identically shaped*, not *shared*.

### contract-melt-retirement-subtractive

- **Severity**: P1 — the charter mandates a subtractive candidate (charter:70); without one,
  field 4's "retirement and negative-result retention" is unimplementable for every other
  contract, and the shortlist cannot pass its own hard gate.
- **Where**: charter `:41` (do not erase failed probes), `:70`, `:82`;
  `internal/tool/registry.go:67-71` (the Compound `AllowedGlobs` mechanism this reuses).
- **What**: Candidate **Melt**, the field's pruning operation. 1. *Input*: graded artifacts
  past `expires_at`, or with two consecutive failed assays. 2. *Transformation*: **defacement,
  not deletion** — grade → `retired`, plus `retired_reason` and the identity of the failing
  test. 3. *Output/consumer*: a retirement record consumed by an explicit `negative_results`
  query and by source-domain base-rate statistics (charter:41 says exactly this material is
  durable evidence). 4. *Mark/office/tolerance/date letter/melt rule*: mark `retired`; office
  = the assay office, never the maker; tolerance = expiry or two failures; date letter
  `retired_at`; melt rule explicitly forbids `os.Remove`. 5. *Trigger/pace*: a Compound-cadence
  sweep; the slowest layer in the design. 6. *Re-entry*: retired material is invisible to
  Orient's default read and visible to explicit query — **the read filter, not the move, is
  the retirement**. 7. *Runtime delta*: a `retire` tool gated to Compound with
  `AllowedGlobs` limited to the speculative and retired namespaces; the constraint type
  already exists. 8. *Overlap*: Compound persists winners; Melt persists losers **as losers**.
  That asymmetry is its distinctness claim. 9. *Failure/Goodhart*: burying inconvenient
  disconfirmations; "clean frontier" as a metric. 10. *Pilot*: seed three leads that must
  recur across corpus tasks; Melt loses if a retired lead is re-proposed and re-probed at
  full cost inside one corpus run. 11. *Classification*: capability/artifact operation.
- **Evidence**: nothing in the Go tree implements expiry, retirement, or pruning today, so
  every rival contract's field-4 promise ("its expiry, retirement, and negative-result
  retention behavior", charter:40) is currently a promise about machinery that does not
  exist. Melt is the cheapest way to make those promises checkable, which is why it should
  survive the tournament even though this lens expects it to **lose phasehood**.
- **Suggestion**: seed Melt into the longlist as the mandated subtractive entry and score it
  under "value relative to the no-S null" rather than "generativity", where it will and
  should score zero.

### contract-reprove-retrial-decay-fusion

- **Severity**: P1 — this is this lens's half of fusion 2 (charter:134); a fusion that
  yields no new discriminator does not count (charter:136), and this one does.
- **Where**: charter `:131-136`; `internal/mutations/signal.go:17-25` (no provenance field);
  `internal/mutations/store.go:56` (`ReadRecent` is age-blind).
- **What**: Candidate **Reprove** — re-trial of already-promoted claims. Fusion of cybernetic
  control (a feedback loop with a measured error term) × organizational transfer (a mechanism
  imported from a source domain stops holding when the source drifts). *Emergent discriminator
  neither parent supplies*: **knowledge decay rate as the control variable, and source
  staleness as the trigger** — the S fires when the recorded source artifact's commit no longer
  matches current state, not when a human feels uncertain. Contract: 1. input = promoted claims
  older than their date letter whose source is addressable as path+commit; 2. transformation =
  re-run the original dispositive test, emitting confirm/demote/retire; 3. output = updated
  grade plus a decay datum (how long this claim class survived), consumed by the trigger policy
  itself, closing the loop; 4. mark/office/tolerance as Assay, plus a per-class decay half-life;
  5. trigger = source-commit mismatch, slowest pace layer; 6. re-entry = demotions push material
  back **down** to speculative; 7. delta = a source-provenance field on the signal record, which
  is also the provenance half this lens owes fusion 1; 9. failure = churn, re-proving forever,
  bounded by the decay estimate; 10. pilot = two corpus runs separated by a seeded upstream
  change, losing if no promoted claim is demoted when its source is invalidated;
  11. classification = capability on a slow trigger.
- **Evidence**: Reprove is the only candidate this lens can construct that **removes**
  authority. Every other candidate in the field, incumbent legs included, is monotonic: today
  `ReadRecent(n)` returns the newest *n* signals with no staleness test, so a claim promoted
  once is never re-examined, only diluted by volume.
- **Suggestion**: carry Reprove into the shortlist as a fusion product, and require the
  eventual recommendation to state which operation demotes — if the answer is "none", the
  design has a one-way authority ratchet and the reviewer should say so explicitly.

## Verdict

Filed four contracts (Assay, Melt, Reprove, and the no-S null's grading contract) before any
elimination, and constructed rather than asserted the laundering path: evidence JSONL →
`Aggregate` → `quality-signals.jsonl` → `quality_history` in Orient, with no grade field
anywhere along it. This lens expects **Melt and Reprove to lose phasehood** and survive as
capabilities, and expects **Assay to lose to the parsimony adversary** as a separate letter
while surviving as the office that every other candidate's field 4 must name; the evidence
that would reverse that is a demonstration that grading cannot be enforced from inside
Reflect without its own gate matrix row. The strongest single result is that the no-S null is
not neutral — it already grades by throughput, with maker and office identical — so "no S" is
a *choice of grading regime*, not the absence of one.
