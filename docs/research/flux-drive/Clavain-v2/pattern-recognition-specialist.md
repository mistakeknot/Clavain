---
agent: pattern-recognition-specialist
tier: 3
issues:
  - id: P0-1
    severity: P0
    section: "Hooks Documentation"
    title: "README and architecture diagram omit 2 of 3 hook scripts and the SessionEnd lifecycle event"
  - id: P1-1
    severity: P1
    section: "Frontmatter Consistency"
    title: "plan-reviewer.md uses YAML block scalar while all 22 other agents use inline quoted description strings"
  - id: P1-2
    severity: P1
    section: "Frontmatter Consistency"
    title: "pr-comment-resolver.md has orphan 'color: blue' field not used by any other agent"
  - id: P1-3
    severity: P1
    section: "Code Duplication"
    title: "resolve-parallel and resolve-todo-parallel share near-identical Plan/Implement sections with informal first-person prose"
  - id: P1-4
    severity: P1
    section: "Frontmatter Consistency"
    title: "argument-hint values in heal-skill.md and create-agent-skill.md are unquoted while all 17 other commands use double-quoted strings"
  - id: P1-5
    severity: P1
    section: "Cross-Plugin Dependency"
    title: "flux-drive Tier 1 roster hardcodes gurgeh-plugin subagent types with no fallback when gurgeh-plugin is absent"
  - id: P1-6
    severity: P1
    section: "Upstream Sync"
    title: "brainstorm.md command is mapped from two different upstreams (superpowers and compound-engineering) creating merge ambiguity"
  - id: P1-7
    severity: P1
    section: "Trunk-Based Policy"
    title: "work.md and review.md contain feature-branch and worktree references that contradict trunk-based development policy"
  - id: P2-1
    severity: P2
    section: "Code Duplication"
    title: "escape_for_json function is duplicated identically in session-start.sh and agent-mail-register.sh"
  - id: P2-2
    severity: P2
    section: "Frontmatter Consistency"
    title: "allowed-tools format varies between inline arrays, multi-line YAML lists, and single values across commands"
  - id: P2-3
    severity: P2
    section: "Naming Consistency"
    title: "CREATION-LOG.md in systematic-debugging is an orphan artifact not present in any other skill directory"
  - id: P2-4
    severity: P2
    section: "Frontmatter Consistency"
    title: "learnings-researcher uses model: haiku while all 22 other agents use model: inherit -- intentional but undocumented"
  - id: P2-5
    severity: P2
    section: "Routing Table Coverage"
    title: "codex-delegation skill not mentioned in using-clavain routing table Layer 2 Workflow domain"
  - id: P2-6
    severity: P2
    section: "Description Style"
    title: "Skill descriptions follow 'Use when' pattern inconsistently -- some omit it or use alternative phrasing"
improvements:
  - id: IMP-1
    title: "Add validation script that checks frontmatter field consistency across all components"
    section: "Frontmatter Consistency"
  - id: IMP-2
    title: "Extract escape_for_json into a shared hooks/lib.sh sourced by both hooks"
    section: "Code Duplication"
  - id: IMP-3
    title: "Document the model: haiku exception in AGENTS.md as a deliberate cost-optimization decision"
    section: "Architecture Documentation"
  - id: IMP-4
    title: "Add explicit fallback clause to flux-drive for when gurgeh-plugin is not installed"
    section: "Cross-Plugin Dependency"
verdict: needs-changes
---

## Summary

This second-pass review of Clavain follows a prior 6-agent flux-drive review that identified 29 issues, of which 13 were fixed. The cleanup addressed the most visible issues: stale component counts, the `liek this` typo, `type.Make` spacing, Rails content scrubbing, and the agent-native-audit broken skill invocation. However, several structural consistency issues remain that the cleanup did not touch, and the fixes introduced one new discrepancy (hooks documentation now undercounts hook scripts).

