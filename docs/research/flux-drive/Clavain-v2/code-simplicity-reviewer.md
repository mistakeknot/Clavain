---
agent: code-simplicity-reviewer
tier: 3
issues:
  - id: P0-1
    severity: P0
    section: "using-clavain routing table"
    title: "Red Flags table consumes ~16 lines of every-session context for marginal value"
  - id: P1-1
    severity: P1
    section: "engineering-docs skill"
    title: "489-line skill is 3x the recommended size with a 7-step process, decision menu, and Future Enhancements section"
  - id: P1-2
    severity: P1
    section: "writing-skills skill"
    title: "656-line meta-skill is the largest skill in the plugin — contains a full TDD tutorial that should be reference material"
  - id: P1-3
    severity: P1
    section: "learnings command"
    title: "200-line command duplicates engineering-docs skill with 6-subagent orchestration layer on top"
  - id: P1-4
    severity: P1
    section: "review command"
    title: "455-line review command with stakeholder analysis, XML tags, and template repetition"
  - id: P2-1
    severity: P2
    section: "resolve-parallel commands"
    title: "Three resolve-* commands share 80% identical structure"
  - id: P2-2
    severity: P2
    section: "clodex command"
    title: "Alias command is a separate file that could be a one-line redirect"
  - id: P2-3
    severity: P2
    section: "work command"
    title: "Phase 4 duplicates landing-a-change skill content"
improvements:
  - id: IMP-1
    title: "Cut Red Flags table from using-clavain to save ~16 lines of per-session context"
    section: "using-clavain routing table"
  - id: IMP-2
    title: "Collapse engineering-docs to under 200 lines by extracting process details to sub-files"
    section: "engineering-docs skill"
  - id: IMP-3
    title: "Extract TDD tutorial from writing-skills into a reference sub-file"
    section: "writing-skills skill"
  - id: IMP-4
    title: "Make learnings command a thin shim that invokes engineering-docs directly"
    section: "learnings command"
  - id: IMP-5
    title: "Strip review command of stakeholder checklists and template repetition"
    section: "review command"
  - id: IMP-6
    title: "Consolidate three resolve-* commands into one parameterized command"
    section: "resolve-parallel commands"
verdict: needs-changes
---

## Summary

Clavain is a 32-skill, 23-agent, 24-command Claude Code plugin that provides engineering discipline workflows. The recent cleanup removed dead namespaces and consolidated source material, but significant unnecessary complexity remains. The most impactful issue is that the `using-clavain` skill -- injected into every single session via the SessionStart hook -- carries approximately 16 lines of "Red Flags" rationalization table that burns context tokens on every conversation for dubious benefit. Beyond that, several skills and commands are 2-4x their recommended size, and there is meaningful duplication between commands and the skills they route to.

The hook script itself (`session-start.sh`) is clean and well-engineered after the recent cleanup. The `AGENTS.md` development guide is appropriately sized at ~270 lines. The 3-layer routing system is justified by the 32-skill scale. The problems are concentrated in a handful of overweight files and duplicated command/skill patterns.

Estimated total LOC reduction opportunity: 400-500 lines across 6-8 files (roughly 15-20% of total plugin content).

---

## Section-by-Section Review

### 1. `skills/using-clavain/SKILL.md` (137 lines) -- Routing Table

**Core Purpose:** Tell the agent which skills/commands/agents exist and how to find the right one for any task. This is injected into every session via the SessionStart hook, so every token counts.

**What works:**
- The 3-layer routing tables (Stage, Domain, Language) are well-organized and justified by the 32-skill scale.
- The Skill Priority section (lines 97-107) is valuable -- it prevents agents from starting with meta skills when they should start with process skills.
- The Key Commands Quick Reference table (lines 121-137) is useful.
- The `<EXTREMELY-IMPORTANT>` wrapper and rule statement are necessary for compliance.

**What does not work:**

The Red Flags table (lines 79-94) is 16 lines of rationalization prevention that gets loaded into every single session. This is a recurring context tax. Each of those 11 rows says essentially the same thing: "if you are thinking of skipping a skill, do not skip the skill." This is addressed more concisely by the single sentence on line 27: "Invoke relevant skills BEFORE any response or action. Even a 1% chance a skill might apply means you should invoke it."

The `<EXTREMELY-IMPORTANT>` block at lines 6-12 restates the same instruction three times in three different ways ("you ABSOLUTELY MUST", "YOU DO NOT HAVE A CHOICE", "This is not negotiable"). One firm statement would suffice. The current version is 7 lines; it could be 2.

