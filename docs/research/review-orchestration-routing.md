# Orchestration and Routing Review — fd-orchestration-routing

**Date:** 2026-02-19
**Reviewer role:** Multi-agent orchestration specialist
**Documents reviewed:**
- `/root/projects/Interverse/hub/clavain/docs/vision.md` (Clavain OS — model routing, macro-stages, fleet)
- `/root/projects/Interverse/infra/intercore/docs/product/intercore-vision.md` (Intercore kernel)
- `/root/projects/Interverse/infra/intercore/docs/product/autarch-vision.md` (Autarch apps)
- Supporting implementation: `internal/dispatch/dispatch.go`, `internal/dispatch/spawn.go`, `cmd/ic/dispatch.go`, `internal/budget/budget.go`, `config/dispatch/tiers.yaml`, `skills/using-clavain/references/routing-tables.md`

---

## Summary

The three-document vision describes a coherent, well-structured orchestration stack. The kernel/OS/profiler separation is architecturally sound and the mechanism/policy split is cleanly stated throughout. However, there are meaningful gaps between what is promised at the vision layer and what is enforced at the implementation layer. The most critical gap is **spawn limits: mentioned as planned but absent from the current dispatch implementation**. Secondary concerns include the cost arithmetic behind the "12 agents cheaper than 8" claim, the underspecified fan-out failure semantics, and the model selection criteria being narrative rather than algorithmic.

---

## Finding 1 (P0): Spawn Limits Described as Enforced — Not Implemented

**Claim (Intercore vision, Resource Management section):**
> "Hard limits on agent proliferation: Maximum spawn depth... Maximum children per dispatch (fan-out limit)... Maximum total agents per run. These are kernel-enforced invariants, not suggestions. An agent cannot bypass them regardless of what the LLM requests."

**Reality in code (`internal/dispatch/spawn.go`, `cmd/ic/dispatch.go`):**
The `Spawn()` function inserts a record and starts a process. There is no pre-spawn check against any concurrency limit. `cmdDispatchSpawn()` parses flags and calls `dispatch.Spawn()` directly — no `ListActive()` call, no count comparison, no enforcement path. The `--parent-id=` flag is accepted and stored, but parent-child depth is not traversed or bounded.

The Dispatch struct carries `ParentID *string` for lineage tracking, but the only place active dispatches are listed is `ListActive()`, which is a read-only query used by `cmdDispatchList`. Nothing calls it before spawning.

**Concrete scenario:** An OS-level hook misconfigured to spawn review agents per-file on a 200-file diff would create 200 concurrent agent processes. The kernel would record all of them and report their token usage, but nothing would prevent the spawn. The budget checker runs *after* tokens are reported (post-completion), not at spawn time.

**Severity:** P0. The vision markets this as a kernel-enforced safety property. It is not yet enforced. Any scenario where the OS layer over-fans (a review command on a large diff, an event reactor that re-queues on each incoming event, a prompt that tells an agent to spawn subagents) will run unchecked until the budget checker fires post-completion — which is too late to prevent the resource spike.

**What is needed:**
- A `CountActive(ctx, scopeID)` query in `dispatch.Store`
- A `SpawnLimits` struct (max_concurrent_per_run, max_depth, max_total) that `Spawn()` accepts and enforces before record creation
- A depth-traversal helper that walks `parent_id` chains to compute current depth
- Rejection with a structured error (not silent failure) when limits are exceeded, recorded as a rejected spawn event

---

## Finding 2 (P1): Fan-Out Partial Failure Semantics Are Unspecified

**Claim (Intercore vision, Dispatch section):**
> "Fan-out tracking — parent-child dispatch relationships for parallel agent patterns."
> "Verdict collection — structured results collected from completed dispatches."

**Claim (Clavain vision, Dispatch Topology section):**
> "Does the fan-out model handle partial failure, asymmetric completion, result aggregation?"