The codebase is well-structured: all 32 skills have SKILL.md files, all directories use kebab-case, the 3-layer routing table is comprehensive, and naming conventions are consistent. The remaining issues are primarily about **frontmatter field format consistency** (3 issues), **documentation accuracy for hooks** (1 P0), and **unfixed items from the prior review** (resolve command duplication, worktree/branch references, gurgeh-plugin dependency).

## Section-by-Section Review

### 1. Frontmatter Consistency -- Skills

All 32 skills have valid YAML frontmatter with `name` and `description` fields. The frontmatter delimiter `---` appears correctly at lines 1 and 4 (or later for skills with additional fields). No skills define `model:` -- this is correct since skills are not agents.

**Fields used across skills:**

| Field | Count | Notes |
|-------|-------|-------|
| `name` | 32/32 | Consistent |
| `description` | 32/32 | Consistent |
| `user-invocable` | 1/32 | `slack-messaging` only (`false`) |
| `allowed-tools` | 2/32 | `slack-messaging`, `engineering-docs` |
| `preconditions` | 1/32 | `engineering-docs` only |

The `engineering-docs` skill is the only one with `preconditions` and `allowed-tools` in its frontmatter. The `slack-messaging` skill is the only one with `user-invocable: false`. These are legitimate specializations, not inconsistencies.

**Description style**: Most skill descriptions follow the "Use when [trigger condition]" pattern. Outliers:

| Skill | Description Start | Expected Pattern |
|-------|------------------|------------------|
| `using-clavain` | "Use when starting any conversation" | Acceptable variant |
| `codex-delegation` | "Use when executing a plan with Codex agents" | Matches pattern |
| `flux-drive` | "Use when reviewing documents or codebases" | Matches pattern |
| `distinctive-design` | "Use when creating distinctive, production-grade interfaces" | Matches pattern |

All 32 skill descriptions begin with "Use when" -- this is fully consistent.

### 2. Frontmatter Consistency -- Agents

All 23 agents have `name`, `description`, and `model` fields.

**Format outliers:**

1. `/root/projects/Clavain/agents/review/plan-reviewer.md` uses `description: |` (YAML block scalar) while all 22 other agents use `description: "..."` (inline double-quoted strings). This was flagged in the prior review as P2 and remains unfixed.

2. `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` has `color: blue` (line 4), a field not present on any other agent. This was flagged in the prior review as P2 and remains unfixed.

3. `/root/projects/Clavain/agents/research/learnings-researcher.md` uses `model: haiku` while all 22 other agents use `model: inherit`. This is an intentional cost optimization for lightweight research tasks but is not documented anywhere in AGENTS.md or CLAUDE.md.

**Description content**: All agent descriptions include `<example>` blocks with `<commentary>` tags. This is a consistent pattern across all 23 agents. The descriptions are verbose (most exceed 500 characters) but uniformly structured.

### 3. Frontmatter Consistency -- Commands

All 24 commands have `name` and `description` fields.

**argument-hint quoting inconsistency:**

- `/root/projects/Clavain/commands/heal-skill.md` line 4: `argument-hint: [optional: specific issue to fix]` (unquoted)
- `/root/projects/Clavain/commands/create-agent-skill.md` line 5: `argument-hint: [skill description or requirements]` (unquoted)
- All other 17 commands with `argument-hint` use double-quoted strings: `argument-hint: "[...]"`

Because YAML interprets `[...]` as an array, the unquoted values may parse incorrectly in strict YAML parsers. The Claude Code plugin system may tolerate this, but it is a format deviation.

**allowed-tools format inconsistency:**

Three different formats are used:
- Inline YAML array: `allowed-tools: [Read, Edit, Bash(ls:*), Bash(git:*)]` (heal-skill.md)
- Multi-line YAML list with `- item` entries (upstream-sync.md, codex-first.md, clodex.md)
- Single value: `allowed-tools: Skill(create-agent-skills)` (create-agent-skill.md)

While all three are valid YAML, consistency would improve maintainability.

