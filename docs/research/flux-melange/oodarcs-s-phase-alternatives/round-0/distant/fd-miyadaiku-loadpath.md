# fd-miyadaiku-loadpath — round 0

Load-path inventory taken before reading any candidate (from the standing frame, not the charter's prose):

| Load | Member carrying it today | Cut at |
|---|---|---|
| Outward/lateral search | Orient, Decide, Act (web_search, web_fetch) | `internal/tool/builtin.go:19-22` |
| Retrieval of prior-session lessons | Orient (quality_history) | `internal/tool/builtin.go:26-29` |
| Hypothesis + reversible probe lifecycle | Act (init/run_experiment), Act+Reflect (log_experiment) | `internal/tool/builtin.go:33-51` |
| Probe outcome record (hypothesis, decision, delta) | evidence schema | `internal/agent/deps.go:90-96` |
| Promotion of a session into durable signal | Compound | `internal/agent/agent.go:246-253` |
| Phase = capability gate (the frame's actual contract) | tool registry | `internal/tool/registry.go:49-72`, `PHILOSOPHY.md:13` |
| Sequencing | forward-only index over `phaseOrder` | `internal/agent/phase.go:10-52` |

## Findings Index

- [P0] tournament-has-no-load-path-inventory — candidates are scored against phase *names*, not against the members that already carry their load (§Tournament criteria)
- [P1] scout-reentry-has-no-mortise — the `⇢ Observe` arrow targets the one phase the runtime cannot start or route (§Current leading candidate: Scout)
- [P1] phase-vs-sideloop-has-no-mechanical-test — required item 8 asks for a phase/side-loop verdict with no test; in Skaffen a phase is a gate delta (§Required adversarial review)
- [P2] scout-pinned-downstream-of-compound — placed after the phase that writes the session's quality signal, while its triggers fire in Orient (§Current leading candidate: Scout)
- [P2] complexity-cost-has-no-unit — the criterion that decides "earns a new letter" is unquantified; the re-cut count is countable and unstated (§Tournament criteria)

## Findings

### tournament-has-no-load-path-inventory

- **Severity:** P0
- **Where:** charter lines 85-96 (§Tournament criteria, "Semantic distinctness: minimal overlap with O/O/R/C"), and lines 74-83 (per-candidate spec item 5, "What existing phase it overlaps with and why it is not redundant")
- **What:** Overlap is asked for as an assertion the candidate's advocate writes, and it is asked against the six phase *names*. The frame's actual duties are carried by gate entries and registered tools, not by names, so a candidate can be scored "semantically distinct" while every one of its contract fields is already carried by a standing member. Scout is the live example: three of its seven emitted fields have named carriers today. Outward search into related domains is already a capability of Orient/Decide/Act (`internal/tool/builtin.go:19-22`, `webPhases := []Phase{PhaseOrient, PhaseDecide, PhaseAct}`). "Falsifiable prediction" plus "reversible probe" is the existing experiment trio — `init_experiment` and `run_experiment` gated to Act and `log_experiment` gated to Act+Reflect (`internal/tool/builtin.go:33-51`) — and the evidence schema already carries `Hypothesis`, `Decision`, and `Delta` for exactly that lifecycle (`internal/agent/deps.go:90-96`). Because the inventory was never taken, the no-S null's score is computed against the same names, so the null is scored as "absence of a phase" rather than as "these five members already carry the load"; the comparison cannot be repaired by adjusting a score.
- **Evidence:** `internal/tool/builtin.go:19-22`, `:26-29`, `:33-51`; `internal/agent/deps.go:90-96`; charter:80, charter:89.
- **Suggestion:** One added row to the per-candidate spec (charter:74-83): *"For each field of your emitted artifact, name the file:line of the member that carries that load today, or state that none does."* A candidate scores on distinctness only for fields with no named carrier. Applied to Scout, that reduces its distinct surface to `authority: speculative`, the expiration condition, and "where the analogy breaks" — which is a materially different tournament.

### scout-reentry-has-no-mortise

- **Severity:** P1
- **Where:** charter lines 41-47 (topology `Reflect → Compound → Scout ⇢ Observe`) and per-candidate spec item 4 ("Re-entry path into OODARC", charter:79)
- **What:** The tenon is drawn and the mortise does not exist. `phaseFSM` is a forward-only cursor over a fixed slice: `Advance()` increments an index and errors past the end, there is no back-edge, no `Goto`, and `IsTerminal()` is defined as "at Compound" (`internal/agent/phase.go:10-17`, `:39-47`, `:49-52`). A `⇢ Observe` arrow out of the terminal member is not expressible in that member. Worse, the arrow's target is the frame's least-seated member: print mode's phase validation switch accepts only orient, decide, act, reflect, compound and rejects `observe` outright (`cmd/skaffen/main.go:216-221`); the flag's own help text omits it (`:55`); and the `--model` fan-out loop skips it (`:160`). Failure scenario: an implementer takes the charter literally, adds Scout after Compound, and discovers the re-entry has to be a new session — so "re-enter Observe → Orient → …" silently means "next run, if a human starts one", and the conditional side-loop the charter describes becomes a cross-session handoff nobody wired. Two implementers will seat this differently: one as an FSM back-edge, one as an artifact dropped in a directory.
- **Evidence:** `internal/agent/phase.go:10-52`; `cmd/skaffen/main.go:55`, `:160`, `:216-221`, `:514`.
- **Suggestion:** Amend spec item 4 to require the re-entry be written as a concrete transition — source phase, target phase, and what marks it — plus one sentence stating whether the target phase is reachable in the current runtime. Does the charter intend Observe to become startable as part of this work, or does Scout re-enter at Orient (which already holds the web tools)?

### phase-vs-sideloop-has-no-mechanical-test

- **Severity:** P1
- **Where:** charter:83 (item 8, "Whether it is truly a phase, an optional side-loop, a tool/capability, or merely an artifact type") and charter:104-105 (the "Phase vs side-loop" disagreement probe)
- **What:** The most consequential question in the charter is posed with no test, so it will be answered by taste. In this frame the answer is mechanical and cheap to compute: a phase in Skaffen *is* a capability gate — `PHILOSOPHY.md:13` states phases are "hard security boundaries" enforced by the tool registry, and `defaultGates` (`internal/tool/registry.go:49-72`) is where that enforcement lives. So the discriminator is the **gate delta**: a candidate is a load-bearing member only if it requires a tool set that no existing gate grants, or forbids a tool that an existing gate grants. Run on Scout, the delta against Orient is empty — Orient already grants `read/glob/grep/ls` plus `web_search`/`web_fetch` plus `quality_history`. A member that needs no new gate is a shore, not a post: it carries no continuous load and can be pulled without the frame moving.
- **Evidence:** `PHILOSOPHY.md:13`; `internal/tool/registry.go:49-72`; `internal/tool/builtin.go:19-22`, `:26-29`.
- **Suggestion:** Add one line to item 8: *"State the candidate's gate delta — tools it must gain and tools it must lose relative to the nearest existing phase. Empty delta ⇒ side-loop or capability, not a phase."* Two force-path candidates that pass this test where Scout fails it, offered so the shortlist is not all shores: **Reseat** — an operation whose only job is re-cutting a member that has drifted out of true (re-derive phase gates and phase prompts from observed tool-denial and error rates), which needs a gate no phase has today (write access to `defaultGates` and the phase prompt text, currently written by nobody at runtime); and **Shore** — an explicitly temporary member installed with a removal condition and a named load it carries only until a permanent member is cut, whose gate is the union of two phases for a bounded window. Both are traceable to force-path reasoning rather than to renaming a seed.

### scout-pinned-downstream-of-compound

- **Severity:** P2
- **Where:** charter:41-47 (topology) versus charter:31 (Scout's triggers: "validated mechanism, unresolved contradiction, or detected shear")
- **What:** The member is pinned at the wrong end of the beam in two directions. Downstream: Compound is not merely last, it is where the session's durable output is cut — `agent.go:246-253` runs `mutations.Aggregate` and writes the quality signal when the phase is Compound. Anything Scout produces after that point cannot influence the artifact the frame actually carries forward, and the only reader of that artifact is Orient in a *later* session via `quality_history` (`internal/tool/builtin.go:26-29`). Upstream: two of Scout's three stated triggers — unresolved contradiction and detected shear — are conditions that surface while interpreting evidence, i.e. in Orient, which already holds the outward-search tools. The diagram will therefore be read as sequencing guidance the runtime's trigger points cannot honour: readers will expect Scout to fire when a contradiction appears, and the drawing says it fires after promotion.
- **Evidence:** `internal/agent/agent.go:246-253`; `internal/tool/builtin.go:19-22`, `:26-29`; charter:31, charter:44.
- **Suggestion:** Either redraw as a side-loop hanging off Orient (`Orient ⇠ Scout ⇢ Orient`) with Compound as an optional second entry point, or keep the drawing and add one sentence stating that scout output is deliberately next-session-only and does not participate in the current session's compounded artifact. Both are one-line edits; leaving the ambiguity is what costs.

### complexity-cost-has-no-unit

- **Severity:** P2
- **Where:** charter:96 ("Complexity cost: earns a new letter rather than adding taxonomy")
- **What:** The criterion that is supposed to protect the frame from an ornamental seventh member is the only criterion with no unit, so it will lose every argument against the criteria that have vivid ones (generativity, mnemonic). The cost is countable. Adding a seventh phase requires re-cuts at, minimum: `internal/agent/phase.go:10-17` (phaseOrder, plus `IsTerminal` semantics at `:50-52` if the member lands after Compound); `internal/tool/tool.go:48-53` (constants) and `:56-60` (the legacy alias block — five aliases `brainstorm/plan/build/review/ship` still documented as the phase FSM at `AGENTS.md:9`, so a seventh member must gain an alias or deliberately break parity); `internal/tool/registry.go:49-72` (a new `defaultGates` entry — omitting it silently grants zero tools); `internal/router/router.go:21-26` (phase model defaults); `internal/router/shadow.go:26-42` (two shadow maps); `cmd/skaffen/main.go:55` (flag help), `:160` (the `--model` fan-out), `:216-221` and `:514` (phase validation); `internal/session/session.go:85-101` (per-phase prompt guidance). That is ten sites plus the phase-gate matrix tests AGENTS.md:60 requires. The side-loop/capability form costs one site — a `RegisterForPhases(NewScoutTool(), []Phase{PhaseOrient})` line in `internal/tool/builtin.go`. The no-S null costs zero.
- **Evidence:** the ten file:line sites above; `AGENTS.md:60`.
- **Suggestion:** Replace charter:96 with the count itself: *"Complexity cost: number of re-cut sites in the running frame (phase order, constants and aliases, gate matrix, router defaults, shadow maps, CLI validation and flags, phase prompts, gate-matrix tests). Report the count for each shortlisted candidate and for the null side by side: phase ≈ 10+tests, capability = 1, null = 0."* A criterion with a number in it is the only one that can beat generativity in a close call.

## Verdict

The comparison is standing on an uncut sill: no candidate is scored against the members that already carry its load, and in Scout's case three of seven contract fields have named carriers in `builtin.go` today — so the tournament as written cannot distinguish a new member from a duplicate one. Two further joints are one-sided rather than wrong: the `⇢ Observe` re-entry names a target the FSM cannot reach and the CLI refuses to start, and the phase-versus-side-loop question is asked without the gate-delta test that this frame makes trivially available (by which Scout is a shore, not a post). Fix the inventory row, the re-entry transition, the gate-delta test, and the re-cut count, and the same tournament becomes decidable without re-running it.
