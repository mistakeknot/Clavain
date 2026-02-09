---
agent: architecture-strategist
tier: adaptive
issues:
  - id: P0-1
    severity: P0
    section: "Agent Output Contract"
    title: "YAML frontmatter contract relies entirely on runtime prompt override; 16/18 agent system prompts define incompatible native output formats"
  - id: P1-1
    severity: P1
    section: "Dual Dispatch (Task vs Codex)"
    title: "Output contract divergence between Task and Codex dispatch paths -- Codex review-agent template duplicates frontmatter spec with subtle structural differences"
  - id: P1-2
    severity: P1
    section: "Phase Boundaries"
    title: "Phase 2 verification (Step 2.3) and Phase 3 verification (Step 3.0) duplicate the same file-existence check with no shared contract defining completion"
  - id: P1-3
    severity: P1
    section: "Cross-Skill Integration"
    title: "Phase 4 interpeer chaining invokes mine mode inline but the mine mode contract expects structured model perspectives that flux-drive synthesis does not produce"
  - id: P1-4
    severity: P1
    section: "Agent Roster Design"
    title: "Static roster in SKILL.md is a maintenance liability -- 19 agents hardcoded as a markdown table with no single-source-of-truth validation against actual agent files"
  - id: P2-1
    severity: P2
    section: "Error Propagation"
    title: "Codex dispatch has 3-tier fallback (retry Codex -> fallback to Task -> stub) while Task dispatch has 2-tier (retry -> stub), creating asymmetric error handling"
  - id: P2-2
    severity: P2
    section: "Dual Dispatch (Task vs Codex)"
    title: "Codex launch-codex.md uses find-based path resolution with two fallback locations, creating fragile coupling to plugin cache directory structure"
  - id: P2-3
    severity: P2
    section: "Phase Boundaries"
    title: "Token trimming logic is specified in prose within launch.md but has no formal rules -- agents may receive inconsistent document views"
improvements:
  - id: IMP-1
    title: "Extract a shared completion-contract type (e.g., a schema file) defining what constitutes a valid agent output, referenced by both dispatch paths and synthesis"
    section: "Agent Output Contract"
  - id: IMP-2
    title: "Add a roster validation script that compares SKILL.md roster entries against actual files in agents/review/ and agents/workflow/"
    section: "Agent Roster Design"
  - id: IMP-3
    title: "Unify error handling into a shared error-stub specification referenced by both launch.md and launch-codex.md"
    section: "Error Propagation"
  - id: IMP-4
    title: "Define token-trimming as a named strategy (e.g., 'focus-trim') with explicit rules for section retention, rather than inline prose instructions"
    section: "Phase Boundaries"
  - id: IMP-5
    title: "Add frontmatter examples to all 16 agent system prompts that currently lack them, reducing reliance on the runtime prompt override"
    section: "Agent Output Contract"
verdict: needs-changes
---

### Summary (3-5 lines)

The flux-drive system implements a well-structured 4-phase pipeline (Analyze, Launch, Synthesize, Cross-AI) with a dual-dispatch architecture (Task subagents vs Codex CLI). The overall phase separation is sound, but the system's central contract -- YAML frontmatter output from agents -- is architecturally fragile because it relies entirely on a runtime prompt override that competes with 16 different native output formats baked into agent system prompts. The dual-dispatch paths (Task vs Codex) share the same logical intent but diverge in error handling semantics and output template placement. Cross-skill integration with interpeer has a contract mismatch where the mine mode expects structured model perspectives that flux-drive's synthesis does not natively produce.

### Issues Found

**1. P0-1: YAML frontmatter contract relies entirely on runtime prompt override (P0)**

This is the system's most significant architectural vulnerability. The flux-drive pipeline depends on every agent producing YAML frontmatter with specific keys (`agent`, `tier`, `issues`, `improvements`, `verdict`). However:

- 16 of 18 agents define their own incompatible output formats in their system prompts (e.g., `architecture-strategist.md` lines 34-50 specify `### Architecture Assessment` / `### Specific Issues` / `### Summary`)
- The frontmatter requirement is injected only at runtime via the launch prompt template (`phases/launch.md` lines 60-110), which begins with "Your agent definition has a default output format. IGNORE IT"
- This creates a prompt-level conflict: the agent's system prompt says one thing, the task prompt says another. LLM compliance with the override is probabilistic, not guaranteed
- The synthesis phase (`phases/synthesize.md` Step 3.1) acknowledges this by including a "Malformed" classification with prose fallback -- this is a design-time admission that the contract is unreliable
- The existing research file `/root/projects/Clavain/docs/research/research-flux-drive-patterns.md` independently confirms this: "Only 2/18 agents explicitly reference YAML frontmatter in their system prompts"

