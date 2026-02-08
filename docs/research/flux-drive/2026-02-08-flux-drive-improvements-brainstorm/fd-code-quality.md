---
agent: fd-code-quality
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Improvement Area 2: Token Optimization"
    title: "Tier 3 model hints in SKILL.md conflict with agent frontmatter model: inherit"
  - id: P1-1
    severity: P1
    section: "Improvement Area 1: Agent Output Validation"
    title: "Step 3.0.5 is misnumbered — placed after Step 3.1 in the implemented SKILL.md"
  - id: P1-2
    severity: P1
    section: "Improvement Area 2: Token Optimization"
    title: "Prompt template is 95 lines, not ~85; brainstorm's ~50-line target would cut the YAML output spec"
  - id: P1-3
    severity: P1
    section: "Improvement Area 2: Token Optimization"
    title: "Token trimming is instruction-only — no enforcement mechanism when agents ignore it"
  - id: P1-4
    severity: P1
    section: "Key Decisions"
    title: "Decision 2 (Codex-first execution) is not a flux-drive design decision — it is a workflow choice"
improvements:
  - id: IMP-1
    title: "Renumber Step 3.0.5 to Step 3.1 and shift current 3.1 to 3.2"
    section: "Improvement Area 1: Agent Output Validation"
  - id: IMP-2
    title: "Add a concrete fallback for when trimming is not performed — measure actual token cost post-launch"
    section: "Improvement Area 2: Token Optimization"
  - id: IMP-3
    title: "Clarify that Tier 3 model hints are orchestrator-level overrides, not agent-file changes"
    section: "Improvement Area 2: Token Optimization"
  - id: IMP-4
    title: "Add domain-specific document slicing detail to the brainstorm — currently one line with no design"
    section: "Improvement Area 2: Token Optimization"
  - id: IMP-5
    title: "Move --fast flag from Open Questions to a concrete design option with trade-offs"
    section: "Open Questions"
verdict: needs-changes
---

### Summary

The brainstorm correctly identifies the six highest-value improvements to flux-drive and the recent commit (3d02843) has already implemented most of them in the SKILL.md. The implemented changes follow project conventions for the most part: kebab-case naming, imperative instructions, YAML frontmatter patterns, and directory structure. However, there is a P0 conflict between the Tier 3 model hints in the SKILL.md roster table (recommending `haiku`/`sonnet`) and the actual agent `.md` files which all declare `model: inherit`. This means the model hints are advisory text that the orchestrator must manually apply at Task launch time, but the brainstorm and the SKILL.md do not make this explicit, creating ambiguity about whether the agent files need updating. There are also several step-ordering and prompt-sizing issues that should be cleaned up before this improvement pass is considered complete.

### Section-by-Section Review

#### Key Decisions

**Decision 1 (Full scope / Approach C):** Sound. The brainstorm references self-review data (29+28 issues) which grounds the scope in real findings rather than speculative improvement.

**Decision 2 (Codex-first execution):** This is a workflow execution decision, not a flux-drive design decision. It has no bearing on what the SKILL.md should contain. Including it in "Key Decisions" is misleading — it implies the flux-drive skill itself has a Codex dependency. The flux-drive SKILL.md never mentions Codex. This decision belongs in a plan document (output of `/clavain:write-plan`), not in the brainstorm's key decisions.

**Decision 3 (No subagent architecture changes):** Correct and consistent with the AGENTS.md convention that agent `.md` files define the system prompt and the SKILL.md orchestrates when/how to launch them.

**Decision 4 (YAML frontmatter is working):** Correct. The structured output approach is consistent with how all Clavain agents already use YAML frontmatter in their own definition files. The validation step (Area 1) is the right complement.

#### Improvement Area 1: Agent Output Validation (Reliability)

The brainstorm describes adding "a validation step in Phase 3 before synthesis." This has been implemented as Step 3.0.5 in the SKILL.md. Two issues:

1. **Step numbering is inconsistent with project conventions.** The SKILL.md uses integer steps elsewhere (1.0, 1.1, 1.2, 1.3, 2.0, 2.1, 3.0, 3.1, 3.2, 3.3, 3.4). Step 3.0.5 breaks this pattern. More critically, it is placed *after* Step 3.1 (Collect Results) in the file, despite its description saying "Before synthesis, validate each agent's output file." Reading the SKILL.md linearly, a practitioner would collect results at 3.1, then validate at 3.0.5, then deduplicate at 3.2. The numbering suggests it should come before 3.1 but its position says otherwise.

