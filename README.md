# Clavain

Clavain, named after one of the protagonists from Alastair Reynolds's [Revelation Space series](https://en.wikipedia.org/wiki/Revelation_Space_series), is a **highly** opinionated Claude Code plugin that encapsulates how I personally like to use Claude Code to build things. I do not think it is the best way for everyone, but it works very well for me and I hope it can, at the very least, provide some inspiration for your own Claude Code experience.

With 31 skills, 23 agents, 25 commands, 3 hooks, and 2 MCP servers, there is a lot here (and it is constantly changing). Before installing, I would probably recommend you point Claude Code to this directory and ask it to review this plugin against how you like to work. It's especially helpful if [you run `/insights` first](https://x.com/trq212/status/2019173731042750509) so Claude Code can evaluate Clavin against your actual historical workflow.

Merged, modified, and maintained with updates from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Install

```bash
# From marketplace
claude plugin install clavain@interagency-marketplace

# Local development
claude --plugin-dir /path/to/Clavain
```

## What's Included

### Skills (32)

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
| `clodex` | Codex dispatch — megaprompt for single tasks, parallel delegation for many, with debate and Oracle escalation |
| `upstream-sync` | Track updates from upstream tool repos |

### Agents (23)

Specialized execution agents dispatched by commands and skills:

**Review (15):** architecture-strategist, code-simplicity-reviewer, pattern-recognition-specialist, performance-oracle, security-sentinel, agent-native-reviewer, kieran-python-reviewer, kieran-typescript-reviewer, kieran-go-reviewer, kieran-shell-reviewer, concurrency-reviewer, plan-reviewer, data-migration-expert, data-integrity-reviewer, deployment-verification-agent

**Research (5):** best-practices-researcher, framework-docs-researcher, git-history-analyzer, learnings-researcher, repo-research-analyst

**Workflow (3):** pr-comment-resolver, spec-flow-analyzer, bug-reproduction-validator

### Commands (24)

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
| `/clavain:plan-review` | Parallel plan review |
| `/clavain:quality-gates` | Auto-select reviewers |
| `/clavain:repro-first-debugging` | Disciplined bug investigation |
| `/clavain:migration-safety` | Data migration risk assessment |
| `/clavain:compound` | Document solved problems |
| `/clavain:changelog` | Generate changelog |
| `/clavain:triage` | Categorize findings |
| `/clavain:resolve-parallel` | Resolve TODOs in parallel |
| `/clavain:resolve-pr-parallel` | Resolve PR comments in parallel |
| `/clavain:resolve-todo-parallel` | Resolve file TODOs in parallel |
| `/clavain:agent-native-audit` | Agent-native architecture review |
| `/clavain:create-agent-skill` | Create skills/agents |
| `/clavain:generate-command` | Generate new commands |
| `/clavain:heal-skill` | Fix broken skills |
| `/clavain:clodex-toggle` | Toggle codex-first execution mode (short alias) |
| `/clavain:codex-first` | Toggle codex-first execution mode |
| `/clavain:debate` | Structured Claude↔Codex debate |
| `/clavain:upstream-sync` | Check upstream repos for updates |

### Hooks (3)

- **PreToolUse** — Autopilot gate: when codex-first mode is active (flag file exists), denies Edit/Write/MultiEdit/NotebookEdit and directs Claude to dispatch changes through Codex agents.
- **SessionStart** — Injects `using-clavain` skill content as context on every session start, resume, clear, and compact. Also warns when upstream baseline (`docs/upstream-versions.json`) is stale (>7 days).

### MCP Servers (2)

- **context7** — Library documentation lookup via [Context7](https://context7.com)
- **mcp-agent-mail** — Multi-agent coordination, file reservations, messaging via [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail)

## Architecture

```
clavain/
├── .claude-plugin/plugin.json    # Manifest
├── skills/                        # 32 discipline skills (SKILL.md each)
├── agents/
│   ├── review/                    # 15 code review agents
│   ├── research/                  # 5 research agents
│   └── workflow/                  # 3 workflow agents
├── commands/                      # 24 slash commands
├── hooks/
│   ├── hooks.json                 # Hook registration (PreToolUse + SessionStart + SessionEnd)
│   ├── autopilot.sh               # Codex-first mode gate (blocks writes when active)
│   └── session-start.sh           # Context injection + staleness warning
├── scripts/
│   ├── dispatch.sh                # Codex exec wrapper with sensible defaults
│   ├── debate.sh                  # Structured 2-round Claude↔Codex debate
│   └── upstream-check.sh          # Checks upstream repos via gh api
├── docs/
│   └── upstream-versions.json     # Upstream sync baseline
└── .github/workflows/
    ├── upstream-check.yml         # Daily cron for upstream change detection
    └── sync.yml                   # Weekly auto-merge via Claude Code + Codex
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
