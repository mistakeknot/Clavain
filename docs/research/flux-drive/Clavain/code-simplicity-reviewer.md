---
agent: code-simplicity-reviewer
tier: 3
issues:
  - id: P0-1
    severity: P0
    section: "upstreams.json fileMap"
    title: "Five compound-engineering fileMap entries use underscores but local files use hyphens -- sync silently broken"
  - id: P0-2
    severity: P0
    section: "Skills: create-agent-skills vs writing-skills"
    title: "Two skills for skill authoring cover nearly identical ground -- 955 combined lines"
  - id: P1-1
    severity: P1
    section: "Count Drift"
    title: "plugin.json, CLAUDE.md, AGENTS.md, and README.md report different skill/command counts"
  - id: P1-2
    severity: P1
    section: "Previous Research References Phantom File"
    title: "Prior flux-drive research documents reference lib/skills-core.js which does not exist on disk"
  - id: P1-3
    severity: P1
    section: "Commands: resolve_parallel vs resolve_todo_parallel vs resolve_pr_parallel"
    title: "Three resolve commands share 90% identical structure with same typo -- only input source differs"
  - id: P1-4
    severity: P1
    section: "Skills: working-with-claude-code vs developing-claude-code-plugins"
    title: "Two skills for Claude Code plugin development with overlapping scope"
  - id: P1-5
    severity: P1
    section: "Commands: review vs quality-gates"
    title: "Both commands dispatch reviewer agents with synthesis -- quality-gates is a lightweight review"
  - id: P1-6
    severity: P1
    section: "Skills: engineering-docs"
    title: "510-line skill with XML-style enforcement tags and Rails-specific patterns in a general plugin"
  - id: P1-7
    severity: P1
    section: "Commands: learnings"
    title: "202-line command launches 6+ parallel subagents for documenting a solved problem -- over-engineered"
  - id: P1-8
    severity: P1
    section: "Skills: writing-skills"
    title: "655 lines -- longest skill, with extensive anti-rationalization content duplicated from TDD"
  - id: P1-9
    severity: P1
    section: "Commands: brainstorm vs skills/brainstorming"
    title: "Command is 115 lines replicating skill logic instead of being a thin shim"
  - id: P2-1
    severity: P2
    section: "Commands: review"
    title: "454-line review command has redundant stakeholder perspectives and ultra-thinking prompts"
  - id: P2-2
    severity: P2
    section: "Skills: agent-native-architecture"
    title: "435 lines -- comprehensive essay-like skill is more educational reference than actionable workflow"
  - id: P2-3
    severity: P2
    section: "Dual Upstream Sync Systems"
    title: "upstream-check.sh and sync.yml serve different purposes but the overlap creates confusion"
  - id: P2-4
    severity: P2
    section: "Commands: clodex alias"
    title: "clodex.md is a 16-line alias file that adds a command without adding value"
  - id: P2-5
    severity: P2
    section: "docs-sp-reference CLAUDE.md instruction"
    title: "CLAUDE.md says 'don't modify docs-sp-reference/' but the directory does not exist on disk"
improvements:
  - id: IMP-1
    title: "Fix upstreams.json fileMap to use hyphens matching actual local filenames"
    section: "upstreams.json fileMap"
  - id: IMP-2
    title: "Reconcile component counts across plugin.json, CLAUDE.md, AGENTS.md, and README.md"
    section: "Count Drift"
  - id: IMP-3
    title: "Annotate or remove prior flux-drive research references to non-existent lib/skills-core.js"
    section: "Previous Research References Phantom File"
  - id: IMP-4
    title: "Consolidate three resolve commands into one with a source parameter"
    section: "Commands: Resolve"
  - id: IMP-5
    title: "Merge create-agent-skills and writing-skills into one skill"
    section: "Skills: Skill Authoring"
  - id: IMP-6
    title: "Cut review command to ~150 lines by removing stakeholder/ultra-thinking bloat"
    section: "Commands: Review"
  - id: IMP-7
    title: "Simplify learnings command from 6 parallel subagents to direct file write"
    section: "Commands: Learnings"
  - id: IMP-8
    title: "Reduce writing-skills to ~300 lines by removing TDD content duplication"
    section: "Skills: Writing Skills"
  - id: IMP-9
    title: "Cut engineering-docs from 510 to ~200 lines by removing XML tags and Rails specifics"
    section: "Skills: Engineering Docs"
  - id: IMP-10
    title: "Remove clodex.md alias or document alias within codex-first.md"
    section: "Commands: clodex alias"
  - id: IMP-11
    title: "Remove stale docs-sp-reference instruction from CLAUDE.md"
    section: "docs-sp-reference CLAUDE.md instruction"
