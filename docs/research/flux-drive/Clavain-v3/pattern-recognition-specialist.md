---
agent: pattern-recognition-specialist
tier: 3
issues:
  - id: P1-1
    severity: P1
    section: "AGENTS.md Architecture Tree"
    title: "Review agent count says 20 but actual count is 21"
  - id: P1-2
    severity: P1
    section: "Agent Frontmatter Schema"
    title: "5 fd-* agents missing required <example> blocks in description"
  - id: P2-1
    severity: P2
    section: "Routing Table vs Quick Reference"
    title: "3 commands missing from 3-layer routing tables (compound, setup, interpeer)"
  - id: P2-2
    severity: P2
    section: "Naming Conventions"
    title: "Inconsistent agent suffix taxonomy -- 10 different suffixes across 29 agents"
  - id: P2-3
    severity: P2
    section: "Cross-AI Review Skills"
    title: "prompterpeer, winterpeer, splinterpeer have no corresponding commands despite interpeer having one"
  - id: P2-4
    severity: P2
    section: "commands/setup.md"
    title: "Phantom reference to /clavain:tool-time which is a separate plugin command"
  - id: P2-5
    severity: P2
    section: "Naming Conventions"
    title: "brainstorm (command) vs brainstorming (skill) asymmetry -- confusing naming pair"
  - id: P2-6
    severity: P2
    section: "Command Duplication"
    title: "codex-first and clodex-toggle are duplicate commands for the same function"
  - id: P2-7
    severity: P2
    section: "Command Overlap"
    title: "resolve-parallel vs resolve-todo-parallel have confusing naming -- both resolve TODOs"
  - id: P2-8
    severity: P2
    section: "Routing Table"
    title: "fd-* agents (5 Tier 1 review agents) absent from using-clavain routing tables"
  - id: P3-1
    severity: P3
    section: "Agent Model Field"
    title: "learnings-researcher is the only agent using model: haiku -- all others use inherit"
improvements:
  - id: IMP-1
    title: "Add <example> blocks to all 5 fd-* agents to match schema convention"
    section: "Agent Frontmatter"
  - id: IMP-2
    title: "Fix AGENTS.md tree comment to say 21 review agents"
    section: "AGENTS.md"
  - id: IMP-3
    title: "Add compound, setup, and interpeer to the Stage routing table"
    section: "Routing Table"
  - id: IMP-4
    title: "Standardize agent suffix taxonomy or document the rationale for variation"
    section: "Naming Conventions"
  - id: IMP-5
    title: "Consider adding commands for prompterpeer, winterpeer, splinterpeer"
    section: "Cross-AI Commands"
  - id: IMP-6
    title: "Correct the /clavain:tool-time reference in setup.md to use proper plugin namespace"
    section: "commands/setup.md"
  - id: IMP-7
    title: "Add fd-* agents to using-clavain routing table Layer 2 or document why they are excluded"
    section: "Routing Table"
verdict: needs-changes
---

## Summary

Clavain v0.4.6 is a structurally sound plugin with accurate component counts (34 skills, 29 agents, 27 commands). All command files referenced in the Quick Reference exist on disk, all skill directory names match their SKILL.md frontmatter `name` fields, and all agent frontmatter `name` fields match their filenames. No phantom namespace references (`superpowers:`, `compound-engineering:`) remain in active code. However, there are 11 issues: 2 at P1 severity (count mismatch, missing schema elements), 8 at P2 (routing gaps, naming inconsistencies, duplicate commands, phantom references), and 1 at P3 (model field anomaly). The issues cluster around three themes: frontmatter schema compliance for the newer fd-* agents, routing table completeness, and naming convention drift.

## Section-by-Section Review

### 1. Command-to-File Consistency

**Status: PASS**

All 27 commands listed in the `/clavain:using-clavain` Quick Reference table correspond to command files on disk at `/root/projects/Clavain/commands/`. Verified by matching each command name in the Quick Reference against the filename (minus `.md`):

