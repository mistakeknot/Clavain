---
agent: fd-architecture
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Improvement Area 1 / Phase 3"
    title: "Step 3.0.5 is placed AFTER Step 3.1 in SKILL.md, contradicting its own numbering"
  - id: P1-1
    severity: P1
    section: "Improvement Area 2 — Token Optimization"
    title: "Model hints in roster table are disconnected from agent frontmatter (all agents use model: inherit)"
  - id: P1-2
    severity: P1
    section: "Token Budget Target"
    title: "29% savings claim is arithmetically inconsistent with per-agent 50% reduction"
  - id: P1-3
    severity: P1
    section: "Improvement Area 2 — Token Optimization"
    title: "Prompt template grew to ~92 lines after recent commit, opposite of the compression goal"
  - id: P1-4
    severity: P1
    section: "Improvement Area 3 — Stale Integration Claims"
    title: "Already fixed in commit 3d02843 — brainstorm is stale on this point"
  - id: P2-1
    severity: P2
    section: "Open Questions"
    title: "Open questions lack recommendations, leaving implementers without guidance"
improvements:
  - id: IMP-1
    title: "Renumber Step 3.0.5 to Step 3.1 and shift existing 3.1 to 3.2"
    section: "Improvement Area 1"
  - id: IMP-2
    title: "Add model field to Tier 3 agent frontmatter files, not just the roster table"
    section: "Improvement Area 2"
  - id: IMP-3
    title: "Rework token budget math with bottom-up estimates per optimization"
    section: "Token Budget Target"
  - id: IMP-4
    title: "Add --fast flag as a concrete proposal with agent selection rules"
    section: "Open Questions"
  - id: IMP-5
    title: "Domain-specific document slicing needs a concrete mechanism, not just a bullet point"
    section: "Improvement Area 2"
  - id: IMP-6
    title: "Phase 4 testing plan should specify what 'test' means for a skill with no test harness"
    section: "Improvement Area 6"
verdict: needs-changes
---

### Summary

The brainstorm identifies the right six improvement areas for flux-drive and correctly prioritizes them. However, three of the six areas have already been partially or fully implemented in commit `3d02843` (output validation, token optimization, stale claims fix), making the brainstorm partially stale as a forward-looking document. The remaining gaps are real: the step ordering in the implemented validation is wrong (P0), the model-hint architecture has a disconnect between the roster table and actual agent files (P1), and the token budget math does not hold up under scrutiny (P1). The Open Questions section is thin and needs concrete recommendations before implementation planning.

### Section-by-Section Review

#### What We're Building

Sound framing. The six-area scope is well-bounded and avoids the trap of rewriting the entire skill. The phrase "comprehensive improvement pass" accurately describes what this is: iterative refinement, not a redesign.

#### Why This Approach

The evidence base is strong -- two self-reviews with specific issue counts (29 and 28) provide real data. The 38% duplication figure (75K of 197K tokens going to document duplication) is a compelling justification for token optimization. However, this section does not clarify how those numbers were measured. Were they from actual token counts or estimates? This matters because the Token Budget Target section builds on these numbers.

#### Key Decisions

**Decision 1 (Full scope / Approach C)** -- References "Approach C" without defining Approaches A or B. A reader encountering this brainstorm for the first time has no context for what was rejected. This is a minor documentation gap, not a structural issue.

**Decision 2 (Codex-first execution)** -- Architecturally sound. The writing-plans skill already supports Codex delegation (Step 4 in its execution handoff), so this aligns with existing patterns.

**Decision 3 (No subagent architecture changes)** -- This is the most important architectural constraint and it is correct. The Tier 1-4 agent system is stable and the brainstorm properly scopes changes to the SKILL.md orchestration layer only. The agent markdown files remain untouched.

**Decision 4 (YAML frontmatter is working)** -- Confirmed by the implementation in commit `3d02843`. The validation step was added (Step 3.0.5) with fallback to prose reading, which is the right resilience pattern.

#### Improvement Area 1: Agent Output Validation

