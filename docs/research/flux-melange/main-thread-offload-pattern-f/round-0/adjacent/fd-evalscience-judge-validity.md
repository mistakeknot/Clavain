# fd-evalscience-judge-validity — round 0

## Findings Index
- [P0] gate-measures-wrong-quantity — the ≤50% gate scores output tokens while the doc's own diagnosis puts 85% of cost in context, not output (§The measured problem / §The shape Orchestrator)
- [P1] q-a-answerable-analytically-not-empirically — Q-A treats as an open empirical question something the validator's stated contract already forecloses by construction (§Open questions / §The shape Validator)
- [P1] frozen-criteria-validity-undermined-by-own-evidence — pilot-1's 6/6 gauge-defect rate means the validator's sole yardstick is, by the doc's own data, frequently wrong (§Escalation)
- [P2] no-independent-check-on-executor-self-report — "reports the verify output verbatim" has no cross-check against the validator's own re-run (§The shape Executor/Validator)
- [P2] meter-attribution-rules-unvalidated — the gate and the whole problem statement rest on profile.py's lane-attribution being correct, which is asserted, not shown (§What makes it enforceable, bullet 1)

## Findings

### gate-measures-wrong-quantity
- **Severity**: P0
- **Where**: "The shape" § Orchestrator (line 15: "Target: the orchestrator's own turns generate ≤50% of the goal's output tokens") versus "The measured problem" (line 7: "About 85% of main-thread cost is context (cache read + cache write) re-sent every turn at 220–320K tokens per turn... the main thread generated 51.7M [tokens]")
- **What**: The gate is defined on *output*-token share, but the doc's own cost breakdown says 85% of main-thread cost is *context* (cache read + cache write), not generation. These are different quantities that can move independently: a goal can satisfy the ≤50% output-token gate by having the orchestrator emit fewer tokens per turn while still carrying 220-320K context on every one of those turns — the gate reads green while the cost driver the doc opens by naming is completely untouched.
- **Evidence**: Line 9 itself concludes "the lever is not 'swap the main model' — it is fewer, smaller main-thread turns" — i.e., the doc's own stated remedy is about turn *size* (context), not output-token *share*. The gate that operationalizes this remedy (line 15) measures the wrong half of that sentence.
- **Suggestion**: Add a context-volume or cache-read-share companion metric to the gate, sourced from the same instrument — `interstat/scripts/profile.py` already reports "context per turn" (line 23) — rather than gating on output-token share alone. Until that's added, a pilot's passing gate cannot be read as evidence Pattern F reduced cost; it can only be read as evidence output-token share dropped, a different and only loosely correlated claim.