Lines 109-115 (Skill Types: Rigid vs Flexible) are only 6 lines but add no actionable information. "The skill itself tells you which" means this section is self-defeating -- it says "look at the skill to know" which is what the agent would do anyway.

**Recommendation:** Cut the Red Flags table entirely. Compress the EXTREMELY-IMPORTANT block. Cut the Skill Types section. Saves approximately 25 lines of per-session context.

### 2. `skills/engineering-docs/SKILL.md` (489 lines)

**Core Purpose:** Document a solved problem as a structured markdown file with YAML frontmatter.

This skill is 489 lines -- more than 3x the recommended 150-word limit for frequently-loaded skills, and 2.5x the 200-line target for normal skills. The AGENTS.md itself says skills should be "1,500-2,000 words" and this skill is well over that.

**Specific problems:**

- **7-step process with sub-steps is over-engineered.** The actual task is: gather context, classify the problem, write a markdown file using a template, optionally cross-reference. This does not need 7 formal steps with blocking gates.
- **Decision Menu (lines 240-320):** A 7-option post-documentation menu with detailed handling for each option. Options 4 and 5 ("Add to existing skill" and "Create new skill") are speculative -- they describe full workflows for actions that are rarely if ever triggered from this context. YAGNI.
- **Future Enhancements section (lines 479-489):** Lists 6 features explicitly marked "Not in scope." This is the textbook YAGNI violation -- documenting features you have decided not to build.
- **Duplicate section headers:** Lines 326 ("## Decision Gate: Post-Documentation") and 328 ("## Decision Menu After Capture") describe the same thing. Lines 345-346 have "## Success Criteria" repeated twice.
- **Error Handling section (lines 360-383):** 4 error cases with detailed recovery flows for a documentation skill. The actual error cases (missing context, YAML invalid) are already covered by the blocking gates in Steps 2 and 5.
- **Quality Guidelines (lines 401-423):** 14 bullet points of good/avoid documentation advice. This is a style guide, not operational instructions.

**Recommendation:** Cut to under 200 lines. Move the YAML schema reference, decision menu details, and quality guidelines into sub-files in the `references/` directory. The SKILL.md body should be: overview, 3-4 step process, link to template, done.

### 3. `skills/writing-skills/SKILL.md` (656 lines)

**Core Purpose:** Guide the creation of new Clavain skills.

At 656 lines, this is the single largest skill file in the entire plugin. It contains:

- A full TDD tutorial mapped to skill creation (lines 30-44, 533-558)
- Claude Search Optimization (CSO) guide with 5 subsections (lines 140-290)
- Flowchart usage guide (lines 291-316)
- Code example guidelines (lines 326-345)
- File organization guide with 3 example layouts (lines 347-370)
- Anti-patterns section (lines 562-580)
- Rationalization prevention tables (lines 444-508)
- Testing methodology for 4 different skill types (lines 395-455)
- A 30-item deployment checklist (lines 596-634)

The skill is essentially a comprehensive handbook. Much of this content (CSO, flowcharts, code examples, anti-patterns, testing methodology) is reference material that should live in sub-files, not in the SKILL.md body. The skill already has sub-files (`testing-skills-with-subagents.md`, `persuasion-principles.md`, `examples/`) but the SKILL.md itself has not been trimmed to match.

**Recommendation:** Keep the SKILL.md body to under 200 lines: overview, skill types, SKILL.md structure template, the Iron Law, checklist. Move CSO guide, flowchart conventions, testing methodology, and anti-patterns to reference sub-files. Saves approximately 400 lines.

### 4. `commands/learnings.md` (200 lines)

**Core Purpose:** Trigger the `engineering-docs` skill to document a solved problem.

This command should be a thin shim (like `execute-plan.md` at 10 lines), but instead it is 200 lines that re-describe the entire engineering-docs workflow with a 6-subagent parallel orchestration layer on top. It describes "Context Analyzer", "Solution Extractor", "Related Docs Finder", "Prevention Strategist", "Category Classifier", and "Documentation Writer" as parallel subagents, then adds 7 optional specialized agent invocations post-documentation.

The engineering-docs skill already describes the same workflow as a 7-step process. The learnings command adds a parallel execution strategy and agent roster that the engineering-docs skill does not reference. This creates two competing descriptions of the same workflow.

Additionally, lines 82-92 use XML `<preconditions>` tags with attributes like `enforcement="advisory"` -- a pattern that adds structural complexity without changing behavior.

