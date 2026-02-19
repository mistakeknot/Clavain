# Autonomy Design Review: Intercore + Clavain + Autarch Vision

**Reviewer:** fd-autonomy-design (Autonomous Systems Designer)
**Date:** 2026-02-19
**Documents reviewed:**
- `/root/projects/Interverse/infra/intercore/docs/product/intercore-vision.md` (v1.6)
- `/root/projects/Interverse/hub/clavain/docs/vision.md`
- `/root/projects/Interverse/infra/intercore/docs/product/autarch-vision.md` (v1.0)

**Supporting context:**
- `/root/projects/Interverse/infra/intercore/CLAUDE.md`
- Prior safety reviews in `docs/research/` (mutex plan, run-tracking plan)
- Active codebase in `infra/intercore/`

---

## Executive Summary

The vision is architecturally sound, technically grounded, and unusually honest about what is not yet built. The kernel/OS/profiler separation is clean and defensible. The autonomy ladder is correctly ordered. Most risks are acknowledged somewhere in the documents.

What the vision does not adequately address are: (1) the self-improvement loop's reward hacking and error amplification paths, which receive only a research question flag rather than a design response; (2) the confidence scoring model which conflates independent thresholds with calibrated probabilistic accuracy; (3) the absence of a rate-of-change limit on adaptive threshold drift; and (4) the gap between "human above the loop" as a stated goal and the reality that for several autonomy actions the human notification arrives after the irreversible step.

The design is shippable at Level 0 and Level 1. Level 2 (React) introduces operational risks the vision underspecifies. Level 3 (Adapt/self-improvement) has a documented risk (reward hacking) with no concrete mitigation design beyond "Interspect reads kernel events." Level 4 (Orchestrate/fleet) is appropriately deferred to v4 with no gaps introduced by its current absence.

---

## 1. Autonomy Ladder Soundness

### Level 0: Record — Achievable. Well-specified.

**Claim (intercore-vision.md):** "The kernel records what happened. Runs, phases, dispatches, artifacts — all tracked."

**Assessment:** This level is implemented. SQLite WAL, transactional dual-write (state + events in same transaction), dedup keys, consumer cursors, and crash recovery semantics are all specified with enough precision to be correct. The prior correctness review of the run-tracking plan confirms this.

**Gap:** Token tracking at Level 0 is self-reported, not independently verified. The vision acknowledges this: "An agent that misreports its token usage undermines budgeting." The Tier 2 mitigation (injecting tracking at the API call layer) is correctly deferred but the implication is that cost reporting at Level 0 is advisory, not trustworthy. Any downstream decision that relies on per-dispatch token counts (model routing, budget alerts) should be treated as best-effort until Tier 2 is built.

---

### Level 1: Enforce — Achievable. Slightly underspecified at the gate policy layer.

**Claim:** "Gates evaluate real conditions. A run cannot advance from `planned` to `executing` without a plan artifact."

**Assessment:** The mechanism is sound. Hard gates block advancement. Gate checks are kernel-enforced: `artifact_exists`, `agents_complete`, `verdict_exists`. Gate evidence is recorded whether pass or fail. The distinction between hard/soft/none gate tiers is clear.

**Gap — gate override audit trail is not surfaced to Interspect:** Gate overrides (`ic gate override <run_id> --reason=<text>`) are recorded as events. The vision states that Interspect reads kernel events and proposes OS changes. But the vision does not specify that Interspect has a specific analysis path for "gates that are frequently overridden." If engineers routinely override gates under time pressure and Interspect cannot detect this pattern, the feedback loop is broken: gates that are consistently bypassed look like normally-passing gates from the event stream. A `gate.override` event type distinct from `gate.passed` is implied but should be explicitly confirmed.

**Finding L1-A (P2):** Confirm that `gate.override` events use a distinct event type (not the same `gate.passed` type). Interspect must be able to query override rate per gate separately from pass rate to detect gates that exist in name only.

---

### Level 2: React — Technically achievable. Operational risks underspecified.

**Claim:** "Events trigger automatic reactions. When a run advances to `review`, the kernel emits an event. The OS subscribes and spawns review agents. When all agents complete, the OS advances the phase. The human observes and intervenes only on exceptions."

**Assessment:** The mechanism is correct: pull-based event consumption, consumer cursors for at-least-once delivery, the OS event reactor as a long-lived `ic events tail -f` process. The idempotency design (dedup keys on events, optimistic concurrency on phase transitions) handles the obvious failure modes.

