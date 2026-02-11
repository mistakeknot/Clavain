### Findings Index
- P1 | P1-1 | "Pyramid Mode — Token Budget Estimate" | Summarization cost is unaccounted — orchestrator overhead likely offsets 30-50% of claimed 70% savings
- P1 | P1-2 | "Pyramid Mode — Expansion Request Loop" | Re-launch latency adds a full agent invocation round-trip with no budget in the time estimate
- P1 | P1-3 | "Pyramid Mode — Design" | Redundant code path with diff slicing creates two parallel content-assembly systems to maintain
- P1 | P1-4 | "Shift-Work Boundary — Option A" | Batch=ALL autonomous mode risks context window exhaustion on plans with 20+ tasks
- P2 | P2-1 | "Pyramid Mode — Trigger" | 500-line threshold is arbitrary — no measurement basis for where summarization ROI turns positive
- P2 | P2-2 | "Auto-Inject Learnings — Design" | 15-30s latency claim is plausible but depends on docs/solutions/ size, which varies by orders of magnitude
- P2 | P2-3 | "Auto-Inject Learnings — Design" | Plan file mutation during lfg pipeline creates implicit state coupling between Step 4.5 and Step 5
- P2 | P2-4 | "Shift-Work Boundary — Option A" | Spec completeness check grep patterns are fragile — false positives will trigger autonomous mode on incomplete specs
- IMP | IMP-1 | "Pyramid Mode — Design" | Unify pyramid scan and diff slicing under a single content-assembly abstraction
- IMP | IMP-2 | "Auto-Inject Learnings — Design" | Gate learnings injection on docs/solutions/ file count — skip entirely when directory has fewer than 5 files
- IMP | IMP-3 | "Shift-Work Boundary — Option A" | Add a task-count ceiling for autonomous batch=ALL mode to prevent context window blowouts
- IMP | IMP-4 | "Pyramid Mode — Token Budget Estimate" | Instrument actual token usage per agent before and after pyramid mode to validate savings claims
Verdict: needs-changes

---

### Summary

The three design documents propose meaningful performance improvements to the Clavain flux-drive and lfg workflows: pyramid mode for context reduction, automatic learnings injection, and an interactive-to-autonomous shift boundary. The pyramid mode proposal is the most ambitious and contains the most significant performance claims. Its core promise of 70% context reduction is overstated because it does not account for the orchestrator's summarization cost, expansion re-launch overhead, or interaction with the existing diff slicing system. The auto-inject learnings proposal is low-risk but its latency claims need grounding in actual directory sizes. The shift-work boundary has a context window risk when batch=ALL encounters large plans.

### Issues Found

**P1-1: Summarization cost is unaccounted — orchestrator overhead likely offsets 30-50% of claimed 70% savings**

Severity: P1
Section: Pyramid Mode — Token Budget Estimate (lines 92-96 of pyramid-mode-flux-drive.md)

The token budget estimate claims ~70% context reduction:
```
Current: 1000 lines x 6 agents = 6000 line-equivalents in prompts
Pyramid: ~200 lines overview + ~250 lines domain-specific per agent x 6 = ~1700 line-equivalents
Savings: ~70% context reduction
```

This calculation only measures tokens sent TO agents. It omits the tokens consumed BY the orchestrator to produce the pyramid overview. The orchestrator (the main Claude session running flux-drive) must:

1. Read the full document (1000 lines into its own context).
2. Generate section-level summaries: 2-3 sentences per section for 8 sections = ~40-60 lines of generated summary text. This generation cost is roughly proportional to the input size, since the orchestrator must comprehend each section to summarize it.
3. Map sections to agent domains (trivial cost).
4. Assemble per-agent content (6 assembly operations).

The orchestrator's context usage for step (1) alone is 1000 lines. The generation of summaries in step (2) adds output tokens proportional to document size. For a 1000-line document, this is likely 200-400 output tokens for the summaries themselves plus the full 1000-line input in the orchestrator's context.