verdict: needs-changes
---

## Simplification Analysis

### Summary

Clavain is a general-purpose engineering discipline plugin for Claude Code, consolidating 4 upstream repos into 32 skills, 23 agents, and 24 commands. The core architecture (SessionStart hook injects routing, 3-layer dispatch, markdown-only components) is sound and appropriately simple. This review identified one P0 bug (fileMap naming mismatch that silently breaks automated sync), several documentation inconsistencies, and significant redundancy from the 4-plugin merge. The originally-flagged `lib/skills-core.js` does **not exist** on disk -- it was already removed, but prior research documents still reference it. Estimated total LOC that could be removed or consolidated: **~2,200 lines** (roughly 18% of the total across skills + commands + agents).

---

### Section-by-Section Review

#### 1. upstreams.json fileMap Bug (P0)

The compound-engineering section of `/root/projects/Clavain/upstreams.json` (lines 103-116) maps 5 command files using underscores in the **local** target path:

```json
"commands/generate_command.md": "commands/generate_command.md",
"commands/plan_review.md": "commands/plan_review.md",
"commands/resolve_parallel.md": "commands/resolve_parallel.md",
"commands/resolve_pr_parallel.md": "commands/resolve_pr_parallel.md",
"commands/resolve_todo_parallel.md": "commands/resolve_todo_parallel.md",
```

But ALL local command files use hyphens. A glob search for `commands/*_*.md` returns zero files. The actual files are `generate-command.md`, `plan-review.md`, `resolve-parallel.md`, `resolve-pr-parallel.md`, `resolve-todo-parallel.md`.

This means the weekly `sync.yml` workflow (which uses `upstreams.json` fileMap to match upstream paths to local paths) will either: (a) silently skip these files because the local target path does not match any existing file, or (b) create duplicate files with underscore names alongside the hyphenated originals.

**Fix:** Update the right-hand side of each mapping to use the actual hyphenated filenames. The left-hand side (upstream path) should keep whatever naming the upstream repo uses.

#### 2. lib/skills-core.js (Does Not Exist -- Phantom Reference)

The project context asked whether `lib/skills-core.js` is dead code. After thorough filesystem search: **this file does not exist.** There is no `lib/` directory at all. The only `.js` files in the repo are two legitimate utility scripts:

- `/root/projects/Clavain/skills/writing-skills/render-graphs.js` -- 168 lines, Graphviz DOT renderer for SKILL.md diagrams
- `/root/projects/Clavain/skills/working-with-claude-code/scripts/update_docs.js` -- 119 lines, fetches Claude Code docs from `docs.claude.com`

Neither is the `skills-core.js` library discussed in the project context. However, prior flux-drive research documents at `/root/projects/Clavain/docs/research/flux-drive/Clavain/fd-code-quality.md`, `/root/projects/Clavain/docs/research/flux-drive/Clavain/fd-architecture.md`, and `/root/projects/Clavain/docs/research/flux-drive/Clavain/summary.md` extensively analyze `lib/skills-core.js` as a 208-line file with `superpowers:` namespace references. That file has been deleted since those reviews were written. The research documents are now misleading and will waste future reviewers' time investigating a phantom issue.

A grep for `superpowers:` across the live codebase (excluding `docs/research/`) returns zero matches. The namespace cleanup is complete.

#### 3. Count Drift Across Documentation (P1)

Four files report different component counts:

| Source | Skills | Agents | Commands |
|--------|--------|--------|----------|
| `plugin.json` (line 4) | 32 | 23 | 24 |
| `CLAUDE.md` (line 7) | 31 | 23 | 22 |
| `AGENTS.md` (line 12) | 31 | 23 | 22 |
| `README.md` (line 3) | 32 | 23 | 24 |

Actual filesystem counts: 32 skills (SKILL.md files), 23 agents, 24 commands. `plugin.json` and `README.md` are correct. `CLAUDE.md` and `AGENTS.md` are stale by 1 skill and 2 commands, likely because `codex-first-dispatch` (skill), `clodex.md` (command), and `codex-first.md` (command) were added after those files were last updated.

