---
artifact_type: melange-synthesis
method: flux-melange
target: docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md
target_description: "Main-thread offload (Pattern F): thin Fable orchestrator, fresh-context Sonnet executors, Opus validators against frozen criteria, gated by main-thread token share; design for review before three pilots"
goal: "Stress-test Pattern F before its pilots: silent offload failures, validator information gain, residual orchestrator context, plan drift and stale state, token-share blind spots, and false premises in Q-A through Q-E."
weights: risk-hunt
rounds_run: 3
halt_reason: DRY
total_fusions: 3
emergent_findings: 1
runtime: codex
date: 2026-09-03
---

# Main-thread offload Pattern F — melange synthesis

Pattern F is not pilot-ready as written. Its largest risks are not model capability gaps but broken evidence identity: mutable handoffs, shared checkout state, validators that can mutate what they judge, and a success gate that can improve when delegated waste increases. The proposed Opus role is also underspecified as an experiment. Replaying the same frozen oracle does not test whether Opus adds semantic information.

**If you read one thing — f-024 (HEAT 18):** a workspace-write validator can commit after its review diff is captured, leave `git status --porcelain` unchanged, and return PASS over a tree it authored but never independently observed. Make validation read-only and bind its verdict to an immutable tree ID before any pilot.

## Re-score basis

I re-scored the 39-row merged ledger against the final cluster map, not the per-round arrival order. Novelty is therefore inverse final overlap: repeated findings in the immutable-handoff, shared-checkout, output-denominator, and Q-B attribution clusters fall to 0 even when they first appeared as novel. Blast radius measures how much of a pilot or landing decision can be invalidated; likelihood measures whether the current implementation makes the path ordinary rather than merely possible. Risk is `blast × likelihood`; HEAT is `novelty × risk`. Severity below is retained only as a reference label.

The re-score leaves two non-dominated upheld points: `(novelty 3, risk 6)` and `(novelty 2, risk 9)`. No upheld finding has both greater novelty and greater risk than either one.

## 1. Novelty×Risk Frontier

### f-024 — validator mutation defeats independent observation

- **Claim:** A validator can commit a change while leaving porcelain status unchanged, causing its PASS over the pre-review diff to authorize validator-authored state that was never independently observed.
- **Lens:** `fd-fused-causal-assurance-handoff-cox`, fusing `fd-distributed-systems-handoff-cox` with `fd-software-verification-validator-value-cox`.
- **Re-scored risk:** blast 3 × likelihood 2 = **6**. A hit can authorize the wrong tree across an entire item and its dependents; it requires validator mutation, which is permitted but not inevitable.
- **Novelty / HEAT:** 3 / **18**. No base lens independently connected a hidden committed transition to false validator independence.
- **Severity, reference only:** P1.
- **Evidence:** `scripts/orchestrate.py:694-701` captures the diff before review; `:703-714` grants the Codex reviewer workspace-write; `:716-744` compares only porcelain status, not HEAD or tree identity.

### f-010 — the gate cannot see an explicitly supported execution lane

- **Claim:** The cited profiler cannot observe the Codex execution lane that Pattern F explicitly includes.
- **Lens:** `fd-observability-token-gate-cox`.
- **Re-scored risk:** blast 3 × likelihood 3 = **9**. Every Codex-routed pilot item can be omitted from the gating denominator and resource totals, and Codex is a configured default execution route.
- **Novelty / HEAT:** 2 / **18**. One domain lens found it; no other final cluster duplicates the metering omission.
- **Severity, reference only:** P1.
- **Evidence:** `interstat/scripts/profile.py:25,38-52,71-87` reads Claude Code transcripts and emits only main/subagent lanes; `config/routing.yaml:22-32` routes unmapped execution to Codex; `scripts/dispatch.sh:951-992` records routing metadata but not Codex usage.

These findings lead together. f-024 is the maximum-novelty, mid-risk point; f-010 is the mid-novelty, maximum-risk point. A scalar severity sort would hide that trade.

## 2. Top Fusions

### Emergent: f-024 — causal assurance × mutable handoff (HEAT 18)