| Quick Reference Command | File on Disk | Match |
|------------------------|-------------|-------|
| lfg | `commands/lfg.md` | Yes |
| brainstorm | `commands/brainstorm.md` | Yes |
| write-plan | `commands/write-plan.md` | Yes |
| work | `commands/work.md` | Yes |
| execute-plan | `commands/execute-plan.md` | Yes |
| review | `commands/review.md` | Yes |
| plan-review | `commands/plan-review.md` | Yes |
| flux-drive | `commands/flux-drive.md` | Yes |
| quality-gates | `commands/quality-gates.md` | Yes |
| repro-first-debugging | `commands/repro-first-debugging.md` | Yes |
| resolve-parallel | `commands/resolve-parallel.md` | Yes |
| resolve-todo-parallel | `commands/resolve-todo-parallel.md` | Yes |
| resolve-pr-parallel | `commands/resolve-pr-parallel.md` | Yes |
| migration-safety | `commands/migration-safety.md` | Yes |
| agent-native-audit | `commands/agent-native-audit.md` | Yes |
| changelog | `commands/changelog.md` | Yes |
| triage | `commands/triage.md` | Yes |
| compound | `commands/compound.md` | Yes |
| create-agent-skill | `commands/create-agent-skill.md` | Yes |
| generate-command | `commands/generate-command.md` | Yes |
| heal-skill | `commands/heal-skill.md` | Yes |
| interpeer | `commands/interpeer.md` | Yes |
| debate | `commands/debate.md` | Yes |
| codex-first | `commands/codex-first.md` | Yes |
| clodex-toggle | `commands/clodex-toggle.md` | Yes |
| upstream-sync | `commands/upstream-sync.md` | Yes |
| setup | `commands/setup.md` | Yes |

No orphan command files exist -- every `.md` file in `commands/` appears in the Quick Reference, and vice versa.

### 2. Agent Reference Consistency

**Status: PASS with caveat (P2-8)**

All 29 agents exist on disk and every agent referenced from a command or skill resolves to an actual file:

- `commands/review.md` references: pattern-recognition-specialist, architecture-strategist, security-sentinel, performance-oracle, git-history-analyzer, agent-native-reviewer, go-reviewer, python-reviewer, typescript-reviewer, shell-reviewer, rust-reviewer, concurrency-reviewer, data-integrity-reviewer, data-migration-expert, deployment-verification-agent, code-simplicity-reviewer -- all exist at `/root/projects/Clavain/agents/review/` or `/root/projects/Clavain/agents/research/` or `/root/projects/Clavain/agents/workflow/`.
- `commands/plan-review.md` references: plan-reviewer, architecture-strategist, code-simplicity-reviewer -- all exist.
- `commands/migration-safety.md` references: data-migration-expert, data-integrity-reviewer, deployment-verification-agent -- all exist.
- `commands/repro-first-debugging.md` references: bug-reproduction-validator, git-history-analyzer -- all exist.
- `commands/quality-gates.md` references: code-simplicity-reviewer, go-reviewer, security-sentinel, data-integrity-reviewer, data-migration-expert, performance-oracle, concurrency-reviewer, architecture-strategist, python-reviewer, typescript-reviewer, shell-reviewer, rust-reviewer -- all exist.
- `skills/flux-drive/SKILL.md` references all 5 fd-* agents and 13 Tier 3 agents -- all exist.

**Caveat (P2-8):** The 5 fd-* agents (fd-architecture, fd-code-quality, fd-performance, fd-security, fd-user-experience) exist on disk and are referenced in `skills/flux-drive/SKILL.md` but are NOT mentioned anywhere in the `using-clavain` routing tables. They are flux-drive-specific Tier 1 agents, so this may be intentional (they are only dispatched through the flux-drive skill), but it means the routing table does not account for all 29 agents. A user browsing the routing table would not discover these agents exist.

### 3. Skill-to-Directory Name Consistency

**Status: PASS**

Every skill's SKILL.md frontmatter `name` field matches its parent directory name. Verified all 34:

| Directory | Frontmatter name | Match |
|-----------|-----------------|-------|
| agent-mail-coordination | agent-mail-coordination | Yes |
| agent-native-architecture | agent-native-architecture | Yes |
| beads-workflow | beads-workflow | Yes |
| brainstorming | brainstorming | Yes |
| clodex | clodex | Yes |
| create-agent-skills | create-agent-skills | Yes |
| developing-claude-code-plugins | developing-claude-code-plugins | Yes |
| dispatching-parallel-agents | dispatching-parallel-agents | Yes |
| distinctive-design | distinctive-design | Yes |
| engineering-docs | engineering-docs | Yes |
| executing-plans | executing-plans | Yes |
| file-todos | file-todos | Yes |
| finding-duplicate-functions | finding-duplicate-functions | Yes |
| flux-drive | flux-drive | Yes |
| interpeer | interpeer | Yes |
| landing-a-change | landing-a-change | Yes |
| mcp-cli | mcp-cli | Yes |
| prompterpeer | prompterpeer | Yes |
| receiving-code-review | receiving-code-review | Yes |
| refactor-safely | refactor-safely | Yes |
| requesting-code-review | requesting-code-review | Yes |
| slack-messaging | slack-messaging | Yes |
| splinterpeer | splinterpeer | Yes |
| subagent-driven-development | subagent-driven-development | Yes |
| systematic-debugging | systematic-debugging | Yes |
| test-driven-development | test-driven-development | Yes |
| upstream-sync | upstream-sync | Yes |
| using-clavain | using-clavain | Yes |
| using-tmux-for-interactive-commands | using-tmux-for-interactive-commands | Yes |
| verification-before-completion | verification-before-completion | Yes |
| winterpeer | winterpeer | Yes |
| working-with-claude-code | working-with-claude-code | Yes |
| writing-plans | writing-plans | Yes |
| writing-skills | writing-skills | Yes |

### 4. Agent Frontmatter Schema Consistency

**Status: NEEDS CHANGES (P1-2)**

The AGENTS.md specifies that agent frontmatter must include: `name`, `description` (with `<example>` blocks containing `<commentary>`), and `model`.

All 29 agents have `name` and `model` fields. All 29 agents have `description` fields. However, 5 agents lack the required `<example>` blocks in their descriptions:

| Agent | File | Has `<example>` | Has `<commentary>` |
|-------|------|-----------------|-------------------|
| fd-architecture | `/root/projects/Clavain/agents/review/fd-architecture.md` | No | No |
| fd-code-quality | `/root/projects/Clavain/agents/review/fd-code-quality.md` | No | No |
| fd-performance | `/root/projects/Clavain/agents/review/fd-performance.md` | No | No |
| fd-security | `/root/projects/Clavain/agents/review/fd-security.md` | No | No |
| fd-user-experience | `/root/projects/Clavain/agents/review/fd-user-experience.md` | No | No |

All 5 are the newer fd-* (flux-drive) Tier 1 agents. The remaining 24 agents all have `<example>` blocks with `<commentary>` as required.

**Model field consistency:** 28 of 29 agents use `model: inherit`. The lone exception is `learnings-researcher` at `/root/projects/Clavain/agents/research/learnings-researcher.md`, which uses `model: haiku` with a comment explaining the rationale (grep-based filtering, no heavy reasoning needed). This is a deliberate cost optimization, not an oversight (P3-1).

### 5. Naming Convention Analysis

**Status: NEEDS ATTENTION (P2-2, P2-5, P2-7)**

#### 5a. Agent Suffix Taxonomy

Agents use 10 different suffix patterns across 29 agents, creating an inconsistent naming taxonomy:

| Suffix Pattern | Agents | Count |
|---------------|--------|-------|
| `-reviewer` | go-reviewer, python-reviewer, typescript-reviewer, shell-reviewer, rust-reviewer, code-simplicity-reviewer, data-integrity-reviewer, concurrency-reviewer, agent-native-reviewer | 9 |
| `fd-*` (prefix, no suffix) | fd-architecture, fd-code-quality, fd-performance, fd-security, fd-user-experience | 5 |
| `-researcher` | best-practices-researcher, framework-docs-researcher, learnings-researcher | 3 |
| `-specialist` | pattern-recognition-specialist | 1 |
| `-strategist` | architecture-strategist | 1 |
| `-oracle` | performance-oracle | 1 |
| `-sentinel` | security-sentinel | 1 |
| `-expert` | data-migration-expert | 1 |
| `-agent` | deployment-verification-agent | 1 |
| `-analyst` | repo-research-analyst | 1 |
| `-analyzer` | git-history-analyzer, spec-flow-analyzer | 2 |
| `-validator` | bug-reproduction-validator | 1 |
| `-resolver` | pr-comment-resolver | 1 |

The review agents especially have inconsistent suffixes: most use `-reviewer` but security uses `-sentinel`, performance uses `-oracle`, architecture uses `-strategist`, data migration uses `-expert`, deployment uses `-agent`, and pattern recognition uses `-specialist`. These are conceptually all review agents (they all live in `agents/review/`) but use 7 different suffixes.

This is not necessarily wrong -- the creative names provide personality. But it means searching for "reviewer" will miss 12 of 21 review agents.

#### 5b. brainstorm vs brainstorming (P2-5)

- The **skill** is named `brainstorming` (directory: `skills/brainstorming/`)
- The **command** is named `brainstorm` (file: `commands/brainstorm.md`)

The command's description says "For freeform brainstorming without phases, use /brainstorming instead" and the skill says "For a guided workflow with repo research, use /brainstorm instead." These are distinct components that cross-reference each other with clear delineation. However, the naming is confusing:

- `/clavain:brainstorm` invokes the structured 4-phase **command**
- `clavain:brainstorming` invokes the freeform **skill**

The intuition that the longer name (`brainstorming`) is more comprehensive is wrong -- it is actually the simpler, freeform one. The shorter name (`brainstorm`) is the structured workflow. This is a naming trap.

#### 5c. resolve-parallel vs resolve-todo-parallel (P2-7)

Three commands share the `resolve-*-parallel` pattern:

| Command | Source | What It Resolves |
|---------|--------|-----------------|
| `resolve-parallel` | Grep for `TODO` in codebase | Code TODO comments |
| `resolve-todo-parallel` | `todos/*.md` files | CLI todo system entries |
| `resolve-pr-parallel` | `gh pr view` comments | PR review comments |

The naming issue: `resolve-parallel` resolves TODO comments (code-level), while `resolve-todo-parallel` resolves todo files (filesystem-level). The word "todo" appears in both contexts but means different things. A user wanting to resolve code TODOs might mistakenly reach for `resolve-todo-parallel`, and vice versa.

A clearer naming would distinguish the source: `resolve-code-todos-parallel`, `resolve-file-todos-parallel`, `resolve-pr-comments-parallel`. But this would break existing usage, so documenting the distinction prominently may be more practical.

### 6. Routing Table Completeness

**Status: NEEDS ATTENTION (P2-1, P2-3, P2-8)**

#### 6a. Commands missing from routing tables (P2-1)

Three commands appear in the Quick Reference but NOT in the 3-layer routing tables:

| Command | In Quick Reference | In Routing Table |
|---------|-------------------|-----------------|
| `compound` | Yes (line 149) | No |
| `setup` | Yes (line 158) | No |
| `interpeer` | Yes (line 153) | No (only in Cross-AI section) |

`compound` should logically appear in the **Ship** stage (it captures solved problems for documentation). `setup` could appear in **Meta** (it bootstraps the modpack). `interpeer` is in the Cross-AI Review section but not in any routing table row, which means the routing heuristic cannot discover it through the normal 3-layer lookup.

#### 6b. Skills without commands (P2-3)

Three cross-AI skills have no corresponding command:

| Skill | Has Command |
|-------|------------|
| `interpeer` | Yes (`/clavain:interpeer`) |
| `prompterpeer` | No |
| `winterpeer` | No |
| `splinterpeer` | No |

Users can invoke these via `Skill(prompterpeer)` etc., but there is no `/clavain:prompterpeer` slash command for direct invocation. Since `interpeer` has a command, the asymmetry suggests the other three were overlooked or intentionally omitted (they may be considered internal orchestration tools called by flux-drive rather than user-facing commands).

#### 6c. fd-* agents absent from routing table (P2-8)

The 5 codebase-aware review agents (fd-architecture, fd-code-quality, fd-performance, fd-security, fd-user-experience) are not in any routing table. They are only discoverable through the flux-drive skill's internal Agent Roster. This is likely intentional since they are dispatched exclusively by flux-drive, but it means the routing table's agent inventory is incomplete (24 of 29 agents are in the routing table).

### 7. Duplicate and Overlapping Commands

**Status: DOCUMENTED BUT NOTABLE (P2-6)**

`/clavain:codex-first` and `/clavain:clodex-toggle` are the same command. The clodex-toggle file at `/root/projects/Clavain/commands/clodex-toggle.md` explicitly says "This is an alias for `/codex-first`." The routing table lists both in the Execute stage. This is intentional but inflates the command count -- it could be argued this is 26 unique commands + 1 alias rather than 27 commands.

### 8. Phantom References

**Status: ONE FOUND (P2-4)**

In `/root/projects/Clavain/commands/setup.md` line 144:
```
- Run `/clavain:tool-time` to see tool usage analytics
```

`tool-time` is a separate plugin from the `interagency-marketplace`, not a Clavain command. The correct invocation would be `/tool-time:` (whatever its namespace is) or simply removing the `clavain:` prefix. Running `/clavain:tool-time` would fail because no `commands/tool-time.md` exists in Clavain.

### 9. AGENTS.md Count Discrepancy

**Status: STALE (P1-1)**

In `/root/projects/Clavain/AGENTS.md` line 40, the architecture tree says:
```
│   ├── review/                    # 20 code review agents
```

But the actual count at `/root/projects/Clavain/agents/review/` is 21 files. The prose description at line 125 correctly says "(21)". The tree comment is stale by one agent (likely the most recently added fd-* agent).

### 10. Orphan Analysis

**Status: CLEAN**

No orphan files detected:
- Every command file is in the Quick Reference
- Every skill directory is in the routing table or Cross-AI section
- Every agent is referenced from at least one command, skill, or the flux-drive roster
- No agent files exist outside `agents/{review,research,workflow}/`
- No command files exist outside `commands/`
- No skill directories exist without a SKILL.md

The least-referenced agents are `spec-flow-analyzer` and `learnings-researcher`, each referenced only in the routing table and their own file (no command explicitly dispatches them). However, they are available for general Task tool dispatch via the routing table, so they are not truly orphaned.

## Issues Found

### P1 (Must Fix)

**P1-1: AGENTS.md architecture tree says 20 review agents, actual count is 21.**
File: `/root/projects/Clavain/AGENTS.md`, line 40. The prose at line 125 correctly says 21. Simple fix: change "20" to "21" in the tree comment.

**P1-2: Five fd-* agents missing required `<example>` blocks in description frontmatter.**
Files:
- `/root/projects/Clavain/agents/review/fd-architecture.md`
- `/root/projects/Clavain/agents/review/fd-code-quality.md`
- `/root/projects/Clavain/agents/review/fd-performance.md`
- `/root/projects/Clavain/agents/review/fd-security.md`
- `/root/projects/Clavain/agents/review/fd-user-experience.md`

The AGENTS.md convention at line 119 states: "Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger." All 24 non-fd agents comply; the 5 fd-* agents do not. These agents use a shorter prose description format. Since Claude Code uses the description field for agent discovery and dispatch, the missing examples may reduce dispatch accuracy.

### P2 (Should Fix)

