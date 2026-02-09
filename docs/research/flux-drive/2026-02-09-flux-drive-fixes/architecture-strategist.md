---
agent: architecture-strategist
tier: adaptive
issues:
  - id: P1-1
    severity: P1
    section: "Task 3: Reconcile tier naming"
    title: "launch-codex.md TIER field still uses numeric {1|2|3}, creating contract split with launch.md's {domain|project|adaptive|cross-ai}"
  - id: P1-2
    severity: P1
    section: "Task 1 + Task 4: Output contract and error handling"
    title: "Duplicate wait-for-completion logic in Step 2.3 (launch.md) and Step 3.0 (synthesize.md) with subtly different behavior"
  - id: P2-1
    severity: P2
    section: "Task 3: Reconcile tier naming"
    title: "Tier 4 heading in SKILL.md still uses numeric 'Tier 4' while all other tiers migrated to descriptive names"
  - id: P2-2
    severity: P2
    section: "Task 4: Retry/error handling"
    title: "Retry-once strategy is under-specified for Oracle (Bash dispatch) vs Task-dispatched agents"
  - id: P2-3
    severity: P2
    section: "Execution Order"
    title: "Plan claims Tasks 4 and 5 can run after Task 3 independently, but Task 4 modifies launch.md which Task 3 also touches"
improvements:
  - id: IMP-1
    title: "Codex review-agent.md template should echo the output format override preamble from launch.md"
    section: "Task 1: Fix output format contract"
  - id: IMP-2
    title: "Consolidate completion-checking into a single authoritative phase rather than splitting across launch and synthesize"
    section: "Task 4: Retry/error handling"
  - id: IMP-3
    title: "Add cross-ai.md to the list of files needing tier name updates in Task 3"
    section: "Task 3: Reconcile tier naming"
verdict: needs-changes
---

### Summary (3-5 lines)

The plan is well-structured and addresses real contract issues in the flux-drive orchestrator-agent boundary. Most tasks (1, 2, 5) have already been implemented in the current codebase, which validates the plan's approach. However, Task 3 (tier naming) was incompletely applied: `launch-codex.md` line 74 still uses numeric tiers `{1|2|3}` while `launch.md` line 82 now uses `{domain|project|adaptive|cross-ai}`, creating a contract split between the two dispatch paths. Additionally, the plan introduced a responsibility overlap between Step 2.3 (launch.md) and Step 3.0 (synthesize.md) for agent completion checking that should be resolved.

### Issues Found

**P1-1: launch-codex.md TIER field still uses numeric `{1|2|3}` (Task 3)**

The plan's Task 3, Step 4 says: "Replace 'Tier 2 bootstrap' heading and 'Tier 2 agents' references with 'Project Agent bootstrap' and 'Project Agents'." This was done (line 19: "Project Agent bootstrap", line 21: "Project Agents"). However, the plan did not address the `TIER:` field in the task description template at `/root/projects/Clavain/skills/flux-drive/phases/launch-codex.md` line 73-74, which still reads:

```
TIER:
{1|2|3}
```

Meanwhile, `/root/projects/Clavain/skills/flux-drive/phases/launch.md` line 82 was updated to:

```
tier: {domain|project|adaptive|cross-ai}
```

This means agents dispatched via Task tool write `tier: adaptive` in their frontmatter, while agents dispatched via Codex write `tier: 2`. The synthesize phase (Step 3.1) validates the `tier` key exists but does not normalize values, so deduplication logic in Step 3.3 that references "Domain Specialists and Project Agents over Adaptive Reviewers" cannot reliably distinguish tiers from Codex-dispatched agents. The `review-agent.md` template at `/root/projects/Clavain/skills/clodex/templates/review-agent.md` line 22 uses `{{TIER}}` directly, so it will emit whatever the task description provides.

**P1-2: Duplicate completion-checking logic between launch and synthesize (Tasks 1+4)**

Step 2.3 in `/root/projects/Clavain/skills/flux-drive/phases/launch.md` (lines 161-181) checks for missing files after 5 minutes, retries once, and creates stub files on failure. Step 3.0 in `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` (lines 5-12) also waits for all agents, polls every 30 seconds, and after 5 minutes proceeds with what it has, noting missing agents as "no findings."

