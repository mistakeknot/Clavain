---
agent: fd-architecture
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Hook System"
    title: "Hook count mismatch: documentation says 2 hooks but 3 scripts registered across 2 events"
  - id: P0-2
    severity: P0
    section: "Hook System"
    title: "AGENTS.md falsely claims 'Currently only SessionStart hook' -- SessionEnd hook exists"
  - id: P1-1
    severity: P1
    section: "Hook System"
    title: "agent-mail-register.sh and dotfiles-sync.sh completely undocumented in README/AGENTS.md"
  - id: P1-2
    severity: P1
    section: "Cross-References"
    title: "review.md references stale path .claude/skills/file-todos/assets/todo-template.md"
  - id: P1-3
    severity: P1
    section: "Upstream Sync"
    title: "AGENTS.md references nonexistent scripts/sync-upstreams.sh"
  - id: P2-1
    severity: P2
    section: "Cross-References"
    title: "3 command files reference sibling commands without clavain: namespace prefix"
  - id: P2-2
    severity: P2
    section: "Architecture Diagrams"
    title: "Architecture tree in AGENTS.md and README.md omit agent-mail-register.sh and dotfiles-sync.sh"
  - id: P2-3
    severity: P2
    section: "Validation"
    title: "Validation scripts in CLAUDE.md and AGENTS.md only syntax-check session-start.sh, not all 3 hook scripts"
improvements:
  - id: IMP-1
    title: "Add Commands column to Layer 2 routing table"
    section: "Routing Table"
  - id: IMP-2
    title: "Standardize hook counting terminology across documentation"
    section: "Component Counts"
  - id: IMP-3
    title: "Add hook count to plugin.json description string"
    section: "Component Counts"
verdict: needs-changes
---

# Architecture Review: Clavain Plugin Post-Cleanup Validation

## Summary

The prior cleanup (13 issues fixed) was effective at removing stale namespace references, correcting component counts, and purging Rails/Ruby content. The core counts (32 skills, 23 agents, 24 commands) are accurate and consistent across all surfaces. The routing table in `using-clavain/SKILL.md` accounts for all 32 skills and all 23 agents. No phantom `superpowers:` or `compound-engineering:` references remain in active code.

However, the cleanup missed the hook system entirely. Two hooks were added after the initial documentation was written (`agent-mail-register.sh` for Agent Mail auto-registration, `dotfiles-sync.sh` for SessionEnd dotfiles sync), and documentation was never updated to reflect them. This creates a systemic inconsistency where every documentation surface says "2 hooks" but the actual hook system has 3 scripts across 2 events. Additionally, `scripts/sync-upstreams.sh` is referenced in AGENTS.md but does not exist on disk, and the `review.md` command contains stale `.claude/skills/` path references from the pre-plugin era.

**Overall: 8 issues found (2 P0, 3 P1, 3 P2), 3 improvements suggested.**

---

## Section-by-Section Review

### 1. Hook System

**Files examined:**
- `/root/projects/Clavain/hooks/hooks.json` (hook registration)
- `/root/projects/Clavain/hooks/session-start.sh` (context injection)
- `/root/projects/Clavain/hooks/agent-mail-register.sh` (Agent Mail registration)
- `/root/projects/Clavain/hooks/dotfiles-sync.sh` (SessionEnd dotfiles sync)
- `/root/projects/Clavain/AGENTS.md` lines 38-40, 126-131
- `/root/projects/Clavain/README.md` lines 99-101, 119-121

**Actual state on disk:**

`hooks/hooks.json` registers 3 hook scripts across 2 events:

| Event | Script | Purpose |
|-------|--------|---------|
| SessionStart | `session-start.sh` | Injects using-clavain SKILL.md + upstream staleness warning |
| SessionStart | `agent-mail-register.sh` | Auto-registers with MCP Agent Mail, injects agent identity |
| SessionEnd | `dotfiles-sync.sh` | Syncs dotfiles to GitHub via external script |

