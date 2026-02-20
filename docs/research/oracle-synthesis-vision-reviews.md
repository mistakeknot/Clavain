# Synthesis: Oracle Vision Doc Reviews

**Date:** 2026-02-19
**Sources:** 4 Oracle (GPT-5.2 Pro) reviews — combined 3-doc review, plus individual reviews of intercore-vision.md, clavain-vision.md, and autarch-vision.md
**Method:** Deduplication + thematic grouping across all 4 reviews, ranked by cross-doc impact

---

## Theme 1: Layer Count and Stack Definition (highest leverage)

**Core problem:** The docs say "three-layer architecture" but describe 4-5 tiers (Kernel, OS, Drivers, Apps, Profiler). "Layer 3" sometimes means Drivers, sometimes Apps. Autarch is both "above layers" and within the stack.

**Related findings:**
- Combined P0-1: "three-layer stack is not defined consistently"
- Intercore P0.1: "three-layer architecture contradicts your stated 3-layer model"
- Clavain P1: "layering/numbering is internally inconsistent"
- Autarch P0.3: "Drivers adds an undocumented layer"

**Coherent fix:** Define a single canonical stack and enforce it in all three docs:

| Layer | Name | Owns |
|-------|------|------|
| 3 | Apps (Autarch) | Interactive surfaces, rendering, user input |
| 2 | OS (Clavain) | Policy, workflow, routing, opinions |
| 1 | Kernel (Intercore) | Primitives, durability, enforcement, events |

Place **Drivers (companion plugins)** as OS extensions within Layer 2 — they implement OS-delegated capabilities. Place **Interspect (Profiler)** as a cross-cutting concern, not a layer. Remove all "Layer 3: Drivers" language.

---

## Theme 2: Write-Path Contract (most critical missing piece)

**Core problem:** No enforcement mechanism defines which layers can mutate kernel state. Apps and drivers "call ic directly" while the OS is supposedly the policy authority. This makes "each layer stays in its lane" aspirational, not architected.

**Related findings:**
- Combined P0-2: "apps and drivers call ic directly without a policy firewall"
- Intercore P0.7: "plugins call ic directly undermines OS policy enforcement"
- Clavain P0: "drivers call the kernel directly undermines OS authority"
- Autarch P0.4: "app configures OS policy directly via kernel primitives"
- Autarch P0.5: "Coldwine/Clavain orchestration split contradicts apps render"

**Coherent fix:** Define a split-write model:

1. **Kernel writes** — only the kernel emits events and transitions state
2. **OS writes** — only the OS (Clavain) may invoke policy-governing mutations: `ic run create`, `ic run advance`, `ic gate override`, phase chain definitions
3. **Driver writes** — drivers may only write to constrained namespaces: capability results, artifacts, evidence, telemetry (not run/phase/gate mutations)
4. **App writes** — apps are read-only to kernel + submit intents to OS. Apps call OS operations, not kernel primitives, for anything that implies policy

Add one explicit "Write-Path Contract" section to each vision doc.

---

## Theme 3: Kernel Policy Leakage (mechanism vs policy)

**Core problem:** The kernel doc claims "mechanism, not policy" but specifies scoring algorithms, decay rates, dedup thresholds, sprint presets, revert plan generation, and backlog semantics — all of which are policy.

**Related findings:**
- Combined P1-6: "discovery scoring slips from primitive into policy"
- Intercore P0.3: "kernel claims mechanism but specifies policy algorithms"
- Intercore P0.4: "kernel takes ownership of backlog semantics (OS domain)"
- Intercore P0.5: "kernel generates git revert sequences (OS responsibility)"
- Intercore P0.6: "kernel defaults/presets contradict 'kernel doesn't own phase semantics'"
- Intercore P0.8: "dependency graph auto-verification events are workflow reactions"
- Clavain P0: "kernel is mechanism not policy while repeatedly taking policy ownership"
- Autarch P1.3: "Pollard migration pushes policy into kernel"

**Coherent fix:** Apply a strict boundary test — if it encodes human preference, workflow opinion, or domain vocabulary, it belongs in the OS:

| Move from Kernel to OS | Kernel keeps |
|------------------------|-------------|
| Confidence scoring algorithms + weights | Store scores as opaque numbers |
| Dedup threshold (0.85) + decay rate (30d) | Enforce thresholds passed by OS |
| Sprint presets + phase chain defaults | Accept phase chains from OS |
| Git revert plan generation | Store commit SHAs as provenance |
| Auto-verification event reactions | Emit `run.completed` events |
| Backlog item semantics ("bead", priority) | Generic work item registry |

---

## Theme 4: ic state Contradiction

**Core problem:** Kernel state is declared "kernel-internal only" and "not a general-purpose config store," but the migration table uses `ic state` for OS/session features.

**Related findings:**
- Combined P0-3: "kernel state is kernel-internal but migration plans use it as OS store"
- Intercore P1.3: "kernel never stores OS policy vs kernel stores run config snapshots"

**Coherent fix:** Choose one:
1. **Promote state** to a supported public primitive with namespacing (`_kernel/*` reserved, `os/*` for Clavain, `app/*` for Autarch)
2. **Keep state private** and introduce explicit OS-owned persistence (`ic session`, `ic scratch`) with different guarantees

Option 1 is simpler and matches actual usage.

---

## Theme 5: Execution Model Gaps (daemon vs CLI)

**Core problem:** The kernel is "not a daemon" and "stateless between CLI calls," but several features require continuous execution: time-based decay, reconciliation engine, event broker.

**Related findings:**
- Combined P0-4: "time-based decay specified as kernel behavior but kernel is no daemon"
- Clavain P0: "kernel stateless between CLI calls conflicts with reconciliation engine"
- Autarch P0.2: "ic tui depends on WebSocket broker (implies running server)"

