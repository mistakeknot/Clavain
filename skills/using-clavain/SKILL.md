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

**In other environments:** Check your platform's documentation for how skills are loaded.

# Using Clavain

Clavain provides 32 skills, 23 agents, and 25 commands. To avoid overwhelm, use the **3-layer routing** below to find the right component.

## The Rule

**Invoke relevant skills BEFORE any response or action.** Even a 1% chance a skill might apply means you should invoke it.

## 3-Layer Routing

### Layer 1: What stage are you in?

| Stage | Primary Skills | Primary Commands | Key Agents |
|-------|---------------|-----------------|------------|
| **Explore** | brainstorming | brainstorm | repo-research-analyst, best-practices-researcher |
| **Plan** | writing-plans | write-plan, plan-review | architecture-strategist, spec-flow-analyzer |
| **Review (docs)** | flux-drive | flux-drive | (triaged from roster — up to 8 agents) |
| **Execute** | executing-plans, subagent-driven-development, dispatching-parallel-agents, codex-delegation | work, execute-plan, lfg, resolve-parallel, resolve-todo-parallel, resolve-pr-parallel, codex-first, clodex | — |
| **Debug** | systematic-debugging | repro-first-debugging | bug-reproduction-validator, git-history-analyzer |
| **Review** | requesting-code-review, receiving-code-review | review, quality-gates, plan-review, migration-safety, agent-native-audit | kieran-{go,python,typescript,shell}-reviewer, security-sentinel, performance-oracle, concurrency-reviewer, code-simplicity-reviewer |
| **Ship** | landing-a-change, verification-before-completion | changelog, triage | deployment-verification-agent |
| **Meta** | writing-skills, developing-claude-code-plugins, working-with-claude-code, upstream-sync, create-agent-skills | create-agent-skill, generate-command, heal-skill, upstream-sync | — |

### Layer 2: What domain?

| Domain | Skills | Agents |
|--------|--------|--------|
| **Code** | test-driven-development, finding-duplicate-functions, refactor-safely | pattern-recognition-specialist, code-simplicity-reviewer, agent-native-reviewer |
| **Data** | — | data-integrity-reviewer, data-migration-expert |
| **Deploy** | — | deployment-verification-agent |
| **Docs** | engineering-docs | framework-docs-researcher, learnings-researcher |
| **Research** | mcp-cli | best-practices-researcher, repo-research-analyst, git-history-analyzer |
| **Workflow** | file-todos, beads-workflow, oracle-review, slack-messaging, agent-mail-coordination, codex-first-dispatch, codex-delegation | pr-comment-resolver |
| **Design** | distinctive-design | — |
| **Infra** | using-tmux-for-interactive-commands, agent-native-architecture | — |

### Layer 3: What language? (optional — applies to review stage)

| Language | Agent |
|----------|-------|
| Go (.go) | kieran-go-reviewer |
| Python (.py) | kieran-python-reviewer |
| TypeScript (.ts/.tsx) | kieran-typescript-reviewer |
| Shell (.sh/.bash) | kieran-shell-reviewer |
| Any async/concurrent code | concurrency-reviewer |
| Any with security surface | security-sentinel |
| Any with perf concerns | performance-oracle |

### Cross-AI (Oracle)

When Oracle is available (detected at session start), it can supplement any review stage with a GPT-5.2 Pro perspective. See `oracle-review` skill for invocation.

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

## Skill Types

**Rigid** (TDD, debugging, verification): Follow exactly. Don't adapt away discipline.

**Flexible** (patterns, design): Adapt principles to context.

The skill itself tells you which.

## Plugin Conflicts

Clavain replaces these official plugins (disabled in settings): code-review, pr-review-toolkit, code-simplifier, commit-commands, feature-dev, claude-md-management, frontend-design, hookify. If you see duplicate agent names in the Task tool roster, check `docs/plugin-audit.md` for resolution.

## User Instructions

Instructions say WHAT, not HOW. "Add X" or "Fix Y" doesn't mean skip workflows.

## Key Commands Quick Reference

| Command | When |
|---------|------|
| `/clavain:lfg [description]` | Full autonomous workflow (brainstorm → plan → execute → review) |
| `/clavain:brainstorm [idea]` | Explore before planning |
| `/clavain:write-plan [spec]` | Create implementation plan |
| `/clavain:work [plan]` | Execute a plan |
| `/clavain:review [PR/branch]` | Multi-agent code review |
| `/clavain:quality-gates` | Auto-select reviewers for current changes |
| `/clavain:repro-first-debugging` | Disciplined bug investigation |
| `/clavain:changelog` | Generate changelog from recent commits |
| `/clavain:triage [findings]` | Triage and categorize findings |
| `/clavain:migration-safety [migration]` | Database migration safety review |
| `/clavain:learnings` | Capture solved problem as documentation |
| `/clavain:upstream-sync` | Check upstream repos for updates, generate upgrade checklist |
| `/clavain:setup` | Bootstrap modpack — install plugins, disable conflicts, verify MCP |
