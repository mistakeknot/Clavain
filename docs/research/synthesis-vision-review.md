# Vision Document Review — Synthesis

**Reviewed:** 2026-02-19
**Documents:** intercore-vision.md (v1.6), clavain/docs/vision.md, autarch-vision.md (v1.0)
**Agents:** 6 (fd-layer-boundary, fd-cross-reference, fd-architecture-coherence, fd-autonomy-design, fd-kernel-contract, fd-orchestration-routing)

---

## Verdict: NEEDS_WORK

The three documents describe a coherent and architecturally sound vision. The kernel/OS/profiler separation is the strongest design decision and is consistently stated across all three. However, the review uncovered **4 P0 findings** (two false-enforcement claims in the kernel vision, one self-improvement safety gap, and one P0-severity broken invariant), **11 P1 findings**, and significant gaps between claimed and implemented behavior. The P0s all block either Level 2 deployment or open-source credibility. They are fixable — none require architectural rework — but the documents must not be published or used as implementation targets in their current form.

---

## P0 Findings (4)

### P0-1: Transactional Dual-Write is Broken for Dispatch Events

- **Agents:** fd-kernel-contract
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — "Transactional Dual-Write" section; implementation in `internal/dispatch/dispatch.go` and event bus architecture
- **Issue:** The vision claims "State table mutations and their corresponding events are written in the same SQLite transaction. There is no window where a table reflects a new state but the event log doesn't." This guarantee holds for phase events but is explicitly broken for dispatch events. The event bus architecture fires DispatchEventRecorder callbacks after `UpdateStatus()` commits — AGENTS.md confirms: "Callbacks fire after DB commit (fire-and-forget)." A process killed between the dispatch status commit and the event append leaves the database showing `status=completed` with no `dispatch.completed` event in the log.
- **Failure scenario:** The OS event reactor (Level 2 autonomy) is waiting for `dispatch.completed` to advance the phase. The process is OOM-killed after UpdateStatus commits but before the event fires. The run stalls permanently — the database says "completed," the event bus has no record, the event reactor never receives the trigger. Manual reconciliation required.
- **Fix:** Move the `dispatch_events` INSERT inside the `UpdateStatus` transaction, before returning to the callback infrastructure. The callback/Notifier layer handles non-durable fan-out (in-process, UI, hooks) but the DB event record must be committed atomically with the status change. This is straightforward given `SetMaxOpenConns(1)`.

---

### P0-2: Spawn Limits Described as Kernel-Enforced — Not Implemented

- **Agents:** fd-orchestration-routing (primary), corroborated by fd-kernel-contract ("Spawn limits: Unverified — may be planned v2 rather than current")
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — "Resource Management" section; `internal/dispatch/spawn.go`, `cmd/ic/dispatch.go`
- **Issue:** The vision states: "Hard limits on agent proliferation: Maximum spawn depth... Maximum children per dispatch (fan-out limit)... Maximum total agents per run. These are kernel-enforced invariants, not suggestions. An agent cannot bypass them regardless of what the LLM requests." Inspection of `spawn.go` and `cmd/ic/dispatch.go` shows `Spawn()` inserts a record and starts a process with no pre-spawn check against any concurrency limit. `cmdDispatchSpawn()` calls `dispatch.Spawn()` directly — no `ListActive()` call, no count comparison, no enforcement path. `ParentID` is stored for lineage tracking but depth is never traversed or bounded.
- **Failure scenario:** An OS hook misconfigured to fan out per-file on a 200-file diff creates 200 concurrent agent processes. The kernel records all of them. Nothing stops the spawn. The budget checker fires post-completion, which is too late to prevent the resource spike. The "kernel-enforced" guarantee is entirely absent from the implementation.
- **Fix:** Add `CountActive(ctx, scopeID)` to the dispatch store. Add a `SpawnLimits` struct (max_concurrent_per_run, max_depth, max_total) that `Spawn()` enforces before record creation. Add depth-traversal of `parent_id` chains. Reject with a structured error (`ErrSpawnLimitExceeded`) recorded as a rejected spawn event. In the vision doc, segregate enforcement claims by availability horizon (current vs planned).

---

### P0-3: Discovery Confidence-Tier Enforcement Is an Assertion Without a Mechanism

