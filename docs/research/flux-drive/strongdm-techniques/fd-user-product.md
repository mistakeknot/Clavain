### Findings Index
- P1 | P1-1 | "Shift-Work Boundary" | Autonomous mode removes per-batch checkpoints without user-visible rollback or pause mechanism
- P1 | P1-2 | "Shift-Work Boundary" | Spec completeness checklist uses keyword-grep heuristics that will false-positive on plans that mention criteria without satisfying them
- P1 | P1-3 | "Pyramid Mode" | Expansion request loop creates unpredictable wait times with no user progress signal
- P1 | P1-4 | "All Documents" | No user opt-out or override mechanism for any of the three features once triggered
- P2 | P2-1 | "Auto-Inject Learnings" | "No prior learnings found" message on most projects creates negative-value UX noise
- P2 | P2-2 | "Shift-Work Boundary" | Boundary placement between Step 4 and Step 4.5 creates a confusing fractional step-numbering scheme
- P2 | P2-3 | "Pyramid Mode" | 500-line threshold is arbitrary with no evidence; wrong threshold degrades review quality silently
- P2 | P2-4 | "Auto-Inject Learnings" | Learnings appended to plan file mutate a reviewed artifact after flux-drive has already approved it
- IMP | IMP-1 | "Shift-Work Boundary" | Add an explicit "pause autonomous" escape hatch so users can intervene mid-execution
- IMP | IMP-2 | "Pyramid Mode" | Surface pyramid mode as a user-visible setting rather than a hidden size-based trigger
- IMP | IMP-3 | "Auto-Inject Learnings" | Skip the step entirely when docs/solutions/ is empty rather than running agent and reporting nothing
- IMP | IMP-4 | "All Documents" | Implement these features incrementally with feature flags rather than as permanent lfg modifications
Verdict: needs-changes

### Summary

These three design documents propose StrongDM-inspired enhancements to the Clavain plugin's core `/lfg` workflow and `/flux-drive` review system. The primary user is a developer working inside Claude Code who uses `/lfg` as their end-to-end engineering workflow and `/flux-drive` for multi-agent document review. Their job: ship features safely using an AI-assisted pipeline that brainstorms, plans, reviews, executes, tests, and deploys.

All three proposals address real friction points. Pyramid mode tackles context waste in large reviews. Auto-inject learnings closes a documented-but-broken integration. Shift-work boundary formalizes the interactive-to-autonomous transition that already exists implicitly. However, each proposal has user-facing edge cases that could degrade the workflow experience, and the shift-work proposal in particular represents a significant trust boundary change that needs more guardrails before users will be confident in it.

### Issues Found

#### P1-1: Autonomous mode removes per-batch checkpoints without user-visible rollback or pause mechanism
**Severity: P1** | **Document: Shift-Work Boundary** | **Section: Option A (Step 4a)**

The shift-work proposal changes executing-plans from batch-of-3-with-approval to batch-size-ALL-no-approval. This is the single largest UX change across all three documents. The current batch-of-3 model exists specifically because users need visibility into what the agent is doing — it builds trust incrementally by letting users course-correct early.

The document says autonomous mode "still stops on blockers (test failures, missing dependencies)" but does not address:
- What happens when the agent makes a wrong architectural choice 15 tasks in? The user discovers this only at the end (quality-gates), after significant work that may need to be reverted.
- How does a user pause autonomous execution mid-stream if they realize the plan had an ambiguity they missed?
- What is the recovery path? If quality-gates finds P0 issues after 30 tasks executed autonomously, does the user re-run the entire execution or just the broken parts?

The executing-plans skill (`/root/projects/Clavain/skills/executing-plans/SKILL.md`) explicitly says "Between batches: just report and wait" and "Don't force through blockers — stop and ask." Autonomous mode inverts both of these principles without establishing replacement safety nets.

**Evidence:** executing-plans SKILL.md lines 73-76 (batch report + wait pattern), lines 92-98 (stop and ask pattern). The shift-work doc says "Still stops on blockers" but defines no mechanism for detecting non-blocker-but-wrong-direction situations, which are the majority of real problems.

