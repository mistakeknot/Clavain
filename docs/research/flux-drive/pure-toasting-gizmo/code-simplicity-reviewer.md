---
agent: code-simplicity-reviewer
tier: 3
issues:
  - id: P1-1
    severity: P1
    section: "Change 3: Create agent-creator template for Tier 2 bootstrap"
    title: "Tier 2 bootstrap agent is premature abstraction — no existing users, no proven need"
  - id: P1-2
    severity: P1
    section: "Change 3: Staleness detection"
    title: "Staleness detection via git diff is over-engineered for a feature that may never trigger"
  - id: P1-3
    severity: P1
    section: "Change 1: Create review dispatch template"
    title: "Two new templates (review-agent.md + create-review-agent.md) when one or zero would suffice"
  - id: P2-1
    severity: P2
    section: "Change 2: Codex dispatch path"
    title: "Template resolution duplicates existing dispatch.sh find patterns — could reuse"
  - id: P2-2
    severity: P2
    section: "Change 2: Codex dispatch path"
    title: "Intermediate temp files (/tmp/flux-codex-*.md) add unnecessary I/O and cleanup concerns"
improvements:
  - id: IMP-1
    title: "Defer Tier 2 bootstrap entirely — implement only when a real project requests it"
    section: "Change 3"
  - id: IMP-2
    title: "If Tier 2 bootstrap is kept, replace git-diff staleness with simple file-age or manual regeneration"
    section: "Change 3"
  - id: IMP-3
    title: "Inline the review-agent template constraints into the prompt template in SKILL.md instead of creating a separate file"
    section: "Change 1"
  - id: IMP-4
    title: "Use dispatch.sh's existing --template flag with the parallel-task template, adding review constraints inline"
    section: "Change 2"
verdict: needs-changes
---

## Summary

The plan adds Codex dispatch to flux-drive when clodex mode is active. The core idea is sound: detect `autopilot.flag`, use `codex exec` via `dispatch.sh` instead of the Task tool. However, roughly half the plan's complexity (the entire Change 3 section plus one of the two new templates) serves a speculative feature -- automated Tier 2 agent bootstrapping -- that has no existing users and no proven need. The staleness detection mechanism layered on top of that bootstrap adds further accidental complexity. The plan could ship with ~40% less surface area by deferring Tier 2 bootstrap and questioning whether the review-agent template needs to be a separate file at all.

## Section-by-Section Review

### Change 1: Create review dispatch template (`review-agent.md`)

The proposed template is 20 lines of markdown with 7 placeholders. Compare it to the existing `parallel-task.md` (20 lines, 5 placeholders). The structural difference is that `review-agent.md` replaces "Success Criteria" (build/test) with review-specific constraints (no code modification, output format). This is a legitimate distinction.

However, the flux-drive SKILL.md already contains a detailed "Prompt template for each agent" section (lines 266-362) that specifies the full prompt structure, YAML frontmatter format, section headings, and constraints. The proposed `review-agent.md` template duplicates a subset of this. The dispatch.sh `--template` flag is designed for implementation tasks where the template structure (Explore -> Implement -> Verify) is reusable. For review tasks, the prompt structure is already defined in SKILL.md and is more detailed than what the template captures.

**Question:** Does `review-agent.md` add value beyond what the SKILL.md prompt template already provides? The SKILL.md prompt template has agent-specific customization (focus area, depth needed, divergence context) that cannot be captured in a static template with simple `{{KEY}}` substitution. Claude will still need to assemble most of the prompt itself. The template would only provide the 5-line "Constraints" footer and the generic "You are a code/document reviewer" preamble -- hardly worth a separate file.

**Verdict:** The template is a nice-to-have, not a necessity. If it is kept, it should be the *only* new template (not one of two).

### Change 2: Codex dispatch path (Step 2.1-codex)

This is the core of the plan and is well-structured. The conditional detection via `autopilot.flag` is simple and reuses the existing clodex detection mechanism. The parallel dispatch via background Bash calls mirrors the existing Task dispatch pattern.

Two minor concerns:

1. **Path resolution duplication.** The plan shows 6 lines of `find` commands to locate `dispatch.sh` and the review template. The clodex SKILL.md already has identical `find` patterns (lines 45-49). Flux-drive could reference the clodex skill's Step 0 pattern or extract this into a shared shell snippet. This is minor but worth noting since copy-paste path resolution is fragile.

2. **Temp file round-trip.** The plan writes each agent's prompt to `/tmp/flux-codex-{agent-name}.md`, then passes it to `dispatch.sh --prompt-file`. This is necessary because `dispatch.sh` requires either a positional argument or `--prompt-file`, and the prompts are too large for command-line arguments. This is acceptable but adds cleanup concerns. The plan does not mention cleanup of `/tmp/flux-codex-*.md` files.

