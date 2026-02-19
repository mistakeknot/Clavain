# Fix-Conflict Analysis: Vision Document Content Move Recommendations

**Source:** `hub/clavain/docs/research/synthesis-vision-review.md`
**Scope:** All 46 findings across 6 agent reports
**Date:** 2026-02-19
**Analyst:** fd-architecture (Flux-Drive)

---

## Method

The synthesis lists 46 findings (4 P0, 11 P1, 17 P2, 14 P3). Not all findings are content moves — many are wording fixes, implementation bugs, or missing design sections. This analysis identifies every finding that recommends moving, removing, or migrating content between the three vision documents, then checks whether those moves conflict with one another.

The three documents:
- `infra/intercore/docs/product/intercore-vision.md` (kernel — mechanism, primitives, durability)
- `hub/clavain/docs/vision.md` (OS — policy, workflow, agency)
- `infra/intercore/docs/product/autarch-vision.md` (apps — TUI surfaces)

---

## 1. Content Move Inventory

Seventeen distinct content moves are recommended across all findings. They are organized by source document.

### FROM intercore-vision.md

**Move IC-1**
- Source: `intercore-vision.md` lines 554–563 — Confidence-Tiered Autonomy table, "Autonomous Action" and "Human Action Required" columns
- Destination: `clavain/docs/vision.md` (Discovery → Backlog Pipeline, confidence-tiered autonomy policy table)
- Recommended by: synthesis P0-3, fd-layer-boundary P0-1
- Content summary: Two-column prescriptions for what OS must do at each confidence tier ("Create bead (P3 default)", "write briefing doc", "Appears in inbox") — OS workflow policy masquerading as kernel invariant

**Move IC-2**
- Source: `intercore-vision.md` lines 629–664 — "Concrete Scenario: A Feature Sprint" (Clavain phase vocabulary throughout)
- Destination: `clavain/docs/vision.md` or a migration guide; kernel doc retains only an abstract scenario using opaque phase labels
- Recommended by: fd-layer-boundary P1-1
- Content summary: The feature sprint example hardcodes Clavain's 8-phase chain ("brainstorm", "plan-review", etc.) and uses Clavain terminology in kernel narrative commentary, training readers that the kernel knows what "brainstorm" means

**Move IC-3**
- Source: `intercore-vision.md` lines 129 and 133 — event reactor daemon architecture and Autarch signal broker description in Process Model section
- Destination: Line 129 reactor architecture moves to `clavain/docs/vision.md` (event reactor lifecycle section); line 133 broker description moves to `autarch-vision.md` (signal architecture section)
- Recommended by: synthesis P1-1, fd-layer-boundary P1-2
- Content summary: Process Model correctly labels the reactor "an OS component" but then describes its internal command form (`ic events tail -f --consumer=clavain-reactor --poll-interval`) and the Autarch broker's internal architecture (in-process pub/sub, WebSocket streaming, backpressure evict-oldest-on-full)

**Move IC-4**
- Source: `intercore-vision.md` line 199 — Autarch ConfidenceScore weights (completeness 20%, consistency 25%, specificity 20%, research 20%, assumptions 15%) in the Autonomy Ladder Level 3 section
- Destination: Cross-reference pointer only; the weights remain in `autarch-vision.md` where the ConfidenceScore model lives
- Recommended by: fd-layer-boundary P2-1
- Content summary: The specific percentage weights of Autarch's confidence scoring formula are cited in the kernel doc as design rationale; these are OS/App policy, not kernel mechanism

**Move IC-5**
- Source: `intercore-vision.md` lines 569–571 — "Staleness decay mechanism" paragraph using "Beads" terminology
- Destination: Terminology fix only (replace "Beads created from discoveries" with "Discovery records that map to backlog items"); content stays in intercore-vision.md as kernel mechanism, but OS-specific vocabulary is removed
- Recommended by: fd-layer-boundary P2-2
- Content summary: A kernel primitive is described using a Clavain vocabulary term ("bead") that the kernel does not and should not know; this is a lighter edit than a full move but is catalogued here because the OS-specific framing must come out