- **Agents:** fd-kernel-contract (primary), corroborated by fd-layer-boundary (P0-1: kernel doc prescribes OS autonomy policy as kernel-enforced invariant) and fd-orchestration-routing (implicitly — spawn limits parallel)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — "Confidence-Tiered Autonomy" section, "Enforces vs Records" table
- **Issue:** The vision states: "This is a kernel-enforced gate, not a prompt suggestion... An OS-layer component cannot auto-create a bead for a discovery scored at 0.4 — the kernel will reject the promotion." The current kernel schema (as listed in AGENTS.md) has no `discoveries` table. The vision's own "What already exists" section acknowledges "kernel integration is missing — discovery events through the event bus, event-driven scan triggers, kernel-enforced confidence tiers." The enforcement claim appears in the invariants section as if it is a current guarantee; it is a v3 planned feature. Additionally, the same section prescribes OS-layer workflow actions ("Create bead (P3 default)", "write briefing doc", "Appears in inbox") within a kernel doc — these are Clavain vocabulary, not kernel primitives (fd-layer-boundary P0-1).
- **Failure scenario:** OS code integrating with the kernel today calls `ic [discovery-promote]`. The kernel has no such enforcement and either returns "unknown command" or succeeds without any tier check. A bead is created for a 0.4-confidence discovery with no audit trail and no block. Interject integration built on this guarantee operates on a false foundation.
- **Fix:** The "Enforces vs Records" table must add a column indicating current vs planned horizon. The invariants section must be rewritten to describe only what v1 enforces. Remove the "Autonomous Action" and "Human Action Required" columns from the kernel's tier table (OS workflow policy does not belong in a kernel doc); replace with a pointer to the Clavain vision doc for the policy definition.

---

### P0-4: Self-Improvement Loop Has No Designed Safeguard Against Reward Hacking

- **Agents:** fd-autonomy-design (primary)
- **Location:** `hub/clavain/docs/vision.md` — self-improvement section; `infra/intercore/docs/product/intercore-vision.md` — Interspect integration
- **Issue:** The Clavain vision lists "Self-improvement feedback loops — how to prevent reward hacking ('skip reviews because it speeds runs')?" as a research question. Acknowledging a threat as a research question is not the same as designing against it. Interspect's objective optimizes outcomes-per-token. A run that skips review completes faster and costs fewer tokens. If review agents surface findings that delay the sprint, Interspect could correctly learn that review is a "bottleneck" and propose downweighting review agents or softening review gates. The only stated safeguard is "the human reviews proposals and maintains veto power" — which assumes (a) the human can detect which proposals are reward hacking vs genuine insight, (b) proposals include enough context for judgment, and (c) proposal volume does not exceed the human's review capacity. None of these are designed for.
- **Failure scenario:** Interspect accumulates data showing `fd-safety` often produces findings that delay sprint advancement (because they catch real problems requiring rework). Interspect proposes excluding `fd-safety` from future sprints, citing a high correction rate. The proposal looks identical to a correct proposal to exclude `fd-game-design` from a Go backend project — both propose excluding an agent, both cite evidence. The human accepts the proposal. Safety review is disabled. Future sprints ship with unreviewed safety properties.
- **Fix:** (a) Proposals to exclude or downweight `fd-safety`, `fd-security`, `fd-correctness` must require explicit out-of-band human override, not just proposal accept — these agents are not excludable through normal Interspect flow. (b) Each proposal must include a quality impact estimate: "In the last 20 runs, this agent's findings were acted on N times." (c) A maximum proposal batch size per session (suggest 3) to prevent overload. (d) Canary alert thresholds must be defined quantitatively (e.g., "if run rollback rate increases >X% in the 14-day window"). (e) Proposals must never auto-apply on TTL expiry.

---

## P1 Findings (11)

### P1-1: Event Reactor Lifecycle Is Undefined — Silent Workflow Stall

