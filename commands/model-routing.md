---
name: model-routing
description: Toggle subagent model routing between economy (smart defaults) and quality (all opus) mode
argument-hint: "[economy|quality|status]"
disable-model-invocation: true
---

# Model Routing

<routing_arg> #$ARGUMENTS </routing_arg>

Single source of truth: `config/routing.yaml`.

## `status` (default)

Source `scripts/lib-routing.sh`, call `routing_list_mappings`. Inspect `config/routing.yaml`:
- `defaults.model=sonnet` + economy categories → **economy**
- `defaults.model=opus` + all categories opus → **quality**
- Otherwise → **custom**

Show only phases/categories that deviate from default:
```
Mode: economy
Defaults: research: haiku | review: sonnet | workflow: sonnet | synthesis: haiku
Phase overrides:
  brainstorm: opus (all categories)
```

## `economy`

Cost-optimized defaults: research→haiku, review→sonnet, workflow→sonnet, synthesis→haiku. Brainstorm stays on opus.

```bash
sed -i '/^subagents:/,/^dispatch:/{
  /^  defaults:/,/^  phases:/{
    s/^\(    model:\).*/\1 sonnet/
    /^    categories:/,/^  [a-z]/{
      s/^\(      research:\).*/\1 haiku/
      s/^\(      review:\).*/\1 sonnet/
      s/^\(      workflow:\).*/\1 sonnet/
      s/^\(      synthesis:\).*/\1 haiku/
    }
  }
}' config/routing.yaml

sed -i '/^  phases:/,/^dispatch:/{
  /^\(      model:\).*/s//\1 sonnet/
  /brainstorm:/{n;s/^\(      model:\).*/\1 opus/}
}' config/routing.yaml
```

## `quality`

All agents on opus. Set defaults, then all phase models and category overrides to `inherit`.

```bash
sed -i '/^subagents:/,/^dispatch:/{
  /^  defaults:/,/^  phases:/{
    s/^\(    model:\).*/\1 opus/
    /^    categories:/,/^  [a-z]/{
      s/^\(      research:\).*/\1 opus/
      s/^\(      review:\).*/\1 opus/
      s/^\(      workflow:\).*/\1 opus/
      s/^\(      synthesis:\).*/\1 opus/
    }
  }
}' config/routing.yaml

sed -i '/^  phases:/,/^dispatch:/{ s/^\(      model:\).*/\1 inherit/ }' config/routing.yaml

sed -i '/^  phases:/,/^dispatch:/{ /^        [a-z].*:/{ s/^\(        [a-z][a-z0-9_-]*:\).*/\1 inherit/ } }' config/routing.yaml
```

## Notes

- Takes effect immediately for new dispatches; does not affect running agents
- Economy saves ~5x on research, ~3x on review vs quality
- Individual agents overrideable via `model: <tier>` in Task call
- `fd-safety` and `fd-correctness` always resolve to ≥sonnet regardless of mode (enforced by `agent-roles.yaml`)

## Capability-routing doctrine (frontier-tier sessions)

When a frontier-tier model (fable) is available — especially during a limited window — its capacity is the scarce resource. Route by capability, not habit:

| Role | Tier | Why |
|------|------|-----|
| Planning, plan review (/flux-review), architecture, cross-repo synthesis | fable | Small token volume, maximum downstream leverage — a bad plan multiplies cost through every later stage |
| Execution of execution-grade plans | sonnet | Bulk of token volume; near-opus on coding/agentic; ~5x cheaper than fable |
| Validation of execution | opus | Verification asymmetry: checking against explicit criteria is cheaper than producing the work — but only if criteria exist |
| Escalation target | fable | See two-strikes rule below |

**Rules:**

1. **Validators check against the plan's acceptance criteria** (`<verify>` blocks, Must-Haves), never their own judgment. The plan author writes the criteria at plan time; the validator only confirms them.
2. **Two-strikes escalation:** executor fails a task 2x, or validator rejects 2x → escalate the item to the frontier tier and record the failure mode. Never loop cheap retries — they aren't cheap.
3. **Hard-problem exception:** work that previously stalled on lesser models does NOT get the split — the frontier model stays in the execution loop or reviews every diff itself. A validator can only catch what it can understand.
4. **Small-task lane:** tasks under ~30 min of agent time skip the pipeline; one model end-to-end. Handoff overhead exceeds the savings.
5. **Plans are written for a weaker executor** — the pipeline's silent failure mode is a plan that assumes frontier judgment. `writing-plans` already enforces exact paths, complete code, and machine-checkable verify blocks; do not relax those when the plan author is a frontier model.
6. **Pilot before batching:** before fanning a plan backlog out to cheap executors, run 2-3 items through the full loop (plan → review → execute → validate → land) and fix the plan template while the frontier model is still available.
7. **Measure plan→execution pass rate** (interspect delegation calibration), not just shipped count — it's the signal that the doctrine is holding.

## Routing-table v2 — cross-provider (2026-07-27)

Source: flux-melange `subsidized-fleet-orchestration` (3 rounds + 3-round parley
vs a gpt-5.6-sol mirror; 24/31 findings upheld; contested collapsed 7→2→1) plus
pilot-1 evidence and primary-source pool facts. Entries carry `verified_at` and
expire — model facts here rot in weeks, not quarters (K3 launched 07-16,
GPT-5.6 07-09; consensus 16).

### Pool facts (verified 2026-07-27, support.claude.com art. 15424964; mirrored in `ic state get model.fable.pool global`)

- ONE shared weekly pool for all Claude models on Max. Fable is **standing
  capacity since 2026-07-20** (the "limited window" era is over), sub-capped at
  **50% of the weekly pool**, and drains **both** buckets per call. Drawdown
  rate is unpublished — measure, don't assume. Overflow = usage credits or
  model switch.