**Move IC-6**
- Source: `intercore-vision.md` lines 509–519 — "Sprint Migration: Hybrid to Kernel-Driven" section title and framing prose using "sprint" as a kernel concept
- Destination: Rename within intercore-vision.md to "OS Workflow Migration: Hybrid to Kernel-Driven"; migration table content stays, but "sprint" vocabulary is replaced with "OS workflow" or "phase-chain workflow"
- Recommended by: fd-layer-boundary P3-3
- Content summary: "Sprint" is OS vocabulary in a kernel doc section; this is a rename and terminology fix, not a content relocation

**Move IC-7**
- Source: `intercore-vision.md` line 600 — "Autarch is merging into the Interverse monorepo" (present continuous tense)
- Destination: Stays in intercore-vision.md but tense corrected to future
- Recommended by: fd-cross-reference P1-3
- Content summary: Not a content move; a factual accuracy fix. Listed for completeness.

### FROM clavain/docs/vision.md

**Move CL-1**
- Source: `clavain/docs/vision.md` line 403 — "Not a Claude Code plugin. Clavain runs on its own TUI (Autarch)." (present-tense claim)
- Destination: Stays in clavain/docs/vision.md but reframed as aspirational identity
- Recommended by: synthesis P1-9, fd-cross-reference P1-1
- Content summary: The claim is factually incorrect today; the fix is a reframing to "not primarily a Claude Code plugin" with current-state/target-state callout; no content moves, but the correction changes how Clavain describes its own architecture

**Move CL-2**
- Source: `clavain/docs/vision.md` lines 255–268 — Model Routing "Layer 1", "Layer 2", "Layer 3" section headings
- Destination: Stays in clavain/docs/vision.md but headings renamed to "Tier 1/2/3" or "Stage 1/2/3" to avoid collision with stack layer labels
- Recommended by: fd-cross-reference P2-4
- Content summary: Terminology collision within one document; the three routing stages reuse the same numbering as the three architectural layers, creating ambiguity for readers

**Move CL-3**
- Source: `clavain/docs/vision.md` lines 257–260 — Layer 1 / Kernel Mechanism description that re-explains kernel internals
- Destination: Replace the authoring tone with a cross-reference to intercore-vision.md; content reduces to "the kernel records dispatch details; the OS configures routing policy on top"
- Recommended by: fd-layer-boundary P2-3
- Content summary: The Clavain doc authors kernel behavior with ownership tone rather than referencing it; the fix is a cross-reference addition, not content removal

### FROM autarch-vision.md (content additions to autarch-vision.md)

**Move AU-1**
- Source: `intercore-vision.md` line 133 — Autarch signal broker architecture (in-process pub/sub, WebSocket streaming, backpressure)
- Destination: `autarch-vision.md` — new "Signal Architecture" section
- Recommended by: fd-layer-boundary P1-2 (the "where it should live" prescription)
- Content summary: The kernel's Process Model section describes App-layer broker internals that belong in the Autarch vision doc; this move adds a section to autarch-vision.md and shrinks the kernel doc to a pointer

**Move AU-2**
- Source: `autarch-vision.md` lines 13–32 — Main architecture diagram (currently omits Interspect and Drivers)
- Destination: Stays in autarch-vision.md but expanded to include Drivers (Layer 3) and Interspect (cross-cutting profiler)
- Recommended by: fd-cross-reference P2-1
- Content summary: The autarch diagram is the most incomplete of the three; the fix adds two missing components to give autarch readers a complete model of the stack they sit atop

**Move AU-3**
- Source: `autarch-vision.md` lines 95–101 (Gurgeh arbiter) and lines 103–109 (Coldwine orchestration)
- Destination: Either (a) add explicit migration target statement that Gurgeh's arbiter moves to Clavain OS layer, or (b) add a justified exception explaining why PRD generation intelligence is legitimately an App concern
- Recommended by: synthesis P1-7, fd-layer-boundary P1-3, fd-architecture-coherence Finding 1
- Content summary: The Autarch doc states "Apps don't contain agency logic" then describes Gurgeh's arbiter and Coldwine's orchestration as app-layer logic; this is the highest-confidence content conflict (3 agents independently flagged it)