- **Parents:** `fd-distributed-systems-handoff-cox` × `fd-software-verification-validator-value-cox`.
- **Intersection justification:** The handoff parent supplies the hidden repository transition that the porcelain guard misses. The assurance parent supplies the independence rule: an oracle may not mutate the specimen and certify an earlier observation. Remove either contribution and the issue collapses into either a generic permission defect or a generic mutable-state race, not false acceptance.
- **Evidence:** The review diff is materialized before dispatch, the validator has workspace-write, and post-review contamination detection compares porcelain strings without checking HEAD, index tree, worktree tree, or an immutable validation snapshot (`scripts/orchestrate.py:694-744`).

This was the sole emergent finding. The same fusion's f-022 and f-023 were useful but not emergent: they converged on the already-established immutable-handoff and shared-checkout clusters.

### Negative fusion results

- **`fd-distributed-systems-handoff-cox` × `fd-batik-negative-reserve-cox`: independent here.** f-029, f-030, and f-031 restated immutable artifact identity, shared-checkout attribution, and validation-window placement. Their evidence—live plan and criteria paths, one shared `project_dir`, cumulative diffs, and absent digests—was already sufficient from a parent or prior cluster; the reserve vocabulary did not produce a new failure mechanism.
- **`fd-observability-token-gate-cox` × `fd-batik-negative-reserve-cox`: independent here.** f-032, f-033, f-034, and f-035 collapsed into existing denominator inflation, Q-B phase attribution, shared-checkout crosstalk, and validator marginal-value clusters. The fusion sharpened remediation by adding repair-window accounting, but the underlying claims were available without the cross-product.

## 3. Taste Calls

None. Every ledger record has `taste: 0` and `taste_kind: null`; there is no defensible elegance, smell, asymmetry, naming, simplicity, or metaphor-leak call to preserve or fix. The distant lenses produced operational claims, not aesthetic judgments.

## 4. Convergence Spine

This is trusted commodity, not the headline. It is ordered by HEAT; ties are broken by risk and then number of contributing lenses, never by severity.

| Representative | Re-scored novelty × risk = HEAT | Convergent lenses | What can be trusted |
|---|---:|---|---|
| **f-018** | 1 × 9 = **9** | software verification; isnad/provenance | Q-A has the wrong premise as written. An Opus validator restricted to the executor's frozen criteria and verify block cannot detect omissions in that same chain. The pilot must compare distinct interventions—mechanical replay versus semantic diff review—on the same immutable artifact, and record first observer and adjudicated truth. |
| **f-007** | 1 × 6 = **6** | software verification; reserve-accounting fusion | Existing telemetry cannot estimate Opus's marginal information. PASS counts and criterion totals lack fault class, first observer, counterfactual arm, false acceptance/rejection, and adjudicated truth. |
| **f-001** | 0 × 9 = **0** | distributed handoff; sumitsuke; isnad; Meroitic steering; two fusion lenses | A path is not a handoff identity. Bind executor, machine gate, validator, retry, and resume to one envelope containing plan/criteria digests, base tree, result tree, attempt, and environment evidence. Six reports across base and fusion tiers reached this cluster. |
| **f-014** | 0 × 9 = **0** | distributed handoff; sumitsuke; causal-assurance fusion; causal-reserve fusion; reserve-accounting fusion | Parallel task PASSes in one mutable checkout do not certify the final assembled tree. Isolate worktrees or serialize, attribute diffs to item-owned commits, and run one final gate over the exact landing tree and union of criteria. |
| **f-009** | 0 × 9 = **0** | observability; isnad; reserve-accounting fusion | `main_output / total_output <= 50%` is Goodhartable by delegated verbosity and failed rounds. Pair the share with absolute main/context/cache volume, total resources, retries, latency, human recovery, and quality-normalized landed outcomes. |
| **f-011** | 0 × 6 = **0** | observability; isnad; reserve-accounting fusion; Meroitic steering | Session-level lane totals cannot answer Q-B. Planning, report ingestion, checkpoint handling, repair, landing, and controller re-entry need event-time goal/run/task/attempt/phase attribution. This representative remains raw because verification was budget-clamped, despite four-lens convergence. |

