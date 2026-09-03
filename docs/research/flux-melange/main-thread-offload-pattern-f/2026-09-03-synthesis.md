---
artifact_type: melange-synthesis
method: flux-melange
target: docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md
target_description: "Main-thread offload (Pattern F): thin Fable orchestrator, fresh-context Sonnet executors, Opus validators against frozen criteria, gated by main-thread token share — design doc for review before three pilots"
goal: "Stress-test the main-thread offload architecture (Pattern F) before its pilots run: what silently fails when execution moves from a 300K-context frontier main thread to fresh-context Sonnet executors and Opus validators; whether the validator adds information or only cost; where the orchestrator's context still bloats; plan-drift and stale-state failure modes; what the token-share gate (<=50% main-thread generated tokens) fails to capture; and which of the five open questions Q-A..Q-E has a wrong premise."
weights: risk-hunt
rounds_run: 5
halt_reason: DRY
total_fusions: 1
emergent_findings: 6
runtime: claude
date: 2026-09-03
---

# Pattern F — melange synthesis

48 findings across 5 rounds, 6 base lenses and 1 fusion lens, 19 agent slots. 5 refuted, 43 upheld, 39 surfaced across the five views.

## Re-scoring note — the pilots already ran

The per-round scores were fast triage estimates against the design doc alone. Re-scoring them, I read one artifact the earlier rounds mostly did not: `docs/goals/2026-09-03-main-thread-offload-journal.md`, the goal's own five-pilot journal, written by the orchestrator this design describes. Only round 2's `fd-distsys-state-coherence` had reached it, and only for two rows.

The journal is not confirmation from a friendly witness. It is the design running against reality, and it moves scores in both directions:

- **It confirms three findings hard.** Pilot 1's plan asserted branch `main` while the checkout sat on `sweep/2026-09-02` (the plan-staleness cluster, live). Pilot 1b hit a "concurrent old-parser writer" (the isolation cluster, live). Two of five runs were blocked by a defect in the plan's own verify block, never by the code (the frozen-criteria cluster, live).
- **It settles the gate question empirically.** Main-thread share of *generated tokens*: 86%, against a ≤50% gate. Main-thread share of *cost*: 35%, against an 85% baseline. The design's objective was met and its gate failed, in the same run, on the same data.
- **It refutes or inverts two claims the ledger scored high.** The validator's "structurally cannot add information" prediction did not hold: four of five validations surfaced a real defect the verify block did not check. And the fragmentation-arbitrage mechanism runs backwards at observed ratios — orchestrator output was 70K against 13K from every executor and validator combined, so cutting a goal into more items raises the numerator faster than the denominator.

I have re-scored against that evidence and marked every finding whose status the journal changed. Where a finding's mechanism is falsified but its conclusion survives for a different reason, I say so rather than quietly keeping the score.

---

## 1. Novelty × Risk frontier

On an integer 3 × 9 grid the Pareto front saturates: one finding sits at the corner (novelty 3, risk 9) and formally dominates everything else. So the front is reported as its corner plus the two poles of the near-front band, which is where the discrimination actually lives.

### Corner — f-041 · the verdict register exists, is unwired, and could not hold the answer anyway

*Lenses: `fd-fused-replay-independence` (fusion of `fd-distsys-state-coherence` × `fd-assay-independence`)*

Clavain already has the durable, population-level verdict register that the independence critique says Pattern F lacks: `_interspect_insert_evidence` in `commands/execute-plan.md`, feeding interspect calibration. Pattern F's dispatch shape never states whether it routes through that call site. Where it is reached, the write is fail-open at three separate layers — `2>/dev/null || true`, a `[[ -n "$interspect_root" ]]` guard, and `[[ -f "$db" ]] || return 1` in `lib-interspect.sh:3047`. And the schema cannot carry the finding even if it fired: a bare `pass` boolean with `escalation_count` hardcoded to 0 cannot distinguish a validator's independent confirmation from a mechanical replay of the executor's own checker.

Risk decomposition: **blast 3 × likelihood 3 = 9**. Novelty 3. Heat 27, the run's argmax.

The journal closes this: the goal's only durable record of five validator verdicts and their value is a hand-typed markdown table. Nothing machine-readable was written; no calibration process will ever see the run that was supposed to answer Q-A. Severity P1 for reference.

### Max-novelty pole — f-032 · the gate's denominator, and the cost that never enters it