**Documentation state:**

Every documentation surface says "2 hooks" and only describes the SessionStart/session-start.sh hook:

- `CLAUDE.md` line 7: "2 hooks"
- `AGENTS.md` line 12: "2 hooks"
- `AGENTS.md` line 39: architecture tree only shows `hooks.json` and `session-start.sh`
- `AGENTS.md` line 128: "Currently only `SessionStart` hook"
- `README.md` line 3: "2 hooks"
- `README.md` line 99: "### Hooks (2)" -- lists only SessionStart bullet
- `README.md` lines 119-121: architecture tree only shows `hooks.json` and `session-start.sh`
- `plugin.json` line 4: description says "2 MCP servers" (no hook count, which is fine)

The fundamental question: what counts as a "hook"? Options:

1. **Events** (2): SessionStart, SessionEnd -- this is how Claude Code's hook system is structured
2. **Scripts** (3): session-start.sh, agent-mail-register.sh, dotfiles-sync.sh -- this is what's registered
3. **Entries in hooks.json** (2): the SessionStart array and SessionEnd array

The current documentation says "2 hooks" which could be interpreted as "2 hook events." But `README.md` line 99-101 says "Hooks (2)" then only lists one bullet point (SessionStart), which is clearly wrong regardless of counting methodology -- there's also a SessionEnd event.

### 2. Component Counts

**Files examined:**
- `/root/projects/Clavain/CLAUDE.md` line 7
- `/root/projects/Clavain/AGENTS.md` line 12
- `/root/projects/Clavain/README.md` line 3
- `/root/projects/Clavain/.claude-plugin/plugin.json` line 4
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 22

**Verification results:**

| Component | Documented Count | Actual Count | Match? |
|-----------|-----------------|--------------|--------|
| Skills | 32 | 32 | YES |
| Agents | 23 | 23 | YES |
| Commands | 24 | 24 | YES |
| Hooks | 2 | 3 scripts / 2 events | AMBIGUOUS |
| MCP Servers | 2 | 2 | YES |

All surfaces (CLAUDE.md, AGENTS.md, README.md, plugin.json, using-clavain/SKILL.md) agree on 32/23/24. The cleanup correctly fixed these counts. The hook count is the only inconsistency.

### 3. Routing Table Completeness

**File examined:** `/root/projects/Clavain/skills/using-clavain/SKILL.md`

**Skills coverage (32 total):**

All 32 skills appear in either Layer 1 or Layer 2 routing tables:
- Layer 1 (Stage): 17 skills mapped across Explore/Plan/Review(docs)/Execute/Debug/Review/Ship/Meta
- Layer 2 (Domain): 14 additional skills mapped across Code/Data/Deploy/Docs/Research/Workflow/Design/Infra
- `using-clavain` is the routing table itself, correctly excluded from its own table

All 32 accounted for. No phantom skills referenced in routing that don't exist on disk.

**Agents coverage (23 total):**

All 23 agents appear in Layer 1, Layer 2, or Layer 3 routing tables. Cross-referencing against the full agent list from disk:

- review/architecture-strategist.md -- Layer 1 (Plan)
- review/code-simplicity-reviewer.md -- Layer 1 (Review), Layer 2 (Code)
- review/pattern-recognition-specialist.md -- Layer 2 (Code)
- review/performance-oracle.md -- Layer 1 (Review), Layer 3
- review/security-sentinel.md -- Layer 1 (Review), Layer 3
- review/agent-native-reviewer.md -- Layer 2 (Code)
- review/kieran-go-reviewer.md -- Layer 1 (Review), Layer 3
- review/kieran-python-reviewer.md -- Layer 1 (Review), Layer 3
- review/kieran-typescript-reviewer.md -- Layer 1 (Review), Layer 3
- review/kieran-shell-reviewer.md -- Layer 1 (Review), Layer 3
- review/concurrency-reviewer.md -- Layer 1 (Review), Layer 3
- review/plan-reviewer.md -- Layer 1 (Review)
- review/data-integrity-reviewer.md -- Layer 2 (Data)
- review/data-migration-expert.md -- Layer 2 (Data)
- review/deployment-verification-agent.md -- Layer 1 (Ship), Layer 2 (Deploy)
- research/best-practices-researcher.md -- Layer 1 (Explore), Layer 2 (Research)
- research/framework-docs-researcher.md -- Layer 2 (Docs)
- research/git-history-analyzer.md -- Layer 1 (Debug), Layer 2 (Research)
- research/learnings-researcher.md -- Layer 2 (Docs)
- research/repo-research-analyst.md -- Layer 1 (Explore), Layer 2 (Research)
- workflow/bug-reproduction-validator.md -- Layer 1 (Debug)
- workflow/pr-comment-resolver.md -- Layer 2 (Workflow)
- workflow/spec-flow-analyzer.md -- Layer 1 (Plan)

All 23 accounted for.

**Commands coverage (24 total):**

Layer 1 maps most commands. Layer 2 does not have a Commands column (by design -- it only has Skills and Agents). The Key Commands Quick Reference at the bottom of using-clavain/SKILL.md lists 12 frequently-used commands.

Commands in Layer 1 routing: brainstorm, write-plan, plan-review, flux-drive, work, execute-plan, lfg, resolve-parallel, resolve-todo-parallel, resolve-pr-parallel, codex-first, clodex, repro-first-debugging, review, quality-gates, migration-safety, agent-native-audit, changelog, triage, create-agent-skill, generate-command, heal-skill, upstream-sync (23 commands)

Missing from Layer 1 routing: **learnings** (1 command). The `learnings` command appears only in the Key Commands Quick Reference (line 135) but is not mapped in any routing table row. It logically belongs in the "Ship" stage (Layer 1) or the "Docs" domain (Layer 2).

### 4. Cross-References

**Stale path references in review.md:**

`/root/projects/Clavain/commands/review.md` references `.claude/skills/file-todos/assets/todo-template.md` three times (lines 240, 288, 308). This path is from the pre-plugin era when skills were installed into `~/.claude/skills/`. In the plugin architecture, the correct path would be relative to the plugin root: `skills/file-todos/assets/todo-template.md` (or accessed via `${CLAUDE_PLUGIN_ROOT}/skills/file-todos/assets/todo-template.md`).

The file exists at `/root/projects/Clavain/skills/file-todos/assets/todo-template.md`.

**Missing namespace prefix in command cross-references:**

Three instances where commands reference sibling Clavain commands without the `clavain:` prefix:

1. `/root/projects/Clavain/commands/review.md` line 401: `/triage` should be `/clavain:triage`
2. `/root/projects/Clavain/commands/review.md` line 408: `/resolve-todo-parallel` should be `/clavain:resolve-todo-parallel`
3. `/root/projects/Clavain/commands/triage.md` line 206: `/resolve-todo-parallel` should be `/clavain:resolve-todo-parallel`

Note: `triage.md` lines 299 and 307 also reference `/resolve-todo-parallel` without prefix, but these appear in descriptive/commentary text rather than as actionable command invocations.

### 5. Upstream Sync

**File examined:** `/root/projects/Clavain/upstreams.json`

**File mapping verification:**

All 4 upstream entries in `upstreams.json` have valid file mappings. Every target path in the `fileMap` objects was verified to exist on disk:

- `superpowers` (25 file mappings) -- all targets exist
- `superpowers-lab` (4 file mappings) -- all targets exist
- `superpowers-dev` (7 file mappings, including glob) -- all targets exist
- `compound-engineering` (35 file mappings, including globs) -- all targets exist

The `superpowers` upstream correctly maps `using-superpowers/SKILL.md` to `using-clavain/SKILL.md` (namespace rename) and `agents/code-reviewer.md` to `agents/review/plan-reviewer.md` (restructured path). The `compound-engineering` upstream correctly maps `data-integrity-guardian.md` to `data-integrity-reviewer.md` (local rename).

