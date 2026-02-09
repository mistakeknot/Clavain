---
agent: fd-code-quality
tier: adaptive
issues:
  - id: P1-1
    severity: P1
    section: "phases/launch-codex.md"
    title: "Codex launch template uses different output format preamble wording than Task launch template"
  - id: P1-2
    severity: P1
    section: "SKILL.md — Agent Roster"
    title: "Agent Roster still references defunct 'Project Agents' category but roster table only has 'Adaptive' tier"
  - id: P1-3
    severity: P1
    section: "phases/launch-codex.md"
    title: "Task description section headers use inconsistent format vs clodex SKILL.md conventions"
  - id: P2-1
    severity: P2
    section: "SKILL.md — Phase references"
    title: "Phase numbering gap — Phase 4 reads cross-ai.md but SKILL.md describes it as 'Optional' without clear skip condition"
  - id: P2-2
    severity: P2
    section: "phases/launch.md — Prompt template"
    title: "Prompt template duplicates YAML frontmatter spec that review-agent.md template also contains"
  - id: P2-3
    severity: P2
    section: "SKILL.md — Agent Roster table"
    title: "spec-flow-analyzer listed under Adaptive Reviewers but uses workflow subagent_type"
improvements:
  - id: IMP-1
    title: "Align phases/ subdirectory pattern with clodex's references/ and templates/ convention"
    section: "File organization"
  - id: IMP-2
    title: "Add explicit version/revision metadata to SKILL.md frontmatter like clodex does"
    section: "SKILL.md frontmatter"
  - id: IMP-3
    title: "Standardize agent tier vocabulary across SKILL.md, launch.md, and launch-codex.md"
    section: "Cross-file consistency"
  - id: IMP-4
    title: "Extract shared YAML frontmatter output spec into a reusable sub-file"
    section: "DRY — launch.md vs review-agent.md"
verdict: needs-changes
---

### Summary (3-5 lines)

The flux-drive skill is the most structurally complex skill in Clavain, spanning 5 files across a `phases/` subdirectory. Its core conventions -- YAML frontmatter, imperative voice, progressive loading -- align well with Clavain's documented skill patterns. However, cross-file consistency has drifted: the launch.md prompt template and the clodex review-agent.md template define the same YAML output format with subtly different preamble wording, the agent tier vocabulary is inconsistent between files, and the Agent Roster mixes category labels that no longer match the actual agent definitions. These are maintainability issues that will compound as more agents are added.

### Issues Found

**P1-1: Codex launch template output format preamble diverges from Task launch template**
- Location: `/root/projects/Clavain/skills/flux-drive/phases/launch-codex.md` (line 67-68 REVIEW_PROMPT section) vs `/root/projects/Clavain/skills/flux-drive/phases/launch.md` (lines 61-66)
- Convention: Clavain skills should use consistent, canonical prompt patterns. The clodex `review-agent.md` template at `/root/projects/Clavain/skills/clodex/templates/review-agent.md` says: "**CRITICAL: Output Format Override** -- Your agent identity below may define a default output format. IGNORE IT. Use ONLY the format specified in Phase 3 of this prompt." Meanwhile, launch.md's prompt template uses different wording: "Your agent definition has a default output format. IGNORE IT for this task. You MUST use the format specified below." These express the same intent but with different phrasing, meaning an agent dispatched via Codex vs Task gets a subtly different instruction.
- Violation: Two paths to the same outcome (review agent output) use divergent prompts. If one is updated, the other may be missed.
- Fix: Extract the output format override preamble into a single canonical block. Either (a) launch-codex.md should reference "use the same prompt template from phases/launch.md" (which it already says at line 68 but the review-agent.md template duplicates it anyway), or (b) both should reference a shared sub-file like `phases/output-format.md`.