*Lens: `fd-warp-lot-economics`*

The ≤50% gate is defined on the goal's total output tokens, a denominator that scales with item count. The weaver's reading: every changeover leaves thrums, and a schedule that looks efficient per-item while multiplying changeovers is the classic loom-economics error. Each dispatched item pays ~20–40K of executor priming plus a comparable validator priming, none of which the gate counts.

Risk decomposition: **blast 3 × likelihood 2 = 6**. Novelty 3. Heat 18. Severity P0 as filed; I hold it at P1.

**Re-scored, with the mechanism inverted.** The journal's numbers run the arbitrage backwards: main generated 70K, all subagents combined 13K. Executors copy execution-grade plans, so they generate almost nothing; splitting an item into two mostly doubles *plan authoring*, which is main-lane output. Fragmentation makes the gate score worse, not better.

The other half survives and is larger than filed. The subagent lanes moved 23.0M + 6.9M + 1.0M ≈ 30.9M cache-read tokens against the main thread's 9.8M. Offload did not reduce context volume; it tripled it, and won on price — Sonnet and Opus cache reads are cheaper per token than Fable's. That is a real win and a fragile one, since it survives only while the tier price gap holds. The lens found the right cost term and predicted the wrong sign, which is worth more than either alone.

### Max-risk pole — f-006 · the gate measures a quantity the diagnosis does not name

*Lens: `fd-evalscience-judge-validity`*

Line 7 puts 85% of main-thread cost in context — cache read plus cache write, re-sent every turn at 220–320K. Line 9 concludes the lever is "fewer, smaller main-thread turns." Line 15 then sets the gate on **output tokens**, a different quantity entirely. A goal can pass the gate with orchestrator turns still carrying 300K of context each, and can fail it while cutting cost by 60%.

Risk decomposition: **blast 3 × likelihood 3 = 9**. Novelty 2. Heat 18. Severity P0.

**Confirmed by the run it governs.** The journal records 86% output share against the ≤50% gate — failed — alongside 35% cost share against an 85% baseline — a 2.4× improvement in the thing the design exists to fix. The orchestrator's own recorded reason is exactly this finding: "offload moves context volume, not authorship." A replacement metric (cost share per goal) is already proposed for mk's ruling. This is a construct-validity error caught by the instrument disagreeing with the outcome on the first run, which is the good case; had the gate been enforced as written, a successful pilot would have been recorded as a failure.

### Near-front band

| id | claim (compressed) | lens | nov | blast × lik | heat | note |
|---|---|---|---|---|---|---|
| f-039 | `profile.py` has no goal/bead argument at all — only `--session`/`--days`. The gate's unit is "the goal," which the meter cannot address | `fd-distsys-state-coherence` | 2 | 3 × 3 = 9 | 18 | **Confirmed live**: the journal's own number was taken with `--session`, the undercount path |
| f-024 | Adjudication: the validator's re-run is a third, untested configuration — not reading (0/6) and not gauge-lint's decoupled dry-run (6/6), but post-hoc replay against already-mutated state | fusion: `fd-distsys` × `fd-assay` | 3 | 3 × 2 = 6 | 18 | Prediction falsified by the journal; the taxonomy it built is what survives |
| f-033 | Fresh context is mandated per item, twice, with no stated reason and no batching alternative examined — the largest fixed-cost lever spent by default | `fd-warp-lot-economics` | 3 | 2 × 3 = 6 | 18 | **Confirmed live**: 253 Sonnet + 93 Opus messages across 5 items, 30.9M cache reads |
| f-042 | "Frozen criteria" freezes text, not repo state; three spawns touch an unpinned trunk, and the obvious fix (pin the commit) collapses the validator into guaranteed replay | fusion lens | 3 | 2 × 3 = 6 | 18 | Q-E scopes drift to the executor and misses the validator-side case |
| f-011 | The orchestrator authors plan quality and is scored on its own output share; a thinner plan improves its metric and pushes cost onto a budget the gate ignores | `fd-econ-principal-agent` | 3 | 3 × 2 = 6 | 18 | Note the countervailing force: execution-grade plans are *long*, so quality and metric pull the same way at current ratios |
| f-034 | Pilot-1's 6/6 gauge-defect rate is shakedown data the source frames as process-immaturity evidence, not a steady-state rate | `fd-warp-lot-economics` | 3 | 2 × 3 = 6 | 18 | **Now self-referential**: the journal draws a steady-state Q-A conclusion from 5 first-run pilots |
| f-013 | Frozen criteria buy validator independence from executor taste at the price of its only power to catch a systematically thin plan | `fd-econ-principal-agent` | 3 | 2 × 3 = 6 | 18 | The structural counterpart to f-011: no independent check on the one party that authors the standard |
| f-007 | Q-A cannot be resolved by the pilot data the doc proposes to use | `fd-evalscience-judge-validity` | 2 | 3 × 3 = 9 | 18 | **Conclusion confirmed, mechanism refuted** — see §5 |
| f-003 | Two-strikes needs a durable per-item counter surviving separate fresh spawns; no storage location is named anywhere in the design | `fd-distsys-state-coherence` | 2 | 3 × 2 = 6 | 12 | Untouched by the pilots because no item reached strike two |