### q-a-answerable-analytically-not-empirically
- **Severity**: P1
- **Where**: Q-A (line 30: "Does the validator add information, or only cost, when the plan's verify block is already executed by the executor?... the pilots will show whether Opus catches anything the verify block missed") versus "The shape" § Validator (line 17: "Re-runs the verify block itself. Judges ONLY against the frozen criteria in the plan")
- **What**: The validator's stated contract is to re-run the *same* procedure against the *same* criteria the executor already ran. By construction, an identical procedure re-run against identical criteria cannot surface a defect class the procedure was blind to on the first pass — it can only surface cases where the identical run gives a *different* result the second time (re-execution flakiness / non-idempotence), which is a distinct signal from "catching something the verify block missed."
- **Evidence**: The contract as written (line 17) contains no second, independent check beyond re-execution — no additional criteria, no code read, no cross-reference to the plan's intent beyond the frozen block. Q-A's own phrasing ("catches anything the verify block missed") describes a capability the stated contract does not have a mechanism for.
- **Suggestion**: Answer the analytic half of Q-A now, before pilots: as specified, the validator adds independence-of-execution (catches an executor that lied about or mis-ran the block) but not independence-of-criteria (cannot catch a blind spot the criteria share with the executor's own run). If detecting missed defects is the actual goal, the validator needs a check the plan's verify block doesn't already encode — otherwise reframe Q-A as "is re-execution independence worth the cost," which pilot data *can* answer.

### frozen-criteria-validity-undermined-by-own-evidence
- **Severity**: P1
- **Where**: "The shape" § Escalation (line 19: "the orchestrator, which fixes the plan (usual case: the verify block was wrong, per pilot-1's 6/6 gauge defects)") versus § Validator (line 17: "Judges ONLY against the frozen criteria in the plan (never its own taste)")
- **What**: The doc's own cited pilot-1 result is that 6 of 6 gauge defects were caused by a wrong verify block, not by wrong execution. The validator's entire mandate is to judge strictly against that same class of criteria. On the design's own evidence, the yardstick the validator is required to trust is the thing most often broken — yet the validator has no stated channel to distinguish "FAIL because criteria are wrong" from "FAIL because execution is wrong"; both produce the identical PASS/FAIL-with-quoted-criterion artifact.
- **Evidence**: 6/6 is a complete sample in the cited pilot, not a fraction — the doc treats it as strong enough evidence to justify a whole clause ("usual case") in the escalation rule, which makes it strong enough evidence that frozen-criteria judging is, empirically, frequently judging against a broken instrument.
- **Suggestion**: Give the validator (or the two-strikes log) a second output channel distinct from PASS/FAIL: "criteria plausibly defective" vs. "execution plausibly defective," even as a guess. Without it, every escalation reads identically in the log regardless of which failure class it actually was, and no one downstream — including the pilots trying to measure Q-A — can separate the two.

### no-independent-check-on-executor-self-report
- **Severity**: P2
- **Where**: "The shape" § Executor (line 16: "reports the verify output verbatim") and § Validator (line 17: "Re-runs the verify block itself")
- **What**: The executor's report — the artifact that reaches the orchestrator's context and is central to Q-B (line 31) — is taken on the sole integrity claim "verbatim," with no cross-check against what the validator observes when it independently re-runs the same block. If the two diverge, nothing in the design states which is authoritative or how the divergence itself surfaces; divergence isn't PASS, isn't FAIL-with-quoted-criterion, and has no named third bucket.
- **Evidence**: Lines 16-17 describe the report and the re-run as parallel, independently-produced artifacts with no stated reconciliation step between them.
- **Suggestion**: Have the validator diff its own verify-block output against the executor's reported output as a cheap first check before judging against frozen criteria; a mismatch is itself informative (flags a mis-reporting executor or a non-idempotent block) and currently has nowhere to be recorded.

### meter-attribution-rules-unvalidated
- **Severity**: P2
- **Where**: "What makes it enforceable" bullet 1 (line 23: "`interstat/scripts/profile.py` reports main vs subagent by model, context per turn, and the main-thread share of generated tokens... The gate is a number on that report, not a feeling")
- **What**: The entire problem statement (lines 5-9) and the gate (line 15) are read off this one instrument's lane-attribution rules, but nothing in the doc states how those attribution rules are validated — e.g., whether a subagent-of-subagent spawn, or a Codex-lane execution (Q-C, line 32), is attributed to the correct bucket. "Not a feeling" asserts objectivity for the gate's *threshold*, but says nothing about the *instrument's* own accuracy.
- **Evidence**: The doc leans on this instrument for its most load-bearing numbers (85% context cost, 51.7M vs 2.1M token split, line 7) with no cited validation step for the attribution logic itself.
- **Suggestion**: Before pilots run, spot-check profile.py's attribution against a small hand-traced session (main thread vs. nested subagent vs. Codex lane) and note the result alongside the gate definition — an unvalidated instrument is a construct-validity risk one level below the gate formula, and it's cheap to check once.

## Verdict
The most consequential problem is that the gate measures a different quantity than the one the doc's own diagnosis identifies as the cost driver — a P0 because it can let a pilot pass while the underlying problem is untouched. The remaining findings share a pattern: the validator's frozen-criteria contract is well-designed against rater drift but, as specified, structurally cannot distinguish the things this design most needs distinguished (missed-defect vs. flaky re-run, bad-criteria vs. bad-execution, matching vs. diverging self-report) — all fixable with a second output channel rather than a redesign.
