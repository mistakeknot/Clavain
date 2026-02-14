# Clavain — Development Guide

General-purpose engineering discipline plugin for Claude Code. Merged from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Quick Reference

| Item | Value |
|------|-------|
| Repo | `https://github.com/mistakeknot/Clavain` |
| Namespace | `clavain:` |
| Manifest | `.claude-plugin/plugin.json` |
| Components | 27 skills, 5 agents, 36 commands, 7 hooks, 1 MCP servers |
| License | MIT |

## Runbooks

- Codex sync operations: `docs/runbooks/codex-sync.md`
- Optional automated Codex refresh job: `scripts/codex-auto-refresh.sh` (cron/systemd/launchd examples in `docs/runbooks/codex-sync.md`)
- GitHub web PR agent commands (`/clavain:claude-review`, `/clavain:codex-review`, `/clavain:dual-review`) are documented in `docs/runbooks/codex-sync.md`
- GitHub issue command `/clavain:upstream-sync` (for `upstream-sync` issues) is documented in `docs/runbooks/codex-sync.md`

## Architecture

```
Clavain/
├── .claude-plugin/plugin.json     # Plugin manifest (name, version, MCP servers)
├── skills/                        # 27 discipline skills
│   ├── using-clavain/SKILL.md     # Bootstrap routing (injected via SessionStart hook)
│   ├── brainstorming/SKILL.md     # Explore phase
│   ├── writing-plans/SKILL.md     # Plan phase
│   ├── executing-plans/SKILL.md   # Execute phase
│   ├── test-driven-development/SKILL.md
│   ├── systematic-debugging/SKILL.md
│   ├── flux-drive/                # Has sub-resources (phases/, references/)
│   │   ├── SKILL.md
│   │   ├── phases/                # Phase-specific instructions (launch, synthesis, etc.)
│   │   └── references/            # Extracted reference material
│   │       ├── agent-roster.md    # Agent categories, invocation, Oracle CLI usage
│   │       └── scoring-examples.md # Worked triage scoring examples
│   ├── writing-skills/            # Has sub-resources (examples/, references)
│   │   ├── SKILL.md
│   │   ├── testing-skills-with-subagents.md
│   │   ├── persuasion-principles.md
│   │   └── examples/
│   └── ...                        # Each skill is a directory with SKILL.md
├── agents/
│   ├── review/                    # 3 review agents
│   └── workflow/                  # 2 workflow agents
├── commands/                      # 36 slash commands
│   ├── setup.md               # Modpack installer
│   └── interpeer.md           # Quick cross-AI peer review (+ 34 others)
├── hooks/
│   ├── hooks.json                 # Hook registration (SessionStart + PostToolUse + Stop + SessionEnd)
│   ├── lib.sh                     # Shared utilities (escape_for_json)
│   ├── sprint-scan.sh             # Sprint awareness scanner (sourced by session-start + sprint-status)
│   ├── session-start.sh           # Context injection + upstream staleness + sprint awareness
│   ├── clodex-audit.sh             # Clodex mode source code write audit (PostToolUse Edit/Write)
│   ├── lib-gates.sh               # Phase gate shim (delegates to interphase; no-op stub if absent)
│   ├── lib-discovery.sh           # Plugin discovery shim (delegates to interphase; no-op stub if absent)
│   ├── auto-publish.sh            # Auto-publish after git push (PostToolUse Bash)
│   ├── auto-compound.sh           # Auto-compound knowledge capture on Stop
│   ├── session-handoff.sh         # HANDOFF.md generation on incomplete work
│   └── dotfiles-sync.sh           # Sync dotfile changes on session end
├── config/
│   └── dispatch/                  # Codex dispatch configuration
├── scripts/
│   ├── debate.sh                  # Structured 2-round Claude↔Codex debate
│   ├── dispatch.sh                # Codex exec wrapper with sensible defaults
│   ├── install-codex.sh           # Codex skill installer
│   ├── codex-auto-refresh.sh      # Automated local Codex sync helper
│   ├── gen-catalog.py             # Generate skill/agent/command catalog
│   ├── bump-version.sh            # Bump version across plugin.json + marketplace.json
│   ├── upstream-check.sh          # Checks 7 upstream repos via gh api
│   └── upstream-impact-report.py  # Generates impact digest for upstream PRs
├── docs/
│   └── upstream-versions.json     # Baseline for upstream sync tracking
└── .github/workflows/
    ├── upstream-check.yml              # Daily cron: opens GitHub issues on upstream changes
    ├── sync.yml                        # Weekly cron: Claude Code + Codex auto-merge upstream
    ├── upstream-impact.yml             # PR impact digest for upstream-sync changes
    ├── upstream-decision-gate.yml      # Human decision gate for upstream-sync PRs
    ├── pr-agent-commands.yml           # Issue comment dispatch for /review and /codex-review
    ├── upstream-sync-issue-command.yml # Issue comment dispatch for /sync
    ├── codex-refresh-reminder.yml      # Push-triggered Codex skill freshness check
    └── codex-refresh-reminder-pr.yml   # PR-triggered Codex skill freshness check
```