### NEW CONTENT required by fixes (not moves from existing sections)

**Move NEW-1**
- Source: None — content does not exist yet
- Destination: `clavain/docs/vision.md` — new dedicated section on event reactor lifecycle (who starts it, who restarts it, behavior on gate failure, manual recovery path via `ic run advance <id>`)
- Recommended by: synthesis P1-1, fd-autonomy-design L2-A, fd-architecture-coherence Finding 3
- Content summary: The event reactor lifecycle is currently described in the kernel doc (wrong home) or not described at all; a proper OS-layer section is required for Level 2 autonomy to be deployable

**Move NEW-2**
- Source: None — content does not exist yet
- Destination: `clavain/docs/vision.md` — current-state vs target-state callout in the architecture section
- Recommended by: synthesis P1-9 (fix prescription)
- Content summary: The gap between "Clavain is not a Claude Code plugin" (target) and "Clavain is currently deployed as a Claude Code plugin" (present) requires an explicit callout; this is new content, not relocated content

**Move NEW-3**
- Source: intercore-vision.md "Enforces vs Records" table — needs a current-vs-planned horizon column
- Destination: Stays in intercore-vision.md but gains a new column
- Recommended by: synthesis P0-3 (fix prescription)
- Content summary: The table currently shows what the kernel enforces without distinguishing what is enforced today from what is planned; adding a horizon column resolves the false enforcement claims in P0-2 and P0-3

---

## 2. Conflict Detection

Checking every recommended move against every other for dependency conflicts, destination conflicts, and cross-reference breakage.

### Conflict Check: IC-1 vs IC-2

IC-1 removes the OS action policy columns from the kernel's confidence tier table (lines 554–563). IC-2 moves the concrete scenario (lines 629–664) to the Clavain doc, or rewrites it with opaque labels.

**No conflict.** These are independent regions of intercore-vision.md. The tier table section (535–585) and the concrete scenario section (625–664) do not cross-reference each other. Both moves reduce the kernel doc. IC-1 content lands in clavain/docs/vision.md's existing Discovery → Backlog Pipeline section; IC-2 content either lands in clavain/docs/vision.md as an OS example or is replaced in-place with opaque labels. The destinations are compatible — the Clavain doc already has the confidence-tiered autonomy policy table (lines 175–191) that IC-1 columns are merging into.

### Conflict Check: IC-1 vs Move CL-1 (Clavain "Not a Claude Code plugin" fix)

IC-1 adds OS workflow prescription (bead creation, briefing docs, inbox) to the Clavain vision doc. CL-1 reframes the identity claim in the "What Clavain Is Not" section. These are in different sections of clavain/docs/vision.md and do not interact.

**No conflict.**

### Conflict Check: IC-3 (reactor/broker move) vs Move NEW-1 (new reactor lifecycle section in Clavain)

IC-3 removes the event reactor description from intercore-vision.md lines 129 and 133. NEW-1 requires a new, fuller reactor lifecycle section to be written into clavain/docs/vision.md. If IC-3 is applied before NEW-1 is written, the intercore doc loses its reactor description with no replacement yet in the Clavain doc. The intercore doc currently has the only reactor architecture description anywhere.

**Dependency conflict: IC-3 must not be applied until NEW-1 is written.** If IC-3 is applied first, readers who need the reactor architecture have nowhere to look. This is the most significant ordering dependency in the entire set of moves.

### Conflict Check: IC-3 (broker description) vs Move AU-1 (broker description destination)

IC-3 removes the broker description from intercore-vision.md line 133. AU-1 adds that content as a new "Signal Architecture" section in autarch-vision.md. These are two halves of the same operation on different documents.

**No conflict, but tight coupling.** IC-3 and AU-1 must be applied as a unit. Applying IC-3 without AU-1 leaves the broker architecture documented nowhere. Applying AU-1 without IC-3 creates duplication. They should be a single atomic commit.