2. **Validation and collection overlap.** Step 3.1 already handles the malformed-frontmatter case: "The frontmatter is missing or malformed (fallback to reading Summary + Issues sections)." Step 3.0.5 duplicates this with its own "Malformed" classification. The brainstorm should have specified whether 3.0.5 *replaces* the fallback logic in 3.1 or *supplements* it. Currently both exist, creating ambiguity.

**Recommendation:** Renumber to Step 3.1 (Validate Agent Output), shift current 3.1 to 3.2 (Collect Results), and remove the redundant fallback sentence from what becomes 3.2, since 3.1 now handles classification.

#### Improvement Area 2: Token Optimization (Cost)

This is the most impactful area and the one with the most issues.

**Section trimming (enforced instructions):** The brainstorm says "Actually implement '1-line summary for out-of-domain sections' rule." The implementation in the prompt template adds explicit trimming instructions (lines 277-284 of SKILL.md). However, this is still instruction-based — the orchestrator tells the agent "you MUST trim," but there is no mechanism to verify the agent actually did it. Agents receiving the full document in the prompt may simply process it all. The brainstorm's "domain-specific document slicing" bullet (Area 2, bullet 4) hints at the solution: the orchestrator should do the slicing *before* constructing the prompt. But this is a single line with no design detail. If this is deferred, the brainstorm should say so explicitly. If not deferred, it needs a concrete description of how Step 1.1's section analysis feeds into per-agent prompt construction.

**Haiku model hint:** The SKILL.md roster table now shows `model: haiku` for code-simplicity-reviewer and pattern-recognition-specialist, and `model: sonnet` for the others. However, every agent `.md` file in `agents/review/` declares `model: inherit` in its YAML frontmatter. This creates a P0 naming/convention conflict:

- If the intent is that the SKILL.md's roster table *overrides* the agent file's `model` field at Task launch time, the SKILL.md should say this explicitly (e.g., "pass `model: haiku` as a Task parameter, overriding the agent's default").
- If the intent is to *change* the agent `.md` files from `model: inherit` to `model: haiku`, the brainstorm should say so, and that contradicts Decision 3 ("No subagent architecture changes").
- Currently the SKILL.md says "use the recommended `model` parameter to reduce token costs" but does not clarify *how* to pass this — as a Task tool parameter? By editing the agent file? This is the kind of ambiguity that leads to no actual change at runtime.

**Prompt template compression:** The brainstorm says "Reduce from ~85 lines to ~50 lines." The actual template (lines 257-351) is 95 lines, not ~85. The YAML output spec alone is 20 lines (lines 313-331), the prose output format is 16 lines (lines 333-350), and these two blocks total 36 lines. Compressing the whole template to ~50 lines would require cutting the output specification, which would degrade agent output consistency — the very thing Area 1 is trying to improve. The brainstorm does not address this tension.

**Token budget table:** The brainstorm estimates savings from 197K to 140K tokens (29% reduction), with per-agent document cost dropping from ~12K to ~6K (50% reduction). These numbers are internally inconsistent: if document cost drops 50% for 6 agents, that saves 36K tokens, bringing the total from 197K to 161K, not 140K. Getting to 140K requires an additional 21K of savings that are not accounted for (prompt template compression alone would save ~2-3K at most across 6 agents).

#### Improvement Area 3: Fix Stale Integration Claims

Correctly identified, correctly resolved (remove rather than implement), and already implemented in commit 3d02843. The "Called by" section in SKILL.md now only lists `/clavain:flux-drive`. Clean.

#### Improvement Area 4: qmd Integration

Implemented correctly. Step 1.0 now includes qmd semantic search as point 4. The "See also" footer also references qmd. This follows the existing pattern of other skills referencing MCP tools (e.g., `mcp-cli` skill). No naming or convention issues.

#### Improvement Area 5: Triage Calibration

Scoring examples and thin/adequate/deep thresholds have been added to the SKILL.md (lines 111-131). The examples are concrete and use actual agent names from the roster. The thresholds (<5 lines = thin, 5-30 = adequate, 30+ = deep) are reasonable heuristics.

One gap: the brainstorm mentions "Mine convergence data from past reviews to inform future scoring" but provides no mechanism for this. This is aspirational without a design for where convergence data would be stored or how it would feed back into triage. If deferred, it should be explicitly marked as deferred. If intended, it needs a data storage design (e.g., a JSONL file in `docs/research/flux-drive/`).

#### Improvement Area 6: Phase 4 Validation