f-017 finds Q-E's stale-plan candidate misframed: stale-plan execution already exists in the baseline; Pattern F amplifies it by removing tacit main-thread compensation. The genuinely new fault is loss of unstated invariants at the fresh-context boundary. Q-C received no comparable evidence, and Q-D's proposed wrong-premise finding was refuted.

## 5. Live Disagreements

None remained open at halt. That is a primary signal about this run's internal consistency, not proof that every raw finding is true: 16 rows never received budgeted verification.

## Caveats

- **Failed probes:** none recorded (`failed: 0` in both probe rounds). There is no failed-agent gap to impute.
- **Budget-clamped verification:** 19 findings were upheld, 4 refuted, and 16 remained raw. The surfaced Q-B representative is explicitly raw; all frontier findings are upheld. Empty on-disk convergence/disagreement arrays are a workflow-mode artifact, so this synthesis uses the supplied controller cluster map.
- **Regions never reached:** the loop did not materially resolve Q-C's Codex-first pilot classes, did not run a cross-accounting sensitivity analysis for Q-D, and did not observe an actual Fable/Sonnet/Opus pilot. No conclusion here demonstrates runtime quality, latency, or realized token savings.
- **Taste and conflict surfaces:** no finding was taste-flagged and no disagreement survived, so those views are empty rather than evidence of aesthetic agreement or exhaustive adversarial coverage.

## Spice Trail

### Round 0 — assay

- **Yield:** 11; **novel cluster rate:** 0.71.
- **Observed production:** 21 findings; 2 agents dispatched according to controller telemetry.
- **Directives:** none. The opening assay established the dominant fault families: mutable handoff identity, shared-checkout crosstalk, vacuous or repeated validation, output-share Goodharting, phase attribution, and pilot-design gaps.
- **Steering result:** High breadth justified continuing. The next round fused the strongest shared heat and widened into an orthogonal negative-reserve lens.

### Round 1 — probe, then assay

- **Yield:** 3; **novel cluster rate:** 0.71.
- **Observed production:** 7 findings; 2 agents dispatched; 0 failed.
- **Directive — FUSE:** `fd-fused-causal-assurance-handoff-cox`, because `shared_heat 3, complementarity 2, redundancy 0`. Distributed handoff identity was crossed with assurance validity. It produced the run's only emergent result, f-024, while f-022 and f-023 reinforced existing clusters.
- **Directive — STEER-WIDE:** `fd-batik-negative-reserve-cox`, because `novel_cluster_rate 0.71 >= 0.6 — widening still pays`. It steered toward negative scope, inspection windows, checkpoint ownership, and transition coverage; only checkpoint ownership and transition coverage survived verification as distinct upheld claims.
- **Steering result:** Novelty remained high enough to spend the final round on two targeted fusions plus one farther control-loop lens.

### Round 2 — probe, then assay

- **Yield:** 0; **novel cluster rate:** 0.09.
- **Observed production:** 11 findings; 3 agents dispatched; 0 failed.
- **Directive — FUSE:** `fd-fused-causal-reserve-handoff-cox`, because `shared_heat 2, complementarity 1, redundancy 0`. It steered handoff identity into protected-boundary timing; all three results converged on prior clusters.
- **Directive — FUSE:** `fd-fused-reserve-accounting-cox`, because `shared_heat 2, complementarity 1, redundancy 0`. It steered workload accounting into repair-window and reserve-state accounting; all four results converged on prior clusters.
- **Directive — STEER-WIDE:** `fd-meroitic-furnace-steering-cox`, because `novel_cluster_rate 0.71 >= 0.6 — widening still pays`. It steered toward bounded live executor authority, controller decision windows, transient validation state, and exception traffic. These remained raw under the verification budget.
- **Halt:** **DRY**. The final round generated 11 formulations but no controller yield, only 0.09 novel-cluster rate, and two zero-emergent fusions. Further lensing was producing refinements and corroboration rather than decision-changing mechanisms.
