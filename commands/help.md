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
| `/clavain:resolve` | Auto-resolve findings from any source |
| `/clavain:fixbuild` | Fix build/test failures |

### Review
| `/interflux:flux-drive` | Deep multi-agent review (any input type) |
|---|---|
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
| `/clavain:triage` | Prioritize and categorize open issues |
| `/clavain:compound` | Document a solved problem for future reference |
| `/clavain:smoke-test` | Run smoke tests on agent dispatch |

### Debug
| `/clavain:repro-first-debugging` | Disciplined reproduce-first bug investigation |
|---|---|

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

For the full routing guide with skills and agents, use the `using-clavain` skill.
