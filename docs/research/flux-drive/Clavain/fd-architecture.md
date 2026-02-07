---
agent: fd-architecture
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Component Count Consistency"
    title: "Pervasive count mismatch: actual 32 skills / 24 commands but AGENTS.md, using-clavain SKILL.md, and plugin.json each report different numbers"
  - id: P1-1
    severity: P1
    section: "Routing Table Completeness"
    title: "codex-first-dispatch skill, codex-first command, and clodex command are absent from the using-clavain routing table"
  - id: P1-2
    severity: P1
    section: "Upstream Sync Architecture"
    title: "Two independent upstream sync systems operate on different state files with overlapping but non-identical repo lists and no documented relationship"
  - id: P1-3
    severity: P1
    section: "Upstream fileMap Conflict"
    title: "brainstorming/SKILL.md is mapped in both the superpowers and compound-engineering upstreams.json entries, creating a last-writer-wins merge conflict"
  - id: P1-4
    severity: P1
    section: "flux-drive Skill"
    title: "Tier 1 agents reference gurgeh-plugin subagent types creating an undeclared cross-plugin dependency"
  - id: P2-1
    severity: P2
    section: "Command Layer Consistency"
    title: "work.md Phase 4 mentions feature branches and git push -u origin despite trunk-based development policy"
  - id: P2-2
    severity: P2
    section: "Command Layer Consistency"
    title: "review.md prerequisites mention worktrees despite trunk-based-only policy"
  - id: P2-3
    severity: P2
    section: "Hook Architecture"
    title: "SessionStart hook marked async:true may not block before first LLM response, causing routing table absence on first turn"
  - id: P2-4
    severity: P2
    section: "MCP Server Configuration"
    title: "mcp-agent-mail server hardcodes localhost:8765 with no health check or graceful degradation for portable use"
  - id: P2-5
    severity: P2
    section: "Upstream Remnant Contamination"
    title: "Rails-specific content remains in deployment-verification-agent and work.md despite general-purpose-only policy"
  - id: P2-6
    severity: P2
    section: "Command Layer Consistency"
    title: "Thick commands (review 455 lines, work 275 lines) embed full workflow logic that belongs in skills"
improvements:
  - id: IMP-1
    title: "Unify upstream sync systems or clearly document their distinct purposes"
    section: "Upstream Sync Architecture"
  - id: IMP-2
    title: "Add automated component count validation to prevent count drift"
    section: "Component Count Consistency"
  - id: IMP-3
    title: "Ship Clavain-native Tier 1 agents for flux-drive instead of depending on external gurgeh-plugin"
    section: "flux-drive Skill"
  - id: IMP-4
    title: "Standardize command thickness conventions with explicit categories in AGENTS.md"
    section: "Command Layer Consistency"
  - id: IMP-5
    title: "Add cross-reference validation script to prevent phantom references from accumulating"
    section: "Cross-Reference Integrity"
verdict: needs-changes
---

### Summary

Clavain's core architecture is sound and has improved significantly since the prior review (c57fbeb). The 3-layer routing system (Stage / Domain / Language), the skill/agent/command decomposition, and the SessionStart hook injection form a coherent plugin architecture. Most P0 and P1 issues from the prior review have been fixed: phantom agent references (cora-test-reviewer, data-integrity-guardian), invalid @agent- syntax, compound-docs references, EVERY_WRITE_STYLE.md, bin/get-pr-comments scripts, and lib/skills-core.js have all been removed or corrected. However, the project has grown (32 skills, 24 commands) without updating component counts in multiple authoritative files, the routing table has gaps for the new codex-first components, and the dual upstream sync systems create architectural confusion.

### Section-by-Section Review

#### 1. Component Count Consistency

This is the most pervasive issue. The actual component counts on disk are:

- **Skills**: 32 (verified via glob of `skills/*/SKILL.md`)
- **Agents**: 23 (verified via glob of `agents/{review,research,workflow}/*.md`)
- **Commands**: 24 (verified via glob of `commands/*.md`)

But multiple authoritative files disagree:

| File | Location | Claims |
|------|----------|--------|
| `/root/projects/Clavain/CLAUDE.md` | line 7 | 32 skills, 23 agents, 24 commands |
| `/root/projects/Clavain/README.md` | line 3 | 32 skills, 23 agents, 24 commands |
| `/root/projects/Clavain/.claude-plugin/plugin.json` | line 4 | 23 agents, 24 commands, 32 skills |
| `/root/projects/Clavain/AGENTS.md` | line 12 | **31 skills, 23 agents, 22 commands** |
| `/root/projects/Clavain/skills/using-clavain/SKILL.md` | line 22 | **31 skills, 23 agents, 22 commands** |

CLAUDE.md, README.md, and plugin.json are correct (32/23/24). AGENTS.md and the using-clavain SKILL.md are stale (31/23/22). The using-clavain SKILL.md count is especially critical because it is injected into every session via the SessionStart hook -- agents will believe they have 31 skills and 22 commands when 32 and 24 actually exist, potentially missing the newer components during routing.

The discrepancy is exactly accounted for by the new components added after the prior review:
- **New skill** (31 -> 32): `codex-first-dispatch`
- **New commands** (22 -> 24): `codex-first`, `clodex`

#### 2. Routing Table Completeness (`skills/using-clavain/SKILL.md`)

The routing table is the architectural linchpin. It was improved since the last review: `codex-delegation` now appears in the Execute stage (line 37). However, three newer components are missing:

| Component | Type | Should Be In |
|-----------|------|-------------|
| `codex-first-dispatch` | skill | Execute stage, alongside `codex-delegation` |
| `codex-first` | command | Execute stage commands column, or Meta stage |
| `clodex` | command | Same row as `codex-first` (it is an alias) |

The `codex-first-dispatch` skill is the execution primitive for codex-first mode -- it is referenced from `codex-first` command's "Dispatch Workflow" section (line 57 of `/root/projects/Clavain/commands/codex-first.md`). Without routing table presence, the using-clavain routing heuristic will never direct users to this skill.

Additionally, the routing table's Key Commands Quick Reference (lines 122-134 of `/root/projects/Clavain/skills/using-clavain/SKILL.md`) lists 9 commands. With 24 total commands, 15 are unlisted. While listing all 24 would be excessive, the codex-first toggle deserves a spot since it changes session-wide behavior.

#### 3. Plugin Manifest (`.claude-plugin/plugin.json`)

The manifest is clean and correct. Two MCP servers are declared:

- **context7**: Remote HTTP endpoint (`https://mcp.context7.com/mcp`). No concerns -- external service with expected availability.
- **mcp-agent-mail**: Local HTTP endpoint (`http://127.0.0.1:8765/mcp`). This hardcoded localhost dependency means the plugin will generate connection errors on any machine where the mcp-agent-mail server is not running. Since Clavain is a general-purpose plugin, most users will not have this server. There is no documented setup requirement in README.md or AGENTS.md, no health check, and no graceful degradation.

The plugin.json description field is the only place that correctly lists all three counts (32 skills, 24 commands, 23 agents) in one line. This is correct.

#### 4. Hook Architecture (`hooks/hooks.json` + `hooks/session-start.sh`)

The SessionStart hook design is architecturally sound:

- `session-start.sh` reads `using-clavain/SKILL.md`, JSON-escapes it with performant bash parameter expansion, and outputs `hookSpecificOutput.additionalContext` JSON
- The upstream staleness check (file age of `docs/upstream-versions.json` > 7 days) is local-only with no network calls -- good design for a session-start hook
- `set -euo pipefail` and proper error handling

Remaining concern: The hook is marked `"async": true` in `/root/projects/Clavain/hooks/hooks.json`. For a SessionStart hook that injects the routing table, this means the hook might not complete before the first LLM response. If the routing table arrives late, the first user message may be processed without skill awareness. Changing to `"async": false` would guarantee the routing context is present for the first turn.

#### 5. 3-Layer Decomposition (Skills / Agents / Commands)

