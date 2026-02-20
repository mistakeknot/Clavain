# Oracle (GPT-5.2 Pro) — Combined Review of Three Vision Docs

**Date:** 2026-02-19
**Model:** GPT-5.2 Pro (browser mode)
**Files reviewed:** intercore-vision.md, clavain-vision.md, autarch-vision.md

---

## P0 — Blocking

### P0-1 — The "three-layer" stack is not defined consistently

**Where:**
- intercore-vision.md (section Three-Layer Architecture)
- clavain-vision.md (section Architecture)
- autarch-vision.md (section Relationship to the Three-Layer Architecture)

**Problematic text:**
- intercore-vision.md claims the three layers are Drivers/OS/Kernel:
  "### Three-Layer Architecture … Layer 3: Drivers (Plugins) … Layer 2: OS (Clavain) … Layer 1: Kernel (Intercore) …"
- But the same doc also places Autarch above everything:
  "Autarch (Apps) — interactive TUI surfaces (see Autarch vision doc)"
- clavain-vision.md draws Apps plus "Layer 3":
  "Apps (Autarch) … Layer 3: Drivers … Layer 2: OS (Clavain) … Layer 1: Kernel (Intercore) …"
- autarch-vision.md treats "Apps / Drivers / OS / Kernel" as a four-tier picture while naming it "Three-Layer":
  "## Relationship to the Three-Layer Architecture … Apps (Autarch) … Drivers … OS (Clavain) … Kernel (Intercore) …"

**Why this blocks:**
You can't enforce "each layer stays in its lane" if the lanes aren't the same across docs. Right now:
- sometimes "layer 3" = Drivers,
- sometimes apps are "above layers" but not counted,
- sometimes the overall system is implicitly 4+ tiers (plus Interspect).

**Fix:**
Pick one canonical stack and apply it everywhere. If you truly want the 3-layer system you stated (Intercore/Clavain/Autarch), then Drivers must be reclassified (e.g., "OS extensions" within Clavain, not a distinct layer), and all "Layer 3: Drivers" language should be removed or renamed.

---

### P0-2 — Apps and drivers "call ic directly" without a policy firewall (OS bypass risk)

**Where:**
- intercore-vision.md (Three-Layer Architecture)
- clavain-vision.md (Architecture)
- autarch-vision.md (Relationship to the Three-Layer Architecture; What Autarch Is Not)

**Problematic text:**
- intercore-vision.md: "Plugins call ic directly for shared state — no Clavain bottleneck"
- clavain-vision.md: "Drivers … Call the kernel directly for shared state — no Clavain bottleneck"
- autarch-vision.md: "Autarch (TUI: Bigend, Gurgeh, Coldwine, Pollard) → calls ic"
  and: "Autarch reads and writes kernel state through ic; it doesn't own the system of record."

**Why this blocks:**
If apps and drivers can write to the kernel directly, then OS policy is not enforceable as a boundary. The kernel enforces structural invariants (gates, limits), but not policy/workflow intent (routing rules, "what phases mean", "who is allowed to create/advance runs", etc.). Nothing in these docs defines:
- which ic commands are allowed from apps vs OS,
- how run creation is prevented from becoming "any UI can invent policy,"
- how drivers avoid silently embedding policy ("no Clavain bottleneck" encourages it).

**Fix:**
Define a write-path contract. Examples:
- Apps are read-only to ic (except maybe UX annotations), and must invoke Clavain for actions that imply policy (create run, advance phase, spawn dispatch with routing).
- Drivers may call ic only to emit capability results (artifacts, verdicts, telemetry), but must not create/advance runs or set gate policy.
- Alternatively: kernel-level capability tokens / roles (OS token vs app token) controlling which commands can mutate which tables. If you don't want ACL complexity, go with the "apps call OS for writes" model.

Until that exists, "each layer stays in its lane" is aspirational, not architected.

---

### P0-3 — Kernel state is "kernel-internal only" but migration plans use it as an OS/session store (direct contradiction)

**Where:**
- intercore-vision.md (State; Migration Strategy)

**Problematic text:**
- Kernel ownership claim: "A scoped key-value store with TTL. Used exclusively for kernel-internal coordination data … This is not a general-purpose config store."
- Migration table uses ic state for OS/session semantics:
  "/tmp/intercheck-${SID}.json (accumulator) | ic state set intercheck.count <n> --scope=session"
  and: ".clavain/scratch/handoff-*.md (session state) | ic run + ic state (run state outlives sessions)"

