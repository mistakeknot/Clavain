---
agent: fd-user-experience
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Routing Table Completeness"
    title: "7 of 24 commands are invisible in the using-clavain routing table"
  - id: P0-2
    severity: P0
    section: "Component Count Inconsistencies"
    title: "Counts disagree across CLAUDE.md, AGENTS.md, README.md, plugin.json, and using-clavain"
  - id: P1-1
    severity: P1
    section: "Command Naming Confusions"
    title: "work vs execute-plan: two commands for the same stage with unclear differentiation"
  - id: P1-2
    severity: P1
    section: "Command Naming Confusions"
    title: "Three resolve-* commands with overlapping names and near-identical bodies"
  - id: P1-3
    severity: P1
    section: "Namespace Prefix Errors"
    title: "Commands reference /triage and /resolve-todo-parallel without clavain: prefix"
  - id: P1-4
    severity: P1
    section: "Onboarding and Discovery"
    title: "No progressive disclosure path for new users -- 24 commands presented flat"
  - id: P2-1
    severity: P2
    section: "Argument Hint Formatting"
    title: "Two commands lack argument-hint; two have unquoted YAML values"
  - id: P2-2
    severity: P2
    section: "Routing Table Cognitive Load"
    title: "Routing table mixes skills, commands, and agents in a single wide table hard to scan at 80 columns"
  - id: P2-3
    severity: P2
    section: "Typos in Command Bodies"
    title: "Typo 'liek this' in resolve-parallel and resolve-todo-parallel"
improvements:
  - id: IMP-1
    title: "Add all 24 commands to the routing table or explain why they are excluded"
    section: "Routing Table Completeness"
  - id: IMP-2
    title: "Consolidate resolve-parallel, resolve-pr-parallel, resolve-todo-parallel into one command with a target argument"
    section: "Command Naming Confusions"
  - id: IMP-3
    title: "Add a Quick Start section to the README showing the 5 core commands a new user needs"
    section: "Onboarding and Discovery"
  - id: IMP-4
    title: "Reconcile component counts to a single source of truth with a validation script"
    section: "Component Count Inconsistencies"
  - id: IMP-5
    title: "Differentiate or merge work and execute-plan commands"
    section: "Command Naming Confusions"
verdict: needs-changes
---

### Summary

Clavain's command/skill surface is ambitiously broad (24 commands, 32 skills, 23 agents) and the 3-layer routing table in `using-clavain/SKILL.md` is a strong architectural idea. However, the routing table has significant gaps (7 commands invisible), naming collisions make multiple command pairs confusing (`work` vs `execute-plan`, the three `resolve-*` variants), and component counts disagree across 5 files. A new user who installs the plugin today has no guided onboarding path and faces 24 flat commands with no indication of which 5 matter most. These are fixable issues, and the underlying design is sound.

### Section-by-Section Review

#### 1. Routing Table (`/root/projects/Clavain/skills/using-clavain/SKILL.md`)

The routing table is the single most important UX element in Clavain. It is injected into every session via the SessionStart hook, meaning every Claude Code session begins by reading this content. It needs to be complete and scannable.

**What works well:**
- The 3-layer model (Stage / Domain / Language) is intuitive and maps cleanly to how engineers think about their work.
- The "Red Flags" table on lines 80-94 is unusually effective -- it anticipates rationalizations and addresses them directly.
- The "Key Commands Quick Reference" at lines 121-134 gives a curated subset, which is exactly the kind of progressive disclosure needed.

**What does not work:**
- **7 of 24 commands are completely absent from the routing table.** The missing commands are: `execute-plan`, `codex-first`, `clodex`, `migration-safety`, `agent-native-audit`, `triage`, and `resolve-pr-parallel`. A user (or the agent itself) who needs to triage findings, toggle codex-first mode, or audit agent-native architecture has no way to discover these through the routing table. They only exist in the README.
- The routing table on lines 32-41 uses a wide 4-column markdown table format (Stage | Primary Skills | Primary Commands | Key Agents). At 80 columns -- the standard terminal width -- this table wraps badly. Since this content is injected as system context rather than rendered in a browser, the wrapping degrades readability.
- The table says "Clavain provides 31 skills, 23 agents, and 22 commands" (line 22), but the actual counts are 32 skills, 23 agents, and 24 commands per the filesystem.