**Check system vs sync system:**

The check system (`scripts/upstream-check.sh`) tracks 7 upstream repos. The sync system (`upstreams.json`) tracks 4 upstream repos with file mappings. The 3 difference (beads, oracle, mcp_agent_mail) are upstream tools whose skills were written locally in Clavain rather than imported from upstream repos. This is correct and expected.

**Missing script reference:**

`/root/projects/Clavain/AGENTS.md` line 241 references `bash scripts/sync-upstreams.sh` for "full auto-merge locally." This file does not exist. Only `scripts/upstream-check.sh` exists in the scripts directory. The sync system is driven by `.github/workflows/sync.yml` (GitHub Action) rather than a local script. According to project memory, `scripts/sync-upstreams.sh` was intended as a "local runner" but may have been removed or never created.

### 6. Architecture Diagrams

Both AGENTS.md (lines 17-48) and README.md (lines 110-129) show directory tree diagrams for the hooks directory that only list:

```
hooks/
    hooks.json
    session-start.sh
```

The actual contents of the hooks directory are:

```
hooks/
    hooks.json
    session-start.sh
    agent-mail-register.sh
    dotfiles-sync.sh
```

### 7. Validation Scripts

The validation checklist in AGENTS.md (line 169) and quick validation script (line 190) only check `session-start.sh`:

```bash
bash -n hooks/session-start.sh && echo "Hook script OK"
```

Similarly, CLAUDE.md (line 19) only checks:

```bash
bash -n hooks/session-start.sh        # Syntax check
```

Neither checks `agent-mail-register.sh` or `dotfiles-sync.sh` for syntax validity.

### 8. Plugin.json

