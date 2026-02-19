# Vision Review — Milestone Triage

**Date:** 2026-02-19
**Purpose:** Map each P0/P1 finding to the Intercore horizon it blocks, so the review is actionable rather than a flat severity list.

---

## Intercore Horizons (from intercore-vision.md)

| Horizon | Timeframe | Key Deliverables |
|---------|-----------|-----------------|
| **v1** | Current | Gates enforce. Events flow. Dispatches tracked. System of record. |
| **v1.5** | 1-2 months | Hook cutover, sprint hybrid mode, custom phase chains, API stability contract, Autarch monorepo merge. |
| **v2** | 2-4 months | Sprint kernel-driven, lane scheduling, token tracking, discovery events, Interspect Phase 1, rollback, Bigend migration, `ic tui`. |
| **v3** | 4-8 months | Interspect Phase 2-3, sandboxing Tier 1, confidence-tier enforcement, backlog refinement, Pollard/Gurgeh migration. |
| **v4** | 8-14 months | Portfolio runs, dependency graph, resource scheduling, sandboxing Tier 2, Coldwine migration. |

---

## P0 Findings — Horizon Mapping

### P0-1: Transactional Dual-Write Broken for Dispatch Events
**Blocks:** v2 (event-driven advancement)
**Urgency:** HIGH — must fix before Level 2 deployment.
**Why:** The event reactor at Level 2 relies on `dispatch.completed` events to trigger phase advancement. If dispatch status commits without the event, runs stall silently. This is a correctness bug in current code, not a missing feature.
**Fix complexity:** Low — move the event INSERT inside the existing transaction. Single-file change in `internal/dispatch/dispatch.go`.
**Recommendation:** Fix in v1 (current), don't wait for v2. The bug exists today and makes the event bus unreliable for any consumer.

### P0-2: Spawn Limits Not Implemented
**Blocks:** v2 (lane scheduling, token tracking)
**Urgency:** MEDIUM — dangerous now but survivable with careful OS-level hygiene.
**Why:** Without spawn limits, a misconfigured hook can create unbounded agent processes. Lane scheduling at v2 assumes the kernel can enforce concurrency caps. Token tracking at v2 assumes budgets can prevent runaway spawns.
**Fix complexity:** Medium — add `CountActive()`, `SpawnLimits` struct, depth traversal of `parent_id`. ~200 lines across dispatch store and spawn handler.
**Recommendation:** Fix early in v1.5. The hook cutover at v1.5 increases the risk surface (more automated `ic dispatch spawn` calls from hooks).

### P0-3: Discovery Confidence-Tier Enforcement Aspirational
**Blocks:** v3 (confidence-tiered autonomy gates)
**Urgency:** LOW (relative to other P0s) — the discovery subsystem doesn't exist yet, so there's no false enforcement today.
**Why:** The vision doc claims the enforcement is current. It's not — there's no `discoveries` table. The doc must be corrected to mark this as v3 planned. The actual implementation is on the v3 timeline and isn't blocking anything before that.
**Fix complexity:** Doc fix is trivial (add horizon column to "Enforces vs Records" table). Implementation is v3 scope.
**Recommendation:** Fix the doc now. Implementation tracks with v3 naturally.

### P0-4: Self-Improvement Reward Hacking Unsafeguarded
**Blocks:** v3 (Interspect Phase 2-3)
**Urgency:** LOW — Interspect doesn't modify anything autonomously today. This matters when proposals auto-apply.
**Why:** The safeguards (protected agent classes, quality impact estimates, batch limits, canary thresholds) must be designed before Interspect Phase 2 ships. But Phase 1 (read-only consumer) is safe — it only reads events.
**Fix complexity:** Design work, not code. Add the safeguard framework to the Clavain vision doc; implement with Interspect Phase 2.
**Recommendation:** Write the design into the vision doc now. Implement at v3.

---

## P1 Findings — Horizon Mapping

### P1-1: Event Reactor Lifecycle Undefined
**Blocks:** v2 (event-driven advancement — Track A3)
**Urgency:** HIGH — this is the single biggest blocker for Level 2 autonomy.
**Why:** Level 2 is "the system does the next obvious thing." Without defining who starts the reactor, who restarts it on crash, and what a downed reactor looks like, Level 2 cannot be safely deployed. The v2 milestone explicitly includes "event-driven advancement."
**Fix complexity:** Medium — design doc in Clavain vision (lifecycle, subscription contract, failure behavior, manual recovery). Implementation follows.
**Recommendation:** Design now, implement at v2. This is the critical path item.