#### 2. Command Naming (`/root/projects/Clavain/commands/`)

**Confusingly similar pairs:**

| Pair | Problem |
|------|---------|
| `work` vs `execute-plan` | Both execute plans. `work` is the full-featured 275-line command in the routing table. `execute-plan` is a 2-line delegator to the `executing-plans` skill. Neither command explains when to use one vs the other. |
| `resolve-parallel` vs `resolve-pr-parallel` vs `resolve-todo-parallel` | Three commands with the same `resolve-*-parallel` pattern. `resolve-parallel` resolves TODO comments. `resolve-todo-parallel` resolves file-based todos from `todos/`. `resolve-pr-parallel` resolves PR review comments. The naming does not clearly distinguish "TODO comments in code" from "todo files in todos/ directory" from "PR review threads." |
| `codex-first` vs `clodex` | Identical functionality. `clodex` is a pure alias file that says "follow codex-first command's instructions exactly." Having two entries in the command list for the same function adds noise. |

**Non-obvious names:**
- `lfg` -- "Let's F***ing Go" is memorable but opaque to new users. The description helps ("Full autonomous engineering workflow"), but the name alone communicates nothing about what it does.
- `quality-gates` -- Could be confused with CI/CD quality gates. It is actually "auto-select reviewers for current changes."
- `flux-drive` -- A project-specific name for document review. Without reading the description, a new user would have no idea what this does.

**Good names:**
- `brainstorm`, `review`, `write-plan`, `work`, `changelog`, `learnings`, `triage` -- these are all immediately self-explanatory.

#### 3. Argument Hints

Most commands have well-formatted argument hints in square brackets with clear descriptions. Two inconsistencies:

| File | Issue |
|------|-------|
| `/root/projects/Clavain/commands/heal-skill.md` | `argument-hint: [optional: specific issue to fix]` -- missing outer quotes, making it a YAML bare value |
| `/root/projects/Clavain/commands/create-agent-skill.md` | `argument-hint: [skill description or requirements]` -- same issue, missing quotes |
| `/root/projects/Clavain/commands/write-plan.md` | No `argument-hint` at all (uses `disable-model-invocation: true` instead) |
| `/root/projects/Clavain/commands/execute-plan.md` | No `argument-hint` at all (same pattern) |

For `write-plan` and `execute-plan`, the lack of argument-hint means the user gets no inline guidance about what to pass. Even with `disable-model-invocation`, the hint would still be useful for discovery purposes (e.g., when listing available commands).

#### 4. Onboarding Experience

A new user installs Clavain and starts a session. The SessionStart hook injects `using-clavain` content. This is a good mechanism -- the user does not need to know about the plugin to benefit from it. However:

- The injected content is wrapped in `<EXTREMELY_IMPORTANT>` and `<EXTREMELY-IMPORTANT>` tags (lines 6-12 of `using-clavain/SKILL.md`), which sets an aggressive tone for a first interaction.
- The content is approximately 135 lines of markdown, all injected at once. This is a substantial amount of system context to consume before the user's first message is even processed.
- There is no "Getting Started" or "Try these first" section. The routing table is comprehensive but not welcoming. A new user does not know whether to start with `/clavain:lfg`, `/clavain:brainstorm`, or just type naturally and let skill auto-triggering handle it.
- The README (`/root/projects/Clavain/README.md`) lists all 24 commands in a flat table with no grouping or recommended starting point. There is no "Quick Start" section that says "Try these 3 commands first."

#### 5. Cross-Reference Errors in Command Bodies

Several commands reference other commands without the `clavain:` namespace prefix:

- `/root/projects/Clavain/commands/triage.md` line 206: `/resolve-todo-parallel` (should be `/clavain:resolve-todo-parallel`)
- `/root/projects/Clavain/commands/triage.md` line 299: `/resolve-todo-parallel` (same)
- `/root/projects/Clavain/commands/triage.md` line 307: `/resolve-todo-parallel` (same)
- `/root/projects/Clavain/commands/review.md` line 401: `/triage` (should be `/clavain:triage`)
- `/root/projects/Clavain/commands/review.md` line 408: `/resolve-todo-parallel` (should be `/clavain:resolve-todo-parallel`)