**Recommendation:** Reduce to a thin shim like `execute-plan.md`: "Invoke the `clavain:engineering-docs` skill and follow it exactly as presented to you." If parallel agent dispatch is truly needed, add it to the engineering-docs skill itself rather than having two competing workflow descriptions. Saves approximately 180 lines.

### 5. `commands/review.md` (455 lines)

**Core Purpose:** Run multi-agent code review on a PR or branch.

This is the second-largest command file. Several sections are unnecessary:

- **Stakeholder Perspective Analysis (lines 119-155):** 37 lines asking questions like "What's the ROI?", "What's the total cost of ownership?", "How does this affect time-to-market?" These are business analysis questions, not code review questions. The actual review is performed by the specialized agents (security-sentinel, performance-oracle, etc.) which have their own prompts.
- **Scenario Exploration checklist (lines 157-172):** 10 generic checklist items ("Concurrent Access", "Scale Testing", "Cascading Failures") that are already covered by the specialized agents. The concurrency-reviewer handles race conditions; the performance-oracle handles scale; the security-sentinel handles injection attacks.
- **Multi-Angle Review Perspectives (lines 176-203):** 28 lines of bullet points ("Code craftsmanship evaluation", "Knowledge sharing effectiveness", "Mentoring opportunities") that read like a management framework, not operational instructions. No agent acts on "Team Dynamics Angle."
- **Template repetition (lines 270-348):** The todo file structure, naming convention, and status values are described twice -- once in the instruction body and again in the template section. The `file-todos` skill already defines all of this.
- **Phase numbering is broken:** Sections jump from "### 1" to "### 4" to "### 6" with non-sequential numbering, suggesting content was deleted but headers were not renumbered.
- **XML tags throughout:** `<command_purpose>`, `<role>`, `<review_target>`, `<task_list>`, `<parallel_tasks>`, `<conditional_agents>`, `<ultrathink_instruction>`, `<deliverable>`, `<thinking_prompt>`, `<stakeholder_perspectives>`, `<questions>`, `<scenario_checklist>`, `<synthesis_tasks>`, `<critical_instruction>`, `<critical_requirement>`. These XML tags add structural overhead without changing agent behavior compared to markdown headers.

**Recommendation:** Cut stakeholder analysis, scenario exploration, multi-angle perspectives, and template repetition. Fix broken numbering. Replace XML tags with markdown headers. Target: 200 lines. Saves approximately 250 lines.

### 6. `commands/resolve-parallel.md`, `resolve-todo-parallel.md`, `resolve-pr-parallel.md`

**Core Purpose:** Resolve items (TODO comments, file todos, PR comments) using parallel subagents.

These three commands share approximately 80% identical structure:
1. Analyze (gather items)
2. Plan (create TodoWrite list with mermaid diagram)
3. Implement (spawn pr-comment-resolver agents in parallel)
4. Commit & Resolve

The differences are:
- `resolve-parallel`: resolves TODO comments in code
- `resolve-todo-parallel`: resolves `todos/*.md` file todos
- `resolve-pr-parallel`: resolves PR comments via `gh pr view`

The Plan section is copy-pasted verbatim across all three, including the identical instruction: "Output a mermaid flow diagram showing how we can do this."

**Recommendation:** Consolidate into a single `resolve-parallel` command with an argument that specifies the source type (`todos`, `pr`, or `code`), or keep three commands but extract the shared plan/implement/commit workflow into a shared reference.

### 7. `commands/clodex.md` (16 lines)

This is an alias file that says "Follow the codex-first command's instructions exactly." Alias commands are a pattern that adds file count without adding value. The Claude Code plugin system does not natively support command aliases, so this works by loading the clodex command content and then telling the agent to go find the codex-first content -- a two-step indirection.

**Recommendation:** If the alias is important for UX (shorter name), keep it but note this is a minor inefficiency. Low priority.

### 8. `commands/work.md` (277 lines)

**Core Purpose:** Execute a work plan autonomously.

The command is well-structured with clear phases (Quick Start, Execute, Quality Check, Ship It). However, Phase 4 (Ship It, lines 161-207) substantially duplicates the `landing-a-change` skill content. Both describe: verify tests, stage specific files (not `git add .`), commit with conventional message, create PR with gh, notify user. The `work` command does not reference the `landing-a-change` skill; it re-implements the same workflow inline.

**Recommendation:** Replace Phase 4 with "Use the `clavain:landing-a-change` skill to complete this work." This is what `executing-plans` already does (line 49). Saves approximately 50 lines.

### 9. `hooks/session-start.sh` (52 lines)

**Core Purpose:** Inject `using-clavain` skill content into every session as system context.