#### 4. Dual Upstream Sync Systems (P2 -- Justified But Unclear)

Two distinct sync mechanisms exist:

**System A: Detection** -- `/root/projects/Clavain/scripts/upstream-check.sh` (150 lines) + `/root/projects/Clavain/.github/workflows/upstream-check.yml` (100 lines) + `/root/projects/Clavain/docs/upstream-versions.json`. Checks 7 repos daily via `gh api` for new releases/commits. Opens GitHub issues. Lightweight, no file changes.

**System B: Merge** -- `/root/projects/Clavain/upstreams.json` (120 lines) + `/root/projects/Clavain/.github/workflows/sync.yml` (155 lines). Tracks 4 repos weekly with per-file mapping. Claude Code + Codex auto-merge upstream file changes. Heavy, AI-driven.

The separation is defensible: detection is cheap and runs daily; merge is expensive and runs weekly. System A tracks 3 additional repos (beads, oracle, agent-mail) that are knowledge sources rather than file sources. The `session-start.sh` hook only checks System A's staleness.

The main simplicity concern is that the relationship between the two systems is not documented clearly. A future contributor would not immediately understand why there are two JSON files (`docs/upstream-versions.json` and `upstreams.json`) tracking overlapping sets of repos with different schemas.

**Recommendation:** Add a brief comment in `upstreams.json` or a section in `AGENTS.md` explaining: "upstream-check.sh detects changes across all 7 knowledge sources. upstreams.json drives the actual file-level merge for the 4 repos that contribute files to Clavain."

#### 5. Skill Authoring: create-agent-skills vs writing-skills (P0)

Two skills teach the same domain -- how to write Claude Code skills -- from different angles:

- `/root/projects/Clavain/skills/create-agent-skills/SKILL.md` (299 lines): Anthropic's official spec (frontmatter format, naming, directory structure, audit rubric)
- `/root/projects/Clavain/skills/writing-skills/SKILL.md` (655 lines): TDD applied to documentation (pressure testing with subagents, RED-GREEN-REFACTOR, CSO optimization)

Both specify YAML frontmatter fields, directory structure, naming conventions, skill type taxonomies, and anti-patterns. The unique content in `writing-skills` is the TDD testing methodology and CSO section, but ~200 lines of rationalization prevention tables are duplicated from `test-driven-development`.

**Recommendation:** Merge into one skill. Keep `create-agent-skills` as primary, fold in TDD testing methodology (~100 lines) and CSO section from `writing-skills`. Cross-reference `test-driven-development` for rationalization tables instead of duplicating them. Target: ~350 lines combined, down from 954.

#### 6. Resolve Commands: Near-Identical Trio (P1)

`/root/projects/Clavain/commands/resolve-parallel.md` (34 lines), `/root/projects/Clavain/commands/resolve-todo-parallel.md` (37 lines), and `/root/projects/Clavain/commands/resolve-pr-parallel.md` (49 lines) share the same 4-step workflow (Analyze, Plan, Implement via parallel agents, Commit), the same planning prose word-for-word, and even the same typo ("liek this" instead of "like this").

The only difference is the source of items: code TODOs, file todos from `todos/*.md`, or PR comments via `gh pr view`.

**Recommendation:** Consolidate into a single `/resolve` command with an argument or auto-detection. One command, ~50 lines. Saves ~70 lines and eliminates the confusing near-identical trio.

#### 7. review.md Bloat (P2)

`/root/projects/Clavain/commands/review.md` is 455 lines. It includes:

- XML ceremony (`<task_list>`, `<thinking>`, `<parallel_tasks>`, `<stakeholder_perspectives>`, etc.) adding visual noise
- 5-stakeholder perspective analysis (developer, ops, end user, security, business) with generic questions like "What's the ROI?" -- not actionable from a code review agent
- "Multi-Angle Review Perspectives" section (technical excellence, business value, risk management, team dynamics) duplicating what the specialized agents already cover
- Duplicated severity legend (appears in both Phase 4 synthesis and Step 3 summary report)
- 100+ lines of detailed todo file creation instructions that duplicate the `file-todos` skill

The core logic is: (1) determine review target, (2) dispatch 6-12 agents based on file types and risk, (3) synthesize findings, (4) create todo files. That is ~100-150 lines of actionable content.

