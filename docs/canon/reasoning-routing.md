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

Opt-in `experiment-*` profiles require their registered task scope, a fresh cross-lab producer check, local launch admission before expiry, and strict receipts, without changing default seats or floors (mk-47vtm.10).

## Capacity failure and fallback

Quota, authentication, permission, timeout, and infrastructure failures are operational, not capability strikes. Keep failed receipts; re-resolve using observed availability. Quota-error usage is unknown. Opus 5.5 (`claude-opus-5-5`) replaced Fable 5.1 and Opus 5 in every seat: it is the first-choice planning author (Astra is its cross-lab reviewer and the fallback author) and the plan-review primary, reviewed by Astra; with Astra out an Opus-authored plan fails closed and gets a declared adversarial same-model Opus review by hand. Author and review chains stay distinct. Routine-execution, scout and release-preparation may end with Sonnet instead. `release-authority` has no capacity substitute: substituting it changes authority, not capacity. `main-integrator` now falls back to `pilot-opus` (owner ruling 2026-09-25: Codex exhaustion must never block development); that fallback is informational only — it tells the running session which model to claim, never a delegated subprocess. `fast`/`fast-clavain`/`deep`/`deep-clavain` and `validation-sol` gained the same terminal Claude fallback; see [capacity procedures](reasoning-routing-operations.md#capacity-failure-and-fallback) for the full chain and the `--tier`-vs-`--role` resolution split. Keep model/effort and reviewer independence; fallback cannot change a parent or erase failed work. Headroom forecasts are execution-only: planning, plan-review, validation, escalation and cross-lab-review receive no headroom input. For the probe recipe and why a fallback is never the default, see [capacity procedures](reasoning-routing-operations.md#capacity-failure-and-fallback). Review roles `validation` and `cross-lab-review` prefer a frontier lab other than the producer's (owner ruling 2026-09-24; needs `ic` >= 2caa435); for Claude-produced work, when the Codex lane is out, `validation` substitutes Opus without waiting for reset, or Sonnet when Opus produced it; see [cross-lab review order](reasoning-routing-operations.md#code-review-goes-to-another-lab-first). A 429 outlasting provider retries is capacity, not a capability strike. A same-lab substitute review reached after a capacity walk is provisional but non-blocking, filing re-check items for the other lab when the reviewer lists them or leaves the section missing or empty; see [capacity procedures](reasoning-routing-operations.md#capacity-failure-and-fallback).

## Handoff and escalation

Packaged dispatch enforces a cumulative three-failure review budget per bead
(source: bead `mk-i16ab.6`). Before starting `cross-lab-review`, `plan-review`,
or `validation`, it counts failed review receipts for the resolved `--bead`
across all PR heads and these roles. The shared verdict classifier maps FAIL
and its BLOCK alias to FAIL; PR receipts store BLOCK, while run receipts now
store `verdict_class`. PASS, PASS WITH NOTES, UNKNOWN and absent verdicts do
not count. PASS does **not** reset earlier failures; superseded failed receipts
still count as rounds that happened. Provider errors alone are not failures.
Matching dispatch/attempt IDs deduplicate a run receipt and its PR receipt.

At three failures, another dispatch exits **25** before resolving or starting
a seat, with a message pointing to one private summary at
`<review-receipt-dir>/round-limits/<bead>.md`. Exclusive creation preserves that
first summary on repeated or concurrent refusals. It offers exactly three
options: park, redesign on a frontier seat, or accept a stated limit. Record
the choice and consequences on the bead; the summary grants no merge approval
and no automatic reset. There is no override environment flag.

History comes from `CLAVAIN_DISPATCH_RECEIPT_FILE` (default
`$XDG_STATE_HOME/clavain/dispatch-receipts.jsonl`) and
`CLAVAIN_REVIEW_RECEIPT_DIR` (default `$XDG_STATE_HOME/clavain/reviews`);
`XDG_STATE_HOME` defaults to `$HOME/.local/state`. Keep these shared across
dispatches to preserve the budget. Legacy receipts without a bead or verdict
cannot be attributed retroactively and do not count; dispatch without a bead
cannot enforce a per-bead budget. Missing history means no recorded failures;
unreadable or malformed history, or failure to write the summary, exits **26**
without launching a seat. The check uses completed receipts available at
admission: already-running concurrent reviews are not cancelled or reserved.

Two demonstrated capability, verdict, or criteria failures request escalation; a disproven premise escalates immediately. Exit codes do not classify failure. Handoff carries decisions, constraints, verification, and escalation conditions; do not end `investigation_active` while investigation remains. Retain relevant playtests, experiments, user evidence, and production canaries. Structural tests lack empirical acceptance.

## Host delivery and evidence

User authority, sandboxing, independent review, fresh verification, release and publication approval remain binding. A push does not authorize publication. Missing companions do not authorize installation. Cached green results cannot replace fresh evidence. Report unsupported host gates. Source/hash prove instruction; dispatch receipts enforce; fresh host sessions show behavior. Use [host procedures](reasoning-routing-operations.md#host-delivery-and-evidence) when needed. Update selected blocks by narrow synchronization only: no broad installer or automatic refresh.

## Calibration and rollout

Keep decisions, exclusions, profile, failure class, actual model/effort, retries, usage, outcomes and defects in existing attribution evidence. Missing or blank identity/hash makes conformance unknown and acceptance false; unknown usage and unrun empirical acceptance stay unknown. Calibration cannot relax frontier requirements, reviewer independence, quality floors, or authority gates. Source bytes screen only; they prove no quota saving. Preserve fresh receipts and acceptance evidence; see [calibration procedures](reasoning-routing-operations.md#calibration-and-rollout) when applicable.
