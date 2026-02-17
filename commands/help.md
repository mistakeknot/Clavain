---
name: help
description: Show Clavain commands organized by daily drivers first, then by workflow stage
---

# Clavain Help

## Daily Drivers

These are the commands you'll use most often:

| Command | What it does | Example |
|---------|-------------|---------|
| `/clavain:sprint` | Full autonomous workflow — brainstorm → plan → execute → review → ship | `/sprint build a caching layer` |
| `/clavain:brainstorm` | Structured 4-phase brainstorm with auto-handoff to write-plan | `/brainstorm how should we handle auth?` |
| `/clavain:write-plan` | Create detailed implementation plan with bite-sized tasks | `/write-plan` (after brainstorm) |
| `/clavain:tdd` | Run RED-GREEN-REFACTOR for a task before coding | `/tdd implement auth refresh flow` |
| `/clavain:work` | Execute a plan efficiently, maintaining quality | `/work docs/plans/2026-02-11-auth.md` |
| `/interflux:flux-drive` | Deep multi-agent review of any document, diff, or repo | `/flux-drive docs/plans/my-plan.md` |
| `/clavain:quality-gates` | Auto-select reviewers based on git diff | `/quality-gates` |
| `/clavain:resolve` | Fix findings from TODOs, PR comments, or todo files | `/resolve` |
| `/clavain:interpeer` | Quick cross-AI peer review (Claude ↔ Codex/Oracle) | `/interpeer` |

## By Stage

### Explore
| `/clavain:brainstorm` | Structured brainstorm → auto-handoff to plan |
|---|---|
| `/clavain:strategy` | Bridge brainstorm → plan with PRD creation and beads tracking |
| `/clavain:debate` | Structured Claude ↔ Codex debate before implementing |

### Plan
| `/clavain:write-plan` | Create implementation plan |
|---|---|
| `/clavain:plan-review` | Lightweight 3-agent plan review |

### Execute
| `/clavain:work` | Execute plans with quality checkpoints |
|---|---|
| `/clavain:execute-plan` | Execute plan in separate session with review checkpoints |
| `/clavain:sprint` | Full autonomous pipeline (brainstorm through ship) |
| `/clavain:codex-sprint` | Full sprint flow with Codex-first execution |
| `/clavain:resolve` | Auto-resolve findings from any source |
| `/clavain:fixbuild` | Fix build/test failures |

### Review
| `/interflux:flux-drive` | Deep multi-agent review (any input type) |
|---|---|
| `/clavain:code-review` | Rigorous code review and feedback triage | `/code-review` |
| `/clavain:quality-gates` | Quick code review from git diff |
| `/clavain:review` | PR-focused multi-agent review |
| `/clavain:review-doc` | Lightweight single-pass document refinement |
| `/clavain:interpeer` | Cross-AI peer review (quick/deep/council/mine modes) |
| `/clavain:migration-safety` | Database migration safety checks |
| `/clavain:triage-prs` | Batch PR backlog triage with fd-* agents |
| `/interflux:flux-gen` | Generate domain-specific review agents for your project |

### Ship
| `/clavain:changelog` | Generate changelog from recent commits |
|---|---|
| `/clavain:verify` | Run verification checks before declaring work complete | `/verify` |
| `/clavain:todos` | Track follow-up and handoff work in file-based todos | `/todos` |
| `/clavain:triage` | Prioritize and categorize open issues |
| `/clavain:land` | Apply landing checklist for safe handoff | `/land` |
| `/clavain:compound` | Document a solved problem for future reference |
| `/clavain:smoke-test` | Run smoke tests on agent dispatch |

### Docs
| Command | What it does | Example |
|---|---|---|
| `/clavain:docs` | Capture a solved problem as searchable engineering docs | `/docs` |

### Debug
| `/clavain:repro-first-debugging` | Disciplined reproduce-first bug investigation |
|---|---|
| `/clavain:refactor` | Run refactors with duplication/risk controls |

### Meta
| `/clavain:setup` | Bootstrap Clavain — install plugins, verify MCP, configure hooks |
|---|---|
| `/clavain:help` | This command |
| `/clavain:doctor` | Health check — MCP servers, tools, beads, plugin conflicts |
| `/clavain:codex-bootstrap` | Keep Codex Clavain installation fresh (install + doctor + wrappers) |
| `/clavain:create-agent-skill` | Create new agent skills |
| `/clavain:generate-command` | Scaffold a new command |
| `/clavain:heal-skill` | Fix broken skills |
| `/clavain:upstream-sync` | Check upstream repos for updates |
| `/clavain:clodex-toggle` | Toggle Codex delegation mode |
| `/clavain:sprint-status` | Deep scan of sprint workflow state and recommendations |
| `/clavain:model-routing` | Configure model routing for agents |
| `/clavain:interserve` | Launch full Codex workflow for larger tasks | `/interserve` |

For the full routing guide with skills and agents, use the `using-clavain` skill.