**Recommendation:** Cut to ~150-200 lines. Remove stakeholder perspectives (~80 lines), multi-angle review perspectives (~30 lines), verbose todo creation instructions (~100 lines, reference `file-todos` skill instead), deduplicate severity legend. Replace XML tags with markdown headings.

#### 8. learnings.md Over-Engineering (P1)

`/root/projects/Clavain/commands/learnings.md` (202 lines) dispatches 6 parallel subagents to document a single solved problem: Context Analyzer, Solution Extractor, Related Docs Finder, Prevention Strategist, Category Classifier, Documentation Writer. Then optionally triggers additional specialized agents.

For documenting "the N+1 query fix we just applied," this is disproportionate. A single agent (or the main thread) with a structured template can extract context, write the solution, find related docs, and classify the category in one pass.

**Recommendation:** Reduce to a thin shim invoking the `engineering-docs` skill (which already handles structured solution documentation). Target: ~20 lines. Saves ~180 lines.

#### 9. Plugin-Dev Skills Overlap (P1)

`/root/projects/Clavain/skills/working-with-claude-code/SKILL.md` (173 lines) is a reference index listing ~35 documentation files in `references/`. `/root/projects/Clavain/skills/developing-claude-code-plugins/SKILL.md` (285 lines) is a workflow guide for the plugin lifecycle. `developing-claude-code-plugins` already cross-references `working-with-claude-code`.

**Recommendation:** Merge `working-with-claude-code` into `developing-claude-code-plugins` as a "Reference Index" section. Target: ~300 lines combined, saving ~150.

#### 10. brainstorm Command vs Skill (P1)

`/root/projects/Clavain/commands/brainstorm.md` (115 lines) replicates and expands the `brainstorming` skill's content with 4 phases. Other similar commands like `/write-plan` and `/execute-plan` are thin shims (~7 lines each).

**Recommendation:** Reduce to a thin shim: "Invoke the `clavain:brainstorming` skill for: $ARGUMENTS." If Phase 0 (requirements clarity check) is valuable, add it to the skill (~10 lines). Target: 7-10 line command. Saves ~90 lines.

#### 11. clodex.md Alias (P2)

`/root/projects/Clavain/commands/clodex.md` is 16 lines that simply say "this is an alias for /codex-first." The maintenance risk is that if `codex-first.md` is updated, someone must remember the alias file exists.

**Recommendation:** Remove `clodex.md` or note the alias within `codex-first.md` frontmatter/header. If the plugin framework requires a separate file for aliases, add a comment in `codex-first.md` referencing it.

#### 12. docs-sp-reference Stale Reference (P2)

`CLAUDE.md` contains the instruction: "docs-sp-reference/ is historical archive from source plugins -- don't modify." But `docs-sp-reference/` does not exist on disk (glob returns zero files, directory is not present). The `.gitignore` does not mention it. This instruction is harmless but misleading.

**Recommendation:** Remove the instruction from CLAUDE.md.

---

### Issues Found

| ID | Severity | File(s) | Description |
|----|----------|---------|-------------|
| P0-1 | P0 | `/root/projects/Clavain/upstreams.json` lines 106-112 | 5 fileMap entries use underscores for local targets but local files use hyphens -- sync silently broken |
| P0-2 | P0 | `skills/create-agent-skills/` + `skills/writing-skills/` | Two skills for same domain, 955 combined lines |
| P1-1 | P1 | `CLAUDE.md`, `AGENTS.md` | Say "31 skills, 22 commands" but actual counts are 32/24 |
| P1-2 | P1 | `docs/research/flux-drive/Clavain/fd-*.md`, `summary.md` | Reference `lib/skills-core.js` which does not exist |
| P1-3 | P1 | `commands/resolve-*.md` (3 files) | Near-identical commands with shared typo ("liek this") |
| P1-4 | P1 | `skills/working-with-claude-code/` + `skills/developing-claude-code-plugins/` | Overlapping plugin-dev skills |
| P1-5 | P1 | `commands/review.md` + `commands/quality-gates.md` | quality-gates is a strict subset of review |
| P1-6 | P1 | `skills/engineering-docs/SKILL.md` | 510 lines with XML tags and Rails-specific content |
| P1-7 | P1 | `commands/learnings.md` | 6 parallel subagents for writing one doc file |
| P1-8 | P1 | `skills/writing-skills/SKILL.md` | 655 lines, duplicates TDD rationalization content |
| P1-9 | P1 | `commands/brainstorm.md` | 115 lines replicating skill logic instead of thin shim |
| P2-1 | P2 | `commands/review.md` | 455 lines of XML ceremony, stakeholder analysis, duplicated legends |
| P2-2 | P2 | `skills/agent-native-architecture/SKILL.md` | 435-line educational essay more than actionable workflow |
| P2-3 | P2 | `scripts/upstream-check.sh` + `.github/workflows/sync.yml` | Dual sync systems with unclear relationship |
| P2-4 | P2 | `commands/clodex.md` | 16-line alias file |
| P2-5 | P2 | `CLAUDE.md` | References non-existent `docs-sp-reference/` directory |

