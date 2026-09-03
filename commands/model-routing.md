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

Cost-optimized defaults: research→haiku, review→sonnet, workflow→sonnet, synthesis→haiku. Doctrine phases (brainstorm, strategized, planned) are never rewritten by a mode toggle — see § Routing-table v2 (Sylveste-0pk).

```bash
bash "${CLAUDE_PLUGIN_ROOT:-.}/scripts/routing-mode.sh" economy
```

## `quality`

All agents on opus. Sets defaults, then non-doctrine phase models and category overrides to `inherit`; brainstorm, strategized, planned keep their doctrine entries (Sylveste-0pk).

```bash
bash "${CLAUDE_PLUGIN_ROOT:-.}/scripts/routing-mode.sh" quality
```

## Notes

- Takes effect immediately for new dispatches; does not affect running agents
- Economy saves ~5x on research, ~3x on review vs quality
- Individual agents overrideable via `model: <tier>` in Task call
- `fd-safety` and `fd-correctness` always resolve to ≥sonnet regardless of mode (enforced by `agent-roles.yaml`)
- Mode toggles go through `scripts/routing-mode.sh`, which skips the doctrine phases; tested in `tests/shell/routing_mode.bats`.

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


## Measured 2026-09-03 — Pattern F pilots (goal 1b53da77)