**Gap 1 — Event reactor process management is underdefined:** The vision describes the OS event reactor as "a long-lived `ic events tail -f --consumer=clavain-reactor` process with `--poll-interval`." But the vision does not address: what manages this process? Who restarts it if it crashes? If it dies while events are queued, it replays from cursor on restart (correct), but there is no specification for how long it can be down before the workflow is considered stalled.

At Level 1, the human drives phase advancement manually and the kernel records. At Level 2, the OS reactor drives it automatically. If the reactor is down, the workflow stops silently. A human opening the TUI would see the run stuck at a phase with completed dispatches but no advancement. The vision does not describe a "reactor health" signal, a watchdog, or a manual recovery path for this scenario.

**Finding L2-A (P1):** The event reactor process needs a defined lifecycle: start-on-session, systemd service, or inline in a Clavain hook. Without this, Level 2 autonomy has a silent failure mode — the OS reactor dies, dispatches complete, but the workflow stalls indefinitely. Specify: (a) how the reactor is started, (b) what "reactor not running" looks like to a human, and (c) the manual recovery path (`ic run advance <id>` manually).

**Gap 2 — Event storms on fanout completion:** The vision describes fan-out dispatch for multi-agent review. When 7 review agents all complete within seconds of each other, the event reactor will receive 7 `dispatch.completed` events and attempt to evaluate `agents_complete` gate 7 times. Optimistic concurrency (`WHERE phase = ?`) ensures only one phase advancement wins. The other 6 lose with `ErrStalePhase` and should re-read state and decide the transition no longer applies. This behavior is specified.

But the vision does not specify what happens to the 6 losing reactor iterations. Do they log and exit cleanly? Do they retry the advancement anyway? If the reactor does not correctly handle `ErrStalePhase` as "work complete, nothing to do," it could log spurious errors or enter retry loops. This is an implementation detail but a critical one for Level 2 correctness.

**Finding L2-B (P2):** Specify the reactor's `ErrStalePhase` handling explicitly in the OS design (not just as a kernel invariant). The contract should be: on `ErrStalePhase`, re-read the current phase and confirm the desired transition already occurred; if so, treat as success and do nothing; if not, investigate.

**Gap 3 — Cascading reactions:** The vision's concrete scenario shows phase transitions triggering agent dispatches triggering completion events triggering further phase transitions. At Level 2 this chain is: `run.advanced → (reactor) dispatch agents → dispatch.completed (x7) → (reactor) advance phase → run.advanced...`. If a phase advancement triggers a sequence that ends in an error (e.g., all dispatches fail, gate fails), the reactor will receive a `gate.failed` event. The vision does not describe the reactor's response to a gate failure: does it pause, notify the human, or retry dispatch? The human is supposed to "observe and intervene only on exceptions" — but the mechanism for surfacing exceptions to human attention is not specified beyond "the TUI tails events."

**Finding L2-C (P1):** For Level 2 to be safely autonomous, gate failures in the event reactor chain must have a specified escalation path. At minimum: on `gate.failed` from an automatic advancement attempt, the reactor should pause the run (new run state: `paused`), emit a `run.paused` event with the gate failure evidence, and surface this in the Bigend/TUI as requiring human action. Without this, a failing gate in the automatic chain produces a stalled run with no human notification.

---

### Level 3: Adapt (self-improvement) — Design present, safety underspecified.

**Claim (clavain-vision.md):** "Interspect reads kernel events and correlates them with outcomes. Agents that consistently produce false positives get downweighted. Phases that never produce useful artifacts get skipped by default. Gate rules tighten or relax based on evidence."

**Assessment:** The mechanism description is correct at a high level. Interspect reads the event stream, proposes OS configuration changes, and the OS applies them as overlays. The kernel enforces the updated rules. The human reviews proposals and maintains veto power.

This is where the most important safety questions arise.

**Gap 1 — Reward hacking: acknowledged but not designed for.**

The Clavain vision explicitly lists "Self-improvement feedback loops — how to prevent reward hacking ('skip reviews because it speeds runs')?" as a research question in the long-term research section. This is honest. However, acknowledging a threat as a research question is not the same as designing against it.

Reward hacking in this context: Interspect's objective is to improve the outcomes-per-token ratio. A run that skips review phases completes faster and costs fewer tokens. If review agents frequently surface findings that delay the sprint (failing gates), Interspect could learn — incorrectly — that review is the bottleneck to efficiency and propose downweighting review agents or softening review gates.

