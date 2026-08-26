# fd-cybernetics-loop-topology — round 0

Target: `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md`
Grounding verified in-repo: `internal/agent/phase.go`, `internal/agent/agent.go`, `internal/tool/registry.go`,
`internal/tool/builtin.go`, `internal/tool/web_search.go`, `internal/agent/deps.go`, `internal/mutations/signal.go`.

Method note: for each shortlisted candidate the charter should force the reviewer to draw the loop with and
without the box. I did that for Scout against the runtime that actually implements OODARC (Skaffen's
`phaseFSM` + phase-gated `Registry`), and the diagram does not change — except in one place where it
*cannot* be drawn at all.

## Findings Index

- [P1] reentry-edge-has-no-transition-and-no-channel — `Scout ⇢ Observe` needs a backward edge the FSM does not have and an ingestion channel Observe does not have (§Current leading candidate: Scout)
- [P1] trigger-is-not-a-predicate-over-loop-state — "unresolved contradiction" and "detected shear" have no referent in any state record the loop carries (§Current leading candidate: Scout)
- [P1] no-deletion-test-in-the-tournament — eight criteria, none asks which edge or state variable disappears when the box is deleted; Scout's mechanism already exists as an Orient-gated capability (§Tournament criteria)
- [P2] gate-sits-at-slowest-point-while-triggers-fire-at-fastest — full-cycle deadtime, and the phase Scout occupies has no search tools at all (§Current leading candidate: Scout)
- [P2] orthogonality-axiom-is-asserted-then-contradicted-by-a-candidate — Share is inherently multi-agent, so it is a topology change, not a loop element (§Existing model, §Previously considered alternatives)

## Findings

### reentry-edge-has-no-transition-and-no-channel

- **Severity:** P1
- **Where:** charter:41-47 (`Reflect → Compound → Scout ⇢ Observe`); `internal/agent/phase.go:9-52`; `internal/tool/registry.go:49-72`
- **What:** The charter draws the edge as if it existed. In the runtime it is unrepresentable in two independent ways. (1) *No transition.* `phaseFSM` exposes `Current()`, `Advance()` and `IsTerminal()` only; `Advance()` increments an index into a fixed `phaseOrder` slice and returns `cannot advance past %s` at Compound (`phase.go:39-49`). There is no `SetPhase`, no backward edge, no rewind — the "coupled loop" is implemented as a monotone line. (2) *No channel.* Even granting the transition, Observe's entire tool surface is `read, glob, grep, ls` (`registry.go:50-52`) — local workspace inspection. A scout report can only become an Observe input by being written into the workspace, i.e. onto exactly the same read surface as ground-truth source files. The charter never says who fires the `⇢` edge, on what authority, or how many times per cycle it may fire.
- **Evidence:** `phase.go:10-16` (`phaseOrder` literal), `phase.go:39-49` (`Advance`), `phase.go:50-52` (`IsTerminal` at Compound); `registry.go:50-52` (Observe gates) vs `registry.go:165-177` (`Tools(phase)` returns only gated tools).
- **Failure scenario:** An implementer reads charter:44 as a spec and appends `PhaseScout` to `phaseOrder` after `PhaseCompound`. Compound stops being terminal, so `IsTerminal()` now fires one phase late; the Compound-gated quality-signal write (`agent.go:246-253`) still runs at Compound, so the session's durable artifact is cut *before* Scout runs and nothing Scout produces can influence it; and the session ends in a phase with no successor. Whoever fixes that adds an unguarded reset of `f.index = 0`, and the session now cycles with no firing bound.
- **Suggestion:** One added clause in §Required adversarial review item 4: *"Name the concrete transition this candidate adds to `internal/agent/phase.go:phaseOrder`/`phaseFSM` — forward edge, backward edge, or none — the actor that fires it, the per-cycle firing bound, and the tool-gate entry in `internal/tool/registry.go:defaultGates` through which its output re-enters."* A candidate that needs no transition has answered the phase-versus-capability question by itself.

### trigger-is-not-a-predicate-over-loop-state