**Verdict:** Sound design. Ship this part.

### Change 3: Tier 2 bootstrap + staleness detection

This is where the plan departs from YAGNI significantly.

**The current state of Tier 2 agents:** Flux-drive SKILL.md (lines 176-182) already handles Tier 2 agents. The instruction is explicit: "If no Tier 2 agents exist, skip this tier entirely. Do NOT create them -- that is a separate workflow." The existing design intentionally defers agent creation.

The plan now proposes:
1. A new template (`create-review-agent.md`) for a Codex agent that creates `fd-*.md` files
2. A blocking dispatch step that runs before review agents launch
3. A sidecar file (`.fd-agents-commit`) to track when agents were created
4. A staleness detection mechanism using `git diff --stat` on CLAUDE.md/AGENTS.md
5. Conditional regeneration logic

This is a significant amount of machinery for a feature that:
- Has zero existing users (no project currently has `fd-*.md` files created this way)
- Runs only when *both* clodex mode is active *and* no Tier 2 agents exist
- Produces agents whose quality is untested (generated agents reviewing generated reviews)
- Adds a blocking synchronous step to what is otherwise a parallel workflow

**The staleness detection is particularly over-engineered.** The plan presents two approaches (file timestamps via `stat` and git diff), then settles on the git diff approach. But the fundamental question is: why detect staleness at all? If the agents are stale, the user can delete them and re-run. Or flux-drive could simply print "Tier 2 agents were created N days ago" and let the user decide. Automated staleness detection with git-diff-based regeneration is solving a problem that has not yet manifested.

**The "creation agent" pattern is premature abstraction.** Instead of one agent that creates other agents (meta-agents), a simpler approach would be to document how users can manually create `fd-*.md` files with a few examples in a skill or runbook. When the pattern proves its value, *then* automate it.

**Verdict:** Defer entirely. The existing "skip Tier 2 if none exist" behavior is the right default. If automated bootstrap is later proven necessary, it can be added as a separate skill (`clavain:bootstrap-reviewers`) rather than embedded in flux-drive's dispatch path.

### Change 4: See Also reference

A one-line addition. Fine as-is.

## Issues Found

### P1-1: Tier 2 bootstrap agent is premature abstraction

**Section:** Change 3 (lines 152-223 of the plan)

The plan proposes a Codex agent that creates other agents (`create-review-agent.md`), a sidecar commit-tracking file, and a conditional bootstrap step -- all for a feature with zero existing users. The current SKILL.md explicitly says "Do NOT create them -- that is a separate workflow." The plan contradicts this established design decision without explaining why the decision should change now.

**Impact:** ~70 lines of plan complexity, one new template, new state management (`.fd-agents-commit`), and a blocking synchronous step added to the dispatch flow.

### P1-2: Staleness detection is over-engineered

**Section:** Change 3, integration subsection (lines 200-223 of the plan)

The plan proposes git-diff-based staleness detection with automatic regeneration. This solves a second-order problem (stale auto-generated agents) for a first-order feature (auto-generated agents) that does not yet exist. Even if Tier 2 bootstrap ships, staleness detection should be deferred until users report that stale agents are a problem.

**Simpler alternative:** If staleness matters, print the age of `fd-*.md` files during triage and let the user decide. One line of output replaces 20+ lines of git-diff shell logic.

### P1-3: Two new templates when one or zero would suffice

**Section:** Changes 1 and 3

The plan creates `review-agent.md` (review dispatch) and `create-review-agent.md` (agent creation). The second template exists solely for the Tier 2 bootstrap feature (defer per P1-1). The first template largely duplicates the prompt structure already defined in SKILL.md lines 266-362. If the review template is kept, it should be the only new file.

### P2-1: Template resolution duplicates existing patterns

**Section:** Change 2 (lines 103-109 of the plan)

The `find` commands to locate `dispatch.sh` and the review template duplicate the pattern already in `clodex/SKILL.md` Step 0 (lines 45-49). This is a maintenance burden -- if the plugin cache structure changes, two skills need updating.

### P2-2: Temp files lack cleanup

**Section:** Change 2 (lines 133-134 of the plan)

The plan writes prompt files to `/tmp/flux-codex-{agent-name}.md` but never mentions cleanup. Over many flux-drive runs, these accumulate. Either clean up after dispatch completes or use a timestamped subdirectory that can be removed atomically.

## Improvements Suggested

### IMP-1: Defer Tier 2 bootstrap entirely (highest impact)