### Conflict Check: IC-1 (remove OS action policy from kernel tier table) vs the existing clavain/docs/vision.md tier table

The Clavain vision already has a confidence tier table at lines 175–191 with OS Policy column. IC-1 recommends moving the "Autonomous Action" and "Human Action Required" columns from the kernel's tier table into the Clavain doc. But the Clavain doc already has an equivalent table. The question is whether IC-1 creates a duplicate table in the Clavain doc.

**Potential duplication conflict.** The Clavain doc's existing tier table (lines 175–191) already has "OS Policy" content covering bead creation and inbox surfacing. IC-1 should not append another table; it should verify that the kernel's columns are already represented in the Clavain table, then remove the columns from the kernel doc and add a pointer. No new content needs to land in the Clavain doc — the target already exists. This eliminates the duplication risk if the implementer checks the Clavain table first.

**Resolved with: verify-before-move discipline.** The Clavain tier table at lines 175–191 already contains the substance of the kernel's two action columns. IC-1 is a removal-plus-pointer operation, not a content-transplant operation.

### Conflict Check: Move AU-3 (Gurgeh arbiter / Coldwine orchestration) vs Move AU-2 (diagram expansion)

AU-3 requires a reconciliation statement in autarch-vision.md: either acknowledge the arbiter as a migration target to the OS layer, or justify why PRD intelligence is legitimately App-layer. AU-2 adds Drivers and Interspect to the autarch diagram.

**No conflict.** AU-2 touches the diagram block (lines 13–32). AU-3 touches the "Four Tools" section (lines 51–109). Independent regions.

### Conflict Check: Move IC-4 (remove ConfidenceScore weights from kernel) vs autarch-vision.md content

IC-4 removes the specific Autarch ConfidenceScore weights from intercore-vision.md line 199 and replaces them with a cross-reference to autarch-vision.md. The weights (completeness 20%, etc.) appear in the kernel doc but the actual ConfidenceScore implementation lives in Autarch's code. The autarch-vision.md describes Gurgeh's confidence scoring (line 55: "confidence scoring (0.0-1.0 across completeness, consistency, specificity, and research axes)") but does not publish the specific weights in the vision doc either.

**Partial destination gap.** The autarch-vision.md does not currently have a section that documents the specific weights. IC-4 proposes a cross-reference pointer to the Autarch vision doc, but the Autarch vision doc does not yet document the formula. The cross-reference would point to a section that does not fully exist. This is a P2 severity concern — the weights are cited as rationale guidance, not kernel specification, so removing them from the kernel doc without a full landing zone is acceptable; the code is the source of truth for the exact weights. The cross-reference can point to the Gurgeh tool description in autarch-vision.md as the location where the scoring model lives.

**Resolution:** IC-4 is safe to apply. The pointer does not need to resolve to a verbatim weight table in the autarch doc — it needs to point to the correct layer (Apps) as the owner of the formula.

### Conflict Check: Move IC-6 (rename "Sprint Migration" section) vs other moves

IC-6 is a terminology rename within the intercore-vision.md migration strategy section. No other move touches this section.

**No conflict.**

### Conflict Check: Move CL-2 (rename model routing Layer headings) vs Move CL-3 (add cross-reference to kernel doc)

CL-2 renames the headings of the three model routing sections in clavain/docs/vision.md. CL-3 adds a cross-reference sentence to the same sections. These are complementary edits to the same section.

**No conflict.** CL-3 cross-reference can be added during or after the CL-2 rename. If CL-2 is applied first, CL-3 still applies cleanly to the renamed headings.

### Conflict Check: Move NEW-1 (new reactor lifecycle section in Clavain) vs intercore-vision.md existing content

NEW-1 adds new content to clavain/docs/vision.md. The source for this content does not currently exist in any document — it must be written from scratch using the design requirements specified in synthesis P1-1 (reactor lifecycle: systemd unit vs hook vs session-scoped process, subscription contract, gate failure behavior, manual recovery via `ic run advance <id>`). After NEW-1 is written, IC-3 can safely remove the kernel doc's reactor description and replace it with a pointer to the Clavain doc.