The brainstorm lists testing tasks (Oracle availability detection, CLI invocation, splinterpeer auto-chain, winterpeer offer logic). These are test activities, not design decisions. They belong in a plan, not a brainstorm. The implementation in SKILL.md adds:
- Fallback Oracle detection (which + pgrep)
- Timeout wrapper with error handling
- Splinterpeer availability prerequisite check

These follow established patterns from `~/.claude/CLAUDE.md` (Oracle requires `DISPLAY=:99` and `CHROME_PATH`). The `timeout 300 env` pattern is correct.

#### Open Questions

The three open questions are well-formed but should have been resolved before marking the brainstorm "Approved for implementation":

1. `--fast` flag: This would require changes to Step 1.2's selection rules (capping at 3 instead of 8). Not trivial to design without deciding how to select which 3.
2. Thin-section enrichment testing: This is a straightforward deferral decision.
3. Tier 3 default model: Directly relates to the P0 model-hint issue above.

### Issues Found

1. **P0-1: Tier 3 model hints conflict with agent frontmatter** (Section: Improvement Area 2). The SKILL.md roster table specifies `model: haiku` and `model: sonnet` for Tier 3 agents, but every agent `.md` file declares `model: inherit`. Neither the brainstorm nor the SKILL.md clarifies the override mechanism. Without this, the model hints are dead text that produces no runtime effect. This should be resolved before implementation proceeds: either (a) document that the orchestrator passes `model` as a Task parameter, or (b) update the agent `.md` files (which contradicts Decision 3).

2. **P1-1: Step 3.0.5 misnumbered and misplaced** (Section: Improvement Area 1). The step is numbered 3.0.5 but placed after Step 3.1 in the file. This violates the sequential numbering convention used throughout the rest of the SKILL.md and creates confusion about execution order.

3. **P1-2: Prompt template size mismatch** (Section: Improvement Area 2). The brainstorm says "~85 lines," actual is 95 lines. The ~50-line target would require cutting the YAML output specification, which conflicts with the validation goals in Area 1. The brainstorm does not acknowledge this trade-off.

4. **P1-3: Token trimming has no enforcement** (Section: Improvement Area 2). The trimming rules are instructions to the agent, not structural enforcement. Agents may ignore them. The brainstorm's "domain-specific document slicing" bullet hints at orchestrator-side slicing but provides no design.

5. **P1-4: Key Decision 2 is out of scope** (Section: Key Decisions). "Codex-first execution" is a plan-level workflow choice, not a flux-drive design decision. Including it here implies a dependency that does not exist in the SKILL.md.

### Improvements Suggested

1. **IMP-1: Renumber Step 3.0.5 to Step 3.1** and shift subsequent steps. Remove the redundant fallback sentence from the current Step 3.1. This aligns with the SKILL.md's existing convention of integer step numbering and eliminates the logical ordering confusion.

2. **IMP-2: Add token measurement to the plan.** After implementing trimming, run a real flux-drive review and measure actual per-agent token consumption. Compare against the ~6K target. If instruction-based trimming does not achieve the target, escalate to orchestrator-side slicing. The brainstorm should explicitly state this measurement step.

3. **IMP-3: Clarify model override mechanism.** Add a sentence to the Tier 3 roster section explaining that the `model` column is a Task-launch parameter, not a change to the agent `.md` file. Example: "When launching Tier 3 agents, pass the model value from this table as the `model` parameter to the Task tool. This overrides the agent's `model: inherit` default for this review session only."

4. **IMP-4: Design the domain-specific document slicing feature.** The brainstorm's bullet "Phase 1 extracts per-domain section summaries that agents receive instead of full document" is a significant feature that deserves its own subsection. It should specify: (a) what data structure holds the per-domain slices, (b) how section-to-domain mapping works, (c) whether slicing happens in Step 1.1 or between 1.1 and 2.1. If deferred, mark it explicitly as a future iteration.

5. **IMP-5: Resolve open questions before implementation.** The brainstorm is marked "Approved for implementation" but has three open questions. At minimum, the `--fast` flag and Tier 3 model default questions should have answers recorded, since they affect the SKILL.md's selection rules and the model-hint design respectively. The thin-section enrichment question is safe to defer.

### Overall Assessment

The brainstorm is well-grounded in real self-review data and the six improvement areas are correctly prioritized. Most have already been implemented in the SKILL.md with good adherence to Clavain's conventions. However, the model-hint conflict (P0-1) is a genuine design gap that needs resolution before the token optimization goals can be met, and the step-numbering issue (P1-1) should be fixed as a straightforward cleanup. Verdict: **needs-changes** on the model-hint mechanism and step ordering; the rest is solid.