These two steps have overlapping responsibility but subtly different behavior:
- Step 2.3 retries failed agents and creates `verdict: error` stubs
- Step 3.0 treats missing files as "no findings" (not "error")

If both run sequentially as designed, Step 2.3 should handle all failures before Step 3.0 starts. But the plan does not make this ordering contract explicit -- it is implicit from phase numbering. If an implementer reads the phases independently (which is how flux-drive works: "Read each phase file when you reach it"), they may not realize Step 3.0's 5-minute wait is now redundant because Step 2.3 already covers it. This creates a risk of double-waiting (10 minutes total for a missing agent) or conflicting stub behaviors.

**P2-1: "Tier 4" heading not renamed to "Cross-AI (Oracle)" consistently (Task 3)**

SKILL.md line 200 still reads `### Tier 4 -- Cross-AI (Oracle)`. The plan's Task 3 table says Tier 4 maps to "Cross-AI" and is "Unchanged," but this creates an inconsistency: Tiers 1-3 no longer use numeric labels, yet Tier 4 retains its number. The heading should be `### Cross-AI (Oracle)` for consistency. Similarly, `cross-ai.md` line 7 and `launch-codex.md` line 97 still reference "Tier 4" by number.

**P2-2: Retry logic under-specified for Oracle dispatch (Task 4)**

Step 2.3 in launch.md says "Re-launch the agent with the same prompt (use `run_in_background: false`)." For Task-dispatched agents, this is straightforward. For Oracle, the dispatch is a Bash command with `timeout 480` and environment variables. The retry instruction does not distinguish between these two dispatch mechanisms. Retrying Oracle foreground could block the session for up to 8 minutes. The plan should specify that Oracle retries should also use `run_in_background: true` with a shorter timeout, or simply skip Oracle retry entirely (the error handler in the Oracle bash command already writes a failure message to the output file).

**P2-3: Execution order underestimates Task 3/4 file overlap**

The plan states: "Tasks 4 and 5 touch different parts of launch.md and SKILL.md respectively -- can run after Task 3." But Task 3 Step 3 modifies launch.md (tier references in the prompt template), and Task 4 Step 1 adds Step 2.3 to launch.md (completion verification). While they target different sections of the file, the plan's sequential execution order (Task 3 before Task 4) already handles this correctly. The stated rationale ("can run after Task 3") implies they could be parallelized, which is misleading since both modify launch.md.

### Improvements Suggested

**IMP-1: Align the Codex review-agent.md template with the launch.md output contract**

The Codex dispatch path uses `/root/projects/Clavain/skills/clodex/templates/review-agent.md` which has its own output format section (lines 18-33). This template's "Phase 3: Write Report" section defines the same YAML frontmatter structure as launch.md's prompt template, but without the "CRITICAL: Output Format Override" preamble or the "IGNORE your default output format" instruction. Since Task 1's core insight is that agent system prompts override the output format, the same override language should appear in the Codex template. The plan should add the Codex template to Task 1's file list:
- Add: `skills/clodex/templates/review-agent.md` (add output format override preamble to Phase 2 section)

**IMP-2: Make Step 2.3 the single authority for completion checking, simplify Step 3.0**

Rather than having two competing wait-and-check sequences, Step 3.0 should simply verify that Step 2.3 completed (check that all expected files exist, including error stubs) and proceed immediately. Change Step 3.0 from a polling loop to a validation pass:
```
Step 3.0: All agents completed in Phase 2 (Step 2.3 guarantees one .md per agent).
Validate: ls {OUTPUT_DIR}/ and confirm N files. If count < N, Phase 2 did not complete properly -- abort.
```
This eliminates the 5-minute redundant wait and makes the responsibility boundary between launch and synthesize clean.

**IMP-3: Add cross-ai.md to Task 3 file list**

`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` line 7 references "Tier 4" by number. Task 3's file list covers SKILL.md, synthesize.md, launch.md, and launch-codex.md but not cross-ai.md. Add it to ensure complete tier naming migration.

### Overall Assessment

The plan addresses real architectural issues in the flux-drive orchestrator-agent contract. Tasks 1, 2, and 5 are correctly designed and already implemented. The primary risk is the tier naming inconsistency between the two dispatch paths (Task and Codex), which creates a contract split that will cause subtle issues in synthesis deduplication. The secondary risk is the overlapping completion-checking logic that should be consolidated.