**Ordering dependency confirmed (see IC-3 vs NEW-1 above):** Write NEW-1 first, then apply IC-3.

### Conflict Check: Move NEW-3 (add horizon column to Enforces vs Records table) vs IC-1 (remove action policy columns from confidence tier table)

NEW-3 modifies the "Enforces vs Records" table (lines 327–343 of intercore-vision.md). IC-1 modifies the "Confidence-Tiered Autonomy" table (lines 555–563 of intercore-vision.md). Different tables, different sections.

**No conflict.**

### Summary of conflicts found

| Pair | Conflict Type | Resolution |
|---|---|---|
| IC-3 → NEW-1 | Ordering dependency: IC-3 removes reactor architecture before NEW-1 writes it | Apply NEW-1 before IC-3 |
| IC-3 + AU-1 | Tight coupling: two halves of one operation | Apply atomically as one commit |
| IC-1 → clavain tier table | Potential duplication: Clavain already has equivalent content | Verify Clavain table covers substance before removal; this is removal-plus-pointer, not transplant |
| IC-4 → autarch-vision.md | Partial destination gap: weights cited in kernel; autarch doc does not publish formula | Acceptable: pointer to correct layer (Apps) is sufficient; code is source of truth |

No two moves recommend different destinations for the same content. No move A assumes content that move B removes (except the IC-3/NEW-1 pair, which is an ordering dependency, not a contradiction).

---

## 3. Aggregate Impact Assessment

### intercore-vision.md: what it loses

Content removed by the recommended moves:

| Move | Lines Affected | Character of Loss |
|---|---|---|
| IC-1 | 555–563 (2 table columns) | OS action policy removed from tier table |
| IC-2 | 629–664 (34 lines) | Concrete scenario with Clavain phase vocabulary — either moved or rewritten with opaque labels |
| IC-3 | lines 129, 133 (2 paragraphs) | Reactor command-form description; Autarch broker internals |
| IC-4 | line 199 (1 phrase) | Specific ConfidenceScore weights citation |
| IC-5 | lines 569–571 (terminology) | "Beads" vocabulary replaced, not removed |
| IC-6 | lines 509–519 (section title + framing) | "Sprint" vocabulary replaced, not removed |
| NEW-3 | lines 327–343 (table gains column) | Addition, not loss |

Net loss: approximately 38–42 lines of content. The document is currently 701 lines. After moves, approximately 660 lines remain. This is a 6% reduction in size — not a skeleton risk.

**Risk assessment: Low.** The kernel doc does not lose core mechanism content. Every removed item is either OS policy (action prescriptions), OS vocabulary used in kernel prose, or App-layer architecture described in the wrong place. The mechanisms themselves — discovery records, confidence scoring primitives, event types, tier boundaries — all remain. The kernel doc becomes more accurate about what it actually owns, not thinner in substance.

The highest-impact removal is IC-2 (the concrete scenario). If the entire scenario is removed rather than rewritten, the kernel doc loses its best pedagogical example of how phases, gates, and dispatches compose in practice. The recommended approach is to rewrite the scenario with opaque labels ("phase-0", "gate-checked-phase", "review-dispatch") rather than removing it entirely. This preserves the teaching value while removing the OS vocabulary leak.

### clavain/docs/vision.md: what it gains

Content added by the recommended moves:

| Move | Content Gained |
|---|---|
| IC-1 | Two action policy columns already present in Clavain's existing tier table — net gain is zero new content; kernel doc gains a pointer |
| IC-2 (if moved, not rewritten) | Concrete feature sprint scenario with Clavain phase names |
| IC-3 (reactor portion) | Reactor architecture absorbed into NEW-1 |
| NEW-1 | New section: event reactor lifecycle (systemd vs hook vs session-scoped, subscription contract, gate failure behavior, recovery path) |
| NEW-2 | Current-state vs target-state callout in architecture section |
| CL-1 | Reframe of "Not a Claude Code plugin" — content stays, wording changes |
| CL-2 | Model routing heading rename — no content added |
| CL-3 | Cross-reference sentence added to model routing section |