No issues found. The manifest correctly declares 2 MCP servers (context7, mcp-agent-mail), has valid JSON, and the description accurately lists component counts (minus hooks, which plugin.json doesn't mention -- acceptable since hooks are registered in hooks.json, not plugin.json).

---

## Issues Found

### P0-1: Hook count mismatch across all documentation surfaces

**Location:** CLAUDE.md line 7, AGENTS.md line 12, README.md lines 3 and 99, hooks/hooks.json

**Problem:** Every documentation file says "2 hooks" but `hooks/hooks.json` registers 3 hook scripts (session-start.sh, agent-mail-register.sh, dotfiles-sync.sh) across 2 events (SessionStart, SessionEnd). The README says "Hooks (2)" but only lists 1 bullet point -- it doesn't even document the SessionEnd event, let alone the agent-mail-register SessionStart hook. This is a factual error regardless of counting methodology.

**Suggestion:** Decide on counting methodology (recommend counting scripts, i.e. "3 hooks"), then update:
1. `CLAUDE.md` line 7: "32 skills, 23 agents, 24 commands, **3 hooks**, 2 MCP servers"
2. `AGENTS.md` line 12: same
3. `README.md` line 3: same
4. `README.md` lines 99-101: "### Hooks (3)" with 3 bullet points
5. `plugin.json` line 4: optionally add ", 3 hooks" to description

### P0-2: AGENTS.md falsely states "Currently only SessionStart hook"

**Location:** `/root/projects/Clavain/AGENTS.md` line 128

**Problem:** Line 128 reads "Currently only `SessionStart` hook (matcher: `startup|resume|clear|compact`)". This is factually false -- hooks.json also registers a SessionEnd hook (dotfiles-sync.sh). Line 129 says "session-start.sh does two things" which is accurate for that script but the section omits the other two scripts entirely.

**Suggestion:** Rewrite the Hooks section (lines 126-131) to document all 3 hooks:
- SessionStart: session-start.sh (context injection + staleness warning)
- SessionStart: agent-mail-register.sh (Agent Mail auto-registration, graceful no-op if server not running)
- SessionEnd: dotfiles-sync.sh (sync dotfiles to GitHub, graceful no-op if sync script missing)

### P1-1: agent-mail-register.sh and dotfiles-sync.sh completely undocumented

**Location:** `/root/projects/Clavain/README.md` lines 99-101, `/root/projects/Clavain/AGENTS.md` lines 126-131

**Problem:** Two functional hook scripts have no documentation anywhere:
- `agent-mail-register.sh`: 114 lines, calls MCP Agent Mail's `macro_start_session`, injects agent identity into session context. Non-trivial script with JSON-RPC calls, response parsing, and error handling.
- `dotfiles-sync.sh`: 25 lines, runs an external dotfiles sync script. Simple but undocumented.

**Suggestion:** Add documentation for both in AGENTS.md's Hooks section and README.md's Hooks section. Key details to document:
- `agent-mail-register.sh`: depends on Agent Mail MCP server being configured in plugin.json, gracefully no-ops with 2s timeout, injects agent name and inbox status
- `dotfiles-sync.sh`: depends on external `/root/projects/dotfiles-sync/sync-dotfiles.sh`, runs async at session end, logs to `/var/log/dotfiles-sync.log`

### P1-2: review.md references stale .claude/skills/ path

**Location:** `/root/projects/Clavain/commands/review.md` lines 240, 288, 308

**Problem:** Three references to `.claude/skills/file-todos/assets/todo-template.md` use the old pre-plugin path format. In the plugin architecture, skills live under the plugin root, not `~/.claude/skills/`. The correct way to reference this within a plugin command is either the skill name (`file-todos`) or the plugin-relative path (`skills/file-todos/assets/todo-template.md`).

**Suggestion:** Replace all 3 instances with the skill invocation pattern already established in the codebase. Instead of hardcoding a path, instruct the agent to invoke the `file-todos` skill which already knows its own template location. If a path is needed, use `${CLAUDE_PLUGIN_ROOT}/skills/file-todos/assets/todo-template.md`.

### P1-3: AGENTS.md references nonexistent scripts/sync-upstreams.sh

**Location:** `/root/projects/Clavain/AGENTS.md` line 241

**Problem:** The "Manual sync check" section references `bash scripts/sync-upstreams.sh` for "full auto-merge locally" but this script does not exist. Only `scripts/upstream-check.sh` exists. The sync system is driven by `.github/workflows/sync.yml` (GitHub Action), not a local script.

**Suggestion:** Either:
1. Remove the reference to `scripts/sync-upstreams.sh` and replace with the actual way to trigger sync locally (if one exists), or
2. Create the script if local sync is a desired capability, or
3. Replace with instructions to manually trigger the GitHub Action: `gh workflow run sync.yml`

### P2-1: Commands reference sibling commands without clavain: prefix

**Location:** `/root/projects/Clavain/commands/review.md` lines 401, 408; `/root/projects/Clavain/commands/triage.md` line 206

**Problem:** Three actionable command references use bare names (`/triage`, `/resolve-todo-parallel`) instead of namespaced names (`/clavain:triage`, `/clavain:resolve-todo-parallel`). In the plugin system, commands must be invoked with the namespace prefix.

**Suggestion:** Update all 3 instances to use the `clavain:` prefix. Also grep for any other bare command references across all commands:
- `review.md:401`: `/triage` -> `/clavain:triage`
- `review.md:408`: `/resolve-todo-parallel` -> `/clavain:resolve-todo-parallel`
- `triage.md:206`: `/resolve-todo-parallel` -> `/clavain:resolve-todo-parallel`

### P2-2: Architecture diagrams omit 2 of 3 hook scripts

**Location:** `/root/projects/Clavain/AGENTS.md` lines 38-40, `/root/projects/Clavain/README.md` lines 119-121

**Problem:** Both architecture tree diagrams show only `hooks.json` and `session-start.sh` under the hooks directory. The actual directory also contains `agent-mail-register.sh` and `dotfiles-sync.sh`.

**Suggestion:** Update both diagrams to show all files:
```
hooks/
    hooks.json                 # Hook registration (SessionStart + SessionEnd)
    session-start.sh           # Context injection + upstream staleness warning
    agent-mail-register.sh     # Agent Mail auto-registration
    dotfiles-sync.sh           # SessionEnd dotfiles sync
```

### P2-3: Validation scripts only check 1 of 3 hook scripts

**Location:** `/root/projects/Clavain/CLAUDE.md` line 19, `/root/projects/Clavain/AGENTS.md` lines 169, 190

**Problem:** Validation commands only syntax-check `session-start.sh`. If `agent-mail-register.sh` or `dotfiles-sync.sh` develop syntax errors, they won't be caught by the documented validation process.

**Suggestion:** Extend validation to cover all hook scripts:
```bash
bash -n hooks/session-start.sh && echo "session-start OK"
bash -n hooks/agent-mail-register.sh && echo "agent-mail-register OK"
bash -n hooks/dotfiles-sync.sh && echo "dotfiles-sync OK"
```

---

## Improvements Suggested

### IMP-1: Add Commands column to Layer 2 routing table

**Location:** `/root/projects/Clavain/skills/using-clavain/SKILL.md` lines 45-54

**Current state:** Layer 2 has only Skills and Agents columns. The `learnings` command is the only command not mapped in any routing table (Layer 1 or Layer 2). It only appears in the Key Commands Quick Reference.

**Suggestion:** Either add a Commands column to Layer 2 or add `learnings` to the Ship row in Layer 1. The simpler fix is adding `learnings` to Layer 1's Ship row:
```
| **Ship** | landing-a-change, verification-before-completion | changelog, triage, learnings | deployment-verification-agent |
```

### IMP-2: Standardize hook counting terminology

**Location:** All documentation surfaces

**Current state:** "2 hooks" is ambiguous -- could mean 2 events or 2 scripts (actually 3 scripts). Different readers will interpret "hooks" differently.

**Suggestion:** Use "3 hooks (2 events)" or explicitly state "3 hook scripts" to be unambiguous. The plugin has 3 distinct behaviors triggered by hooks, which is the most useful count for users.

### IMP-3: Add hook count to plugin.json description

**Location:** `/root/projects/Clavain/.claude-plugin/plugin.json` line 4

**Current state:** Description mentions "23 agents, 24 commands, 32 skills, 2 MCP servers" but omits hooks.

**Suggestion:** Add hook count for completeness: "23 agents, 24 commands, 32 skills, 3 hooks, 2 MCP servers". This makes plugin.json consistent with all other documentation surfaces.

---

## Overall Assessment

**Verdict: needs-changes**

The prior cleanup was thorough for its scope (namespace migration, count corrections, Rails content removal), but the hook system was a blind spot. The 3 issues cluster around a single root cause: two hook scripts (`agent-mail-register.sh` and `dotfiles-sync.sh`) were added without corresponding documentation updates. This is a common pattern -- the code works correctly, but documentation drifted.

**Top 3 changes to make:**

1. **Document all 3 hooks** (addresses P0-1, P0-2, P1-1, P2-2, P2-3): Update hook count in all 5 documentation surfaces, rewrite AGENTS.md hooks section to describe all 3 scripts, update architecture diagrams, extend validation scripts. This is one coherent change that resolves 5 of 8 issues.

2. **Fix stale paths in review.md** (addresses P1-2): Replace `.claude/skills/file-todos/assets/todo-template.md` with plugin-relative path or skill invocation. 3 lines to change.

3. **Fix or remove sync-upstreams.sh reference** (addresses P1-3): Either create the script or update AGENTS.md line 241 to reflect the actual sync mechanism. 1 line to change.

The P2 issues (namespace prefixes, architecture diagrams, validation scripts) are lower priority but should be fixed alongside the P0/P1 changes since they're all part of the same documentation drift pattern.