---

## 2. Top fusions

One fusion lens was attempted — `fd-fused-replay-independence`, from `fd-distsys-state-coherence` × `fd-assay-independence`, under an intersection-only hard constraint that explicitly discards the parent-alone claims (bare "no commit-SHA precondition," bare "the validator shares the method"). Six emergent findings resulted across rounds 1 and 2; two were later refuted.

**f-041 — verdict register unwired and schema-inert.** Parents: distsys × assay. *Intersection justification:* the distsys half sees a durable log that is call-site-bound and fails open at three layers, invisible without tracing the shell script and its DB-existence check. The assay half sees that a successful write would still be diagnostically inert, because the schema collapses two different assay strengths — replay and independent confirmation — into one boolean. Neither parent alone reaches "wire it up *and* redesign the independence field before pilots start." *Evidence:* `execute-plan.md:44-52`; `lib-interspect.sh:3047-3048`; `execute-plan.md:9`'s mandatory checkpoint pauses, which sit in tension with a thin autonomous orchestrator. Novelty 3 × risk 9.

**f-042 — validator-side drift collapses independence.** Parents: distsys × assay. *Intersection justification:* the distsys half sees three spawns against an unpinned trunk with no lease and no strike category for the resulting spurious FAIL. The assay half sees that the obvious coordination fix is not free — pinning the commit fully realizes the guaranteed-replay condition that makes a second examination certify nothing. A pure distsys reviewer recommends the pin; a pure assay reviewer assumes "frozen criteria" already covers reproducibility. Only both together show the design is silently choosing between two failure modes rather than missing an obvious fix. Novelty 3 × risk 6.

**f-024 — the three-configuration adjudication.** Parents: distsys × assay, dispatched as PROBE-DISAGREEMENT against the f-004 ↔ f-020 contradiction. *Intersection justification:* adjudicates a direct textual contradiction at the same location by grounding both parents against `model-routing.md`'s actual pilot-1 data and `writing-plans/SKILL.md`'s canonical verify-block shape. It found f-020's citation over-reaching — the 0/6 belongs to the *reading-based* review step, not to any re-execution — and separated three distinct configurations: reading (0/6), gauge-lint's pre-freeze decoupled dry-run (6/6), and Pattern F's post-hoc replay against mutated state (never measured). Novelty 3 × risk 6. The taxonomy is the durable product; the prediction attached to it did not survive the journal.

**f-025 — the dropped mechanism.** Surfaced while resolving f-024's citation: Pattern F's escalation text cites pilot-1's 6/6 by name to justify what happens after two strikes, but the three-role shape never adopts rule 9 — the mandatory pre-freeze gauge dry-run, blocking, by a model other than the plan's author, wired as step 0 of `/plan-review` — which is the mechanism doctrine built *in direct response to that same finding*. Novelty 0 by the lens's own scoring, risk 9. See §4; this is the run's clearest commodity.

**Negative results.** `fd-distsys-state-coherence` × `fd-assay-independence` produced two emergent findings that did not survive verification: f-026 (a second citation-correction pass that duplicated f-024's own correction) and f-028 (gauge-lint certifies a hypothetical dry-run diff, not the real one — refuted once the executor's verbatim-application contract was read against pilot data showing 5/5 code-correct verbatim application). Both are recorded as emergent-but-refuted rather than dropped. No other lens pair was fused: `fd-econ-principal-agent` × `fd-evalscience-judge-validity` was the obvious second candidate and was never dispatched — see caveats.

---

## 3. Taste calls

