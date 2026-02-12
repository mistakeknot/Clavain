---
name: using-clavain
description: Use when starting any conversation - establishes how to find and use skills, agents, and commands, requiring Skill tool invocation before ANY response including clarifying questions
---

**Proactive skill invocation is required.** When a skill matches the current task — even partially — invoke it before responding. Skills are designed to be triggered automatically; skipping a relevant skill degrades output quality.

## How to Access Skills

**In Claude Code:** Use the `Skill` tool. When you invoke a skill, its content is loaded and presented to you—follow it directly. Never use the Read tool on skill files.

**In Codex CLI:** Install Clavain skills with `bash ~/.codex/clavain/scripts/install-codex.sh install`. Codex discovers them from `~/.agents/skills/clavain/` on startup, so restart Codex after install.

# Quick Router — 30 skills, 17 agents, and 37 commands

| You want to... | Run this |
|----------------|----------|
| Build a feature end-to-end | `/clavain:lfg` (no args = work discovery, with args = full pipeline) |
| Review code, docs, or plans | `/clavain:flux-drive` (alias: `/clavain:deep-review`) |
| Quick review from git diff | `/clavain:quality-gates` |
| Cross-AI second opinion | `/clavain:interpeer` (alias: `/clavain:cross-review`) |
| Plan an implementation | `/clavain:write-plan` → `/clavain:work` |
| Fix a bug | `/clavain:repro-first-debugging` |
| Fix build/test failure | `/clavain:fixbuild` |
| Resolve review findings | `/clavain:resolve` |
| Generate domain-specific reviewers | `/clavain:flux-gen` |
| Check project health | `/clavain:doctor` or `/clavain:sprint-status` |
| See all commands | `/clavain:help` |

## Routing Heuristic

When a user message arrives:

1. **Detect stage** from the request ("build" → Execute, "fix bug" → Debug, "review" → Review, "plan" → Plan, "what should we" → Explore)
2. **Detect domain** from context (file types, topic, recent conversation)
3. **Invoke the primary skill first** (process skills before domain skills before meta skills)

For the full routing tables with all skills, agents, and commands by stage/domain/concern, see `using-clavain/references/routing-tables.md`.

## Red Flag

If you catch yourself thinking "I'll just do this without a skill" — STOP. Check for a matching skill first. Skills evolve; read the current version even if you "remember" it.
