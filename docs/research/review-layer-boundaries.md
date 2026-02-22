# Layer Boundary Review: Intercore, Clavain, Autarch Vision Documents

**Reviewer:** fd-layer-boundary
**Date:** 2026-02-19
**Documents reviewed:**
- `/root/projects/Interverse/infra/intercore/docs/product/intercore-vision.md` (v1.6)
- `/root/projects/Interverse/os/clavain/docs/vision.md` (undated, revised 2026-02-19)
- `/root/projects/Interverse/infra/intercore/docs/product/autarch-vision.md` (v1.0)

---

## Layer Model Reference

| Layer | Name | Mandate |
|---|---|---|
| Kernel | Intercore | Mechanism, primitives, durability. No OS policy, no app presentation. |
| OS | Clavain | Policy, opinions, workflow definitions. Does not reimplement kernel mechanisms or describe app UIs. |
| Apps | Autarch | Interactive surfaces. Does not contain agency logic or kernel implementation details. |

---

## Summary of Findings

| Severity | Count | Boundary |
|---|---|---|
| P0 | 1 | Kernel doc prescribes OS workflow policy in a normative section |
| P1 | 3 | Kernel doc contains named phase prescriptions; Kernel doc owns daemon architecture that belongs to OS; Autarch doc contains OS agency logic |
| P2 | 5 | Blurred ownership of confidence scoring weights; IC doc owns OS adaptive-threshold prose; Clavain doc duplicates kernel mechanism table; Cross-layer diagram inconsistency; Kernel doc describes TUI consumer internals |
| P3 | 3 | Naming drift; Referential asymmetry; Cross-doc link hygiene |

---

## P0: Critical Boundary Violation

### P0-1 — Intercore doc prescribes OS autonomy policy as kernel-enforced invariant (Kernel→OS leak)

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Autonomous Research and Backlog Intelligence → Confidence-Tiered Autonomy"
**Lines:** 554–563

**What the text says:**

> "This is a **kernel-enforced gate**, not a prompt suggestion. The scoring model produces a number; the tier boundaries are configuration; the action constraints at each tier are invariants. An OS-layer component cannot auto-create a bead for a discovery scored at 0.4 — the kernel will reject the promotion."

Immediately before this, lines 555–562 contain the tier table:

| Tier | Score Range | Autonomous Action | Human Action Required |
|---|---|---|---|
| High | ≥ 0.8 | Create bead (P3 default), write briefing doc, emit `discovery.promoted` | Notification in session inbox; human can adjust priority or dismiss |
| Medium | 0.5 – 0.8 | Write briefing draft, emit `discovery.proposed` | Appears in inbox; human promotes, dismisses, or adjusts |

**Why this is P0:**

The kernel doc does not just define that tiered gates exist (mechanism) — it defines the exact actions the OS must take at each tier, including "Create bead (P3 default)", "write briefing doc", and "Appears in inbox". These are OS workflow outputs, not kernel primitives. The kernel cannot know what a "bead" is (beads are a Clavain concept, not a kernel concept). The kernel cannot know what "inbox" means (that is an OS/app presentation concern).

The phrase "An OS-layer component cannot auto-create a bead for a discovery scored at 0.4 — the kernel will reject the promotion" directly contradicts the stated principle on lines 112–116 of the same document: "Phase names and semantics — 'brainstorm', 'review', 'polish' are Clavain vocabulary. The kernel accepts arbitrary phase chains." The same rule applies: "beads", "briefing docs", and "session inbox" are Clavain vocabulary. The kernel should not know or enforce them.

The kernel can legitimately enforce: "a discovery at tier X may only reach state Y". What it cannot legitimately contain is the mapping from tier to "write briefing doc" or "create bead (P3 default)" — those are OS policy decisions.

**Where it should live:** The action column of this table belongs entirely in the Clavain vision doc under "Discovery → Backlog Pipeline → Confidence-tiered autonomy policy". The kernel table should only define the tier names and score ranges, with a note that the OS configures the permitted action set for each tier.