- **Severity:** P1
- **Where:** charter:31 ("accepts a validated mechanism, unresolved contradiction, or detected shear"); charter:78 (spec item 3)
- **What:** The leading candidate holds the leading slot on a trigger no reviewer can evaluate mechanically. `grep -rni shear` across the repo returns only this charter and the melange outputs derived from it — there is no shear detector, field, or event. "Unresolved contradiction" is equally unrepresentable: the loop's per-turn state record `agent.Evidence` carries phase, turn, tool calls, token counts, stop reason, outcome, complexity, budget (`deps.go:60-88`) and its cross-session record `mutations.QualitySignal` carries task type plus hard/soft/human rate scalars (`signal.go:16-47`). Neither can express "two beliefs conflict." Only "validated mechanism" has a referent — a Compound-phase write. Charter:78 asks each candidate to state a trigger but never requires it to be decidable, so an undecidable trigger costs a candidate nothing in the tournament.
- **Evidence:** verified grep (charter is the sole non-derived hit for "shear"); `deps.go:60-88`; `signal.go:16-47`; charter:78.
- **Failure scenario:** Scout wins and an implementer must decide when it fires. With no state predicate the trigger degrades to model self-report ("this feels stuck"), which is neither schedulable nor auditable: evidence records show scout turns with no antecedent, the operation's pace layer becomes whatever the model's mood is that turn, and a reviewer cannot distinguish a missed Scout from a correctly skipped one — so the operation can never be tuned or retired on behavioural grounds.
- **Suggestion:** Amend charter:78 to *"Trigger stated as a predicate over named loop state that exists today (e.g. `QualitySignal.Soft.ToolErrorRate > x` for N consecutive sessions of one `TaskType`, or a Compound write), plus the natural pace layer that predicate implies."* Then flag every candidate that cannot be written that way — including Scout, whose "shear" must either be defined in loop-state terms or struck.

### no-deletion-test-in-the-tournament

- **Severity:** P1
- **Where:** charter:89-96 (§Tournament criteria); `internal/tool/builtin.go:20-22`; `internal/tool/web_search.go:75-87`
- **What:** All eight criteria are semantic, procedural, or aesthetic. "Semantic distinctness" scores overlap of *definitions* against O/O/R/C; nothing scores whether the loop's transfer function changes when the box is deleted. So a candidate that is fully realizable as a tool registered to an existing phase can score maximum distinctness and win. That is not hypothetical here: outward search already exists as an Orient-gated capability — `web_search`/`web_fetch` are registered for `{Orient, Decide, Act}` (`builtin.go:20-22`) and `tierForPhase` deliberately spends the `deep` Exa tier in Orient and the `instant` tier in Act (`web_search.go:76-87`). Skaffen has already encoded "exploration belongs to Orient, exploitation belongs to Act" as a gain schedule on one tool. Scout's core mechanism therefore has a home that adds no edge and no state.
- **Evidence:** charter:89-96; `builtin.go:19-22`; `web_search.go:75-87`; `registry.go:136-153` (`RegisterForPhases` is the whole cost of the capability implementation).
- **Failure scenario:** The tournament crowns a winner whose real implementation diff is one `RegisterForPhases` call plus a prompt, while the charter's required output (charter:117) reports it as a new loop element with a confidence figure. The team then pays acronym cost, doc cost, `defaultGates` cost and Intercore role-map cost for a change that leaves the diagram identical — and the exploration/exploitation question the S was supposed to regulate stays unasked, because the honest diagnosis is that Orient is under-specified, not that a phase is missing.
- **Suggestion:** Add a ninth criterion and make it a *gate*, not a score: *"**Topological necessity:** name the edge, state variable, or authority boundary that disappears if this box is deleted, and draw the loop with and without it. If the diagram is unchanged, the candidate exits the phase tournament and is scored as a capability."* Add a paired question to §Required disagreement probes: *"Is S the right regulator for the exploration/exploitation imbalance, or is it a symptom of Orient being under-specified?"*