**P1-2: Agent Roster section still references "Project Agents" category but all agents in the table are "Adaptive"**
- Location: `/root/projects/Clavain/skills/flux-drive/SKILL.md` lines 176-183 (Project Agents heading) and lines 188-208 (Adaptive Reviewers table)
- Convention: AGENTS.md at line 133 lists agent categories as review/research/workflow. The `agents/review/` directory contains files like `fd-code-quality.md` and `architecture-strategist.md` which are all Clavain plugin agents.
- Violation: The "Project Agents (.claude/agents/fd-*.md)" heading at line 176 describes agents that live in the *target project's* `.claude/agents/` directory, not in the Clavain plugin. This is architecturally correct but confusing because the tier labels used in the frontmatter output spec are `domain|project|adaptive|cross-ai` (launch.md line 79) while the roster only defines categories called "Project Agents", "Adaptive Reviewers", and "Cross-AI". There is no "domain" tier defined anywhere. A reviewer asked to output `tier: domain` has no roster entry to reference.
- Fix: Either (a) remove "domain" from the tier enum in the YAML frontmatter spec since no agents use it, or (b) document what "domain" means (perhaps it was a planned tier that was never implemented). Align the tier vocabulary to exactly match what the roster defines.

**P1-3: Task description section headers in launch-codex.md use different format than clodex SKILL.md**
- Location: `/root/projects/Clavain/skills/flux-drive/phases/launch-codex.md` lines 61-78 vs `/root/projects/Clavain/skills/clodex/SKILL.md` lines 60-78
- Convention: The clodex skill's megaprompt mode uses section headers like `GOAL:`, `EXPLORE_TARGETS:`, `IMPLEMENT:`, `BUILD_CMD:`, `TEST_CMD:`. The parallel delegation mode uses `PROJECT:`, `TASK:`, `FILES:`, `CRITERIA:`, `BUILD_CMD:`, `TEST_CMD:`.
- Violation: flux-drive's launch-codex.md introduces its own set of section headers: `PROJECT:`, `AGENT_IDENTITY:`, `REVIEW_PROMPT:`, `AGENT_NAME:`, `TIER:`, `OUTPUT_FILE:`. While the dispatch.sh parser uses `^[A-Z_]+:$` regex (so any SCREAMING_SNAKE header works), this creates a third vocabulary of section names alongside clodex's two. The `AGENT_IDENTITY:` and `REVIEW_PROMPT:` headers are unique to flux-drive and not documented in clodex.
- Fix: This is acceptable as-is since review agents have genuinely different input needs than implementation agents. But document the relationship: add a comment in launch-codex.md noting that these headers are specific to the review-agent.md template and parsed by dispatch.sh's generic section parser. This prevents future maintainers from thinking they need to match clodex's headers.

**P2-1: Phase 4 optional skip condition is implicit**
- Location: `/root/projects/Clavain/skills/flux-drive/SKILL.md` lines 248-251
- Convention: Other phases (1, 2, 3) have explicit gating: Phase 2 has clodex mode detection, Phase 3 has "verify all agents completed". Phase 4 says "Read the cross-AI phase file now" with "(Optional)" in the heading but the actual skip logic is buried inside `phases/cross-ai.md` at Step 4.1.
- Violation: The progressive loading instruction says "Read each phase file when you reach it -- not before" (line 10). For Phase 4, the orchestrator has to read the file to discover it should skip it. This is a minor waste but more importantly inconsistent with how Phase 2 handles its conditional (clodex detection happens before reading launch-codex.md).
- Fix: Add a one-line gate in SKILL.md before the Phase 4 read instruction: "If Oracle was not in the triage roster, skip Phase 4 and offer the lightweight interpeer option described below."

**P2-2: YAML frontmatter output spec is duplicated in launch.md and review-agent.md**
- Location: `/root/projects/Clavain/skills/flux-drive/phases/launch.md` lines 69-108 vs `/root/projects/Clavain/skills/clodex/templates/review-agent.md` lines 20-35
- Convention: Clavain AGENTS.md says "Keep SKILL.md lean (1,500-2,000 words) -- move detailed content to sub-files" (line 112). DRY is a project value.
- Violation: The exact same YAML frontmatter structure (`agent`, `tier`, `issues`, `improvements`, `verdict`) and prose structure (`Summary`, `Issues Found`, `Improvements Suggested`, `Overall Assessment`) is defined in both files. If the schema changes (e.g., adding a `confidence` field), both must be updated independently.
- Fix: Extract the output format spec into `skills/flux-drive/phases/output-format.md` (or a shared location). Both launch.md and review-agent.md can reference it. This also makes it easier to validate agent output against a single canonical spec.

