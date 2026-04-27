---
name: using-clavain
description: Use at start of any conversation — how to find/use skills, agents, commands. Requires Skill invocation before ANY response, including clarifying questions.
---

**Proactive skill invocation is required.** When a skill matches the current task — even partially — invoke it before responding.

# Quick Router — 17 skills, 6 agents, and 51 commands

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
| Set up a new project | `/clavain:project-onboard` |
| Check project health | `/clavain:clavain-doctor` or `/clavain:sprint-status` |
| Generate roadmap/PRD | `/interpath:roadmap` or `/interpath:prd` |
| Check doc freshness | `/interwatch:watch` |
| Run scenario tests | `clavain-cli scenario-run <pattern>` |
| Check quality gate | `clavain-cli scenario-score <run-id> --summary` |
| Check scenario policy | `clavain-cli scenario-policy-check <agent> <action> --path=<p>` |
| See all commands | `/clavain:clavain-help` |

## Auto-Route Rule

**Invoke `/clavain:route` when:** bead ID mentioned, request is a feature/bugfix/implementation, user says "what's next" and picks work.

**Do NOT auto-route when:** request is informational, is a review/publish/commit/status check (use specific skill), or already mid-execution inside a routed workflow.

## Routing Heuristic

1. Detect stage: "build" → Execute, "fix bug" → Debug, "review" → Review, "plan" → Plan
2. Detect domain from context (file types, topic, recent conversation)
3. Invoke the primary skill first — don't skip

Full routing tables: `using-clavain/references/routing-tables.md`