This script is clean and well-engineered. The `escape_for_json()` function uses bash parameter substitution (5 replacements) which is appropriate -- the comment explains why it replaced a character-by-character loop. The upstream staleness check is a local file age check with no network calls. The JSON output is correctly structured.

No issues found. This is the right level of complexity for what it does.

### 10. `AGENTS.md` (269 lines)

**Core Purpose:** Development guide for contributors.

Appropriately sized. Covers architecture, conventions, component types, adding components, validation, upstream tracking, and session completion. No significant waste. The "Landing the Plane" section at the end (lines 244-269) could be argued as belonging in a skill rather than the dev guide, but it is short enough not to matter.

No issues found.

### 11. 3-Layer Routing System

The 3-layer routing (Stage, Domain, Language) maps 32 skills, 23 agents, and 24 commands to user intent through three successive filters. For a plugin of this size, this is justified. A flat list of 79 components would be harder to navigate. The routing tables fit on one screen each and provide clear lookup paths.

The routing heuristic (lines 68-76 of using-clavain) is 8 lines and actionable. No over-engineering here.

---

## Issues Found

### P0-1: Red Flags table in using-clavain burns per-session context (P0)

**File:** `/root/projects/Clavain/skills/using-clavain/SKILL.md`, lines 79-94

**Why P0:** This content is injected into every single session. Every token in this file has a recurring cost. The Red Flags table is 16 lines (11 rows + header) that all say the same thing: "do not rationalize skipping skills." This message is already conveyed by line 27 and the EXTREMELY-IMPORTANT block.

**Fix:** Delete lines 79-94 entirely. The existing rule statement and priority section are sufficient.

### P1-1: engineering-docs skill is 489 lines (P1)

**File:** `/root/projects/Clavain/skills/engineering-docs/SKILL.md`

489 lines for a documentation skill. Contains a Future Enhancements section listing features explicitly not being built, duplicate section headers, a 7-option decision menu with full handler descriptions for rarely-used options, and error handling that duplicates the blocking gates.

**Fix:** Trim to under 200 lines. Move decision menu details, quality guidelines, and error handling to reference sub-files. Delete Future Enhancements section.

### P1-2: writing-skills skill is 656 lines (P1)

**File:** `/root/projects/Clavain/skills/writing-skills/SKILL.md`

Largest skill in the plugin. Contains a full TDD tutorial, CSO guide, flowchart conventions, 4-type testing methodology, and 30-item checklist -- all inline rather than in reference sub-files.

**Fix:** Keep SKILL.md body under 200 lines. Move CSO, testing methodology, and anti-patterns to `references/` sub-files.

### P1-3: learnings command duplicates engineering-docs skill (P1)

**File:** `/root/projects/Clavain/commands/learnings.md`

200 lines re-describing the engineering-docs workflow with a parallel subagent layer. Two competing descriptions of the same workflow exist.

**Fix:** Reduce to thin shim: "Invoke the `clavain:engineering-docs` skill."

### P1-4: review command has 250+ lines of non-actionable content (P1)

**File:** `/root/projects/Clavain/commands/review.md`

Stakeholder analysis ("What's the ROI?"), scenario checklists (already covered by specialized agents), multi-angle perspectives ("Team Dynamics Angle"), and repeated todo file templates.

**Fix:** Cut non-actionable sections, fix broken numbering, replace XML tags with markdown. Target 200 lines.

### P2-1: Three resolve-* commands share 80% identical structure (P2)

**Files:** `/root/projects/Clavain/commands/resolve-parallel.md`, `resolve-todo-parallel.md`, `resolve-pr-parallel.md`

Plan and Implement sections are copy-pasted verbatim.

**Fix:** Consolidate or extract shared workflow.

### P2-2: clodex is an alias file with indirection cost (P2)

**File:** `/root/projects/Clavain/commands/clodex.md`

Loads one command's content, then tells agent to go find another command's content.

**Fix:** Low priority. Accept or inline the codex-first content.

### P2-3: work command Phase 4 duplicates landing-a-change skill (P2)

**File:** `/root/projects/Clavain/commands/work.md`, lines 161-207

Re-implements verify-test-commit-push-PR workflow already in the landing-a-change skill.

**Fix:** Replace Phase 4 with skill reference, as executing-plans already does.

---

## Improvements Suggested

### IMP-1: Cut Red Flags table from using-clavain

**Current:** 16 lines of rationalization prevention in every-session context.
**Proposed:** Delete the table. The rule statement and EXTREMELY-IMPORTANT block are sufficient.
**Impact:** 16 lines saved from every-session context injection. Reduces recurring token cost.

