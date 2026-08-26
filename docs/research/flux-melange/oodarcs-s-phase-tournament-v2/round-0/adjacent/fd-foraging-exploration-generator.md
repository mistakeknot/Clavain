# fd-foraging-exploration-generator — round 0

Seed position 1 (exploration advocate). Contracts first, verdicts second. All contracts are
stated in the charter's eleven-field form, compressed; every field named below is verified
against committed Skaffen code, not predicted.

## Findings Index

- [P0] contract-divert-patch-leaving — Divert: a marginal-value patch-leaving operation that reallocates the next unit of attention instead of emitting a report (§Candidate-generation requirement)
- [P0] contract-widen-sampling-policy — Widen: modulates sampling policy (model tier, thinking budget, candidate count) under measured non-stationarity; the runtime currently has no exploration variable at all (§Per-candidate contract)
- [P1] contract-sweep-mechanism-space — Sweep: bounded variation generation in *mechanism* space, reusing `internal/experiment`'s permutation machinery rather than a new store (§Candidate-generation requirement)
- [P1] no-s-exploration-regret-baseline — the null's affirmative loss is measurable and near-total: exploration exists as two ungated tools with no trigger, no budget, and no record (§Pilot contract)
- [P2] policy-class-undercount — the charter mandates exactly one policy-class candidate against ten artifact-class slots, so clustering will fold the policy class into Scout (§Candidate-generation requirement)

## Findings

### contract-divert-patch-leaving

- **Severity:** P0
- **Where:** §Candidate-generation requirement (target lines 60-71, the "changes the exploration/exploitation policy" slot); runtime anchors `internal/agent/phase.go:10-16,39-47`, `internal/tui/commands.go:196-215`, `internal/agent/deps.go:61-96`
- **What:** Contract for **Divert** — a name absent from both charters and not a synonym of Scout/Search/Speculate/Synthesize, because its output is an allocation change, not a document.
  1. *Input/preconditions:* the current phase's within-phase yield series — new files touched per turn, distinct grep/read targets per turn, repeated tool errors — all already present per turn in `agent.Evidence.ToolCalls` / `FileActivity` (`deps.go:66-67`).
  2. *Transformation:* apply a marginal-value-theorem test. When marginal yield of the current patch (this file set, this hypothesis) falls below the session's running average yield net of switch cost, leave the patch.
  3. *Output/consumer:* not a report — a `patch_leave` decision consumed by the loop itself: drop the current file set from context, widen the tool gate to `web_search`/`web_fetch`, and reset the yield window.
  4. *Authority/storage:* no new claims are produced, so no grade is needed; only a `divert` evidence record. This is the class of S candidate that is epistemically free.
  5. *Trigger/pace:* fast layer, within-session, per-turn evaluation.
  6. *Re-entry:* stays inside the current phase; Divert is a within-phase policy, so it never needs the FSM.
  7. *Runtime delta:* a yield accumulator plus a gate widening — no new phase constant.
  8. *Overlap:* none with Observe/Orient/Reflect/Compound, which have no allocation logic anywhere.
  9. *Failure/Goodhart:* thrashing (leave-rate gaming a novelty metric); bound by max leaves per session.
  10. *Losing condition:* on the pre-registered corpus, Divert loses if turns-to-useful-probe does not fall on hidden-mechanism tasks, or if leave-rate exceeds threshold on no-benefit tasks.
  11. *Classification:* capability + policy, explicitly not a phase.
- **Evidence:** the runtime has no allocation logic to compete with. `phaseFSM.Advance` (`phase.go:39-47`) moves forward one index only and errors at Compound (`IsTerminal`, `phase.go:49-51`); its sole caller is the human `/advance` command (`tui/commands.go:196-215`). Nothing computes depletion, yield, or switch cost anywhere in `internal/`.
- **Suggestion:** add Divert to the longlist explicitly as the policy-class representative, and record that it needs no letter — it is the cheapest way to satisfy the charter's "changes the exploration/exploitation policy" requirement.

### contract-widen-sampling-policy

- **Severity:** P0
- **Where:** §Per-candidate contract (target lines 77-89); runtime anchors `internal/router/router.go:20-27,80-107`, `internal/mutations/best.go:20-40`, `internal/session/session.go:80-92`
- **What:** Contract for **Widen** — a sampling-policy modulator, the bandit analogue of Divert at the slow layer.
  1. *Input:* non-stationarity evidence — the rate at which the Pareto front in `mutations` changes membership between sessions.
  2. *Transformation:* raise or lower the exploration parameter: `thinkingBudget`, model tier via `SelectModel`, and how many alternatives Decide is required to enumerate.
  3. *Output/consumer:* a per-session policy tuple consumed by `DefaultRouter` at the existing resolution point (`router.go:80-107`), which already merges six override sources and can take a seventh.
  4. *Authority:* none; it changes sampling, not claims.
  5. *Trigger/pace:* slow layer, per session.
  6. *Re-entry:* none needed.
  7. *Runtime delta:* one more clause in `SelectModel`'s resolution order plus an exploration parameter in `router.Config`.
  8. *Overlap:* Orient reads history but cannot change policy; `formatQualityHistory` and `Inspire` only inject text (`session.go:80-92`).
  9. *Failure:* oscillation between explore and exploit; damp with hysteresis.
  10. *Losing condition:* no improvement in validated discoveries at equal token budget across the corpus's shifting-environment bucket.
  11. *Classification:* capability/edge modifier.
