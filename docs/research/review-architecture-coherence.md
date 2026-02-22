# Architecture Coherence Review: Intercore / Clavain / Autarch Three-Layer Stack

**Reviewer:** fd-architecture-coherence
**Date:** 2026-02-19
**Documents reviewed:**
- `/root/projects/Interverse/infra/intercore/docs/product/intercore-vision.md` (v1.6)
- `/root/projects/Interverse/os/clavain/docs/vision.md`
- `/root/projects/Interverse/infra/intercore/docs/product/autarch-vision.md` (v1.0)

---

## Summary Judgment

The three documents tell a broadly coherent story about a layered autonomous development stack. The kernel/OS boundary is the strongest seam in the design, with clear and consistent ownership on both sides. The OS/apps boundary is the weakest. Several claims of layer independence do not survive scrutiny, and a small number of responsibility gaps and overlaps will cause real integration problems during migration. None of the issues are circular-dependency class; all are fixable within the current architecture model.

---

## Finding 1 — P1: Autarch Independence Claim Is False; Apps Embed OS Logic

**Documents:** autarch-vision.md (section "The Four Tools" and "Migration to Intercore Backend"), clavain-vision.md (section "Architecture")

**What the docs claim:** "Apps render; the OS decides; the kernel records." (autarch-vision.md). Autarch is described as "swappable" and not containing agency logic.

**What is actually described:**

Gurgeh implements an 8-phase spec sprint with per-phase AI generation, confidence scoring across four axes (completeness, consistency, specificity, research), cross-section consistency checking, assumption confidence decay, and spec evolution versioning. The doc says "Gurgeh's arbiter (the sprint orchestration engine) remains as tool-specific logic — it drives the LLM conversation that generates each spec section."

That arbiter is agency logic — it decides how to sequence LLM calls, which prompt generates which section, and when to advance. This is precisely what the OS is supposed to own. The boundary statement ("Apps render OS decisions; they don't make them") is contradicted by the arbiter's described behavior.

Coldwine further embeds an `Initiative → Epic → Story → Task` hierarchy with agent coordination. The doc acknowledges this is deeply coupled to Autarch's domain model. It then says "Coldwine provides TUI-driven orchestration while Clavain provides CLI-driven orchestration, both calling the same kernel primitives." Two components in different layers owning the same logical responsibility (task orchestration) is an overlap, not a separation.

**Concrete failure scenario:** A team builds a web dashboard as an alternative to Autarch. They expect to render kernel state and call `ic` commands. They discover that Gurgeh's PRD-generation workflow and Coldwine's task decomposition live in Autarch-layer code, not in Clavain skills or kernel gates. To replicate the workflow in their web app, they must either duplicate the arbiter logic or depend on Autarch as a library — which breaks the "apps are swappable" guarantee.

**Smallest fix:** The docs should distinguish two Autarch sub-layers: (a) pure rendering components (Bigend reads kernel state, Pollard is a scanner that feeds the discovery pipeline) and (b) workflow components that embed domain logic (Gurgeh's arbiter, Coldwine's orchestration). For (b), document explicitly that the workflow logic is Autarch-internal and the swappability guarantee does not apply to those tools. Alternatively, move the arbiter logic into a Clavain skill (making Gurgeh a thin TUI wrapper over a kernel-driven sprint), which would make the independence claim true but require architectural work.

---

## Finding 2 — P1: Kernel Claims Claude Code Agnosticism but Dispatch Subsystem Assumes Claude Code / Codex on PATH

**Documents:** intercore-vision.md (sections "Process Model", "Dispatch", "Migration Strategy: Hook Cutover")

**What the docs claim:** "Host-agnostic Go CLI + SQLite — works from Claude Code, Codex, bare shell, or any future platform." (intercore-vision.md, Three-Layer Architecture). "If Claude Code disappears, the kernel and all its data survive untouched."

**What is actually described:**

The dispatch subsystem's backend detection reads: "the kernel validates that the requested agent backend (claude, codex) is available on `$PATH` before dispatching." The `DispatchConfig` separates billing path into "subscription-cli vs api." The migration table maps current Clavain hooks to `ic` replacements (including `/tmp/clavain-dispatch-$$.json → ic dispatch status`). The Hook Cutover section says plugins "currently doing state management through temp files... should instead call `ic`."