This area has been **fully implemented** in commit `3d02843` as Step 3.0.5 in the SKILL.md. The brainstorm's four bullet points (validation step, `---` check, error reporting, fallback behavior) are all present in the current SKILL.md at lines 382-395.

**However, the implementation has a P0 ordering bug**: Step 3.0.5 appears physically after Step 3.1 (Collect Results) in the file, even though its number (3.0.5) implies it should execute before 3.1. An LLM following the file sequentially will read Step 3.1 first, collect results, and only then encounter the validation step -- at which point collection has already happened without validation. The validation's fallback logic also overlaps with Step 3.1's own malformed-frontmatter handling, creating ambiguity about which takes precedence.

#### Improvement Area 2: Token Optimization

This is the highest-value area and the one with the most remaining architectural questions.

**Section trimming** -- Implemented in commit `3d02843`. The prompt template now includes explicit "IMPORTANT -- Token Optimization" instructions (SKILL.md lines 277-284) with a FULL/SUMMARY approach. This is directionally correct but relies entirely on the orchestrating agent (the one running flux-drive) to correctly trim the document before pasting it into each agent's prompt. There is no enforcement mechanism -- if the orchestrator includes the full document, agents receive it without protest.

**Haiku model hint** -- The roster table in SKILL.md now shows `model: haiku` for code-simplicity-reviewer and pattern-recognition-specialist. But every single agent markdown file in `agents/review/` still has `model: inherit` in its frontmatter. The `model` field in the SKILL.md roster table is a *recommendation to the orchestrator* to pass a model parameter when calling Task, but it is not enforced by the agent files themselves. If the orchestrator omits the model parameter, the agent runs at the inherited (opus) model. This is a disconnect that could silently waste the tokens the optimization is supposed to save.

**Compress prompt template** -- The brainstorm targets reducing the prompt from ~85 lines to ~50 lines. After commit `3d02843`, the template is actually ~92 lines (lines 257-349), having grown from the addition of token optimization instructions and FULL/SUMMARY examples. The compression goal has not been achieved; the template grew.

**Domain-specific document slicing** -- The brainstorm says "Phase 1 extracts per-domain section summaries that agents receive instead of full document." This is the most ambitious optimization and has no implementation. It would require the orchestrator to produce N different trimmed versions of the document (one per agent), rather than a single trimmed version. This is feasible but significantly increases Phase 1 complexity. The brainstorm does not specify the mechanism -- should this be N separate Read+summarize passes? A template with slots? The implementation plan needs to flesh this out.

#### Improvement Area 3: Stale Integration Claims

**Already fixed** in commit `3d02843`. The diff shows the removal of:
```
- `writing-plans` skill (after plan completion)
- `brainstorming` skill (after design completion)
```
from the "Called by" section. The brainstorm's decision to "Remove claims for now, add as future enhancement" was executed.

I verified independently that neither `skills/brainstorming/SKILL.md` nor `skills/writing-plans/SKILL.md` contains any reference to flux-drive.

#### Improvement Area 4: qmd Integration

**Implemented** in commit `3d02843`. Step 1.0 now includes item 4: "If qmd MCP tools are available, run a semantic search for project context." The integration is appropriately optional ("if available") and properly scoped as a supplement to CLAUDE.md/AGENTS.md reading.

One concern: the brainstorm says "Helps Tier 1 agents get better project context" but the implementation puts qmd in the orchestrator's Phase 1 analysis, not in the agents themselves. This is actually the better design -- agents should not independently call qmd because that would multiply MCP calls. But the brainstorm's description is misleading about where the integration happens.

#### Improvement Area 5: Triage Calibration

**Partially implemented** in commit `3d02843`. Concrete scoring examples were added (SKILL.md lines 112-131) for two scenarios (Go API plan, Python CLI README) plus thin/adequate/deep thresholds. The brainstorm's first two bullets are done.