Net addition: NEW-1 is the only substantial new section (estimated 20–30 lines of new content). IC-2 adds the concrete scenario only if it is physically moved rather than rewritten in-place. Given IC-2's recommendation is rewrite-in-place or move, the Clavain doc could absorb up to ~34 lines from the concrete scenario.

**Risk assessment: Low.** The Clavain doc does not become bloated. The single new section (NEW-1, event reactor lifecycle) is necessary content that does not currently exist anywhere — it fills a real gap rather than duplicating what the kernel doc already says. The concrete scenario, if moved rather than rewritten, is appropriate in the Clavain doc since it uses Clavain's vocabulary. The Clavain doc is currently ~416 lines; adding 50–65 lines of legitimate OS-layer content is proportionate and does not threaten coherence.

### autarch-vision.md: what it gains

Content added by the recommended moves:

| Move | Content Gained |
|---|---|
| IC-3 (broker portion) / AU-1 | New "Signal Architecture" section describing Autarch's in-process pub/sub broker, WebSocket streaming, backpressure |
| AU-2 | Drivers layer and Interspect cross-cutting profiler added to main architecture diagram |
| AU-3 | Reconciliation statement: Gurgeh arbiter as migration target (or justified exception) |

Net addition: AU-1 adds approximately 10–15 lines of new section content. AU-2 adds approximately 12 lines to the existing diagram. AU-3 adds approximately 5–10 lines of acknowledgment or justification.

**Risk assessment: autarch-vision.md gains needed content.** The Autarch doc was extracted from the Intercore vision doc on 2026-02-19 (per its footer) and at 153 lines is the thinnest of the three documents. Adding the signal broker section, the complete stack diagram, and the arbiter reconciliation statement brings the document to approximately 185–190 lines — appropriate depth for an architectural vision document covering four tools and a shared component library.

The most important gain is AU-3: the reconciliation of "Apps don't contain agency logic" with the actual current-state architecture. Without this fix, the Autarch doc contradicts itself and gives teams a false expectation that building a Bigend replacement will be as simple as reading kernel state. The Gurgeh arbiter and Coldwine orchestration are the hard parts; the document owes contributors an honest account of where those boundaries currently sit.

### Is the resulting balance appropriate for kernel/OS/apps?

Yes, with one condition.

After all moves:
- intercore-vision.md (~660 lines): kernel mechanism and primitives, no OS vocabulary, no App-layer architecture
- clavain/docs/vision.md (~465 lines): OS policy, workflow definitions, reactor lifecycle, discovery pipeline — appropriately the densest OS-layer document
- autarch-vision.md (~190 lines): TUI surfaces, migration plan, signal broker, complete stack diagram — thin but accurate and honest about current-state coupling

The condition: Move IC-2 should be a rewrite-in-place (opaque labels) rather than a physical move. Physically moving the concrete scenario to the Clavain doc bloats the OS doc with implementation-level detail that is better suited as a kernel doc pedagogical example. If the scenario uses opaque phase labels ("phase-0" through "phase-7"), it teaches the kernel's mechanism without leaking OS vocabulary, and the kernel doc retains its best teaching aid.

---

## 4. Move Ordering

Moves that have no dependencies on each other can be applied in parallel. Moves with ordering dependencies must be sequenced.

### Strict ordering requirements

**Stage 1 (must complete before Stage 2):**
- NEW-1: Write the event reactor lifecycle section in clavain/docs/vision.md

**Stage 2 (depends on Stage 1 complete):**
- IC-3 + AU-1 (atomic): Remove reactor architecture from intercore-vision.md Process Model; add signal broker section to autarch-vision.md