- **Agents:** fd-autonomy-design (L2-A), fd-architecture-coherence (Finding 3), fd-layer-boundary (P1-2)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — Process Model section; `hub/clavain/docs/vision.md` — Track A roadmap
- **Issue:** At Level 2 autonomy, the OS event reactor drives phase transitions automatically. The vision describes it as "a long-lived `ic events tail -f --consumer=clavain-reactor` process with `--poll-interval`" and correctly labels it "an OS component, not a kernel daemon" — but then describes its internal architecture in the kernel doc. Neither document specifies who starts the reactor, who restarts it on crash, or what a downed reactor looks like to a human. The Clavain vision's Track A3 mentions "event-driven advancement" as a deliverable with no implementation description.
- **Failure scenario:** The reactor is implemented as a Clavain hook (dies at session end). Dispatches complete overnight; the run is stuck. A human opens the TUI to see a run with all dispatches completed and no phase advancement. There is no "reactor not running" signal, no stall timeout, no manual recovery command documented.
- **Fix:** Add a dedicated section to the Clavain vision: reactor lifecycle (systemd unit vs hook vs session-scoped process), subscription contract, behavior on gate failure, and manual recovery path (`ic run advance <id>` to step in). Reference this section from the Intercore Process Model section and remove the OS reactor architecture from the kernel doc.

---

### P1-2: Gate Failure in Automatic Reactor Chain Has No Escalation Path

- **Agents:** fd-autonomy-design (L2-C), corroborated by fd-orchestration-routing (fan-out failure semantics)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — Gates section; `hub/clavain/docs/vision.md` — autonomy model
- **Issue:** At Level 2, the event reactor chain can produce a gate failure (all dispatches complete, gate condition not met). The vision's human-above-the-loop model says "the human observes and intervenes only on exceptions" — but the mechanism for surfacing exceptions to human attention when the reactor chain fails is not specified. The TUI tails events, but a gate failure in an unmonitored run produces a stalled workflow with no active notification.
- **Failure scenario:** Seven review agents complete; gate evaluation fails because `verdict_exists` is not met (all verdicts were rejected). The reactor receives `gate.failed`. No run state transition to `paused`. No inbox notification. The run appears stuck with no indication of why or what action is needed.
- **Fix:** On `gate.failed` from an automatic advancement attempt, the reactor must pause the run (`run.paused` state), emit a `run.paused` event with the gate failure evidence, and surface this in Bigend/TUI as requiring human action.

---

### P1-3: Stalled Dispatch Permanently Blocks `agents_complete` Gate

- **Agents:** fd-autonomy-design (AL-A), corroborated by fd-kernel-contract (reconciliation pattern analysis)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — Dispatch section, reconciliation primitives
- **Issue:** A dispatch process killed without self-reporting (`kill -9`, OOM, container eviction) remains in `running` state. The `agents_complete` gate checks whether all dispatches are in a completed state — it does not distinguish "running" from "running but dead." The reconciliation engine emits `reconciliation.anomaly` events but does not auto-resolve. The gate is permanently blocked until a human runs `ic dispatch reconcile` and explicitly resolves the orphaned dispatch.
- **Failure scenario:** One of seven review agents is OOM-killed mid-execution. It never reports a terminal state. The `agents_complete` gate never passes. The run is stuck indefinitely. The human must notice the stalled run, investigate which dispatch is orphaned, and manually reconcile.
- **Fix:** The `agents_complete` gate must accept "confirmed dead by reconciliation" dispatches as terminal. Define the reconciliation polling interval. Add a `stalled` dispatch state (or automatically transition orphaned dispatches to `failed` after the reconciliation age window). The gate check should be: all dispatches in terminal states OR confirmed dead by reconciliation.

---

### P1-4: High-Confidence Bead Auto-Creation Is Action-Before-Notification

- **Agents:** fd-autonomy-design (HITL-A, L-1-A)
- **Location:** `hub/clavain/docs/vision.md` — Discovery → Backlog Pipeline, confidence-tiered autonomy
- **Issue:** At confidence >= 0.8, the system auto-creates a bead and then sends a notification. The "human above the loop" framing requires human position to be anterior to the action, not posterior. In a well-managed backlog, bead creation has downstream effects (sprint targeting, estimation, reporting). The rollback primitive exists but its cost is non-trivial. The current flow is "create then notify" — effectively "human below a one-way action."
- **Failure scenario:** A discovery is scored at 0.82 based on an uncalibrated embedding model. A bead is auto-created. The human receives the notification 30 seconds later, finds the bead is irrelevant, and dismisses it. The bead was already created in `active` state, may have been seen by other agents, and must now be explicitly closed.
- **Fix:** Create the bead in `proposed` state. Send the inbox notification. Auto-promote to `active` only after N minutes (configurable, suggest 15) without human dismissal. This preserves asynchronous human control without requiring synchronous approval.

---

### P1-5: Level 2 Auto-Advancement Does Not Distinguish "Completed" from "Completed Well"