The kernel is host-agnostic for state and events. It is not host-agnostic for dispatch. The dispatch subsystem has a hard-coded enumeration of agent backends (`claude`, `codex`) — baked into the backend detection logic. A future platform (e.g., a local Ollama runner, a containerized LLM, a hypothetical "Gemini CLI") would require kernel code changes to add backend support.

Additionally, the migration strategy's Hook Cutover section describes all replacement patterns in terms of bash hooks running in Claude Code sessions. The "prerequisite: the `ic` binary must be built and available on `$PATH`" with "the launcher script pattern (already used for MCP servers)" is Claude Code infrastructure.

**Concrete failure scenario:** The host platform shifts from Claude Code to a VS Code extension with a different execution model (not bash hooks, not slash commands, not MCP servers). The kernel's state, events, and gates survive. The dispatch subsystem does not: it looks for `claude` or `codex` on PATH and finds neither. The Hook Cutover migration — the primary path from temp files to kernel state — was designed for Claude Code's hook system specifically. A different host platform must reinvent the migration.

**Distinction:** This is not a fatal problem. The kernel's core value (durable state, gates, events) genuinely is host-agnostic. The dispatch backend assumption is a reasonable scope constraint for v1. The issue is that the vision document overstates the guarantee: "If Claude Code disappears, the kernel and all its data survive untouched" is true for the data; it is false for the dispatch workflow and the hook-based migration path.

**Smallest fix:** Qualify the independence claim. Change "If Claude Code disappears, the kernel and all its data survive untouched" to "If Claude Code disappears, the kernel's state, events, and gates survive untouched. Dispatch would require new backend adapters for the replacement platform." Document that `claude` and `codex` are the v1 backend enumeration, and that adding new backends (e.g., Ollama) requires a new backend adapter — this is a small, well-defined extension point, not a rewrite. This sets accurate expectations without changing the architecture.

---

## Finding 3 — P2: Event Reactor Placement Is Ambiguous — Belongs to OS but Described in Kernel Section

**Documents:** intercore-vision.md (sections "Process Model" and "Events"), clavain-vision.md (section "Architecture" and Track A roadmap)

**What the docs claim:** The kernel has no event loop; it is CLI-only. "No background event loop. The kernel does not poll, watch, or react on its own." (intercore-vision.md, Process Model). Event reaction is OS-level.

**What is actually described:**

The kernel Process Model section introduces the concept: "An OS-level event reactor (e.g., Clavain reacting to `dispatch.completed` by advancing the phase) runs as a long-lived `ic events tail -f --consumer=clavain-reactor` process with `--poll-interval`. This is an OS component, not a kernel daemon."

This is architecturally correct, but the event reactor is described in the kernel vision document, not the Clavain vision document. The Clavain vision's Track A roadmap step A3 mentions "Event-driven advancement — phase transitions trigger automatic agent dispatch and advancement" as a Clavain-owned deliverable, with no description of what runs the reactor or how it is managed.

Neither document describes: which process owns the reactor's lifecycle (who starts it, restarts it on crash, monitors its lag), how the reactor is deployed alongside Clavain's hooks, or what happens if the reactor and a human both try to advance a phase simultaneously (optimistic concurrency resolves this, but neither doc says so in this context).

**Concrete failure scenario:** The reactor is built as part of Track A3. A contributor working from the Clavain vision builds it as a Clavain hook (called at session start, dies at session end). Another contributor, reading the Intercore vision, builds it as a long-lived process launched by a systemd unit. These two implementations have different lifecycle and failure modes but the docs do not resolve which is correct. The ambiguity is architectural, not just documentation.

**Smallest fix:** Add a dedicated section to the Clavain vision describing the event reactor: who owns its process lifecycle (systemd unit vs hook vs session-lived process), what it subscribes to, what actions it takes, and how it composes with human-initiated advancement. Reference this section from the Intercore Process Model section so the Intercore doc does not have to describe OS components.

---

## Finding 4 — P2: Discovery Pipeline Ownership Is Split Across Two Layers Without a Clear Seam

**Documents:** intercore-vision.md (section "Autonomous Research and Backlog Intelligence"), clavain-vision.md (section "Discover" and "Discovery → Backlog Pipeline"), autarch-vision.md (section "Migration to Intercore Backend: Pollard")

