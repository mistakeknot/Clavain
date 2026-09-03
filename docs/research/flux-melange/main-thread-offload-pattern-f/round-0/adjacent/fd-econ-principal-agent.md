# fd-econ-principal-agent — round 0

## Findings Index
- [P1] orchestrator-scored-on-metric-it-alone-authors — the orchestrator's gate rewards thin plans while writing complete plans is also the orchestrator's own job (§The shape / Orchestrator)
- [P1] report-not-repair-has-no-enforcement — the executor's cheapest defection under an ambiguous plan step is silent narrow interpretation, not flagging (§The shape / Executor)
- [P2] validator-independent-of-executor-not-of-plan-author — the validator's frozen-criteria design blocks taste-drift but also removes its only power to catch a thin plan (§The shape / Validator)
- [P2] escalation-decision-is-self-review — the same orchestrator that wrote a defective plan decides whether to patch it or escalate, with no named second party (§Escalation)
- [P2] inherit-escape-hatch-recurs-the-docs-own-diagnosed-gap — `model: inherit` is self-declared with no named auditor, echoing the doc's own "no named integration owner" admission (§What makes it enforceable, bullet 2)

## Findings

### orchestrator-scored-on-metric-it-alone-authors
- **Severity**: P1
- **Where**: "The shape" § Orchestrator (line 15: "writes execution-grade plans (exact paths, complete code, machine-checkable verify blocks... Target: the orchestrator's own turns generate ≤50% of the goal's output tokens")
- **What**: The orchestrator is the sole author of plan quality and is simultaneously the party scored on its own output-token share. Writing a genuinely execution-grade plan — exact paths, complete code, a correct verify block — costs orchestrator-generated tokens right now. Writing a thinner, less-specified plan costs fewer of those tokens immediately, and its cost (extra executor retries, extra validator re-runs, more escalations) lands on a budget the orchestrator's own gate does not count.
- **Evidence**: Nothing in "What makes it enforceable" (lines 21-26) pairs the token-share gate with any measure of plan quality or downstream retry rate — the gate is single-sided. The doc's own escalation clause even names the failure mode this produces as the *usual* case ("the verify block was wrong, per pilot-1's 6/6 gauge defects," line 19) without connecting it back to the metric that incentivizes writing thinner verify blocks in the first place.
- **Suggestion**: Pair the token-share gate with a companion number the orchestrator is also scored on — e.g., executor-retry rate or strike rate per plan authored by that orchestrator turn — so thinning a plan to hit the token target shows up as a cost the same party bears, not one it externalizes onto executors and validators.

### report-not-repair-has-no-enforcement
- **Severity**: P1
- **Where**: "The shape" § Executor (line 16: "Never expands scope; a plan defect is reported, not repaired")
- **What**: This is stated as an instruction with no incentive behind it. Facing an ambiguous plan step, a fresh-context executor has two paths: flag it as a defect (which fails this attempt, and may read as the executor's failure even though the plan caused it) or silently pick the narrowest plausible reading and proceed (keeps the attempt moving, produces a PASS). Nothing rewards the first path over the second.
- **Evidence**: The validator's contract (line 17) re-runs the *same* verify block the executor's narrow interpretation already satisfied, and judges "ONLY against the frozen criteria in the plan" — so a narrowly-reinterpreted-but-passing execution and a correctly-executed one produce the identical PASS artifact. The cheapest concrete defection available to the executor — interpret narrowly, don't flag, still pass — is invisible to every downstream check the design names.
- **Suggestion**: Give the executor a lower-cost path to flag ambiguity than an outright fail — e.g., a "proceeded under interpretation: X" note attached to a PASS report, reviewable without costing a strike — so flagging isn't strictly worse for the executor than silently guessing.

### validator-independent-of-executor-not-of-plan-author
- **Severity**: P2
- **Where**: "The shape" § Validator (line 17: "Judges ONLY against the frozen criteria in the plan (never its own taste)")
- **What**: This rule is well-motivated against validator taste-drift, and correctly makes the validator independent of the *executor*. But it also means the validator has zero power to catch a systematically thin or under-specified plan — it can only ever confirm or deny conformance to whatever the orchestrator wrote. If the orchestrator-scored-on-metric-it-alone-authors incentive above is live, the validator structurally cannot serve as a check on it.
- **Evidence**: The frozen-criteria rule (line 17) names exactly one thing the validator must never do (apply its own taste) and names no channel for it to flag "these criteria look thin" as distinct from "FAIL against these criteria" — the same gap the evaluation-science lens raises from a construct-validity angle; from an incentive angle, it means the plan author faces no independent check at all.
- **Suggestion**: Not a validator redesign — a separate, cheap channel: let the validator optionally note "criteria appear underspecified for this task" alongside its PASS/FAIL, without it counting as a taste-based FAIL. That gives the design a second party's signal on plan quality without compromising frozen-criteria judging.

### escalation-decision-is-self-review
- **Severity**: P2
- **Where**: "The shape" § Escalation (line 19: "returns the item to the orchestrator, which fixes the plan (usual case: the verify block was wrong...) or takes the item frontier-in-the-loop and says so")
- **What**: The party that authored the defective plan is the same party deciding, after two strikes, whether the fix is "patch the plan" (cheap, doesn't require admitting the item needs frontier attention) or "escalate" (an explicit admission, per the doctrine's own two-strikes framing, that this item exceeded the offload shape). No named second party checks whether the orchestrator's "verify block was wrong" diagnosis is accurate rather than a convenient way to avoid escalating.
- **Evidence**: Line 19 names exactly two outcomes and one decision-maker (the orchestrator) for both; no independent party is named to audit which outcome was chosen or why.
- **Suggestion**: At minimum, log the orchestrator's stated reason for choosing "fix the plan" over "escalate" as a durable, reviewable field (ties to the strike-counter storage gap the distributed-systems lens raises) — cheap, and it turns an invisible self-review into an auditable one without adding a new role.

### inherit-escape-hatch-recurs-the-docs-own-diagnosed-gap
- **Severity**: P2
- **Where**: "What makes it enforceable" bullet 2 (line 24: "Deliberate frontier-in-the-loop spawns name `model: inherit` explicitly") versus "The measured problem" (line 7: "The doctrine's Pattern F (execution routing overlay) requires a named integration owner and has none")
- **What**: The `inherit` escape hatch is self-declared by whoever writes the spawn site, with no stated review step confirming that a given `inherit` use is actually a deliberate frontier-in-the-loop call rather than a leftover or lazy default across the "48 command/skill sites, 25 doc-shaped agents" the inheritance closure covers. This is the same "requires an owner and has none" shape the doc names as the very reason Pattern F is needed, recurring one layer down inside Pattern F's own inheritance-closure mechanism.
- **Evidence**: The doc explicitly diagnoses the ungoverned-exception failure mode once already (line 7) and then reintroduces an ungoverned exception of the same shape three bullets later (line 24) without connecting the two.
- **Suggestion**: Name an owner (or a periodic audit — e.g., a routing-drift check already implied by this project's own autosync/interspect tooling) for `inherit` usage specifically, distinct from the doctrine owner named for the pattern overall (line 3) — a recurrence of a named failure mode is a stronger finding than a fresh one, and the doc's own text hands you the diagnosis.

## Verdict
The design's incentive gaps cluster around one structural fact: the orchestrator is principal, plan-author, and self-reviewer at escalation all at once, while the validator's independence (deliberately, and correctly, from the executor) leaves it with no power to check the orchestrator. None of these need new roles — a companion metric, a cheap non-blocking flag channel, and a logged escalation reason would close the gaps that matter most before the token-share gate starts shaping how plans get written.