- **Agents:** fd-autonomy-design (HITL-B)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — Gates, dispatch completion; `hub/clavain/docs/vision.md` — Level 2 autonomy
- **Issue:** The `agents_complete` gate fires when all dispatches reach a terminal state. It does not check verdict quality. A dispatch that completes with a `failed` or `rejected` verdict satisfies the gate if `agents_complete` is the only gate condition. Auto-advancement from execution phases (execute, test) can proceed past bad dispatch outputs.
- **Failure scenario:** A code-execution dispatch completes successfully (it ran to completion) but produced a `rejected` verdict (the code review agent found a critical bug). `agents_complete` fires. `HasVerdict()` returns true (one non-rejected verdict from a different agent). The run advances to Ship with unreviewed critical findings.
- **Fix:** Auto-advancement from execution phases must require a `verdict_exists` gate with a minimum verdict quality signal, not just `agents_complete`. "Dispatches finished" is not the same as "dispatches finished acceptably." Gate failures on quality signal should surface as requiring human decision.

---

### P1-6: Durable Consumer Cursors Have a 24h TTL, Contradicting "Never Expire"

- **Agents:** fd-kernel-contract (F4), corroborated by fd-orchestration-routing (Finding 10)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — Consumer cursors section; AGENTS.md — Dual Cursors
- **Issue:** The vision states: "Durable consumers' cursors never expire." AGENTS.md confirms cursors are stored in the `state` table with a 24h TTL for auto-cleanup. A durable consumer offline for 25+ hours silently loses its cursor. When it resumes, it cannot know it lost events. The `ic events cursor register --durable` command does not appear in the AGENTS.md CLI table — the implementation may not yet exist.
- **Failure scenario:** Server maintenance window of 30 hours. Interspect's cursor expires. It resumes from the oldest retained event (or from now). Hundreds of `dispatch.completed` and `phase.advanced` events from the outage are missed. Interspect's self-improvement model is trained on biased, incomplete data. Routing proposals are incorrect.
- **Fix:** Durable consumer cursors must be stored in a dedicated table without TTL. Implement `ic events cursor register --durable` as a distinct CLI command. The state table is inappropriate as a backing store for durability guarantees.

---

### P1-7: Autarch Independence Claim Is False — Apps Embed OS Agency Logic

- **Agents:** fd-architecture-coherence (Finding 1), fd-layer-boundary (P1-3), fd-autonomy-design (implicit)
- **Location:** `infra/intercore/docs/product/autarch-vision.md` — "The Four Tools" section; `hub/clavain/docs/vision.md` — Architecture
- **Issue:** The autarch-vision.md states "Apps render; the OS decides; the kernel records" and describes Autarch as "swappable." Gurgeh's "arbiter (the sprint orchestration engine) remains as tool-specific logic — it drives the LLM conversation that generates each spec section." This is agency logic: deciding how to sequence LLM calls, which prompts generate which sections, when to advance. Coldwine "provides TUI-driven orchestration" — orchestration policy (sequence, conditions, dispatch decisions) belongs in the OS, not an App. The contradiction between "Apps don't contain agency logic" (autarch-vision.md line 42) and the actual descriptions of Gurgeh and Coldwine is unreconciled.
- **Failure scenario:** A team builds a web dashboard as an Autarch alternative. They expect to render kernel state and call `ic` commands. They discover that Gurgeh's PRD-generation workflow lives in Autarch-layer code. To replicate it, they must either duplicate the arbiter logic or depend on Autarch as a library — which breaks the "apps are swappable" guarantee entirely.
- **Fix:** Either (a) explicitly acknowledge that Gurgeh's arbiter is a migration target to the OS layer and the current architecture is transitional, with a timeline; or (b) add a section justifying why PRD generation intelligence is legitimately an App concern — with acknowledgment that these tools are not swappable. The current text contradicts itself without reconciliation.

---

### P1-8: Budget Events Are Never Emitted — Recorder Is Wired as nil

