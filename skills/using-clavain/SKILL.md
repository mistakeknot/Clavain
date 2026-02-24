---
name: using-clavain
description: Use when starting any conversation - establishes how to find and use skills, agents, and commands, requiring Skill tool invocation before ANY response including clarifying questions
---

**Proactive skill invocation is required.** When a skill matches the current task — even partially — invoke it before responding.

# Quick Router — 16 skills, 4 agents, and 58 commands

| You want to... | Run this |
|----------------|----------|
| Build a feature end-to-end | `/clavain:route` |
| Force full lifecycle | `/clavain:sprint` |
| Review code, docs, or plans | `/interflux:flux-drive` |
| Quick review from git diff | `/clavain:quality-gates` |
| Cross-AI second opinion | `/clavain:interpeer` |
| Plan an implementation | `/clavain:write-plan` → `/clavain:work` |
| Fix a bug | `/clavain:repro-first-debugging` |
| Fix build/test failure | `/clavain:fixbuild` |
| Resolve review findings | `/clavain:resolve` |
| Check project health | `/clavain:doctor` or `/clavain:sprint-status` |
| Generate a roadmap/PRD | `/interpath:roadmap` or `/interpath:prd` |
| Check doc freshness | `/interwatch:watch` |
| See all commands | `/clavain:help` |

## Routing Heuristic

1. **Detect stage** from the request ("build" → Execute, "fix bug" → Debug, "review" → Review, "plan" → Plan)
2. **Detect domain** from context (file types, topic, recent conversation)
3. **Invoke the primary skill first** — don't skip relevant skills

Full routing tables: `using-clavain/references/routing-tables.md`