### Improvements Suggested

| ID | Title | Impact |
|----|-------|--------|
| IMP-1 | Fix `upstreams.json` fileMap: change underscore local targets to hyphens | Fixes broken sync for 5 files |
| IMP-2 | Update CLAUDE.md and AGENTS.md counts to 32 skills, 24 commands | Eliminates confusion, 4 lines changed |
| IMP-3 | Annotate prior flux-drive research re: deleted `lib/skills-core.js` | Prevents wasted investigation |
| IMP-4 | Consolidate 3 resolve commands into 1 | -2 files, -70 lines |
| IMP-5 | Merge `create-agent-skills` and `writing-skills` | -600 lines |
| IMP-6 | Cut `review.md` to ~150-200 lines | -250 lines |
| IMP-7 | Simplify `learnings.md` to thin shim | -180 lines |
| IMP-8 | Reduce `writing-skills` TDD duplication | -350 lines |
| IMP-9 | Rewrite `engineering-docs` without XML/Rails | -310 lines |
| IMP-10 | Remove `clodex.md` alias | -1 file, -16 lines |
| IMP-11 | Remove stale `docs-sp-reference/` instruction from CLAUDE.md | 1 line |

### YAGNI Violations

1. **`engineering-docs` "Future Enhancements" section** (lines 502-510 of SKILL.md): Lists features like "search by date range", "metrics", "export to shareable format." Not needed now.

2. **`review.md` stakeholder perspectives** (lines 119-155): "Business Perspective: What's the ROI?" is not actionable from a code review agent reviewing a diff.

3. **`review.md` "Multi-Angle Review Perspectives"** (lines 176-203): "Team Dynamics Angle: Mentoring opportunities" is aspirational, not functional.

4. **`learnings.md` 6 parallel subagents**: A Context Analyzer, Solution Extractor, Related Docs Finder, Prevention Strategist, Category Classifier, and Documentation Writer for writing one markdown file. A single agent pass suffices.

5. **`writing-skills` persuasion psychology references**: Academic citations (Cialdini, 2021; Meincke et al., 2025) for convincing an LLM to follow rules.

6. **`clodex.md` alias file**: 16 lines that say "follow codex-first.md." Users can type `/clavain:codex-first` directly.

### Overall Assessment

**Total potential LOC reduction: ~2,200 lines (18% of total)**

The plugin's core concepts are sound -- the 3-layer routing, SessionStart hook, and skill/agent/command separation are clean designs. The complexity is concentrated in specific areas:

1. **Post-merge redundancy**: Same concept implemented differently across source plugins (skill authoring, plan execution, review commands)
2. **Commands that should be thin shims** grew into standalone workflows duplicating skill content
3. **Over-engineering for parallelism**: 6 subagents to write one doc file
4. **One concrete sync bug**: Underscore/hyphen mismatch in `upstreams.json` fileMap

The 32 skills and 23 agents are individually justified. The consolidation opportunities are in commands (not the core component types) and in 2-3 skill pairs that cover the same domain.

**Complexity score: Medium-High** -- not because individual components are complex, but because overlapping components from the 4-plugin merge create navigation burden.

**Recommended action: Proceed with simplifications.** Priority order:
1. **Immediate**: Fix P0-1 (fileMap underscore bug) -- 5 lines changed in `upstreams.json`
2. **Quick wins**: IMP-2 (count reconciliation), IMP-3 (annotate stale research), IMP-10 (remove clodex alias), IMP-11 (remove stale CLAUDE.md instruction)
3. **Medium effort**: IMP-4 (consolidate resolve commands), IMP-6 (trim review.md), IMP-7 (simplify learnings.md), IMP-9 (rewrite engineering-docs)
4. **Larger refactors**: IMP-5 (merge skill-authoring skills), IMP-8 (trim writing-skills)