**P2-1: Three commands absent from 3-layer routing tables.**
`compound` (documentation capture), `setup` (modpack bootstrap), and `interpeer` (cross-AI review) appear only in the Quick Reference, not in the Stage/Domain/Language routing tables. This creates a gap in the routing heuristic for users who rely on the structured tables.

**P2-2: Inconsistent agent suffix taxonomy (10 suffixes across 29 agents).**
Review agents use 7 different suffixes (`-reviewer`, `-sentinel`, `-oracle`, `-strategist`, `-specialist`, `-expert`, `-agent`). While creative names are not wrong, they make systematic discovery harder.

**P2-3: Three cross-AI skills (prompterpeer, winterpeer, splinterpeer) lack commands.**
`interpeer` has a command; the other three do not, creating asymmetry in the cross-AI stack.

**P2-4: Phantom `/clavain:tool-time` reference in setup.md.**
File: `/root/projects/Clavain/commands/setup.md`, line 144. `tool-time` is a separate plugin, not a Clavain command.

**P2-5: brainstorm (command) vs brainstorming (skill) naming is counterintuitive.**
The shorter name is the more structured workflow; the longer name is the simpler freeform mode. This inverts natural expectations.

**P2-6: codex-first and clodex-toggle are duplicate commands.**
Both exist to toggle the same flag. `clodex-toggle` is an explicit alias. This inflates the command count from 26 unique to 27.

**P2-7: resolve-parallel and resolve-todo-parallel naming confusion.**
Both involve "resolving TODOs" but from different sources (code comments vs filesystem todo files). The naming does not clearly distinguish the source.

**P2-8: Five fd-* agents absent from using-clavain routing tables.**
The flux-drive Tier 1 agents exist only within the flux-drive skill's internal roster. Users browsing the routing table cannot discover them.

### P3 (Nice to Have)

**P3-1: learnings-researcher is the only agent using `model: haiku`.**
All other 28 agents use `model: inherit`. The haiku choice is justified (grep-based filtering, lightweight task), but the anomaly may surprise future contributors.

## Improvements Suggested

**IMP-1: Add `<example>` blocks to fd-* agents.**
Follow the pattern used by the other 24 agents. Each fd-* agent's description should include 2 `<example>` blocks with `<commentary>` showing when to trigger it, particularly in the context of flux-drive document review.

**IMP-2: Fix AGENTS.md tree comment.**
Change line 40 from `# 20 code review agents` to `# 21 code review agents`.

**IMP-3: Add missing commands to routing tables.**
Add `compound` to the Ship stage, `setup` to the Meta stage, and `interpeer` to the Review stage (or create a dedicated Cross-AI row in Layer 1).

**IMP-4: Document agent suffix rationale or standardize.**
Either add a note in AGENTS.md explaining the naming philosophy (e.g., "suffixes reflect the agent's role archetype, not just their category") or standardize to fewer suffix patterns over time.

**IMP-5: Consider commands for prompterpeer/winterpeer/splinterpeer.**
If these are user-facing skills, adding commands would provide parity with `interpeer`. If they are internal-only, document this distinction.

**IMP-6: Fix the tool-time reference in setup.md.**
Either remove the `/clavain:` prefix or replace the line with the correct plugin namespace.

**IMP-7: Add fd-* agents to routing table or document exclusion.**
Either add a row to Layer 2 (e.g., "Review (codebase-aware)" domain) or add a note explaining these agents are flux-drive-internal and not directly dispatched.

## Overall Assessment

Clavain is a well-structured plugin with strong internal consistency. The component counts (34/29/27) are accurate. All cross-references between commands, skills, and agents resolve to real files. The two P1 issues are straightforward fixes (a stale count comment and missing frontmatter elements on 5 newer agents). The P2 issues primarily reflect organic growth -- naming conventions that were consistent when there were fewer components have drifted as new components were added with different patterns. The routing table completeness gaps affect discoverability but not functionality. Overall, the codebase is clean and would benefit most from the frontmatter standardization (IMP-1) and the routing table updates (IMP-3, IMP-7).