The architectural concern is that the entire synthesis pipeline's machine-parseability depends on a best-effort prompt override. The fallback path (prose parsing) is fundamentally less reliable and loses the structured deduplication and convergence-counting that frontmatter enables.

**2. P1-1: Output contract divergence between Task and Codex dispatch paths (P1)**

The YAML frontmatter specification exists in three separate locations with no single source of truth:

- `phases/launch.md` lines 72-93 (Task dispatch prompt template)
- `skills/clodex/templates/review-agent.md` lines 19-35 (Codex dispatch template)
- `phases/launch-codex.md` lines 57-78 (Codex task description format)

The Codex template (`review-agent.md`) includes a "Final Report" section (lines 44-47) with `VERDICT: COMPLETE | INCOMPLETE` that is absent from the Task dispatch path. This means Codex-dispatched agents produce additional metadata that Task-dispatched agents do not. The synthesis phase (`phases/synthesize.md`) does not account for this difference -- it only looks for YAML frontmatter, not the Codex-specific final report block.

Additionally, the Codex template has a 3-phase structure (Explore -> Analyze -> Write Report) that differs from the single-shot prompt template used by Task dispatch. This means agents dispatched via Codex follow a different execution flow than those dispatched via Task, even when reviewing the same document.

**3. P1-2: Duplicate completion verification across phase boundaries (P1)**

Phase 2, Step 2.3 ("Verify agent completion") and Phase 3, Step 3.0 ("Verify all agents completed") both perform file-existence checks on `{OUTPUT_DIR}/*.md`. The handoff contract between phases is implicit:

- Phase 2 guarantees "one `.md` file per launched agent -- either findings or an error stub"
- Phase 3 re-verifies this same invariant ("Confirm N files... If count < N, Phase 2 did not complete properly")

There is no shared data structure (e.g., a manifest file listing expected agents and their status) that Phase 2 produces and Phase 3 consumes. Both phases independently count files and compare to expected counts. If an agent name changes between dispatch and verification (e.g., due to a naming inconsistency), both phases would independently fail to detect the mismatch.

**4. P1-3: Contract mismatch in interpeer mine mode chaining (P1)**

Phase 4 (cross-ai.md, Step 4.3) auto-chains to interpeer mine mode when disagreements are found between Oracle and Claude agents. However, the mine mode contract (interpeer SKILL.md lines 306-375) expects:

- "Two or more model perspectives" as structured input
- Each perspective must be classifiable into claims that can be compared

What flux-drive actually produces is:
- A synthesized summary (from Phase 3) that has already deduplicated and merged findings
- Oracle's raw output file (which may or may not follow the YAML frontmatter format)

The synthesis step (Phase 3, Step 3.3) actively destroys the per-agent perspective that mine mode needs -- it deduplicates, groups by section, and merges. By the time Phase 4 runs, the individual agent perspectives that would make mine mode useful are only available by re-reading the individual agent output files, but the Phase 4 instructions do not direct the orchestrator to do this. Step 4.2 only compares "Oracle's findings with the synthesized findings from Step 3.2", not with individual agent outputs.

**5. P1-4: Static roster is a maintenance liability (P1)**

The agent roster in `SKILL.md` (lines 188-209) is a hand-maintained markdown table listing 19 agents with their `subagent_type` values and domains. This table has no validation mechanism:

- Agent files could be added to `agents/review/` without updating the roster (the file `agents/review/product-skeptic.md`, `agents/review/strategic-reviewer.md`, and `agents/review/user-advocate.md` exist and ARE in the roster, but there is no automated check)
- Agent files could be renamed or deleted without updating the roster
- The `subagent_type` values in the roster must exactly match the Claude Code plugin's agent naming convention (`clavain:review:<name>`), but this is validated only at runtime when dispatch fails
- The roster also includes `spec-flow-analyzer` from `agents/workflow/` -- mixing categories increases the chance of a stale entry

The CLAUDE.md quick commands section includes validation (`ls agents/{review,research,workflow}/*.md | wc -l` should be 29), but this validates agent count, not roster-to-file correspondence.

**6. P2-1: Asymmetric error handling between dispatch paths (P2)**

Task dispatch (`phases/launch.md` Step 2.3) has a 2-tier error handling strategy:
1. Retry once (foreground, `run_in_background: false`)
2. Create error stub if retry fails

Codex dispatch (`phases/launch-codex.md` error handling section) has a 3-tier strategy:
1. Retry once with same prompt file
2. Fall back to Task dispatch for that agent
3. Note failure in synthesis summary

