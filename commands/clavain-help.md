---
name: clavain-help
description: Show Clavain commands organized by daily drivers first, then by workflow stage
---

# Clavain Help

## Daily Drivers

| Command | Purpose | Example |
|---------|---------|---------|
| `/clavain:route` | Adaptive entry — discovers, classifies, dispatches | `/route build a caching layer` |
| `/clavain:brainstorm` | 4-phase brainstorm → auto-handoff to write-plan | `/brainstorm how should we handle auth?` |
| `/clavain:write-plan` | Create implementation plan with bite-sized tasks | `/write-plan` |
| `/clavain:tdd` | RED-GREEN-REFACTOR before coding | `/tdd implement auth refresh flow` |
| `/clavain:work` | Execute plan with quality checkpoints | `/work docs/plans/2026-02-11-auth.md` |
| `/interflux:flux-drive` | Deep multi-agent review (any input) | `/flux-drive docs/plans/my-plan.md` |
| `/clavain:quality-gates` | Gate orchestrator — delegates to flux-drive, enforces pass/fail | `/quality-gates` |
| `/clavain:resolve` | Fix findings from TODOs/PR comments | `/resolve` |
| `/clavain:remontoire` | Operate the portfolio agency across hosts | `/remontoire status` |
| `/interpeer:interpeer` | Cross-AI peer review (Claude ↔ Codex/Oracle) | `/interpeer` |

## By Stage

### Explore
| `/clavain:brainstorm` | Structured brainstorm → plan |
|---|---|
| `/clavain:strategy` | PRD creation + beads tracking |
| `/clavain:recall` | Search all knowledge systems |
| `/clavain:debate` | Claude ↔ Codex debate before implementing |

### Plan
| `/clavain:write-plan` | Implementation plan |
|---|---|
| `/clavain:plan-review` | Lightweight 3-agent plan review |

### Execute
| `/clavain:route` | Adaptive entry |
|---|---|
| `/clavain:remontoire` | Shadow, propose, inspect, approve, decline, resume, and verify receipts |
| `/clavain:work` | Execute plans |
| `/clavain:execute-plan` | Execute in separate session |
| `/clavain:sprint` | Full autonomous pipeline |
| `/clavain:resolve` | Auto-resolve findings |
| `/clavain:fixbuild` | Fix build/test failures |

### Review
| `/interflux:flux-drive` | Deep multi-agent review |
|---|---|
| `/clavain:review-discipline` | Disciplined code review + feedback triage |
| `/clavain:quality-gates` | Quick review from git diff |
| `/clavain:clavain-review` | PR-focused multi-agent review |
| `/clavain:review-doc` | Single-pass doc refinement |
| `/interpeer:interpeer` | Cross-AI peer review |
| `/clavain:migration-safety` | DB migration safety checks |
| `/clavain:pr-triage` | Batch PR triage with fd-* agents |
| `/interflux:flux-gen` | Generate domain-specific review agents |

### Ship
| `/clavain:changelog` | Changelog from recent commits |
|---|---|
| `/clavain:verify` | Verification checks before done |
| `/clavain:todos` | File-based follow-up tracking |
| `/clavain:triage` | Prioritize open issues |
| `/clavain:land` | Landing checklist |
| `/clavain:compound` | Document solved problems |
| `/clavain:smoke-test` | Smoke tests on agent dispatch |

### Debug
| `/clavain:repro-first-debugging` | Reproduce-first bug investigation |
|---|---|
| `/clavain:refactor` | Refactors with duplication/risk controls |

### Guardrails
| `/clavain:freeze` | Restrict edits to declared paths (scope lock) |
|---|---|
| `/clavain:unfreeze` | Lift the scope lock |

### Meta
| `/clavain:project-onboard` | Set up project with Sylveste automation |
|---|---|
| `/clavain:setup` | Bootstrap Clavain |
| `/clavain:clavain-help` | This command |
| `/clavain:clavain-doctor` | Health check |
| `/clavain:codex-bootstrap` | Keep Codex installation fresh |
| `/clavain:create-agent-skill` | Create agent skills |
| `/clavain:generate-command` | Scaffold a new command |
| `/clavain:heal-skill` | Fix broken skills |
| `/clavain:upstream-sync` | Check upstream for updates |
| `/clavain:clodex-toggle` | Toggle Codex delegation mode |
| `/clavain:sprint-status` | Sprint workflow state + recommendations |
| `/clavain:model-routing` | Configure model routing |
| `/clavain:interserve` | Launch full Codex workflow for large tasks |
| `/clavain:clavain-status` | Unified status across Clavain, artifacts, drift |
| `/clavain:update-check` | Report available updates without changing anything |
| `/clavain:distill` | Synthesize docs into categorized solutions |
| `/clavain:galiana` | Discipline analytics — KPIs, defects, cache |

### Beads & goals
| `/clavain:next-goal` | Propose leverage-ranked successor goals |
|---|---|
| `/clavain:goal-form` | Collaborative goal-formation ritual |
| `/clavain:campaign` | Orchestrate epic execution across phases |
| `/clavain:bead-sweep` | Find stale beads already implemented |
| `/clavain:sprint-dag` | Visualize sprint execution as a DAG |
| `/clavain:reflect` | Capture sprint learnings |
| `/clavain:describe-pr` | PR title + description from branch commits |
| `/clavain:clavain-init` | Scaffold .clavain/ in the current project |
| `/clavain:peers` | View detected peer agent rigs |

Most commands above are **user-invocable only** — type them; Claude won't reach
for them on its own. That keeps their descriptions out of every session's
context. The daily drivers (`route`, `work`, `sprint`, `ship`, `verify`,
`quality-gates`) and anything `/clavain:route` dispatches to stay auto-invocable.

For the full routing guide with skills and agents, use the `using-clavain` skill.
