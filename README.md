# Clavain

General-purpose engineering discipline plugin for Claude Code. 31 skills, 23 agents, 22 commands, 2 hooks, 2 MCP servers.

Merged from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Install

```bash
# From marketplace (once published)
claude plugin install clavain@interagency-marketplace

# Local development
claude --plugin-dir /path/to/Clavain
```

## What's Included

### Skills (30)

Process discipline skills that guide HOW you work:

| Skill | Purpose |
|-------|---------|
| `using-clavain` | Bootstrap routing — maps tasks to skills/agents/commands |
| `brainstorming` | Structured exploration before planning |
| `writing-plans` | Create implementation plans with bite-sized tasks |
| `executing-plans` | Execute plans with review checkpoints |
| `test-driven-development` | RED-GREEN-REFACTOR cycle |
| `systematic-debugging` | Evidence-first bug investigation |
| `verification-before-completion` | Verify before claiming done |
| `landing-a-change` | Trunk-based finish checklist |
| `refactor-safely` | Disciplined refactoring playbook |
| `subagent-driven-development` | Parallel subagent execution |
| `dispatching-parallel-agents` | When/how to parallelize |
| `requesting-code-review` | Dispatch reviewer subagents |
| `receiving-code-review` | Handle review feedback |
| `distinctive-design` | Anti-AI-slop visual aesthetic |
| `oracle-review` | GPT-5.2 Pro cross-AI review |
| `beads-workflow` | bd CLI issue tracking |
| `engineering-docs` | Capture solved problems as docs |
| `file-todos` | File-based todo tracking |
| `agent-native-architecture` | Build agent-first applications |
| `create-agent-skills` | Write Claude Code skills/agents |
| `developing-claude-code-plugins` | Plugin development patterns |
| `working-with-claude-code` | Claude Code CLI reference |
| `writing-skills` | TDD for skill documentation |
| `using-tmux-for-interactive-commands` | Interactive CLI in tmux |
| `slack-messaging` | Slack integration |
| `mcp-cli` | On-demand MCP server usage |
| `finding-duplicate-functions` | Semantic dedup detection |
| `flux-drive` | Intelligent document/repo review with agent triage |
| `agent-mail-coordination` | Multi-agent coordination via MCP Agent Mail |
| `codex-delegation` | Execute plan tasks via Codex agents (interclode bridge) |
| `upstream-sync` | Track updates from upstream tool repos |
| `codex-delegation` | Parallel implementation via Codex agents (interclode) |

### Agents (23)

Specialized execution agents dispatched by commands and skills:

**Review (15):** architecture-strategist, code-simplicity-reviewer, pattern-recognition-specialist, performance-oracle, security-sentinel, agent-native-reviewer, kieran-python-reviewer, kieran-typescript-reviewer, kieran-go-reviewer, kieran-shell-reviewer, concurrency-reviewer, plan-reviewer, data-migration-expert, data-integrity-reviewer, deployment-verification-agent

**Research (5):** best-practices-researcher, framework-docs-researcher, git-history-analyzer, learnings-researcher, repo-research-analyst

**Workflow (3):** pr-comment-resolver, spec-flow-analyzer, bug-reproduction-validator

### Commands (22)

User-invoked slash commands:

| Command | Purpose |
|---------|---------|
| `/clavain:lfg` | Full autonomous workflow |
| `/clavain:brainstorm` | Explore before planning |
| `/clavain:write-plan` | Create implementation plan |
| `/clavain:flux-drive` | Intelligent document/repo review with agent triage |
| `/clavain:work` | Execute a plan |
| `/clavain:review` | Multi-agent code review |
| `/clavain:execute-plan` | Execute plan in batches |
| `/clavain:plan_review` | Parallel plan review |
| `/clavain:quality-gates` | Auto-select reviewers |
| `/clavain:repro-first-debugging` | Disciplined bug investigation |
| `/clavain:migration-safety` | Data migration risk assessment |
| `/clavain:learnings` | Document solved problems |
| `/clavain:changelog` | Generate changelog |
| `/clavain:triage` | Categorize findings |
| `/clavain:resolve_parallel` | Resolve TODOs in parallel |
| `/clavain:resolve_pr_parallel` | Resolve PR comments in parallel |
| `/clavain:resolve_todo_parallel` | Resolve file TODOs in parallel |
| `/clavain:agent-native-audit` | Agent-native architecture review |
| `/clavain:create-agent-skill` | Create skills/agents |
| `/clavain:generate_command` | Generate new commands |
| `/clavain:heal-skill` | Fix broken skills |
| `/clavain:upstream-sync` | Check upstream repos for updates |

### Hooks (2)

- **SessionStart** — Injects `using-clavain` skill content as context on every session start, resume, clear, and compact

### MCP Servers (2)

- **context7** — Library documentation lookup via [Context7](https://context7.com)
- **mcp-agent-mail** — Multi-agent coordination, file reservations, messaging via [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail)

## Architecture

```
clavain/
├── .claude-plugin/plugin.json    # Manifest
├── skills/                        # 30 discipline skills (SKILL.md each)
├── agents/
│   ├── review/                    # 15 code review agents
│   ├── research/                  # 5 research agents
│   └── workflow/                  # 3 workflow agents
├── commands/                      # 22 slash commands
├── hooks/
│   ├── hooks.json                 # Hook registration
│   └── session-start.sh           # Context injection script
├── lib/                           # Shared utilities
└── docs-sp-reference/             # Historical superpowers documentation
```

## How It Works

The `using-clavain` skill is injected into every session via the SessionStart hook. It provides a 3-layer routing system:

1. **Stage** — What phase are you in? (explore/plan/execute/debug/review/ship/meta)
2. **Domain** — What kind of work? (code/data/deploy/docs/research/workflow)
3. **Language** — What language? (go/py/ts/sh/markdown)

This routes you to the right skill, agent, or command for each task.

## Credits

Built on the work of:

- **Jesse Vincent** ([@obra](https://github.com/obra)) — [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code)
- **Kieran Klaassen** ([@kieranklaassen](https://github.com/kieranklaassen)) — [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin) at [Every](https://every.to)
- **Steve Yegge** ([@steveyegge](https://github.com/steveyegge)) — [beads](https://github.com/steveyegge/beads)
- **Peter Steinberger** ([@steipete](https://github.com/steipete)) — [oracle](https://github.com/steipete/oracle)
- **Jeff Emanuel** ([@Dicklesworthstone](https://github.com/Dicklesworthstone)) — [mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail)

## License

MIT