**Skills (32)**: Well-organized with one directory per skill. Sub-resources (references, examples, templates) are properly nested within skill directories. YAML frontmatter is consistent. The `engineering-docs` skill has been cleaned up -- no more compound-docs heading, EVERY_WRITE references, or hotwire-native content.

**Agents (23)**: Properly categorized into review (15), research (5), and workflow (3). The `<example>` blocks with `<commentary>` are present in all agents examined. Language-specific reviewers have non-overlapping domains. The agent roster is well-partitioned.

**Commands (24)**: The layer continues to show inconsistent thickness:

| Category | Commands | Line Counts |
|----------|----------|-------------|
| Thin wrappers | write-plan, execute-plan, flux-drive, create-agent-skill, clodex | 1-16 lines each |
| Moderate | brainstorm, quality-gates, plan-review, codex-first, upstream-sync | 16-94 lines each |
| Thick workflows | review (455 lines), work (275 lines), learnings (203 lines), triage (~311 lines) | Full multi-phase workflows |

The thick commands embed complete workflow logic including multi-agent dispatch, synthesis, and todo creation. AGENTS.md convention says commands "can reference skills" and "can dispatch agents" but the thick commands go beyond this -- they contain the full orchestration. This is not necessarily wrong, but the architectural convention should acknowledge both patterns.

#### 6. Upstream Sync Architecture

This is the most architecturally confusing area. There are **two independent upstream sync systems**:

**System 1: Daily Change Detection**
- Files: `scripts/upstream-check.sh`, `docs/upstream-versions.json`, `.github/workflows/upstream-check.yml`
- Tracks: 7 repos (superpowers, superpowers-lab, superpowers-dev, compound-engineering, beads, oracle, mcp_agent_mail)
- State: `docs/upstream-versions.json` stores release tags and short commit SHAs per repo
- Automation: Daily GitHub Action at 08:00 UTC, opens issues labeled `upstream-sync`
- Purpose: **Detection** -- "have the upstreams changed?"

**System 2: Automated Merge Pipeline**
- Files: `upstreams.json`, `.github/workflows/sync.yml` (untracked), `scripts/sync-upstreams.sh` (missing from disk)
- Tracks: 4 repos (superpowers, superpowers-lab, superpowers-dev, compound-engineering) -- NOT beads, oracle, mcp_agent_mail
- State: `upstreams.json` stores full commit SHAs, file-level mapping with rename/path transformations
- Automation: Weekly GitHub Action on Mondays, uses Claude Code + Codex to merge, creates PRs
- Purpose: **Remediation** -- "apply upstream changes to local files"

The architectural relationship is undocumented. Key concerns:

1. **Different repo lists**: System 1 tracks 7 repos; System 2 tracks 4. The 3 missing from System 2 (beads, oracle, mcp_agent_mail) are "knowledge upstreams" (Clavain documents their APIs) vs "source upstreams" (Clavain contains their files). This distinction makes sense but is never stated.

2. **Different state formats**: System 1 uses short SHAs in `docs/upstream-versions.json`; System 2 uses full SHAs in `upstreams.json`. The commit hashes in System 1 (`a98c5df`) match the shortened form of System 2's hashes (`a98c5dfc9de0df5318f4980d91d24780a566ee60`), suggesting they were synchronized at one point but will drift independently.

3. **Session-start hook only checks System 1**: The staleness warning in `session-start.sh` checks `docs/upstream-versions.json` age, not `upstreams.json`. This means the hook warns about stale change detection but not stale merge state.

4. **`scripts/sync-upstreams.sh` referenced in MEMORY.md but missing from disk**: The MEMORY.md file states this script exists, but glob and git status show only `scripts/upstream-check.sh` on disk. The `sync.yml` workflow uses Claude Code inline prompting instead of a local script, which is consistent with the file not existing -- but MEMORY.md is misleading.

5. **`upstreams.json` and `sync.yml` are both untracked** (shown in git status). They exist on disk but are not committed to the repo. This means the automated merge pipeline is not yet checked into the repository.

#### 7. Upstream fileMap Conflict

