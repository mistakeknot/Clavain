---
name: using-clavain
description: Use at start of any conversation — how to find/use skills, agents, commands. Requires Skill invocation before ANY response, including clarifying questions.
---

**Proactive skill invocation is required.** When a skill matches the current task — even partially — invoke it before responding.

## The OODARC Loop (how to work, every turn)

Clavain operates on **OODARC** — Observe · Orient · Decide · Act · Reflect · Compound — at nested timescales (per-turn, per-sprint, cross-session). Run it explicitly each turn:

1. **Observe** — read the actual tool results, file state, and test output. Don't act on assumptions about what happened.
2. **Orient** — situate against the goal and recent evidence. What changed? What's anomalous? At sprint scale, `ic situation snapshot --run=<id>` is the canonical one-shot Observe→Orient call — one query for runs, dispatches, queue, budget, and recent events, instead of polling each separately.
3. **Decide** — choose the next action; prefer the known fast path, deliberate when novel or high-stakes.
4. **Act** — invoke the tool / make the edit / advance the phase.
5. **Reflect** — did the outcome match expectation? On a *significant* outcome (error, recovery, surprise, novel situation) pause and debrief before continuing; on routine ones, continue and let evidence accumulate.
6. **Compound** — persist the lesson so it changes future behavior (a fix, a calibration, a solution doc, a bead). Reflect without Compound is just journaling.

The compounding half (Reflect + Compound) is what makes the system get smarter across sessions — it is not optional. See `PHILOSOPHY.md` § The OODARC Lens.

# Quick Router — 20 skills, 6 agents, and 56 commands

| You want to... | Run this |
|----------------|----------|
| Build a feature end-to-end | `/clavain:route` |
| Force full lifecycle | `/clavain:sprint` |
| Review code, docs, or plans | `/interflux:flux-drive` |
| Quick review from git diff | `/clavain:quality-gates` |
| Cross-AI second opinion | `/interpeer:interpeer` |
| Plan an implementation | `/clavain:write-plan` → `/clavain:work` |
| Fix a bug | `/clavain:repro-first-debugging` |
| Fix build/test failure | `/clavain:fixbuild` |
| Resolve review findings | `/clavain:resolve` |
| Set up a new project | `/clavain:project-onboard` |
| Check project health | `/clavain:clavain-doctor` or `/clavain:sprint-status` |
| Operate the portfolio agency | `/clavain:remontoire status` |
| One-shot situation snapshot (Observe) | `ic situation snapshot --run=<id>` |
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