Net savings recalculation:
- Without pyramid: orchestrator reads document once (~1000 lines) + 6 agents each get 1000 lines = 7000 line-equivalents total system-wide.
- With pyramid: orchestrator reads document once (~1000 lines) + generates summaries (~200 output tokens) + 6 agents each get ~280 lines = ~2880 line-equivalents total, plus orchestrator generation overhead.
- Actual savings: closer to ~59%, not 70%. And this ignores expansion re-launches (P1-2).

The 70% figure is a per-agent-input metric, not a system-wide metric. The document should state both figures because the orchestrator's summarization work is not free — it consumes context in the main session where context is most scarce (the orchestrator holds the full skill definition, phase files, agent roster, triage tables, and monitoring state).

Confidence: High. The arithmetic follows directly from the proposal's own structure.

**P1-2: Re-launch latency adds a full agent invocation round-trip with no budget in the time estimate**

Severity: P1
Section: Pyramid Mode — Expansion Request Loop (lines 98-104)

The expansion request mechanism says:
```
If Stage 1 agent requests expansion, include it in the Stage 2 prompt
(batch with Stage 2 launch)
```

This means an expansion request from a Stage 1 agent does NOT trigger an immediate re-launch — it piggybacks on Stage 2. This is efficient. However, the document also says in the Changes section (line 75):
```
Add handling for expansion requests in Step 2.2b (post-Stage 1):
if an agent requested expansion, re-launch with expanded content
```

These two statements contradict each other. Line 75 says "re-launch" (new invocation), while lines 101-102 say "batch with Stage 2 launch" (no new invocation). If the intent is a re-launch, the performance cost is significant:

- Current Stage 1 timing: ~3-5 minutes (per launch.md Step 2.3 timeout).
- Adding an expansion re-launch: +3-5 minutes for the re-launched agent.
- If 2 of 3 Stage 1 agents request expansion, that is 2 extra invocations at 1-2 minutes each (haiku-class agents are faster, but these are sonnet-class review agents).

The total wall-clock time for a review could increase from ~8-10 minutes (Stage 1 + Stage 2) to ~13-15 minutes (Stage 1 + expansions + Stage 2). That is a 50-60% latency increase on the review workflow, which directly contradicts the performance optimization goal of pyramid mode.

The document needs to resolve the contradiction and explicitly budget the latency cost of expansion re-launches. If expansions piggyback on Stage 2, the cost is zero extra wall-clock time (good). If they are separate re-launches, the cost needs to be stated.

Confidence: High. The contradiction is in the text; the latency cost of agent invocations is well-established from existing flux-drive behavior.

**P1-3: Redundant code path with diff slicing creates two parallel content-assembly systems**

Severity: P1
Section: Pyramid Mode — Design / Edge Cases (lines 31, 89)

The pyramid mode document acknowledges diff slicing exists:
```
Diff input type: Skip — diff slicing already handles this
```

But the two systems solve the same fundamental problem — "how to give each agent a subset of content relevant to their domain" — with completely different mechanisms:

| Aspect | Diff Slicing | Pyramid Mode |
|--------|-------------|--------------|
| Input type | Diffs | Files/directories |
| Routing | File pattern + keyword matching (config/flux-drive/diff-routing.md) | Section-to-domain mapping using "domain keywords" |
| Content delivery | Priority hunks (full) + context summaries | Pyramid overview + domain-expanded sections |
| Expansion | "Request full hunks" annotation | "Request expansion: [section]" annotation |
| Metadata | `[Diff slicing active: ...]` | `[Pyramid mode: ...]` |

The prompt template in launch.md (lines 163-294) would need to handle three content modes: full content (small docs), pyramid content (large files/dirs), and sliced content (large diffs). The synthesis phase would need to handle convergence counting differently for each mode. The shared-contracts.md would need two separate metadata formats.

This is a maintenance and correctness concern, not just complexity. Each content-assembly path is a surface for bugs where an agent receives the wrong content for its domain. The existing diff slicing is already non-trivial (80% threshold, cross-cutting agent exceptions, overlap resolution). Adding a second system doubles the testing surface.