These will cause failures if Claude attempts to invoke them literally. The agent may be smart enough to infer the namespace, but relying on inference rather than explicit references is fragile.

#### 6. Component Count Drift

Component counts are stated in 5 locations and disagree:

| Location | Skills | Agents | Commands |
|----------|--------|--------|----------|
| `/root/projects/Clavain/CLAUDE.md` (line 7) | 32 | 23 | 24 |
| `/root/projects/Clavain/README.md` (line 3) | 32 | 23 | 24 |
| `/root/projects/Clavain/.claude-plugin/plugin.json` (line 4) | 32 | 23 | 24 |
| `/root/projects/Clavain/AGENTS.md` (line 12) | 31 | 23 | 22 |
| `/root/projects/Clavain/skills/using-clavain/SKILL.md` (line 22) | 31 | 23 | 22 |

Actual filesystem counts: 32 skills, 23 agents, 24 commands.

`AGENTS.md` and `using-clavain/SKILL.md` are stale by 1 skill and 2 commands. Since `using-clavain` is the routing table injected into every session, the stale count there means the agent is told there are fewer components than actually exist, potentially causing it to not look for newer additions.

#### 7. Workflow Coherence

The `/clavain:lfg` command defines the flagship workflow: brainstorm -> write-plan -> flux-drive -> work -> review -> resolve-todo-parallel -> quality-gates. This is a well-designed pipeline.

However, several workflow handoffs are incomplete:

- `/clavain:review` (line 401) suggests running `/triage` next, but triage is not in the routing table, so a user following the routing table to discover next steps would not find it.
- `/clavain:triage` (line 307) suggests running `/resolve-todo-parallel` next, creating a review -> triage -> resolve pipeline that works well but is undiscoverable through the routing table.
- `/clavain:work` (line 180-198) suggests creating a PR on a feature branch, but the project's CLAUDE.md explicitly states trunk-based development with no branches. The command body contradicts the project's own conventions.

#### 8. The resolve-* Family

The three `resolve-*` commands share nearly identical structure:

| Command | Source of items | Agent dispatched |
|---------|----------------|-----------------|
| `resolve-parallel` | "Gather the things todo from above" (vague) | `pr-comment-resolver` |
| `resolve-pr-parallel` | `gh pr view` comments | `pr-comment-resolver` |
| `resolve-todo-parallel` | `todos/*.md` files | `pr-comment-resolver` |

All three dispatch `pr-comment-resolver` agents. The bodies of `resolve-parallel` and `resolve-todo-parallel` are near-identical, including the same typo ("liek this" on line 23 and line 25 respectively). The `resolve-parallel` command's description says "Resolve all TODO comments" but its body says "Gather the things todo from above" -- unclear whether "above" means the conversation context, a previous command's output, or something else.

This family would be clearer as a single command with an explicit target argument: `/clavain:resolve [pr|todos|inline]`.

### Issues Found

**P0-1: 7 of 24 commands are invisible in the routing table**
- Location: `/root/projects/Clavain/skills/using-clavain/SKILL.md`, lines 32-41 and 121-134
- Missing: `execute-plan`, `codex-first`, `clodex`, `migration-safety`, `agent-native-audit`, `triage`, `resolve-pr-parallel`
- Impact: The routing table is the primary discovery mechanism (injected every session). Commands not listed there are effectively hidden from both the agent and the user. `triage` and `migration-safety` are particularly important omissions since they are referenced by other commands (`review` references `triage`).
- Fix: Add the 7 missing commands to the appropriate Stage rows. `migration-safety` belongs in Data domain. `triage` and `resolve-pr-parallel` belong in Review/Execute stages. `codex-first`/`clodex` belong in Meta. `agent-native-audit` belongs in Review. `execute-plan` should either be added to Execute or deprecated in favor of `work`.