**Reality:**
The `parent_id` relationship is stored, but the kernel provides no semantic for what happens when some children complete and some fail. The `agents_complete` gate check (referenced in Intercore vision under Gates) verifies "are all active agents finished?" — but does not distinguish complete/failed/timeout outcomes within the fan-out group.

The `HasVerdict()` method checks for at least one non-rejected verdict across the scope. In a 7-agent flux-drive review where 2 agents timeout, `HasVerdict()` returns `true` if any 1 of the remaining 5 produced a verdict. The gate passes. The 2 timeouts are silently dropped from the analysis.

**Concrete scenario:** A flux-drive review dispatches 7 fd-* agents against a large diff. The fd-safety and fd-correctness agents (the two most expensive and most critical) hit their timeout. The remaining 5 complete. The `agents_complete` gate fires (no spawned/running dispatches remain). `HasVerdict()` returns true. The run advances to Ship with no safety or correctness analysis. The Interspect evidence log will show 2 timeout events, but no automatic action prevents the phase advance.

**What is needed:**
- A `ChildrenStatus(ctx, parentID)` query returning per-child terminal status
- Configurable fan-out completion policy: `all_must_complete`, `quorum(n)`, `any_success`. Currently hardcoded to "gate passes when no active dispatches remain plus any verdict exists"
- Hard gate variants that treat timed-out agents as failures when they are in critical roles (fd-safety, fd-correctness)
- At minimum, the vision should be updated to document the current behavior (any-success semantics) so OS-layer operators know what they are building against

---

## Finding 3 (P1): Token Tracking Is Self-Reported and Fire-and-Forget

**Claim (Intercore vision, Cost and Billing section):**
> "Per-dispatch token counts (input, output, cache hits) — self-reported by agents"

**Reality in code (`internal/budget/budget.go`, `cmd/ic/dispatch.go`):**

The budget checker is invoked from `cmdDispatchTokens()` — it only runs when someone calls `ic dispatch tokens <id> --set --in=... --out=...`. Nothing in `Spawn()` or `UpdateStatus()` triggers a budget check. If an agent never calls `ic dispatch tokens`, the budget is never evaluated for that dispatch.

Additionally, `emitEvent()` in the budget checker is fire-and-forget:
```go
func (c *Checker) emitEvent(ctx context.Context, runID, eventType, reason string) {
    if c.recorder != nil {
        c.recorder(ctx, runID, eventType, reason) // error ignored
    }
}
```
The `recorder` is passed as `nil` in `cmdDispatchTokens()`:
```go
checker := budget.New(pStore, dStore, sStore, nil)
```
So `budget.warning` and `budget.exceeded` events are never emitted to the event bus, even if the threshold is crossed. The check produces stderr output, but no kernel event is written. Interspect cannot react to budget crossings because the events do not exist.

**Severity:** P1. The budget system exists but is not wired to actually emit events or enforce limits. "The kernel emits events when thresholds are crossed" (Intercore vision) is currently false — stderr output is not an event.

**What is needed:**
- Wire a real `EventRecorder` into the budget checker in `cmdDispatchTokens()`
- Consider triggering a budget check from `UpdateStatus()` when a dispatch reaches a terminal state, not only from explicit token-set calls
- Document the self-reporting assumption explicitly in the spawn interface so OS-layer callers know they are responsible for calling `ic dispatch tokens` at agent completion

---

## Finding 4 (P2): Three-Layer Routing — Layer 3 (Adaptive) Has No Implementation Path

**Claim (Clavain vision, Model Routing Architecture):**
> "Layer 3: Adaptive Optimization — The agent fleet registry stores cost/quality profiles per agent×model combination. The composer optimizes the entire fleet dispatch within a budget constraint. 'Run this review with $5 budget' → the composer allocates Opus to the 2 highest-impact agents and Haiku to the rest. Interspect's outcome data drives profile updates."