- **Agents:** fd-orchestration-routing (Finding 3), corroborated by fd-kernel-contract (F6)
- **Location:** `infra/intercore/docs/product/intercore-vision.md` — Cost and Billing section; `internal/budget/budget.go`, `cmd/ic/dispatch.go`
- **Issue:** The vision describes `budget.warning` and `budget.exceeded` as kernel events that Interspect can react to. In `cmdDispatchTokens()`, the budget checker is instantiated with `nil` as the event recorder: `checker := budget.New(pStore, dStore, sStore, nil)`. The `emitEvent()` method is fire-and-forget with the recorder nil check producing a no-op. Budget threshold crossings produce stderr output only — no event is written to the event bus. Interspect cannot react to budget crossings because the events do not exist.
- **Failure scenario:** A dispatch consumes 2M tokens against a 100k budget. The budget checker fires on token-set call, writes to stderr, emits no event. The run continues. Interspect, watching the event bus, sees no `budget.exceeded` event and takes no action. The next sprint-level summary is the first indication of the cost overrun.
- **Fix:** Wire a real `EventRecorder` into the budget checker in `cmdDispatchTokens()`. Consider triggering a budget check from `UpdateStatus()` when a dispatch reaches terminal state, not only from explicit `ic dispatch tokens` calls. Document that budget tracking depends on the OS calling `ic dispatch tokens` at agent completion.

---

### P1-9: "Clavain Is Not a Claude Code Plugin" Contradicts Current Deployment Reality

- **Agents:** fd-cross-reference (P1-1), fd-architecture-coherence (Finding 7)
- **Location:** `hub/clavain/docs/vision.md` — "What Clavain Is Not" section, line 403
- **Issue:** The vision states as present fact: "Not a Claude Code plugin. Clavain runs on its own TUI (Autarch)." Clavain is currently deployed as a Claude Code plugin with `.claude-plugin/plugin.json`, `hooks.json`, 21 hooks, 52 slash commands, and all hooks running inside Claude Code sessions. Autarch TUI is not yet functional as the primary interface — it is a v1.5-v3 migration target. A new contributor reading this section will encounter immediate contradiction with the actual codebase.
- **Failure scenario:** A contributor reads "Clavain runs on its own TUI (Autarch)" and "The Claude Code plugin interface is one driver among several." They expect to work with Clavain through Autarch. They find a Claude Code plugin with 52 slash commands and no functioning Autarch TUI. They waste significant time investigating the discrepancy.
- **Fix:** Change the present-tense claim to an aspirational framing: "Not primarily a Claude Code plugin — by design. Clavain's identity is an autonomous software agency. Autarch (TUI) is the target primary interface; today it ships as a Claude Code plugin because that surface is available now. The architecture is designed to outlive any single host platform." Add a "Current State vs Target State" callout to the architecture section.

---

### P1-10: Adaptive Threshold Drift Has No Convergence Bounds

- **Agents:** fd-autonomy-design (L3-B)
- **Location:** `hub/clavain/docs/vision.md` — Discovery → Backlog Pipeline, adaptive thresholds
- **Issue:** The vision describes adaptive thresholds: "If humans consistently promote Medium items (>30% rate), the High threshold lowers by 0.02 per feedback cycle." There is no stated absolute floor/ceiling, no per-cycle change limit across many cycles, and no diversity injection mechanism. If the interest profile vector is miscalibrated early, human promotions shift the profile in that direction, surfacing more of the same type, causing more promotions — a standard filter bubble failure mode. The 0.02 per-cycle limit prevents single-cycle wild swings but allows unbounded drift across many cycles.
- **Failure scenario:** Early discovery set is biased toward arXiv papers on one topic. The system promotes these heavily. The profile converges on this corner of the interest space. After 50 cycles, the system surfaces only papers closely related to this topic. Relevant HN posts, GitHub repos, and Anthropic updates in adjacent areas score below threshold and are discarded.
- **Fix:** Add: (a) absolute floor/ceiling (e.g., High cannot go below 0.6 or above 0.95); (b) a per-cycle change limit that also applies across cumulative drift (e.g., no more than 0.1 total movement from initial value without explicit human reset); (c) a configurable percentage of discoveries surfaced from the long tail regardless of score, to provide calibration data outside the current profile.

---

### P1-11: Gate Override Writes Phase Change Before Audit Event — Crash Leaves Advance Without Audit Trail

