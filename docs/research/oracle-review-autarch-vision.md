## Review: `infra/intercore/docs/product/autarch-vision.md`

This doc has a clear intent (“Apps render; OS decides; kernel records”), but it repeatedly violates its own 3-layer boundary (and introduces a 4th quasi-layer). The biggest issues are dependency inversion (`ic` depending on Autarch), apps configuring OS policy directly via kernel primitives, and an under-specified/contradictory “signal broker” story.

Below are findings by severity (P0–P3). Each item includes the problematic quote(s), what’s wrong, and what to change.

---

# P0 — Must fix (breaks the 3-layer architecture or key claims)

## P0.1 Kernel depends on the App layer (`ic tui` built on Autarch’s `pkg/tui`)

> “Beyond the four Autarch tools, the shared component library enables a lightweight `ic tui` subcommand — a kernel-native TUI…”
> “This minimal TUI would be built on `pkg/tui` components and call `ic` directly.”

**Problem (layer boundary violation):**

* You explicitly position `pkg/tui` as **Autarch’s** shared library:

  > “Autarch’s shared TUI component library…”
* Then you propose the **kernel** shipping a feature that depends on that app-layer library. That inverts dependencies: kernel must not depend on apps.

**What to change:**

* Pick one:

  1. **Move `pkg/tui` out of Autarch** into a truly shared, lower-layer module (kernel-owned or a neutral shared repo) with explicit API stability guarantees, or
  2. Re-scope `ic tui` as **an Autarch app** (e.g., `autarch ic-tui` or `bigend-lite`), not a kernel-native subcommand, or
  3. Write `ic tui` using a kernel-owned minimal UI package (no dependence on Autarch).

---

## P0.2 `ic tui` is “kernel-native” but depends on an Autarch-side WebSocket broker

> “WebSocket streaming to TUI and web consumers — Bigend’s dashboard and `ic tui` connect via WebSocket rather than polling”

**Problem (contradiction + dependency inversion):**

* Earlier you claim `ic tui` is “always available wherever `ic` is installed”:

  > “It’s the kernel’s own status display — simpler than Bigend but always available wherever `ic` is installed.”
* But a WebSocket broker implies **some server process** must be running. If that server is “Autarch’s signal broker” (app-layer), then `ic tui` is no longer “always available”—it’s coupled to an app service.

**What to change:**

* If you want push: make it a **kernel/OS capability**, not an app-layer broker that kernel tools depend on.

  * Option A: kernel exposes `ic events stream --ws` (or similar), and TUIs connect to kernel directly.
  * Option B: OS (Clavain) runs a control-plane daemon providing push projections; apps connect to OS, not kernel.
* If you want to keep broker app-layer: then **don’t route `ic tui` through it**. Keep `ic tui` pull-based (`ic events tail`) and reserve the broker for Autarch-only experiences.

---

## P0.3 “Drivers (Companion Plugins)” adds an undocumented layer and explicitly bypasses the OS

> “Drivers (Companion Plugins) … Call the kernel directly for shared state — no Clavain bottleneck”

**Problem (boundary violation + architecture drift):**

* Your supposed stack is 3-layer. This introduces a 4th layer (“Drivers”) sitting between Apps and OS, with an explicit goal of bypassing OS (“no Clavain bottleneck”).
* A “driver” that wraps “review, coordination, code mapping, research” is almost certainly **policy-heavy** (OS territory), not a mechanical kernel adapter.

**What to change:**

* Define what “drivers” are *in layer terms*:

  * If they are **kernel adapters** (mechanism): they belong under kernel (or kernel plugin interface) and must be policy-free.
  * If they orchestrate workflows: they are **OS plugins** (Clavain skills/hooks), and apps should call OS.
* Remove “no Clavain bottleneck” language unless you can prove OS is not the policy locus. As written, it undermines your core layering principle.

---

## P0.4 App configures OS policy directly (phase chains, gate rules) via kernel primitives