**Commands missing argument-hint** (5/24):
- `write-plan` (has `disable-model-invocation: true` instead)
- `execute-plan` (has `disable-model-invocation: true` instead)
- `codex-first`
- `clodex`
- `review` -- wait, review does have `argument-hint`. Let me recount.

Actually: `write-plan`, `execute-plan`, `codex-first`, and `clodex` lack `argument-hint`. The first two use `disable-model-invocation` which is a valid alternative pattern. The latter two are toggle commands where an argument hint is arguably unnecessary.

### 4. Naming Consistency

**Directory naming**: All 32 skill directories use kebab-case consistently. No underscores, no camelCase.

**Agent file naming**: All 23 agent files use kebab-case. The `kieran-*-reviewer` naming pattern is consistent across Go, Python, TypeScript, and Shell variants.

**Command file naming**: All 24 command files use kebab-case.

**Upstream fileMap naming**: The compound-engineering upstream correctly maps from upstream snake_case filenames (`generate_command.md`, `plan_review.md`, etc.) to local kebab-case filenames (`generate-command.md`, `plan-review.md`, etc.). This is intentional cross-naming-convention mapping, not an error.

**One orphan file**: `/root/projects/Clavain/skills/systematic-debugging/CREATION-LOG.md` is a development artifact (creation log from the skill's extraction) that does not appear in any other skill directory. All other supplementary files in skill directories are functional (references, scripts, templates, workflows, assets). This file serves no runtime purpose.

### 5. Routing Table Coverage

The using-clavain routing table (Layer 1 + Layer 2) was updated in the prior cleanup. Checking current coverage:

**Skills in routing table vs filesystem:**

All 32 skills appear in at least one routing table layer, with one exception:
- `codex-delegation` appears in Layer 1 Execute stage but NOT in Layer 2 Workflow domain. Since the closely related `codex-first-dispatch` IS in Layer 2 Workflow, this is a minor gap.

**Commands in routing table:**

The Layer 1 table includes the following commands per stage. Cross-referencing against the 24 actual commands:

| Command | In Routing Table? |
|---------|------------------|
| `brainstorm` | Yes (Explore) |
| `write-plan` | Yes (Plan) |
| `plan-review` | Yes (Plan + Review) |
| `flux-drive` | Yes (Review docs) |
| `work` | Yes (Execute) |
| `execute-plan` | Yes (Execute) |
| `lfg` | Yes (Execute) |
| `resolve-parallel` | Yes (Execute) |
| `resolve-todo-parallel` | Yes (Execute) |
| `resolve-pr-parallel` | Yes (Execute) |
| `codex-first` | Yes (Execute) |
| `clodex` | Yes (Execute) |
| `repro-first-debugging` | Yes (Debug) |
| `review` | Yes (Review) |
| `quality-gates` | Yes (Review) |
| `migration-safety` | Yes (Review) |
| `agent-native-audit` | Yes (Review) |
| `changelog` | Yes (Ship) |
| `triage` | Yes (Ship) |
| `create-agent-skill` | Yes (Meta) |
| `generate-command` | Yes (Meta) |
| `heal-skill` | Yes (Meta) |
| `upstream-sync` | Yes (Meta) |
| `learnings` | Yes (Review, via Quick Reference) |

All 24 commands are now discoverable. The prior review's P1 about missing commands has been fixed.

### 6. Code Duplication

**resolve-parallel and resolve-todo-parallel:**

These two commands share near-identical text in their Plan (step 2) and Implement (step 3) sections. The shared text includes:

- Identical Plan paragraph: "Create a TodoWrite list of all unresolved items grouped by type. Make sure to look at dependencies..." (67 words, identical verbatim)
- Identical Implement pattern: "Spawn a pr-comment-resolver agent for each unresolved item..." (same structure)
- First-person voice: "I'll put the to-dos in the mermaid diagram flow-wise so the agent knows how to proceed in order" -- this appears in both files identically
- Informal phrasing in resolve-parallel: "Gather the things todo from above" (line 13)

The only differences between the two are:
- Step 1 (Analyze): resolve-parallel says "Gather the things todo from above" while resolve-todo-parallel says "Get all unresolved TODOs from the /todos/*.md directory"
- Step 4 (Commit): resolve-todo-parallel adds "Remove the TODO from the file, and mark it as resolved"
- resolve-todo-parallel has a filter rule for docs/plans/ and docs/solutions/ artifacts

This is approximately 20 lines of duplicated content. The prior review flagged this as P1/P2 for consolidation and it remains unfixed.

**escape_for_json in hook scripts:**

`/root/projects/Clavain/hooks/session-start.sh` (lines 16-24) and `/root/projects/Clavain/hooks/agent-mail-register.sh` (lines 93-101) contain identical `escape_for_json()` function implementations. This is a small duplication (9 lines) but could be extracted to a shared `hooks/lib.sh`.

### 7. Hooks Documentation

The README says "Hooks (2)" and describes only the SessionStart hook. However:

- `hooks.json` registers **3 hook scripts** across **2 lifecycle events**:
  - SessionStart: `session-start.sh` (context injection) + `agent-mail-register.sh` (Agent Mail auto-registration)
  - SessionEnd: `dotfiles-sync.sh` (config sync to GitHub)

- The README's architecture diagram lists only `session-start.sh` under hooks/
- The README's "Hooks (2)" heading describes only 1 hook behavior

This is a P0 because the README is the primary discovery surface and undercounts by 2 scripts and omits an entire lifecycle event. The CLAUDE.md also says "2 hooks" which was likely correct before the agent-mail-register.sh and dotfiles-sync.sh hooks were added.

### 8. Cross-Plugin Dependency (gurgeh-plugin)

`/root/projects/Clavain/skills/flux-drive/SKILL.md` lines 133-143 define Tier 1 agents that reference `gurgeh-plugin:fd-*` subagent types. The skill has a cross-project awareness clause (line 98) but no explicit fallback for when gurgeh-plugin is simply not installed.

The deduplication rule (line 104, rule 4) says "If a Tier 1 or Tier 2 agent covers the same domain as a Tier 3 agent, drop the Tier 3 one." This means when gurgeh-plugin IS installed, Tier 3 agents get suppressed. When gurgeh-plugin is NOT installed, the Tier 1 agents will fail at dispatch -- but the Tier 3 agents were already dropped during triage.

In practice, the current review demonstrates that the system does work without gurgeh-plugin (this very review is running through flux-drive using Tier 3 agents). The implicit fallback works but is not documented, making the behavior fragile.

### 9. Upstream Sync Consistency

`/root/projects/Clavain/upstreams.json` has a duplicate mapping for `commands/brainstorm.md`:
- Line 33 (superpowers): `"commands/brainstorm.md": "commands/brainstorm.md"`
- Line 113 (compound-engineering): `"commands/workflows/brainstorm.md": "commands/brainstorm.md"`

Both upstreams map different source paths to the same local file. If both upstreams modify their version, the sync system will face a merge conflict. This was flagged in the prior review (P1) and remains unfixed.

### 10. Trunk-Based Policy Violations

CLAUDE.md explicitly states: "Trunk-based development -- no branches/worktrees skills."

However:
- `/root/projects/Clavain/commands/work.md` line 185: `git push -u origin feature-branch-name` and line 182: "Create Pull Request (if using PR workflow)"
- `/root/projects/Clavain/commands/review.md` line 20: "Proper permissions to create worktrees" and line 47: "Ensure that the code is ready for analysis (either in worktree or on current branch)"

These references suggest a feature-branch workflow that contradicts the trunk-based policy. The prior review flagged these as P2 and they remain unfixed.

## Issues Found

### P0 -- Critical

**P0-1: README and architecture diagram omit 2 of 3 hook scripts and the SessionEnd lifecycle event**

Location: `/root/projects/Clavain/README.md` lines 99-101, 119-121

The README says "Hooks (2)" and only documents the SessionStart hook's context injection behavior. The actual hooks.json registers 3 scripts across 2 lifecycle events. The `agent-mail-register.sh` (SessionStart) and `dotfiles-sync.sh` (SessionEnd) are undocumented. The architecture diagram (line 121) only lists `session-start.sh`. CLAUDE.md line 4 also says "2 hooks" which may have been correct before these were added.

**Impact**: New users and developers cannot discover the agent-mail auto-registration or dotfiles-sync features. The hook count in CLAUDE.md and README.md is stale.

### P1 -- Important

**P1-1: plan-reviewer.md uses YAML block scalar while all 22 other agents use inline quoted description**

Location: `/root/projects/Clavain/agents/review/plan-reviewer.md` line 3

Uses `description: |` followed by multi-line content. All other 22 agents use `description: "..."` with inline double-quoted strings. This is functionally equivalent but creates a format inconsistency.

**P1-2: pr-comment-resolver.md has orphan 'color: blue' field**

Location: `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` line 4

The `color: blue` field does not appear on any other agent. It may be a remnant from the compound-engineering upstream. Unless this field has a functional effect in the Claude Code agent system, it should be removed for consistency.

**P1-3: resolve-parallel and resolve-todo-parallel share near-identical Plan/Implement sections with informal prose**

Locations:
- `/root/projects/Clavain/commands/resolve-parallel.md` lines 17-29
- `/root/projects/Clavain/commands/resolve-todo-parallel.md` lines 19-31

The shared text includes first-person voice ("I'll put the to-dos"), informal phrasing ("Gather the things todo from above"), and identical instructional prose. These could be consolidated or at minimum have the duplicated text standardized and the informal language cleaned up.

**P1-4: argument-hint values in heal-skill.md and create-agent-skill.md are unquoted**

Locations:
- `/root/projects/Clavain/commands/heal-skill.md` line 4: `argument-hint: [optional: specific issue to fix]`
- `/root/projects/Clavain/commands/create-agent-skill.md` line 5: `argument-hint: [skill description or requirements]`

YAML interprets `[...]` as an array. All other 17 commands use double-quoted strings for this field. The unquoted form may cause unexpected parsing behavior.

**P1-5: flux-drive Tier 1 roster hardcodes gurgeh-plugin subagent types with no explicit fallback**

Location: `/root/projects/Clavain/skills/flux-drive/SKILL.md` lines 133-143

When gurgeh-plugin is not installed, Tier 1 agents fail at dispatch. The deduplication rule (line 104) suppresses Tier 3 alternatives during triage. The implicit fallback works in practice (Tier 3 agents get selected when Tier 1 types are unavailable) but this behavior is not documented and could break if the triage logic changes.

**P1-6: brainstorm.md command is mapped from two upstreams**

Location: `/root/projects/Clavain/upstreams.json` lines 33 and 113

Both the `superpowers` and `compound-engineering` upstreams map to the same local file `commands/brainstorm.md`. If both upstreams change their version, the sync system will produce conflicting merges.

**P1-7: work.md and review.md contain feature-branch/worktree references**

Locations:
- `/root/projects/Clavain/commands/work.md` lines 182-185
- `/root/projects/Clavain/commands/review.md` lines 20, 47

CLAUDE.md states "Trunk-based development -- no branches/worktrees skills." These commands still reference `git push -u origin feature-branch-name` and "Proper permissions to create worktrees."

### P2 -- Nice-to-have

**P2-1: escape_for_json function duplicated in two hook scripts**

Locations:
- `/root/projects/Clavain/hooks/session-start.sh` lines 16-24
- `/root/projects/Clavain/hooks/agent-mail-register.sh` lines 93-101

Identical 9-line bash function. Could be extracted to `hooks/lib.sh` and sourced.

**P2-2: allowed-tools format varies across commands**

Three different YAML formats used:
- Inline array: `[Read, Edit, Bash(ls:*), Bash(git:*)]` in `heal-skill.md`
- Multi-line list in `upstream-sync.md`, `codex-first.md`, `clodex.md`
- Single value in `create-agent-skill.md`

**P2-3: CREATION-LOG.md orphan artifact in systematic-debugging**

Location: `/root/projects/Clavain/skills/systematic-debugging/CREATION-LOG.md`

This is a development history document (references `/Users/jesse/.claude/CLAUDE.md`) that does not appear in any other skill directory and serves no runtime purpose.

**P2-4: learnings-researcher uses model: haiku -- intentional but undocumented**

Location: `/root/projects/Clavain/agents/research/learnings-researcher.md` line 4

This is a deliberate cost optimization (lightweight grep-first filtering) but the exception is not documented in AGENTS.md or CLAUDE.md. Future maintainers may "fix" it to `model: inherit` without understanding the rationale.

**P2-5: codex-delegation skill missing from routing table Layer 2**

Location: `/root/projects/Clavain/skills/using-clavain/SKILL.md` Layer 2 Workflow domain (line 52)

The skill `codex-delegation` is listed in Layer 1 Execute stage but not in Layer 2 Workflow domain, where `codex-first-dispatch` IS listed. Both are workflow-category skills related to Codex agent delegation.

**P2-6: Skill descriptions follow 'Use when' pattern with some style variation**

Most descriptions start "Use when [condition]" but some add long qualifying clauses or use slightly different phrasing. This is consistent enough to not warrant changes but worth monitoring as new skills are added.

## Improvements Suggested

**IMP-1: Add a frontmatter validation script**

Create `scripts/validate-frontmatter.sh` that checks:
- All skills have `name` and `description` in YAML frontmatter
- All agents have `name`, `description`, and `model` in YAML frontmatter
- All `description` values in agents use inline double-quoted strings (not block scalar)
- All `argument-hint` values in commands are double-quoted
- No unexpected fields (like `color`) appear
- Component counts match README/CLAUDE.md/AGENTS.md/using-clavain

This would prevent drift as new components are added.

**IMP-2: Extract escape_for_json into shared hooks/lib.sh**

Create `/root/projects/Clavain/hooks/lib.sh` containing the shared `escape_for_json` function. Both `session-start.sh` and `agent-mail-register.sh` would source it: `source "$(dirname "$0")/lib.sh"`.

**IMP-3: Document the model: haiku exception**

Add a note to AGENTS.md in the architecture section:
> `learnings-researcher` uses `model: haiku` (not `model: inherit`) as a deliberate cost optimization. Its grep-first filtering workflow is lightweight enough that Haiku is sufficient, and using a smaller model reduces cost for high-frequency research queries.

**IMP-4: Add explicit fallback clause to flux-drive for absent gurgeh-plugin**

Add to `/root/projects/Clavain/skills/flux-drive/SKILL.md` after line 143:
> **Fallback when gurgeh-plugin is not installed**: If Tier 1 agent subagent_types are not available, the triage system should select Tier 3 agents for the same domains instead. Do NOT include Tier 1 agents in the selection if gurgeh-plugin is not installed on this system.

## Overall Assessment

Clavain is structurally sound after the prior cleanup. All 32 skills, 23 agents, and 24 commands follow kebab-case naming, have valid frontmatter, and are discoverable through the routing table. The main cleanup addressed the highest-impact issues (stale counts, Rails content, broken references).

The remaining issues fall into two categories: (1) format consistency that was flagged before but deferred (plan-reviewer block scalar, pr-comment-resolver color field, resolve command duplication, branch/worktree references) and (2) a new documentation gap from adding hooks without updating the README count. The P0 (hooks documentation) and the P1-4 (YAML parsing risk from unquoted argument-hint) are the highest-priority remaining items. Everything else is polish.

Verdict: **needs-changes** -- the P0 hooks documentation gap and P1 frontmatter parsing risks should be addressed, but the overall architecture is clean and well-organized.