**What the docs describe:**

The kernel owns: discovery records, confidence scoring, confidence-tiered action gates, discovery events, backlog events, feedback ingestion, dedup threshold enforcement, staleness decay. (intercore-vision.md)

Clavain (OS) owns: source configuration, scan scheduling, trigger modes, confidence threshold tuning, adaptive thresholds, autonomy policy, backlog refinement rules, interest profile management, feedback loop. (clavain-vision.md, Discovery → Backlog Pipeline)

Autarch/Pollard owns: multi-domain hunters, watch mode, insight synthesis. Migration will connect "hunter results → `ic discovery` events through the kernel event bus" and "insight scoring → kernel confidence scoring with Pollard's domain-specific weights." (autarch-vision.md)

**The seam problem:**

Three layers all claim parts of scoring. The kernel claims "confidence scoring: embedding-based similarity against a learned profile vector, with configurable weight multipliers." Clavain claims "confidence threshold tuning and adaptive thresholds" and "interest profile management." Autarch/Pollard claims "domain-specific weights" for hunter results.

These are not cleanly separated. The "learned profile vector" is stored where? The kernel doc says feedback ingestion updates it. The Clavain doc says Clavain manages the feedback loop. The Autarch doc says Pollard's domain-specific weights feed in. The result is that three documents each describe influence over the same scoring artifact (the profile vector) without stating who writes it, who reads it, and who owns its schema.

Adaptive thresholds are similarly split. The Clavain doc says thresholds shift with the promotion-to-discovery ratio. The kernel doc says "confidence-tiered autonomy gates" are kernel-enforced with configurable thresholds. Neither says who updates the stored threshold values and in what format.

**Concrete failure scenario:** Interspect reads kernel events and proposes OS config changes, including "lower the High threshold from 0.8 to 0.75." That proposal targets which config file? If thresholds are stored in Clavain config (OS-layer), Interspect modifies Clavain config and the kernel reads it at enforcement time. If thresholds are stored in the kernel's state table (as the kernel doc implies for confidence tiers), Interspect must call `ic` to update them. Neither document resolves this. An implementer must make an architectural decision that neither doc has pre-decided.

**Smallest fix:** Add a single table to either the intercore-vision.md or clavain-vision.md (or cross-linked between them) that explicitly maps each discovery-pipeline data artifact to its owning layer: profile vector (stored where, updated how), tier thresholds (stored where, updated how), source trust weights (stored where, updated how). This table forces the ownership question to be answered before implementation begins.

---

## Finding 5 — P2: Interspect's Relationship to Clavain Is Undefined — Profiler Modifies OS Config, But "OS Config" Has No Schema

**Documents:** intercore-vision.md (sections "Kernel / OS / Profiler Model" and "Interspect Migration: Staged to Kernel Events"), clavain-vision.md (section "Architecture" and Track B)

**What the docs claim:** "Interspect reads kernel events and correlates with human corrections. Proposes changes to OS configuration (routing rules, agent prompts)." "Never modifies the kernel — only the OS layer." (intercore-vision.md). The Clavain Track B roadmap shows B3 "Adaptive routing — Interspect outcome data drives model/agent selection."

**The gap:**

"OS configuration" is described in behavior (Interspect proposes changes to routing rules, gate policies, agent prompts) but never in structure. Neither document defines: what file format Clavain's routing table uses, what a "gate policy" looks like as a config artifact, how Interspect's proposals are staged for human review before application, or what the schema of an "overlay" is.

The Interspect migration plan says "Phase 3: Retire Interspect's own SQLite database. Interspect's state becomes a materialized view derived entirely from kernel events." This describes Interspect's read path. The write path — how a proposal becomes an applied config change — has no implementation sketch in any of the three docs.

**Concrete failure scenario:** The self-improvement loop is described as the capstone capability ("evidence-based self-improvement — the system learns from its own history"). When an implementer reaches Track B3, they must decide: does Interspect write a YAML patch file that a human reviews and applies with a CLI command? Does it call a Clavain skill that applies the change? Does it write directly to a kernel state key? None of the three docs answer this. The proposal/apply interface between Interspect and Clavain is the most important seam for the self-improvement story, and it is entirely undescribed.