**P2-3: spec-flow-analyzer listed under Adaptive Reviewers but has workflow subagent_type**
- Location: `/root/projects/Clavain/skills/flux-drive/SKILL.md` line 205
- Convention: The Adaptive Reviewers table header says "These agents auto-detect project documentation" but spec-flow-analyzer's subagent_type is `clavain:workflow:spec-flow-analyzer`, not `clavain:review:*`. Per AGENTS.md line 135, workflow agents are a separate category with different characteristics.
- Violation: Mixing a workflow agent into the "Adaptive Reviewers" section creates a false impression that all agents in the table have the same behavior. The scoring rules reference "Adaptive Reviewers" as a category that gets +1 bonus -- should spec-flow-analyzer get that bonus?
- Fix: Either (a) move spec-flow-analyzer to its own small "Workflow Agents" sub-table in the roster, or (b) rename the table to "Plugin Agents" to accurately describe all non-Project, non-Oracle agents.

### Improvements Suggested

**IMP-1: Align phases/ subdirectory naming with clodex's references/ and templates/ pattern**
- Location: `/root/projects/Clavain/skills/flux-drive/phases/`
- The clodex skill uses `references/` for reference material and `templates/` for dispatch templates. The interpeer skill uses `references/` for Oracle docs. Flux-drive introduces a new subdirectory name, `phases/`, which no other skill uses. This is not wrong -- phases are genuinely different from references or templates -- but it is the only skill that uses this naming. Consider whether `phases/` is the right abstraction or whether these files are closer to "references" that the orchestrator reads on demand. Given that the content is procedural instructions rather than reference material, `phases/` is defensible but worth documenting in AGENTS.md as an accepted sub-directory pattern alongside `references/`, `templates/`, and `examples/`.

**IMP-2: Add version metadata to SKILL.md frontmatter**
- Location: `/root/projects/Clavain/skills/flux-drive/SKILL.md` lines 1-4
- The clodex skill includes `version: 0.3.0` in its frontmatter. Flux-drive does not. Given that flux-drive is the most complex skill in the plugin (5 files, 4 phases, 19+ agents in its roster), version tracking would help correlate behavior changes across sessions. Convention from AGENTS.md line 109-110 only requires `name` and `description`, so `version` is optional, but clodex sets a precedent.

**IMP-3: Standardize agent tier vocabulary**
- Location: Cross-file (`SKILL.md`, `phases/launch.md`, `phases/launch-codex.md`)
- The YAML frontmatter output spec at launch.md line 79 defines tiers as `domain|project|adaptive|cross-ai`. The roster in SKILL.md uses "Project Agents", "Adaptive Reviewers", and "Cross-AI (Oracle)". The review-agent.md template at line 33 shows `tier: {{TIER}}`. These should all use the exact same vocabulary. Recommend canonicalizing to: `project` (for .claude/agents/fd-*.md), `adaptive` (for all plugin agents regardless of review/workflow/research category), and `cross-ai` (for Oracle). Drop `domain` unless there is a documented use case.

**IMP-4: Extract shared output format spec to reduce duplication**
- Location: `/root/projects/Clavain/skills/flux-drive/phases/launch.md` and `/root/projects/Clavain/skills/clodex/templates/review-agent.md`
- Both files define the same YAML frontmatter schema and prose structure for agent output. A shared file (e.g., `skills/flux-drive/phases/output-format.md`) would make the schema authoritative in one place. The launch.md prompt template would say "See output-format.md for the required format" and review-agent.md would embed it at build time via dispatch.sh. This is the highest-leverage DRY improvement for flux-drive maintainability.

### Overall Assessment

Flux-drive is well-structured for its complexity. The progressive-loading pattern (`phases/` directory with on-demand reads) is a sound approach for a 5-file skill that would be unwieldy as a single SKILL.md. Naming conventions (kebab-case files, imperative voice, YAML frontmatter) align with Clavain's documented patterns. The main quality issues are cross-file consistency: tier vocabulary drift between files, duplicated output format specs, and a minor category mismatch in the agent roster. These are P1-P2 issues that affect maintainability rather than correctness. Fixing the tier vocabulary (IMP-3) and extracting the shared output format (IMP-4) would be the highest-impact changes.