**Rationale:** IC-3 removes content from the kernel doc. If applied before NEW-1 creates a landing zone in the Clavain doc, the reactor architecture exists nowhere. The 24-hour window between Stage 1 and Stage 2 creates a broken reference state but does not invalidate any other doc content.

### Moves with no ordering dependencies (can be applied in any order)

All of the following are independent of each other and of the Stage 1/Stage 2 chain:

- IC-1 (remove OS action policy columns from kernel tier table, verify Clavain table already covers substance, add pointer)
- IC-2 (rewrite concrete scenario with opaque phase labels — rewrite-in-place recommended)
- IC-4 (remove ConfidenceScore weights citation from kernel doc, add cross-reference to Autarch)
- IC-5 (terminology fix: "Beads" → "Discovery records" in kernel decay description)
- IC-6 (rename "Sprint Migration" section to "OS Workflow Migration")
- IC-7 (tense fix: "is merging" → "will merge" for Autarch in intercore-vision.md)
- CL-1 (reframe "Not a Claude Code plugin" as aspirational identity)
- CL-2 (rename model routing Layer 1/2/3 headings to Tier 1/2/3)
- CL-3 (add cross-reference to intercore-vision.md from Clavain model routing section)
- AU-2 (add Drivers and Interspect to autarch-vision.md architecture diagram)
- AU-3 (add arbiter reconciliation statement to autarch-vision.md Four Tools section)
- NEW-2 (add current-state vs target-state callout to Clavain architecture section)
- NEW-3 (add horizon column to intercore-vision.md Enforces vs Records table)

### Dependency chain visualization

```
NEW-1 (write reactor lifecycle in Clavain)
  |
  └─→ IC-3 + AU-1 (atomic: remove from kernel, add to autarch)

[All other moves: independent, any order]
```

### Recommended batching for minimal churn

**Batch A** (kernel doc cleanups — no Clavain or Autarch doc changes needed):
IC-1, IC-2 (rewrite), IC-4, IC-5, IC-6, IC-7, NEW-3

**Batch B** (Clavain doc fixes):
CL-1, CL-2, CL-3, NEW-2

**Batch C** (Autarch doc additions):
AU-2, AU-3

**Batch D** (requires Batch B NEW-1 to exist):
NEW-1 (write first), then IC-3 + AU-1 (atomic)

Batches A, B, and C have no internal ordering dependencies and can be worked in parallel. Batch D must follow the NEW-1 completion.

---

## 5. Recommendation

### Moves to apply: all 17, with one modification

All 17 recommended content moves address genuine boundary violations or factual inaccuracies. None are redundant, speculative, or in tension with each other (after resolving the IC-3/NEW-1 ordering dependency). The full set should be applied.

**The one modification:** IC-2 should be implemented as a rewrite-in-place (replace Clavain phase names with opaque labels and add an explicit callout), not as a physical content move. Physically transplanting the scenario to the Clavain doc creates a pedagogical gap in the kernel doc (it loses its only end-to-end example) and adds OS-specific detail to the Clavain doc that it does not need to own. The rewrite-in-place satisfies fd-layer-boundary P1-1's requirement (the kernel doc stops training readers that the kernel knows what "brainstorm" means) while preserving the teaching value of the scenario for kernel readers.

### Priority sequencing for must-fix vs optional cleanup

**Must-fix before any implementation work resumes on Level 2 autonomy (event reactor):**
- NEW-1 (write reactor lifecycle section in Clavain)
- IC-3 + AU-1 (remove reactor architecture from kernel doc, add to Autarch)
- This unblocks teams implementing the Level 2 event reactor from getting authoritative lifecycle guidance from the wrong document

**Must-fix before publishing intercore-vision.md as open-source documentation:**
- IC-1 (false enforcement claim: kernel cannot enforce "create bead")
- NEW-3 (add horizon column distinguishing current from planned enforcement)
- IC-5 (kernel doc cannot contain "Bead" vocabulary)
- IC-7 (tense fix for Autarch merge status)
- AU-3 (reconcile "Apps don't contain agency logic" with Gurgeh arbiter)