**Recommendation:** Do not launch autonomous mode without (a) an explicit "pause" escape hatch the user can trigger mid-execution, and (b) incremental git commits per logical unit so that reverting partial work is cheap. The `/work` command (`/root/projects/Clavain/commands/work.md` lines 71-98) already has incremental commit logic — autonomous mode should mandate it, not just allow it.

#### P1-2: Spec completeness checklist uses keyword-grep heuristics that will false-positive
**Severity: P1** | **Document: Shift-Work Boundary** | **Section: Step 4a checklist**

The spec completeness gate checks for keywords like "done when", "acceptance", "test", "verify", "not in scope". This is a string-matching heuristic applied to natural-language plan files. Problems:

1. A plan that says "We should define acceptance criteria later" will match "acceptance" and pass the gate.
2. A plan that uses different terminology ("expected behavior" instead of "acceptance criteria") will fail the gate even though the plan is complete.
3. The checklist has no concept of quality — finding the word "test" in the plan is very different from having a meaningful test strategy.

The document acknowledges this indirectly: "If any are missing, ask the user." But asking "Plan is missing test strategy — add it or proceed?" trains users to always click "proceed anyway", because the false-positive rate will erode trust in the gate. Within a few uses, the gate becomes a speed bump users reflexively dismiss.

**Evidence:** The Step 4a checklist: `(search for "done when", "acceptance", "success criteria")` — these are literal string searches against markdown content, not semantic analysis.

**Recommendation:** Either (a) make the completeness check semantic (the orchestrator reads the plan and evaluates whether criteria are genuinely present, not just mentioned), or (b) drop the automated check and instead present a human-readable checklist that the user confirms manually. Option (b) is simpler and more honest about what the system can actually verify.

#### P1-3: Expansion request loop creates unpredictable wait times with no user progress signal
**Severity: P1** | **Document: Pyramid Mode** | **Section: Expansion Request Loop**

When a Stage 1 agent requests section expansion, the orchestrator must "re-launch with expanded content (like diff slicing re-run)." For Stage 1 agents, expansion is "batched with Stage 2 launch." This means:

1. User approves Stage 1 launch (Step 1.3)
2. Stage 1 agents run (~3-5 minutes)
3. One agent requests expansion
4. Agent is re-launched with expanded content, batched with Stage 2

The user sees "Stage 1 complete" but then has to wait for re-launched agents plus Stage 2. The document provides no mechanism to communicate this to the user. The current flux-drive flow has clear progress markers (Step 2.3 monitoring contract). The expansion loop breaks that contract by adding an indeterminate re-launch cycle between stages.

The "max 1 expansion request per agent per run" limit helps prevent infinite loops but does not solve the progress-visibility problem. If 3 Stage 1 agents each request expansion, the user waits for 3 re-launches plus Stage 2, with no advance warning that this would happen.

**Evidence:** Pyramid Mode doc lines 98-104 (expansion loop rules). Compare with launch.md Step 2.3 (monitoring contract lines 301-338) which has explicit polling, timing, and status messages — none of which account for expansion re-launches.

**Recommendation:** (a) Report expansion requests to the user before re-launching: "fd-architecture requested expanded view of sections X and Y. Re-launching with expanded content." (b) Count expansion re-launches in the monitoring contract. (c) Consider making expansion a user-approved action rather than automatic, at least for Stage 1, since Stage 1 is supposed to be the fast triage pass.

#### P1-4: No user opt-out or override mechanism for any of the three features
**Severity: P1** | **Document: All Documents**

None of the three proposals include a way for users to disable the feature. Pyramid mode triggers automatically at >500 lines. Learnings injection runs automatically in every lfg invocation. Autonomous mode activates based on a spec completeness check. In each case, the behavior changes without the user opting in.

For a workflow tool that users run daily, this is significant. Consider:
- A user who prefers to send full documents to review agents (perhaps because they have found that pyramid summaries miss important context in their domain)
- A user who has no docs/solutions/ and does not want the "No prior learnings found" message cluttering every lfg run
- A user who has a complete spec but still wants batch-of-3 checkpoints because they are working in a high-risk codebase