### Preserve

**f-044 · `taste_kind: latent-fix` (+2).** The smallest viable fix for the model-tier laundering gap already exists in the codebase and is already imported. `cost.py:118-125` classifies any model string into a tier by substring match; `profile.py:23` imports `get_pricing`; `profile.py:107` is the sole call site and feeds only `calc_cost`. One branch feeding `lane_out` closes the gap. A finding that ends at an existing unused function rather than at a proposal is worth more than the six findings that describe the same gap.

**f-042 · `taste_kind: honest-dilemma` (+2).** Both parent lenses have a documented machinery bias — distsys answers staleness with pins and locks, assay answers doubt with registers and counter-assays. The fused finding declines to prescribe, and instead names the exchange rate: pinning buys reproducibility and spends independence at the same rate. Naming a tradeoff the design is making unknowingly beats recommending either horn.

**f-024 · `taste_kind: citation-hygiene` (+1).** The adjudication upheld the weaker-sounding claim and refuted the stronger one by checking what `model-routing.md:99` actually attributes the 0/6 to. It cost the run its most quotable line and left the argument standing on ground that holds.

### Fix

**f-047 · `taste_kind: overclaim` (-2).** The "Inheritance closed" bullet sits under "What makes it enforceable rather than aspirational" and enforces only *which model answers* at 48 command sites and 25 doc-shaped agents. It installs none of Pattern F's actual message contract — frozen criteria, verbatim verify output, no scope expansion — at any of them. Rollout evidence for a discipline the rollout does not confer, in the section whose whole job is to separate the enforceable from the aspirational.

**f-011 · `taste_kind: metric-conflict` (-1).** One role authors the plans and is scored on its own share of output tokens, with no offsetting metric named. At current ratios the incentive happens to point the right way, which is luck rather than design.

**f-015 · `taste_kind: self-similar-gap` (-1).** `model: inherit` is a self-declared escape hatch with no named auditor — the same "requires a named integration owner and has none" shape the doc diagnoses in line 7 as the reason Pattern F is needed, recurring one layer down inside Pattern F's own inheritance closure.

**f-036 · `taste_kind: class-blind-postmortem` (-1).** Both live collisions were triaged and closed as ordinary per-plan gauge defects — fixed by correcting one verify assertion — rather than as a contract-level isolation gap. The fix does not close the class, and the enforceability section is unchanged by the pilot run that surfaced both.

**f-048 · `taste_kind: smell` (-1).** *Lens: `fd-shepherd-outrun-discretion`.* The 30-day open-ended read across dispersed transcripts is what produced this document's headline finding, and nobody asked for it. The substrate survives — `profile.py` retains subagent JSONL identically — but the tool answers only three pre-defined questions, and the design names no owner or cadence for the unrequested look. The shepherd's reading: condition is read by walking through, not by counting at the gate.

---

## 4. Convergence spine

High-convergence, low-novelty, high-confidence. These are commodity: multiple independent lenses reached them, several are now confirmed by live pilot data, and none of them needs further argument before the next pilot.

**Plan staleness has no precondition pin** — f-029 (CONFIRMED), f-016, f-001, f-030, f-031. Three lenses independently (`fd-distsys-state-coherence`, `fd-pilotage-handoff`, `fd-evalscience-judge-validity`), plus four other flux-melange lens agents in this repo already carrying the same flag. No plan field, executor contract, validator contract, or orchestrator script checks commit SHA, branch, or clean tree at any point. `writing-plans/SKILL.md` has no State category in Must-Haves and no precondition item in its Remember checklist, so the gap replicates into every plan by construction. `executing-plans`' one SHA-shaped artifact, `vetted_sha`, is written *after* verification — a postcondition. **Live:** pilot 1's plan asserted `main` against a `sweep/2026-09-02` checkout; the fix was a manual cherry-pick.

**No concurrent-writer isolation** — f-035 (CONFIRMED), f-018, f-005. The executor receives "the repo path" with no worktree and no interlock reservation, in a repo where both mechanisms already ship and where `codex-integration.md:12` documents a worktree-first contract for the analogous case. **Live:** pilot 1b's verify block collided with what the journal itself calls "a concurrent old-parser writer."