- Consequence: "preserve the frontier window" and "burn the frontier window"
  were opposite claims about the same resource. The scarce resource is the
  pool; Fable tokens are its most expensive drain.

### Role table (dose column mandatory — a share without a reserve is unenforceable, a reserve without a share protects nothing; consensus 7)

| Role | Runtime/model | Dose & reserve | Basis |
|------|--------------|----------------|-------|
| Main thread / orchestration | Opus (1M) — interim operating choice, NOT a verdict; Q1 settles by dose data, not a winner (parley item 20) | n/a | inheritance safety (unpinned spawns inherit main model), token volume, context headroom |
| Plan authoring | fable, fallback opus (`strategized` phase) | measure; provisional: reserve ≥1 fable call/window for escalation | §1 asymmetry; plan defects replicate into every consumer |
| **Gauge dry-run + review** | `plan-gauge-lint.py` (mechanical, blocking) THEN any model ≠ plan author | lint every plan; 1 review per plan, both before freeze | pilot-1 rounds 1+2: 4/4 frontier-authored plan-executions struck out on the plan's OWN verify block, never on code (~60 edits byte-exact, zero drift). 6 gauge defects observed; 5 are "emitted text vs. a checker the same author wrote". Reviewing caught none of them across two rounds — the linter replays all 6. The verify block is a replicated, marking-grade artifact: an omission in it passes every downstream check (consensus 2/3) |
| Plan review verdict | fable, fallback opus (`planned` phase); lens pools stay sonnet/haiku | dose guard in routing.yaml | leverage vs dose explosion |
| Execution (execution-grade plans) | sonnet in-harness | bulk | measured 0.909 (n=11) |
| Validation | opus, against FROZEN criteria only | per plan | verification asymmetry; criteria frozen before execution, exogenous to the treatment in any A/B (parley item 33) |
| Scouts — correctness (recuttable) | haiku / cheap lane | wide | wrong candidates leave artifacts a verifier can reject |
| Scouts — coverage (propagates) | frontier or adversarial second scout | narrow | omitted candidates leave NO artifact; verification cannot see gaps (f-030, consensus 4). Pattern D requires a coverage adversary, not just a frontier synthesizer |
| Cross-lab second review at gates | gpt-5.6-sol via codex peer (sandboxed) — reviewer must RE-DERIVE from requirements, never inspect the incumbent plan (consensus 10); K3 via kimi CLI lane (interflux ≥0.2.85) as third seat when warranted | gate-tier only | sealed first-pass + disposition field (upheld/dismissed), never raw disagreement counts (consensus 11) |
| Escalation / tie-break | fable | reserve-protected | two-strikes, with STRIKE TAXONOMY below |

### Rules added in v2

8. **Strike taxonomy (consensus 8):** a strike = capability or premise failure
   ONLY. Sandbox denials, approval-gate blocks, auth expiry, rate exhaustion,
   and infra errors are NOT strikes — counting them escalates to the scarcest
   tier for problems that are not capability failures.
9. **Gauge DRY-RUN before freeze** (strengthened 2026-07-27 by pilot-1 round 2):
   the plan's verify blocks are **executed against the plan's own emitted
   output** — `scripts/plan-gauge-lint.py <plan> --repo-root <repo>`, blocking,
   wired as step 0 of `/plan-review` — and only then reviewed by a model other
   than the author, and frozen. In any A/B the gauge is authored by NEITHER arm
   and runs unmodified against both.

   Reading the gauge is not the control. Round 1 struck out both arms on gauge
   defects; those gauges were repaired; **round 2 struck out both arms again, on
   a third gauge defect each.** Six observed in total, five of one shape: *the
   plan's emitted text is simultaneously the artifact and an input to a checker
   the same author wrote, and nobody ever executed one against the other.* Two
   frontier-tier authors, a frontier-tier reviewer, and the harness itself each
   shipped an instance — so this is not an author-tier weakness a better
   reviewer fixes. It is n=6 that reading cannot see it and execution can.
   Meanwhile ~60 edits applied byte-exact across all four executions with zero
   drift: the code was never what failed.
10. **Panel protocol:** sealed first-pass findings with a validated schema and
    a disposition field; parley terminates semantically (one blind round, at
    most one response round, then an executable falsifier or a human decision;
    unresolved high-blast dissent fails closed — consensus 13). Manifests state
    each arm's approval surface and filesystem scope (parley item 38: a
    sandboxed reviewer sees less and objects more; the metric reads that as
    cross-lab value).
11. **Peer-runtime constraint (measured live):** unsandboxed peer templates
    (`hermes --yolo`) are blocked by the harness safety classifier when spawned
    from subagents; sandboxed codex (`--full-auto`, workspace-write) passes
    with warnings. Compose panels from sandboxed or HTTP/OAuth lanes.
12. **z.ai re-entry gate (consensus 41):** three triggers — executor-capacity
    bottleneck; a missing epistemic role under a predeclared gauge;
    availability (premium buckets exhausted with gauge-ready work queued).
    None fires as of 2026-07-27 (pool at 54%/20%/16%). Never env-swap the main
    Claude profile (consensus 43).
13. **Patterns compose:** A–C are base session architectures; D (scout
    fan-out), E (gate panel), F (execution routing) are overlays on a base
    (consensus 9). Pattern F requires a named integration owner (consensus 14).

Open (explicitly unresolved): Q1 dose values for Fable-main vs Opus-main;
provider-diversity vs panel-policy estimand for the review pilot (last live
contested topic); drawdown rates per lane. These close on measurement, not
argument.
