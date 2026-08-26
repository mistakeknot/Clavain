# fd-cybernetics-parsimony-adversary — round 0

Seed position 5 (parsimony adversary), bound by the ordering rule at target line 54.

**Ordering compliance, stated first:** positions 1-4 have produced operational contracts in this
same round — Divert / Widen / Sweep (`fd-foraging-exploration-generator.md`), Retire /
Stress-test / Anomaly-capture (`fd-falsification-disconfirmation-contracts.md`), Scout-collect /
Assess (`fd-reconnaissance-provenance-contracts.md`), Transplant / Template
(`fd-transfer-propagation-contracts.md`). Elimination is therefore permitted from this point.
Where a verdict still depends on a contract not yet on the board, I defer explicitly rather than
eliminating.

## Findings Index

- [P0] no-s-null-affirmative-map — the null carries exploration, falsification, simulation, and transfer in named code; its one provable gap is retirement, which nothing carries (§Baseline / lesson 7)
- [P0] decide-is-the-consolidation-candidate — Observe, Orient, and Decide share a byte-identical gate and identical routing; Orient's sole delta is one read-only tool and Decide has no delta at all (§ lesson 8)
- [P1] edge-modifier-absorbs-scout — Scout's whole observable effect is reachable as a gate signature plus one evidence field plus a rate limit, with zero FSM change (§Per-candidate contract field 7)
- [P1] sparse-trigger-starvation-invalidates-pilot — there is no automatic phase trigger in the runtime, so an "optional, sparse" S fires only when a human types `/advance`, and the pilot's null result would be uninterpretable (§Pilot contract)
- [P3] letter-economy-S-is-contested — seven candidate verbs share the letter, so S carries no meaning by itself, unlike each of O/O/D/A/R/C (§Comparative criteria, mnemonic/taste) [t]

## Findings

### no-s-null-affirmative-map

- **Severity:** P0
- **Where:** §Lessons, item 7 (target line 43) and §Pilot contract (lines 142-147)
- **What:** The affirmative specification of the null, per capability, with the code that carries it:
  - **Exploration** — `web_search` and `web_fetch`, registered for Orient/Decide/Act (`internal/tool/builtin.go:19-22`). Present; untriggered and unbudgeted.
  - **Falsification** — Reflect's verify-and-validate sequence (`internal/session/session.go:149-167`) plus `log_experiment`, available in Act and Reflect (`internal/tool/builtin.go:44-50`). Present; scoped to the current diff.
  - **Simulation** — `internal/experiment`: campaign worktrees, benchmark runs, keep/discard with recorded hypothesis and delta (`internal/experiment/gitops.go:87-146`, `internal/experiment/store.go:33-52`). Present and comparatively strong.
  - **Transfer** — `Inspire` injecting prior-session summaries into the Orient prompt (`internal/mutations/inspire.go:21-40`, `internal/session/session.go:80-92`) plus Compound's markdown writes under manifest globs (`internal/tool/registry.go:44-46,67-70`). Present but precondition-free.
  - **Retirement** — **nothing.** All three stores are `O_APPEND` JSONL with no status, TTL, or demotion field (`internal/mutations/store.go:26-52`, `internal/mutations/signal.go:17-46`, `internal/agent/deps.go:61-96`); the only forgetting is the `ReadRecent(n)` recency window (`internal/tool/quality_history.go:44-60`).
  So the honest null statement is: without a new operation, Skaffen loses **nothing it currently has** in exploration, falsification, simulation, or transfer, and continues to have **no way to expire or demote anything it has ever written**.
- **Null's losing condition, symmetric with any candidate:** on the pre-registered corpus, the no-S null loses if (a) it records fewer than N search attempts on hidden-mechanism tasks — i.e. its exploration capability is nominal — or (b) its false-transfer cost on the tempting-analogy bucket exceeds the retirement-equipped arm's, demonstrating that unexpiring material is doing measurable harm.
- **Suggestion:** replace the charter's prose null with this table in the required output, and let the tournament's burden of proof be specific: a candidate must beat the null on the retirement gap or bring evidence that the untriggered exploration capability is the binding constraint.

### decide-is-the-consolidation-candidate

- **Severity:** P0
- **Where:** §Lessons, item 8 (target line 44) and §Required output item 7 (line 167); runtime anchors `internal/tool/registry.go:49-58`, `internal/tool/builtin.go:26-29`, `internal/router/router.go:20-27`, `internal/tui/commands.go:196-215`
- **What:** Turning the knife on the incumbents, precisely rather than generally. `defaultGates` gives Observe, Orient, and Decide the **same four tools**: `read`, `glob`, `grep`, `ls`, all unconstrained (`registry.go:50-58`). `phaseDefaults` routes all six phases to `ModelOpus` (`router.go:20-27`). Transitions between all six are the same human `/advance` keystroke (`tui/commands.go:196-215`). Within that triple:
  - **Orient** has exactly one enforceable delta: `quality_history`, registered for Orient alone (`builtin.go:26-29`), plus prompt-level injection of `Inspire` (`session.go:80-92`). One read-only tool and a prompt block.
  - **Decide** has **no delta of any kind** — not one tool, not one constraint, not one prompt clause, not one routing difference. Its runtime existence is a label on the status bar.
  The tournament is about to apply a runtime-enforcement gate (target line 96) to challengers. Applied symmetrically, Decide fails it outright and Orient passes by a single tool. The recommendation space must therefore include consolidating Decide into Orient (or into Act, where the commitment actually becomes observable).