**Current state:**
- Layer 1 (kernel dispatch records with model field): implemented
- Layer 2 (static tier config in `config/dispatch/tiers.yaml`): implemented as a 4-tier YAML file — but this file is read by `dispatch.sh` (bash), not by the kernel. The kernel stores the model string per dispatch but does not read or enforce tier config. Layer 2 is currently a convention, not a policy mechanism.
- Layer 3 (Composer, fleet registry, budget-aware allocation): does not exist. Not in roadmap with a concrete milestone — it appears as Track B/C convergence at C3, which depends on B1, C1, and C2, none of which are implemented.

**The gap in Layer 2:** `config/dispatch/tiers.yaml` defines four tiers. But the routing table in `skills/using-clavain/references/routing-tables.md` maps stages to agents and commands — it does not map to tier names. There is no enforcement that "fd-architecture defaults to Opus" as stated in the vision. An operator could dispatch all agents on `fast` tier by passing the wrong `--model` flag and the kernel would accept it without complaint.

**Concrete scenario:** Layer 2 is described as "Plugins declare default model preferences." But there is no plugin schema field for model preference. When interflux dispatches fd-architecture, the model choice lives in the interflux skill text or the operator's dispatch invocation, not in a kernel-readable declaration. A routing regression (wrong model used for an agent) would not be detectable from kernel event data alone.

**What is needed before claiming Layer 2 is implemented:**
- A per-agent default model preference stored as kernel-readable metadata (not just in a bash YAML file)
- A validation step in dispatch spawn that compares the requested model against the declared default and logs divergence as a routing event
- The tiers.yaml model names (`gpt-5.3-codex-spark`, `gpt-5.3-codex`) do not match the Clavain vision model taxonomy (Gemini, Opus, Codex, Haiku, Oracle). This is either a naming discrepancy or the tiers.yaml is the actual production tier mapping and the vision's model taxonomy is aspirational. This needs clarification.

---

## Finding 5 (P2): "12 Agents Cheaper than 8" — Arithmetic Not Grounded