The third bullet -- "Mine convergence data from past reviews to inform future scoring" -- has no implementation and is the most architecturally interesting idea. It would require persisting review metadata (which agents were selected, what they found, convergence rates) across sessions. Clavain has no persistent state mechanism for this today. The brainstorm does not address where this data would be stored or how it would be accessed. This is a future enhancement that should be explicitly deferred with a concrete storage proposal.

#### Improvement Area 6: Phase 4 Validation

**Partially implemented** in commit `3d02843`. Oracle availability detection was improved (two-method check at SKILL.md lines 196-199), error handling was added (timeout + fallback at lines 210-214), and splinterpeer availability checking was added (line 524). These address three of the five bullets.

The brainstorm says "Test Oracle CLI invocation" and "Test splinterpeer auto-chain" and "Fix any bugs found." In a project with no test harness (as documented in AGENTS.md under "Known Constraints: No tests"), what does "test" mean here? The brainstorm should specify: is this manual testing by running flux-drive on a document with Oracle available? A checklist of scenarios to try? A subagent that simulates failures? Without this clarification, "test and fix any bugs found" is too vague for implementation planning.

#### Open Questions

The three questions are all legitimate but the brainstorm provides no analysis or recommendations:

1. **`--fast` flag** -- This is worth implementing. A natural design: `--fast` caps at 3 agents, skips Tier 4, skips thin-section enrichment, and uses haiku for all Tier 3. It aligns with the existing `model` hints and agent cap architecture. Recommendation: yes, add it.

2. **Thin-section enrichment testing** -- Step 3.3's enrichment is complex (launches additional Task Explore agents + Context7 MCP calls). Testing it now makes sense because it is the least-exercised path and the most likely to fail silently. Recommendation: test now, defer optimization.

3. **Tier 3 default model** -- The brainstorm already puts `haiku` on code-simplicity-reviewer and pattern-recognition-specialist and `sonnet` on the rest. This is the right split: simple pattern-matching tasks (YAGNI check, anti-pattern detection) work fine with haiku; tasks requiring reasoning about system design need sonnet. The question is already answered by the roster table. Recommendation: keep the existing split.

#### Token Budget Target

The math does not add up:

- The brainstorm claims per-agent document cost drops from ~12K to ~6K tokens (50% reduction per agent).
- With 6 agents, that saves 6 x 6K = 36K tokens.
- Starting from 197K, subtracting 36K gives 161K, not the claimed 140K.
- To reach 140K, you need 57K in savings, which is more than the 36K from document trimming alone.

The missing ~21K would presumably come from haiku model hints (which save tokens on output, not input) and prompt compression (which the brainstorm targets at ~35 lines, roughly 1K tokens per agent = 6K total). Even combining all three: 36K (trimming) + 6K (prompt compression) = 42K. That gets to 155K, still above 140K.

The 29% reduction target is aspirational. A more honest estimate based on the proposed optimizations is ~20-22% (saving ~40-43K tokens), bringing the total to ~154-157K for 6 agents.

### Issues Found

1. **P0-1: Step 3.0.5 ordering bug in SKILL.md** -- Step 3.0.5 (Validate Agent Output) is physically positioned after Step 3.1 (Collect Results) in the file. Since Claude reads the skill linearly, it will execute collection before validation, defeating the validation's purpose. The validation step must come before collection, or the two steps must be merged. This was introduced by the commit that implemented the brainstorm's Area 1.

2. **P1-1: Model hint architecture disconnect** -- The roster table in SKILL.md recommends `model: haiku` for two Tier 3 agents, but all 20 agent markdown files in `agents/review/` specify `model: inherit`. The model parameter in the Task tool call is set by the orchestrator based on the roster table, not the agent file. If the orchestrator ignores the table (or a future refactoring changes the table), the agents silently run at full cost. The model recommendation should be encoded in the agent files themselves, or the SKILL.md should include an explicit instruction like "You MUST pass the model parameter from the roster table when calling Task."

3. **P1-2: Token budget arithmetic is wrong** -- The brainstorm claims 29% savings (197K to 140K = 57K saved) but the proposed optimizations sum to ~42K at best. The implementation plan should use realistic estimates or identify additional savings sources.