## How It Works

### SessionStart Hook

On every session start, resume, clear, or compact, the `session-start.sh` hook:

1. Reads `skills/using-clavain/SKILL.md`
2. JSON-escapes the content
3. Outputs `hookSpecificOutput.additionalContext` JSON
4. Claude Code injects this as system context

This means every session starts with the 3-layer routing table, so the agent knows which skill/agent/command to invoke for any task.

### 3-Layer Routing

The `using-clavain` skill provides a routing system:

1. **Stage** — What phase? (explore / plan / execute / debug / review / ship / meta)
2. **Domain** — What kind of work? (code / data / deploy / docs / research / workflow / design / infra)
3. **Concern** — What review concern? (architecture / safety / correctness / quality / user-product / performance)

Each cell maps to specific skills, commands, and agents.

### Component Types

| Type | Location | Format | Triggered By |
|------|----------|--------|-------------|
| **Skill** | `skills/<name>/SKILL.md` | Markdown with YAML frontmatter (`name`, `description`) | `Skill` tool invocation |
| **Agent** | `agents/<category>/<name>.md` | Markdown with YAML frontmatter (`name`, `description`, `model`) | `Task` tool with `subagent_type` |
| **Command** | `commands/<name>.md` | Markdown with YAML frontmatter (`name`, `description`, `argument-hint`) | `/clavain:<name>` slash command |
| **Hook** | `hooks/hooks.json` + scripts | JSON registration + bash scripts | Automatic on registered events |
| **MCP Server** | `.claude-plugin/plugin.json` `mcpServers` | JSON config | Automatic on plugin load |

## Component Conventions

### Skills

- One directory per skill: `skills/<kebab-case-name>/SKILL.md`
- YAML frontmatter: `name` (must match directory name) and `description` (third-person, with trigger phrases)
- Body written in imperative form ("Do X", not "You should do X")
- Keep SKILL.md lean (1,500-2,000 words) — move detailed content to sub-files
- Sub-resources go in the skill directory: `examples/`, `references/`, helper `.md` files
- Description should contain specific trigger phrases so Claude matches the skill to user intent

Example frontmatter:
```yaml
---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---
```

### Agents

- Flat files in category directories: `agents/review/`, `agents/workflow/`
- YAML frontmatter: `name`, `description` (with `<example>` blocks showing when to trigger), `model` (usually `inherit`)
- Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger
- System prompt is the body of the markdown file
- Agents are dispatched via `Task` tool — they run as subagents with their own context