The clodex toggle (`/root/projects/Clavain/skills/executing-plans/SKILL.md` lines 26-30) already demonstrates the pattern: a flag file at `.claude/clodex-toggle.flag` that the user controls. These features need equivalent toggles or at minimum a way to pass `--no-pyramid`, `--no-learnings`, or `--interactive` to the relevant commands.

**Evidence:** None of the three documents contain the words "opt-out", "disable", "flag", "toggle", or "override".

**Recommendation:** Add a configuration mechanism. The simplest approach: respect environment variables or flag files in `.claude/` (consistent with the existing clodex-toggle pattern).

### Improvements Suggested

#### IMP-1: Add an explicit "pause autonomous" escape hatch
**Document: Shift-Work Boundary**

Autonomous mode should check for a sentinel file (e.g., `.claude/pause-execution`) between task groups. If the file exists, the agent pauses and reports status, just like the current batch checkpoint. This gives users a way to intervene without requiring the agent to anticipate every possible reason to stop.

This is analogous to how CI systems allow manual pipeline pauses. The user creates the file (or a command like `/clavain:pause` creates it), the agent detects it at the next natural boundary, and the user gets the same "Ready for feedback" prompt they get today.

#### IMP-2: Surface pyramid mode as a user-visible setting
**Document: Pyramid Mode**

Rather than silently activating at >500 lines, pyramid mode should be announced and configurable. The document mentions a "Pyramid mode: N sections summarized" annotation, which is good. But the 500-line threshold should be adjustable, and users should be told at the Step 1.3 confirmation prompt that pyramid mode will be used, so they can override if desired.

Suggested UX: At the triage confirmation (Step 1.3), add a line like: "Document is 1200 lines. Pyramid mode will summarize 8 sections and expand 2 per agent. Override: send full content to all agents." This gives users informed consent.

#### IMP-3: Skip learnings step entirely when no knowledge base exists
**Document: Auto-Inject Learnings**

The document says: "If no relevant learnings found: say 'No prior learnings found for this domain' and proceed." But for projects without `docs/solutions/`, this message will appear on literally every `/lfg` run. It provides zero value and adds latency (the learnings-researcher agent still has to launch, scan, find nothing, and report nothing).

Better approach: Before launching the agent, check whether `docs/solutions/` or `config/flux-drive/knowledge/` contain any files. If both are empty, skip the step silently. Only launch the agent when there is a non-empty knowledge base to search.

This is consistent with how flux-drive already handles Oracle availability — it checks for prerequisites before attempting the cross-AI phase.

#### IMP-4: Implement these features with feature flags for incremental rollout
**Document: All Documents**

All three features modify the core `/lfg` workflow. Shipping all three simultaneously increases the surface area for user confusion. A user who last used `/lfg` a week ago would encounter: a new pyramid scanning phase, a new learnings injection step, a new spec completeness gate, and potentially autonomous execution mode — all at once.

Recommendation: Ship each feature behind a flag (even if just a `.claude/<feature>.flag` file), enable them one at a time, and collect user feedback on each before enabling the next. This also makes it easy to disable a feature if it causes problems, without rolling back the other two.

### Overall Assessment

The three proposals address real problems in the Clavain workflow. Pyramid mode tackles context efficiency. Learnings injection closes a documented integration gap. Shift-work boundary formalizes an implicit workflow transition. The designs are well-researched and reference appropriate precedents (StrongDM techniques, existing Clavain patterns like diff slicing and clodex-toggle).

However, the shift-work boundary proposal needs the most work before implementation. Removing per-batch checkpoints is a trust-reducing change that requires compensating mechanisms (pause escape hatch, mandatory incremental commits, clear recovery paths). The keyword-grep spec completeness check will erode user confidence through false positives and should be redesigned as a human-confirmed checklist.

The pyramid mode proposal is the most technically sound but needs better progress communication around expansion requests. The learnings injection proposal is the lowest-risk and closest to shippable, needing only the empty-knowledge-base short-circuit to avoid becoming noise.

Priority ordering for implementation: (1) Auto-inject learnings (lowest risk, closes a real gap), (2) Pyramid mode (clear value, needs monitoring contract updates), (3) Shift-work boundary (highest user impact, needs the most design iteration before it is safe to ship).

<!-- flux-drive:complete -->
