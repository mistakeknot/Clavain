---
agent: fd-architecture
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Architecture Tree"
    title: "AGENTS.md and README.md architecture trees say '20 code review agents' but there are 21 on disk (rust-reviewer)"
  - id: P0-2
    severity: P0
    section: "Component Counts"
    title: "CLAUDE.md validation comment says 'Should be 28' agents but actual count is 29 (21+5+3)"
  - id: P1-1
    severity: P1
    section: "Component Counts"
    title: "Review agent count inconsistent across 5 surfaces: 15, 20, and 21 used interchangeably"
  - id: P1-2
    severity: P1
    section: "Component Counts"
    title: "CLAUDE.md language-specific reviewers list omits Rust despite rust-reviewer.md existing on disk"
  - id: P1-3
    severity: P1
    section: "Architecture Tree"
    title: "AGENTS.md scripts/ tree shows only upstream-check.sh; missing dispatch.sh, debate.sh, install-codex.sh, upstream-impact-report.py"
  - id: P1-4
    severity: P1
    section: "Architecture Tree"
    title: "AGENTS.md and README.md .github/workflows/ trees are incomplete vs 8 actual workflow files on disk"
  - id: P1-5
    severity: P1
    section: "Flux Drive Roster"
    title: "README.md says flux-drive pulls from 'a roster of 28 agents across 4 tiers' but fixed roster is 19 (5 T1 + 13 T3 + 1 T4)"
  - id: P2-1
    severity: P2
    section: "Hook Registration"
    title: "SessionEnd hook entry in hooks.json lacks matcher field (all other entries have one)"
  - id: P2-2
    severity: P2
    section: "Plugin Audit"
    title: "Three different review agent counts in conflict tables: AGENTS.md says 15, README.md says 20, docs/plugin-audit.md says 15"
improvements:
  - id: IMP-1
    title: "Standardize review agent count to 21 across all documentation surfaces"
    section: "Component Counts"
  - id: IMP-2
    title: "Update AGENTS.md and README.md architecture trees to reflect actual scripts/ and .github/workflows/ contents"
    section: "Architecture Tree"
  - id: IMP-3
    title: "Add Rust to CLAUDE.md language-specific reviewers list"
    section: "Design Decisions"
  - id: IMP-4
    title: "Correct flux-drive roster claim in README from 28 to actual count (19 fixed + dynamic Tier 2)"
    section: "Flux Drive Roster"
  - id: IMP-5
    title: "Add single-source-of-truth mechanism for component counts to prevent future drift"
    section: "Validation"
verdict: needs-changes
---

## Summary

The Clavain repo is architecturally sound -- the 3-layer routing, hook wiring, MCP server configuration, upstream sync system, and pipeline coherence are all well-designed and functionally correct. The primary issues are documentation drift: component counts have diverged across 8+ documentation surfaces as components were added (notably rust-reviewer). The architecture trees in AGENTS.md and README.md are stale relative to actual disk contents in `scripts/` and `.github/workflows/`. No wiring bugs or broken references were found -- all hooks.json entries point to scripts that exist, all MCP servers are correctly configured, and the `/lfg` pipeline steps reference real commands and skills.

## Section-by-Section Review

### Component Count Consistency

There are 8 surfaces that declare component counts. The table below shows the actual state:

| Surface | Skills | Agents | Review Agents (sub) | Commands | Hooks | MCP Servers |
|---------|--------|--------|---------------------|----------|-------|-------------|
| **Actual on disk** | **34** | **29** | **21** | **27** | **3 events, 4 scripts** | **3** |
| CLAUDE.md line 7 | 34 | 29 | -- | 27 | 3 | 3 |
| CLAUDE.md line 17 (comment) | 34 | **28** | -- | 27 | -- | -- |
| AGENTS.md line 12 | 34 | 29 | -- | 27 | 3 | 3 |
| AGENTS.md line 40 (tree) | 34 | -- | **20** | 27 | -- | -- |
| AGENTS.md line 125 | -- | -- | 21 | -- | -- | -- |
| AGENTS.md line 275 | -- | -- | **15** | -- | -- | -- |
| README.md line 7 | 34 | 29 | -- | 27 | 3 | 3 |
| README.md line 58 | -- | -- | **28** (flux roster) | -- | -- | -- |
| README.md line 152 | -- | 29 | 21 | -- | -- | -- |
| README.md line 234 | -- | -- | **20** | -- | -- | -- |
| README.md line 259 (tree) | -- | -- | **20** | -- | -- | -- |
| plugin.json line 4 | 34 | 29 | -- | 27 | -- | 3 |
| using-clavain SKILL.md line 24 | 34 | 29 | -- | 27 | -- | -- |
| docs/plugin-audit.md line 21 | -- | -- | **15** | -- | -- | -- |

**Findings:**

1. **Architecture tree comment "20 code review agents"** appears in AGENTS.md line 40 and README.md line 259. The actual count is 21 -- `rust-reviewer.md` exists in `agents/review/` but was not accounted for in these tree comments. The Quick Reference table in AGENTS.md (line 125) and the README body text (line 152) were both correctly updated to say 21, but the tree comments were missed.

2. **CLAUDE.md validation comment says "Should be 28"** (line 17: `ls agents/{review,research,workflow}/*.md | wc -l  # Should be 28`). The actual count is 29: 21 review + 5 research + 3 workflow. This was likely correct before rust-reviewer was added.

3. **Review agent count in conflict tables**: AGENTS.md line 275 says "15 review agents" and `docs/plugin-audit.md` line 21 says the same. README.md line 234 says "20 review agents". The actual count is 21. These are references to how many review agents Clavain provides as a replacement for the `code-review` plugin. The numbers 15 and 20 likely reflect older states of the repo.

4. **CLAUDE.md Design Decisions line 31** lists "Language-specific reviewers: Go, Python, TypeScript, Shell (no Ruby/Rails)" but there is now also a `rust-reviewer.md` on disk. Rust is missing from this list.

### Architecture Tree Accuracy in AGENTS.md

The AGENTS.md architecture tree (lines 23-62) is structurally correct for the top-level layout but has two categories of staleness:

**scripts/ directory (AGENTS.md line 53-54):**
- Tree shows: `upstream-check.sh` only
- Actual contents: `upstream-check.sh`, `dispatch.sh`, `debate.sh`, `install-codex.sh`, `upstream-impact-report.py`
- The README.md tree (line 270-272) correctly shows `dispatch.sh`, `debate.sh`, and `upstream-check.sh` but is also missing `install-codex.sh` and `upstream-impact-report.py`.

**.github/workflows/ directory:**
- AGENTS.md tree shows 4 workflows: `upstream-check.yml`, `sync.yml`, `upstream-impact.yml`, `upstream-decision-gate.yml`
- README.md tree shows 2 workflows: `upstream-check.yml`, `sync.yml`
- Actual on disk: 8 workflows: `upstream-check.yml`, `sync.yml`, `upstream-impact.yml`, `upstream-decision-gate.yml`, `pr-agent-commands.yml`, `upstream-sync-issue-command.yml`, `codex-refresh-reminder.yml`, `codex-refresh-reminder-pr.yml`
- The AGENTS.md tree is closer to complete (4/8) but still missing 4 workflows. The README tree is significantly incomplete (2/8).

### Hook Registration vs Actual Hook Files

**hooks.json registration** declares 3 events with 4 script references:
1. `PreToolUse` -> `autopilot.sh` (with matcher `Edit|Write|MultiEdit|NotebookEdit`)
2. `SessionStart` -> `session-start.sh` + `agent-mail-register.sh` (with matcher `startup|resume|clear|compact`)
3. `SessionEnd` -> `dotfiles-sync.sh` (no matcher)