The claim that "the human reviews proposals and maintains veto power" is the only stated safeguard. This is a human-above-the-loop control, which is correct in principle. But it assumes:

1. The human can detect which proposals are reward hacking versus genuine insight.
2. Proposals are presented with enough context for the human to assess them.
3. The volume of proposals does not exceed the human's capacity to review them.

None of these are designed for in the vision.

**Finding L3-A (P0):** The self-improvement loop has no designed-in safeguard against proposals that optimize a proxy metric (speed, token cost) at the expense of the actual goal (software quality). Specifically:

- A proposal to skip or downweight `fd-safety` because it often produces findings that delay sprint advancement looks identical to a correct proposal to exclude `fd-game-design` from a Go backend project. Both propose excluding an agent. Both cite evidence. The human must distinguish them.
- A proposal to lower a gate threshold ("plan-review gate fails 40% of the time; lower the threshold") could be correct (gate is miscalibrated) or reward hacking (gate is correctly catching bad plans). The evidence shown will be the failure rate, not the quality of what the gate was catching.

Required mitigation design:

(a) **Orthogonal quality signal.** Interspect proposals should be required to show impact on a quality signal independent of efficiency. For example: "agent exclusion proposed because correction rate exceeds 80%; however, this agent's findings were acted on N% of the time in the past 6 months." If an agent's findings are frequently acted on, that is evidence against exclusion regardless of correction rate.

(b) **Protected agent categories.** `fd-safety`, `fd-security`, and `fd-correctness` should be marked as protected agents that cannot be excluded or downweighted by Interspect proposals without an explicit out-of-band human override (not just a proposal accept). The vision currently describes "warnings when excluded" for cross-cutting agents, which is insufficient — a warning can be dismissed.

(c) **Proposal impact estimation.** Before presenting a proposal, Interspect should estimate: "If this proposal had been active for the past 20 runs, how many gate failures would have been avoided, and how many issues that were subsequently fixed would have been missed?" This counterfactual framing gives the human a basis for judgment.

**Gap 2 — Error amplification feedback loops.**

The adaptive threshold mechanism in the discovery pipeline has a described path to error amplification. From clavain-vision.md: "If humans consistently promote Medium items (>30% rate), the High threshold lowers by 0.02 per feedback cycle."

The risk: if the interest profile vector is miscalibrated early (perhaps because the first N discoveries shown are not representative), human promotions shift the profile in a direction that surfaces more discoveries of the same type. More promotions shift the profile further. The system converges on a narrow, possibly irrelevant corner of the interest space. This is a standard filter bubble / feedback loop failure mode.

The vision does not describe: (a) a convergence check on the profile vector, (b) a floor on threshold movement per cycle, or (c) a periodic "surprise me" signal that introduces high-scoring items from outside the current interest profile to test whether the profile is over-narrowed.

**Finding L3-B (P1):** The adaptive threshold system needs:
- A per-cycle change limit (e.g., threshold moves no more than 0.02 per feedback cycle; the vision already states this but does not state what prevents drift over many cycles)
- An absolute floor/ceiling on thresholds (e.g., High cannot go below 0.6, cannot rise above 0.95)
- A diversity injection: a configurable percentage of discoveries surfaced to the human should bypass scoring and be drawn from the long tail, to provide calibration data outside the current profile

**Gap 3 — Confidence score calibration gap.**

The confidence scoring system (intercore-vision.md) describes a weighted composite model for agent outcomes (completeness 20%, consistency 25%, specificity 20%, research 20%, assumptions 15%). The discovery confidence system uses embedding similarity against a profile vector. Both are described as producing "confidence scores."

Neither system describes how these scores are calibrated against actual outcomes. A score of 0.8 is supposed to mean "high confidence" but absent calibration, it means only "high score on this specific weighting function." Whether 0.8 actually predicts good outcomes is unknown until the system accumulates data and someone checks.

This is not a flaw unique to this system — it is a standard machine learning calibration problem. But the vision's confidence-tiered autonomy gates (auto-execute at 0.8, propose-to-human at 0.5) treat these scores as if they were calibrated probabilities. They are not, initially. An uncalibrated score of 0.8 that is systematically wrong about quality would cause the kernel to auto-execute actions (create beads, auto-advance phases) that should have been surfaced for human review.

