# Clavain Plugin Health Audit

**Date:** 2026-02-22
**Version audited:** 0.6.60
**Auditor:** Claude Opus 4.6

## Executive Summary

The Clavain plugin is in **good functional health** with minor issues. All JSON configs are valid, all shell scripts pass syntax checks, and all component files exist and are non-empty. The three issues found are:

1. **3 hook scripts lack owner-execute permission** (interspect-session.sh, interspect-evidence.sh, interspect-session-end.sh)
2. **Count drift** in CLAUDE.md — claims 15 skills / 52 commands but actual counts are 16 skills / 53 commands
3. **4 missing script references** in commands — all are companion plugin scripts looked up in the plugin cache (by design, not bugs)

---

## Summary Table

| Component            | Count | Expected | Status                                      |
|---------------------|-------|----------|---------------------------------------------|
| plugin.json          | 1     | 1        | OK — valid JSON, v0.6.60                    |
| hooks.json           | 1     | 1        | OK — valid JSON, 12 hook bindings           |
| agent-rig.json       | 1     | 1        | OK — valid JSON, v0.6.60 (matches plugin.json) |
| Hook scripts         | 12    | 12       | **3 NOT EXECUTABLE** (see below)            |
| Hook libraries       | 10    | —        | All OK (sourced, not directly executed)      |
| Skills               | 16    | 15       | All OK — SKILL.md present and non-empty (+1 over docs claim) |
| Commands             | 53    | 52       | All OK — all .md files present and non-empty (+1 over docs claim) |
| Agents               | 4     | 4        | All OK — all .md files present and non-empty |
| MCP servers          | 2     | —        | context7 (HTTP), qmd (stdio) — both tools available |
| Shell syntax (hooks) | 22/22 | —        | All pass `bash -n`                           |
| Shell syntax (scripts)| 17/17| —        | All pass `bash -n`                           |
| External tools       | 4/4   | —        | oracle, codex, beads, qmd — all installed    |

---

## Detailed Findings

### 1. Hook Executability Issues (3 files)

These hooks are registered in hooks.json and will be invoked by Claude Code directly (not sourced), so they need the execute bit set:

| File | Permissions | Issue |
|------|-------------|-------|
| `hooks/interspect-session.sh` | `-rw-rwxr--+` | Missing owner execute (u+x) |
| `hooks/interspect-evidence.sh` | `-rw-rwxr--+` | Missing owner execute (u+x) |
| `hooks/interspect-session-end.sh` | `-rw-rwxr--+` | Missing owner execute (u+x) |

All three have group execute set but not owner execute. If Claude Code runs hooks as the file owner (`mk`), these hooks will fail to execute. The file permission pattern `-rw-rwxr--+` means:
- Owner (mk): read+write, NO execute
- Group: read+write+execute
- Other: read only

**Impact:** These 3 hooks (SessionStart interspect-session, PostToolUse interspect-evidence, Stop interspect-session-end) may silently fail depending on how the hook runner invokes them. If the runner uses `bash <script>` rather than `./<script>`, they will still work. If it uses exec permissions, they will fail.

### 2. Count Drift in Documentation

CLAUDE.md states: "15 skills, 4 agents, 52 commands, 12 hooks"

Actual counts:
- Skills: **16** (one more than documented)
- Commands: **53** (one more than documented)
- Agents: 4 (correct)
- Hook bindings: 12 (correct)

**Extra skill:** `lane` — added 2026-02-21, after the docs were last synced.
**Extra command:** One of the recently added commands (likely `reflect.md` or another interspect-* command).

### 3. Companion Script References (By Design — Not Bugs)

Commands `doctor.md` and `setup.md` reference scripts that live in companion plugins (looked up in `~/.claude/plugins/cache/`). These are expected to be absent from the clavain directory itself:

| Script Reference | Companion Plugin | Context |
|-----------------|-----------------|---------|
| `scripts/interlock-register.sh` | interlock | Doctor/Setup check |
| `scripts/interpath.sh` | interpath | Doctor check |
| `scripts/interwatch.sh` | interwatch | Doctor check |
| `scripts/statusline.sh` | interline | Doctor/Setup check |

These are properly guarded with `ls ... 2>/dev/null` and report "not installed" gracefully. This is correct behavior.

---

## Component Inventory

### Hook Bindings (12 total, from hooks.json)

| Event | Script | Matcher | Timeout | Executable |
|-------|--------|---------|---------|------------|
| SessionStart | session-start.sh | startup\|resume\|clear\|compact | async | YES |
| SessionStart | interspect-session.sh | startup\|resume\|clear\|compact | async | **NO** |
| PostToolUse | interserve-audit.sh | Edit\|Write\|MultiEdit\|NotebookEdit | 5s | YES |
| PostToolUse | auto-publish.sh | Bash | 15s | YES |
| PostToolUse | bead-agent-bind.sh | Bash | 5s | YES |
| PostToolUse | catalog-reminder.sh | Edit\|Write\|MultiEdit | 5s | YES |
| PostToolUse | interspect-evidence.sh | Task | 5s | **NO** |
| Stop | session-handoff.sh | (all) | 5s | YES |
| Stop | auto-stop-actions.sh | (all) | 5s | YES |
| Stop | interspect-session-end.sh | (all) | 5s | **NO** |
| SessionEnd | dotfiles-sync.sh | (all) | async | YES |
| SessionEnd | session-end-handoff.sh | (all) | async | YES |

