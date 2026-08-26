# fd-reconnaissance-provenance-contracts — round 0

Seed position 3 (reconnaissance advocate). Scout steelmanned into its strongest operational
form, split into collection and interpretation, with provenance, dissemination boundary, read
filter, and the laundering trace made concrete against committed code.

## Findings Index

- [P0] contract-scout-split-collect-vs-assess — the strongest Scout is two operations: a collection half with a real gate delta and an interpretation half that is Orient with different vocabulary (§Baseline / §Candidate-generation requirement)
- [P0] laundering-trace-cass-into-orient-prompt — an ungraded, unexpiring speculative channel already exists: `cass` output is shelled out and injected verbatim into the Orient system prompt (§Tournament gates, epistemic separation)
- [P0] laundering-trace-evidence-to-quality-history — four unconditional hops carry any S-phase turn's footprint into a cross-session aggregate that Orient reads back; no hop carries a grade (§Tournament gates)
- [P1] provenance-schema-concrete — name the fields, the writer, the reader, and the check; reuse the typed-record pattern from `internal/experiment` rather than inventing a store (§Per-candidate contract field 4)
- [P2] classification-decides-fsm-work — collection sits upstream of Observe and is unrepresentable in the current forward-only FSM; interpretation sits beside Orient and needs no FSM change at all (§Per-candidate contract field 11)

## Findings

### contract-scout-split-collect-vs-assess

- **Severity:** P0
- **Where:** §Baseline (target line 29) and §Candidate-generation requirement (line 60); runtime anchors `internal/tool/builtin.go:19-22`, `internal/tool/registry.go:49-71,140-160`
- **What:** Scout as written bundles collection ("search related, lateral, and orthogonal domains") with interpretation ("mapping, breakpoints, falsifiable prediction"). Split, only one half earns phasehood.
  **Scout (collection) — eleven-field:** *Input:* a tasking — a validated mechanism, an unresolved contradiction, or a detected shear, with a named information requirement. *Transformation:* bounded outward search; it is **forbidden to conclude** — no mapping, no prediction, no recommendation. *Output:* graded raw items (source, query, retrieval time, source grade, excerpt). *Authority:* raw reporting, ungraded for reliability until assessed. *Trigger/pace:* on tasking; sparse. *Re-entry:* its product enters an interpretation step, never Decide. *Runtime delta — the discriminator:* a genuinely novel gate, `read`+`web_search`+`web_fetch` with **no** `edit`, `write`, or `bash`. That combination exists nowhere today: web tools are registered for Orient/Decide/Act (`builtin.go:19-22`), and Act also carries write/edit/bash (`registry.go:59-62`). So collection-Scout is the only candidate on the board with a gate signature no current phase has, and `GateConstraint` already supports the rate limit that bounds it (`registry.go:140-160`). *Overlap:* Observe reads local state only. *Failure:* collection drift into interpretation. *Losing condition:* no increase in validated mechanism discoveries per search turn. *Classification:* runtime phase or side-loop — it passes the enforcement test.
  **Assess (interpretation):** *Input:* graded raw items. *Transformation:* structure mapping, breakpoint identification, falsifiable prediction. *Runtime delta:* none — its tool set is Orient's read set exactly (`registry.go:53-55`). *Classification:* capability invoked by Orient, not a phase.
- **Failure scenario if not split:** the tournament scores one bundled Scout, its collection half's real gate delta is used to justify phasehood for the interpretation half, and Skaffen gains a phase whose licensed conclusions were never bounded.
- **Suggestion:** enter Scout-collect and Assess as two separate longlist entries with separate classifications, and add "what this operation is forbidden to conclude" to the per-candidate contract.

### laundering-trace-cass-into-orient-prompt

- **Severity:** P0
- **Where:** §Tournament gates, "epistemic separation of speculative and validated material" (target line 100); runtime anchors `internal/mutations/inspire.go:21-40,63-86,88-113`, `internal/session/session.go:80-92`, `internal/mutations/best.go:20-40`
- **What:** The charter treats the competing-truth-channel risk as prospective. It is already live. `Store.Inspire` (`inspire.go:21-40`) assembles three sources — a Pareto "best approaches" summary (`best.go:20-40`), mutation suggestions, and **`cassSearch`, which shells out to an external `cass` binary and returns whatever it prints** (`inspire.go:63-86`). `FormatInspiration` concatenates them under the heading "Orient Inspiration" (`inspire.go:88-113`), and `session.go:85-91` appends that block to the **Orient system prompt**. So third-party session text, retrieved by a truncated 100-character keyword query and matched by `ClassifyTask`'s substring heuristic (`inspire.go:43-60`), enters the model's highest-authority context position carrying no source field, no grade, no retrieval timestamp, and no expiry.
- **Failure scenario, end to end:** a prior session that failed for unrelated reasons is surfaced by keyword match; its narrative appears in the Orient system prompt as unattributed guidance; the model orients on it; the resulting turn is recorded as ordinary evidence. A speculative report from any future S phase routed through this same channel would be indistinguishable from validated history — the channel launders by construction, because the prompt has no slot for provenance.
- **Suggestion:** any S candidate that writes anything readable by Orient must first make this channel graded: add source, grade, and retrieved-at to `Inspiration`, render them in `FormatInspiration`, and label the block as unvalidated. Make that a hard gate in §Tournament gates rather than a per-candidate promise.