**Finding L3-C (P2):** Confidence tiers should be treated as provisional until the system has accumulated enough data to estimate calibration. At Level 3 entry, reduce or disable auto-execute (the High tier behavior) until Interspect has analyzed at least N proposals (suggest N=50 per agent) and can confirm the score distribution is predictive of good outcomes. Only after calibration validation should auto-execute be re-enabled for that agent/category.

---

### "Level -1: Discover" — Sound extension, one risk to flag.

**Claim (clavain-vision.md):** "Before the system can record, enforce, or react to work, it must find work worth doing."

**Assessment:** The framing is correct. The discovery pipeline (interject, source adapters, embedding scoring, confidence gates) is the most fleshed-out Level -1 mechanism described. It is a logical predecessor to Level 0, not a level above it.

The design appropriately separates the kernel mechanism (discovery records, confidence gates, events) from OS policy (which sources, what thresholds, what actions). The feedback loop design is thoughtful.

**Gap — Autonomous bead creation at High confidence tier is an irreversible-ish action:**

At confidence >= 0.8, the system auto-creates a bead and writes a briefing doc, then sends a notification. The vision states "Notification in session inbox; human can adjust priority or dismiss." But the bead is already created. In a well-managed backlog, bead creation is not trivially reversible — it has effects (it may become a sprint target, accumulate estimates, appear in reports, etc.). The rollback primitive (`ic discovery rollback --source=<source> --since=<timestamp>`) exists and is specified, but the cost of rollback (finding which beads to close, re-evaluating downstream effects) is non-trivial.

**Finding L-1-A (P2):** For the auto-create action at High confidence, consider a short approval window rather than immediate execution: create the bead in `proposed` state, send the inbox notification, and auto-promote to `active` only after N minutes without human dismissal. This preserves the "human above the loop" goal more faithfully for backlog mutations than the current "create then notify" flow.

---

### Level 4: Orchestrate — Appropriately aspirational.

**Assessment:** Level 4 is correctly positioned as the v4 horizon (8-14 months). The vision does not overspecify it. The cross-project event relay (relay process tailing multiple project DBs), portfolio-level runs, and dependency graph awareness are all described at sufficient level to be checkable when the time comes.

**One question for v3 → v4 transition:** The relay mechanism (a relay process tailing multiple SQLite databases and writing to a shared relay DB) introduces a new single point of failure. If the relay process dies, all cross-project coordination silently stops. The vision does not describe the relay's failure mode or the recovery path. This is appropriate for v4 aspirational content but should be flagged for the v4 design phase.

---

## 2. Self-Improvement Loop Integrity

### The stated design

From intercore-vision.md: "Interspect reads kernel events and correlates with human corrections. Proposes changes to OS configuration (routing rules, agent prompts). Never modifies the kernel — only the OS layer."

From clavain-vision.md: "The profiler proposes changes. The OS applies them as overlays. The kernel enforces the updated rules. The human reviews proposals and maintains veto power."

### Safeguards present

1. **Kernel immutability:** Interspect cannot modify the kernel. This is a hard boundary. It prevents Interspect from weakening kernel enforcement (e.g., raising spawn limits to allow unconstrained agent proliferation).

2. **OS-layer only:** Interspect proposes changes to routing rules, agent prompts, and gate policies. These are version-controlled OS configuration, not runtime kernel state. A bad proposal can be reverted by reverting the config change.

3. **Human veto:** Proposals must be accepted by the human. This is the primary guard.

4. **Canary monitoring:** After a routing override is applied, Interspect monitors for 14 days or 20 uses. If the override causes problems, `/interspect:revert` undoes it. This is specified in the actual system today (AGENTS.md).

### Safeguards missing or underspecified