**Frozen criteria are never independently assayed** — f-021, f-008. Two lenses. The orchestrator authors both the plan and the criteria; the validator is barred from applying anything else; none of the four enforceability bullets checks the criteria. **Live:** 2 of 5 pilot runs were blocked by a defect in the plan's own verify block, never by the code — the journal's own words, "the plan's emitted text is simultaneously the artifact and an input to a checker the same author wrote."

**Rule 9 was dropped** — f-025. Novelty 0, risk 9, and the single most actionable item in the run. Pattern F cites pilot-1's 6/6 to justify escalation and never adopts the pre-freeze gauge dry-run that doctrine built in response to it. Adding step 0 back is a one-line change to the shape.

**The meter cannot resolve the gate's own unit** — f-010, f-022, f-038, f-043, f-039, f-040, f-044. Two lenses, seven findings, the densest cluster in the ledger. `profile.py`'s lane split is three path/flag proxies OR'd together, never consults `model`, has no goal or bead argument, and hardcodes a glob root that may not reach codex transcripts. **Live:** the journal's own table shows a Haiku 4.5 row with 30 messages in the subagent lane — an unrelated tool subagent counted as offloaded execution — and the number was scoped by `--session`, the exact undercount path.

**No non-strike failure category** — f-023, f-046. Two lenses. Doctrine's strike taxonomy excludes sandbox denials, auth expiry, and infra errors; Pattern F's binary PASS/FAIL has no field to carry the equivalent, so flake, drift, and infra all consume strike budget as genuine defects. f-046 adds the codex-lane instance and notes Q-C's "classes with parity" presupposes a parity test defined nowhere.

**Partial application leaves an unspecified tree** — f-002, f-017. Two lenses. The contract names a commit on success and nothing on failure, while `writing-plans`' per-task commit step means a multi-task plan can be partially committed with no field recording which tasks landed.