**P0-2: Component counts disagree across 5 files**
- Locations: `CLAUDE.md:7`, `README.md:3`, `plugin.json:4`, `AGENTS.md:12`, `using-clavain/SKILL.md:22`
- Three files say 32/23/24, two files say 31/23/22. The filesystem has 32/23/24.
- Fix: Update `AGENTS.md` line 12 and `using-clavain/SKILL.md` line 22 to match actual counts (32 skills, 24 commands). Better: add a validation step to the existing validation checklist in `AGENTS.md` lines 162-173 that compares stated counts against `ls | wc -l` output.

**P1-1: work vs execute-plan confusion**
- Location: `/root/projects/Clavain/commands/work.md` and `/root/projects/Clavain/commands/execute-plan.md`
- Both are for the "Execute" stage. `work` is a 275-line comprehensive command. `execute-plan` is a 2-line skill delegator. The routing table only lists `work`. A user who guesses `/clavain:execute-plan` gets a different (simpler) experience than `/clavain:work` with no explanation of why.
- Fix: Either deprecate `execute-plan` (since `work` subsumes it), or clearly document in both commands when to use which. If kept, `execute-plan` should explain "Use this for batch execution with review checkpoints. For full-featured execution, use `/clavain:work`."

**P1-2: Three near-identical resolve-* commands**
- Location: `/root/projects/Clavain/commands/resolve-parallel.md`, `resolve-pr-parallel.md`, `resolve-todo-parallel.md`
- The names differ only in the middle segment (`pr`, `todo`, or nothing). `resolve-parallel` vs `resolve-todo-parallel` is particularly confusing because both resolve "TODOs" but from different sources.
- Fix: Consider consolidating into `/clavain:resolve [pr|todos|inline]` or at minimum rename `resolve-parallel` to `resolve-inline-parallel` to clarify that it operates on inline TODO comments.

**P1-3: Missing clavain: namespace prefix in cross-references**
- Location: `/root/projects/Clavain/commands/triage.md` (lines 206, 299, 307), `/root/projects/Clavain/commands/review.md` (lines 401, 408)
- References use `/triage` and `/resolve-todo-parallel` instead of `/clavain:triage` and `/clavain:resolve-todo-parallel`.
- Fix: Add `clavain:` prefix to all 5 occurrences.

**P1-4: No progressive disclosure for new users**
- Location: `/root/projects/Clavain/README.md` and `/root/projects/Clavain/skills/using-clavain/SKILL.md`
- The README lists 24 commands flat. The routing table is comprehensive but not welcoming. There is no "start here" guidance.
- Fix: Add a "Quick Start" section to the README before the full commands table. Example: "New to Clavain? Start with `/clavain:brainstorm` to explore an idea, `/clavain:write-plan` to plan it, `/clavain:work` to build it, `/clavain:review` to check it. Or just use `/clavain:lfg` to do all of the above automatically."

**P2-1: Argument hint formatting inconsistencies**
- Location: `/root/projects/Clavain/commands/heal-skill.md` line 4, `/root/projects/Clavain/commands/create-agent-skill.md` line 5
- Values are unquoted YAML, which works but is inconsistent with the 20 other commands that use quoted strings. `write-plan` and `execute-plan` lack argument-hint entirely.
- Fix: Quote the two bare values. Add argument-hints to `write-plan` and `execute-plan` (e.g., `"[specification or feature description]"` and `"[plan file path]"`).

**P2-2: Routing table readability at 80 columns**
- Location: `/root/projects/Clavain/skills/using-clavain/SKILL.md`, lines 32-41
- The 4-column table (Stage | Primary Skills | Primary Commands | Key Agents) contains cells with comma-separated lists of 4-5 items. At 80 columns this wraps and becomes hard to scan.
- Fix: Since this is consumed as system context (not rendered HTML), consider restructuring as nested lists or separate tables per stage. Alternatively, keep the table but truncate each cell to the top 2-3 items with "..." indicating more exist.

**P2-3: Typo in command bodies**
- Location: `/root/projects/Clavain/commands/resolve-parallel.md` line 23, `/root/projects/Clavain/commands/resolve-todo-parallel.md` line 25
- Both contain "liek this" (should be "like this").
- Fix: Correct the typo in both files.

