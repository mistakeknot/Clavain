# Clavain Routing Tables

Full routing reference for skills, agents, and commands. This is the detailed version of the compact router injected at session start.

For the compact version, see the `using-clavain` skill.

## Layer 1: What stage are you in?

| Stage | Primary Skills | Primary Commands | Key Agents |
|-------|---------------|-----------------|------------|
| **Explore** | brainstorming | brainstorm | interflux:research:repo-research-analyst, interflux:research:best-practices-researcher |
| **Plan** | writing-plans | write-plan, plan-review | interflux:fd-architecture, plan-reviewer |
| **Review (docs)** | flux-drive | flux-drive | (triaged from fd-* roster in interflux — adaptive 4-12 agents)¹ |
| **Execute** | executing-plans, subagent-driven-development, dispatching-parallel-agents, clodex | work, execute-plan, sprint², resolve, debate | — |
| **Debug** | systematic-debugging | repro-first-debugging | bug-reproduction-validator, interflux:research:git-history-analyzer |
| **Review** | code-review-discipline | review, quality-gates, plan-review, migration-safety, agent-native-audit, interpeer | interflux:fd-architecture, fd-safety, fd-correctness, fd-quality, fd-performance, fd-user-product |
| **Ship** | landing-a-change, verification-before-completion | changelog, triage, compound | interflux:fd-safety |
| **Meta** | writing-skills, developing-claude-code-plugins, working-with-claude-code, upstream-sync, create-agent-skills | setup, help, doctor, sprint-status, create-agent-skill, generate-command, heal-skill, upstream-sync | — |

## Layer 2: What domain?

| Domain | Skills | Agents |
|--------|--------|--------|
| **Code** | test-driven-development, finding-duplicate-functions, refactor-safely | interflux:fd-architecture, interflux:fd-quality, agent-native-reviewer |
| **Data** | — | interflux:fd-correctness, data-migration-expert |
| **Deploy** | — | interflux:fd-safety |
| **Docs** | engineering-docs | interflux:research:framework-docs-researcher, interflux:research:learnings-researcher |
| **Research** | mcp-cli | interflux:research:best-practices-researcher, interflux:research:repo-research-analyst, interflux:research:git-history-analyzer |
| **Workflow** | file-todos, slack-messaging, clodex | pr-comment-resolver, sprint-status |
| **Design** | distinctive-design | — |
| **Infra** | using-tmux-for-interactive-commands, agent-native-architecture | — |

## Layer 3: What concern? (optional — applies to review stage)

| Concern | Agent |
|---------|-------|
| Architecture, boundaries, patterns | interflux:fd-architecture |
| Security, credentials, trust boundaries | interflux:fd-safety |
| Data integrity, concurrency, async | interflux:fd-correctness |
| Naming, conventions, language idioms | interflux:fd-quality |
| User flows, UX, product reasoning | interflux:fd-user-product |
| Performance, bottlenecks, scaling | interflux:fd-performance |
| Game design, balance, pacing, emergent behavior | interflux:fd-game-design |
| Database migrations | data-migration-expert |
| Agent-native design | agent-native-reviewer |

## Which review command?

| Command | Use when... | Input |
|---------|------------|-------|
| `/interflux:flux-drive` | Deep review of documents, plans, repos, or large diffs with scored agent triage | File, directory, or diff |
| `/clavain:quality-gates` | Quick code review of working changes (auto-selects agents from git diff) | None (uses git diff) |
| `/clavain:review` | PR-focused multi-agent review | PR number, URL, or branch |
| `/clavain:plan-review` | Lightweight 3-agent plan review | Plan file |
| `/interflux:flux-gen` | Generate project-specific domain review agents in `.claude/agents/` | Optional: domain name |

**Default:** If unsure, use `/interflux:flux-drive` — it handles the widest range of inputs and auto-triages agents.

¹ **flux-drive agents (fd-*)**: 7 core review agents in the interflux companion plugin that auto-detect project docs (CLAUDE.md/AGENTS.md) for codebase-aware analysis.

² **`/sprint` discovery mode**: With no arguments, `/sprint` scans open beads, ranks by priority, and presents the top options via AskUserQuestion. User picks a bead and gets routed to the right command. With arguments, `/sprint` runs the full 9-step pipeline as before.

## Cross-AI Review

`interpeer` is the unified cross-AI review skill with escalating modes:

| Mode | What it does | Speed |
|------|-------------|-------|
| `quick` (default) | Claude↔Codex auto-detect | Seconds |
| `deep` | Oracle with prompt review | Minutes |
| `council` | Multi-model synthesis | Slowest |
| `mine` | Disagreement → tests/specs | N/A |

Say "go deeper" to escalate from quick → deep → council → mine.

For Oracle CLI reference, see `interpeer/references/oracle-reference.md`.

## Skill Priority

When multiple skills could apply, use this order:

1. **Process skills first** (brainstorming, debugging, TDD) — these determine HOW to approach the task
2. **Domain skills second** (distinctive-design, refactor-safely) — these guide execution
3. **Meta skills last** (writing-skills, developing-claude-code-plugins) — only when explicitly meta

"Let's build X" → brainstorming first, then domain skills.
"Fix this bug" → systematic-debugging first, then domain-specific skills.
"Review this code" → code-review-discipline first, then language-specific reviewers.