### Hook Libraries (10 files, sourced by hooks — not directly executed)

| File | Size | Notes |
|------|------|-------|
| lib.sh | 11,663B | Core hook utilities |
| lib-intercore.sh | 23,727B | Intercore integration library |
| lib-interspect.sh | 77,831B | Interspect shared library (largest file) |
| lib-sprint.sh | 50,282B | Sprint state library (executable — unusual for a lib) |
| lib-spec.sh | 8,242B | Spec utilities |
| lib-signals.sh | 3,301B | Signal handling |
| lib-verdict.sh | 4,614B | Verdict formatting |
| lib-discovery.sh | 934B | Shim to interphase |
| lib-gates.sh | 1,499B | Shim to interphase |
| sprint-scan.sh | 21,822B | Sprint scanner (sourced by session-start.sh) |

### Skills (16 directories)

| Skill | SKILL.md Size | Status |
|-------|---------------|--------|
| brainstorming | 2,488B | OK |
| code-review-discipline | 5,485B | OK |
| dispatching-parallel-agents | 8,444B | OK |
| engineering-docs | 11,968B | OK |
| executing-plans | 4,428B | OK |
| file-todos | 7,626B | OK |
| galiana | 3,726B | OK |
| interserve | 8,037B | OK |
| landing-a-change | 4,557B | OK |
| lane | 3,310B | OK |
| refactor-safely | 3,826B | OK |
| subagent-driven-development | 10,044B | OK |
| upstream-sync | 6,049B | OK |
| using-clavain | 1,492B | OK |
| using-tmux-for-interactive-commands | 5,074B | OK |
| writing-plans | 6,378B | OK |

### Commands (53 files)

All 53 command .md files are present and non-empty. Full list:

brainstorm, changelog, clodex-toggle, code-review, codex-bootstrap, codex-sprint, compound, create-agent-skill, debate, docs, doctor, execute-plan, fixbuild, galiana, generate-command, heal-skill, help, init, interpeer, interserve, interspect, interspect-correction, interspect-evidence, interspect-health, interspect-propose, interspect-revert, interspect-status, interspect-unblock, land, migration-safety, model-routing, plan-review, quality-gates, refactor, reflect, repro-first-debugging, resolve, review, review-doc, setup, smoke-test, sprint, sprint-status, status, strategy, tdd, todos, triage, triage-prs, upstream-sync, verify, work, write-plan

### Agents (4 files across 2 directories)

| Category | Agent | Size | Status |
|----------|-------|------|--------|
| review | data-migration-expert.md | 5,351B | OK |
| review | plan-reviewer.md | 4,247B | OK |
| workflow | bug-reproduction-validator.md | 5,237B | OK |
| workflow | pr-comment-resolver.md | 4,261B | OK |

### MCP Servers (2 registered)

| Server | Type | Status |
|--------|------|--------|
| context7 | HTTP (https://mcp.context7.com/mcp) | External service — available |
| qmd | stdio (`qmd mcp`) | Installed at /home/mk/.bun/bin/qmd |

### External Tools (4 registered in agent-rig.json)

| Tool | Check Command | Status | Path |
|------|--------------|--------|------|
| oracle | `command -v oracle` | Installed | /usr/bin/oracle |
| codex | `command -v codex` | Installed | /usr/bin/codex |
| beads | `command -v bd` | Installed | /home/mk/.local/bin/bd |
| qmd | `command -v qmd` | Installed | /home/mk/.bun/bin/qmd |

### Scripts Directory (17 .sh files + 5 .py files)

All 17 shell scripts pass `bash -n` syntax check. Key scripts:

| Script | Size | Executable | Purpose |
|--------|------|------------|---------|
| bump-version.sh | 239B | Yes | Version bumping |
| check-versions.sh | 269B | Yes | Version consistency check |
| clodex-toggle.sh | 2,008B | Yes | Codex toggle |
| codex-bootstrap.sh | 2,871B | Yes | Codex initialization |
| debate.sh | 8,252B | Yes | Multi-agent debate orchestration |
| dispatch.sh | 23,315B | Yes | Agent dispatch engine |
| lib-routing.sh | 23,956B | No (library) | Routing logic |
| sync-upstreams.sh | 37,933B | Yes | Upstream sync (largest script) |
| migrate-sprints-to-ic.sh | 5,793B | Yes | Sprint migration to Intercore |

### JSON Config Validation

| File | Valid JSON | Version |
|------|-----------|---------|
| .claude-plugin/plugin.json | Yes | 0.6.60 |
| hooks/hooks.json | Yes | — |
| agent-rig.json | Yes | 0.6.60 |

Version consistency: plugin.json and agent-rig.json both report **0.6.60** — in sync.

---

## Recommendations (Not Actioned)

1. **Fix execute permissions** on the 3 interspect hook scripts:
   ```bash
   chmod u+x hooks/interspect-session.sh hooks/interspect-evidence.sh hooks/interspect-session-end.sh
   ```

2. **Update CLAUDE.md counts** from "15 skills, 52 commands" to "16 skills, 53 commands"

3. **Consider:** `lib-sprint.sh` and `sprint-scan.sh` have inconsistent permissions — lib-sprint.sh is executable (unusual for a sourced library) while sprint-scan.sh is not. This is cosmetic but could cause confusion.
