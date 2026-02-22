# Deep Product and Architecture Review: Autarch Vision Document

**Document reviewed:** `infra/intercore/docs/product/autarch-vision.md` (154 lines, v1.0, 2026-02-19)
**Reviewer:** Flux-drive User & Product Reviewer
**Date:** 2026-02-19
**Supporting docs consulted:**
- `infra/intercore/AGENTS.md` (kernel CLI reference)
- `infra/intercore/internal/db/schema.sql` (actual schema v5)
- `infra/intercore/docs/prds/2026-02-19-intercore-vision-roadmap.md` (epic roadmap)
- `hub/autarch/AGENTS.md` (actual Autarch state)
- `hub/autarch/pkg/tui/` (30 files — actual component inventory)
- `hub/autarch/pkg/contract/types.go` (Initiative/Epic/Story/Task types)
- `hub/autarch/pkg/events/store.go` (separate `~/.autarch/events.db`)
- `hub/autarch/internal/coldwine/` (TUI model.go: 2,219 lines)
- `os/clavain/docs/vision.md` (OS-layer intent)

---

## Summary Verdict

The vision document is coherent and internally consistent as a narrative. Its architecture claims are correct at a high level. The problems are in the execution layer: the migration ordering has two load-bearing dependencies on infrastructure that does not exist yet, the "apps are swappable" claim breaks down for exactly the two tools where it matters most, the `ic tui` proposal inverts the dependency graph without acknowledging it, and the `pkg/tui` component list is incomplete in ways that will cause rework. None of these are fatal to the vision; all require explicit resolution before the migration plan can be committed to.

**Primary user for this change:** A single product-minded engineer (the inner circle described in `os/clavain/docs/vision.md` line 55) who wants observable, reproducible, kernel-backed agent orchestration across four interactive tools.

---

## Issue 1 (P1): Pollard Migration Depends on a Table That Does Not Exist

**Location:** Lines 87–93 ("2. Pollard")
**Evidence:** `infra/intercore/internal/db/schema.sql` contains tables `state`, `sentinels`, `dispatches`, `runs`, `phase_events`, `run_agents`, `run_artifacts`, `dispatch_events`. There is no `discoveries` table.

The vision states that Pollard migration connects hunter results to `ic discovery` events. Lines 87–93 reference `ic discovery search`, `ic discovery` events, and kernel-enforced confidence scoring. The epic roadmap (`docs/prds/2026-02-19-intercore-vision-roadmap.md`) acknowledges this: E5 (Discovery Pipeline, P2) introduces the `discoveries` table, confidence tiers, and `ic discovery scan/submit/search/promote/dismiss`. E5 depends on E2, which depends on E1. The Intercore vision roadmap places E5 at P2, meaning it does not exist even as planned work in E1-E3.

Pollard is listed as migration step 2 (before Gurgeh and Coldwine). If taken literally, Pollard migration cannot proceed until E5 is complete. E5 is not scheduled before E7 (Autarch Migration Phase 1), meaning the migration ordering as written (Bigend → Pollard → Gurgeh → Coldwine) cannot be executed in that sequence without violating the epic dependency chain.

**Concrete failure scenario:** A team attempts Pollard migration after Bigend succeeds. They discover `ic discovery search` does not exist. Pollard's hunters have no kernel surface to emit events to. Either Pollard migration blocks entirely, or it ships with a parallel/fallback path that creates a second source of truth — exactly the condition the migration is trying to eliminate.

**Required resolution:** The migration ordering must either (a) move Pollard to after E5, placing it at migration step 3 or 4 (after Gurgeh), or (b) explicitly scope Pollard's Phase 1 migration to dispatch-tracking only (hunters emit to `ic dispatch`, not `ic discovery`) and defer discovery pipeline integration to Phase 2. The current document presents a single-phase Pollard migration that conflates two distinct migrations.

---

## Issue 2 (P1): `ic tui` Creates an Upward Dependency from Kernel to App Layer

**Location:** Lines 134–142 ("What `pkg/tui` Enables")
**Evidence:** `hub/autarch/pkg/tui/` is a Go package in `github.com/mistakeknot/autarch`. `ic` is a Go binary in `github.com/mistakeknot/intercore` (separate module, separate repo). The epic roadmap E7 acceptance criterion (line 83) states: "pkg/tui components (ShellLayout, ChatPanel) are importable from hub/autarch/pkg/tui."

