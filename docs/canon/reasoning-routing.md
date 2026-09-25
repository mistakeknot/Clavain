# Reasoning routing

Required selected-source read for substantive work. Read [operations](reasoning-routing-operations.md) only when relevant. This canon governs `config/routing.yaml` roles; resolution is not execution.

## Classify and resolve

Read `clavain:using-clavain` and selected skills before even small behavior edits or plan execution. Record JSON `reasons` and nonempty `rationale`. Permitted reasons and Typical evidence:

| Reason | Typical evidence |
|---|---|
| `unresolved-success-criteria` | Outcomes need playtests or user evidence. |
| `foundational-invariants` | Authority or identity/consistency semantics change. |
| `broad-consequences` | A shared protocol affects many consumers. |
| `difficult-verification` | Experiments or production canaries decide correctness. |
| `capability-failure` | Execution or review demonstrates an unsolved capability gap. |

Settled routine work records `reasons: []` with rationale. An empty reasons array does not waive recording or existing gates. Domain names alone do not elevate. Substantial new game, agent, AI/ML, graph, or product-strategy capabilities require frontier planning. Keep frontier involvement through changing investigation.

Resolve roles with `ic --json route dispatch --policy=<selected-policy> --role=planning --context-file=<decision.json>`. Execute through packaged `scripts/dispatch.sh --role <role>` with the same `CLAVAIN_ROUTING_POLICY` and `CLAVAIN_DECISION_CONTEXT`. Unsupported `--role` stays open; `--type` or `--tier` cannot satisfy it. Receipts retain policy source/hash, reasons, exclusions, profile and actual model/effort. Source order: `--policy`, `CLAVAIN_ROUTING_POLICY`, `CLAVAIN_ROOT`, selected Claude plugin root, managed Clavain skill link, legacy discovery; bad explicit choices fail closed. The dispatch wrapper selects its packaged policy unless explicitly overridden. Never select the newest cache directory by accident. Configuration does not change a running parent model.

Routine example (settled scope). `CLAVAIN_SELECTED_ROOT` is the verified root of the native Clavain skill location; the `ic` line previews resolution, and the dispatch receipt is authoritative:

```json
{"reasons": [], "rationale": "Settled routine change; tests define acceptance", "investigation_active": false}
```

```bash
export CLAVAIN_ROUTING_POLICY="${CLAVAIN_ROUTING_POLICY:-${CLAVAIN_SELECTED_ROOT:?set from native Clavain skill location}/config/routing.yaml}"
ic --json route dispatch --policy="${CLAVAIN_ROUTING_POLICY:?}" --role=routine-execution --context-file=/tmp/decision.json
CLAVAIN_DECISION_CONTEXT=/tmp/decision.json bash "${CLAVAIN_SELECTED_ROOT:?}/scripts/dispatch.sh" --policy "${CLAVAIN_ROUTING_POLICY:?}" --role routine-execution --prompt-file /tmp/brief.md
```

Elevated work lists its `reasons` (plus `domain` when relevant); `investigation_active: true` requires reasons. `plan-review`, `validation` and `cross-lab-review` add `--producer-identity=<author receipt identity>`.

Use one frontier author. Foundational or especially consequential plans require independent other-frontier plan review. Bind `--producer-identity` from the actual author receipt. No fallback may review its producer, route frontier-required work to a non-frontier seat, or evade blocked review by changing destination. Aliases and dated/provider-decorated identities cannot evade reviewer separation. `ci-campaign-pilot` requires `scope: mk-ag2s`; keep the general policy unchanged.

## Capacity failure and fallback

Quota, authentication, permission, timeout, and infrastructure failures are operational, not capability strikes. Keep failed receipts; re-resolve using observed availability. Quota-error usage is unknown. `claude-opus-5` is a last declared substitute where eligible; author and review chains stay distinct. Routine-execution, scout and release-preparation may end with Sonnet instead. `release-authority` has no capacity substitute: substituting it changes authority, not capacity. `main-integrator` now falls back to `pilot-opus` (mk ruling 2026-09-25: Codex exhaustion must never block development); that fallback is informational only — it tells the running session which model to claim, never a delegated subprocess. `fast`/`fast-clavain`/`deep`/`deep-clavain` and `validation-sol` gained the same terminal Claude fallback; see [capacity procedures](reasoning-routing-operations.md#capacity-failure-and-fallback) for the full chain and the `--tier`-vs-`--role` resolution split. Keep model/effort and reviewer independence; fallback cannot change a parent or erase failed work. Headroom forecasts are execution-only: planning, plan-review, validation, escalation and cross-lab-review receive no headroom input. For the probe recipe and why a fallback is never the default, see [capacity procedures](reasoning-routing-operations.md#capacity-failure-and-fallback). Review roles `validation` and `cross-lab-review` prefer a frontier lab other than the producer's (mk ruling 2026-09-24; needs `ic` >= 2caa435); for Claude-produced work, when the Codex lane is out, `validation` substitutes Opus without waiting for reset or escalating to Fable; see [cross-lab review order](reasoning-routing-operations.md#code-review-goes-to-another-lab-first). A 429 outlasting provider retries is capacity, not a capability strike. A same-lab substitute review reached after a capacity walk is provisional but non-blocking, filing re-check items for the other lab only when the reviewer lists them; see [capacity procedures](reasoning-routing-operations.md#capacity-failure-and-fallback).

## Handoff and escalation

Two demonstrated capability, verdict, or criteria failures request escalation; a disproven premise escalates immediately. Exit codes do not classify failure. Handoff carries decisions, constraints, verification, and escalation conditions; do not end `investigation_active` while investigation remains. Retain relevant playtests, experiments, user evidence, and production canaries. Structural tests lack empirical acceptance.

## Host delivery and evidence

User authority, sandboxing, independent review, fresh verification, release and publication approval remain binding. A push does not authorize publication. Missing companions do not authorize installation. Cached green results cannot replace fresh evidence. Report unsupported host gates. Source/hash prove instruction; dispatch receipts enforce; fresh host sessions show behavior. Use [host procedures](reasoning-routing-operations.md#host-delivery-and-evidence) when needed. Update selected blocks by narrow synchronization only: no broad installer or automatic refresh.

## Calibration and rollout

Keep decisions, exclusions, profile, failure class, actual model/effort, retries, usage, outcomes and defects in existing attribution evidence. Missing or blank identity/hash makes conformance unknown and acceptance false; unknown usage and unrun empirical acceptance stay unknown. Calibration cannot relax frontier requirements, reviewer independence, quality floors, or authority gates. Source bytes screen only; they prove no quota saving. Preserve fresh receipts and acceptance evidence; see [calibration procedures](reasoning-routing-operations.md#calibration-and-rollout) when applicable.