**Smallest fix:** Add a "Proposal Interface" section to the Clavain vision (or an Interspect sub-section) that defines: the format of Interspect proposals (e.g., a JSON/YAML patch diff against a versioned config schema), how proposals are surfaced for human review (inbox bead, TUI pane, CLI command), and the command/mechanism by which a reviewed proposal is applied. This is not a kernel concern — the kernel records that a proposal was made; the OS decides how to apply it.

---

## Finding 6 — P2: Migration Path for Autarch Backend Migration Risks New Coupling During Transition

**Documents:** autarch-vision.md (section "Migration to Intercore Backend"), intercore-vision.md (section "Apps Layer (Autarch)")

**What the docs describe:**

The migration order is: Bigend (first) → Pollard → Gurgeh → Coldwine (last). Coldwine has the deepest coupling. During migration, each tool runs in a hybrid state: some state in its existing backend (YAML, tool-specific SQLite), some in the kernel.

Gurgeh's confidence scores become kernel gate evidence. Gurgeh's phase progression maps to `ic run create` with a custom phase chain. "Spec evolution → run versioning (new run per spec revision, linked via portfolio)."

**The coupling risk:**

Portfolio runs — described as a v4 future capability in the Intercore horizon table — are required for Gurgeh's spec evolution model (new run per revision, linked via portfolio). Gurgeh's migration plan depends on a kernel capability that is explicitly deferred to v4 (8-14 months). If Gurgeh migrates on the timeline implied (v2-v3), it cannot implement spec evolution linking until the portfolio primitive ships. This leaves a gap: either spec evolution is silently dropped from Gurgeh during migration, or the portfolio primitive must be pulled forward, or Gurgeh must maintain its own revision-linking mechanism during the transition period (adding hybrid coupling, not removing it).

Additionally, Coldwine's `Initiative → Epic → Story → Task` hierarchy maps to "beads (Coldwine's planning hierarchy maps to bead types and dependencies)." But beads are a Clavain-layer concept (backed by the beads system, not the kernel). The kernel does not have a "bead" primitive. This mapping passes through Clavain, creating a Coldwine → Clavain → kernel dependency chain that breaks the stated "Autarch calls `ic` directly" architecture pattern.

**Concrete failure scenario:** A Coldwine contributor following the migration plan calls `ic` to create tasks but discovers the kernel has no task/story/epic concept. They look at the Autarch doc, which says "Task hierarchy → beads." They look for a bead creation API in `ic` and find none — beads are managed by the Clavain plugin layer, not the kernel. The migration plan maps to a concept that belongs to neither the kernel nor a defined kernel extension point.

**Smallest fix for portfolio dependency:** State explicitly in the Gurgeh migration plan that spec evolution linking is deferred until the portfolio primitive ships (v4), and describe the interim representation (e.g., a `parent_run_id` convention in the run goal string, or a manual bead linking the two runs). This sets expectations without blocking the migration.

**Smallest fix for bead mapping:** Clarify in the Coldwine migration plan whether "beads" means Clavain-layer beads (requiring Coldwine to call Clavain, not just `ic`) or a kernel-level task record that does not yet exist (requiring a kernel extension). If the former, document the dependency explicitly. If the latter, spec the kernel extension before writing the migration.

---

## Finding 7 — P2: Clavain's "Not a Claude Code Plugin" Claim Conflicts with Its Described Implementation

**Documents:** clavain-vision.md (section "What Clavain Is Not")

**What the doc claims:** "Not a Claude Code plugin. Clavain runs on its own TUI (Autarch). It dispatches to Claude, Codex, Gemini, GPT-5.2, and other models as execution backends. The Claude Code plugin interface is one driver among several — a UX adapter, not the identity."

**What the docs collectively describe:**

The Clavain CLAUDE.md describes the plugin manifest (`.claude-plugin/plugin.json`), hook files (`session-start.sh`, `session-handoff.sh`, `auto-compound.sh`, etc.), skill files, commands, and agents — all Claude Code plugin constructs. The intercore-vision.md migration section describes replacing temp files in Clavain's bash hooks with `ic` calls, where those hooks are Claude Code hook events (session start, stop, tool use). The Clavain vision's Track A roadmap describes "Hook cutover" as Clavain's primary migration path — hooks that run inside Claude Code sessions.

