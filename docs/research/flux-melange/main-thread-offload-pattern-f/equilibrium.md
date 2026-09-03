---
artifact_type: melange-equilibrium
date: 2026-09-03
runtimes: ["claude", "codex"]
exchange_rounds: 3
equilibrium: false
---

# Parley equilibrium — main-thread offload (Pattern F)

Round 3 resolved all five standing contested topics. Both advocates reported `changed_mind: true`; each conceded at least one topic to the other, and claude conceded two of its own prior affirmations outright. One new contested topic opened — not over analysis, over remedy. Moderator re-verified every load-bearing citation below against the live repositories and a fresh meter run; deltas from the advocates' own readings are recorded where they matter.

## Consensus

### Meter and gate construct

**Codex execution lane is invisible to the gate's meter** — *claude, codex*
`profile.py` cannot observe Codex-routed execution, so any Codex-lane item falls outside the gate's per-goal denominator — a schema incompatibility, not a wrong glob root: `profile.py:25,42-52` scan only `~/.claude/projects/**/*.jsonl`; 5028 `.jsonl` rollouts exist under `~/.codex` and 0 of 20 sampled contain the substring `usage`, so `:59`'s usage-substring skip and `:68`'s `message.get('usage')` would discard every line even with the root widened. `routing.yaml:27-32` makes Codex the default executor backend.

**The meter has no goal unit, which is the unit the gate names** — *claude, codex*
Target:15 defines the denominator per goal; `profile.py:91-101` exposes only `--days`, `--session`, `--since`, `--until`, `--json` — no goal, bead, task or run identifier. Session/time filtering can proxy one carefully isolated goal and cannot generally measure the gated unit.

**Unrelated subagents contaminate the offload denominator** — *claude, codex*
`profile.py:38-39,80` classify by file path or `isSidechain` alone, then `:112-120` place all such output in one denominator, so any research or utility agent improves the gate without executing Pattern F work. Live instance, now grown: the Haiku 4.5 lane stood at 30 messages in the journal and reads 180 at moderator verification — a 6x increase of pure contamination. Deleting that lane moves `main_cost_share` from 0.262 to 0.280, so the contamination is worth 1.8 points in the passing direction.

**The output-share gate lacks construct validity** — *claude, codex*
Target:7-9 diagnose context cost; target:15 gates generated-output share, and the two dissociate in the run the gate governs — journal 86% output share (gate 50%, failed) against 35% cost share (baseline 85%, a 2.4x improvement in the thing the design exists to fix).

**The gate's denominator is Goodhartable by delegated waste; fragmentation runs the other way** — *claude, codex*
`total_out = main + subagent` with no absolute-output or quality term (`profile.py:112-120`), so added subagent verbosity or a FAILED retry round mechanically lowers main share — a strictly worse run scores strictly better. The fragmentation arbitrage is inverted at observed ratios because splitting an item raises plan authorship faster than executor output; claude self-refuted its own f-032 mechanism and holds the magnitude as second-order (~2 points per extra retry round).

**The gate's own number now includes the cost of reviewing the gate** — *claude, codex* (claude filed; codex ratified round 3)
Re-running the journal's exact invocation returns a different number every time it is run, always in the passing direction. Four readings of one window: journal 0.86 / 0.35; claude round 2 0.816 / 0.286; codex round 3 0.829 / 0.300 then 0.815 / 0.265; moderator round 3 **0.815 / 0.262** at `total_cost` 51.79. The subagent rows grew from 253 Sonnet / 93 Opus (journal) to 494 / 211 — the melange review loops of this design document. Codex's concession states the consequence precisely: unrelated later work in the same session improves a historical goal's gate score, and exact attribution to individual reviews is impossible with this instrument. The drift did not stop for the exchange — three readings taken inside round 3 alone differ (Haiku 175, 176, 180 messages).