Categories:
- **review/** — Review specialists (3): plan-reviewer, agent-native-reviewer, and data-migration-expert. The 7 core fd-* agents live in the **interflux** companion plugin. The 5 research agents also moved to interflux.
- **workflow/** — Process automation (2): PR comments, bug reproduction

### Commands

- Flat `.md` files in `commands/`
- YAML frontmatter: `name`, `description`, `argument-hint` (optional)
- Body contains instructions FOR Claude (not for the user)
- Commands can reference skills: "Use the `clavain:writing-plans` skill"
- Commands can dispatch agents: "Launch `Task(interflux:review:fd-architecture)`"
- Invoked as `/clavain:<name>` by users

### Hooks

- Registration in `hooks/hooks.json` — specifies event, matcher regex, and command
- Scripts in `hooks/` — use `${CLAUDE_PLUGIN_ROOT}` for portable paths
- **SessionStart** (matcher: `startup|resume|clear|compact`):
  - `session-start.sh` — injects `using-clavain` skill content, clodex behavioral contract (when active), upstream staleness warnings
- **PostToolUse** (matcher: `Edit|Write|MultiEdit|NotebookEdit`):
  - `clodex-audit.sh` — logs source code writes when clodex mode is active (audit only, no denial)
- **PostToolUse** (matcher: `Bash`):
  - `auto-publish.sh` — detects `git push` in plugin repos, auto-bumps patch version if needed, syncs marketplace (60s TTL sentinel prevents loops)
- **Stop**:
  - `auto-compound.sh` — detects compoundable signals (commits, resolutions, insights), prompts knowledge capture
  - `session-handoff.sh` — detects uncommitted work or in-progress beads, prompts HANDOFF.md creation (once per session)
- **SessionEnd**:
  - `dotfiles-sync.sh` — syncs dotfile changes at end of session
- Scripts must output valid JSON to stdout
- Use `set -euo pipefail` in all hook scripts

## Adding Components

### Add a Skill

1. Create `skills/<name>/SKILL.md` with frontmatter
2. Add to the routing table in `skills/using-clavain/SKILL.md` (appropriate stage/domain row)
3. Update `plugin.json` description count if needed
4. Update `README.md` skills table

### Add an Agent

1. Create `agents/<category>/<name>.md` with frontmatter including `<example>` blocks
2. Add to the routing table in `skills/using-clavain/SKILL.md`
3. Reference from relevant commands if applicable
4. Update `README.md` agents list

### Add a Command

1. Create `commands/<name>.md` with frontmatter
2. Reference relevant skills in the body
3. Update `README.md` commands table

### Add an MCP Server

1. Add to `mcpServers` in `.claude-plugin/plugin.json`
2. Document required environment variables in README

## Validation Checklist

When making changes, verify:

- [ ] Skill `name` in frontmatter matches directory name
- [ ] All `clavain:` references point to existing skills/commands (no phantom references)
- [ ] Agent `description` includes `<example>` blocks with `<commentary>`
- [ ] Command `name` in frontmatter matches filename (minus `.md`)
- [ ] `hooks/hooks.json` is valid JSON
- [ ] `hooks/lib.sh` passes `bash -n` syntax check
- [ ] `hooks/session-start.sh` passes `bash -n` syntax check
- [ ] `hooks/auto-compound.sh` passes `bash -n` syntax check
- [ ] `hooks/session-handoff.sh` passes `bash -n` syntax check
- [ ] `hooks/dotfiles-sync.sh` passes `bash -n` syntax check
- [ ] `hooks/auto-publish.sh` passes `bash -n` syntax check
- [ ] `hooks/clodex-audit.sh` passes `bash -n` syntax check
- [ ] No references to dropped namespaces (`superpowers:`, `compound-engineering:`)
- [ ] No references to dropped components (Rails, Ruby, Every.to, Figma, Xcode)
- [ ] Routing table in `using-clavain/SKILL.md` is consistent with actual components

Quick validation:
```bash
# Count components
echo "Skills: $(ls skills/*/SKILL.md | wc -l)"      # Should be 27
echo "Agents: $(ls agents/{review,workflow}/*.md | wc -l)"
echo "Commands: $(ls commands/*.md | wc -l)"        # Should be 36

# Check for phantom namespace references
grep -r 'superpowers:' skills/ agents/ commands/ hooks/ || echo "Clean"
grep -r 'compound-engineering:' skills/ agents/ commands/ hooks/ || echo "Clean"

# Validate JSON
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('Manifest OK')"
python3 -c "import json; json.load(open('hooks/hooks.json')); print('Hooks OK')"

# Syntax check scripts
bash -n hooks/lib.sh && echo "lib.sh OK"
bash -n hooks/session-start.sh && echo "session-start.sh OK"
bash -n hooks/auto-compound.sh && echo "auto-compound.sh OK"
bash -n hooks/session-handoff.sh && echo "session-handoff.sh OK"
bash -n hooks/dotfiles-sync.sh && echo "dotfiles-sync.sh OK"
bash -n hooks/auto-publish.sh && echo "auto-publish.sh OK"
bash -n hooks/clodex-audit.sh && echo "clodex-audit.sh OK"
bash -n scripts/upstream-check.sh && echo "Upstream check OK"