**Minimum fix:** Remove the "Autonomous Action" and "Human Action Required" columns from the kernel's tier table. Replace with: "The kernel enforces that only OS-configured actions for this tier may be executed. Action definitions are OS policy." Point to Clavain vision doc for the policy.

---

## P1: Significant Boundary Violations

### P1-1 — Intercore doc prescribes named OS phases in the concrete scenario (Kernel→OS leak)

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Concrete Scenario: A Feature Sprint"
**Lines:** 629–664

**What the text says:**

```
ic run create --project=. --goal="Add user auth" --complexity=3 \
  --phases='["brainstorm","strategize","plan","plan-review","execute","test","review","ship"]'
```

The concrete scenario is valuable as documentation, but it establishes "brainstorm", "strategize", "plan", "plan-review", "execute", "test", "review", "ship" as the default 8-phase chain within the kernel doc — reinforcing these as the canonical phases at the kernel level, not as one possible OS-configured phase chain. The narrative (lines 634–664) then uses "brainstorm" and "plan-review" as if they are kernel concepts: "Kernel evaluates gate for brainstorm→strategize transition."

The same document correctly states on line 112: "'brainstorm', 'review', 'polish' are Clavain vocabulary. The kernel accepts arbitrary phase chains."

**Why this is P1 and not just P3:** The concrete scenario with named phases trains readers (and future contributors) to think the kernel knows what "brainstorm" means. The narrative commentary around it uses phase names as if they are structural kernel properties. This is the kind of boundary blur that leads to future kernel code containing phase-name checks.

**Where it should live:** The concrete scenario belongs in the Clavain vision doc, or in a migration guide, with a framing note that these are example OS-supplied phase names. The kernel doc's scenario section should use opaque labels ("phase-0", "phase-3") or generic domain terms ("gate-checked phase", "multi-agent phase").

**Minimum fix:** Add an explicit callout at the start of the scenario: "The phase names in this example (brainstorm, plan-review, etc.) are supplied by Clavain at run-creation time. The kernel treats them as opaque strings. This scenario uses Clavain's phase vocabulary for readability only." Optionally, move the scenario to the Clavain doc and replace the kernel doc's scenario with one using opaque identifiers.

---

### P1-2 — Intercore doc owns the event reactor daemon architecture (Kernel→OS leak)

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Process Model"
**Lines:** 129, 133

**Line 129:**

> "An OS-level event reactor (e.g., Clavain reacting to `dispatch.completed` by advancing the phase) runs as a long-lived `ic events tail -f --consumer=clavain-reactor` process with `--poll-interval`. This is an OS component, not a kernel daemon..."

**Line 133:**

> "...When this becomes necessary, Autarch's signal broker provides a proven pattern: an in-process pub/sub fan-out with typed subscriptions, WebSocket streaming to TUI/web consumers, and backpressure handling (evict-oldest-on-full for non-durable consumers). The durable event log remains the source of truth; the broker is a real-time projection of it for latency-sensitive consumers."

**Why this is P1:**

Line 129 is correct in labeling the reactor "an OS component" — but then proceeds to describe its internal architecture (long-lived process, `--consumer=clavain-reactor`, `--poll-interval`) in the kernel doc. The kernel doc should state that event consumption is pull-based and that OS-layer consumers may implement reactors; it should not specify how the OS reactor works.

Line 133 goes further: it describes Autarch's signal broker architecture in detail (in-process pub/sub, WebSocket streaming, backpressure handling with evict-oldest-on-full) within a kernel doc section. This is two layers above the kernel. The kernel doc is teaching the reader about an App-layer component's internal architecture as design guidance for a future kernel daemon.

The information is not wrong, but it is in the wrong document. The kernel's "Process Model" section should end at: "event consumption is pull-based; consumers poll via `ic events tail --consumer`. If sub-second latency is required, an OS-level event reactor or App-layer broker may wrap this API." The broker architecture belongs in the Autarch vision doc, which already exists.