You define OS responsibility as:

> “Configures the kernel: phase chains, gate rules, dispatch policies”

Then you prescribe app-owned configuration:

> “Spec sprint → `ic run create --phases='["vision","problem","users","features","cujs","requirements","scope","acceptance"]'`”
> “Phase confidence scores → kernel gate evidence (Gurgeh’s confidence thresholds become gate rules)”

**Problem (contradiction + boundary violation):**

* Phase chains and gate rules are explicitly OS policy/config. The migration plan has **Gurgeh** (an app) defining phase chains and effectively defining gating semantics.

**What to change:**

* Replace app-specified chains with OS-defined templates:

  * e.g., `ic run create --chain=prd_sprint_v1` where the chain definition is controlled by Clavain.
* Apps should select among OS-provided workflows, not embed/author them.

---

## P0.5 Coldwine/Clavain orchestration split contradicts “apps render OS decisions”

> “Coldwine provides TUI-driven orchestration while Clavain provides CLI-driven orchestration, both calling the same kernel primitives.”

**Problem (layer boundary violation):**

* “Orchestration” is OS policy/workflow. If both App and OS “orchestrate,” then policy is duplicated and the “apps are swappable” guarantee collapses (same problem you acknowledge for Gurgeh, but this sentence normalizes it as the “resolution”).

**What to change:**

* Make **one orchestrator** (OS). Provide two front-ends:

  * Clavain CLI = one UI surface
  * Coldwine TUI = another UI surface
    Both should issue intents into the OS (or use the same OS workflow engine), not orchestrate independently against kernel primitives.

---

# P1 — High priority (major ambiguity / likely rework)

## P1.1 The doc claims apps are swappable, but multiple sections require app-specific intelligence

You say:

> “Apps render; the OS decides; the kernel records.”
> “When Clavain’s policies change … Autarch’s UIs reflect the change without code modification…”

But your own transitional block concedes:

> “Until that migration, the ‘apps are swappable’ claim is partially false for Gurgeh and Coldwine…”

**Problem:**

* The “swappable” claim is used as a guiding architectural principle, but in practice:

  * Gurgeh’s arbiter
  * Coldwine orchestration
  * Pollard’s scoring/watch behavior
    all embed intelligence that isn’t clearly OS-owned yet.

**What to change:**

* Move the “apps are swappable” claim into a **Target State** section and explicitly label current reality as **Non-compliant** for specific tools (including Pollard, not only Gurgeh/Coldwine).
* Add a boundary table: for each tool, what is App-only vs OS-owned vs Kernel-owned.

---

## P1.2 “Multi-project mission control” vs unclear kernel support for cross-project queries

> “Project discovery → `ic run list` across project databases”

**Problem (completeness + feasibility):**

* `ic` is described as “Go CLI + SQLite” and the kernel is “durable system of record.” Nothing here explains:

  * how many SQLite DBs exist,
  * how a tool enumerates them,
  * whether `ic run list` can span multiple DBs,
  * whether there is a global registry/index.

As written, “across project databases” is hand-wavy and likely not implementable without new kernel capabilities.

**What to change:**

* Specify one concrete approach:

  * A global registry DB (kernel-level) that indexes project DB paths
  * A workspace file format (OS-level) that enumerates projects
  * Or keep filesystem scanning as explicit kernel-agnostic discovery (but then don’t imply kernel provides it)

---

## P1.3 Pollard migration pushes policy into kernel (“kernel confidence scoring with Pollard weights”)

> “Insight scoring → kernel confidence scoring with Pollard’s domain-specific weights”

**Problem (boundary confusion):**

* Confidence scoring, weighting, and thresholds are classic **policy**.
* If the kernel owns scoring, it stops being “mechanism, not policy.”

**What to change:**

* Decide where scoring lives:

  * Kernel: store evidence + raw metrics only (mechanism).
  * OS: compute scoring policies (weights/thresholds), store the resulting decisions back into kernel as artifacts/evidence.
  * Apps: display and allow user interaction, but do not define weights as business logic.