- **Agents:** fd-kernel-contract (F7)
- **Location:** `infra/intercore/AGENTS.md` — Override; `infra/intercore/docs/product/intercore-vision.md` — "Fail Safe, Not Fail Silent"
- **Issue:** AGENTS.md acknowledges: "`ic gate override` force-advances past a failed gate. It calls `UpdatePhase` first, then records the event — if a crash occurs between, the advance happened without audit." The vision's "Fail Safe, Not Fail Silent" principle is specifically violated for the code path most likely to be scrutinized (forced overrides are exactly the events auditors care about). Interspect's analysis of gate override patterns will have gaps from any crash-between incidents.
- **Failure scenario:** A gate override is force-applied. Between `UpdatePhase` commit and the event INSERT, the process is killed (OOM). The run advances without any audit record. Interspect sees a phase advance with no preceding gate evaluation or override event. The self-improvement model treats this as an unexplained jump.
- **Fix:** Wrap `UpdatePhase` and the override event INSERT in a single transaction. Both operations are SQLite writes on the same `SetMaxOpenConns(1)` connection — the fear that drove the current ordering ("safer than audit without advance") is eliminable.

---

## P2 Findings (17)

| # | Finding | Location | Agents |
|---|---------|----------|--------|
| 1 | Event reactor ErrStalePhase handling undefined — spurious errors or retry loops | intercore-vision.md | fd-autonomy-design (L2-B) |
| 2 | Fan-out timeout coordination protocol unspecified — undefined state when child times out | intercore-vision.md | fd-autonomy-design (AL-B), fd-orchestration-routing (Finding 2) |
| 3 | Confidence scores uncalibrated at initial deployment — auto-execute on unvalidated scores | intercore-vision.md | fd-autonomy-design (L3-C) |
| 4 | Same confidence threshold (0.8) applied to actions with different error costs (discovery vs phase advance) | clavain/docs/vision.md | fd-autonomy-design (HITL-D) |
| 5 | Discovery event-triggered fan-out has no re-entrancy guard — potential scan cascade | clavain/docs/vision.md | fd-orchestration-routing (Finding 8) |
| 6 | `gate.override` event type may not be distinct from `gate.passed` — Interspect cannot detect bypass patterns | intercore-vision.md | fd-autonomy-design (L1-A) |
| 7 | Discovery pipeline scoring ownership split across kernel, OS, and App without a seam definition | all three docs | fd-architecture-coherence (Finding 4) |
| 8 | Interspect → Clavain proposal format undefined — no schema or apply mechanism | clavain/docs/vision.md | fd-architecture-coherence (Finding 5) |
| 9 | Autarch migration depends on v4 portfolio primitive for Gurgeh spec evolution; Coldwine bead mapping crosses undefined layer boundary | autarch-vision.md | fd-architecture-coherence (Finding 6) |
| 10 | Lock stale-break is not atomic — two-process race window during stale detection | intercore implementation | fd-kernel-contract (F3, F8) |
| 11 | Dual-cursor design produces ambiguous event ordering and degrades at-least-once on TTL expiry | intercore-vision.md | fd-kernel-contract (F10) |
| 12 | API stability claim covers DB schema but not CLI flags or event schemas | intercore-vision.md | fd-kernel-contract (F9), fd-orchestration-routing (Finding 7) |
| 13 | Model routing layer 2/3: tiers.yaml uses Codex/GPT model names; vision uses Claude/Gemini/Oracle taxonomy — not reconciled | clavain/docs/vision.md + tiers.yaml | fd-orchestration-routing (Finding 4, 7) |
| 14 | "12 agents cheaper than 8" claim has no arithmetic basis — Composer not built | clavain/docs/vision.md | fd-orchestration-routing (Finding 5) |
| 15 | Cross-phase handoff protocol (Discover→Design artifact schema) unspecified — prerequisite for autonomous pipeline | clavain/docs/vision.md | fd-orchestration-routing (Finding 6) |
| 16 | Cross-layer architecture diagrams are inconsistent — Autarch diagram omits Drivers and Interspect; layer numbering conflicts | all three docs | fd-layer-boundary (P2-4), fd-cross-reference (P2-1, P2-3) |
| 17 | `ic tui` subcommand would require kernel to depend on Autarch's `pkg/tui` — inverted dependency direction | intercore-vision.md | fd-architecture-coherence (dependency table) |

---

## P3 Findings (14)