**Why this blocks:**
You are defining state as "kernel-private," then immediately making it an OS feature dependency. That forces the kernel to support OS semantics (stability, debugging UX, tooling, migration guarantees) that your text explicitly rejects.

**Fix:**
Choose one:
1. Promote state to a supported public primitive (rename internal keys under a reserved namespace like `_kernel/*`), OR
2. Keep state private and introduce an explicit OS-owned persistence surface (e.g., `ic session`, `ic note`, `ic scratch`) with different guarantees.

---

### P0-4 — Time-based backlog decay is specified as kernel behavior, but the kernel is explicitly "no daemon" (execution model gap)

**Where:**
- intercore-vision.md (Process Model; Backlog Refinement Primitives)
- clavain-vision.md (Backlog refinement rules)

**Problematic text:**
- Kernel is not a daemon: "Intercore is a CLI binary, not a daemon… There is no long-running server process."
- Yet kernel is described as performing time-based decay: "Discovery records… decay in priority over time (configurable rate, default: one priority level per 30 days…)"
- OS doc repeats it as kernel behavior: "Staleness decay — kernel decays priority on inactive beads…"

**Why this blocks:**
Either:
- something periodically runs (OS timer/cron/reactor), or
- decay is computed lazily (virtual priority), or
- the kernel becomes a service.

None of that is spelled out, so this is currently unimplementable as written.

**Fix:**
Specify one mechanism and cross-reference it in both docs:
- "OS runs `ic backlog decay --now=<ts>` daily" (writes events), or
- "Priority decay is computed at query time; no mutation; last-activity timestamps drive effective priority."

---

### P0-5 — "interphase" overlaps Intercore's core responsibility (authority confusion)

**Where:**
- clavain-vision.md (Drivers table)
- intercore-vision.md (Core Idea / ownership)

**Problematic text:**
- clavain-vision.md: "interphase | Phase tracking and gates are generalizable | Shipped"
- intercore-vision.md: "Intercore … provides the primitives — runs, phases, gates …"

**Why this blocks:**
External readers (and future you) won't know which module is authoritative for phases/gates. If interphase exists as "shipped," why is Intercore needed (or vice versa)?

**Fix:**
Add a single sentence in both docs clarifying:
- interphase is legacy and superseded by Intercore, or
- interphase becomes a compatibility shim that calls ic and provides no independent state.

---

### P0-6 — "Driver" is used for two different concepts (capability plugin vs host UX adapter)

**Where:**
- intercore-vision.md (Companion Plugins (Drivers); Layer 3: Drivers)
- clavain-vision.md (What Clavain Is Not)

**Problematic text:**
- Capability drivers: "Companion Plugins (Drivers) … interflux, interlock, interject…"
- Host/UX adapter also called a driver: "The Claude Code plugin interface is one driver among several — a UX adapter, not the identity."

**Why this blocks:**
When you say "drivers call the kernel directly," it's ambiguous whether you mean:
- inter-* capability plugins, or
- host platform adapters (Claude Code integration).

This ambiguity undermines every boundary statement.

**Fix:**
Rename one category globally:
- Capability plugins (or "companions") vs host adapters (or "frontends").

---

## P1 — Layer Violations

### P1-1 — Kernel doc uses OS-level term "bead" (leaks policy vocabulary into mechanism layer)

**Where:**
- intercore-vision.md (Dependency Graph Awareness; Migration Strategy table)

**Problematic text:**
- Kernel describes OS action in OS vocabulary: "The OS consumes this event and creates a 'verify downstream' bead…"
- Migration table is saturated with Clavain-specific artifacts: "/tmp/clavain-bead-${SID}.json (phase sideband) | ic run phase <id>"

**Why it's a lane violation:**
Kernel docs should speak in kernel nouns ("backlog item", "work item", "record"), not OS UI nouns ("bead").

**Fix:**
Replace "bead" with a kernel-generic term everywhere in Intercore, and explicitly say: "Clavain renders backlog items as beads."

---

### P1-2 — Kernel is planning to ship a TUI (ic tui) (apps leaking into kernel lane)

**Where:**
- intercore-vision.md (Success at Each Horizon)
- autarch-vision.md (What pkg/tui Enables)