The kernel (`ic`) is defined as the lowest layer. It has no external dependencies on layers above it — that is the architectural claim that makes it swappable and portable. Building `ic tui` using `pkg/tui` requires the `intercore` Go module to import `github.com/mistakeknot/autarch/pkg/tui`. This is a direct upward dependency: Kernel → App Layer.

The document does not acknowledge this inversion. It presents `ic tui` as a natural extension enabled by `pkg/tui` without noting the module coupling problem. There are three resolution paths, none of which are free:

1. **Extract `pkg/tui` into a third module** — `github.com/mistakeknot/interverse-tui` (or similar). Both `intercore` and `autarch` import it. This preserves layering. Cost: new module, additional maintenance surface, versioning coordination.
2. **Copy the relevant components into `intercore`** — violates DRY, creates divergence risk. Acceptable only if the components are extremely stable.
3. **`ic tui` is a thin binary in the `autarch` repo** — not part of the `ic` binary. Shipped alongside `ic` but built from the app layer. The document's claim that it is "always available wherever `ic` is installed" would then be false.

Path 3 is the most consistent with the stated architecture but requires correcting the document's claim. Path 1 is architecturally cleanest but adds scope.

**The document presents this as settled and simple.** It is neither. This decision shapes the module boundary of the entire kernel, and must be made before E7 work begins.

---

## Issue 3 (P1): "Apps Are Swappable" Breaks for Gurgeh and Coldwine

**Location:** Lines 36–38 ("Apps Are Swappable"), Lines 100–109 ("4. Coldwine")
**Evidence:** `hub/autarch/internal/gurgeh/arbiter/orchestrator.go` (sprint flow state machine), `hub/autarch/internal/coldwine/tui/model.go` (2,219 lines)

The document states at line 40: "Apps render; the OS decides; the kernel records." At line 44: "Apps don't contain agency logic." These are definitional claims that then govern the "swappable" assertion.

The actual Autarch source contradicts this for two of the four tools:

**Gurgeh.** The Arbiter subsystem (`internal/gurgeh/arbiter/`) is a sprint orchestration engine that drives LLM conversations, manages phase sequencing, performs cross-section consistency checking, applies confidence scoring thresholds, triggers targeted Pollard research scans per phase, and decides when to advance the sprint. The document acknowledges at line 101: "Gurgeh's arbiter (the sprint orchestration engine) remains as tool-specific logic." This is not rendering. This is agency. The arbiter makes decisions about what to generate, when to accept, and how to score confidence — decisions the document claims belong to the OS layer.

**Coldwine.** At 2,219 lines, `internal/coldwine/tui/model.go` contains significant orchestration logic including git worktree management, agent coordination state machines, drift detection, and task lifecycle management. Line 109 acknowledges this: "Coldwine provides TUI-driven orchestration." Orchestration is not rendering.

The swappability claim is technically true at a trivial level: you could write a different app that calls `ic dispatch` and `ic run`. But you cannot write a different app that provides the same PRD sprint workflow without reimplementing the Arbiter, which is thousands of lines of domain-specific logic. The Arbiter is not a rendering concern. It would need to live somewhere — either in the OS (Clavain), in the kernel (wrong), or in every app that wants PRD generation.

**The unresolved question this raises:** After Gurgeh migrates to the kernel backend, does the Arbiter move to Clavain (OS layer)? Or does it stay in Gurgeh, making Gurgeh "swappable" only in the sense that a replacement would have to re-implement the same Arbiter logic? The document does not address this. The architectural claim and the actual codebase are currently inconsistent, and the migration plan does not resolve the inconsistency.

---

## Issue 4 (P1): Gurgeh Migration Assumes v4 Portfolio Primitive at P3 Timeline

**Location:** Lines 95–101 ("3. Gurgeh")

Line 99 states: "Spec evolution → run versioning (new run per spec revision, linked via portfolio)."

The `runs` table has no portfolio concept. Linking runs via portfolio is described in E8 (Level 4 — Orchestrate, P3) which includes `ic run create --projects=a,b` for portfolio-level runs and a `project_deps` table. E8 depends on E5 and E7, placing it at minimum 3-4 epics after E7. The roadmap labels E8 as P3 with no timeline, described elsewhere in the Clavain vision as 8-14 months out.