- **Failure scenario:** the tournament eliminates every S candidate for lacking a capability/routing delta while retaining an incumbent leg that has none, and Skaffen ships a six-letter mnemonic where one letter is enforced by nothing — the exact "ornamental step" the charter's closing line forbids, already present.
- **Suggestion:** add Decide-consolidation as a named entry in the comparison matrix alongside the S candidates. The cheaper mechanism that absorbs Decide's effect: a required decision-statement section in Orient's prompt with the same read-only gate — zero phases, zero FSM change.

### edge-modifier-absorbs-scout

- **Severity:** P1
- **Where:** §Per-candidate contract field 7 (target line 85) and §Comparative criteria (lines 109-116); runtime anchors `internal/tool/registry.go:140-160`, `internal/tool/builtin.go:19-22`, `internal/agent/deps.go:61-96`
- **What:** Delete the box and redraw the loop: what observable behaviour of Scout is unreachable without a letter? Taking seed 3's steelman at its strongest, Scout-collect's entire enforceable content is (i) a tool set of `read` + `web_search` + `web_fetch` with no write/bash, (ii) a bound on how many searches, and (iii) a grade on what it emits. All three are expressible with machinery that exists: `RegisterForPhasesWithConstraint` already supports `AllowedGlobs`, `RateLimit`, and `RequirePrompt` (`registry.go:140-160`), and the missing grade is one field on `agent.Evidence` (`deps.go:61-96`). Nothing here requires `phaseOrder` to grow.
  I concede the one thing an edge modifier cannot supply: a gate signature must attach to *some* phase, and no current phase both permits web tools and forbids writes (Orient/Decide permit web and forbid writes today — `builtin.go:19-22` with `registry.go:53-58` — which is in fact the signature, meaning Scout-collect is *already* Orient's capability set). That strengthens the elimination rather than weakening it.
- **Suggestion:** score Scout as a capability-plus-grade proposal in the matrix, and require anyone arguing for phasehood to name the behaviour that a constrained capability invoked from Orient cannot produce.

### sparse-trigger-starvation-invalidates-pilot

- **Severity:** P1
- **Where:** §Pilot contract (target lines 142-157); runtime anchors `internal/agent/phase.go:39-51`, `internal/tui/commands.go:196-215`
- **What:** Every candidate on the board is described as conditional, sparse, or triggered. The runtime has **no automatic trigger for anything**: `phaseFSM.Advance` is called from exactly one place, the `/advance` slash command (`tui/commands.go:196-215`), and it moves strictly forward, erroring at Compound (`phase.go:39-51`). So in the pilot, the S arm's phase fires only when a human decides to type a command — and in print mode it may never fire at all.
- **Failure scenario:** the pilot runs equal-budget traces, the S arm entered S on a handful of tasks, the aggregate shows no difference, and the tournament concludes S has no value. The actual finding would be that the trigger fired too rarely to test anything — a null result indistinguishable from a real one, on the review's only empirical instrument.
- **Suggestion:** add two lines to the pilot contract: instrument S-entry rate per task, and predeclare a minimum firing rate below which the arm is reported as underpowered rather than as evidence against the candidate. Also predeclare the maximum: an S that fires on most tasks is not the sparse operation being tested.

### letter-economy-S-is-contested

- **Severity:** P3 [t]
- **Where:** §Comparative criteria, mnemonic/taste (target line 114)
- **What:** Each of O, O, D, A, R, C names one operation. **S** currently names seven — Scout, Search, Speculate, Simulate, Synthesize, Stress-test, Share, Select — and the tournament will add more. A letter that requires a glossary to disambiguate carries no mnemonic load; the acronym would gain a slot whose meaning must be looked up, which is the opposite of what a mnemonic is for. If the winner is a capability or side-loop, OODARC stays six letters and the naming problem dissolves entirely.
- **Suggestion:** make the mnemonic criterion conditional rather than comparative — score it only for candidates that survive as phases, and record that a capability-class winner should keep its full verb name and no letter.

## Verdict

The null is stronger than the charter assumes on four of five capabilities and empty on the
fifth: exploration, falsification, simulation, and transfer are all carried by named code, while
retirement is carried by nothing, so retirement is the only gap a new operation can claim
without argument. Turning the same knife on the incumbents, Decide has no enforceable delta of
any kind — same gate, same model, same transition mechanic as Observe and Orient — so
consolidation belongs in the recommendation space beside the S candidates. Scout's enforceable
content is reachable as a constrained capability plus one evidence field, and no candidate can
be fairly tested until the pilot instruments S-entry rate, because the runtime's only phase
trigger is a human keystroke.