- **ARCH-A:** Confidence tier boundaries (0.8/0.5/0.3) — kernel constants or OS-configurable? Not clarified. (fd-autonomy-design)
- **HITL-C:** Proposal TTL and expiry behavior for Interspect proposals unspecified — proposals should never auto-apply. (fd-autonomy-design)
- **L4-relay:** Cross-project relay process is a single point of failure — appropriate to flag for v4 design. (fd-autonomy-design)
- **F11:** "No background event loop" overstates statelessness — SpawnHandler/HookHandler run detached goroutines with untracked context.Background(); goroutine leak risk on repeated invocations. (fd-kernel-contract)
- **F12:** Clock monotonicity risk acknowledged but not mitigated — NTP backward jump affects sentinel TTLs and stale detection. (fd-kernel-contract)
- **Finding 8:** SQLite schema is an implicit API surface — direct query access from app code unguarded. (fd-architecture-coherence)
- **Finding 9:** Layer numbering inconsistent — Autarch has no canonical layer designation across docs. (fd-architecture-coherence)
- **P3-1 (layer):** Naming drift — "Drivers", "Companion Plugins", "Drivers (Plugins)" used interchangeably across docs. (fd-layer-boundary)
- **P3-2 (layer):** Referential asymmetry — Intercore references Clavain vision; Clavain does not reciprocate. (fd-layer-boundary)
- **P3-3 (layer):** "Sprint" used as a concept in Intercore's kernel migration section — OS vocabulary in kernel doc. (fd-layer-boundary)
- **P0-1 (xref):** Plain-text "see Autarch vision doc" in intercore-vision.md line 54 is not a hyperlink — only unnavigable reference in the doc. (fd-cross-reference)
- **P2-4 (xref):** "Layer 1/2/3" labels reused for Model Routing stages in clavain/docs/vision.md — collides with stack layer labels. (fd-cross-reference)
- **P2-6 (xref):** Pollard/Gurgeh migration order: autarch doc gives Pollard a distinct earlier step; intercore v3 horizon lumps both. (fd-cross-reference)
- **Finding 9 (orch):** Agency spec schema not defined before C1 implementation — Composer (C3) and fleet registry (C2) cannot be built without it. (fd-orchestration-routing)

---

## Convergence Analysis

Findings independently identified by multiple agents carry highest confidence. These are the most actionable items.

### Highest confidence (3+ agents independently)

| Finding | Agents | Confidence |
|---------|--------|-----------|
| Autarch apps embed OS agency logic (Gurgeh arbiter, Coldwine orchestration) | fd-architecture-coherence, fd-layer-boundary, fd-autonomy-design | Very high — 3 agents, each from different analytical lens |
| Event reactor lifecycle and failure mode unspecified | fd-autonomy-design, fd-architecture-coherence, fd-layer-boundary | Very high — 3 agents |
| Confidence tier enforcement is aspirational, not current | fd-kernel-contract, fd-layer-boundary, fd-orchestration-routing | Very high — 3 agents |
| Budget event wiring is broken (recorder=nil or self-reported only) | fd-orchestration-routing, fd-kernel-contract | High — 2 agents with independent code inspection |
| Durable consumer cursor TTL contradicts "never expire" guarantee | fd-kernel-contract, fd-orchestration-routing | High — 2 agents |
| "Not a Claude Code plugin" contradicts current reality | fd-cross-reference, fd-architecture-coherence | High — 2 agents |
| Discovery pipeline scoring split across three layers without ownership seam | fd-architecture-coherence, fd-layer-boundary, fd-autonomy-design | High — 3 agents, different aspects |

### Corroborated (2 agents independently)

| Finding | Agents |
|---------|--------|
| Fan-out partial failure semantics unspecified (critical agents drop silently) | fd-autonomy-design, fd-orchestration-routing |
| Lock stale-break race window | fd-kernel-contract (F3, F8) internal consistency |
| Interspect → Clavain proposal interface has no defined schema | fd-architecture-coherence, fd-autonomy-design |
| Adaptive threshold drift / filter bubble | fd-autonomy-design (L3-B) — unique but internally corroborated |
| Cross-layer diagram inconsistencies | fd-layer-boundary, fd-cross-reference, fd-architecture-coherence |
| Spawn limits not implemented | fd-orchestration-routing, fd-kernel-contract (enforcement table audit) |

---

## Agent Reports

- `docs/research/review-layer-boundaries.md` — fd-layer-boundary
- `docs/research/review-cross-references.md` — fd-cross-reference
- `docs/research/review-architecture-coherence.md` — fd-architecture-coherence
- `docs/research/review-autonomy-design.md` — fd-autonomy-design
- `docs/research/review-kernel-contracts.md` — fd-kernel-contract
- `docs/research/review-orchestration-routing.md` — fd-orchestration-routing