---

## P1.4 Signal broker is under-specified: process model, ownership, and cursor semantics are unclear

Key text:

> “Autarch’s signal broker addresses this with an app-layer real-time projection…”
> “In-process pub/sub fan-out…”
> “WebSocket streaming to TUI and web consumers…”

**Problems (completeness + contradiction):**

* “In-process” vs “WebSocket” implies a server. Where does it run?

  * Per-app instance?
  * A shared daemon?
  * Embedded inside Bigend only?
* Cursor semantics:

  > “consumers fall back to `ic events tail` with their cursor position intact.”
  > But you don’t define cursor format, ordering guarantees, or how a broker maps its stream back to the durable log.
* “blocking for durable consumers (audit trails)” conflicts with “broker is non-durable projection” and suggests misuse.

**What to change:**

* Add a minimal spec:

  * broker deployment model (single daemon vs embedded)
  * subscription protocol and event identity (monotonic event IDs required)
  * reconnect strategy and cursor persistence format
  * security model (authz, local-only, etc.)
  * clear statement: durable consumers must read kernel log, not broker

---

## P1.5 Tool boundaries with OS are described aspirationally, but action flows are not defined

Example:

> “Autarch doesn’t decide which model to route a review to… Those are OS decisions.”

But the doc never defines:

* how an app requests an OS decision (RPC? writing an “intent” record into kernel? calling Clavain CLI?),
* what the OS writes back into kernel for the app to render,
* what happens on conflicts (user wants to override gate?).

**What to change:**

* Define the control-plane contract: “App Intent → OS Decision → Kernel Record → App Render”

  * with at least 2–3 concrete flows (e.g., “advance phase”, “dispatch agent”, “approve gate override”).

---

# P2 — Medium priority (product sense, maintainability, overclaims)

## P2.1 Bigend is “mission control” but also “read-only”; current behavior relies on tmux heuristics

> “Bigend — Multi-project mission control. A read-only aggregator…”
> “Currently discovers projects via filesystem scanning and monitors agents via tmux session heuristics.”

**Product sense issue:**

* “Mission control” implies control actions; “read-only aggregator” implies none. This mismatches expectations.
* tmux scraping is fragile; if it’s explicitly transitional, label it as such (and state what kernel signals replace it).

**Fix:**

* Rename or reframe: “Operations dashboard (read-only)” vs “Mission control (read/write)”.
* Add a target interaction list: what *actions* (if any) Bigend will ever allow.

---

## P2.2 Gurgeh’s confidence scoring reads like policy baked into the app (and uses false precision)

> “confidence scoring (0.0-1.0 across completeness, consistency, specificity, and research axes)”
> “assumption confidence decay”
> “cross-section consistency checking”

**Product sense + boundary:**

* This is high-level but implies a lot of algorithmic policy. If the target is OS-owned quality gates, this section should describe Gurgeh as rendering OS-provided scores, not defining them.
* 0.0–1.0 scoring implies quantitative rigor; without calibration/explanations it risks becoming noise.

**Fix:**

* Make scoring explicitly OS-owned: app displays scores + evidence + gate decision explanation.
* Add one paragraph on how scores are produced, validated, and used (even if only as “heuristics”).

---

## P2.3 Coldwine’s “largest single view at 2200+ lines” is a maintainability red flag

> “Has a full Bubble Tea TUI (the largest single view at 2200+ lines).”

**Issue:**

* The doc unintentionally signals architectural debt in the UI codebase and undermines the `pkg/tui` value proposition.

**Fix:**

* Replace with an intent statement: “Refactor into composable views backed by `pkg/tui` primitives; target max view size X; shared navigation/keymap.”
* If you keep the line-count, frame it as **explicit debt** with a plan.

---

## P2.4 `pkg/tui` portability is asserted, not demonstrated; missing API stability/story