Performance implication: The orchestrator must hold the logic for both systems in its context during every review. For file inputs, the orchestrator still reads the diff slicing configuration (to understand when NOT to apply it), plus the pyramid scan logic. This adds ~200 lines of instruction to the orchestrator's working context.

Confidence: High. The files are already in the repo and the architectural overlap is structural.

**P1-4: Batch=ALL autonomous mode risks context window exhaustion on plans with 20+ tasks**

Severity: P1
Section: Shift-Work Boundary — Option A (lines 56-60 of shift-work-boundary.md)

The proposal says autonomous mode sets `batch size = ALL`:
```
In autonomous mode:
- executing-plans runs with batch size = ALL (not 3)
- No per-batch approval — report at end
```

The current executing-plans skill (SKILL.md, Step 2B) uses batch-of-3. Each batch execution involves:
1. Reading the plan tasks (context cost: proportional to plan size).
2. Executing each task (reading files, writing code, running commands).
3. Reporting (context cost: proportional to completed work).

With batch-of-3, the report step acts as a natural context pressure release — the user reviews, the session can shed completed-task state, and context accumulates only for 3 tasks worth of diffs and tool outputs.

With batch=ALL, if a plan has 20 tasks (common for medium features in this workflow), the executing agent must hold:
- The full plan in context (already present).
- The accumulated diffs, tool outputs, and verification results for ALL tasks in a single unbroken execution run.
- The TodoWrite state tracking all 20 tasks.

For a 20-task plan, accumulated execution context could easily reach 50,000-100,000 tokens (each task generates file reads, writes, bash outputs, test results). Claude's context window is 200K tokens, and the agent already consumes significant context from the skill instructions, plan content, and project CLAUDE.md/AGENTS.md.

The risk is not theoretical — it directly mirrors the "unbounded in-memory accumulation" anti-pattern. At 20+ tasks, the agent may start losing earlier task context, leading to:
- Subtle regressions where task 15 undoes something task 3 established.
- Repeated work where the agent forgets it already completed a task.
- Silent quality degradation where the agent's reasoning quality drops as context fills.

The document does mention "Still stops on blockers (test failures, missing dependencies)" but stopping on errors is not the same as managing context growth during successful execution.

Confidence: High. Context window limits are a hard physical constraint. The 20-task scenario is common in Clavain workflows (the test-suite-design plan referenced in the repo had 15+ tasks).

**P2-1: 500-line threshold is arbitrary — no measurement basis**

Severity: P2
Section: Pyramid Mode — Trigger (lines 37-39)

The trigger condition is:
```
Trigger: INPUT_TYPE = file|directory AND estimated document size > 500 lines
```

The document provides no justification for why 500 lines is the right threshold. For comparison, diff slicing triggers at 1000 lines. The pyramid mode engages at half that size.

The right threshold depends on two competing costs:
1. **Cost of not summarizing**: Each extra line sent to all N agents costs N line-equivalents. For 6 agents, sending 600 lines costs 3600 line-equivalents vs. summarizing to ~200 overview + 150 domain = ~2100, saving ~1500 line-equivalents.
2. **Cost of summarizing**: The orchestrator must read, comprehend, and generate summaries. For a 500-line document, this overhead may be 300-500 tokens of orchestrator time, plus the risk of information loss.

At 500 lines, the savings are modest (~25% less context per agent compared to no summarization) while the information-loss risk is non-zero. At 1000 lines, the savings are substantial (~55% less). The ROI crossover point is somewhere between these, but the document does not estimate it.

This is P2 rather than P1 because the threshold can be tuned post-implementation without architectural changes. But launching with the wrong threshold means either wasted orchestrator work (threshold too low) or missed savings (threshold too high).

Recommendation: Start at 750 lines (midpoint) or match the diff slicing threshold at 1000 lines for consistency, and instrument to measure actual token savings.

Confidence: Medium. The exact crossover point requires measurement; the concern that 500 is unsupported is definitional.

**P2-2: 15-30s latency claim depends on docs/solutions/ size**

Severity: P2
Section: Auto-Inject Learnings — Risk (line 122 of auto-inject-learnings-lfg.md)