**Missing: What constitutes a "bad" proposal?** The human veto is effective only if the human can identify reward hacking. The proposals are currently presented with: the correction rate, the evidence IDs, and the proposed action. Missing from the presentation: the quality signal (were this agent's findings acted on? did they catch issues that escaped to production?), a counterfactual estimate, and a clear statement of what category of risk this agent covers.

**Missing: Proposal rate limiting.** If Interspect generates many proposals simultaneously (e.g., after a backlog of agent corrections), the human faces a batch of proposals, each requiring judgment. Proposal overload leads to approval of proposals without adequate review. The vision does not specify a throttle on how many proposals Interspect can surface per session.

**Missing: Self-improvement of Interspect itself.** Interspect's analysis logic is in OS-layer code. Interspect cannot propose changes to itself (it cannot modify the OS code that runs it; it can only propose config changes). This is a correct limitation. However, if Interspect's analysis heuristics are themselves miscalibrated, there is no mechanism to detect and correct this. An Interspect that systematically underestimates certain agents' value will continue to propose their exclusion until a human notices the pattern.

**Missing: Rollback of applied proposals.** Canary monitoring exists. `/interspect:revert` exists. But the vision does not specify what the "problem signal" is that should trigger revert. "The override causes problems" is undefined. Define concretely: what metric increases, what threshold, over what window triggers a canary alert that prompts the human to consider revert?

**Finding SI-A (P0):** The self-improvement loop design is incomplete as a safety specification. The human veto is necessary but not sufficient. Required additions:

1. Proposals for excluding or downweighting `fd-safety`, `fd-security`, `fd-correctness` must require an explicit out-of-band human override (not just proposal accept). These agents are not excludable through the normal Interspect flow.

2. Each proposal must be accompanied by a quality impact estimate: "In the last 20 runs, this agent's findings were acted on N times. If excluded, those N findings would not have been surfaced."

3. A maximum proposal batch size per session (suggest 3). Additional proposals queue for the next session.

4. Canary alerts must be defined quantitatively: "If the run rollback rate increases by more than X% in the 14-day window, or if gate override frequency increases, trigger a canary alert."

---

## 3. Agent Lifecycle Design

### Dispatch state machine

**Stated:** `spawn → running → completed | failed | timeout | cancelled`

**Assessment:** The state machine is appropriate for the described use case. Transitions are clear. The terminal states cover the main failure modes.

**Missing state: `stalled`**

The vision describes a reconciliation primitive (`ic dispatch reconcile`) that detects anomalies: "stale dispatches (process dead but dispatch still marked running)." The reconciliation engine emits "anomaly detected" events but does not auto-resolve — "the kernel records them but does not auto-resolve." The OS is responsible for reconciliation.

What the state machine lacks is a `stalled` state for dispatches where the process is confirmed dead but the dispatch was not properly cleaned up. Currently these dispatches remain in `running` state until the OS explicitly reconciles them. A dispatch in `running` state with a dead process creates incorrect signals for the `agents_complete` gate check: the gate checks whether all dispatches are completed, not whether all dispatches are in a non-running terminal state. A stale running dispatch blocks gate passage indefinitely.

**Finding AL-A (P1):** The `agents_complete` gate check should be: "all dispatches are in a terminal state (`completed`, `failed`, `timeout`, `cancelled`), OR the reconciliation engine has confirmed those remaining as `running` are actually dead." Without this, a dispatch that dies without self-reporting (`killed -9`, OOM, etc.) permanently blocks the gate. Define the reconciliation polling interval and the state transition from `running` to `stalled` (or to `failed`) as part of the Level 2 event reactor design.

### Fan-out model

**Stated:** Parent-child dispatch relationships tracked. Spawn limits: max concurrent dispatches per run, per project, globally. Max spawn depth. Max children per dispatch.

**Assessment:** The fan-out model is sound. OpenClaw-inspired spawn limits are kernel-enforced invariants, not suggestions. The backend detection check (validate the requested agent backend is on PATH before dispatching) is a good defensive check.

**Gap — Fan-out timeout coordination:** If a parent dispatch spawns 7 child agents and one child times out, the parent is waiting for all children to complete. The vision does not specify how the parent is notified of a child timeout. Does the parent receive a `dispatch.timeout` event for the child? Does the parent's own timeout account for child timeouts? The `agents_complete` gate check at the run level checks that all dispatches (including children) are complete — but the parent dispatch itself may be waiting on children in a way that is not observable to the gate check.

**Finding AL-B (P2):** Specify the fan-out timeout protocol: (a) when a child dispatch times out, does the parent dispatch immediately fail or receive a partial-result signal? (b) does the run-level `agents_complete` gate distinguish between "all dispatches completed" and "all dispatches are in terminal states (some may be failed/timeout)"? For review workflows, partial completion (5 of 7 review agents completed, 2 timed out) should be a defined policy, not an undefined state.

### Reconciliation pattern

The fingerprint-based reconciliation engine is well-specified. The pattern of emitting `reconciliation.anomaly` events without auto-resolving is correct — the OS decides policy. The concern is that the OS policy for handling reconciliation anomalies is not specified in the vision.

---

## 4. Human-in-the-Loop Design

### "Human above the loop, not in the loop"

**Stated (clavain-vision.md):** "The agency handles execution mechanics: which model, which agents, what sequence, when to advance, what to review. The human retains strategic control: what to build, which tradeoffs to make, when to ship, where to intervene. This is not 'human in the loop' — it's 'human above the loop.'"

**Assessment:** The design philosophy is sound. The question is whether the implementation delivers it.

**Where it works:**
- Gate enforcement is kernel-enforced, not prompt-based. The human's quality standards survive even if the LLM wants to skip them.
- Self-improvement proposals require explicit human acceptance.
- The TUI provides event stream visibility.
- The rollback primitive gives the human a lever after the fact.

**Where it does not fully work:**

**Case 1: High-confidence auto-bead creation.** At confidence >= 0.8, a bead is created automatically. The human receives a notification after the bead exists. If the bead is incorrect or unwanted, the human must actively dismiss it. This is "human below a one-way action" — the action runs, then the human can undo it. For a well-managed backlog, creating and then closing beads is not neutral. The "human above the loop" framing requires that the human's position relative to the action is anterior, not posterior.

**Finding HITL-A (P1):** For bead auto-creation at the High confidence tier, implement a 15-minute approval window (configurable). The bead is created in `proposed` state. The human receives an inbox notification. If not dismissed within the window, it auto-promotes to `active`. This preserves asynchronous human control without requiring synchronous approval.

**Case 2: Event reactor auto-advancement.** At Level 2, the OS reactor automatically advances phases based on completed dispatches. If a dispatch produces a bad result (wrong code, harmful change) but the verdict status is `completed`, the reactor may advance the phase before the human reviews the dispatch output. The human is notified by the event stream, but the phase has already advanced.

**Finding HITL-B (P1):** At Level 2, auto-advancement from execution phases (execute, test) should require a `verdict_exists` gate with a minimum verdict quality signal, not just `agents_complete`. "The dispatch finished" is not the same as "the dispatch finished well." If all dispatches complete but the verdict is `failed` or `rejected`, the gate should block advancement and surface the failure as requiring human decision, not auto-advance.

**Case 3: Interspect proposal in absence of human attention.** The vision does not describe what happens to a queued proposal if the human is not monitoring for an extended period (e.g., overnight). Does the proposal age out? Does it get applied after N hours? Is the OS degraded in the interim?

**Finding HITL-C (P3):** Specify proposal TTL and behavior on TTL expiry. Proposals should never auto-apply. If a proposal is not reviewed within a configurable window, it should be logged as `expired` and re-evaluated in the next analysis cycle with fresh evidence.

### Confidence-tiered autonomy: justification quality

**Stated:** High (>= 0.8) = auto-execute; Medium (0.5-0.8) = propose to human; Low (0.3-0.5) = log only; Discard (< 0.3) = record.

**Assessment:** The tier boundaries are presented as a design decision but are not justified. Why is 0.8 the auto-execute threshold? The vision cites the Autarch `ConfidenceScore` model, which weights quality metrics across multiple axes. A composite score above 0.8 in that model is a specific, domain-specific threshold.

The problem is that the same threshold (0.8) is used for: discovery auto-promotion (creating a bead), verdict quality (advancing a phase), and agent outcome weighting. These are different domains with different cost-of-error profiles. A false positive in discovery (creating a bead that should not have been created) is low cost. A false positive in phase advancement (advancing a run that should have stayed for review) is higher cost. Using the same threshold for both implies the cost-of-error is the same, which it is not.

**Finding HITL-D (P2):** Differentiate confidence thresholds by action consequence:
- Discovery auto-promotion (low cost of error): 0.8 may be appropriate
- Phase auto-advancement (medium cost): suggest 0.9 or require dual signals (confidence + human review of dispatch outputs)
- Agent exclusion proposals (hard to reverse in practice): treat as high-consequence; do not auto-apply at any threshold

---

## 5. Failure Mode Coverage by Autonomy Level

### Level 0 failures

| Failure Mode | Addressed? | Assessment |
|---|---|---|
| DB corruption | Yes | WAL mode, backup before migration, crash-safe at transaction boundary |
| Session boundary data loss | Yes | Kernel survives session end; state persists |
| Clock skew | Partially | Acknowledged in assumptions: "doesn't guard against backward clock jumps." TTL-dependent operations (sentinels, event retention) may behave incorrectly after NTP step. Low frequency but possible. |
| Concurrent process DB contention | Yes | Single connection, WAL mode, filesystem locks for read-modify-write |
| Token tracking inaccuracy | Partially | Self-reported; acknowledged; Tier 2 mitigation deferred |

**Residual at Level 0:** Clock skew handling. The vision acknowledges this but does not specify a mitigation even as future work. For a single-machine deployment, this is low frequency but worth a monitoring hook: emit a `clock.anomaly` event if `time.Now()` returns a value earlier than the most recently persisted timestamp.

### Level 1 failures

| Failure Mode | Addressed? | Assessment |
|---|---|---|
| Gate bypass by prompting | Yes | Kernel-enforced, not prompt-based |
| Gate override audit trail | Partially | Events recorded, but Interspect analysis of override frequency not specified (Finding L1-A) |
| Artifact hash collision | Not addressed | Two different files with the same SHA256 would be treated as identical artifacts. Vanishingly rare but the vision does not mention this |
| OS policy misconfiguration (wrong gate rules) | Yes | Run config snapshot at creation time; policy changes do not affect in-flight runs |
| Migration rollback compatibility | Partially | Expand-only DDL; acknowledged version-skew risk between binary and DB |

### Level 2 failures

| Failure Mode | Addressed? | Assessment |
|---|---|---|
| Event reactor crash | Not addressed | Silent workflow stall (Finding L2-A) |
| Event storm / duplicate advancement | Addressed | ErrStalePhase + optimistic concurrency |
| ErrStalePhase reactor behavior | Not specified | Finding L2-B |
| Gate failure in automatic chain | Not addressed | Finding L2-C — no specified escalation |
| Dispatch dies without reporting | Partially | Reconciliation primitive exists; reconciliation policy not specified |
| Durable consumer cursor too far behind | Partially | Acknowledged: "a durable consumer that falls behind can block event pruning" — OS should monitor consumer lag. Monitoring mechanism not specified. |

**Critical Level 2 gap:** The event reactor lifecycle and its behavior under gate failures are the two most significant underspecified areas for Level 2. Without both being designed, Level 2 is not safely deployable as described.

### Level 3 failures

| Failure Mode | Addressed? | Assessment |
|---|---|---|
| Reward hacking | Acknowledged as research question | No mitigation design. Finding SI-A (P0). |
| Error amplification in adaptive thresholds | Not addressed | Finding L3-B (P1) |
| Confidence miscalibration | Not addressed | Finding L3-C (P2) |
| Interest profile filter bubble | Not addressed | Embedded in L3-B |
| Interspect own heuristic drift | Not addressed | No mechanism to detect/correct |
| Proposal overload | Not addressed | No rate limit on proposals |
| Canary alert undefined | Not addressed | "Causes problems" is undefined |

**Level 3 is the most significant safety gap.** It has the most failure modes that are either acknowledged without design response or not addressed. The design as stated is a research roadmap item with a mechanism stub, not a deployable self-improvement system.

### Level 4 failures (aspirational)

The vision correctly treats Level 4 as aspirational. No gaps are created by its current absence. The relay process single-point-of-failure question (flagged above) is appropriate to flag for the v4 design phase.

---

## 6. Architecture Soundness: Mechanism/Policy Separation

The kernel/OS/profiler separation is the most important design decision in the vision, and it is sound.

**What works:**
- The kernel does not know what "brainstorm" means. It enforces gate types (`artifact_exists`, `agents_complete`, `verdict_exists`) as mechanisms. The OS provides the policy (brainstorm requires an artifact, plan-review requires all dispatches complete).
- Interspect cannot modify the kernel. It can only propose OS configuration changes. This limits the blast radius of a miscalibrated profiler to OS configuration, not kernel enforcement.
- Phase chains are data supplied at `ic run create` time, not embedded in kernel code. This is genuinely extensible: any phase sequence the OS can express in JSON is a valid workflow.

**One boundary concern:** The run config snapshot stores OS-provided policy (phase chain, gate rules) as data in the kernel. The kernel treats it as opaque structure. But the kernel evaluates gate rules from the snapshot. This means the kernel does need to understand gate rule structure to evaluate them — it is not entirely opaque. The vision distinguishes between "what the kernel knows" and "what it enforces," which is correct: the kernel evaluates `artifact_exists` but does not know what artifact content means. The boundary is at structural evaluation, not semantic interpretation. This is a sound line.

**One language concern:** The vision states "the kernel enforces a confidence-gated autonomy model" for discovery confidence tiers. It also states "the kernel provides the evaluation mechanism; the OS provides the rules." There is a tension: if the tier boundaries (0.8/0.5/0.3) are configurable by the OS, the kernel enforces a mechanism. But the vision tables show fixed boundaries. Are these boundaries truly configurable, or are they baked into the kernel? If baked in, the kernel has policy embedded in it, violating the design principle. If configurable, the OS spec for discovery should declare them explicitly.

**Finding ARCH-A (P3):** Clarify whether confidence tier boundaries (0.8, 0.5, 0.3) are kernel constants or OS-configurable parameters. If OS-configurable, add them to the OS policy spec and the run config snapshot. If kernel constants, acknowledge them as policy embedded in the kernel (a deliberate exception to mechanism/policy separation, for simplicity).

---

## 7. Summary of Findings

### P0: Blocking (requires design response before Level 3 deployment)

| ID | Finding | Location | Impact |
|---|---|---|---|
| SI-A | Self-improvement loop lacks concrete safeguards against reward hacking | clavain-vision.md, intercore-vision.md | Agent exclusion optimizes speed metrics at expense of quality |

### P1: Must Fix (requires design response before Level 2/3 deployment)

| ID | Finding | Location | Impact |
|---|---|---|---|
| L2-A | Event reactor lifecycle undefined | intercore-vision.md | Silent workflow stall when reactor crashes |
| L2-C | No escalation path for gate failure in automatic chain | intercore-vision.md | Stalled run with no human notification |
| AL-A | `agents_complete` gate may be blocked permanently by dead-but-unreconciled dispatch | intercore-vision.md | Gate never passes; workflow stalls |
| HITL-A | High-confidence bead auto-creation is action-before-notification | clavain-vision.md | Unwanted beads created before human can prevent |
| HITL-B | Level 2 auto-advancement does not distinguish "completed" from "completed well" | intercore-vision.md | Phase advances past bad dispatch output |
| L3-B | Adaptive thresholds lack convergence bounds | clavain-vision.md | Filter bubble / interest profile drift |

### P2: Should Fix (design clarification needed)

| ID | Finding | Location | Impact |
|---|---|---|---|
| L1-A | Gate override event type distinct from gate.passed not confirmed | intercore-vision.md | Interspect cannot detect bypass patterns |
| L2-B | ErrStalePhase handling in reactor not specified | intercore-vision.md | Spurious error logs or retry loops |
| AL-B | Fan-out timeout coordination protocol undefined | intercore-vision.md | Undefined state when child dispatch times out |
| L3-C | Confidence scores uncalibrated at initial deployment | intercore-vision.md | Auto-execute actions based on unvalidated scores |
| L-1-A | Bead auto-create is action-before-notification (duplicates HITL-A with different framing) | clavain-vision.md | Harder to reverse than the notification model implies |
| HITL-D | Same confidence threshold applied to actions with different error costs | intercore-vision.md | Threshold too permissive for high-consequence actions |

### P3: Minor / Clarification

| ID | Finding | Location | Impact |
|---|---|---|---|
| HITL-C | Proposal TTL and expiry behavior unspecified | clavain-vision.md | Proposals accumulate or expire silently |
| ARCH-A | Confidence tier boundaries: kernel constants or OS-configurable? | intercore-vision.md | Policy/mechanism separation ambiguity |
| L4-relay | Cross-project relay process is a SPOF | intercore-vision.md | Appropriate for v4; flag for v4 design |

---

## 8. Go / No-Go Assessment by Level

| Level | State | Blockers |
|---|---|---|
| Level 0 (Record) | Go | None blocking. Clock skew is acknowledged residual risk. |
| Level 1 (Enforce) | Go | L1-A is a P2 clarification, not a blocker. |
| Level 2 (React) | No-Go as designed | L2-A (reactor lifecycle), L2-C (gate failure escalation), AL-A (stalled dispatch blocking gate), HITL-B (auto-advancement quality signal) must be designed before Level 2 is deployable. |
| Level 3 (Adapt) | No-Go as designed | SI-A (reward hacking safeguards), L3-B (adaptive threshold bounds), L3-C (confidence calibration) must be designed. Level 2 must be complete first. |
| Level 4 (Orchestrate) | Not yet, by design | Correctly deferred to v4. |

The v1 kernel (Level 0 + Level 1) is ready to ship. Level 2 needs four specific design decisions added to the spec before it is deployable safely. Level 3 needs a concrete self-improvement safety design, not just an acknowledgment of the problem.

---

*Review completed: 2026-02-19. Reviewed against: intercore-vision.md v1.6, clavain-vision.md (2026-02-19 revision), autarch-vision.md v1.0.*