In `/root/projects/Clavain/upstreams.json`, the file `skills/brainstorming/SKILL.md` appears in both the `superpowers` entry (line 10) and the `compound-engineering` entry (line 77). During the sync.yml merge pipeline, both upstreams will attempt to update the same local file. The sync workflow processes upstreams sequentially, so the last one (compound-engineering) will overwrite whatever superpowers wrote. This is a data integrity issue -- the merge pipeline has no conflict detection for overlapping file maps.

This is the only overlapping file between the two upstreams that map to the same local path.

#### 8. flux-drive Skill

The flux-drive skill at `/root/projects/Clavain/skills/flux-drive/SKILL.md` (373 lines) implements a sophisticated 3-phase document review workflow with tiered agent triage.

The Tier 1 agents all reference `gurgeh-plugin:fd-*` subagent types (lines 139-143):

```
| fd-architecture | gurgeh-plugin:fd-architecture | ...
| fd-user-experience | gurgeh-plugin:fd-user-experience | ...
| fd-code-quality | gurgeh-plugin:fd-code-quality | ...
| fd-performance | gurgeh-plugin:fd-performance | ...
| fd-security | gurgeh-plugin:fd-security | ...
```

This creates an implicit cross-plugin dependency. The gurgeh-plugin is a separate project-specific plugin (associated with the Autarch project). If it is not installed, Tier 1 agents will fail at dispatch time. The skill's deduplication rule (Step 1.2 rule 4) says to prefer Tier 1 over Tier 3 when domains overlap -- so in practice, Tier 3 clavain agents will be suppressed in favor of gurgeh-plugin agents that may not exist.

The cross-project awareness logic (line 98) partially mitigates this by noting when the review target is different from where gurgeh-plugin is installed, but it does not handle the case where gurgeh-plugin is simply absent.

Notably, this review itself is running through flux-drive. The current execution demonstrates the fallback: when gurgeh-plugin agents are unavailable, the system falls back to the Architecture Reviewer role specified in the flux-drive prompt template. This works, but it is an implicit fallback rather than an explicit one documented in the skill.

#### 9. Cross-Reference Integrity (Progress Since Prior Review)

The prior review (from the existing fd-architecture.md) identified 11 phantom references. The current state:

| Prior Issue | Status | Evidence |
|-------------|--------|----------|
| P0-1: cora-test-reviewer in learnings.md | **Fixed** | grep returns no matches |
| P0-2: @agent- syntax in plan_review.md | **Fixed** | plan-review.md now uses proper Task tool syntax |
| P1-3: lib/skills-core.js superpowers namespace | **Fixed** | File no longer exists |
| P1-4: compound-docs reference in learnings.md | **Fixed** | grep returns no matches |
| P1-5: engineering-docs contamination | **Fixed** | No compound-docs, doc-fix, EVERY_WRITE, hotwire-native references |
| P1-6: EVERY_WRITE_STYLE in changelog.md | **Fixed** | grep returns no matches |
| P1-7: bin/get-pr-comments in resolve_pr_parallel.md | **Fixed** | Command rewritten to use gh CLI |
| P1-1: codex-delegation missing from routing | **Fixed** | Now in Execute stage |
| P1-2: Rails/Ruby references | **Partially fixed** | Reduced from 6+ files to 3 remaining files |
| P2-5: work.md feature branches | **Not fixed** | Still at line 183 |
| P2-6: review.md worktrees | **Not fixed** | Still at lines 20 and 47 |

Remaining Rails/Ruby references:

| File | Line | Content |
|------|------|---------|
| `/root/projects/Clavain/agents/review/deployment-verification-agent.md` | 58 | `rails db:migrate` in example table |
| `/root/projects/Clavain/commands/work.md` | 85, 127 | `bin/rails test` in examples |

These are now used alongside other language examples (npm test, pytest, go test) rather than as the sole example, which reduces the severity from P1 to P2.

#### 10. Command-Workflow Alignment