### P1-2: Gate Failure in Reactor Chain — No Escalation Path
**Blocks:** v2 (event-driven advancement)
**Urgency:** HIGH — directly entangled with P1-1.
**Why:** When the reactor hits a failed gate, the run stalls with no notification. This makes Level 2 fragile — silent failures requiring manual discovery defeat the purpose.
**Fix complexity:** Low — add `run.paused` state on gate failure, emit event, surface in TUI. Builds on P1-1's reactor design.
**Recommendation:** Design with P1-1, implement at v2.

### P1-3: Stalled Dispatch Blocks `agents_complete` Gate Permanently
**Blocks:** v2 (event-driven advancement)
**Urgency:** HIGH — any OOM/kill-9 during review dispatch permanently blocks the run.
**Why:** Without reconciliation-aware gate evaluation, Level 2 has no self-healing for crashed agents. v2's dispatch tracking is insufficient without this.
**Fix complexity:** Medium — add `stalled` state, update gate to accept reconciliation-confirmed-dead dispatches, define reconciliation polling interval.
**Recommendation:** Implement at v2 alongside the reconciliation engine.

### P1-4: High-Confidence Bead Auto-Creation Is Action-Before-Notification
**Blocks:** v3 (confidence-tiered autonomy)
**Urgency:** LOW — the discovery pipeline doesn't exist yet.
**Why:** When it does exist, creating beads in `proposed` state instead of `active` is the right pattern. This is a design input for v3.
**Fix complexity:** Trivial — use `proposed` state with auto-promote after timeout.
**Recommendation:** Record in the design doc now. Implement at v3.

### P1-5: Level 2 Auto-Advancement Doesn't Distinguish "Completed" from "Completed Well"
**Blocks:** v2 (sprint kernel-driven)
**Urgency:** MEDIUM — matters when sprint auto-advances past review phases.
**Why:** If the sprint skill auto-advances when dispatches finish (regardless of verdict quality), bad code can pass review. The v2 sprint handover assumes gates are meaningful.
**Fix complexity:** Low — add `verdict_quality` gate condition that checks minimum verdict score. ~50 lines.
**Recommendation:** Implement at v2 as part of gate enhancement.

### P1-6: Durable Consumer Cursors Have 24h TTL
**Blocks:** v2 (Interspect Phase 1)
**Urgency:** MEDIUM — Interspect Phase 1 registers as a durable consumer. A 24h outage loses its cursor.
**Why:** Interspect's value depends on complete event history. A lost cursor means biased data and incorrect routing proposals. The 24h TTL contradicts the "never expire" guarantee.
**Fix complexity:** Low — move durable cursors to a dedicated table without TTL. ~100 lines.
**Recommendation:** Fix at v1.5 before Interspect Phase 1 depends on it.

### P1-7: Autarch Apps Embed OS Agency Logic
**Blocks:** v3-v4 (Autarch migration)
**Urgency:** LOW — the migration hasn't started. This is a design question.
**Why:** If Gurgeh's arbiter stays in the app layer, the "apps are swappable" claim is false. Either acknowledge the transition plan or reclassify the arbiter.
**Fix complexity:** Doc clarification. The actual migration of agency logic to the OS layer is a v3-v4 effort.
**Recommendation:** Fix the doc now (acknowledge transitional state). Migration tracks with v3-v4.

### P1-8: Budget Events Never Emitted (Recorder = nil)
**Blocks:** v2 (token tracking, Interspect Phase 1)
**Urgency:** MEDIUM — token tracking is a v2 deliverable and Interspect needs budget events.
**Why:** `cmdDispatchTokens()` passes `nil` as the event recorder. Budget threshold crossings produce stderr output only. Interspect can't react to budget overruns because the events don't exist.
**Fix complexity:** Low — wire a real `EventRecorder` into the budget checker. Single-file change. ~20 lines.
**Recommendation:** Fix at v1.5 alongside the hook cutover (hooks will call `ic dispatch tokens` more frequently).

### P1-9: "Not a Claude Code Plugin" Contradicts Reality
**Blocks:** v1.5 (API stability contract, open-source readiness)
**Urgency:** MEDIUM — a new contributor reading the vision doc will be confused immediately.
**Why:** The vision says "Clavain runs on its own TUI (Autarch)" as present fact. It doesn't. Autarch TUI isn't functional as the primary interface. This undermines the doc's credibility for the open-source audience at v1.5.
**Fix complexity:** Trivial — rewrite one paragraph to use aspirational framing.
**Recommendation:** Fix now. Pure doc change.

### P1-10: Adaptive Threshold Drift Has No Convergence Bounds
**Blocks:** v3 (confidence-tiered autonomy, backlog refinement)
**Urgency:** LOW — adaptive thresholds aren't implemented yet.
**Why:** When they are implemented, unbounded drift creates filter bubbles. Floor/ceiling bounds and long-tail sampling must be part of the v3 design.
**Fix complexity:** Design input — add convergence bounds to the vision doc. Implementation at v3.
**Recommendation:** Record in the design doc now. Implement at v3.

