# Clavain — Development Guide

General-purpose engineering discipline plugin for Claude Code. Merged from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Quick Reference

| Item | Value |
|------|-------|
| Repo | `https://github.com/mistakeknot/Clavain` |
| Namespace | `clavain:` |
| Manifest | `.claude-plugin/plugin.json` |
| Components | 27 skills, 23 agents, 21 commands, 2 hooks, 1 MCP server |
| License | MIT |

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
│   ├── writing-skills/            # Has sub-resources (examples/, references)
│   │   ├── SKILL.md
│   │   ├── testing-skills-with-subagents.md
│   │   ├── persuasion-principles.md
│   │   └── examples/
│   └── ...                        # Each skill is a directory with SKILL.md
├── agents/
│   ├── review/                    # 15 code review agents
│   ├── research/                  # 5 research agents
│   └── workflow/                  # 3 workflow agents
├── commands/                      # 21 slash commands
├── hooks/
│   ├── hooks.json                 # Hook registration (SessionStart)
│   └── session-start.sh           # Reads using-clavain/SKILL.md, outputs JSON
├── lib/
│   └── skills-core.js             # Shared utilities
└── docs-sp-reference/             # Historical archive from source plugins (read-only)
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
3. **Language** — What language? (go / python / typescript / shell / markdown)

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

- Flat files in category directories: `agents/review/`, `agents/research/`, `agents/workflow/`
- YAML frontmatter: `name`, `description` (with `<example>` blocks showing when to trigger), `model` (usually `inherit`)
- Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger
- System prompt is the body of the markdown file
- Agents are dispatched via `Task` tool — they run as subagents with their own context

Categories:
- **review/** — Code review specialists (15): language-specific (kieran-go/python/typescript/shell), cross-cutting (security, performance, concurrency, architecture, patterns, simplicity, agent-native), data (migration, integrity), deployment, plan review
- **research/** — Information gathering (5): best practices, framework docs, git history, learnings, repo analysis
- **workflow/** — Process automation (3): PR comments, spec flow analysis, bug reproduction

### Commands

- Flat `.md` files in `commands/`
- YAML frontmatter: `name`, `description`, `argument-hint` (optional)
- Body contains instructions FOR Claude (not for the user)
- Commands can reference skills: "Use the `clavain:writing-plans` skill"
- Commands can dispatch agents: "Launch `Task(architecture-strategist)`"
- Invoked as `/clavain:<name>` by users

### Hooks

- Registration in `hooks/hooks.json` — specifies event, matcher regex, and command
- Scripts in `hooks/` — use `${CLAUDE_PLUGIN_ROOT}` for portable paths
- Currently only `SessionStart` hook (matcher: `startup|resume|clear|compact`)
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
- [ ] `hooks/session-start.sh` passes `bash -n` syntax check
- [ ] No references to dropped namespaces (`superpowers:`, `compound-engineering:`)
- [ ] No references to dropped components (Rails, Ruby, Every.to, Figma, Xcode)
- [ ] Routing table in `using-clavain/SKILL.md` is consistent with actual components

Quick validation:
```bash
# Count components
echo "Skills: $(ls skills/*/SKILL.md | wc -l)"
echo "Agents: $(ls agents/{review,research,workflow}/*.md | wc -l)"
echo "Commands: $(ls commands/*.md | wc -l)"

# Check for phantom namespace references
grep -r 'superpowers:' skills/ agents/ commands/ hooks/ || echo "Clean"
grep -r 'compound-engineering:' skills/ agents/ commands/ hooks/ || echo "Clean"

# Validate JSON
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('Manifest OK')"
python3 -c "import json; json.load(open('hooks/hooks.json')); print('Hooks OK')"

# Syntax check hook
bash -n hooks/session-start.sh && echo "Hook script OK"
```

## Known Constraints

- **No build step** — pure markdown/JSON/bash plugin, nothing to compile
- **No tests** — plugin validation is structural (file existence, JSON validity, reference consistency)
- **`docs-sp-reference/`** — historical archive from source plugins; read-only, do not modify
- **General-purpose only** — no domain-specific components (Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation)
- **Trunk-based** — no branch/worktree skills; commit directly to `main`

## Credits

- **Jesse Vincent** ([@obra](https://github.com/obra)) — superpowers, superpowers-lab, superpowers-developing-for-claude-code
- **Kieran Klaassen** ([@kieranklaassen](https://github.com/kieranklaassen)) — compound-engineering at [Every](https://every.to)