**Where it should live:** Line 133's broker description belongs in `autarch-vision.md` under a "Signal Architecture" section, or in the Clavain vision under the event reactor description. The kernel doc should only say: "For latency-sensitive consumers, a broker layer above the kernel is the correct architectural pattern. See the Autarch vision doc."

**Minimum fix:** In the kernel's Process Model section, remove the broker implementation details (the "in-process pub/sub fan-out with typed subscriptions, WebSocket streaming, backpressure handling (evict-oldest-on-full)") and replace with a pointer to Autarch's vision doc.

---

### P1-3 — Autarch doc contains OS agency logic in tool descriptions (Apps→OS leak)

**Document:** `infra/intercore/docs/product/autarch-vision.md`
**Section:** "The Four Tools → Coldwine"
**Lines:** 103–109

**What the text says:**

> "Coldwine's migration overlaps with Clavain's sprint skill — both orchestrate task execution with agent dispatch. The resolution is that Coldwine provides TUI-driven orchestration while Clavain provides CLI-driven orchestration, both calling the same kernel primitives."

And in the same section, lines 95–101 (Gurgeh migration):

> "Gurgeh's arbiter (the sprint orchestration engine) remains as tool-specific logic — it drives the LLM conversation that generates each spec section. The kernel tracks the lifecycle; Gurgeh provides the intelligence."

**Why this is P1:**

The Gurgeh description says the tool "drives the LLM conversation that generates each spec section" and retains an "arbiter (the sprint orchestration engine)". This is agency logic — deciding which LLM to prompt, how to drive a multi-step conversation, how to generate spec sections. That is OS-layer policy. An App should render and interact; it should not contain the intelligence for generating PRD sections.

The Coldwine description is cleaner but still describes Coldwine as doing "TUI-driven orchestration" — meaning orchestration logic (which is OS) lives in an App. The document attempts to resolve this by saying both call "the same kernel primitives," but orchestration policy (sequence, conditions, dispatch decisions) belongs in the OS, not in an App that happens to have a TUI.

This is a current-state description of what Autarch tools actually do today, so the violation may be intentional transitional state. However, the vision document presents this as the target architecture, not a temporary coupling. If the intent is that Gurgeh's arbiter eventually moves to Clavain (as the OS), that migration target should be stated explicitly. If the intent is that Apps legitimately contain LLM orchestration logic, that decision contradicts the stated principle on line 42: "Apps don't contain agency logic."

**Where it should live:** Gurgeh's "arbiter" (the PRD generation intelligence) belongs in Clavain as an OS-level skill or phase definition. Gurgeh should render a Clavain-driven PRD sprint: display progress, collect user input, show confidence scores. The intelligence about how to generate a spec section, which model to use, and what the confidence scoring formula is — those are OS decisions.

**Minimum fix:** Either (a) add an explicit acknowledgment that Gurgeh's arbiter is a migration target to the OS layer and the current architecture is transitional, or (b) add a section explaining why PRD generation intelligence is legitimately an App concern (with a justification). The current text states "Apps don't contain agency logic" and then describes agency logic in an App without reconciling the contradiction.

---

## P2: Boundary Blur

### P2-1 — Intercore doc owns the confidence score formula that belongs to the OS

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Autonomy Ladder → Level 3: Adapt"
**Lines:** 199

**What the text says:**

> "...evidence enables weighted confidence scoring across multiple dimensions — completeness, consistency, cost-effectiveness — following the pattern of Autarch's `ConfidenceScore`, which weights quality metrics (completeness 20%, consistency 25%, specificity 20%, research 20%, assumptions 15%) to produce an actionable composite score rather than a binary judgment."

The specific weights (completeness 20%, consistency 25%, specificity 20%, research 20%, assumptions 15%) are Autarch's `ConfidenceScore` formula — they appear here in the kernel doc as design rationale for how Interspect should score gate evidence. But these weights are OS/App policy, not kernel mechanism. The kernel provides the infrastructure for recording structured evidence with dimensions; it does not mandate the weighting formula.