**Problematic text:**
- Kernel roadmap: "Minimal **ic tui** subcommand using pkg/tui components."
- Autarch reinforces "kernel-native TUI": "a lightweight **ic tui** subcommand — a kernel-native TUI…"

**Why it's a lane violation:**
A TUI is an application surface. If Intercore is the kernel, shipping UI inside ic blurs the boundary and creates coupling (pkg/tui dependency, UI concerns in kernel release cadence).

**Fix:**
Make it a separate binary/package (ictui or an Autarch tool) that depends on Intercore, not embedded in the kernel CLI.

---

### P1-3 — Autarch admits it contains "agency logic" (apps violating the "render only" rule)

**Where:**
- autarch-vision.md (Migration to Intercore Backend; Transitional state note)

**Problematic text:**
"Gurgeh's arbiter … remains as tool-specific logic … The arbiter is agency logic … In the target architecture, this intelligence migrates to the OS layer (Clavain)…"

**Why it's a lane violation:**
This is explicitly OS policy/workflow logic sitting inside an app. You do call it "architectural debt," which is good, but it's still a boundary violation relative to the target.

**Fix:**
Add:
- a tracked milestone ("Gurgeh arbiter extraction to Clavain by vX"), and
- a crisp interim rule ("until extracted, Gurgeh is not considered swappable / not considered pure app layer").

Also: Clavain + Intercore docs should cross-reference this caveat when claiming "Apps are swappable" (see P2-3).

---

### P1-4 — Pollard is described as becoming a scanning/pipeline component (OS function) while remaining an "app"

**Where:**
- autarch-vision.md (Migration to Intercore Backend)

**Problematic text:**
"Pollard becomes the scanner component that feeds the discovery → backlog pipeline… Its hunters become Intercore source adapters."

**Why it's a lane violation:**
A scanner that schedules, triggers, and feeds the discovery pipeline is OS workflow execution, not merely a UI surface.

**Fix:**
Either:
- reclassify Pollard's "hunters" as a driver/service (headless capability) and keep Pollard-the-app as a UI on top, or
- say explicitly Pollard is temporarily "app + driver" split during migration.

---

### P1-5 — Coldwine/Clavain both "orchestrate" (policy split across OS and app)

**Where:**
- autarch-vision.md (Migration to Intercore Backend)

**Problematic text:**
"The resolution is that Coldwine provides TUI-driven orchestration while Clavain provides CLI-driven orchestration, both calling the same kernel primitives."

**Why it's a lane violation:**
Orchestration is OS territory. Having two orchestrators (one app, one OS) is a policy fork unless you define a single policy authority and treat the other as a thin client.

**Fix:**
Define: Coldwine issues intent requests to Clavain (OS), and Clavain performs orchestration and writes to ic. Coldwine reads and renders results.

---

### P1-6 — Intercore's discovery scoring description slips from "primitive" into "policy"

**Where:**
- intercore-vision.md (Autonomous Research and Backlog Intelligence)

**Problematic text:**
"Confidence scoring — Embedding-based similarity against a learned profile vector, with configurable weight multipliers for source trust, keyword matches, recency, and capability gaps"

**Why it's a lane violation:**
The more you specify how to score (weights, recency multipliers, "capability gaps"), the more this becomes an opinionated product policy. The kernel should accept a score + evidence and enforce tier boundaries, not define the scoring model.

**Fix:**
Move scoring algorithm details to Clavain (policy) and keep Intercore's role to:
- store scores/evidence,
- enforce tier transitions,
- emit events.

---

## P2 — Inconsistencies

### P2-1 — "OS doesn't need to poll" vs polling-based reality (terminology drift)

**Where:**
- intercore-vision.md (Observable by Default; Process Model)
- clavain-vision.md (Event Reactor Lifecycle)

**Problematic text:**
- Kernel doc: "This means the OS doesn't need to poll for changes. It subscribes to kernel events and reacts."
- But also kernel doc: "Event consumption is pull-based: consumers call ic events tail --consumer=<name>…"
- OS doc makes polling explicit: "polls the kernel event bus: ic events tail -f --consumer=clavain-reactor --poll-interval=500ms"

**Issue:**
Not fatal, but it reads like a contradiction. You mean "don't poll state tables," but the text says "don't poll" broadly.

**Fix:**
Replace "doesn't need to poll" with "doesn't need to poll state tables; it tails the event log."

---