The risk section states:
```
Latency: Adds ~15-30s to the lfg workflow.
```

The learnings-researcher agent (agents/research/learnings-researcher.md) uses a grep-first strategy:
1. Extract keywords from the plan (~1s).
2. Run parallel Grep calls across docs/solutions/ (~2-5s for <100 files).
3. Read frontmatter of matched candidates (~1-3s per file, typically 5-20 files).
4. Score and rank (~1s).
5. Full read of relevant files (~2-5s for 3-5 files).
6. Generate output (~3-5s).

For a typical project with 20-50 documented solutions, 15-30s is plausible. However:

- For a new project with 0-5 solutions: The agent launches, finds nothing, and returns "No prior learnings found" in ~5-10s. The proposal handles this gracefully.
- For a mature project with 200+ solutions: Steps 2-3 could take 30-60s (200 files to grep, potentially 25+ candidates to read frontmatter). The agent's own docs say to re-narrow if >25 candidates, which adds another grep round.
- For a project with no docs/solutions/ directory at all: The agent would need to detect this and exit early. The current agent definition does not handle this case explicitly.

The 15-30s estimate is a reasonable median but the distribution has a long tail. The "non-blocking" mitigation is good — but the document should define what "non-blocking" means operationally. Does the lfg command proceed to Step 5 (execute) while learnings-researcher runs in background? Or does it wait for the agent to finish before starting execution? If it waits, 60s on a large project is noticeable. If it does not wait, the learnings may arrive after execution has already started, reducing their value.

Confidence: Medium. The latency claim is plausible for median cases but the tail behavior is uncharacterized.

**P2-3: Plan file mutation during lfg pipeline creates implicit state coupling**

Severity: P2
Section: Auto-Inject Learnings — Design, Option A (lines 44-46)

The proposal appends a "Relevant Learnings" section to the plan file:
```
Append a "## Relevant Learnings" section to the plan file with:
  - File references to relevant solutions
  - Key gotchas or patterns to follow
  - Applicable past mistakes to avoid
```

The plan file has already been written (Step 3) and reviewed by flux-drive (Step 4) at this point. Mutating it in Step 4.5 means:
1. The plan file that flux-drive reviewed is not the plan file that executing-plans will read.
2. If the user re-runs flux-drive on the plan (e.g., after fixing P1 issues), it will now include the "Relevant Learnings" section, which was not there during the first review.
3. The executing-plans skill reads the plan file and follows its steps. If it encounters the "Relevant Learnings" section, it may attempt to "execute" it as a task.

This is a state-coupling concern, not a performance concern per se. But it has a performance implication: if executing-plans treats the learnings section as tasks to execute, it wastes time and context on non-actionable content.

Mitigation: The proposal should specify that the appended section uses a format that executing-plans will explicitly skip (e.g., a `<!-- advisory-only -->` marker), or inject learnings into the agent's context at invocation time rather than mutating the plan file.

Confidence: High. The plan file is a shared artifact between multiple lfg steps; mutation after review is a known anti-pattern in pipeline design.

**P2-4: Spec completeness check grep patterns are fragile**

Severity: P2
Section: Shift-Work Boundary — Option A (lines 46-53)

The completeness check uses string searches:
```
Check plan file for:
  - Acceptance criteria (search for "done when", "acceptance", "success criteria")
  - Test strategy (search for "test", "verify", "validate")
  - Scope boundary (search for "not in scope", "out of scope", "deferred")
```

The keyword "test" will match almost any plan that mentions testing in any context — including "I'll test this later" or "this is untested." The keyword "validate" will match "validate user input" (a feature description, not a test strategy). The keyword "deferred" will match any mention of deferred work, even if it is not a scope boundary.

