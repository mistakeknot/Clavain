# Cross-Reference Integrity Review: Vision Documents

**Reviewer:** fd-cross-reference
**Date:** 2026-02-19
**Documents Reviewed:**
- `infra/intercore/docs/product/intercore-vision.md` (v1.6, 2026-02-19)
- `os/clavain/docs/vision.md` (no version header, revised 2026-02-19)
- `infra/intercore/docs/product/autarch-vision.md` (v1.0, 2026-02-19)

---

## Invariants That Must Hold

Before listing findings, these are the cross-document invariants the review checks against:

1. Every relative markdown link resolves to an existing file at the computed path.
2. When doc A says "see doc B for topic X", doc B must contain substantive coverage of X.
3. Layer numbers (1/2/3) must refer to the same components across all three docs.
4. The three-layer architecture diagram must be compatible across all three docs.
5. The same concept (drivers, companion plugins, mechanism, policy) must use the same term in the same sense across docs.
6. Migration ordering claims must agree across the intercore and autarch vision docs.
7. Present-tense factual claims must reflect current reality, not future aspirations.

---

## P0 Findings (Broken Links, Nonexistent Content)

### P0-1: Unlinked plain-text reference in intercore-vision.md

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Line:** 54
**Problem:** The `Kernel / OS / Profiler Model` diagram contains:

```
Autarch (Apps) — interactive TUI surfaces (see Autarch vision doc)
```

This is plain prose, not a hyperlink. All other references to the Autarch vision doc within intercore-vision.md use a proper markdown link `[Autarch vision doc](autarch-vision.md)`. This inline mention is the one place that doesn't, making it non-navigable in rendered markdown and inconsistent with the document's own linking pattern.

**Fix:** Replace with the hyperlink form already used elsewhere:

```
Autarch (Apps) — interactive TUI surfaces (see [Autarch vision doc](autarch-vision.md))
```

---

## P1 Findings (Contradictory Definitions, Incorrect Present-Tense Claims)

### P1-1: "Not a Claude Code plugin" contradicts current reality

**Document:** `os/clavain/docs/vision.md`
**Line:** 403
**Problem:** The "What Clavain Is Not" section states:

> **Not a Claude Code plugin.** Clavain runs on its own TUI (Autarch). It dispatches to Claude, Codex, Gemini, GPT-5.2, and other models as execution backends. The Claude Code plugin interface is one driver among several — a UX adapter, not the identity.

This is stated as current fact, but Clavain is currently deployed as a Claude Code plugin with a `.claude-plugin/plugin.json` manifest. The Autarch TUI does not yet replace the Claude Code plugin interface — it is a future aspiration. The intercore vision doc explicitly places "Autarch merged into Interverse monorepo" at the v1.5 horizon (1-2 months out), meaning the architectural state described here has not yet arrived.

Readers who encounter this section will be confused: Clavain has a plugin.json, hooks.json, and is installed as a Claude Code plugin, yet the vision doc says it is not one.

**Fix:** Change the present-tense claim to an aspirational framing:

> **Not primarily a Claude Code plugin.** Clavain's identity is an autonomous software agency, not a Claude Code extension. Autarch (TUI) will be the primary interface; the Claude Code plugin interface is one UX adapter among several. Today it ships as a Claude Code plugin because that surface is available now — but the architecture is designed to outlive any single host platform.

### P1-2: "Real magic lives here" inconsistency in guiding principles

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Line:** 85–89
**Document:** `os/clavain/docs/vision.md`
**Line:** 49

**Problem:** The intercore vision's Layer 1 description says:

> `└── The "real magic" lives here: everything that matters is in 'ic'`

And the guiding principle says:

> **The guiding principle:** Plugins work in Claude Code, but the real magic is in Clavain + Intercore.

The Clavain vision's guiding principle says:

> The guiding principle: the real magic is in the agency logic and the kernel beneath it.

Intercore's Layer 1 bullet claims all the magic lives exclusively in the kernel. The guiding principle (in the same document) corrects this to "Clavain + Intercore". Clavain's vision correctly attributes the magic to agency logic AND kernel. The Layer 1 bullet is the outlier — it overclaims and is internally inconsistent with its own document.

**Fix:** In intercore-vision.md line 85, replace:

```
└── The "real magic" lives here: everything that matters is in `ic`
```

with:

```
└── The durable foundation: kernel + OS together are where capability lives
```

or, if you prefer to keep the spirit, align it with the guiding principle already in the same document:

```
└── Mechanism and policy together — the kernel enables what Clavain builds on top of
```

### P1-3: Autarch merge tense conflict

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Lines:** 600, 689

**Problem:** Line 600 (the Landscape section) says:

> Autarch is merging into the Interverse monorepo as the apps/TUI layer...

Line 689 (the Success Horizons table) says, for v1.5:

> Autarch merged into Interverse monorepo.

The Landscape section uses present continuous ("is merging") implying it has not happened. The horizon table puts the completed merge at v1.5 (1-2 months out). The autarch-vision.md exists inside the intercore/docs/product/ directory already, but there is no `/root/projects/Interverse/infra/autarch/` directory — confirming the code merge has not occurred.

This is not just style. A new contributor reading the Landscape section would believe Autarch is already part of Interverse. The v1.5 horizon table corrects this impression but requires reading further.

**Fix:** In line 600, update the present continuous to future tense:

> Autarch will merge into the Interverse monorepo as the apps/TUI layer...

---

## P2 Findings (Inconsistent Terminology, Diagram Differences, Out-of-Date Claims)

### P2-1: Autarch architecture diagram omits Interspect and Drivers

**Document:** `infra/intercore/docs/product/autarch-vision.md`
**Lines:** 13–32

**Problem:** The primary architecture diagram in autarch-vision.md shows:

```
Apps (Autarch)
OS (Clavain)
Kernel (Intercore)
```

Both the intercore-vision.md and clavain/docs/vision.md include Interspect as a named Profiler element and Drivers (Companion Plugins) as Layer 3. The autarch diagram is the only one of the three that omits both. A reader using only the autarch doc as a reference would not know that Drivers exist as a distinct layer or that Interspect occupies a cross-cutting profiler role.

The autarch doc does reference the three-layer architecture by name in its section heading "Relationship to the Three-Layer Architecture" (line 111), and mentions Interspect not at all. This is the most severe diagram divergence.

**Comparison matrix:**

| Element | intercore-vision diagram | clavain vision diagram | autarch-vision diagram |
|---|---|---|---|
| Apps (Autarch) | Yes (in full diagram) | Yes | Yes |
| Layer 3: Drivers | Yes | Yes | **No** |
| Layer 2: OS (Clavain) | Yes | Yes | Yes (as "OS") |
| Layer 1: Kernel (Intercore) | Yes | Yes | Yes (as "Kernel") |
| Profiler: Interspect | Yes (in full diagram) | Yes | **No** |

**Fix:** Add Drivers and Interspect to the autarch diagram:

```
Apps (Autarch)
├── Interactive TUI tools: Bigend, Gurgeh, Coldwine, Pollard
├── Shared component library: pkg/tui (Bubble Tea + lipgloss)
├── Renders OS opinions into interactive experiences
└── Swappable — Autarch is one set of apps, not the only possible set

Layer 3: Drivers (Companion Plugins)
├── Each wraps one capability (review, coordination, research, visibility)
└── Examples: interflux, interlock, interject, intermux, tldr-swinton

Layer 2: OS (Clavain)
├── The autonomous software agency — macro-stages, quality gates, model routing
├── Skills, prompts, routing tables, workflow definitions
├── Configures the kernel: phase chains, gate rules, dispatch policies
└── Reacts to kernel events (agent completed → advance phase)

Layer 1: Kernel (Intercore)
├── Runs, phases, gates, dispatches, events — the durable system of record
├── Host-agnostic Go CLI + SQLite
└── Mechanism, not policy — the kernel doesn't know what "brainstorm" means

Profiler: Interspect (cross-cutting)
├── Reads kernel events, correlates with corrections
├── Proposes OS configuration changes
└── Never modifies the kernel — only the OS layer
```

### P2-2: Layer 3 example drivers are inconsistent across docs

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Line:** 74 (Three-Layer Architecture diagram)
**Document:** `os/clavain/docs/vision.md`
**Line:** 28

**Problem:** The same "Layer 3 examples" bullet in the three-layer diagram uses different third examples:

- intercore-vision.md line 74: `Examples: interflux (review), interlock (coordination), intermux (visibility)`
- clavain/docs/vision.md line 28: `Examples: interflux (review), interlock (coordination), interject (research)`

The first two examples agree. The third differs: intercore shows `intermux (visibility)`, Clavain shows `interject (research)`. Both are valid drivers. The inconsistency is minor but signals the diagrams were not co-edited. A reader cross-referencing both docs would notice the discrepancy and wonder which is canonical.

**Fix:** Agree on a canonical third example. `interject` is the better third example given that both documents discuss it extensively in the context of the discovery pipeline. Update intercore-vision.md line 74:

```
└── Examples: interflux (review), interlock (coordination), interject (research)
```

### P2-3: Intercore "Kernel / OS / Profiler Model" section title omits Apps

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Line:** 27

**Problem:** The section is titled `## The Kernel / OS / Profiler Model`. The section body contains:

```
Autarch (Apps) — interactive TUI surfaces (see Autarch vision doc)
```

Autarch (Apps) is a fourth named component in the diagram but missing from the section title. The autarch-vision.md was "extracted from the Intercore vision doc on 2026-02-19" (per its footer), which implies the section existed before the extraction. The title was never updated to reflect the four-part model.

**Fix:** Rename the section heading:

```
## The Kernel / OS / Profiler / Apps Model
```

or, since the section body uses a different framing:

```
## The Full Stack: Kernel, OS, Profiler, and Apps
```

### P2-4: "Layer 1/2/3" labels repurposed for Model Routing within Clavain vision

**Document:** `os/clavain/docs/vision.md`
**Lines:** 255–268

**Problem:** The document establishes `Layer 1 = Kernel (Intercore)`, `Layer 2 = OS (Clavain)`, `Layer 3 = Drivers` as the architectural stack terminology. Then, in the "Model Routing Architecture" section, the same labels are reused for a completely different taxonomy:

```
### Layer 1: Kernel Mechanism
### Layer 2: OS Policy
### Layer 3: Adaptive Optimization
```

Here "Layer 1/2/3" describes three stages of model routing sophistication (static → complexity-aware → adaptive), not the three architectural layers of the stack. The term collision creates ambiguity for readers who just learned "Layer 3 = Drivers".

This is a local terminology collision within one document, not a cross-document inconsistency, but it reduces document coherence.

**Fix:** Rename the model routing section headings to avoid the "Layer N" label:

```
### Tier 1: Kernel Mechanism (static routing)
### Tier 2: OS Policy (complexity-aware routing)
### Tier 3: Adaptive Optimization (outcome-driven routing)
```

or use completely different vocabulary:

```
### Stage 1: Kernel-Tracked Dispatch
### Stage 2: Policy-Configured Routing
### Stage 3: Outcome-Adaptive Optimization
```

### P2-5: inter-* constellation table omits Layer 2 (OS/Clavain)

**Document:** `os/clavain/docs/vision.md`
**Lines:** 279–305

**Problem:** The table organizes companions by layer:

```
Infrastructure (Layer 1): intercore, interspect
Drivers (Layer 3): 12 companions
Apps (Autarch): 4 tools
```