**Why P2 and not P1:** The weights are cited as an example pattern, not mandated kernel behavior. The surrounding text says "following the pattern of" — i.e., it is guidance, not a specification. But citing specific weights in a kernel document trains readers to think the kernel should implement or enforce this formula.

**Minimum fix:** Replace the specific weights with: "See the Autarch vision doc for Gurgeh's `ConfidenceScore` implementation, which provides a concrete example of multi-dimensional weighted scoring. The kernel records the raw evidence dimensions; the scoring formula is OS/App policy."

---

### P2-2 — Intercore doc contains adaptive threshold prose that is OS policy

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Autonomous Research and Backlog Intelligence → Backlog Refinement Primitives"
**Lines:** 569–571

**What the text says:**

> "**Staleness decay mechanism.** Beads created from discoveries that are never promoted, never worked on, and receive no additional evidence decay in priority over time (configurable rate, default: one priority level per 30 days without activity). Decayed beads that receive new evidence are re-evaluated — fresh signal reverses decay."

"Beads" are a Clavain concept. The kernel does not and should not know what a bead is. This sentence describes a kernel mechanism using a concept that belongs to the OS layer. The kernel can provide a staleness decay primitive (e.g., "discovery records have a configurable priority decay rate"); it cannot describe that mechanism in terms of beads.

Additionally, lines 573 of the same section:

> "Additional backlog refinement (priority escalation, dependency suggestion, weekly digests, feedback loops) is OS-level policy. See the [Clavain vision doc](../../../../os/clavain/docs/vision.md) for the full discovery → backlog pipeline workflow, including source configuration, trigger modes, and backlog refinement rules."

This correctly defers to the OS doc — but the sentence immediately preceding it (the bead decay sentence) contradicts it by describing OS-level bead behavior inside the kernel doc.

**Minimum fix:** Replace "Beads created from discoveries" with "Discovery records that map to backlog items" and note that the OS layer defines what those backlog items are (e.g., beads in Clavain). The decay mechanism is kernel-provided; the item type is OS-defined.

---

### P2-3 — Clavain doc duplicates the kernel mechanism table

**Document:** `os/clavain/docs/vision.md`
**Section:** "Model Routing Architecture → Layer 1: Kernel Mechanism"
**Lines:** 257–260

**What the text says:**

> "All dispatches flow through `ic dispatch spawn` with an explicit model parameter. The kernel records which model was used, tracks token consumption, and emits events. This is the durable system of record for every model decision."

This is accurate and appropriate for an OS doc to reference. However, in the same section, Clavain's vision duplicates and re-explains kernel internals (token tracking, event emission) that are already fully specified in the Intercore vision doc. The Clavain doc's role here should be: "the kernel records dispatch details; the OS configures routing policy on top." Instead, the Clavain doc authors kernel behavior as if they own it.

**Why P2 and not P1:** The content is accurate and appropriate for cross-referencing. The issue is authorship tone — the Clavain doc asserts how the kernel works rather than citing the kernel doc.

**Minimum fix:** Add a cross-reference: "For full kernel dispatch mechanics, see the [Intercore vision doc](../../../infra/intercore/docs/product/intercore-vision.md). This section describes only the OS routing policy built on top of those primitives."

---

### P2-4 — Cross-layer diagram inconsistency between documents

**Documents:** All three
**Sections:** Architecture diagrams

The Intercore vision (lines 29–63) shows this layer ordering:

```
Clavain (Operating System)
Intercore (Kernel)
Interspect (Profiler)
Autarch (Apps) — interactive TUI surfaces
Companion Plugins (Drivers)
```

The Clavain vision (lines 19–47) shows:

```
Apps (Autarch)
Layer 3: Drivers (Companion Plugins)
Layer 2: OS (Clavain)
Layer 1: Kernel (Intercore)
Profiler: Interspect
```

The Autarch vision (lines 15–31) shows:

```
Apps (Autarch)
OS (Clavain)
Kernel (Intercore)
```