### gate-sits-at-slowest-point-while-triggers-fire-at-fastest

- **Severity:** P2
- **Where:** charter:31 (triggers) vs charter:44 (position after Compound); `internal/tool/registry.go:67-71`; `internal/agent/agent.go:246-253`
- **What:** Two of Scout's three triggers — unresolved contradiction, detected shear — are conditions that surface while interpreting evidence (Orient) or comparing outcome to expectation (Reflect). The gate sits after Compound. So the fastest-arriving signal is queued behind the slowest element in the loop, adding roughly a full cycle of deadtime between detection and search. Worse, the position is tool-infeasible: Compound's gate map is `read, glob, ls, bash, edit(manifest globs), write(manifest globs)` (`registry.go:67-71`) — no `web_search`, no `web_fetch`. A box placed there literally cannot search laterally without a new gate entry, while the phase that *can* (Orient, with the `deep` tier) is where the trigger arose. Compound is also where the session's durable artifact is cut (`agent.go:246-253`), so a post-Compound box writes after the artifact it would want to influence.
- **Evidence:** charter:31, charter:44; `registry.go:53-55` vs `registry.go:67-71`; `builtin.go:20-22`; `agent.go:246-253`.
- **Failure scenario:** Over weeks, cross-domain search fires one cycle late on every contradiction-triggered case; the contradiction is usually resolved or forgotten by then, so scout reports systematically address stale conditions and their probes look uninformative. The measured probe-success rate then argues against S for the wrong reason — bad placement, not bad idea.
- **Suggestion:** In §Required disagreement probes, replace the implied placement with an explicit one: *"Probe: trigger-site placement — for each candidate, state the phase at which the trigger becomes observable and the phase at which the operation runs, and justify any gap in cycles."* Scout should be forced to defend Compound-gating against an Orient-gated variant.

### orthogonality-axiom-is-asserted-then-contradicted-by-a-candidate

- **Severity:** P2
- **Where:** charter:27 ("Agent orchestration is an orthogonal topology over those loops") vs charter:59 (**Share** — "propagate compounded knowledge across agents, projects, or pace layers")
- **What:** The charter states orchestration-orthogonality as an axiom in the same paragraph that anchors the whole review, then seeds a candidate whose entire content is a change to the orchestration topology. Share adds no new loop state and no new authority; it adds an edge *between* loops belonging to different agents. Under the axiom it is out of scope by construction; if it is in scope, the axiom is false and every candidate must additionally be scored on what it does across agents. Skaffen's own architecture takes the axiom seriously — `agentloop` is deliberately phase-agnostic so that multi-agent scenarios need not carry OODARC (`PHILOSOPHY.md:19`), which means cross-agent propagation lives outside the phase system entirely.
- **Evidence:** charter:27; charter:59; `PHILOSOPHY.md:19`; `internal/agentloop/types.go:12-16` (`SelectionHints.Phase` is optional precisely so non-phased consumers exist).
- **Failure scenario:** Share is scored on the same eight criteria as Scout, loses on "semantic distinctness" against Compound, and is eliminated — when the real finding was that it is a different kind of object and the orthogonality axiom is what should have been tested. The team keeps an unexamined axiom and discards the one candidate that would have falsified it.
- **Suggestion:** One sentence added to §Required adversarial review: *"Any candidate that is inherently multi-agent must be scored against the orthogonality claim at charter:27 rather than against O/O/R/C — and if it survives, report the axiom as falsified."*

## Verdict

Read as a controller change rather than a naming exercise, Scout currently has no transition, no ingestion
channel, no decidable trigger, and sits in the one phase whose gate map forbids the search it exists to do —
while its mechanism already ships as an Orient-gated capability with a deliberate deep/instant gain schedule.
The charter's most load-bearing omission is not a missing candidate but a missing gate: nothing in the
tournament asks which edge disappears when the box is deleted, so a capability can win a phase contest.
Add topological necessity as a disqualifier and require triggers as predicates over named loop state, and
the no-S null becomes a fair contestant rather than a formality.