Layer 2 (OS/Clavain) is absent. This makes sense in isolation (the document is about Clavain, so listing "Clavain" in Clavain's own table would be circular), but it creates the impression that the three-layer naming skips from Layer 1 to Layer 3. The "three tiers" framing at line 279 ("infrastructure, drivers, apps") further confuses matters by using "tiers" to mean something different than the numbered Layer N labels used elsewhere.

**Fix:** Add a parenthetical to the section or a row noting Layer 2:

```
The ecosystem has three tiers of companions, all built on top of the OS layer (Clavain itself, Layer 2):

**Infrastructure (Layer 1)**
...

**Drivers (Layer 3)**
...
```

Or simply clarify the "three tiers" framing:

```
The ecosystem has components at every layer of the stack. Clavain (this tool) is Layer 2. Below it and around it:
```

### P2-6: Pollard/Gurgeh migration order differs between intercore and autarch vision docs

**Document:** `infra/intercore/docs/product/autarch-vision.md`
**Lines:** 87, 95 (migration sections 2 and 3)
**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Line:** 691 (v3 horizon)

**Problem:** The autarch-vision.md specifies a migration order:

1. Bigend (first)
2. Pollard (second)
3. Gurgeh (third)
4. Coldwine (last)

The intercore-vision.md v3 horizon lumps Pollard and Gurgeh together:

> Pollard migrated to kernel discovery pipeline. Gurgeh PRD generation backed by kernel runs.

This implies they happen at the same release horizon (v3). The autarch doc gives Pollard a distinct earlier step because Pollard feeds the discovery pipeline (which the kernel needs to support in v2 for discovery events). The intercore doc does not capture this dependency.

This is not a contradiction that will cause a process failure, but any planning based on the intercore horizon table will miss the dependency sequencing.

**Fix:** In intercore-vision.md line 691, separate Pollard and Gurgeh across v2 and v3, matching the autarch doc's ordering:

- v2: Add `Pollard research output connected to kernel discovery events (read path)`
- v3: Keep `Gurgeh PRD generation backed by kernel runs`

### P2-7: Interspect described as "profiler" in all docs but architecture section title says "Profiler Model" — not a formal tier label

**Document:** `infra/intercore/docs/product/intercore-vision.md`
**Line:** 48

**Problem:** Both intercore-vision.md and clavain/docs/vision.md place Interspect under the label "Profiler: Interspect" in their diagrams. This is a useful cross-cutting label. However, the clavain vision's inter-* constellation table (line 281) places interspect under "Infrastructure (Layer 1)" alongside intercore. This creates two different conceptual placements:

- Diagrams: Interspect is a cross-cutting profiler, separate from the layers
- Constellation table: Interspect is infrastructure, same layer as the kernel

These framings are not contradictory at a technical level (Interspect reads kernel events and is low-level infrastructure), but the categorization is unstable — someone editing the constellation table might move interspect to Layer 2 or Layer 3 based on different reasoning.

**Fix (minor):** In the constellation table section of clavain/docs/vision.md, add a clarifying note:

```
**Infrastructure (Layer 1)**
*(Interspect is listed here as infrastructure but operates as a cross-cutting profiler — it reads from the kernel and writes to the OS layer)*
```

### P2-8: Clavain vision diagram's "Apps" block omits pkg/tui, Autarch diagram's "Apps" block includes it

**Document:** `os/clavain/docs/vision.md`
**Lines:** 21–23
**Document:** `infra/intercore/docs/product/autarch-vision.md`
**Lines:** 18

**Problem:** The Clavain vision diagram's Apps block shows:

```
Apps (Autarch)
├── Interactive TUI surfaces: Bigend, Gurgeh, Coldwine, Pollard
├── Renders OS opinions into interactive experiences
└── Swappable — Autarch is one set of apps, not the only possible set
```

The autarch diagram adds `pkg/tui` as a shared component:

```
Apps (Autarch)
├── Interactive TUI tools: Bigend, Gurgeh, Coldwine, Pollard
├── Shared component library: pkg/tui (Bubble Tea + lipgloss)
├── Renders OS opinions into interactive experiences
└── Swappable — Autarch is one set of apps, not the only possible set
```

The Clavain vision also omits mention of `pkg/tui` entirely (zero occurrences in clavain/docs/vision.md, vs the autarch doc devoting a full section to it). This is a minor omission — `pkg/tui` is an internal implementation detail — but when the docs are compared side by side, the Clavain diagram appears to describe an older or simplified view.

**Fix:** Add `pkg/tui` to the Apps block in clavain/docs/vision.md for diagram parity with autarch-vision.md.

---

## P3 Findings (Minor Phrasing Differences)

### P3-1: "Interactive TUI surfaces" vs "Interactive TUI tools"

**Document:** `os/clavain/docs/vision.md` line 21: `Interactive TUI surfaces`
**Document:** `infra/intercore/docs/product/autarch-vision.md` line 17: `Interactive TUI tools`

Both autarch diagram instances in intercore-vision.md (line ~21) use "surfaces". The autarch-vision.md itself uses "tools". Pick one and apply consistently. "Tools" aligns with how the four applications are described throughout the autarch doc.

### P3-2: Guiding principle wording drift

**intercore-vision.md line 89:** `Plugins work in Claude Code, but the real magic is in Clavain + Intercore.`
**clavain/docs/vision.md line 49:** `the real magic is in the agency logic and the kernel beneath it.`

"Clavain + Intercore" vs "agency logic + kernel" — same concept, different words. "Agency logic" is more precise than just "Clavain" since Clavain's identity as an agency is what the vision document is asserting. Clavain's phrasing is better; intercore's could adopt it.

### P3-3: "Apps are swappable" appears only in Clavain vision, not intercore

**clavain/docs/vision.md line 49:** `Apps are swappable.`
**intercore-vision.md:** No equivalent statement.

The intercore Layer 1 bullet says "If Claude Code disappears, the kernel and all its data survive untouched" which is about platform independence, not about app swappability. The Clavain vision's guiding principle is more complete by including "Apps are swappable." This would reinforce autarch's own claim to being the "reference implementation, not the only implementation." Consider adding to the intercore guiding principle.

### P3-4: Clavain vision's Layer 1 bullet uses different survival framing than intercore

**clavain/docs/vision.md line 38:** `If the UX layer disappears, the kernel and all its data survive untouched`
**intercore-vision.md line 85:** `If Claude Code disappears, the kernel and all its data survive untouched`

These are the same sentiment but framed differently. "UX layer" is more general and architecturally precise. "Claude Code" is more concrete and historically specific. The Clavain framing is better as a vision statement; the intercore framing is better as an explanation to someone unfamiliar with the stack. Both are defensible in context.

### P3-5: "Clavain vision doc" link in autarch-vision.md lacks anchor

**Document:** `infra/intercore/docs/product/autarch-vision.md`
**Line:** 93

The link to the Clavain vision doc does not include a heading anchor:

```
(see [Clavain vision doc](../../../../os/clavain/docs/vision.md) for the full pipeline workflow)
```

The clavain vision has a specific section "Discovery → Backlog Pipeline" that this should link to. A fragment anchor would make navigation faster:

```
(see [Clavain vision doc](../../../../os/clavain/docs/vision.md#discovery--backlog-pipeline) for the full pipeline workflow)
```

Similarly, the intercore-vision.md line 573 could benefit from the same anchor.

---

## Summary Table

| ID | Priority | Document(s) | Line(s) | Issue |
|---|---|---|---|---|
| P0-1 | P0 | intercore-vision.md | 54 | Plain-text "see Autarch vision doc" not hyperlinked |
| P1-1 | P1 | clavain/docs/vision.md | 403 | "Not a Claude Code plugin" contradicts current deployment reality |
| P1-2 | P1 | intercore-vision.md | 85 | Layer 1 bullet claims all magic in kernel, contradicts own guiding principle |
| P1-3 | P1 | intercore-vision.md | 600, 689 | Autarch merge tense conflict: "is merging" vs planned "merged" at v1.5 |
| P2-1 | P2 | autarch-vision.md | 13–32 | Main diagram omits Interspect (Profiler) and Drivers (Layer 3) entirely |
| P2-2 | P2 | intercore-vision.md | 74 | Layer 3 third example is `intermux` not `interject` (Clavain says `interject`) |
| P2-3 | P2 | intercore-vision.md | 27 | Section title "Kernel / OS / Profiler Model" omits Apps (Autarch) |
| P2-4 | P2 | clavain/docs/vision.md | 255–268 | "Layer 1/2/3" reused for model routing stages, collides with stack layer labels |
| P2-5 | P2 | clavain/docs/vision.md | 279–305 | Inter-* constellation table skips Layer 2 (OS), confusing three-layer numbering |
| P2-6 | P2 | intercore-vision.md / autarch-vision.md | 691 / 87–103 | Pollard before Gurgeh ordering in autarch vs same-horizon in intercore v3 |
| P2-7 | P2 | clavain/docs/vision.md | 281 | Interspect placed in "Layer 1 infrastructure" in table but as cross-cutting profiler in diagram |
| P2-8 | P2 | clavain/docs/vision.md | 21–23 | Apps diagram block omits pkg/tui, diverging from autarch-vision.md diagram |
| P3-1 | P3 | clavain/vision.md + autarch-vision.md | 21, 17 | "surfaces" vs "tools" — pick one |
| P3-2 | P3 | intercore-vision.md | 89 | Guiding principle wording: "Clavain + Intercore" vs "agency logic + kernel" |
| P3-3 | P3 | intercore-vision.md | 89 | Missing "Apps are swappable" in intercore guiding principle |
| P3-4 | P3 | clavain/vision.md | 38 | "UX layer" vs "Claude Code" as what disappears in kernel survival claim |
| P3-5 | P3 | autarch-vision.md + intercore-vision.md | 93, 573 | Cross-doc links to Clavain vision lack heading anchors for the referenced section |

---

## Content Placement Promises: Verification

| Promise Location | Promise | Target | Found |
|---|---|---|---|
| intercore-vision.md line 533 | "For full details on the four tools, pkg/tui, and the migration plan, see Autarch vision doc" | autarch-vision.md | Fulfilled: four tools covered (§The Four Tools), pkg/tui covered (§pkg/tui), migration plan covered (§Migration to Intercore Backend) |
| intercore-vision.md line 573 | "See Clavain vision doc for the full discovery → backlog pipeline workflow, including source configuration, trigger modes, and backlog refinement rules" | clavain/docs/vision.md | Fulfilled: Source configuration covered (§Discovery → Backlog Pipeline), trigger modes covered (Three trigger modes section), backlog refinement rules covered (Backlog refinement rules section) |
| autarch-vision.md line 93 | "see Clavain vision doc for the full pipeline workflow" | clavain/docs/vision.md | Fulfilled: pipeline diagram and workflow present |
| clavain/docs/vision.md line 49 | "For details on the apps layer, see the Autarch vision doc" | autarch-vision.md | Fulfilled: Autarch doc covers apps layer in depth |
| clavain/docs/vision.md line 305 | Autarch link (same as above) | autarch-vision.md | Fulfilled |

All content placement promises are satisfied. The documents deliver what they promise.

---

## Link Integrity: Final Verification

All relative links were resolved against the actual filesystem:

| Link | Source File | Target Path (resolved) | Exists |
|---|---|---|---|
| `[Autarch vision doc](autarch-vision.md)` | intercore-vision.md (×2) | `/root/projects/Interverse/infra/intercore/docs/product/autarch-vision.md` | Yes |
| `[Clavain vision doc](../../../../os/clavain/docs/vision.md)` | intercore-vision.md | `/root/projects/Interverse/os/clavain/docs/vision.md` | Yes |
| `[Autarch vision doc](../../../infra/intercore/docs/product/autarch-vision.md)` | clavain/docs/vision.md (×2) | `/root/projects/Interverse/infra/intercore/docs/product/autarch-vision.md` | Yes |
| `[Clavain vision doc](../../../../os/clavain/docs/vision.md)` | autarch-vision.md | `/root/projects/Interverse/os/clavain/docs/vision.md` | Yes |

No broken links. All eight relative links resolve correctly. The depth counts (4 levels from `infra/intercore/docs/product/` to Interverse root; 3 levels from `os/clavain/docs/` to Interverse root) are correct.

---

## Highest-Priority Action List

1. **Add the hyperlink** at intercore-vision.md line 54 (P0 — currently un-navigable).
2. **Reframe "Not a Claude Code plugin"** in clavain/docs/vision.md line 403 as an aspirational identity statement, not a current fact (P1 — will mislead new readers).
3. **Fix "real magic lives here"** in intercore-vision.md line 85 to not contradict the guiding principle two paragraphs below it (P1 — internal inconsistency).
4. **Fix "is merging" to "will merge"** in intercore-vision.md line 600 (P1 — tense conflict with the Autarch vision doc being a forward-looking plan).
5. **Add Interspect and Drivers to autarch-vision.md diagram** (P2 — autarch readers are left with an incomplete model of the stack they're building on top of).
6. **Standardize Layer 3 third example** across intercore and Clavain diagrams (P2 — `interject` is the better pick, featured heavily in both docs).
7. **Rename section heading** in intercore-vision.md to include Apps (P2 — title/content mismatch).
8. **Rename "Layer 1/2/3" in model routing section** of clavain/docs/vision.md to avoid collision with the architectural stack numbering (P2 — terminology collision within one document).