Gurgeh's spec evolution feature is one of its most mature capabilities — it already ships versioned snapshots and structured diffs (`internal/gurgeh/specs/evolution.go`). When Gurgeh migrates to the kernel backend (E9, P3), the spec evolution → run versioning link described in lines 98-99 depends on portfolio primitives that do not exist in the kernel and are not scheduled until E8.

**Concrete failure scenario:** Gurgeh migrates its spec sprint to `ic run create` (E9). Each spec revision creates a new run. The "linked via portfolio" part cannot be implemented because the kernel has no portfolio concept yet. The migration ships with orphaned runs — revisions without relationship structure — and the spec evolution feature that users depend on today regresses.

**Resolution:** The Gurgeh migration description must separate what is achievable at E9 (spec sprint as run lifecycle, phase confidence as gate evidence, artifacts) from what requires E8 (revision linking via portfolio). Either split the migration into phases with explicit portfolio dependency noted, or accept that spec evolution loses its cross-revision linking until E8.

---

## Issue 5 (P2): `pkg/tui` Component List Is Incomplete for Four Sophisticated Tools

**Location:** Lines 63–73 ("Shared Component Library: `pkg/tui`")
**Evidence:** `hub/autarch/pkg/tui/` directory contains 30 files, not 7 components.

The document lists 7 items: ShellLayout, ChatPanel, Composer, CommandPicker, AgentSelector, View interface, Tokyo Night theme.

The actual `pkg/tui/` directory contains (non-exhaustive): `shelllayout.go`, `splitlayout.go`, `sidebar.go`, `chatpanel.go`, `chatstream.go`, `composer.go`, `command_picker.go`, `agent_selector.go`, `diff.go`, `docpanel.go`, `logpane.go`, `loghandler.go`, `help.go`, `keys.go`, `components.go`, `styles.go`, `colors.go`, `view.go`, and multiple test files.

Components missing from the document's list but present in source:

- `SplitLayout` — side-by-side pane layout distinct from ShellLayout
- `Sidebar` — tabbed navigation pane (hosts the 4-tool tabs)
- `DocPanel` — scrollable document viewer (PgUp/PgDn from chat focus)
- `LogPane` + `LogHandler` — live log stream with auto-show/hide
- `DiffPanel` — structured diff viewer used in Coldwine review flows
- `ChatStream` — streaming message renderer (distinct from ChatPanel history display)
- `HelpOverlay` — contextual help display
- `Keys` — cross-component key binding registry

The gap matters for two reasons:

1. The `ic tui` minimal implementation described in lines 138-142 requires at minimum SplitLayout, DocPanel, and LogPane (for the event stream tail view). The listed 7 components are not sufficient to build what lines 138-142 describe.

2. Any team building an alternative app layer (the "swappable" claim) using the documented component list would miss the layout and streaming infrastructure and would discover the gap mid-build.

**Recommendation:** Either document all components accurately, or explicitly scope the list to "components used in `ic tui`" and note that additional components exist for the full tool suite.

---

## Issue 6 (P2): Coldwine's Bead Mapping Crosses the App/OS Boundary Silently

**Location:** Lines 103–109 ("4. Coldwine")

Line 104 states: "Task hierarchy → beads (Coldwine's planning hierarchy maps to bead types and dependencies)."

Beads are managed by the OS layer (Clavain) and companion plugins (interphase). The `pkg/contract/types.go` defines `Initiative → Epic → Story → Task` as Autarch's own types. These are stored in Coldwine's own SQLite. The bead system (Dolt/JSONL in the interphase companion) is a separate system managed by the OS layer.

The mapping "Coldwine tasks → beads" is not a kernel primitive. It is an OS-level integration concern. Beads have their own ID scheme, their own persistence backend, their own priority model. Coldwine writing to beads requires calling into Clavain's OS layer, not into the kernel.

The migration plan presents this as a kernel migration step, but it is actually an OS integration. This means:
- The Coldwine migration (Step 4) is not a single migration — it is two migrations: (a) Coldwine → `ic dispatch` for agent lifecycle, and (b) Coldwine → bead system for planning hierarchy, where (b) is an OS-layer integration not a kernel migration.
- If Autarch is supposed to be the "swappable" app layer that does not depend on OS internals, Coldwine writing to beads creates a direct App → OS dependency.

**The unresolved question:** Does Coldwine's task hierarchy stay in Coldwine's own storage and merely link to beads by reference? Or does Clavain's sprint skill and Coldwine's orchestration share bead state bidirectionally? Line 109 asserts both call the "same kernel primitives" but beads are not kernel primitives — they are OS-layer constructs.

