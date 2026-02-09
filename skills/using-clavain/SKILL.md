---
name: using-clavain
description: Use when starting any conversation - establishes how to find and use skills, agents, and commands, requiring Skill tool invocation before ANY response including clarifying questions
---

<EXTREMELY-IMPORTANT>
If you think there is even a 1% chance a skill might apply to what you are doing, you ABSOLUTELY MUST invoke the skill.

IF A SKILL APPLIES TO YOUR TASK, YOU DO NOT HAVE A CHOICE. YOU MUST USE IT.

This is not negotiable. This is not optional. You cannot rationalize your way out of this.
</EXTREMELY-IMPORTANT>

## How to Access Skills

**In Claude Code:** Use the `Skill` tool. When you invoke a skill, its content is loaded and presented to you—follow it directly. Never use the Read tool on skill files.

**In Codex CLI:** Install Clavain skills with `bash ~/.codex/clavain/scripts/install-codex.sh install`. Codex discovers them from `~/.agents/skills/clavain/` on startup, so restart Codex after install.

**In other environments:** Check your platform's documentation for how skills are loaded.

# Using Clavain

Clavain provides 34 skills, 26 agents, and 24 commands. To avoid overwhelm, use the **3-layer routing** below to find the right component.

## The Rule

**Invoke relevant skills BEFORE any response or action.** Even a 1% chance a skill might apply means you should invoke it.

## 3-Layer Routing

### Layer 1: What stage are you in?

| Stage | Primary Skills | Primary Commands | Key Agents |
|-------|---------------|-----------------|------------|
| **Explore** | brainstorming | brainstorm | repo-research-analyst, best-practices-researcher |
| **Plan** | writing-plans | write-plan, plan-review | architecture-strategist, spec-flow-analyzer |
| **Review (docs)** | flux-drive | flux-drive | (triaged from roster — up to 8 agents)¹ |
| **Execute** | executing-plans, subagent-driven-development, dispatching-parallel-agents, clodex | work, execute-plan, lfg, resolve, codex-first, debate | — |
| **Debug** | systematic-debugging | repro-first-debugging | bug-reproduction-validator, git-history-analyzer |
| **Review** | requesting-code-review, receiving-code-review | review, quality-gates, plan-review, migration-safety, agent-native-audit, interpeer | {go,python,typescript,shell,rust}-reviewer, security-sentinel, performance-oracle, concurrency-reviewer, code-simplicity-reviewer |
| **Ship** | landing-a-change, verification-before-completion | changelog, triage, compound | deployment-verification-agent |
| **Meta** | writing-skills, developing-claude-code-plugins, working-with-claude-code, upstream-sync, create-agent-skills | setup, create-agent-skill, generate-command, heal-skill, upstream-sync | — |

### Layer 2: What domain?

| Domain | Skills | Agents |
|--------|--------|--------|
| **Code** | test-driven-development, finding-duplicate-functions, refactor-safely | pattern-recognition-specialist, code-simplicity-reviewer, agent-native-reviewer |
| **Data** | — | data-integrity-reviewer, data-migration-expert |
| **Deploy** | — | deployment-verification-agent |
| **Docs** | engineering-docs | framework-docs-researcher, learnings-researcher |
| **Research** | mcp-cli | best-practices-researcher, repo-research-analyst, git-history-analyzer |
| **Workflow** | file-todos, beads-workflow, slack-messaging, agent-mail-coordination, clodex | pr-comment-resolver |
| **Design** | distinctive-design | — |
| **Infra** | using-tmux-for-interactive-commands, agent-native-architecture | — |

### Layer 3: What language? (optional — applies to review stage)

| Language | Agent |
|----------|-------|
| Go (.go) | go-reviewer |
| Python (.py) | python-reviewer |
| TypeScript (.ts/.tsx) | typescript-reviewer |
| Shell (.sh/.bash) | shell-reviewer |
| Rust (.rs) | rust-reviewer |
| Any async/concurrent code | concurrency-reviewer |
| Any with security surface | security-sentinel |
| Any with perf concerns | performance-oracle |

¹ **flux-drive agents (fd-*)**: `fd-user-experience` and `fd-code-quality` are codebase-aware reviewers auto-selected by flux-drive's triage system. Don't invoke them directly — use `/clavain:flux-drive` which selects the right subset. The `architecture-strategist`, `security-sentinel`, and `performance-oracle` agents now auto-detect project docs and switch between codebase-aware and generic modes.

### Cross-AI Review

`interpeer` is the unified cross-AI review skill with escalating modes:

| Mode | What it does | Speed |
|------|-------------|-------|
| `quick` (default) | Claude↔Codex auto-detect | Seconds |
| `deep` | Oracle with prompt review | Minutes |
| `council` | Multi-model synthesis | Slowest |
| `mine` | Disagreement → tests/specs | N/A |

Say "go deeper" to escalate from quick → deep → council → mine.

For Oracle CLI reference, see `interpeer/references/oracle-reference.md`.

## Routing Heuristic

When a user message arrives:

1. **Detect stage** from the request ("build" → Execute, "fix bug" → Debug, "review" → Review, "plan" → Plan, "what should we" → Explore)
2. **Detect domain** from context (file types, topic, recent conversation)
3. **Pick top 3-5 components** from the routing tables above
4. **Invoke the primary skill** first (process skills before implementation skills)
5. **Suggest agents/commands** as needed during execution

## Red Flag

If you catch yourself thinking "I'll just do this without a skill" — STOP. Check for a matching skill first. Skills evolve; read the current version even if you "remember" it.

## Skill Priority

When multiple skills could apply, use this order:

1. **Process skills first** (brainstorming, debugging, TDD) — these determine HOW to approach the task
2. **Domain skills second** (distinctive-design, refactor-safely) — these guide execution
3. **Meta skills last** (writing-skills, developing-claude-code-plugins) — only when explicitly meta

"Let's build X" → brainstorming first, then domain skills.
"Fix this bug" → systematic-debugging first, then domain-specific skills.
"Review this code" → requesting-code-review first, then language-specific reviewers.