# Test upstream check (no network calls with --json, but needs gh)
bash scripts/upstream-check.sh 2>&1; echo "Exit: $?"  # 0=changes, 1=no changes, 2=error
```

## Modpack — Companion Plugins

Clavain is a modpack: an opinionated integration layer that configures companion plugins into a cohesive engineering rig. It doesn't duplicate their capabilities — it routes to them and wires them together.

### Required

These must be installed for Clavain to function fully.

| Plugin | Source | Why Required |
|--------|--------|-------------|
| **context7** | claude-plugins-official | Runtime doc fetching. Clavain's MCP server. Skills use it to pull upstream docs without bundling them. |
| **explanatory-output-style** | claude-plugins-official | Educational insights in output. Injected via SessionStart hook. |

### Companion Plugins

Extracted subsystems that Clavain delegates to via namespace routing.

| Plugin | Source | What It Provides |
|--------|--------|-----------------|
| **interflux** | interagency-marketplace | Multi-agent review + research engine. 7 fd-* review agents, 5 research agents, flux-drive/flux-research skills, qmd + exa MCP servers. Protocol spec in `docs/spec/`. |
| **interphase** | interagency-marketplace | Phase tracking, gates, and work discovery. lib-phase.sh, lib-gates.sh, lib-discovery.sh. Clavain shims delegate to interphase when installed. |
| **interline** | interagency-marketplace | Statusline renderer. Shows dispatch state, bead context, workflow phase, clodex mode. |

### Recommended

These enhance the rig significantly but aren't hard dependencies.

| Plugin | Source | What It Adds |
|--------|--------|-------------|
| **agent-sdk-dev** | claude-plugins-official | Agent SDK scaffolding: `/new-sdk-app` command, Python + TS verifier agents. |
| **plugin-dev** | claude-plugins-official | Plugin development: 7 skills, 3 agents including agent-creator and skill-reviewer. |
| **interdoc** | interagency-marketplace | AGENTS.md generation for any repo. |
| **auracoil** | interagency-marketplace | GPT-5.2 Pro review of AGENTS.md specifically. |
| **tool-time** | interagency-marketplace | Tool usage analytics across sessions. |
| **security-guidance** | claude-plugins-official | Security warning hooks on file edits. Complements Clavain's fd-safety agent. |
| **serena** | claude-plugins-official | Semantic code analysis via LSP-like tools. Different tool class from Clavain's agents. |

### Infrastructure (language servers)

Enable based on which languages you work with.

| Plugin | Language |
|--------|----------|
| **gopls-lsp** | Go |
| **pyright-lsp** | Python |
| **typescript-lsp** | TypeScript |
| **rust-analyzer-lsp** | Rust |

### Conditional (domain-specific)

| Plugin | Enable When |
|--------|------------|
| **supabase** | Working with Supabase backends |
| **vercel** | Deploying to Vercel |
| **tldrs** + **tldr-swinton** | Hitting context limits, want token-efficient exploration |
| **tuivision** | Building or testing terminal UI apps |

### Conflicts — Disabled by Clavain

These plugins overlap with Clavain's opinionated equivalents. Keeping both causes duplicate agents in the Task tool roster and confusing routing.

| Plugin | Clavain Replacement | Status |
|--------|-------------------|--------|
| code-review | `/review` + `/flux-drive` + 10 review agents | **OFF** |
| pr-review-toolkit | Same agent types exist in Clavain's review roster | **OFF** |
| code-simplifier | `interflux:review:fd-quality` agent | **OFF** |
| commit-commands | `landing-a-change` skill | **OFF** |
| feature-dev | `/work` + `/lfg` + `/brainstorm` | **OFF** |
| claude-md-management | `engineering-docs` skill | **OFF** |
| frontend-design | `distinctive-design` skill | **OFF** |
| hookify | Clavain manages hooks directly | **OFF** |

Full audit rationale: `docs/plugin-audit.md`

## Known Constraints

- **No build step** — pure markdown/JSON/bash plugin, nothing to compile
- **3-tier test suite** — structural (pytest), shell (bats-core), smoke (Claude Code subagents). Run via `tests/run-tests.sh`
- **General-purpose only** — no domain-specific components (Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation)
- **Trunk-based** — no branch/worktree skills; commit directly to `main`

## Upstream Tracking

Clavain bundles knowledge from 6 actively-developed upstream tools. Two systems keep them in sync:

**1. Check System** (lightweight detection):
- `.github/workflows/upstream-check.yml` — daily cron, checks repos via `gh api`, opens/updates issues with `upstream-sync` label
- `scripts/upstream-check.sh` — local runner for same check
- State: `docs/upstream-versions.json`

**2. Sync System** (automated merging):
- `.github/workflows/sync.yml` — weekly cron + manual dispatch, uses Claude Code + Codex CLI to auto-merge upstream changes
- File mappings: `upstreams.json` (source→local path mappings with glob support)
- Work dir: `.upstream-work/` (gitignored)
- `.github/workflows/upstream-impact.yml` — posts upstream impact digest on `upstream-sync` PRs
- `.github/workflows/upstream-decision-gate.yml` — requires human decision record before merge
- Decision records: `docs/upstream-decisions/pr-<PR_NUMBER>.md` (template: `docs/templates/upstream-decision-record.md`)

| Tool | Repo | Clavain Skills Affected |
|------|------|------------------------|
| Beads | `steveyegge/beads` | `interphase` companion plugin — phase tracking, gates, discovery. Default backend is Dolt (version-controlled SQL with cell-level merge); JSONL maintained for git portability; SQLite removed |
| Oracle | `steipete/oracle` | `interpeer`, `prompterpeer`, `winterpeer`, `splinterpeer` |
| superpowers | `obra/superpowers` | Multiple (founding source) |
| superpowers-lab | `obra/superpowers-lab` | `using-tmux`, `slack-messaging`, `mcp-cli`, `finding-duplicate-functions` |
| superpowers-dev | `obra/superpowers-developing-for-claude-code` | `developing-claude-code-plugins`, `working-with-claude-code` |
| compound-engineering | `EveryInc/compound-engineering-plugin` | Multiple (founding source) |

Manual sync check:
```bash
# Check for upstream updates (local — no file changes)
bash scripts/upstream-check.sh
# Trigger full auto-merge (GitHub Action — creates PR)
gh workflow run sync.yml
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