### laundering-trace-evidence-to-quality-history

- **Severity:** P0
- **Where:** §Tournament gates (target lines 99-100) and §Per-candidate contract field 4 (line 82); runtime anchors `internal/agent/deps.go:61-96`, `internal/evidence/emitter.go:38-74,76-95`, `internal/agent/agent.go:248`, `internal/mutations/aggregate.go:28-57`, `internal/tool/quality_history.go:44-60`
- **What:** The concrete laundering path, four hops, every one unconditional committed code:
  1. `agent.Evidence` has no `authority`, `grade`, `source`, or `record_id` field (`deps.go:61-96`).
  2. `JSONLEmitter.Emit` appends every event to one per-session file and bridges best-effort to intercore under `agent_name: skaffen` (`emitter.go:38-74,76-95`) — so the footprint also leaves this repo.
  3. Compound calls `mutations.Aggregate` (`agent.go:248`), which reads every line of that file and silently skips only what fails to unmarshal (`aggregate.go:28-57`); a speculative turn's tokens, tool calls, and outcome are folded into the same sums as validated turns.
  4. `quality_history`, gated to Orient (`builtin.go:28`), reads the aggregate back (`quality_history.go:44-60`).
  There is no point in this chain where a grade could be checked, because no grade is ever written.
- **Failure scenario:** an S phase runs, produces nothing validated, and its read-heavy turns nevertheless shift the aggregate that a later Orient consults — and shift Interspect's routing calibration downstream of the intercore bridge. The charter's central safety claim, "Scout output must re-enter ordinary observation before promotion" (line 29), is enforced by nothing.
- **Suggestion — name the field, the writer, the reader, the check:** add `authority string` to `agent.Evidence` (writer: the emitting turn, default `validated`, `speculative` for S turns); make `Aggregate` skip records where `authority != "validated"` (reader/check, `aggregate.go:36-47`); make `quality_history` refuse to render speculative rows. That is a three-hunk change and it is the precondition for *any* S candidate scoring above the null.

### provenance-schema-concrete

- **Severity:** P1
- **Where:** §Per-candidate contract field 4 (target line 82); runtime anchors `internal/experiment/store.go:15-19,33-52`
- **What:** Field 4 currently asks for "authority grade, storage boundary, read filter, expiry" in prose. Concretely, and separating source reliability from confidence in the claim (the two are routinely collapsed):
  `tasking_id` (which information requirement prompted this), `source` (domain/URL/binary), `collection_method` (`web_search`, `cass`, local read), `source_grade` (A-F reliability of the source), `confidence` (1-5 in the specific claim), `collected_at`, `expires_at` / `review_by`, `promoted_from` (backlink when a claim is later validated). Writer: the S turn. Readers: Decide and Compound. Check: the aggregation step rejects records missing `source_grade` or past `expires_at`.
- **Evidence:** the repo already has the right pattern to copy — typed JSONL records (`RecordTypeSegment|Experiment|Summary`, `experiment/store.go:15-19`) where each record carries its own provenance (`GitSHA`, `MutationID`, `OverrideReason`, `AgentDecision` versus effective `Decision`, `experiment/store.go:33-52`). Note that this schema *already* distinguishes what the agent chose from what was effectively decided and why it was overridden — the exact separation an anti-laundering design needs, implemented once and not reused by the evidence stream.
- **Suggestion:** require every candidate's field 4 to fill this table literally, and to state which existing store it extends. Prose answers should fail the gate.

### classification-decides-fsm-work

- **Severity:** P2
- **Where:** §Per-candidate contract field 11 (target line 89); runtime anchors `internal/agent/phase.go:10-16,39-51`, `internal/tui/commands.go:196-215`
- **What:** Say the classification out loud and price it. Scout-collect sits **upstream of Observe**: it feeds a graded channel that Observe subsequently reads. The current FSM cannot express that — `phaseOrder` is a fixed six-element slice, `Advance` increments by one and errors past Compound (`phase.go:10-16,39-51`), and the only caller is the human `/advance` command (`tui/commands.go:196-215`). An upstream-of-Observe or re-entrant phase requires re-entry semantics the FSM does not have. Assess sits **beside Orient** and needs no FSM change whatsoever — it is a prompt-and-tool change.
- **Suggestion:** add the FSM cost to the comparison matrix's implementation-cost column explicitly: side-loop and capability classifications cost zero FSM work; a genuine phase costs re-entry semantics plus a trigger, and today there is no automatic trigger of any kind to attach one to.

## Verdict

The strongest Scout is two operations, and only the collection half earns runtime phasehood —
it is the sole candidate whose gate signature (read plus web, no write, no bash) exists nowhere
in the current registry, while the interpretation half is Orient's tool set with new vocabulary.
The charter's epistemic-separation gate is currently unenforceable and, worse, already violated:
`cass` output is shelled out and injected verbatim into the Orient system prompt with no source,
grade, or expiry, and the evidence stream has no grade field at any of the four hops that end in
`quality_history`. Adding `authority` to `agent.Evidence` and filtering it in `Aggregate` is a
three-hunk precondition for any S candidate to beat the null on epistemic-safety grounds.