Also converged and surfaced: f-019 (no category for correct-but-insufficient, or for a one-token verify typo — **live**, pilot 3b's executor "refused to commit until corrected," an outcome the binary rule has no name for), and f-007 (below).

---

## 5. Live disagreements

**The formal register is empty.** The single recorded contradiction — f-004 (the validator's re-run is not isolated, so non-idempotent checks produce spurious FAIL) against f-020 (the validator's re-run is a null check that certifies nothing) — was dispatched as PROBE-DISAGREEMENT in round 1 and adjudicated by f-024: not a contradiction over one fact, but two regimes of one gap, with f-020's citation over-reaching and therefore refuted. Nothing else was open at halt.

Reporting that as "no disagreements" would be the wrong summary. The DRY halt stopped the loop before it could see the contradiction that matters, because that contradiction is not between two lenses — it is between the ledger's dominant conclusion and the target project's own live evidence.

**Open · the ledger says the validator adds nothing; the journal says it added the most.** The ledger's largest argument, across `fd-evalscience-judge-validity` and `fd-assay-independence` and both fusion passes (f-007, f-020, f-024, f-025, f-026), is that a validator re-running the same block against the same tree under the same frozen criteria cannot catch what the block was blind to. The journal reports the opposite: five of five validations passed on criteria, and four of five surfaced a real defect the verify block did not check — two of which became fix-forward pilots.

Both are right about different validators. Line 17 specifies: "Judges ONLY against the frozen criteria in the plan (never its own taste). Output: PASS / FAIL with the failing criterion quoted." The journal's header specifies what actually ran: "Validators: Opus 5 subagents, judging only the plan's VERIFY block, **then reporting what the gauge missed**." That second clause is not in the design. It is the channel that produced every unit of measured validator value, and line 17's "ONLY" forbids it.

This resolves f-007 in a way f-007 did not predict. Its mechanism — "cannot by construction catch a defect class the block was blind to" — is refuted for the validator as run. Its conclusion — "the question as posed cannot be resolved by the pilot data the doc proposes to use" — is confirmed, because the pilot data measures a validator the document does not specify. **Q-A remains open, and the journal's answer to it should not be transcribed into the design until the design's validator contract is amended to authorize the channel that produced it.** Concretely: line 17 needs a second output field — a non-binding "beyond the gauge" note — or the pilots' 4/5 result belongs to a pattern that is not Pattern F.

**Open · f-032's arbitrage runs backwards at observed ratios, and its cost term does not.** `fd-warp-lot-economics` predicted that fragmenting a goal into more items would game the gate downward. The journal's 70K main against 13K subagent inverts it: executors copy plans and generate almost nothing, so more items means more plan authorship in the main lane. What the lens got right, and understated, is that the per-item re-priming never enters the gate at all — and it turned out to be 30.9M cache-read tokens against the main thread's 9.8M. Offload tripled context volume and won on tier price. Unresolved: whether that is a durable win or an arbitrage on a price gap, which nothing in the design monitors.

**Latent, never probed.** Every one of the six base lenses declares model capability outside its frame — three say so explicitly in their own failure_mode records. Nothing in 48 findings asks whether Sonnet can actually apply an execution-grade plan or whether Opus can actually read a diff. The journal answers it in passing (5/5 verbatim application) and no lens was equipped to notice that it had.

---

## Which open question has the wrong premise

The goal asked directly. Ranked:

- **Q-A — wrong premise, and consequential.** It assumes the pilots can answer it. They cannot answer it about the validator the document specifies, because the piloted validator ran a wider contract. See §5.
- **Q-B — wrong premise.** It offers a binary: the orchestrator's context goes to reading executor reports or to its own planning. Observed: 29 main-lane messages at 344K context per turn. Neither reports nor planning dominates that; the standing session prefix does, and capping report size cannot move it. The remedy the question proposes ("cap report size in the executor contract") is scoped to the smaller term.
- **Q-C — wrong premise.** "Which pilot classes should go there first" presupposes a parity test that exists nowhere in the doctrine (f-046), and `profile.py`'s hardcoded `~/.claude/projects` glob root may not reach codex transcripts at all, so the lane cannot be measured even after the fact (f-045).
- **Q-E — right in kind, wrong in scope.** Plan drift is real and already happened (pilot 1). Q-E scopes it to "a fresh executor cannot notice"; f-042 shows the validator's later re-run drifts again, and that the pin which fixes it collapses the validator into guaranteed replay.
- **Q-D — premise sound.** The shape is genuinely robust to both pool-accounting regimes. Its stated weakness, that the *ordering* of follow-ups is not robust, is real and is made worse by f-006: with the gate measuring the wrong quantity, the ordering has no reliable signal to sort against.

---

## If you read one thing

**f-041** — argmax heat (27). The mechanism that would have made this whole pattern self-correcting already exists, is already written into `execute-plan.md`, fails open at three layers, is never named by Pattern F's dispatch shape, and could not represent the run's single most interesting result even if it fired. The five pilots that were supposed to answer Q-A left their verdicts in a markdown table. Wire the register, add an independence field to its schema, and the next five pilots produce evidence instead of prose.

---

## Appendix: spice trail

**Round 0 · assay · yield 11 · novel_cluster_rate 0.74.** Two agents, four base lenses across two dispatches (`fd-distsys-state-coherence`, `fd-evalscience-judge-validity`, `fd-econ-principal-agent`, `fd-pilotage-handoff`). 23 findings recorded, 11 counted as yield. Established the four spines that dominate the rest of the run: plan staleness, validator independence, frozen-criteria assay, and meter attribution. Two lenses independently reached the precondition-pin gap without coordination, which is why it scores as commodity rather than insight.

**Round 1 · probe · 4 directives · yield 11 · novel_cluster_rate 0.55.**
- `PROBE-DISAGREEMENT` — the f-004 ↔ f-020 contradiction at line 17 was the only open one and it sat on the highest-risk cluster. Produced f-024 (adjudication, refuted f-020's citation) and f-025 (the dropped rule 9), the run's most durable pair.
- `DEEPEN` on `fd-distsys-state-coherence` (risk 9, unconfirmed) — confirm or refute the staleness cluster. Produced f-026 (refuted as duplicative), f-027, f-028 (refuted).
- `DEEPEN` on `fd-evalscience-judge-validity` (risk 6, unconfirmed) — produced f-029 (CONFIRMED, with a grep over `orchestrate.py` returning zero state checks), f-030, f-031. This is where the staleness cluster stopped being an argument and became a fact.
- `STEER-WIDE` on `fd-warp-lot-economics` — novel_cluster_rate 0.74 ≥ 0.6, so widening still paid. Highest-return directive of the run: three findings, all novelty 3, all in clusters no other lens touched (f-032, f-033, f-034). Cost economics was a genuine hole in the lens set.

**Round 2 · probe · 3 directives · yield 8 · novel_cluster_rate 0.88.**
- Two `DEEPEN` on `fd-distsys-state-coherence` (risk 6, unconfirmed). The first found the pilot journal and confirmed the isolation cluster with two live incidents (f-035) plus the postmortem-misclassification smell (f-036) and the refuted lane-parity claim (f-037). The second went into `profile.py` and produced the meter cluster's hard evidence (f-038, f-039, f-040). Reading the actual instrument rather than reasoning about it is what raised this round's novel_cluster_rate to 0.88.
- `FUSE` — shared_heat 2, complementarity 2, redundancy 1 across `fd-distsys-state-coherence` × `fd-assay-independence`. Built `fd-fused-replay-independence` with an intersection-only hard constraint that explicitly names f-001 and f-020 as inadmissible parent-alone claims. Produced f-041 (the run's argmax) and f-042. One fusion attempted, one fusion that paid.

**Round 3 · probe · 2 directives · yield 6 · novel_cluster_rate 0.50.**
- `DEEPEN` on `fd-evalscience-judge-validity` (risk 6, unconfirmed) — produced f-043 (a self-labeled near-exact restatement of f-038, novelty 0), f-044 (the latent one-line fix, the round's best result), f-045 (codex glob root). The restatement is the first clear dryness signal.
- `STEER-WIDE` on `fd-shepherd-outrun-discretion` — novel_cluster_rate 0.88 ≥ 0.6. Produced f-046, f-047, and f-048, the run's only ledger-assigned taste score. The distance lens found the thing the technical lenses structurally could not: that the design has no "that'll do," no owner for the unrequested look, and an enforceability bullet that overclaims.

**Round 4 · halt · DRY.** No assay recorded in the gain history and no findings added to the ledger. Novel cluster rate had fallen from 0.88 to 0.50 with a self-declared restatement inside the round-3 yield; the controller halted rather than spend a fourth widening on a lens set that had covered its reachable ground.

Cumulative: 48 findings, 48 clusters, 9 cross-lens convergent, 19 slots. Yield curve 11 → 11 → 8 → 6 → 0.

---

## Caveats

- **No probes failed.** Every dispatched directive returned findings; `failed: 0` on all four probe rounds. Nothing was lost to agent error.
- **Round 4 produced nothing and is not in the gain history.** `rounds_run: 5` counts it; the gain history has four entries. Treat round 4 as a zero-yield confirmation round, not as a missing record.
- **The ledger's ref arrays are empty on disk.** Workflow mode does not persist cluster and convergence refs into the ledger rows; the clustering used here is the controller's script-computed state, supplied out of band. The `convergence_refs` visible in individual ledger rows are agent-authored, not controller-computed, and I used both.
- **Verification was budget-clamped on the meter.** Seven findings turn on `interstat/scripts/profile.py`'s behavior. I read the file and confirmed the lane logic, the argparse surface, the glob root, and the `get_pricing` call site directly. Nobody ran it under a constructed `model: inherit` case, so the laundering worked example (f-038, f-043) is confirmed by code reading, not by execution.
- **f-045 is unverified in its load-bearing half.** Whether Codex CLI actually writes transcripts outside `~/.claude/projects` was never checked; the finding confirms only that `profile.py` would miss them if it does.
- **Regions never reached.** Model capability — can Sonnet apply an execution-grade plan, can Opus read a diff — is declared out of frame by every base lens and was never probed; the journal's 5/5 verbatim-application result arrived from outside the review. Q-D (pool accounting) drew no finding at all: `fd-warp-lot-economics` was the only lens with pricing vocabulary and got one round. Nothing examined the plan file as an injection surface, or wall-clock latency, despite Q-C naming the codex lane as "slower." The human loop — mk as doctrine owner, the ruling cadence, what happens when the gate and the outcome disagree — went untouched until the journal forced it, and the journal's own proposed replacement metric is sitting unruled.
- **`fd-econ-principal-agent` × `fd-evalscience-judge-validity` was never fused.** Both lenses declare the other's territory as their own blind spot — economics cannot judge criteria completeness, measurement science has no vocabulary for why a specific actor defects — which is the textbook fusion candidate. It was not dispatched, and f-011 and f-013 sit on that unexplored boundary.
- **One artifact post-dates most of the review.** The pilot journal was written by the orchestrator during the same session that ran this review. Only round 2 reached it. Several round-0 and round-1 scores were estimated without it and have been re-scored here; a reader comparing this synthesis against the raw ledger will find those scores moved, in both directions, for that reason.