The Codex path's Task fallback (tier 2) means a single agent could be dispatched via Codex, fail, then be re-dispatched via Task -- potentially producing output with different characteristics (the Codex template's 3-phase structure vs Task's single-shot prompt). The synthesis phase has no way to know which dispatch path produced a given output file.

**7. P2-2: Fragile path resolution in Codex dispatch (P2)**

`phases/launch-codex.md` resolves critical paths (dispatch.sh, review-agent.md template) using `find` commands with two fallback locations:

```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[[ -z "$DISPATCH" ]] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
```

This creates coupling to:
- The plugin cache directory structure (`~/.claude/plugins/cache/*/clavain/*/`)
- A hardcoded development path (`~/projects/Clavain`)
- The glob pattern `*/clavain/*/scripts/dispatch.sh` which assumes a specific cache layout

If Claude Code changes its plugin cache structure, both `find` calls could fail silently (returning empty), triggering the fallback to Task dispatch with a generic error message. The `head -1` also means that if multiple versions exist in the cache, the resolution is non-deterministic.

Note: The same pattern exists in `skills/clodex/SKILL.md` (lines 45-49), suggesting this is a systemic pattern rather than a one-off issue.

**8. P2-3: Token trimming is underspecified (P2)**

The token trimming instructions in `phases/launch.md` (lines 49-56) are prose-level guidance:

- "Keep FULL content for sections in the agent's focus area"
- "Keep Summary, Goals, Non-Goals in full"
- "For ALL OTHER sections: replace with: `## [Section Name] -- [1-sentence summary]`"
- "Target: ~50% of original document"

This gives the orchestrator (which is also an LLM) significant discretion in what to trim. Two runs of the same review could produce different trimmed documents, meaning agents see inconsistent inputs. The "focus area" determination depends on the triage table's reason column, which is also LLM-generated text. There is no formal mapping from agent domain to document sections.

### Improvements Suggested

**1. IMP-1: Extract a shared output schema**

Create a formal schema file (e.g., `skills/flux-drive/schemas/agent-output.md` or a YAML schema) that defines the required frontmatter structure once. Both `phases/launch.md` and `skills/clodex/templates/review-agent.md` should reference this schema rather than duplicating the specification. The synthesis phase should also reference it for validation. This eliminates the three-copy divergence identified in P1-1.

**2. IMP-2: Add roster validation to quick commands**

Add a validation script (or extend the existing quick commands in CLAUDE.md) that:
- Lists all `.md` files in `agents/review/` and `agents/workflow/`
- Parses the roster table from `skills/flux-drive/SKILL.md`
- Reports agents present in files but missing from roster (and vice versa)
- Validates that `subagent_type` values follow the naming convention

This could be a simple shell script in `scripts/validate-roster.sh` that runs in CI.

**3. IMP-3: Unify error handling specification**

Create a shared error handling specification referenced by both `phases/launch.md` and `phases/launch-codex.md`. The specification should define:
- What constitutes a "failed" agent (exit code, missing file, malformed output)
- The retry strategy (identical for both paths)
- The stub format (already partially unified via the YAML stub in launch.md)
- Whether cross-dispatch fallback (Codex -> Task) is permitted and under what conditions

**4. IMP-4: Formalize token trimming as a named strategy**

Replace the prose-level trimming instructions with a deterministic algorithm:
- Define a priority ordering for section retention (e.g., Summary > agent-focus-sections > Goals/Non-Goals > other)
- Specify a hard token budget (not a percentage target)
- Require the orchestrator to log which sections were trimmed, so synthesis can account for potential blind spots

**5. IMP-5: Add frontmatter awareness to agent system prompts**

For the 16 agents that currently define incompatible native output formats, add a note in their system prompts acknowledging that they may be invoked with a format override:

```markdown
## Output Format

[existing format]

**Note:** When invoked by flux-drive, this format is overridden by the flux-drive output contract (YAML frontmatter + standard prose sections). Follow the task-level format instructions when they differ from the above.
```

This reduces the prompt-level conflict from "IGNORE your format" to "your format may be overridden" -- a softer instruction that LLMs are more likely to follow reliably.

### Overall Assessment

The flux-drive architecture is well-conceived with clear phase separation, intelligent triage, and practical dual-dispatch support. The most significant structural risk is the output contract fragility (P0-1): the entire synthesis pipeline depends on agents producing YAML frontmatter, but this requirement competes with 16 different native output formats and is enforced only via prompt-level override. Addressing this single issue -- by adding frontmatter awareness to agent prompts and extracting a shared schema -- would substantially improve system reliability without requiring architectural restructuring.