**Claim (Clavain vision, Operating Principles #3):**
> "12 agents should cost less than 8 via orchestration optimization, and catch more bugs."

**What this requires:**
For 12 agents to cost less than 8, the delta in agent count (4 extra agents) must be more than offset by model downgrade savings. The math:

If 8 agents all run on Opus at (hypothetically) $15/MTok output and the 4 additional agents run on Haiku at $0.25/MTok output while 4 of the original Opus agents are downgraded to Sonnet at $3/MTok:

- Baseline (8 Opus): 8 × C_opus
- Optimized (12 agents, mixed): 4 × C_opus + 4 × C_sonnet + 4 × C_haiku

For this to hold, the per-agent token consumption and output quality must be well-characterized. Without the "agent fleet registry" (C2 on the roadmap, not yet built), there is no empirical basis for the claim. The Composer (C3, not yet built) is the mechanism that would actually produce this optimization.

**The claim is aspirational, not a current capability.** Stated as a design principle it is fine. Stated as a system property it needs the following:
- Empirical cost/quality profiles per agent×model pair (requires many runs of data)
- The Composer implementation (C3) that actually performs the optimization
- A baseline measurement system to validate the claim (currently no `tokens_per_impact` metric infrastructure exists)

**Risk:** If developers treat this as a current property and use it to justify dispatching larger agent fleets, they will get the 12-agent cost without the optimization, which is strictly more expensive than 8 agents.

**Recommendation:** Qualify this claim in the vision doc: "12 agents should cost less than 8 via the Composer (roadmap C3) — not yet implemented. Current multi-agent dispatches are not cost-optimized across the fleet."

---

## Finding 6 (P2): Cross-Phase Handoff Protocol — Not Specified

**Claim (Clavain vision, Agency Architecture Track C):**
> "C4 — Cross-phase handoff — structured protocol for how Discover's output becomes Design's input"
> "Each macro-stage is a sub-agency with its own model routing, agent composition, and quality gates."

**Reality:**
The handoff protocol between macro-stages is described in one roadmap item (C4) with no sub-specification. The vision gives tables of models-per-stage capability but does not address:

1. What is the artifact schema that Discover produces for Design to consume?
2. How does Design know that Discover's output is complete vs partial?
3. When Discover's research pipeline produces discoveries of varying confidence, which ones gate Design's ability to start?
4. If Design rejects Discover's output ("not enough research"), does that reset Discover or does the human intervene?

**Concrete scenario:** The discovery pipeline auto-creates a bead at confidence >= 0.8. A Design run starts from this bead with only an auto-generated briefing doc as its artifact. Gurgeh begins PRD generation from an incomplete research base. The gate that should block Design until Discover's briefings reach a quality threshold is described as OS policy, but no specification of that policy exists.

The Intercore vision acknowledges this with "C4 depends on C1 (agency specs)" — meaning agency specs must define what each stage produces and consumes. But agency specs are also unimplemented.

**Severity:** P2 for now (future work), but this is a prerequisite for C5 (self-building) and the entire autonomous development pipeline. The handoff gap means each macro-stage is currently manually initiated, which removes the "autonomous" property from the agency.

---

## Finding 7 (P2): Model Selection Criteria Are Narrative, Not Algorithmic

**Claim (Clavain vision, Operating Principle #6):**
> "Gemini's long context window for exploration and research. Opus for reasoning, strategy, and design. Codex for parallel implementation. Haiku for quick checks and linting. Oracle for high-complexity cross-validation."

**The routing tables (`skills/using-clavain/references/routing-tables.md`) do not encode these criteria.** The routing table maps stage/domain/concern to agent names, not model names. The agent-to-model assignment is:
- Declared in agent frontmatter (`model: inherit` in most cases per the AGENTS.md)
- Overridden at dispatch time by the caller's `--model` flag
- Partially captured in `tiers.yaml` as a bash config file

There is no heuristic that selects Gemini when context length exceeds a threshold, no rule that escalates to Oracle when complexity reaches level N, no classifier that distinguishes "linting task → Haiku" from "architectural reasoning → Opus."

**What this means operationally:** The model selection described in the vision is currently a documentation claim, not an implemented routing behavior. A Claude agent reading the vision and then dispatching fd-architecture will use whatever model is configured in the agent's frontmatter or the default tier — which in `tiers.yaml` is `gpt-5.3-codex-spark` (the fast tier for read-only tasks) or `gpt-5.3-codex` (the deep tier). Neither is "Opus" — the vision's model taxonomy and the tiers.yaml model names do not correspond to the same model set.

**The tiers.yaml models are Codex/GPT models.** The vision describes Claude Opus, Gemini, Haiku as the routing targets. This is a real discrepancy: either the tiers.yaml represents the actual dispatch infrastructure (Codex-based), or the vision model taxonomy (Claude/Gemini/Oracle) represents a future multi-backend state. This needs to be reconciled explicitly in both documents.

**What is needed:**
- Acknowledge in the vision that the current dispatch backend is Codex-only (via `dispatch.sh`)
- Map the tier names to their current model equivalents (fast = "exploration/linting tier", deep = "implementation/reasoning tier")
- Define the complexity heuristics that will drive model escalation (B2 on the roadmap)

---

## Finding 8 (P2): Discovery Pipeline Fan-Out Has No Rate Limiting

**Claim (Clavain vision, Discovery section — three trigger modes):**
> "Event-driven (reactive): run.completed triggers search for related prior art. bead.created checks for existing research. dispatch.completed with novel techniques triggers prior art search. discovery.promoted triggers related-discovery search."

**The problem:** Each of these event types can trigger a discovery scan, which itself produces discovery events, which can trigger further scans. The vision explicitly states "Event-driven scans are targeted; scheduled scans cast a wide net" — but does not describe the feedback prevention mechanism.

Consider:
- `discovery.promoted` triggers related-discovery search
- Related-discovery search promotes a new discovery
- New `discovery.promoted` triggers another related-discovery search
- This continues until the source trust / embedding similarity falls below threshold

The discovery pipeline does not have a stated re-entrancy guard. The confidence-tiered autonomy gates prevent unbounded auto-creation of beads (only high-confidence discoveries auto-create), but the scan loop itself is not bounded. Each scan invokes external sources (arXiv, HN, Exa) which have their own rate limits, but the kernel-side trigger chain is unguarded.

**Severity:** P2 for the current implementation (discovery pipeline is not yet wired to kernel events, per the vision's own acknowledgment: "What's missing is kernel integration"). But this gap must be addressed before event-driven discovery is activated or the event-triggered scan volume will be unpredictable.

**What is needed:**
- A sentinel (kernel coordination mechanism already exists) that rate-limits event-driven discovery scans: "at most one event-driven scan per N minutes per trigger type"
- A depth counter on discovery chains: "this discovery was triggered by discovery D42; do not scan again for discoveries triggered by discoveries triggered by D42"
- Explicit documentation of the fan-out prevention mechanism before event-driven triggers are enabled

---

## Finding 9 (P3): "Agency Specs" Concept Is Not Tractable Without Schema

**Claim (Clavain vision, Track C):**
> "C1 — Agency specs — declarative per-stage config: agents, models, tools, artifacts, gates"

The vision does not provide a schema or example for an agency spec. For this to be tractable:
- The spec must be machine-readable (not prose documentation)
- The kernel must validate the spec at run creation time, not at execution time
- Agent names in the spec must resolve to actual dispatch targets (the kernel must know what "fd-architecture" means as a dispatchable target, including which binary to call, which model to use, what sandbox to apply)

Currently, agent names exist in markdown frontmatter in plugin directories. The kernel has no registry of agent names. `ic dispatch spawn` takes `--name=fd-architecture` as a label, not as a lookup key into a registry.

**Impact:** Without a machine-readable agent registry, the Composer (C3) cannot query "what does fd-architecture cost on Opus vs Sonnet vs Haiku?" The fleet registry (C2) is the prerequisite, but it requires a schema definition that does not exist in any of the three documents.

**Recommendation for C1:** Define a minimal agency spec schema before implementation. At minimum: `{ stage: string, agents: [{name, model, role: "critical"|"informational", timeout}], gates: [...], artifacts: [...] }`. The `role` field is important — it determines partial-failure semantics (critical agents failing should block phase advancement; informational agents failing should warn but not block).

---

## Finding 10 (P3): Event Retention and Stale Durable Consumer — Operational Gap

**Claim (Intercore vision, Events section):**
> "The kernel guarantees that no event is pruned while any durable consumer's cursor still points before it. This means a durable consumer that falls behind can block event pruning — the OS should monitor consumer lag and alert on stale durable consumers."

**The risk:** Interspect registers as a durable consumer. If Interspect is not run for an extended period (a week of intensive development without profiling), its cursor falls behind. Events cannot be pruned. The event log grows unboundedly. For a project with many dispatches (a full sprint with 12-agent reviews per phase, 8 phases), the event volume per sprint could be 96+ dispatch events plus phase transitions and gate evaluations — on the order of 200-500 events per sprint. At one sprint per day, the 30-day retention period produces 6,000-15,000 events before pruning. If Interspect is not running, these cannot be pruned.

**This is acknowledged in the vision** ("the OS should monitor consumer lag and alert on stale durable consumers") but no specific monitoring mechanism, alert threshold, or automatic stale-consumer cleanup is described. The operational burden lands on the OS without a concrete runbook.

**Recommendation:** Define a maximum allowed cursor lag for durable consumers (e.g., 7 days). After the lag threshold, emit a `consumer.stale` event and allow pruning to proceed past the stale cursor. Record the cursor position when pruning bypasses it, so the stale consumer can detect the gap on next poll and decide whether to replay from available events or accept the loss.

---

## Architecture Assessment: What Is Sound

The following architectural claims are well-founded and do not require qualification:

**The kernel/OS separation is correct.** Having Intercore provide mechanism (spawn, gate check, event emit) with Clavain providing policy (which agents, what gates, when to advance) is the right separation for an evolvable system. Interspect reading kernel events without modifying the kernel is a clean read-only profiler pattern.

**The linear phase chain is appropriate.** Deferring DAG support until real workflows demand it is the right call. Linear chains with skip primitives cover the known use cases without the convergence gate complexity that DAGs require.

**Event-based observability is the right foundation.** Every state change producing a typed event, consumed by independent observers (TUI, Interspect, relay) without coupling — this is a proven architecture for this problem class. The cursor-based at-least-once delivery is appropriate for the CLI model.

**The big-bang hook cutover rationale is sound.** Dual-path state management (temp files + `ic`) would create consistency hazards that outweigh migration risk. The clean-cutover approach is harder to execute but produces a cleaner system.

**Token tracking as infrastructure, not policy.** The kernel records token counts and emits budget events; the OS decides the response. This is the right layering — the kernel should not make cost-effectiveness decisions.

**The macro-stage model selection rationale is plausible.** Gemini for long-context exploration, Codex for parallel implementation, and Oracle for cross-validation reflect real model capability differences. The taxonomy is aspirational but directionally correct.

---

## Priority Summary

| Finding | Priority | Impact | Status |
|---------|----------|--------|--------|
| Spawn limits described but not implemented | P0 | Unbounded agent proliferation under OS misconfiguration | Missing enforcement code |
| Fan-out partial failure semantics unspecified | P1 | Critical review agents can silently drop; phase advances with incomplete analysis | Missing gate semantics |
| Budget events never emitted (recorder=nil) | P1 | Budget tracking exists but events don't reach Interspect | Wiring bug in dispatch.go |
| Layer 2/3 routing — tiers.yaml model mismatch with vision taxonomy | P2 | Model selection claim is aspirational; current backend is Codex-only | Documentation gap + impl gap |
| "12 agents < 8" cost claim lacks arithmetic basis | P2 | Risk of over-fanning in expectation of cost that won't materialize | Composer not built |
| Cross-phase handoff protocol unspecified | P2 | Autonomous stage-to-stage execution blocked | Prerequisite for C5 |
| Model selection criteria are narrative, not algorithmic | P2 | Routing is manual convention, not enforced policy | B2 not started |
| Discovery event loop has no re-entrancy guard | P2 | Potential scan fan-out when event-driven triggers activate | Pre-activation blocker |
| Agency specs need schema before C1 implementation | P3 | C1-C3 tractability requires this | Design gap |
| Stale durable consumer handling not operationalized | P3 | Unbounded event log growth in extended periods | Runbook gap |

---

## Recommended Immediate Actions (Pre-v1.5)

1. **Add spawn limit enforcement to `Spawn()`** — Add `CountActive(ctx, scopeID)` to the dispatch store and check it against a configurable `max_concurrent_per_run` before creating the dispatch record. Reject with `ErrSpawnLimitExceeded`. This is the P0 fix and protects all other features that rely on controlled fan-out.

2. **Wire event recorder in budget checker** — In `cmdDispatchTokens()`, pass a real `EventRecorder` function that calls `ic events` (or the internal event store directly). `budget.warning` and `budget.exceeded` events must flow to the event bus, not just stderr, for Interspect to react.

3. **Document fan-out completion semantics explicitly** — Before shipping any multi-agent review workflow against real projects, document the current behavior: "gates pass when no dispatches are in spawned/running status AND at least one non-rejected verdict exists." Make clear this is any-success semantics, and that timed-out critical agents do not block advancement. Operators need to know this.

4. **Reconcile vision model taxonomy with tiers.yaml** — The vision says Opus/Gemini/Haiku/Oracle; tiers.yaml says gpt-5.3-codex-spark/gpt-5.3-codex. Add a comment to tiers.yaml mapping tier names to the vision's model roles, or update the vision to use the actual model tier names. This prevents confusion when contributors read both documents.

5. **Add discovery re-entrancy sentinel before enabling event-driven triggers** — Before connecting discovery.promoted events to new scan triggers, add a sentinel (already exists in intercore) that blocks re-trigger within a configurable window. The mechanism is already designed; it just needs to be applied.