- **Evidence:** the runtime is currently pure exploitation with a hardcoded uniform policy. `phaseDefaults` maps all six phases to `ModelOpus` (`router.go:20-27`) — zero phase-level allocation differentiation. The only history channel, `Store.BestSummary`, prints the *Pareto-best* prior sessions into the Orient prompt (`best.go:20-40`, injected at `session.go:80-84`): a philopatry bias with no exploratory counterweight. There is no variable in the codebase whose value is "how much to explore".
- **Suggestion:** carry Widen as a distinct shortlist entry, and require the tournament matrix to show at least one candidate whose delta is a router/gate parameter rather than an artifact.

### contract-sweep-mechanism-space

- **Severity:** P1
- **Where:** §Candidate-generation requirement (target line 60, "at least three candidates not named in either charter"); runtime anchors `internal/experiment/mutation.go:14-27`, `internal/tool/builtin.go:31-51`, `internal/experiment/store.go:33-52`
- **What:** Contract for **Sweep** — variation generation under shear, allocating budget to *mechanism* space (which implementation mechanism to try) rather than *task* space (which file or domain to look at). This distinction is the one the charter's candidate list never draws: Scout, Search, and Speculate all forage the task/knowledge space; Sweep forages the space of code variants.
  1. *Input:* a detected shear (benchmark regression, contradiction between measured metric and expected metric) plus a mutation spec.
  2. *Transformation:* expand a bounded permutation set — `ExpandMutations` already implements parameter sweep, swap, toggle, scale, remove, reorder, enum sweep, capped at `defaultMaxPermutations = 24` (`mutation.go:14-27`).
  3. *Output:* `ExperimentRecord` rows carrying `Hypothesis`, `Delta`, and `Decision` (`experiment/store.go:33-52`).
  4. *Authority:* measured, not speculative — this candidate is epistemically safe by construction because its output is a metric delta, not a claim.
  5. *Trigger/pace:* medium layer, on shear.
  6. *Re-entry:* keep/discard already re-enters via `KeepChanges`/`DiscardChanges` (`gitops.go:87-146`).
  7. *Runtime delta:* the tools exist and are gated to Act (`builtin.go:31-51`), so Sweep is a capability today; phasehood would require only a trigger predicate.
  8-11. *Overlap/failure/losing/classification:* overlaps Act, not Orient; failure mode is permutation explosion (already bounded at 24); loses if swept variants never beat baseline on the corpus; classification: capability.
- **Evidence:** `internal/experiment` is a complete, committed exploration-in-mechanism-space subsystem that neither charter mentions. Any tournament that treats "exploration" as synonymous with "outward document search" is ignoring the one exploration mechanism Skaffen already ships.
- **Suggestion:** enter Sweep on the longlist and state explicitly, per candidate, whether it allocates budget to task space or mechanism space; cluster only within a space, never across.

### no-s-exploration-regret-baseline

- **Severity:** P1
- **Where:** §Pilot contract (target lines 138-157); runtime anchors `internal/tool/builtin.go:19-22`, `internal/agent/deps.go:61-96`
- **What:** The affirmative cost-of-never-exploring statement the charter demands, in measurable form rather than rhetoric. Today's exploration capability is: `web_search` and `web_fetch`, registered for Orient/Decide/Act (`builtin.go:19-22`). It has (a) no trigger — nothing calls it unless the model happens to; (b) no budget — the only budget is the global token budget; (c) no record of *what was searched for* — `agent.Evidence` stores only tool *names* in `ToolCalls` (`deps.go:66`), never queries or results. So the null's exploration rate is unobservable in principle from the evidence stream.
- **Failure scenario:** the pilot runs, the no-S arm scores zero validated mechanism discoveries on the hidden-cross-domain bucket, and no one can tell whether the null explored and failed or never explored — because nothing recorded the search. The comparison then cannot attribute the difference to the S operation.
- **Suggestion:** before any arm runs, add a search-attempt record (query string, phase, turn) to the evidence schema for *both* arms. Predeclare the null's losing condition as: fewer than N recorded search attempts on hidden-mechanism tasks, or discovery rate at or below the no-benefit bucket's false-positive rate.

### policy-class-undercount

- **Severity:** P2
- **Where:** §Candidate-generation requirement (target lines 60-71)
- **What:** The mandated field lists ten artifact/report-shaped slots (Scout, Speculate, Stress-test, Simulate, Synthesize, two no-S variants, three unnamed) and exactly **one** policy-class slot (line 71). With a 10:1 ratio, contract-equivalence clustering (line 73) will merge the single policy candidate into whichever report candidate shares its trigger, and the tournament will conclude that S is a document — a conclusion produced by the seeding ratio, not by the evidence.
- **Evidence:** this is the failure mode my own lens is instructed to audit for: premature convergence on the artifact frame. The three policy contracts above (Divert, Widen, Sweep) are mutually non-synonymous — different spaces (task/sampling/mechanism), different pace layers (turn/session/shear) — and none survives clustering against Scout.
- **Suggestion:** raise the requirement at line 71 from one policy candidate to at least three, spanning attention allocation, sampling policy, and variation generation; and forbid clustering a policy candidate with an artifact candidate regardless of trigger similarity.

## Verdict

Three non-synonymous exploration contracts are on the board — Divert (attention allocation),
Widen (sampling policy), Sweep (mechanism-space variation) — and none of them needs a letter,
which is the strongest affirmative case for exploration this lens can make: the useful part of S
is a policy delta the runtime provably lacks (`phaseDefaults` is uniform Opus; nothing computes
yield or budget), not another report. The null's exploration is real but untriggered, unbudgeted,
and unrecorded, so its loss is measurable but only if search attempts are instrumented in both
arms first. The charter's seeding ratio, ten artifact slots to one policy slot, is the single
change most likely to decide the tournament before any evidence is examined.