The performance concern: false positives on the completeness check will trigger autonomous mode on plans that are actually incomplete. An incomplete spec going through autonomous execution will hit blockers, require the agent to stop (per the proposal's blocker-handling), and then the user must re-engage interactively — wasting the entire autonomous execution time up to the blocker.

For a 20-task plan where the blocker hits at task 5, that is 5 tasks worth of execution time (~5-15 minutes) that must be partially redone or reviewed more carefully.

The pattern matching would benefit from requiring section headers (e.g., `## Acceptance Criteria` or `## Test Strategy`) rather than body-text keywords, which are far more specific signals of intentional spec completeness.

Confidence: Medium. The false-positive rate depends on writing style, which varies. The performance cost of a false-positive autonomous run is measurable.

### Improvements Suggested

**IMP-1: Unify pyramid scan and diff slicing under a single content-assembly abstraction**

Both systems solve the same problem: routing relevant content to domain-specific agents while keeping irrelevant content as compressed summaries. A unified abstraction would:

1. Define a single `ContentSlice` concept: `{overview: string, domain_sections: Record<agent, string[]>, metadata: string}`.
2. Have two producers: `DiffSlicer` (for diff inputs) and `PyramidScanner` (for file/directory inputs).
3. Both produce `ContentSlice` objects that the prompt template consumes uniformly.
4. Synthesis phase handles one convergence model, not two.

This reduces the orchestrator's instruction context by ~150 lines (one content-assembly path instead of two) and halves the testing surface. Trade-off: requires refactoring diff slicing before pyramid mode ships, which increases the initial implementation scope.

**IMP-2: Gate learnings injection on docs/solutions/ file count**

Before launching the learnings-researcher agent, check the directory:
```bash
find docs/solutions/ -name "*.md" | wc -l
```

If the count is 0-4, skip the agent entirely and print "No institutional learnings yet — building knowledge base." This avoids the 5-10s overhead of launching and running an agent that will return nothing, on every lfg run, for all new projects.

The threshold of 5 is chosen because the grep-first strategy needs a minimum corpus to be useful. Below 5 files, the user would benefit more from just reading them directly.

Trade-off: None significant. The check is ~100ms and saves 5-10s per lfg run on sparse projects.

**IMP-3: Add a task-count ceiling for autonomous batch=ALL mode**

Instead of `batch = ALL`, use `batch = min(ALL, 10)`. When a plan has more than 10 tasks, run in batches of 10 with brief status reports between batches but no approval gate (still autonomous — just with periodic context checkpoints).

This caps context accumulation at 10 tasks worth of execution state (~25,000-50,000 tokens) while preserving the autonomous feel. The brief status report between mega-batches also gives the user a natural point to abort if something looks wrong, without requiring per-batch approval.

Trade-off: Adds one brief pause every 10 tasks. For a 20-task plan, this is one pause at the midpoint. The user sees a status report and execution continues automatically within 2-3 seconds.

**IMP-4: Instrument actual token usage per agent before and after pyramid mode**

Before implementing pyramid mode, add token counting to the existing flux-drive workflow:
1. After each agent completes, record the approximate input token count (estimate from line count * ~4 tokens/line for English text, or use the actual token count if available from the API response).
2. Write this to findings.json as a `token_usage` field per agent.
3. After 5-10 reviews, analyze the data to determine the actual savings pyramid mode would provide.

This gives a measured baseline against which pyramid mode's savings can be validated. Without it, the 70% savings claim (or any revised claim) remains speculative.

Trade-off: Adds ~10 lines to the synthesis phase. Token counting is approximate but sufficient for ROI analysis.

### Overall Assessment

The pyramid mode proposal addresses a real performance problem (redundant full-content delivery to all agents) but overstates its savings by ignoring orchestrator costs and expansion overhead, and introduces a maintenance burden by creating a second content-assembly system parallel to diff slicing. The auto-inject learnings proposal is low-risk and well-designed for the common case, but its latency claims need grounding and the plan-file mutation pattern should be reconsidered. The shift-work boundary proposal is the simplest of the three but has a significant context window risk with batch=ALL that needs a ceiling.

The most impactful single change would be unifying pyramid mode and diff slicing into a shared content-assembly abstraction before implementing either enhancement — this prevents the complexity cost from compounding with every future content-routing feature.

<!-- flux-drive:complete -->