### P1-11: Gate Override Writes Phase Before Audit Event
**Blocks:** v1.5 (API stability, open-source readiness)
**Urgency:** MEDIUM — `gate override` is the most audit-sensitive code path.
**Why:** A crash between `UpdatePhase` and the event INSERT leaves an advance without audit trail. This violates the "Fail Safe, Not Fail Silent" principle for the exact operation auditors scrutinize.
**Fix complexity:** Low — wrap both operations in a single transaction. ~30 lines.
**Recommendation:** Fix at v1 (current). Same class of bug as P0-1.

---

## Priority Matrix

### Fix NOW (v1 current — correctness bugs in shipped code)

| Finding | Effort | Impact |
|---------|--------|--------|
| P0-1: Dual-write broken | Low | Event bus reliability |
| P1-11: Gate override non-atomic | Low | Audit trail integrity |
| P1-9: "Not a plugin" claim | Trivial | Doc credibility |
| P0-3: Confidence tier doc fix | Trivial | Doc accuracy |

### Fix at v1.5 (1-2 months — before hook cutover increases risk)

| Finding | Effort | Impact |
|---------|--------|--------|
| P0-2: Spawn limits | Medium | Agent proliferation defense |
| P1-6: Durable cursor TTL | Low | Interspect data completeness |
| P1-8: Budget events nil | Low | Token tracking foundation |
| P1-7: Autarch agency logic doc | Trivial | Architecture clarity |

### Fix at v2 (2-4 months — Level 2 deployment prerequisites)

| Finding | Effort | Impact |
|---------|--------|--------|
| **P1-1: Reactor lifecycle** | **Medium** | **Critical path for Level 2** |
| **P1-2: Gate failure escalation** | **Low** | **Level 2 resilience** |
| **P1-3: Stalled dispatch** | **Medium** | **Level 2 self-healing** |
| P1-5: Verdict quality gates | Low | Sprint auto-advance safety |

### Design now, implement at v3 (4-8 months)

| Finding | Effort | Impact |
|---------|--------|--------|
| P0-4: Reward hacking safeguards | Design | Interspect safety |
| P1-4: Proposed bead state | Trivial | Discovery pipeline safety |
| P1-10: Threshold convergence bounds | Design | Filter bubble prevention |

---

## Critical Path Summary

The **single most important finding** for the next milestone is:

> **P1-1 (Event Reactor Lifecycle) blocks v2.**

Without a defined reactor lifecycle, event-driven advancement (Track A3) cannot ship. P1-2 and P1-3 are directly entangled — the reactor needs escalation paths and stalled-dispatch handling to be deployable. These three findings form a cluster that must be resolved together.

The **quickest wins** (fix today, zero risk) are P0-1 and P1-11 — both are transaction boundary bugs that make the current event bus and audit trail unreliable. Combined fix effort: ~2 hours.

The **highest cost of inaction** is on P0-2 (spawn limits). Every day without spawn limits is a day where a misconfigured hook can create 200 concurrent agent processes. The risk increases at v1.5 when hooks start calling `ic dispatch spawn` automatically.

---

## Cost of Inaction (Per Finding)

| Finding | What Happens If Not Fixed | When It Bites |
|---------|--------------------------|---------------|
| P0-1 | Runs stall silently when process dies mid-dispatch | Any OOM/crash today |
| P0-2 | Runaway agent proliferation from hook misconfiguration | Any fan-out hook today |
| P0-3 | Doc claims enforcement that doesn't exist; contributors build on false assumption | When someone reads the doc |
| P0-4 | Interspect learns to skip safety reviews | Interspect Phase 2 (v3) |
| P1-1 | Level 2 cannot be deployed; v2 milestone blocked | v2 planning begins |
| P1-2 | Level 2 runs stall silently on gate failures | v2 deployment |
| P1-3 | Any crashed agent permanently blocks its run | v2 deployment |
| P1-4 | Auto-created beads from bad scores pollute backlog | v3 discovery launch |
| P1-5 | Auto-advance past failed reviews ships bad code | v2 sprint handover |
| P1-6 | Interspect loses event history on 24h+ outage | v2 Interspect Phase 1 |
| P1-7 | "Apps are swappable" claim misleads contributors | When someone tries to build alt-Autarch |
| P1-8 | Token tracking is write-only; no reactive budget enforcement | v2 token tracking |
| P1-9 | New contributors confused by false present-tense claims | v1.5 open-source readiness |
| P1-10 | Discovery filter bubble after ~50 feedback cycles | v3 discovery launch |
| P1-11 | Gate overrides leave no audit trail on crash | Any forced override today |