> “Autarch’s shared TUI component library is fully portable and immediately reusable…”
> “They have no Autarch domain coupling.”

**Issue (writing quality + completeness):**

* “Fully portable” and “immediately reusable” are strong claims without support:

  * versioning policy?
  * dependency boundaries?
  * test strategy?
  * keymap conventions?
  * theming/accessibility constraints?
* Also, the earlier `ic tui` section demonstrates actual coupling pressure and risks turning `pkg/tui` into a de-facto platform dependency.

**Fix:**

* Add a short contract:

  * semver + deprecation policy
  * what belongs in `pkg/tui` vs app-specific packages
  * keymap & command system conventions
  * theming rules (and why “Tokyo Night” is default)

---

## P2.5 Naming/terminology and scope creep reduce clarity

Examples:

> “Interverse stack”
> “Drivers (Companion Plugins)”
> “Profiler: Interspect (cross-cutting)”

**Issue:**

* Autarch vision doc includes a “drivers” layer and a profiler component that aren’t otherwise integrated into the rest of the doc. This reads like an excerpted architecture diagram rather than an app-layer vision.

**Fix:**

* Either:

  * remove Drivers/Interspect from this doc, or
  * include a tight “adjacent systems” section explaining why they matter to Autarch surfaces and what integration points exist.

---

# P3 — Low priority (style / phrasing / structure)

## P3.1 Redundant architecture explanations

You explain the 3-layer relationship twice with similar diagrams:

> “Autarch sits above the OS…” (first diagram)
> “Relationship to the Three-Layer Architecture” (second diagram)

**Fix:**

* Keep one canonical diagram + one canonical “contract” section (inputs/outputs per layer).

---

## P3.2 Overconfident absolutes that will be falsified by transitional reality

> “When Clavain’s policies change … reflect the change without code modification…”

Given acknowledged debt, this should be scoped:

* “for workflows fully expressed as OS config + kernel state”

---

# Completeness gaps checklist (explicitly requested areas)

## Four tools

Gaps:

* No explicit **App vs OS vs Kernel** responsibility table per tool.
* No definition of **write paths** (what can each tool mutate? via kernel primitives or OS intents?).
* No explicit “non-goals” per tool (especially Bigend vs Coldwine overlap).

## `pkg/tui`

Gaps:

* API stability/versioning and keymap/command conventions.
* How `pkg/tui` avoids becoming a platform dependency that drags kernel/OS upward.

## Migration plan

Gaps:

* Backward compatibility: what happens while YAML/specs and kernel artifacts coexist?
* Data migration mechanics: mapping YAML spec sections → kernel artifacts (IDs, versioning, linking).
* Ownership of templates (phase chains, bead types): currently implied app-owned, should be OS-owned.

## Signal architecture

Gaps:

* Broker runtime/deployment model (daemon vs embedded)
* Cursor/event identity spec and reconnect behavior
* Security/auth model
* Clear separation between durable event log (kernel) vs projections (broker)

---

# One concrete rewrite suggestion (to resolve most P0/P1 issues)

Add a short “Contracts” section with **three explicit APIs**:

1. **Kernel (Intercore) provides**: primitive commands + durable event log + immutable event IDs.
2. **OS (Clavain) provides**: workflow templates (phase chains, gates), routing decisions, and an “intent” interface (CLI/RPC) that apps call.
3. **Apps (Autarch) provide**: rendering + user input → intents; no workflow definitions; no scoring policy.

Then adjust these parts of the doc accordingly:

* Remove kernel-native `ic tui` dependency on Autarch (`pkg/tui`, broker).
* Replace app-owned `ic run create --phases=[…]` with OS-owned templates.
* Reframe signal broker as OS- or kernel-owned push stream, or constrain it to Autarch-only without involving `ic`.

---

If you want, I can rewrite the doc’s two most problematic sections (“What `pkg/tui` Enables” and “Signal Architecture”) into a layer-compliant version while keeping your intended functionality.