---

## Issue 7 (P2): Bigend Migration Is Achievable Today But the Document Overstates Observability Readiness

**Location:** Lines 79–85 ("1. Bigend")

The document correctly identifies Bigend as the lowest-risk first migration. The kernel does expose `ic run list`, `ic dispatch list --active`, and `ic events tail --all --consumer=bigend`. These are real, working today.

However, line 83 includes "Dashboard metrics → kernel aggregates (runs per state, dispatches per status, token totals)." The kernel does not expose aggregate endpoints. `ic run list` returns individual runs; Bigend would compute aggregates client-side from the list output. This is achievable but it means Bigend's dashboard performance depends on the kernel's list query performance across N projects — each project has its own SQLite database (`auto-discovered by walking up from CWD`).

**Multi-project discovery gap:** Bigend monitors "multi-project mission control" (line 53). The kernel is project-local — each project has `.clavain/intercore.db`. `ic run list` operates on a single database. Bigend currently discovers projects via filesystem scanning and monitors each independently. After migration, Bigend would need to call `ic --db=<path> run list` for each discovered project database independently. This is not a blocking problem, but the migration description implies a unified `ic run list` across projects that does not currently exist. E8 (cross-project event relay, P3) is what would actually unify this.

The document presents Bigend as the validation that "the kernel provides sufficient observability data" (line 85). This is true for single-project observability. Multi-project aggregation requires either client-side fan-out or E8's relay process.

---

## Issue 8 (P2): Autarch's Own Event Spine Is Not Mentioned and Creates a Parallel State Problem

**Location:** Lines 111–131 (architecture diagram), overall document

The document describes the kernel event bus (`ic events tail`) as the integration surface. It does not mention that Autarch already has its own event infrastructure: `pkg/events/store.go` maintains `~/.autarch/events.db` — a global SQLite database with its own schema, cursor tracking, and reconciliation logic.

This is a live parallel event store. When Gurgeh and Coldwine migrate to the kernel backend, what happens to `~/.autarch/events.db`? Options:
- It is deprecated and its consumers (cross-tool signals, Bigend signal aggregation) migrate to the kernel event bus.
- It is retained for cross-tool app-layer signals that the kernel does not emit (Gurgeh confidence signals, Coldwine drift alerts) and the kernel bus handles phase/dispatch events.
- It is retained indefinitely as a parallel system, which is exactly the fragmentation the migration intends to end.

The `pkg/signals/` package emits typed alerts through this event spine — competitor shipped, assumption decayed, execution drifted. These are application-level events with no kernel equivalent. After migration, there will be two event buses: the kernel's (phase transitions, dispatch status) and Autarch's own (application signals). This dual-bus architecture is not discussed in the vision document.

**User-facing impact:** A tool like Bigend reading "all events" post-migration must consume from two buses with different APIs, cursor semantics, and data models. The migration plan does not address how these are reconciled.

---

## Issue 9 (P3): Gurgeh/Coldwine Separation — The Right Cut but Needs Justification

**Location:** Lines 55–59 ("The Four Tools")

The document separates Gurgeh (PRD generation) from Coldwine (task orchestration) without explaining why they are not combined. Users will ask: "I finish a PRD in Gurgeh, then switch to Coldwine to execute it — why not one tool?"

The actual answer is good: Gurgeh and Coldwine operate at different cadences (PRD generation is a bounded 20-40 minute sprint; task orchestration is a continuous, multi-day execution loop). Gurgeh is spec-centric (YAML artifacts, confidence scores, consistency checks); Coldwine is process-centric (git worktrees, agent assignment, drift detection). The handoff protocol between them (Briefs → Tasks) is explicit and documented in `hub/autarch/AGENTS.md`.

The vision document does not articulate this rationale. It lists the tools without explaining the separation principle. For a document whose purpose is to establish Autarch as a coherent application layer, this is an omission that will cause recurring questions. A one-paragraph explanation of the separation rationale would close this.

---

## Issue 10 (P3): Missing Elements — Error Handling, Offline Behavior, Interspect

**Location:** Lines 144–150 ("What Autarch Is Not"), overall document

The document does not address:

**Kernel unavailability.** If `.clavain/intercore.db` is locked, corrupted, or missing, what does each tool display? The document says at line 148: "Everything Autarch does can be done via Clavain CLI or direct `ic` commands." But during migration, each tool's core state lives in the kernel. If the kernel is unavailable, Gurgeh's sprint state is inaccessible, Coldwine's task list is unreadable. Post-migration, the tools have a hard runtime dependency on `ic` that does not exist today (tools have their own SQLite). The migration plan does not address degraded-mode behavior.

**Interspect.** The Clavain vision doc (line 43-46) describes Interspect as reading kernel events and proposing routing improvements. Autarch is the surface where those proposals would be reviewed and accepted. The vision document does not mention how Interspect findings surface in the TUI — whether through Bigend's dashboard, through the kernel event stream, or through a separate overlay. E4 (Interspect kernel integration) is a P2 epic that predates E7 (Autarch Phase 1), meaning Interspect will be emitting kernel events before Autarch migrates to read them. This integration surface is undesigned.

**Driver/companion plugin surface.** Clavain's CLAUDE.md describes 31 companion plugins as "drivers (Layer 3)." The Autarch vision does not describe how companion plugins interact with the TUI tools. For example, `interflux` (review agents) is invoked during Gurgeh's PRD review phase — but where does that interaction surface? Is it in Gurgeh's TUI? In Coldwine? These are not Autarch questions per se, but a vision document for the app layer should note where driver output is rendered.

---

## Actionable Recommendations by Priority

**P0 — Blocking E7 work (resolve before E7 planning begins)**
- Decide where `pkg/tui` lives to support `ic tui`: extract to shared module, copy into intercore, or accept `ic tui` is not in the kernel binary. Document the decision with rationale. The current plan is architecturally inconsistent.

**P1 — Blocking migration planning**
1. Reorder Pollard migration to after E5 (Discovery Pipeline). Document Pollard Phase 1 as dispatch-only integration if ordering must stay for product reasons.
2. Split Gurgeh migration into what is achievable at E9 (run lifecycle, gate evidence, artifacts) versus what requires E8 (portfolio linking). Spec evolution regresses on run linking until E8 is delivered.
3. Decide whether the Gurgeh Arbiter moves to Clavain after migration or stays in Gurgeh. If it stays in Gurgeh, revise the "apps are swappable" claim to be accurate: apps are replaceable in principle, but PRD generation requires reimplementing Arbiter-equivalent logic.
4. Clarify Coldwine's bead mapping: is it a kernel migration or an OS integration? If App → OS dependency, document it as such and note it violates the stated swappability principle.

**P2 — Fix before migration spec is written**
1. Update `pkg/tui` component list to be complete and accurate. The current list is insufficient to build the described `ic tui`.
2. Address the dual-event-bus problem: what happens to `~/.autarch/events.db` when tools migrate to the kernel event bus? This must be decided before E7 or E9 produce conflicting event stores.
3. Correct the multi-project `ic run list` implication in the Bigend migration section: Bigend does per-database fan-out, not a unified kernel view. A unified view requires E8.

**P3 — Before the document is shared more broadly**
1. Add a paragraph explaining the Gurgeh/Coldwine separation rationale. The handoff protocol (Briefs → Tasks) is the key insight.
2. Add a section on kernel unavailability behavior. Even one sentence per tool ("if `ic` is unavailable, Gurgeh falls back to reading `.gurgeh/sprints/` directly") would bound the risk.
3. Note the Interspect TUI surface gap — where do Interspect proposals appear in the Autarch tools?

---

## What the Document Gets Right

For completeness, the following claims in the document are accurate and well-grounded:

- The three-layer architecture (Kernel/OS/Apps) is correctly described and consistent with the existing codebase structure.
- Bigend as the first migration is the correct sequencing decision for risk management. It is genuinely read-only and its current data sources (tmux scraping, filesystem scanning) are the weakest part of the current stack.
- The four tools do form a coherent product arc: Pollard (discover) → Gurgeh (design) → Coldwine (build) → Bigend (observe). This maps cleanly to the Clavain macro-stages.
- `pkg/tui` is genuinely portable. The actual source confirms it has no Autarch domain coupling — the 30 files are pure layout, styling, and interaction primitives. The architectural claim holds, even though the list is incomplete.
- The kernel's current API surface (`ic run`, `ic dispatch`, `ic events`, `ic gate`) is sufficient for Bigend's Phase 1 migration today, given single-project scope.
- The document correctly identifies git worktree management and Intermute integration as staying in Coldwine — these are correctly scoped as non-kernel concerns.