**Files on disk in hooks/:**
- `hooks.json` -- registration file
- `lib.sh` -- shared utilities (not registered as a hook, correctly sourced by session-start.sh)
- `autopilot.sh` -- referenced by PreToolUse
- `session-start.sh` -- referenced by SessionStart
- `agent-mail-register.sh` -- referenced by SessionStart
- `dotfiles-sync.sh` -- referenced by SessionEnd

**Assessment:** All hook script references in `hooks.json` point to files that exist on disk. No orphan scripts, no dangling references. The `lib.sh` file is correctly used as a sourced library, not a hook entry. The `${CLAUDE_PLUGIN_ROOT}` variable is used consistently in all hook commands.

**Minor note:** The `SessionEnd` entry lacks a `matcher` field. Both `PreToolUse` and `SessionStart` entries include matchers. The Claude Code hook system may treat a missing matcher as "match all," which is likely the desired behavior for session end (there's only one end event). However, for consistency, adding `"matcher": ".*"` or removing matchers from the documentation expectation would resolve the asymmetry.

**Hook count methodology:** The headline count across CLAUDE.md, AGENTS.md, and README.md is "3 hooks." This counts hook *events* (PreToolUse, SessionStart, SessionEnd), not hook *scripts* (4: autopilot.sh, session-start.sh, agent-mail-register.sh, dotfiles-sync.sh). The README Hooks section (lines 194-198) lists 3 items matching the 3 events, which is consistent with counting events. This is defensible but worth noting: a reader might expect "3 hooks" to mean 3 scripts.

### Pipeline Coherence: /lfg Steps and Clodex Branching

The `/lfg` command (`commands/lfg.md`) defines 7 steps:
1. `/clavain:brainstorm $ARGUMENTS`
2. `/clavain:write-plan`
3. `/clavain:work` (skipped in clodex mode)
4. `/clavain:flux-drive <plan-file>`
5. `/clavain:review`
6. `/clavain:resolve-todo-parallel`
7. `/clavain:quality-gates`

**All referenced commands exist** as files in `commands/`:
- `brainstorm.md` -- exists
- `write-plan.md` -- exists
- `work.md` -- exists
- `flux-drive.md` -- exists (delegates to `clavain:flux-drive` skill)
- `review.md` -- exists
- `resolve-todo-parallel.md` -- exists
- `quality-gates.md` -- exists

**Clodex branching logic** is coherent:
- Step 3 checks `.claude/autopilot.flag` to determine if clodex mode is active
- If active, Step 3 is skipped (write-plan already executed via Codex Delegation in Step 2)
- Step 4 (flux-drive) mentions "clodex mode is active, flux-drive automatically dispatches review agents through Codex"
- The flux-drive SKILL.md (Step 2.1) independently checks the same `.claude/autopilot.flag` file
- Step 6 notes that resolve-todo-parallel has clodex-mode guidance

**Consistency:** The pipeline is internally consistent. The clodex detection mechanism (`.claude/autopilot.flag` file) is used identically across `/lfg`, flux-drive SKILL.md, and the autopilot.sh hook. No phantom command or skill references.

### Upstream Sync Architecture

The upstream sync system has two layers:

**Check System (lightweight):**
- `scripts/upstream-check.sh` -- local script checking 7 repos via `gh api`
- `.github/workflows/upstream-check.yml` -- daily cron running the script
- State: `docs/upstream-versions.json`

**Sync System (automated merging):**
- `upstreams.json` -- defines 7 upstreams with file mappings (source path -> local path)
- `.github/workflows/sync.yml` -- weekly cron using Claude Code + Codex CLI
- `.github/workflows/upstream-impact.yml` -- PR impact digest
- `.github/workflows/upstream-decision-gate.yml` -- human decision gate

**Assessment:** The two systems are complementary and well-separated. The 7 repos tracked are consistent between `scripts/upstream-check.sh` (UPSTREAMS array) and `upstreams.json`. File mappings in `upstreams.json` correctly handle namespace renames (`using-superpowers` -> `using-clavain`, `data-integrity-guardian` -> `data-integrity-reviewer`, `code-reviewer.md` -> `plan-reviewer.md`). The `basePath` for compound-engineering (`plugins/compound-engineering`) is correct.

**One discrepancy in the check script:** Line 22 maps `steipete/oracle` to skill `oracle-review`, but the AGENTS.md upstream tracking table (line 322) maps it to `interpeer, prompterpeer, winterpeer, splinterpeer`. The `oracle-review` skill name doesn't exist -- the Oracle knowledge is stored in `winterpeer/references/`. This is a cosmetic mismatch in the check script's human-readable label, not a functional bug (the check script only detects changes, it doesn't do file mapping).

### MCP Server Configuration

`plugin.json` declares 3 MCP servers:

1. **context7** -- `type: "http"`, URL: `https://mcp.context7.com/mcp` (external service)
2. **mcp-agent-mail** -- `type: "http"`, URL: `http://127.0.0.1:8765/mcp` (local service)
3. **qmd** -- `type: "stdio"`, command: `qmd`, args: `["mcp"]` (local binary)

**Assessment:** Configuration is clean and correct. The `session-start.sh` hook (line 33) probes the agent-mail server at `http://127.0.0.1:8765/health` on startup, which is consistent with the configured URL. The hook gracefully handles the server being unavailable (curl with `--connect-timeout 1`). The context7 and qmd servers are mentioned consistently in AGENTS.md, README.md, and the flux-drive SKILL.md. No orphan MCP references.

## Issues Found

### P0-1: Architecture tree says "20 code review agents" (should be 21)

**Severity:** P0 -- factual error in the primary architecture reference

**Locations:**
- `AGENTS.md` line 40: `review/  # 20 code review agents`
- `README.md` line 259: `review/  # 20 code review agents`

**Root cause:** The `rust-reviewer.md` agent was added but the tree comments in both files were not updated. The AGENTS.md Quick Reference table (line 125) and README body (line 152) were updated to say 21, creating an internal contradiction within each file.

**Fix:** Change "20" to "21" on both lines.

### P0-2: CLAUDE.md validation comment says "Should be 28" (should be 29)

**Severity:** P0 -- incorrect validation gate will report false failures

**Location:** `CLAUDE.md` line 17: `ls agents/{review,research,workflow}/*.md | wc -l  # Should be 28`

**Root cause:** Same as P0-1 -- rust-reviewer was added without updating the validation comment.

**Fix:** Change "28" to "29".

### P1-1: Review agent count inconsistent across conflict tables

**Severity:** P1 -- confusing for readers comparing documentation surfaces

**Locations:**
- `AGENTS.md` line 275: "15 review agents"
- `docs/plugin-audit.md` line 21: "15 review agents"
- `README.md` line 234: "20 review agents"

**Root cause:** These numbers were written at different times and never unified. The 15 likely predates several review agent additions.

**Fix:** Update all three to "21 review agents".

### P1-2: CLAUDE.md omits Rust from language-specific reviewers

**Severity:** P1 -- design decision doc is incomplete

**Location:** `CLAUDE.md` line 31: "Language-specific reviewers: Go, Python, TypeScript, Shell (no Ruby/Rails)"

**Fix:** Change to "Language-specific reviewers: Go, Python, TypeScript, Shell, Rust (no Ruby/Rails)"

### P1-3: AGENTS.md scripts/ tree is incomplete

**Severity:** P1 -- architecture diagram misleads about available tooling

**Location:** `AGENTS.md` lines 53-54 (shows only `upstream-check.sh`)

**Actual files:** `upstream-check.sh`, `dispatch.sh`, `debate.sh`, `install-codex.sh`, `upstream-impact-report.py`

**Fix:** Expand the scripts/ section:
```
scripts/
    dispatch.sh                # Codex exec wrapper with sensible defaults
    debate.sh                  # Structured 2-round Claude <-> Codex debate
    install-codex.sh           # Codex skill installer
    upstream-check.sh          # Checks 7 upstream repos via gh api
    upstream-impact-report.py  # Generates impact digest for upstream PRs
```

### P1-4: Workflow trees incomplete in both AGENTS.md and README.md

**Severity:** P1 -- workflow infrastructure is partially invisible

**AGENTS.md** shows 4 of 8 workflows (missing: `pr-agent-commands.yml`, `upstream-sync-issue-command.yml`, `codex-refresh-reminder.yml`, `codex-refresh-reminder-pr.yml`).

**README.md** shows 2 of 8 workflows (missing 6).

### P1-5: README.md flux-drive roster claim of "28 agents" is inflated

**Severity:** P1 -- sets incorrect expectations for users

**Location:** `README.md` line 58: "It pulls from a roster of 28 agents across 4 tiers"

**Actual fixed roster:** 5 Tier 1 + 13 Tier 3 + 1 Tier 4 = 19 agents. Tier 2 is dynamic (project-specific `.claude/agents/fd-*.md` files). The total agent count in the repo is 29, but not all of them are in the flux-drive roster (research and workflow agents are not review agents).

**Fix:** Change to something like "It selects from a roster of 19 built-in review agents across 4 tiers (plus any project-specific Tier 2 agents):" or simply "It selects from a tiered roster of review agents:".

### P2-1: SessionEnd hook entry lacks matcher field

**Severity:** P2 -- functional but asymmetric with other entries

**Location:** `hooks/hooks.json` lines 32-42

The `SessionEnd` entry has no `matcher` key, while `PreToolUse` and `SessionStart` both have one. This is likely correct behavior (SessionEnd has no sub-events to match against), but the asymmetry may confuse contributors.

### P2-2: Conflict table review agent counts differ across 3 files

**Severity:** P2 -- cosmetic inconsistency in secondary documentation

This is a sub-finding of P1-1. The AGENTS.md conflict table, README conflict table, and plugin-audit.md all give different numbers for the same claim.

## Improvements Suggested

### IMP-1: Standardize review agent count to 21 across all surfaces

Perform a single sweep updating all references to the review agent count:
- `AGENTS.md` line 40 (tree): 20 -> 21
- `AGENTS.md` line 275 (conflict table): 15 -> 21
- `README.md` line 58 (flux-drive prose): fix "28 agents" claim
- `README.md` line 234 (conflict table): 20 -> 21
- `README.md` line 259 (tree): 20 -> 21
- `CLAUDE.md` line 17 (validation comment): 28 -> 29
- `CLAUDE.md` line 31 (language list): add Rust
- `docs/plugin-audit.md` line 21: 15 -> 21

### IMP-2: Update architecture trees to reflect actual disk contents

Both the `scripts/` and `.github/workflows/` sections in AGENTS.md and README.md are incomplete. Update them to match what is actually on disk. Consider adding a "notable workflows" subset in README.md (which is user-facing) while keeping the full list in AGENTS.md (which is the dev guide).

### IMP-3: Add Rust to CLAUDE.md language-specific reviewers list

Update `CLAUDE.md` line 31 from "Go, Python, TypeScript, Shell" to "Go, Python, TypeScript, Shell, Rust".

### IMP-4: Correct flux-drive roster claim in README

The "28 agents across 4 tiers" claim on README line 58 conflates the total agent count (29) with the flux-drive roster size (19 fixed). Rewrite to accurately describe the tiered selection without overstating the roster size.

### IMP-5: Consider a validation script that auto-checks counts

The current validation in CLAUDE.md is manual comments ("Should be 28"). A script in `scripts/` that counts components and compares against canonical values in `plugin.json` would catch drift automatically. This could run in CI.

## Overall Assessment

The Clavain repo has strong architectural coherence. The hook system, pipeline wiring, MCP server configuration, and upstream sync architecture are all correctly implemented and internally consistent. The issues found are exclusively documentation drift -- component counts that fell behind as agents were added. No functional bugs, no broken references, no orphan files. The verdict is **needs-changes** because the P0 issues (factual errors in the architecture trees and validation comments) will cause confusion for contributors and could cause false validation failures, but the fixes are purely textual and low-risk.