The inconsistency: in the Intercore doc, "Autarch (Apps)" appears after Interspect and before "Companion Plugins (Drivers)" with no numbering. In the Clavain doc, Autarch is above Drivers (Layer 3), which is above Clavain (Layer 2), which is above the Kernel (Layer 1). In the Autarch doc, Drivers do not appear at all.

The Drivers layer is numbered "Layer 3" in both the Intercore and Clavain docs, but sits above the OS, which is counterintuitive — drivers in OS terminology sit below the OS, not above it. The naming "Layer 3" for Drivers and "Layer 2" for the OS means layer numbers increase downward in the Clavain doc but the diagram renders top-to-bottom with Apps at top. This is confusing to new readers.

**Minimum fix:** Standardize the layer diagram across all three documents to use a single canonical rendering. Suggest: number layers from 0 (kernel) upward, so Layer 0=Kernel, Layer 1=OS, Layer 2=Drivers, Layer 3=Apps. Or adopt the top-to-bottom convention (Apps at top, no layer numbers) consistently. Eliminate the numbering from the Drivers/OS labels since it currently implies Drivers are "above" the OS in stack terms while the text says they call the kernel directly.

---

### P2-5 — Intercore doc describes TUI consumer internals (Kernel→Apps leak)

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Events → Go API pattern"
**Lines:** 285

**What the text says:**

> "For programmatic consumers (Interspect, TUI, future daemon), the kernel exposes a `Replay(sinceID, filter, handler)` function...Filters are fluent builders — `NewEventFilter().WithEventTypes("phase.advanced", "dispatch.completed").WithSince(t).WithLimit(100)` — enabling consumers to express complex queries without string manipulation. This follows the pattern proven in Autarch's event spine, where the same `EventFilter` serves both CLI queries and programmatic replay."

Citing Autarch's event spine as the design justification for a kernel API is an inverted dependency. The kernel is the permanent layer; the App layer (Autarch) is swappable. Citing an App's internal implementation ("Autarch's event spine") as the proven pattern that the kernel adopts means the kernel's API design is justified by reference to an App it is supposed to be independent of.

**Why P2 and not P1:** The API itself (`Replay`, `EventFilter`) is legitimate kernel mechanism. The citation of "Autarch's event spine" as the justification is the boundary problem — it is a documentation-level dependency that could be removed without changing the API.

**Minimum fix:** Replace "This follows the pattern proven in Autarch's event spine" with a generic justification (e.g., "Fluent filter builders are a well-established pattern for composing queries without string manipulation"). If the Autarch provenance is worth preserving for historical reasons, add it as a parenthetical: "(This pattern was first implemented in Autarch's event spine before being adopted as the kernel standard.)"

---

## P3: Style and Polish

### P3-1 — Naming drift: "Drivers" vs "Companion Plugins"

**Documents:** Intercore vision, Clavain vision
**Observation:** The Intercore doc uses "Companion Plugins (Drivers)" in the first diagram but "Drivers (Plugins)" in the Three-Layer Architecture diagram. The Clavain doc uses "Drivers (Companion Plugins)" in its architecture diagram but "companion plugins" in prose. The Autarch doc omits the Drivers layer entirely.

These are the same components referred to by three slightly different names across the documents. The inconsistency is cosmetic but erodes layer legibility for new readers.

**Minimum fix:** Pick one canonical label — recommend "Drivers (Layer 2)" since that term is used in the "Three-Layer Architecture" diagram — and apply it uniformly across all architecture diagrams. Reserve "companion plugins" for prose references to Claude Code plugin packaging specifically.

---

### P3-2 — Referential asymmetry: Intercore references Clavain's vision doc; Clavain does not reciprocate

**Documents:** `intercore-vision.md` line 573, `autarch-vision.md` line 93
**Observation:** Both the Intercore and Autarch docs contain explicit links to the Clavain vision doc for the "full discovery → backlog pipeline workflow." The Clavain vision doc does not link to the Intercore vision doc except via the architecture diagram reference in its opening section. The "Discovery → Backlog Pipeline" section in Clavain (lines 138–211) describes itself as the authoritative pipeline definition but does not cite the Intercore doc as the source of the kernel primitives it relies on.