**Coherent fix:** Specify that decay and reconciliation are **lazily computed at query time** (virtual priority, not mutations) or **triggered by OS reactor** (`ic backlog decay --now=$(date)` in cron/systemd). The kernel remains a CLI binary. The event reactor is an OS responsibility. The signal broker is an app-layer optimization.

---

## Theme 6: Term Overloading

**Core problem:** Key terms are used with different meanings across docs, creating systematic ambiguity.

**Related findings:**
- Combined P0-6: "'driver' used for two concepts (capability plugin vs host adapter)"
- Intercore P0.2: "drivers overloaded: plugin drivers vs dispatch/sandbox drivers"
- Combined P1-1: "kernel uses OS term 'bead' (leaks policy vocabulary)"
- Clavain P1: "app surfaces and OS sub-agency names conflated"
- Combined P3-3: "add a shared glossary"
- Intercore P2.10: "OS-specific terms appear without definition"

**Coherent fix:** Create a shared glossary referenced by all three docs:

| Term | Meaning | Layer |
|------|---------|-------|
| Companion plugin | inter-* capability module (interflux, interlock, etc.) | OS extension |
| Host adapter | Platform integration (Claude Code plugin interface) | App/OS boundary |
| Work item | Generic kernel record for trackable units | Kernel |
| Bead | Clavain's rendering of a work item | OS |
| Run | Kernel lifecycle primitive | Kernel |
| Sprint | OS-level run template with preset phases | OS |
| Dispatch driver | Agent execution backend (Claude CLI, Codex) | Kernel |

Remove "driver" as a synonym for companion plugin. Use "companion" or "capability module" instead.

---

## Theme 7: interphase Overlap

**Core problem:** interphase is "shipped" as a driver for phase tracking and gates, but Intercore claims ownership of the same primitives. Authority is unclear.

**Related findings:**
- Combined P0-5: "interphase overlaps Intercore's core responsibility"

**Coherent fix:** Add one sentence to both docs: "interphase is a compatibility shim that delegates to `ic` phase/gate primitives. It provides no independent state. New code should call `ic` directly."

---

## Theme 8: Apps Are Not Yet Swappable

**Core problem:** "Apps are swappable" is stated as a global principle, but Gurgeh (arbiter logic), Coldwine (orchestration), and Pollard (scanner pipeline) all embed OS-level intelligence.

**Related findings:**
- Combined P2-3: "apps are swappable asserted globally but Autarch says it's false"
- Combined P1-3: "Autarch contains agency logic"
- Combined P1-4: "Pollard becoming scanner/pipeline component"
- Combined P1-5: "Coldwine/Clavain both orchestrate"
- Autarch P1.1: "claims apps are swappable but multiple sections require app-specific intelligence"

**Coherent fix:** Add a caveat everywhere the claim appears: "Target state: apps are swappable. Current state: Gurgeh, Coldwine, and Pollard embed OS logic that must migrate to Clavain before this holds (see Autarch vision doc, Transitional State)."

---

## Theme 9: ic tui Dependency Inversion

**Core problem:** The kernel proposes shipping `ic tui` built on Autarch's `pkg/tui` library, creating an upward dependency from kernel to app layer.

**Related findings:**
- Combined P1-2: "kernel planning to ship a TUI (apps leaking into kernel)"
- Autarch P0.1: "kernel depends on app layer via pkg/tui"
- Autarch P0.2: "ic tui depends on Autarch WebSocket broker"

**Coherent fix:** Either:
1. Move `pkg/tui` to a neutral shared package (not Autarch-owned)
2. Ship `ic tui` as a separate Autarch tool (`autarch-lite` or `ictui` binary)
3. Keep `ic tui` pull-based only (no broker dependency), built with kernel-owned minimal UI

---

## Theme 10: OS Doc Contains Kernel Implementation Details

**Core problem:** The Clavain vision doc hardcodes kernel CLI commands (`ic events tail -f --consumer=...`), poll intervals, and systemd service definitions. This couples OS vision to kernel internals and Linux-specific deployment.

**Related findings:**
- Clavain P0: "OS vision doc hardcodes kernel CLI commands, poll intervals, systemd"
- Clavain P1: "kernel implementation details leak into OS Architecture section"
- Clavain P1: "current-state inventory counts will rot"

**Coherent fix:** Replace concrete CLI strings with abstract operations:
- "consume event stream via consumer cursor" (not `ic events tail -f --consumer=...`)
- "deploy reactor as a managed service" (not `clavain-reactor.service`)
- "~50 slash commands" (not "52 slash commands, 21 hooks")

---

## Top 5: Do These First

1. **Normalize the stack to 3 layers** (Theme 1) — resolves the most confusion with the smallest edit. Touch all 3 docs, 30 minutes.

2. **Add write-path contracts** (Theme 2) — the single highest-impact architectural clarification. One new section per doc defining who can mutate what. Resolves Themes 2, 3, and 8 partially.

3. **Move policy out of kernel** (Theme 3) — sweep the kernel doc for scoring algorithms, decay rates, revert generation, sprint presets. Move them to Clavain or mark as "OS configures, kernel enforces." This is the largest edit by volume but highly mechanical.

4. **Create shared glossary** (Theme 6) — a single 20-line glossary file referenced by all three docs. Resolves term overloading systemically.

5. **Resolve ic state contradiction** (Theme 4) — choose "promote to public primitive" and add namespacing. Small edit, high conceptual clarity.

These 5 fixes address **28 of the 40+ unique findings** across all 4 reviews. The remaining findings (Themes 5, 7, 8, 9, 10) are important but lower leverage — they can be addressed in a second pass after the core stack definition is solid.