Autarch is the stated TUI. But Autarch is in earlier migration stages (Bigend is "in-progress TUI," Gurgeh migrates third, Coldwine migrates last). In the current implementation, Clavain is a Claude Code plugin. The vision says it is not. The claim is aspirational, not descriptive.

**Concrete failure scenario:** A new contributor reads "Clavain runs on its own TUI (Autarch)" and "The Claude Code plugin interface is one driver among several — a UX adapter, not the identity." They expect to work with Clavain through Autarch. They find Clavain is a Claude Code plugin with 52 slash commands and 21 hooks running inside Claude Code sessions. Autarch's TUI is either not yet functional or not yet integrated. The vision document describes a target state as if it were the current state, causing a false impression of where implementation stands.

**Smallest fix:** Add a "Current State vs Target State" callout to the Clavain vision's architecture section. The current state is: Clavain is primarily a Claude Code plugin. The target state is: Clavain is a kernel-driven agency experienced through Autarch TUI (or any compatible app layer). This is not architectural criticism — it is an honest description of a system mid-migration. The vision is achievable; it should be labeled as a target.

---

## Finding 8 — P3: The "Permanent Kernel" Claim Does Not Account for the SQLite Schema as an API Surface

**Documents:** intercore-vision.md (sections "Three-Layer Architecture" and "Assumptions and Constraints")

**What the docs claim:** "The kernel is permanent." (intercore-vision.md, Three-Layer Architecture). The Assumptions section acknowledges "API stability" as an open-source obligation and mentions CLI flag backward compatibility.

**What is unstated:**

The kernel's persistence layer is SQLite. The schema is the kernel's implicit API surface — apps and the OS read kernel state by querying tables directly or through `ic` CLI commands. The CLI commands are described as stable. The table schema is not. If an app queries `SELECT * FROM dispatches` directly (bypassing `ic`), it couples to the schema. If the schema evolves, the app breaks.

The Autarch migration section describes Bigend migrating to read kernel state via `ic run list`, `ic dispatch list`, and `ic events tail`. This is CLI-mediated and schema-decoupled — correct. But Autarch's `pkg/tui` Go components could in principle import the intercore package and query the database directly (they share the same Go driver: `modernc.org/sqlite`). Nothing in the docs prohibits this, and the shared Go codebase creates the temptation.

**Concrete failure scenario:** A performance-sensitive Bigend view queries the kernel database directly using the Go API rather than shelling out to `ic`. The v1 query works. A kernel schema migration in v1.5 renames a column. Bigend breaks, not at compile time (no typed schema), but at runtime, with a SQL error. The problem is not immediately traceable to the architecture decision.

**Smallest fix:** Add one sentence to the intercore-vision.md "Assumptions and Constraints" section: "The stable API surface is the `ic` CLI. Direct SQLite queries to the kernel database are not a supported interface and may break across schema versions." This is low effort and prevents a class of future coupling.

---

## Finding 9 — P3: Layer Numbering Is Inconsistent Across Documents

**Documents:** intercore-vision.md (Three-Layer Architecture), clavain-vision.md (Architecture), autarch-vision.md (Relationship to the Three-Layer Architecture)

**The inconsistency:**

The intercore-vision.md numbers layers as: Layer 1 (Kernel), Layer 2 (OS), Layer 3 (Drivers/Plugins). Autarch is labeled as a separate "Apps" tier above Layer 3 (but not given a layer number).

The clavain-vision.md uses the same numbering: Layer 1 (Kernel), Layer 2 (OS), Layer 3 (Drivers). Autarch is listed above Layer 3 as "Apps" without a number.

The autarch-vision.md does not use layer numbers at all. It refers to "the application layer" and describes it as "above the OS" without fitting into the numbered scheme.

This is minor but has a practical consequence: contributors referring to "Layer 3" will mean different things when reading intercore-vision.md (Drivers/Plugins) versus when searching the codebase (some files may use their own numbering or none). The Autarch layer has no canonical number, making it harder to reference in technical discussions.

**Smallest fix:** Assign Autarch the explicit designation "Layer 0" (rendering surface, highest level of abstraction) or "Layer 4" (above drivers), and use it consistently across all three documents. The exact number is less important than consistency.

---

## Gap Analysis: Responsibilities With No Clear Owner