### P2-2 — Link paths are inconsistent across docs (cross-reference fragility)

**Where:**
- intercore-vision.md references: "see the Clavain vision doc" and "see the Autarch vision doc"
- clavain-vision.md references: "see the Autarch vision doc" and "Intercore vision doc … (../../../infra/intercore/docs/product/intercore-vision.md)"
- autarch-vision.md references: "see Clavain vision doc"

**Issue:**
These cannot all be correct simultaneously unless the repo layout is extremely specific. Broken cross-links undermine the "coherent architecture" reading experience.

**Fix:**
Use repo-root absolute links (or a consistent docs root) and standardize across all three docs.

---

### P2-3 — "Apps are swappable" is asserted globally, but Autarch says it's currently false for key tools

**Where:**
- clavain-vision.md (Architecture)
- autarch-vision.md (Apps Are Swappable; Transitional state note)

**Problematic text:**
- Clavain says: "Apps are swappable — Autarch is one set of apps, not the only possible set"
- Autarch qualifies: "Until that migration, the 'apps are swappable' claim is partially false for Gurgeh and Coldwine…"

**Issue:**
Not a conceptual contradiction (you acknowledge debt), but it is a cross-doc mismatch because the OS and kernel docs repeat the claim without the caveat.

**Fix:**
Add a one-line caveat in Clavain + Intercore that links to Autarch's "Transitional state" section.

---

### P2-4 — Versioning language is confusing ("planned for v3" but "current schema (v5)")

**Where:**
- intercore-vision.md (Horizon note under discovery tiers)

**Problematic text:**
"The discovery subsystem is planned for v3… do not exist in the current kernel schema (v5)."

**Issue:**
"v3" and "v5" appear to refer to different version axes (product horizon vs schema version), but that's not stated. Readers will assume inconsistency.

**Fix:**
Rename explicitly (e.g., "product horizon v3" vs "schema revision 5") or add one clarifying sentence.

---

### P2-5 — "Interverse monorepo" but "each with its own git repository" (self-contradictory wording)

**Where:**
- intercore-vision.md (Multi-Project Coordination intro)

**Problematic text:**
"The Interverse monorepo contains 25+ modules, each with its own git repository."

**Issue:**
A monorepo is typically one git repository. If you mean "workspace of many repos," the noun is wrong.

**Fix:**
Rename to "workspace," "meta-repo," or "multi-repo constellation."

---

## P3 — Polish

### P3-1 — Overuse of "real magic" / metaphor language reduces precision

**Where:**
- intercore-vision.md (Three-Layer Architecture)
- clavain-vision.md (Architecture / guiding principle)

**Problematic text:**
- "The 'real magic' lives here: everything that matters is in ic"
- "Clavain is the car; Intercore is the engine."

**Issue:**
These are fine rhetorically, but they dilute boundary enforcement language. Architecture docs benefit from declarative contracts over persuasion.

**Fix:**
Replace with explicit invariants ("system of record is X; policy authority is Y; apps are read-only") and keep metaphors to a single short paragraph if desired.

---

### P3-2 — "Clavain runs on its own TUI (Autarch)" is misleading phrasing

**Where:**
- clavain-vision.md (What Clavain Is)

**Problematic text:**
"Clavain runs on its own TUI (Autarch)…"

**Issue:**
It implies Autarch is required infrastructure for Clavain, contradicting the broader "apps are swappable / not required" stance.

**Fix:**
Use: "Clavain is experienced through Autarch" or "Autarch is a primary UI for Clavain."

---

### P3-3 — Add a shared glossary (terminology mismatch friction)

**Where:** All three docs

**Symptoms:**
- "bead" vs "backlog item"
- "driver" (capability plugin) vs "driver" (host adapter)
- "sprint" vs "run"
- "macro-stage" vs "phase"

**Fix:**
One shared glossary section (even 12–20 lines) referenced by all three docs.

---

## Highest-Leverage Repairs

1. **Normalize the stack definition** across all docs (your stated 3 layers) and explicitly place "Drivers" (either OS extensions or a separate 4th tier, but be consistent).
2. **Define the write boundary**: which layer(s) may mutate kernel state, and how apps/drivers route intent through OS policy.
3. **Resolve the `ic state` contradiction** (kernel-private vs OS dependency).
4. **Clarify ownership of phases/gates vs interphase** (merge/deprecate/shim).
5. **Deconflict the term "driver"**.