**Minimum fix:** Add a cross-reference at the top of the "Discovery → Backlog Pipeline" section in `os/clavain/docs/vision.md`: "This section defines OS-level pipeline policy. The underlying kernel primitives (discovery records, confidence scoring, event types, dedup enforcement) are defined in the [Intercore vision doc](../../../infra/intercore/docs/product/intercore-vision.md)."

---

### P3-3 — Intercore doc uses "sprint" as a concept in the migration strategy

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Section:** "Migration Strategy → Sprint Migration: Hybrid to Kernel-Driven"
**Lines:** 509–519

The section title "Sprint Migration" and the body text ("The sprint skill currently orchestrates the full brainstorm→ship workflow") use "sprint" as if it is a kernel concept. The document has correctly established that phase names are OS vocabulary. "Sprint" is an OS concept (Clavain's term for a development run through its standard phase chain), not a kernel concept.

**Minimum fix:** Rename the section to "OS Workflow Migration: Hybrid to Kernel-Driven" and use "OS workflow" or "phase-chain workflow" instead of "sprint" in the kernel doc. The migration table on lines 499–507 (which correctly uses `ic sentinel`, `ic lock`, `ic dispatch`, `ic run` commands) is fine; only the framing prose needs adjustment.

---

## Findings Not Present (Confirming Correct Boundaries)

The following were checked and found correctly scoped:

1. **Clavain doc does not redefine kernel mechanisms.** The "What Kernel Owns" and "What Kernel Does Not Own" framing appears only in the Intercore doc. Clavain correctly treats the kernel as a black box it calls.

2. **Autarch doc does not implement agency logic in the swappable components.** The `pkg/tui` component library (ShellLayout, ChatPanel, etc.) correctly contains no domain logic. Line 73: "These components depend only on Bubble Tea and lipgloss. They have no Autarch domain coupling."

3. **Autarch doc correctly defers routing and gate decisions to Clavain.** Line 42: "Apps don't contain agency logic. Autarch doesn't decide which model to route a review to, or what gates a phase requires, or when to advance a run. Those are OS decisions." This principle is correctly stated, even if P1-3 above identifies a current-state violation in the tool descriptions.

4. **Intercore doc's "What the Kernel Does Not Own" section is correctly scoped.** Lines 112–117 correctly exclude phase names, routing, prompt content, gate policies, session lifecycle, and self-improvement decisions from kernel ownership.

5. **Clavain doc's treatment of Interspect is correctly scoped.** Interspect is described as reading kernel events and proposing OS configuration changes — neither a kernel component nor an App. This is correctly represented in all three documents.

---

## Remediation Priority

| Priority | Finding | Effort | Risk If Ignored |
|---|---|---|---|
| P0-1 | Remove OS action policy from kernel's confidence tier table | Low (delete 2 columns, add pointer) | Kernel will be built to enforce "create bead" logic, which requires kernel→OS coupling |
| P1-1 | Reframe concrete scenario to use opaque phase labels | Low | Future contributors add phase-name checks to kernel code |
| P1-2 | Move event reactor / broker architecture to OS and App docs | Low | Kernel doc becomes the authoritative source for App-layer design, inverting dependency |
| P1-3 | Reconcile Autarch doc's "Apps don't contain agency logic" claim with Gurgeh arbiter | Medium | Design inconsistency hardens into architecture; Gurgeh arbiter never migrates to OS |
| P2-1 through P2-5 | Individual section fixes | Low each | Boundary erosion compounds over time as new contributors follow existing patterns |
| P3-1 through P3-3 | Naming and linking consistency | Trivial | Reader confusion only |

---

*Analysis performed against documents as of 2026-02-19. No code was reviewed — findings are documentation-layer only. Implementation alignment with these docs is a separate review.*