Source: transcript profile of this Mac, 2026-08-04..09-03 (87K assistant messages, `interstat/scripts/profile.py`), then five executor runs through the offload shape in one session. Charter and journal: `Sylveste/docs/goals/2026-09-03-main-thread-offload-{charter,journal}.md`. Design doc: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md`; melange review under `docs/research/flux-melange/main-thread-offload-pattern-f/`.

**Baseline (30 days).** Main thread = 85% of API-equivalent spend and 95% of generated tokens; subagents 15% / 5%. ~85% of main-thread cost is context (cache read + cache write) at 220–320K per turn. The phase table in `routing.yaml` binds only subagent spawns, so it governed the 15%. Fable 5.1 cache reads are $0.25/MTok (Opus 5 $0.50, Fable 5 $1.00): normalized to one turn shape, Fable-5.1-main runs ~1.4–1.9× Opus-5-main and cheaper than Fable-5-main did. Swapping the main model is not the lever; fewer, smaller main-thread turns are.

**Pilots (5 executor runs: 3 pilots + 2 fix-forwards).** Sonnet executors applied every execution-grade plan verbatim — 5/5 code-correct, zero drift. Two runs were blocked by a defect in the plan's own VERIFY block (a grep count the plan's text could not produce; a table-state assertion unreachable because of pruned files and a concurrent old-parser writer). That is pilot-1's finding again: the gauge, never the code. Opus validators passed all five on criteria and found six real defects the gauges did not check; two became fix-forward pilots (1b, 3b). Q-A had the wrong premise (melange consensus, both runtimes): the validator's *replay* of the verify block added no information — 5/5 PASS, as the design predicted — while its second channel, "what the gauge did not check", surfaced six defects. The doctrine should name that channel as a validator output (melange f-008, f-013) rather than credit "the validator".

**Goal-window profile (session aa2bb078 from 18:06:55Z).**

| lane | msgs | output | ctx/turn | $ equiv |
|---|---|---|---|---|
| main (Fable 5.1) | 38 | 87K | 344K | 19 |
| executors + validators (Sonnet 5 / Opus 5 / Haiku) | 275 | 7K | 44–95K | 10 |
| melange review workflow (excluded from the gate) | 616 | 10K | — | 28 |

- Main-thread share of **API-equivalent cost: 65%** execution-only — main vs its own executors and validators (baseline 85%). An earlier reading of 35% counted the melange review's 616 agent messages as offloaded execution; the parley's moderator caught the same drift ("the exchange about the gate moved the gate"). With the review included the share is 33%, a number that measures review fan-out, not offload.
- Main-thread share of **generated tokens: 92%** execution-only (83% with the review; baseline 95%). **The goal's gate (≤50%) is NOT met — not on its literal metric, and not on the cost-share replacement proposed below.**

**Why the gate metric was wrong (recorded, not excused).** With execution-grade plans the executor copies code the orchestrator already wrote, so generated tokens follow *plan authorship*, not execution. Offload moves context volume — the 300K re-read per turn — off the main thread; it cannot move authorship. The number that tracks the doctrine's intent is the main-thread share of cost (or of context volume) per goal, read from `profile.py`. **Proposed replacement gate, for mk to ratify, not ratified here:** main-thread share of API-equivalent cost per goal ≤ 50%, execution lanes only (review workflows excluded), with the small-task lane (rule 4) exempt — paired, per melange f-006/f-032, with a context-volume companion (main-thread cache-read tokens per goal). Reading of this run: offload alone moved the main thread from 85% to 65% of cost. Below 50% needs the orchestrator's own context to shrink — 38 turns at 344K cost $19 against $10 for every executor and validator combined — which means a fresh session or compaction per goal, not more delegation (usage panel: 66% of this account's usage ran at >150K context).

**Q1 (Fable-main vs Opus-main dose).** API-equivalent side closed: ~1.4–1.9× per turn at this workload shape. Pool drawdown remains unmeasured — the agent cannot read `/usage`; mk's start/end-of-week readings close it or it stays open.

**Q1 start reading (mk, `/usage`, 2026-09-03 ~11:45 PT).** Week (all models) **78%** used; week (Fable) **96%** used; both reset Sep 5 12:00 PT; +50% weekly-limit promo through Sep 13. Session (4h wall, this goal plus the verdict goal before it): $87.79 — Fable 5.1 main $26.61, Sonnet subagents $24.24, Opus subagents $30.21, Haiku $4.10, Fable 5 $2.63 → main-thread cost share **30%**, agreeing with profile.py's 35%. Two facts the API-equivalent view could not show: (1) the Fable sub-cap is the binding constraint — 96% consumed against 78% of the shared pool with two days left, so Fable-main across parallel sessions exhausts the Fable bucket before the week ends while the pool still has headroom; (2) Claude Code bills the main thread's cache writes at the 1-hour-TTL rate (2× base: $20/MTok on Fable 5.1 — the $26.61 reconciles only at that rate) and subagents at the 5-minute rate (1.25×), so profile.py's flat cache-write rate undercounts the main lane by ~$5.6 on this session. Usage-page attribution for the last 24h: 83% from subagent-heavy sessions, 68% while 4+ sessions ran in parallel, 66% at >150K context, 18% from interflux, 11% from workflow subagents. End-of-week reading due before Sep 5 12:00 PT. mk runs three Max accounts; this reading is one account's buckets.

**Melange review (2026-09-03, `docs/research/flux-melange/main-thread-offload-pattern-f/`, 5 rounds to DRY, 19 slots, 48 findings / 43 upheld / 5 refuted, codex mirror + parley to equilibrium; condition item 4 asked for the review *before* the pilots — it was dispatched before them and finished after, so its findings could not gate the pilot shape and are folded here instead).** Corner finding f-041: the durable verdict register Pattern F needs already exists (`_interspect_insert_evidence` in `commands/execute-plan.md`) but Pattern F never routes through it, the write is fail-open at three layers, and its schema (a bare `pass`, `escalation_count` hardcoded 0) cannot distinguish a validator's independent confirmation from a replay of the executor's checker — the five verdicts above live only in a hand-typed table, invisible to calibration. f-006/f-032: the gate names a quantity the diagnosis does not (confirmed by this run). Refuted by the journal: "the validator structurally cannot add information". Inverted: fragmentation arbitrage — cutting a goal into more items raises the orchestrator's output faster than the executors'. Contested (1 topic, heat 5, for mk to rule): whether the already-transcribed Q-A sentence should be amended in place (done above) or retracted. Upheld prescriptions f-003/004/006/008/011/012/013/014/015/019/021/023/024/041 are dispositioned in the design doc's "Review disposition" section; f-006 is adopted in the proposed gate, f-008/f-013 were practiced as the validators' second channel, the rest are the successor epic.

**Instrument.** `profile.py` (per-message model, `isSidechain`/path lane split, message.id dedupe — every streamed line of a message carries identical usage, verified) is the gate instrument. `cost.py`'s by-model table windows on a row's last-message timestamp and collapses same-name subagent files onto one row (Sylveste-balk); the installed interstat plugin runs the pre-fix parser until a release. `CLAVAIN_EXECUTOR_SHADOW_LOG` rows (Sylveste-d3m phase 1) are the parity corpus for classes `interserve-fast|deep`.

**Pattern F integration owner:** mk (doctrine); integration surface is `/work`, `/execute-plan`, and `writing-plans` in Clavain. Spawn inheritance is closed at the settings level (`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`; running sessions need a restart to pick it up).