**Current:** Plan adds `create-review-agent.md` template, `.fd-agents-commit` sidecar, staleness detection, and a blocking bootstrap step.

**Proposed:** Remove Change 3 entirely. Keep the existing behavior: "If no Tier 2 agents exist, skip this tier." When automated bootstrap is proven necessary, implement it as a standalone skill (`clavain:bootstrap-reviewers`) that can be invoked independently of flux-drive.

**Impact:** Removes ~70 lines of plan complexity, one template file, all staleness detection logic, and the sidecar file. Reduces the plan from 4 changes to 3 (with Change 4 being trivial).

### IMP-2: If Tier 2 bootstrap is kept, replace staleness with manual trigger

**Current:** Git-diff-based automatic staleness detection with regeneration.

**Proposed:** If a user wants to regenerate Tier 2 agents, they delete the existing `fd-*.md` files and re-run flux-drive. No sidecar file, no git diff, no automatic regeneration. The bootstrap only triggers when agents are absent, not when they are "stale."

**Impact:** Removes ~25 lines of staleness logic. Eliminates the `.fd-agents-commit` sidecar file. Simplifies the bootstrap from "check existence + check staleness + conditional regenerate" to "check existence + conditional create."

### IMP-3: Inline review constraints instead of a separate template file

**Current:** New `review-agent.md` template with 7 placeholders.

**Proposed:** The prompt construction already happens in SKILL.md's Step 2.1. Add a small "Codex dispatch" variant block to the existing prompt template section that adds the review constraints ("Do NOT modify source code", "ONLY create the output file"). This avoids a separate template file while preserving the constraints.

The existing `dispatch.sh` supports bare prompts without `--template`. Use `--prompt-file` with the fully-assembled prompt instead of using template assembly.

**Impact:** One fewer file to maintain. No template-specific placeholder substitution needed. The prompt assembly logic stays in one place (SKILL.md) rather than split between SKILL.md (agent-specific sections) and the template (generic structure).

### IMP-4: Reuse dispatch.sh patterns from clodex SKILL.md

**Current:** Copy-pasted `find` commands in flux-drive to locate dispatch.sh and templates.

**Proposed:** Either: (a) flux-drive references clodex's Step 0 pattern verbatim, making clear it is the canonical source; or (b) extract the path-resolution snippet into a small shell function in `scripts/resolve-paths.sh` that both skills source. Option (a) is simpler; option (b) is only worth it if more skills will need these paths.

**Impact:** Reduces duplication, single point of maintenance for path resolution.

## YAGNI Violations

### 1. Tier 2 Bootstrap Agent (Change 3)

**What it is:** An auto-generation system for project-specific review agents, complete with staleness tracking and regeneration.

**Why it violates YAGNI:** No project currently uses auto-generated Tier 2 agents. The existing manual approach ("skip if none exist") has not been reported as a pain point. The plan builds machinery for a workflow that has not been validated.

**What to do instead:** Ship the Codex dispatch path (Changes 1-2) without Tier 2 bootstrap. If users find themselves wanting project-specific agents, they can create them manually. When a pattern emerges, automate it.

### 2. Staleness Detection (Change 3, subsection)

**What it is:** Git-diff-based detection of whether auto-generated agents are outdated, with automatic regeneration.

**Why it violates YAGNI:** It solves a problem (stale agents) for a feature (auto-generated agents) that does not yet exist. This is two levels of speculation.

**What to do instead:** If bootstrap ships, deletion is the regeneration mechanism. Delete and re-run.

### 3. Second Template File (`create-review-agent.md`)

**What it is:** A specialized template for the bootstrap Codex agent.

**Why it violates YAGNI:** Exists solely to serve the Tier 2 bootstrap feature. If bootstrap is deferred, this file has no purpose.

**What to do instead:** Defer with the rest of Change 3.

## Overall Assessment

The plan has a sound core: detect clodex mode, dispatch review agents via `codex exec` instead of Task, collect results the same way. Changes 1, 2, and 4 accomplish this with reasonable complexity. Change 3 (Tier 2 bootstrap + staleness detection) is where the plan over-engineers, adding speculative automation for a workflow that has no users and no proven need.

**Recommended action:** Ship Changes 1, 2, and 4. Defer Change 3 entirely. Consider whether Change 1 (the review-agent template) is truly needed or whether inline prompt assembly suffices.

**Total potential LOC reduction:** ~40% of the plan's surface area (Change 3 is roughly 90 of ~245 plan lines, plus one template file and all staleness detection logic).

**Complexity score:** Medium (would be Low if Change 3 is deferred)

**Recommended action:** Needs changes -- defer Tier 2 bootstrap, simplify template approach.