**The proposed replacement gate inherits the exact Goodhart it was written to fix** — *claude* (novel round 3; filed after codex's last write)
The doctrine's proposed repair — "main-thread share of API-equivalent cost per goal ≤ 50%" (`commands/model-routing.md:175`) — is the same defect in a different numerator. `profile.py:115-123` computes `main_cost_share` as `lane_cost['main'] / (lane_cost['main'] + lane_cost['subagent'])`: a ratio whose denominator the subagent lane controls, with no absolute-cost term, structurally identical to `main_output_share` two lines above it. Moderator-verified in source and in the live drift above — the goal's absolute cost rose from ~$23 to $51.79 while its score improved by 8.8 points. A gate that is a share cannot be repaired by changing what it is a share of; it needs an absolute term.

**Frontier-subagent meter repair: add a term, do not reassign the lane** — *claude, codex*
Moving a frontier subagent into `lane_out['main']` would corrupt the topology metric the gate rests on in order to fix a tier metric. Rows already carry both dimensions (`profile.py:103-113`); the defect is the scalar summary (`:115-123`), and the fix is a separate frontier-token or pool-cost term beside the lane shares. Two refinements: `get_pricing` (`cost.py:106-126`) maps unknown models to Opus pricing, so it is not a safe tier classifier; and the pilot window has no frontier-model subagent row at all, so the laundering path is latent rather than realized.

### Economics

**"Offload tripled context volume and won on tier price" is withdrawn** — *claude, codex* (was Contested #1, heat 5)
Codex's counterfactual challenge is sustained and claude conceded past it. Codex: the journal presents one treated window with no control arm, and the ratio is not even stable — subagent-to-main cache reads read ~3.2x in the journal and 5.5x on re-run, so it is a mutable window composition, not a causal estimate. Claude: the stated *mechanism* is factually wrong, not merely unsupported. Synthesis line 58's "Sonnet and Opus cache reads are cheaper per token than Fable's" is false for Opus — `cost.py` prices Fable 5.1 cache reads at $0.25/MTok (`:22`) against Opus 5 at $0.50/MTok (`:34`), moderator-verified. On the exact cost term the design's diagnosis names, offload is **more** expensive: the subagent lanes' 63,316,350 cache reads cost $16.87 at their own tiers versus $15.83 had the identical volume been read on the Fable main thread. Both halves of the sentence go.

**The tier discount is a rebate on a cost Pattern F's own fresh-context mandate manufactures** — *claude* (novel round 3; filed after codex's last write)
The economic win is real but sits in a token class neither synthesis discussed. Repricing the live subagent mix at Fable 5.1 rates gives $101.85 against $38.22 actual (moderator re-run) — a genuine 2.66x — but **$85.10 of that, 83.6%, is cache *creation*, not cache read**. Cache creation is the most expensive input class at every tier (Sonnet's $2.50/MTok is 12.5x its own cache read), and cache-write volume is exactly what a fresh context manufactures: the subagent lanes carry 6,808,217 cache-creation tokens against the main lane's 542,373, a **12.6x ratio**, because target:16-17 mandate two cold contexts per item while a continuing main thread re-reads a warm one. The headline result is therefore a tier rebate on a cost the pattern creates by construction. Consequences: fresh-context batching becomes the primary economic lever rather than an experimental nicety; the win's fragility is the `cache_create` rate ratio specifically, not the tier gap generally; and a pool regime that ignores cache reads but charges writes would penalize exactly this shape. *Standing caveat, recorded not adjudicated: codex's methodological objection above — same-window repricing is not a matched control arm — applies to this reprice too, and codex has not filed against it.*

**Q-D's premise is unsound in its enumeration** — *claude, codex* (was Contested #4, heat 4)
Target:33's "The shape above is robust to both" regimes is contradicted by the data. Codex: under a cache-ignored regime, output-priced cost is 93.9% main on the exact window (moderator-verified: main output 77,997 tokens at $50/MTok = $3.90 against $0.25 delegated), so the design is not shown robust there. Claude withdrew its "premise sound" ruling as unevidenced and supplied the missing sensitivity analysis, which runs against it on both named arms: cache-read-weighted is mildly *unfavorable* (+$1.04), output-weighted barely moves. The favorable regime is a third one the question does not name — cache-creation-weighted. Q-D moves from "premise sound" to "premise wrong in its enumeration."

### Pilot evidence and the record

**The journal's headline "4 of 5" does not reconcile to its own table** — *claude, codex* (was Contested #1, heat 6)
Row 1b's Validator cell reads `pending` and that row's beyond-gauge credit goes to the *executor*. The defensible statement is **4 of 4 completed validations produced a beyond-gauge finding** — a stronger rate on a smaller n. Three counts are now in circulation, one hop apart, none of which is the table's: the journal table's 4+2+2+1 = **9** validator-attributed items, the journal prose's **four of five**, and `commands/model-routing.md:163`'s "passed all five on criteria and found six real defects" — **six**. Claude's new evidence closes the snapshot-timing escape: moderator-verified live, `git branch -a --contains 4fa4628` in interstat returns only `sweep/2026-09-02` and no main, while pilot 1's `8672cc3` is on `main` and `origin/main`. Hours after the journal, 1b's work is still not cherry-picked and its validator still has not run. None of the three counts should be treated as canonical until reconciled.

**Q-A has already been transcribed into doctrine** — *claude, codex* (was Contested #2, heat 5; **remedy now contested — see below**)
The prospective consensus was overtaken by the working tree. `commands/model-routing.md:163` states "(design-doc Q-A resolved: it adds information, specifically about the gauge)" while target:17 is unchanged verbatim and still permits only frozen-criteria PASS/FAIL. Claude's added finding, moderator-verified: the doctrine did not merely assert resolution, it **stripped the clause that makes the result readable as evidence**. Journal:3 defines validators as "judging only the plan's VERIFY block, **then reporting what the gauge missed**"; the doctrine sentence drops the second clause, leaving a sentence consistent with target:17's PASS/FAIL-only validator having found those defects — which target:17 forbids. The correction is still free: `git status --porcelain commands/model-routing.md` returns ` M`, Clavain HEAD f12603e. It stops being free at the next commit.

**Q-A remains open for the validator Pattern F specifies** — *claude, codex*
The piloted validator ran a wider contract than the design authorizes: target:17 permits judgment ONLY against frozen criteria with PASS/FAIL output; journal:3 adds the reporting clause; `orchestrate.py:614-619` additionally asks reviewers for spec completeness, scope control, correctness and edge cases. Q-A needs separate arms — mechanical frozen-oracle replay vs semantic review — and line 17 needs a second, non-binding output channel before the pilot result belongs to this pattern.

**Q-B: one arm is answerable by conservation; the rest is not answerable with this meter** — *claude, codex* (was Contested #5, heat 3)
Both now hold the split verdict. Executor and validator reports are a strict subset of subagent output, so subagent output is a hard ceiling on report ingestion, computable with no phase attribution: moderator re-run gives subagent output 17,743 tokens against main-lane cache read 11,419,558 over 34 turns — **0.155% single-pass, 5.28% even under the absurd assumption that every report token arrived at turn 1 and was re-read on all 34 turns**. "Reports dominate" is refuted by conservation, and Q-B's proposed remedy (cap report size) is scoped to a term bounded under 5.3%. The remaining ~95% is **unidentifiable with this instrument** — `profile.py:82-87` discards prompt content and message ancestry after extracting usage, and `:103-123` aggregates by lane and model only, so it cannot separate a standing prefix from accumulated conversation. Claude explicitly does not re-claim the prefix hypothesis; its new datum (main turns 29 → 34, cache read 9.8M → 11.42M, ctx/turn 344K → 352K — context scaling with turn count at near-constant per-turn size) is consistent with an early-and-persistent component but cannot separate the candidates.

**Pilot evidence needs separate run, validation-attempt and finding identities** — *codex* (novel round 3; filed after claude's last write)
The count collision exposes a schema defect deeper than a missing independence boolean: executor runs, validator attempts and discovered findings are being treated as one cardinality. A durable record needs one validation-attempt row bound to item, attempt, validator contract and result tree, plus separately linked finding rows with first-observer provenance. Otherwise "five runs", "four completed validators", "six defects" and "nine table items" can all enter doctrine without a mechanically detectable contradiction. `commands/execute-plan.md:41-50` emits one `plan_execution_outcome` only at whole-command completion, with aggregate criteria counts and no attempt, result-tree, finding or first-observer identity.

**The first pilot set has weak external validity** — *claude, codex*
Five runs in one shakedown session establish that semantic validators can find omissions; they do not estimate a steady-state omission rate or durable economic value. Target:3 still labels Pattern F a design for review.

**The live evidence has no durable repository identity** — *claude, codex*
In Sylveste the charter, condition and journal are untracked; in Clavain the target brainstorm and the entire flux-melange research directory are untracked and `commands/model-routing.md` is a working-tree modification only (Clavain HEAD f12603e, Sylveste HEAD 6fa1a080). This is load-bearing rather than hygiene: the doctrine amendment — the only would-be-tracked artifact in the set — names all four untracked paths as its sources in its own text (`model-routing.md:160`), so it cannot be audited by anyone reading the commit, and the counts have already drifted across exactly that hop. A pilot verdict envelope should bind target, journal, synthesis, doctrine revision and evaluated trees to commit IDs before any of it becomes doctrine.

### Validator contract and integrity

**Pinning the result tree does not destroy validator independence; line 17 does** — *claude, codex*
Converged from opposite directions. Codex: pinning removes state drift without forcing the validator's method, and `orchestrate.py:610-619` demonstrates a semantic reviewer that survives a pin, so the replay-only contract creates the null check, not the pin. Claude: that reviewer is precisely not Pattern F's validator (target:17 bars taste and edge-case probing), so the dilemma is real for the document as written and dissolves only under the Q-A amendment both hold is required. Both locate the fault in line 17.

**The validator-mutation hole is real and was mis-scoped as Pattern F's headline introduced risk** — *claude, codex*
Pattern F never routes its Opus validator through `scripts/orchestrate.py`, a separate shipped review pipeline; the correct Pattern F finding is that its validator contract has no integrity guard at all, with `orchestrate.py` supplying a warning about how a naive guard fails. Claude conceded that `_review_engine_for` (`:660-662`) returns `claude` for `tier=='deep'` and `:427` says that engine "resolves to opus per the validator doctrine", so the deep-tier reviewer is a genuine role-analogue. Unrebutted: the sole workspace-write grant (`:711-714`) is gated on `engine=='codex'`, so the lane nearest Pattern F's validator ships with the mutation ban on. No orchestrate run directory exists — the five pilots were Task-tool spawns that never traversed this path.

**A prompt-level or tool-name-level ban is not the enforceable remedy; HEAD + tree-ID assertion is** — *claude, codex*
Mutual cross-concession; each advocate abandoned its own round-1 horn. The enforceable remedy is orchestration-level isolation or before/after HEAD plus tree-ID assertions, because a tool policy cannot express a tree invariant. Open residue with no advocate: whether a Task-tool spawn — the lane the pilots used — can be given the dispatch read-only profile at all.

**The shipped read-only lever does not cover the mutation it exists to prevent** — *claude, codex* (claude filed; codex ratified round 3)
`dispatch.sh:1063-1068` sets `--permission-mode dontAsk` and disallows only `Edit,Write,NotebookEdit` — tool-name-shaped, not capability-shaped, and **Bash is omitted**. A validator configured exactly as Clavain's default read-only reviewer can run `git commit -am` through Bash, leaving `git status --porcelain` byte-identical while HEAD moves. Codex's concession: the orchestrator never compares HEAD or tree IDs across review (`orchestrate.py:716`, `:738-744`), so the prompt prohibition at `:585-590` is advisory, not an integrity boundary.

**The contamination guard is defeatable and no pre-review tree binds to the verdict** — *claude, codex*
`orchestrate.py:716` captures `dirty_before` and `:738-744` compares `dirty_after != dirty_before`; a commit preserves that equality while HEAD moves. `:772` captures `head0` once before the executor and `:1174-1188` journal only the eventual HEAD, so no pre-review/result-tree pair ever binds to a verdict.

**The verdict register exists, is unwired and fail-open, and its schema would misreport the pilots — worse than by omission** — *claude, codex* (amended by claude's round-3 self-correction)
`commands/execute-plan.md:41-52` emits `plan_execution_outcome` only on that command's completion path, behind three fail-open layers. Claude corrected its own earlier "bare pass boolean" characterization in both directions: the context object **does** carry `author_model`, `executor_model` and `validator_model`, so the register can distinguish who validated and at what tier — but `pass:($cf==0)` derives the outcome **arithmetically from `criteria_failed`**, the gauge count. The verdict field never consults the validator at all; it is a restatement of the gauge. A validator that passes on criteria while reporting a real defect — the journal's entire result, all four completed rows — serializes identically to a validator that found nothing, and a validator that fails an item for a reason outside the frozen criteria cannot be expressed even in principle. Wiring the register as written would make the pilots' finding *structurally unrepresentable* while feeding calibration a clean five-for-five pass record. The remedy is not "add an independence field" but "stop deriving pass from the gauge and give the validator its own outcome channel" — the same amendment target:17 needs, surfacing a second time in the durable store.

### Integration, control flow, and process

**Pattern F conflicts with /execute-plan's mandatory human checkpoints — and with its external-agent opt-in rule** — *claude, codex* (codex filed; claude ratified and extended round 3)
Target:3 names `/execute-plan` an owner and target:15 describes a thin orchestrator that spawns, validates and lands, while `commands/execute-plan.md:11` requires "Stop at checkpoints for user approval. Batch review checkpoints are mandatory — never auto-approve" and `:23-26` places a mandatory architect review checkpoint after each batch. Codex added the skill-level evidence: `:39` mandates `skills/executing-plans/SKILL.md`, which requires approval at `:58`, a per-batch "Ready for feedback" report at `:83-85`, and feedback before the next batch at `:87-89`. Claude added a second conflict that fires on the **default path** rather than at a checkpoint: `:13` states "External agents (Codex, interserve) require explicit user opt-in", while target:16 offers the codex lane as a first-class executor and `config/routing.yaml:27-32` makes `default: [codex]` the enforced route for every unmapped class (moderator-verified). The executor lane routing makes the default is the one the command forbids without human opt-in. `/execute-plan` as written can host neither Pattern F's autonomy nor its default executor, and the design says nothing about either.

**Q-C: parity machinery exists, has never produced a verdict, and evaluates the wrong axis — while the Codex lane is already the enforced default** — *claude, codex*
`mode: enforce` with `default: [codex]` routes every unmapped auto-dispatch class to Codex today, so Q-C's future-tense framing is stale and the metering omission already affects the default path. The harness docstring disclaims the relevant proof (`executor-parity-eval.py:11-13`); its arms are `--cheap` (kimi) vs `--strong` (codex), the direction opposite to Q-C; and a verdict requires stage-3 judge scores from a queue file that does not exist on this machine. `routing.yaml:24` asserts the allowlist rule eight lines above the default that defeats it.

**Doctrine Rule 9 was dropped from Pattern F** — *claude, codex*
Target:19 cites pilot-1's 6/6 gauge defects to justify escalation but never adopts the mechanism doctrine built in response to that same finding: the mandatory pre-freeze gauge dry-run, blocking, by a model other than the plan's author (`commands/model-routing.md:114-130`), already implemented as blocking Step 0 of `commands/plan-review.md:21-34`. It should precede executor dispatch rather than be discovered through strikes.

**"Inheritance closed" is an overclaim in the enforceability section** — *claude, codex*
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` selects which model answers at 48 command/skill sites and 25 doc-shaped agents; it installs none of Pattern F's behavioral contract at any of them. The bullet sits at target:24 under "What makes it enforceable rather than aspirational" while the contract lives at target:16-19. The `model: inherit` escape hatch has no named auditor — structurally the same "requires a named integration owner and has none" diagnosis at target:7 that motivates the document, recurring inside Pattern F's own closure.

**Pattern F has no non-strike failure category** — *claude, codex*
Target:19 offers only executor failure and validator rejection. `commands/model-routing.md:110-113` explicitly excludes sandbox denials, approval gates, auth expiry, rate exhaustion and infrastructure errors from strikes. Without that field, unrelated failures consume the two-strike budget and escalate to the scarce tier.

**The two-strike counter has no durable storage** — *claude, codex*
Target:19 names two strikes with no persistence boundary. Even the adjacent orchestrator keeps rounds in a local loop (`orchestrate.py:792-846`) and journals the TaskResult only after `future.result()` returns (`:1099-1118`), so a mid-pipeline process loss erases strike state.

**Partial-application state is unspecified** — *claude, codex*
Target:16 mandates a commit on success; target:19 returns the item after strikes without defining repository state — no base tree, no record of commits already produced, no unfinished-task list, no cleanup owner. **Pilot 1b is the live instance**, moderator-verified: an item whose executor produced a commit (`4fa4628`), whose validator never ran, whose code sits on `sweep/2026-09-02` and no main, and which the doctrine folds into "passed all five on criteria" with no outstanding-work field anywhere.

**"Gauge defect" is too coarse a taxonomy for the pilot postmortems** — *claude, codex*
Journal:9-13 files branch mismatch, concurrent-writer interference and impossible grep expectations in one column. A logically impossible grep expectation is an oracle defect; an assertion made unreachable by a concurrent writer is an isolation confound. The column obscures whether to repair the plan, isolate the workspace, or retry without charging a strike.

**Q-E's candidate is not the new failure mode** — *claude, codex*
Stale-plan execution already existed in the baseline. The genuinely new fault is loss of unstated invariants at the fresh-context boundary: the orchestrator held 344K ctx/turn and had been working on the sweep branch, so the branch fact was not stale to it — it was tacit and failed to survive serialization into the plan file. Claude's validator-side extension survives as a second instance of the same boundary.

**Fresh-context batching was never tested — and is now the primary economic lever** — *claude, codex*
Target:16-17 mandate two fresh contexts per item without motivating that granularity or comparing batched execution and validation. Promoted this round from experimental nicety to the main economic question by the cache-creation finding: the mandate is what generates the 12.6x subagent cache-write volume that carries 83.6% of the repriced spend.

**The plan author is scored on a metric its own thoroughness degrades** — *claude, codex*
The orchestrator authors the execution-grade plan and is judged partly on main-thread output share (target:15), with no independent plan-quality term to offset the pressure to shorten that artifact. Current ratios happen to make detailed plans operationally useful, which is luck rather than design.

**Model capability is a shared blind spot** — *claude, codex*
Both syntheses underweighted whether the cheaper executor can faithfully apply plans and whether the validator can perform useful semantic review; every base lens declared it out of frame. The journal supplies encouraging evidence from outside the review (5/5 verbatim application; validator information gain), but neither loop designed a capability or quality arm.

**No one owns the unrequested look** — *claude, codex*
The document names implementation and doctrine owners and the lane meter as enforcement, but no owner or cadence for looking beyond the predefined lane report, and no adjudicator for metric/outcome divergence. This pilot's decisive construct-validity finding arose precisely from interpreting a disagreement the literal gate could not explain.

### Method (retired meta-claims)

**The empty disagreement register showed where each loop stopped looking** — *claude, codex*
Both retired the meta-claim. An empty formal register is not proof of internal consistency, and the co-located journal contradicted f-018's realized-value prediction while being admissible during the run. One residue favors neither reading: both registers were computed over lens outputs only, so a register scoped that way is structurally blind to contradictions between the review's conclusions and the target project's concurrent live state — which is exactly where the premise-challenging topics lived.

**A zero-taste ledger is a property of the lens set, not of the target** — *claude, codex*
Reading `taste: 0` on every row as evidence that no defensible taste call exists was an inference from lens metadata to artifact property; at least one grounded structural overclaim exists in the target's own prose. The diagnosis of why the ledger was empty — the distant lenses produced operational claims, not aesthetic judgments — stands, now scoped correctly.

## Contested

### 1. Given Q-A was already transcribed, is the remedy to amend-and-preserve or to retract? — heat 5

Both advocates agree on every fact: the doctrine sentence is defective, target:17 is unchanged, the pilot cardinality is unresolved, and the working tree is still uncommitted. They disagree on what to do about it, and the disagreement is consequential because the window closes at the next commit.

**claude — amend line 17 AND restore the stripped clause; preserve the result.**
The remedy is no longer "amend line 17 or retract the doctrine line" but both halves of a repair: amend target:17 to add the second, non-binding output channel, *and* restore "then reporting what the gauge missed" to the doctrine sentence. Retracting the resolution claim alone would leave a defect count whose provenance is still invisible — a reader of `model-routing.md:163` would still see six defects attributed to a validator whose authorized contract could not have produced them. The information gain was real; what failed is its transcription.
*Evidence:* journal:3 (validator contract with the reporting clause); `commands/model-routing.md:163` (clause absent, "design-doc Q-A resolved"); target:17 verbatim unchanged; `git status --porcelain commands/model-routing.md` → ` M`; Clavain HEAD f12603e. All moderator-verified.

**codex — retract "resolved" first; preserving the result is premature.**
Given the unresolved pilot cardinality, retracting "resolved" is presently safer than amending the target and preserving the result. The claimed information gain rests on a defect count that does not reconcile — six in doctrine, nine in the table, across four completed validations, not five — so preserving the result means preserving a number that has no canonical value. The prospective consensus was overtaken by the working tree; the safe move is to unwind the claim, not to re-express it.
*Evidence:* `commands/model-routing.md:163`; `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:17`; `git status` reports the file modified but uncommitted; journal:7-13 four PASS rows and one pending row against :17's five-validation prose.

*Moderator note: this is a genuine remedy fork, not a residue of the resolved tense dispute. Both remedies are cheap only while the file is uncommitted, so it is decidable now and expensive later. It is also the one item in the table that mk must actually rule on rather than merely accept.*

## Exchange log

**Round 1 — opening syntheses.** Two independent loops produced overlapping structural findings on the gate, the validator contract, the strike machinery and the verdict register. Both loops filed empty disagreement registers. Contested at close: validator-mutation scoping, the pin-vs-independence dilemma, and whether `orchestrate.py` governs Pattern F's roles at all.

**Round 2 — premise challenges and mutual cross-concession.** Codex challenged two premises no lens had questioned: the "tripled and won on price" causal claim (no counterfactual) and Q-D's robustness (no cross-accounting sensitivity). Claude filed two challenges to the shared consensus itself: the journal's 4-of-5 does not reconcile to its own table, and Q-A had *already* been transcribed into doctrine, changing the remedy in kind. Each advocate abandoned its own round-1 horn on the mutation remedy, converging on HEAD + tree-ID assertion. Claude filed two unopposed items after codex's last write (the Bash gap in the read-only lever; the gate measuring the cost of its own review); codex filed one (the `/execute-plan` checkpoint conflict). Five contested topics stood at close.

**Round 3 — full resolution of the standing table, one new fork.** All five contested topics resolved, four by concession and one by mutual convergence. Codex conceded the journal reconciliation, the Q-A transcription tense, the Q-B report-ingestion arm (accepting claude's conservation bound), the read-only lever's Bash gap, and the realized gate contamination. Claude conceded "tripled and won on price" and went past codex's challenge to falsify its own stated mechanism against the live rate table, and withdrew its Q-D affirmation while supplying the sensitivity analysis codex said was missing — which ran against claude on both named arms. Three novel findings, all unopposed: claude's **cache-creation rebate** (83.6% of the repriced win is cache *writes*, a cost the fresh-context mandate manufactures at 12.6x, which relocates the win's fragility and promotes batching to the primary economic lever); claude's **replacement-gate Goodhart** (the doctrine's proposed repair is the same share-shaped defect in a new numerator, demonstrated live by this session's own drift); and codex's **three-cardinality schema defect** (runs, validation attempts and findings need separate identities or contradictions enter doctrine undetectably). Claude also self-corrected its verdict-register characterization in a direction that strengthened the finding: `pass` is derived arithmetically from the gauge, so the pilots' result is not merely unrecorded but structurally unrepresentable. One new contested topic opened — not over analysis but over remedy: amend-and-preserve versus retract. Both advocates reported `changed_mind: true`.

**Moderator verification (round 3).** Every load-bearing citation was re-checked against live repositories and a fresh meter run. All verify. Two deltas worth recording: the meter drifted a *third* time during this round alone (Haiku lane 175 → 176 → 180 messages across the two advocates' runs and the moderator's; `total_cost` $50.93 → $51.79; `main_cost_share` 0.267 → 0.265 → 0.262), which is itself the strongest available instance of the contamination finding — the exchange about the gate moved the gate. And codex's 93.9% and claude's 81.5% are not in conflict: they measure output-priced *cost* share and output *token* share respectively, and both verify exactly.
