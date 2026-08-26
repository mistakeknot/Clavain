# runtime-enforcement-adjudicator — round 1

## Findings Index
- [P1] scout-gate-signature-is-orients — Claim (2) wins on the code: "read+web, no write/bash" is exactly Orient's realized capability set, and the half of claim (1) that is genuinely distinct ("forbidden to conclude") is inexpressible in GateConstraint (§Baseline:29, §Per-candidate contract field 7:85)
- [P1] search-bound-is-a-budget-namespace-not-a-toolset — The contradiction exposes that Scout's only real enforcement delta is a *budget namespace*: RateLimit is keyed by (Phase, tool) and `ResetRateCounts` is never called outside tests, so no capability-in-Orient candidate can satisfy the "bounded trigger/stop rule" hard gate (§Hard gates:100)

## Findings

### scout-gate-signature-is-orients
- **Severity:** P1
- **Where:** docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:29 (§Baseline, Scout proposal), consumed at :85 (§Per-candidate contract field 7)
- **What:** Claim (1) asserts that a collection half with a "read+web, no write/bash" gate signature is "the only candidate delta not present in any current phase." That empirical premise is false. Claim (2) holds.
- **Evidence:**
  - `internal/tool/registry.go:53-55` — `PhaseOrient: {"read": nil, "glob": nil, "grep": nil, "ls": nil}`. No `write`, no `edit`, no `bash`.
  - `internal/tool/builtin.go:19-22` — `webPhases := []Phase{PhaseOrient, PhaseDecide, PhaseAct}`; both `web_search` and `web_fetch` are registered for those phases.
  - Therefore Orient's *realized* capability set is exactly `read, glob, grep, ls, web_search, web_fetch` (+`quality_history`, builtin.go:28) with no write/edit/bash. "Read+web, no write/bash" is not an unoccupied signature — it is Orient's signature, verbatim.
  - The half of claim (1) that *is* genuinely distinct — a collection operation "forbidden to conclude" — is not expressible by the gate machinery at all. `GateConstraint` (registry.go:15-25) carries only `AllowedGlobs`, `RateLimit`, `RequirePrompt`; `Execute` (registry.go:196-258) enforces only path-glob and call-count. There is no output-shape, content, or "may not assert" constraint anywhere in the registry.
  - So claim (1) splits cleanly the wrong way: its *enforceable* half is Orient, and its *distinct* half is unenforceable. This is not an elegant-vs-reckless taste call; it is a checkable fact and it goes against (1).
  - Caveat against over-crediting (2): its "one evidence field" (an authority grade on the output) is also unvalidated by anything — no registry, session, or store path checks for it. (2) is right that the grade sits outside the gate; it should not be read as saying the grade is *enforced*.
- **Suggestion:** Retire "novel gate signature" as Scout's field-7 answer. Any candidate claiming read+web as its runtime delta must be re-scored as a capability-in-Orient (semantic distinctness only), and the "collection forbidden to conclude" idea must be re-pitched as an output-contract claim with an explicit statement that Skaffen has no mechanism to enforce it today.
- **Remediation (target amendment):** Record in §Baseline that Orient's realized gate signature is already `read, glob, grep, ls, web_search, web_fetch, quality_history` with no write/edit/bash — so no candidate may claim a read+web tool set as a runtime-enforcement delta.

### search-bound-is-a-budget-namespace-not-a-toolset
- **Severity:** P1
- **Where:** docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:100 (§Hard gates, "a bounded trigger/stop rule"), consumed at :85 (field 7) and :71 (the policy-changing candidate)
- **What:** Adjudicating the contradiction exposes a third position neither claim took, and it partly rescues (1)'s *conclusion* by a mechanism (1) never named. Scout's only enforceable delta is not its tool set but its **budget namespace** — and the codebase cannot supply one from inside Orient, nor supply a resetting bound at all.
- **Evidence:**
  - Gates are keyed by `(Phase, toolName)` with exactly one `*GateConstraint` per pair (`registry.go:145-152`, `Constraint` at :186-191). A `RateLimit` placed on `web_search` in `PhaseOrient` therefore bounds Orient's *ordinary* searching too. There is no way to budget Scout-searching separately from Orient-searching without a distinct `Phase` value (`internal/tool/tool.go:48-53`). "Capability in Orient" — a mandated field entrant (§:65) — thus fails the bounded-stop-rule hard gate structurally, not incidentally.
  - Worse, the resetting machinery is dead code in production. `ResetRateCounts` (`registry.go:116-120`) is commented "call on phase transition" but the only call site in the repo is `internal/tool/registry_test.go:484`. `Agent.AdvancePhase` (`internal/agent/agent.go:97-100`) calls only `a.fsm.Advance()`, and `phaseFSM.Advance` (`internal/agent/phase.go:39-47`) only bumps an index. The registry is constructed once per process (`cmd/skaffen/main.go:244`).
  - Consequence: every `RateLimit` is a **per-process-forever** budget, not a per-episode one. Reflect's `edit: {RateLimit: 3}` (registry.go:64) is three edits for the entire session across all loops. A Scout search bound built on this machinery would silently disable Scout for the remainder of a long TUI session after the first N searches — the failure mode is exhaustion, not throttling, which is the opposite of the "bounded trigger/stop rule" the gate asks for.
  - This reframes field 7 for the whole field: the discriminating runtime question is not "which tools?" (Observe/Orient/Decide are near-identical, per settled facts) but "whose budget?" — and answering it requires a new `Phase` key *plus* wiring `ResetRateCounts` into the transition.
- **Suggestion:** Rewrite field 7 of the per-candidate contract to ask for a *budget/counter namespace and its reset boundary*, not a tool-set delta; and record the unwired `ResetRateCounts` as a prerequisite bug for any candidate whose contract includes a search or probe bound.
- **Remediation (target amendment):** Amend §Per-candidate contract field 7 to require a budget-namespace and counter-reset boundary rather than a capability/tool delta, and note in §Hard gates that Skaffen's rate-limit reset is currently unwired so a "bounded stop rule" is not implementable without that fix.

## Verdict
Claim (2) holds and claim (1)'s empirical premise is refuted by `builtin.go:19-22` — Orient already *is* read+web with no write/bash, so Scout's advertised gate signature is not a delta; and the only part of (1) that is genuinely distinct ("forbidden to conclude") is exactly the part `GateConstraint` cannot express. It is not an irreducible taste call. The contradiction's residue is more valuable than either claim: the real enforcement axis is the budget namespace, which no capability-in-Orient candidate can own and which no candidate can bound at all until `ResetRateCounts` is actually called on phase transition.