The `lfg.md` command at `/root/projects/Clavain/commands/lfg.md` chains 7 commands: brainstorm -> write-plan -> flux-drive -> work -> review -> resolve-todo-parallel -> quality-gates. This "golden path" is architecturally clean.

The `codex-first.md` command introduces a session-wide behavioral contract that changes how all subsequent execution works. This is a different pattern from other commands -- it is a mode toggle rather than a workflow. The CLAUDE.md auto-detection feature (line 82: "If the project's CLAUDE.md contains `codex-first: true`") adds an implicit activation path. The `clodex.md` command is properly implemented as a thin alias that defers to `codex-first`.

The `upstream-sync.md` command (at `/root/projects/Clavain/commands/upstream-sync.md`) documents the relationship with the System 1 pipeline (daily GitHub Action -> issues -> this command picks them up). It does not mention System 2 (the upstreams.json sync.yml merge pipeline), which reinforces that the two systems are disconnected.

### Issues Found

**P0-1: Pervasive component count mismatch (Component Count Consistency)**
The actual component counts (32 skills, 24 commands) do not match the counts in `/root/projects/Clavain/AGENTS.md` (line 12: "31 skills, 23 agents, 22 commands") or `/root/projects/Clavain/skills/using-clavain/SKILL.md` (line 22: "Clavain provides 31 skills, 23 agents, and 22 commands"). The using-clavain count is injected into every session, causing agents to work with stale component inventories. The discrepancy is caused by the addition of `codex-first-dispatch` (skill), `codex-first` (command), and `clodex` (command) without updating these files.

**P1-1: New codex-first components missing from routing table (Routing Table Completeness)**
The `codex-first-dispatch` skill, `codex-first` command, and `clodex` command are absent from the routing table in `/root/projects/Clavain/skills/using-clavain/SKILL.md`. The codex-first-dispatch skill should appear in the Execute stage alongside `codex-delegation`. The codex-first and clodex commands should appear in either the Execute or Meta stage commands column.

**P1-2: Dual upstream sync systems with no documented relationship (Upstream Sync Architecture)**
System 1 (`scripts/upstream-check.sh` + `docs/upstream-versions.json` + `.github/workflows/upstream-check.yml`) and System 2 (`upstreams.json` + `.github/workflows/sync.yml`) track overlapping sets of repos with different state formats, different automation schedules, and no shared state. System 1 tracks 7 repos for change detection; System 2 tracks 4 repos for automated merging. The 3 repos unique to System 1 are "knowledge upstreams" vs "source upstreams" -- a valid distinction that is never documented. AGENTS.md's "Upstream Tracking" section describes only System 1.

**P1-3: brainstorming/SKILL.md mapped in two upstreams (Upstream fileMap Conflict)**
In `/root/projects/Clavain/upstreams.json`, both the `superpowers` entry (line 10) and the `compound-engineering` entry (line 77) map to `skills/brainstorming/SKILL.md`. The sync.yml merge pipeline has no conflict resolution for overlapping file maps, so the last upstream processed will silently overwrite the prior merge result.

**P1-4: flux-drive Tier 1 depends on gurgeh-plugin (flux-drive Skill)**
All five Tier 1 agents in `/root/projects/Clavain/skills/flux-drive/SKILL.md` (lines 139-143) reference `gurgeh-plugin:fd-*` subagent types. This is an undeclared dependency on a separate plugin. There is no fallback documented in the skill for when gurgeh-plugin is not installed, and the deduplication rule (prefer Tier 1 over Tier 3) will suppress working Tier 3 agents in favor of non-existent Tier 1 agents.

**P2-1: work.md mentions feature branches (Command Layer Consistency)**
`/root/projects/Clavain/commands/work.md` line 183 contains `git push -u origin feature-branch-name`. This contradicts the trunk-based development policy in CLAUDE.md line 30: "Trunk-based development -- no branches/worktrees skills."

**P2-2: review.md mentions worktrees (Command Layer Consistency)**
`/root/projects/Clavain/commands/review.md` line 20 lists "Proper permissions to create worktrees" and line 47 says "in worktree or on current branch." This contradicts the trunk-based-only policy.