**Must-fix before onboarding contributors to Clavain:**
- CL-1 (reframe "Not a Claude Code plugin" — today's contributor will find a plugin, not an Autarch TUI)
- NEW-2 (add current-state vs target-state callout)

**Optional cleanup (low risk if deferred):**
- IC-2 (concrete scenario rewrite — wrong vocabulary but good teaching content; acceptable to defer one release)
- IC-4 (ConfidenceScore weights are guidance, not specification; removing them improves precision but does not fix a false claim)
- IC-6 (terminology rename in migration section; "sprint" in kernel doc is sloppy but does not mislead implementers)
- CL-2, CL-3 (model routing heading rename and cross-reference; reduces confusion but does not cause wrong behavior)
- AU-2 (add Drivers and Interspect to autarch diagram; fills a gap but autarch doc is accurate about what it does cover)
- IC-5 (terminology fix — "Beads" in kernel; imprecise but does not break anything)

### What to reject

No recommended move should be rejected. Every move in the synthesis either corrects a false claim, fixes a factual gap, or removes vocabulary that violates the stated kernel/OS/apps separation. The two moves closest to optional (IC-4 and IC-6) still improve the document's precision and should be done — they are low-effort and high-clarity-value.

The one move that requires the most care is AU-3. The three agents that flagged Gurgeh's arbiter and Coldwine's orchestration as boundary violations are correct that the current architecture contradicts "Apps don't contain agency logic." But the resolution is not to strip the arbiter out of Autarch today — it is to honestly acknowledge the current-state coupling and document the migration target. A premature extraction of the Gurgeh arbiter into Clavain would be a larger architectural change than any vision document fix warrants. AU-3's prescribed fix (acknowledge transitional state with timeline, or justify the exception) is the right scope.

---

## Appendix: Finding-to-Move Cross-Reference

| Synthesis Finding | Corresponding Move(s) |
|---|---|
| P0-2 (spawn limits not enforced) | NEW-3 (horizon column in Enforces/Records table) |
| P0-3 (discovery tier enforcement aspirational) | IC-1, NEW-3 |
| P1-1 (event reactor lifecycle undefined) | NEW-1, IC-3 |
| P1-7 (Autarch embeds OS agency logic) | AU-3 |
| P1-9 ("Not a Claude Code plugin" false) | CL-1, NEW-2 |
| P2-7 (discovery scoring ownership split) | IC-1, NEW-1 (partially) |
| P2-16 (cross-layer diagram inconsistency) | AU-2, IC-2 (rewrite) |
| P2-17 (ic tui inverted dependency) | Not a content move — design decision reversal |
| P3-1 (naming drift Drivers/Companion Plugins) | au-2 diagram standardization |
| P3-2 (referential asymmetry) | CL-3 (add cross-reference from Clavain to Intercore) |
| P3-3 ("Sprint" in kernel migration section) | IC-6 |
| fd-layer-boundary P0-1 | IC-1 |
| fd-layer-boundary P1-1 | IC-2 |
| fd-layer-boundary P1-2 | IC-3, AU-1 |
| fd-layer-boundary P1-3 | AU-3 |
| fd-layer-boundary P2-1 | IC-4 |
| fd-layer-boundary P2-2 | IC-5 |
| fd-layer-boundary P2-3 | CL-3 |
| fd-cross-reference P0-1 | (hyperlink fix — not a content move) |
| fd-cross-reference P1-1 | CL-1 |
| fd-cross-reference P1-3 | IC-7 |
| fd-cross-reference P2-1 | AU-2 |
| fd-cross-reference P2-4 | CL-2 |

Findings not mapped above (P0-1 transaction fix, P0-4 reward hacking, P1-2 gate failure escalation, P1-3 stalled dispatch, P1-4 bead auto-create ordering, P1-5 completion vs completion-well, P1-6 cursor TTL, P1-8 budget recorder nil, P1-10 threshold drift, P1-11 gate override audit, all P2 implementation findings) are implementation corrections, not content moves. They require code changes or new design sections written from scratch, not relocation of existing documentation content.