| Responsibility | Gap Description |
|---|---|
| Event reactor lifecycle | Who starts, monitors, and restarts the long-lived reactor process? Kernel says "OS component." Clavain vision says "Track A3." Neither says systemd, hook, or session-scoped. |
| Interspect → Clavain proposal format | How does a proposal become applied config? No doc defines the proposal schema or apply mechanism. |
| Adaptive threshold storage | Who writes updated tier thresholds after Interspect proposes them? Kernel stores them, OS tunes them — but the write path is unspecified. |
| Bead creation from Coldwine | Coldwine maps tasks to beads, but beads are a Clavain-layer concept not a kernel primitive. The migration path crosses a layer boundary with no defined crossing point. |
| `ic tui` TUI ownership | The kernel vision describes an `ic tui` subcommand using `pkg/tui` from Autarch. But `pkg/tui` lives in Autarch (the apps layer). The kernel depending on an apps-layer library inverts the dependency direction. |

---

## Dependency Direction Analysis

| Dependency | Direction | Assessment |
|---|---|---|
| Clavain → Intercore (calls `ic`) | Apps→OS→Kernel | Correct |
| Autarch → Intercore (calls `ic`) | Apps→Kernel (skips OS) | Permitted per design, correct for read-only views |
| Autarch → Clavain (Coldwine maps to beads) | Apps→OS | Correct in direction, but undocumented crossing point |
| Interspect → Intercore (reads events) | Profiler→Kernel | Correct |
| Interspect → Clavain (proposes config) | Profiler→OS | Correct in direction, crossing point undefined |
| Intercore `ic tui` → `pkg/tui` (Autarch) | Kernel→Apps | Inverted — P2 issue (see Finding 8 context) |
| Gurgeh spec evolution → Portfolio primitive | Apps→Kernel (future) | Dependency on v4 feature for v2-v3 migration |

The `ic tui → pkg/tui` dependency warrants dedicated attention. The intercore-vision.md says (v2 milestone): "Minimal `ic tui` subcommand using `pkg/tui` components." If `pkg/tui` lives in the Autarch repository, the kernel repository would need to import an apps-layer library. This inverts the dependency direction. The resolution is either: (a) move `pkg/tui` to a shared library repository independent of Autarch, or (b) the `ic tui` subcommand imports the components inline rather than depending on the Autarch repo. This is not described in any document.

---

## Seam Quality Assessment

| Seam | Quality | Notes |
|---|---|---|
| Kernel / OS (mechanism vs policy) | Strong | Both docs are consistent. The kernel explicitly lists what it does not own, and the OS sections in the Clavain doc map correctly to those exclusions. |
| OS / Drivers (capabilities vs orchestration) | Strong | Drivers calling `ic` directly without a Clavain bottleneck is well-described. The pattern is consistent across all three docs. |
| OS / Apps (agency vs rendering) | Weak | Gurgeh's arbiter and Coldwine's orchestration embed agency logic in the app layer. The seam is stated as clean but is implemented as blurred. |
| Kernel / Apps (direct reads) | Adequate | The pattern of apps calling `ic` CLI is consistent. The risk of direct schema access is unguarded (Finding 8). |
| Profiler / OS (proposals) | Missing | The write path for Interspect proposals has no defined seam. It is the most important seam for the self-improvement story and has no implementation sketch in any document. |

---

## Priority Summary

| Priority | Finding | Core Problem |
|---|---|---|
| P1 | Finding 1 | Autarch independence claim is false; Gurgeh and Coldwine embed OS-level agency logic |
| P1 | Finding 2 | Kernel independence claim is overstated; dispatch subsystem hard-codes claude/codex backends |
| P2 | Finding 3 | Event reactor placement ambiguous; lifecycle ownership undefined |
| P2 | Finding 4 | Discovery pipeline scoring ownership split across three layers without a seam definition |
| P2 | Finding 5 | Interspect → Clavain proposal interface has no defined schema or apply mechanism |
| P2 | Finding 6 | Autarch migration depends on v4 portfolio primitive; Coldwine bead mapping crosses undefined layer boundary |
| P2 | Finding 7 | Clavain "not a Claude Code plugin" claim describes a target state, not current state |
| P3 | Finding 8 | SQLite schema is an implicit API surface; direct access risk unguarded |
| P3 | Finding 9 | Layer numbering inconsistent; Autarch has no canonical layer designation |