4. **P1-3: Prompt template grew instead of shrinking** -- The brainstorm targets reducing the template from ~85 to ~50 lines. After commit `3d02843`, the template is ~92 lines. The recent additions (token optimization block, FULL/SUMMARY example) are valuable but they moved in the wrong direction relative to this goal. Either the compression target should be dropped or a separate pass should restructure the template.

5. **P1-4: Brainstorm is partially stale** -- Areas 1, 3, and 4 are fully implemented. Area 2 and 5 are partially implemented. Only Area 6 is substantially unaddressed. The brainstorm should be updated to reflect current state before being used to generate an implementation plan, or the plan should explicitly mark which items are already done.

6. **P2-1: Open Questions lack analysis** -- All three questions have clear answers derivable from the existing architecture. The brainstorm should provide recommendations, not just pose questions. This is especially important since the "Next Step" is to run `/clavain:write-plan` -- the plan author needs guidance, not open threads.

### Improvements Suggested

1. **IMP-1: Fix step ordering in SKILL.md** -- Renumber Step 3.0.5 to Step 3.1 (Validate Agent Output), shift the current Step 3.1 (Collect Results) to Step 3.2, and update all subsequent step numbers. Alternatively, merge validation into collection since they operate on the same files. The current "3.0.5" naming looks like it was inserted as a patch without renumbering.

2. **IMP-2: Encode model hints in agent frontmatter** -- Change `model: inherit` to `model: haiku` in `agents/review/code-simplicity-reviewer.md` and `agents/review/pattern-recognition-specialist.md`. Then update the SKILL.md to say "Use the model from the agent's frontmatter when launching via Task." This makes the optimization self-documenting and resilient to roster table changes.

3. **IMP-3: Rework token budget with bottom-up estimates** -- Replace the current top-down table with a breakdown:
   - Document trimming: -6K tokens/agent x 6 agents = -36K
   - Prompt compression: -1K tokens/agent x 6 agents = -6K (if achieved)
   - Model hints: reduces output cost but not input tokens (note this distinction)
   - Realistic target: ~155K (21% reduction), not 140K (29%)

4. **IMP-4: Flesh out the --fast flag proposal** -- Define concrete rules: `--fast` means max 3 agents, Tier 1 only (skip Tier 3/4), skip thin-section enrichment (Step 3.3), skip Phase 4 entirely. Add it as a decision, not an open question.

5. **IMP-5: Specify the domain-specific slicing mechanism** -- The most ambitious token optimization (Area 2, bullet 4) needs a concrete design. Proposed: In Phase 1, the orchestrator produces a "section relevance map" (which sections are FULL vs SUMMARY for each agent's domain). Then in Phase 2, the orchestrator uses this map to construct per-agent prompts. This is already partially how the FULL/SUMMARY instructions work -- the improvement is to make it agent-specific rather than generic.

6. **IMP-6: Define Phase 4 testing as a manual test checklist** -- Since Clavain has no automated test harness, Phase 4 "testing" should be a documented checklist of scenarios to run manually:
   - Run flux-drive on a document with Oracle available and Xvfb running
   - Run flux-drive on a document with Oracle unavailable (verify graceful skip)
   - Run flux-drive on a document where Oracle and Claude agents disagree (verify splinterpeer chain)
   - Run flux-drive on a document triggering P0 findings (verify winterpeer offer)
   Each scenario should have expected behavior documented so the tester knows what "pass" looks like.

### Overall Assessment

The brainstorm is directionally correct and well-scoped. Its biggest risk is staleness: half the improvement areas are already implemented, and the implementation plan generator could waste effort re-implementing things or, worse, overwriting the recent improvements. The P0 step-ordering bug in the already-implemented validation needs immediate attention. The token budget math should be corrected before it becomes a target that drives unnecessary scope additions to hit an unrealistic number. Verdict: **needs-changes** before proceeding to `/clavain:write-plan`.