### Improvements Suggested

**IMP-1: Complete the routing table**
Add all 24 commands to the routing table in `/root/projects/Clavain/skills/using-clavain/SKILL.md`. The 7 missing commands should map as follows:
- `execute-plan` -> Execute stage (or deprecate in favor of `work`)
- `codex-first` / `clodex` -> Meta stage (or a new "Mode" category)
- `migration-safety` -> Data domain in Layer 2
- `agent-native-audit` -> Review stage or Meta stage
- `triage` -> Review stage (post-review workflow)
- `resolve-pr-parallel` -> Execute stage (alongside the other resolve-* commands)

**IMP-2: Consolidate the resolve-* commands**
Replace `resolve-parallel`, `resolve-pr-parallel`, and `resolve-todo-parallel` with a single `/clavain:resolve` command that accepts a target argument:
- `/clavain:resolve pr` -- resolve PR review comments
- `/clavain:resolve todos` -- resolve file-based todos from `todos/`
- `/clavain:resolve inline` -- resolve inline TODO comments in code
This reduces the command count from 24 to 22, decreases cognitive load, and eliminates the confusing naming overlap.

**IMP-3: Add a Quick Start section to the README**
Before the full "Commands (24)" table in `/root/projects/Clavain/README.md`, add a focused section:
```
## Quick Start

New to Clavain? These 5 commands cover 90% of workflows:

| Command | When to use |
|---------|-------------|
| /clavain:lfg [feature] | Full autonomous workflow (does everything below) |
| /clavain:brainstorm [idea] | Explore before planning |
| /clavain:write-plan [spec] | Create implementation plan |
| /clavain:work [plan] | Execute a plan |
| /clavain:review [PR] | Multi-agent code review |

Everything else is specialized. See the full list below.
```

**IMP-4: Reconcile component counts with a validation check**
Add a count-validation step to the existing validation script in `/root/projects/Clavain/AGENTS.md` (lines 176-194) that checks stated counts against filesystem counts:
```bash
# Validate stated counts match reality
SKILL_COUNT=$(ls skills/*/SKILL.md | wc -l)
CMD_COUNT=$(ls commands/*.md | wc -l)
AGENT_COUNT=$(ls agents/{review,research,workflow}/*.md | wc -l)
echo "Actual: $SKILL_COUNT skills, $AGENT_COUNT agents, $CMD_COUNT commands"
# Compare against CLAUDE.md, README.md, plugin.json, AGENTS.md, using-clavain/SKILL.md
```
This prevents future drift as new components are added.

**IMP-5: Clarify or merge work and execute-plan**
Either:
- (a) Deprecate `execute-plan` by having it print "Use `/clavain:work` instead" and redirect, or
- (b) Differentiate them clearly: `execute-plan` for batch execution with review checkpoints (the `executing-plans` skill), `work` for full-featured execution with incremental commits and PR creation.

If option (b), add a "See also" line to both commands pointing to each other with a one-line explanation of the difference. Also add `execute-plan` to the routing table.

### Overall Assessment

**Verdict: needs-changes**

The routing architecture is strong and the command pipeline (brainstorm -> plan -> work -> review -> triage -> resolve) is well-designed. The core problem is that the discovery surface has gaps: 7 commands missing from the routing table, confusing name pairs, and stale counts. These are all fixable without changing the underlying architecture.

**Top 3 changes for better user experience:**

1. **Complete the routing table** (P0-1). The using-clavain routing table is the sole discovery mechanism for most users. Every command must appear there or be explicitly documented as internal/deprecated. This is the single highest-impact fix.

2. **Consolidate the resolve-* commands** (IMP-2 / P1-2). Reducing 3 confusingly-named commands to 1 with a target argument removes naming confusion and lowers the command count, making the full list less daunting.

3. **Add Quick Start guidance** (IMP-3 / P1-4). A 5-command "start here" section in both the README and the using-clavain routing table gives new users a clear on-ramp without requiring them to read and understand all 24 commands before starting work.