**P2-3: SessionStart hook async flag (Hook Architecture)**
The hook in `/root/projects/Clavain/hooks/hooks.json` is marked `"async": true`. If the hook does not complete before the LLM generates its first response, the routing table will be absent from the first turn. For a hook whose sole purpose is context injection, synchronous execution would be safer.

**P2-4: mcp-agent-mail hardcoded localhost (MCP Server Configuration)**
The mcp-agent-mail entry in `/root/projects/Clavain/.claude-plugin/plugin.json` hardcodes `http://127.0.0.1:8765/mcp`. For a general-purpose plugin distributed to users who may not have this server running, this will produce connection errors on every session.

**P2-5: Remaining Rails-specific content (Upstream Remnant Contamination)**
`/root/projects/Clavain/agents/review/deployment-verification-agent.md` line 58 uses `rails db:migrate` as the sole example in a deployment step table. `/root/projects/Clavain/commands/work.md` lines 85 and 127 use `bin/rails test` alongside other test commands. These are reduced from the prior review but still present.

**P2-6: Inconsistent command thickness (Command Layer Consistency)**
Commands range from 1-line skill wrappers (write-plan, flux-drive) to 455-line standalone workflows (review). The AGENTS.md convention does not acknowledge this split. Thick commands embed full multi-agent orchestration that architecturally belongs in skills.

### Improvements Suggested

**IMP-1: Unify or explicitly partition the upstream sync systems**
Document the distinction between "source upstreams" (4 repos tracked by System 2 for automated file merging) and "knowledge upstreams" (3 additional repos tracked by System 1 for change detection only). Add this to `/root/projects/Clavain/AGENTS.md` in the "Upstream Tracking" section. Consider whether System 1 should be deprecated in favor of extending System 2 with a detection-only mode for the 3 knowledge upstreams.

**IMP-2: Add automated component count validation**
Add a step to the validation checklist (or a script) that counts skills, agents, and commands on disk and compares against the counts in CLAUDE.md, AGENTS.md, plugin.json, README.md, and using-clavain/SKILL.md. This would catch count drift immediately when components are added or removed.

**IMP-3: Ship Clavain-native Tier 1 agents for flux-drive**
Instead of depending on gurgeh-plugin for Tier 1 agents, create Clavain-native equivalents (e.g., `agents/review/fd-architecture.md`, `fd-code-quality.md`, etc.) so flux-drive works out of the box. The gurgeh-plugin versions could then be Tier 2 overrides for projects that have gurgeh-plugin installed.

**IMP-4: Standardize command thickness in AGENTS.md**
Add an explicit convention distinguishing "thin commands" (1-10 lines, invoke a skill) from "orchestration commands" (multi-phase workflows). Document which commands fall into each category. For thick commands, consider extracting the workflow into a skill and converting the command to a thin wrapper, similar to how `flux-drive.md` wraps the `flux-drive` skill.

**IMP-5: Add cross-reference validation script**
Create `scripts/validate-refs.sh` that:
1. Extracts all `clavain:` references from skills, commands, and agents
2. Verifies each referenced skill, agent, or command exists on disk
3. Checks that component counts in documentation files match actual counts
4. Fails with a non-zero exit code on any mismatch
This would prevent the phantom reference issues that plagued the initial merge from recurring.

### Overall Assessment

Clavain's architecture is **acceptable with targeted fixes needed**. The core design (3-layer routing, skill/agent/command decomposition, SessionStart hook injection) is strong and has proven itself through active use. The prior review's critical issues (phantom references, invalid dispatch syntax, stale namespace) have been systematically addressed, demonstrating that the project has a functional feedback loop.

The most urgent issues are:
1. **Update component counts** in AGENTS.md and using-clavain/SKILL.md to match actual inventory (32 skills, 24 commands) -- this affects every session via the hook injection.
2. **Add codex-first components to the routing table** -- without this, the codex-first mode is discoverable only by users who already know it exists.
3. **Document the upstream sync architecture** -- the dual-system design is reasonable but the lack of documentation creates confusion about which system does what and how they relate.
