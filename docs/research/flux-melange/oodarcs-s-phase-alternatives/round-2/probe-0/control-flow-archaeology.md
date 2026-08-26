# control-flow-archaeology — round 2

Probe mode: PROBE-DISAGREEMENT. Adjudicates the contradiction between the
"Scout topology is unimplementable" finding (charter:41-47) and the
"phase-vs-side-loop is mechanically decidable by gate delta" finding (charter:83).

## Findings Index

- [P1] gate-delta-holds-topology-objection-is-moot — (2) wins and dissolves (1): Skaffen's FSM carries no control flow at all, so "phase" reduces to a human-selected gate profile, and Scout's gate set is a strict subset of Orient's — delta ∅ (§Current leading candidate / Required per-candidate spec item 8)
- [P1] incumbent-phases-fail-the-charters-own-matrix — the same discriminator collapses Observe ⊂ Decide ⊂ Orient into a 1-tool nesting with identical model routing, so the tournament's reference arm is never held to the bar it applies to challengers; the honest output may be "merge, don't add" (§Tournament criteria / Decision question)

## Findings

### gate-delta-holds-topology-objection-is-moot

- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md:41-47` (the `Reflect → Compound → Scout ⇢ Observe` diagram) and `:83` (per-candidate spec item 8, "truly a phase, an optional side-loop, a tool/capability, or merely an artifact type").
- **What:** Finding (2) holds. It is not an irreducible taste call, and it is not merely in tension with finding (1) — running (2)'s test dissolves (1). But (2)'s premise needs sharpening: in Skaffen a phase is not "a capability gate," it is *a human-selected named capability profile carrying no control flow whatsoever*. Once that is the definition, the missing backward edge that (1) objects to is a category error rather than a defect, and the gate-delta discriminator returns a verdict against Scout-as-phase.
- **Evidence:**
  - `internal/agent/phase.go:9-51` — `phaseOrder` is a fixed six-element slice; `phaseFSM` is an integer index; `Advance()` does `f.index++` and errors past Compound. There is no `Reset`, no `SetPhase`, no reverse edge. (1) is factually right here.
  - `internal/tui/commands.go:196-213` — the **only** caller of `AdvancePhase()` in the non-test tree is the `/advance` slash command. There is no automatic forward transition either. So the charter's arrow notation at `:44` describes a machine that does not exist in *either* direction; the missing backward edge is not the operative defect, the absent loop is.
  - `internal/agent/agent.go:88` — the default FSM start is `tool.PhaseAct`, not Observe. A session does not begin at the top of the loop.
  - `internal/tool/registry.go:48-70` + `internal/tool/builtin.go:19-22, 25-29` — effective gate sets are `Observe {read,glob,grep,ls}`, `Decide = Observe ∪ {web_search,web_fetch}`, `Orient = Decide ∪ {quality_history}`. Scout's stated capability (`:31`, "searches related, lateral, and orthogonal domains") needs exactly `read/grep/glob + web_search/web_fetch` — **a strict subset of Orient's gate set. Gate delta = ∅.**
  - `internal/router/router.go:19-27` — `phaseDefaults` maps all six phases to `ModelOpus`; the router axis discriminates nothing. `SelectModel` (`:78-84`) falls through to `ModelSonnet` with reason `"fallback-default"` on an unknown phase, so declaring a `PhaseScout` constant without editing `phaseDefaults` would silently *downgrade* the phase the charter calls its most generative.
  - `internal/tool/web_search.go:75-86` — `tierForPhase` is the one place phase does real work beyond gating (`Orient→deep`, `Decide→auto`, `Act→instant`). This is the only non-gate axis available, and the charter specifies nothing on it for any candidate.
- **Why (1) loses:** its objection is contingent on ~10 lines (`phaseOrder` is a slice; a `Reset()` or `newPhaseFSM(PhaseObserve)` restores the cycle). A missing edge in a hand-driven index is not evidence about the conceptual question the charter is actually asking. (2)'s objection survives any amount of code addition: you cannot close a gate delta of ∅ by writing more Go, only by inventing a capability Scout has that Orient lacks — and the charter names none.
- **Suggestion:** Replace the `:44` diagram with the four axes that constitute phase-hood in this runtime and require every candidate to fill them: (a) gate delta vs the nearest incumbent phase, (b) `phaseDefaults` model entry, (c) `PhasedTool` behavior parameterization à la `tierForPhase`, (d) any terminal side-effect hook (cf. `agent.go:247`, Compound's evidence aggregation). A candidate scoring ∅ on all four is a prompt, not a phase.

### incumbent-phases-fail-the-charters-own-matrix

- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-alternatives-charter.md:89-96` (Tournament criteria) and `:14` / `:61` (the no-S null).
- **What:** The contradiction exposed this: once you accept the gate-delta discriminator, you have to point it at the incumbents too, and three of six fail. The charter treats OODARC-as-is as an unexamined reference arm while holding challengers to "semantic distinctness: minimal overlap with O/O/R/C" (`:89`) and "operational crispness: enforceable input/output and state transition" (`:90`). Applied symmetrically, the incumbent baseline does not clear its own bar — which makes every ranking against the null uninterpretable and may invert the charter's whole framing from *addition* to *consolidation*.
- **Evidence:** Observe ⊂ Decide ⊂ Orient is strict set nesting (`internal/tool/registry.go:50-58` + `internal/tool/builtin.go:19-22, 27`). The entire runtime content of "Orient vs Decide" is one tool (`quality_history`, Orient-only) plus one Exa tier string (`deep` vs `auto`, `internal/tool/web_search.go:76-86`). All six phases route to the same model (`internal/router/router.go:20-26`). No phase has an enforceable state transition, because the sole transition mechanism is a human typing `/advance` (`internal/tui/commands.go:196`). So Orient and Decide score near-zero on "semantic distinctness" and zero on "enforceable state transition" — the exact grounds on which an S candidate would be rejected.
- **Suggestion:** Score the six incumbent phases on the same eight criteria and publish that row block *above* the candidate rows. If Orient/Decide land below a proposed S candidate, the recommendation space must include "merge existing phases" and "OODARC is over-specified relative to its runtime" as first-class outcomes, not only "add S / add capability / add nothing."

## Verdict

Finding (2) holds; the contradiction is not a taste call. Skaffen's `phaseFSM` is an
index advanced only by a human slash command, so a phase carries no control flow and
*is* a named capability profile — which makes the gate delta the discriminator, and
Scout's delta against Orient is empty. That verdict dissolves (1) rather than
contradicting it: with no delta there is no phase to route, so the absent backward
edge never becomes load-bearing. The sharper consequence is that the same test, run
symmetrically, indicts Observe/Decide/Orient as a 1-tool nesting under identical model
routing — the charter is judging challengers against a baseline it has never scored.