### IMP-2: Collapse engineering-docs to under 200 lines

**Current:** 489-line monolithic SKILL.md with inline decision menus, error handling, quality guidelines, and Future Enhancements.
**Proposed:** Trim to overview + 3-4 step process + link to template. Move details to `references/` sub-files. Delete Future Enhancements.
**Impact:** ~290 lines saved. Faster skill loading, easier maintenance.

### IMP-3: Extract TDD tutorial from writing-skills into reference sub-files

**Current:** 656-line SKILL.md with inline CSO guide, flowchart conventions, testing methodology.
**Proposed:** Keep core process + checklist in SKILL.md (~200 lines). Move CSO, testing, anti-patterns to `references/`.
**Impact:** ~450 lines saved from the SKILL.md body. Content preserved in sub-files.

### IMP-4: Make learnings command a thin shim

**Current:** 200-line command re-describing the engineering-docs workflow with parallel agent overlay.
**Proposed:** 10-line shim: "Invoke the `clavain:engineering-docs` skill and follow it exactly."
**Impact:** ~190 lines saved. Eliminates competing workflow descriptions.

### IMP-5: Strip review command of non-actionable content

**Current:** 455 lines with stakeholder analysis, scenario checklists, multi-angle perspectives, template repetition.
**Proposed:** Keep agent dispatch, synthesis, and todo creation. Cut business/team analysis sections. Fix broken section numbering.
**Impact:** ~250 lines saved. Review command becomes actionable, not aspirational.

### IMP-6: Consolidate resolve-* commands

**Current:** Three separate files sharing 80% identical content.
**Proposed:** Either one parameterized command or extract shared workflow into a reference file.
**Impact:** ~50 lines saved. Eliminates copy-paste maintenance burden.

---

## YAGNI Violations

### engineering-docs Future Enhancements section

Lines 479-489 list 6 features explicitly not being built: "Search by date range", "Filter by severity", "Tag-based search interface", "Metrics", "Export to shareable format", "Import community solutions." This is textbook YAGNI -- documenting features you have decided not to build. These lines consume context when the skill is loaded and provide no operational value.

**What to do instead:** Delete the section. If these features become needed, the need will be obvious and the implementation can be designed fresh with current constraints.

### engineering-docs 7-option decision menu

Options 4 ("Add to existing skill") and 5 ("Create new skill") describe full multi-step workflows for actions that are speculative from within a documentation capture context. If a user wants to create a new skill, they will use the `writing-skills` skill directly.

**What to do instead:** Keep options 1-3 and 6. Cut 4, 5, and 7 (or collapse to "Other").

### review command stakeholder perspectives

A code review command asking "What's the ROI?" and "How does this affect time-to-market?" No review agent acts on these questions. No findings are generated from them. They exist because the command was designed for a hypothetical comprehensive review process that is not implemented.

**What to do instead:** Delete the section. If business analysis is needed, it belongs in a separate planning skill, not a code review command.

### learnings command 6-subagent orchestration

The `learnings` command describes 6 specialized subagents ("Context Analyzer", "Solution Extractor", etc.) that are not actual defined agents in the `agents/` directory. They are aspirational descriptions of a parallel workflow. The engineering-docs skill describes the same work as a sequential 7-step process. Two different execution models for the same task is a YAGNI violation.

**What to do instead:** Pick one model (the sequential engineering-docs process is simpler and already works) and delete the other.

---

## Overall Assessment

**Total potential LOC reduction:** ~450-500 lines across 6-8 files (approximately 15-20% of total plugin content).

**Complexity score:** Medium. The plugin's architecture (routing, hooks, agents) is sound. The complexity lives in individual files that have accumulated detail beyond what is operationally necessary.

**Recommended action:** Proceed with simplifications. The P0 item (Red Flags table in using-clavain) should be addressed first because it has a recurring per-session cost. The P1 items (engineering-docs, writing-skills, learnings, review) are the highest-value cleanup targets. The P2 items are quality-of-life improvements.

**What the cleanup got right:**
- The hook script is clean and efficient.
- AGENTS.md is appropriately sized.
- The 3-layer routing system is justified.
- Thin-shim commands (execute-plan, lfg) are good patterns to replicate.
- Namespace cleanup (no superpowers/compound-engineering references) is thorough.

**What the cleanup missed:**
- Skills that grew organically and were never trimmed to match the recommended size guidance.
- Commands that re-describe skill workflows instead of delegating to them.
- Copy-pasted content across the resolve-* command family.
- A Future Enhancements section that explicitly violates the plugin's own YAGNI principles.
