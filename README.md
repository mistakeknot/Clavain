# Clavain

Clavain, named after one of the protagonists from Alastair Reynolds's [Revelation Space series](https://en.wikipedia.org/wiki/Revelation_Space_series), is a **highly** opinionated Claude Code agent rig that encapsulates how I personally like to use Claude Code to build things. An agent rig, as I define it, is a collection of plugins, skills, and integrations that serves as a cohesive system for working with agents.

I do not think Clavain is the best workflow for everyone, but it works very well for me and I hope it can, at the very least, provide some inspiration for your own experiences with Claude Code.

With 34 skills, 28 agents, 27 commands, 3 hooks, and 2 MCP servers, there is a lot here (and it is constantly changing). Before installing, I recommend you point Claude Code to this directory and ask it to review this plugin against how you like to work. It's especially helpful if [you run `/insights` first](https://x.com/trq212/status/2019173731042750509) so Claude Code can evaluate Clavain against your actual historical usage patterns.

Merged, modified, and maintained with updates from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Install

```bash
# From marketplace
claude plugin install clavain@interagency-marketplace

# Local development
claude --plugin-dir /path/to/Clavain
```

## My Workflow

For simple requests, I type `/lfg add user export feature` and Claude brainstorms the approach, writes a plan, reviews the plan with multiple agents, implements the code, reviews the implementation, resolves any issues, and runs quality gates. One command, full lifecycle. Most of the time I just watch and approve.

For more complex endeavors (or new projects), I use Clavain's pieces individually depending on what I'm doing. The following review of the `/lfg` lifecycle provides a brief explanation of all the different parts of Clavain.

### The `/lfg` Lifecycle

`/lfg` chains seven commands together. Each one can also be invoked standalone:

```
/brainstorm  →  /write-plan  →  /flux-drive  →  /work  →  /review  →  /resolve-todo-parallel  →  /quality-gates
   explore        plan           review plan     execute    review code     fix issues              final check
```

I almost always start with `/brainstorm` even when I think I know what I want. It forces me to articulate requirements before touching code, and Claude often catches edge cases I hadn't considered. After brainstorming, `/write-plan` creates a structured implementation plan, and `/flux-drive` reviews that plan with up to 4 tiers of agents before any code is written.

### Reviewing Things with `/flux-drive`

`/flux-drive`, named after the [Flux Review](https://read.fluxcollective.org/), is probably the command I use most often on its own. Point it at a file, a plan, or an entire repo and it figures out which reviewers are relevant for the given context. It pulls from a roster of 28 agents across 4 tiers:

- **Tier 1** — Codebase-aware agents (architecture, code quality, security, performance, UX) that understand your actual project, not generic checklists
- **Tier 2** — Project-specific agents selected by tech stack (Go reviewer for Go projects, Python reviewer for Python, etc.)
- **Tier 3** — Generic reviewers (concurrency, patterns, simplicity) when the document warrants them
- **Tier 4** — Oracle (GPT-5.2 Pro) for cross-AI perspective on complex decisions

It only launches what's relevant. A simple markdown doc might get 2 agents; a full repo review might get 8. The agents run in parallel in the background, and you get a synthesized report with findings prioritized by severity.

When Oracle is part of the review, `flux-drive` chains into the **interpeer stack** — comparing what Claude-based agents found against what GPT found, flagging disagreements, and optionally escalating critical decisions to a full multi-model council.

### Cross-Agent Review

Because different models and agents genuinely see different things, and the disagreements between them are often more valuable than what either finds alone, I find cross-agent review to be incredibly valuable, especially after a `flux-drive` run.

The interpeer stack escalates in depth:

| Command | What it does | Speed |
|---------|-------------|-------|
| `/interpeer` | Quick Claude↔Codex second opinion | Seconds |
| `prompterpeer` | Deep Oracle analysis with prompt optimization | Minutes |
| `winterpeer` | Full LLM Council — multi-model consensus | Slow |
| `splinterpeer` | Post-processor — turns disagreements into tests and specs | N/A |

`/interpeer` is the lightweight entry point. It auto-detects whether you're running in Claude Code or Codex CLI and calls the other one. For deeper analysis, `prompterpeer` builds optimized prompts for Oracle (GPT-5.2 Pro) and shows you the enhanced prompt before sending. `winterpeer` runs a full council when the stakes are high — critical architecture or security decisions where you want genuine consensus, not just one model's opinion.

`splinterpeer` is my favorite. It takes the *disagreements* between models and converts them into concrete artifacts: tests that would prove one side right, spec clarifications that would resolve ambiguity, and stakeholder questions that surface hidden assumptions.

### Codex-First Mode

Because Codex CLI has far higher usage limits than Claude Code, I like saving Claude Code usage by toggling `/clodex` or mentioning it in my request. In this mode, Claude reads, plans, and writes detailed prompts — but all code changes go through Codex agents. Claude crafts a megaprompt, dispatches it, reads the verdict, and decides if it's acceptable. Think of it as Claude being the tech lead and Codex being the engineer.

For multi-task work, `/clodex` parallelizes naturally. Five independent changes get five Codex agents dispatched simultaneously. Claude collects the results and commits.

### Structured Debate

`/debate` runs a structured 2-round argument between Claude and Codex before implementing a complex task. Each writes an independent position, then responds to the other's. If they fundamentally disagree on architecture or security, Oracle gets called in as a tiebreaker. The output is a synthesis with clear options for you to choose from.

I use this before any architectural decision I'm uncertain about. The debate itself costs less than building the wrong thing.

## What's Included

### Skills (34)

Skills are workflow disciplines — they guide **how** you work, not what tools to call. Each one is a markdown playbook that Claude follows step by step.

| Skill | What it does |
|-------|-------------|
| **Core Lifecycle** | |
| `brainstorming` | Structured exploration before planning |
| `writing-plans` | Create implementation plans with bite-sized tasks |
| `executing-plans` | Execute plans with review checkpoints |
| `verification-before-completion` | Verify before claiming done |
| `landing-a-change` | Trunk-based finish checklist |
| **Code Discipline** | |
| `test-driven-development` | RED-GREEN-REFACTOR cycle |
| `systematic-debugging` | Evidence-first bug investigation |
| `refactor-safely` | Disciplined refactoring with duplication detection |
| `finding-duplicate-functions` | Semantic dedup across codebase |
| **Multi-Agent** | |
| `flux-drive` | Intelligent document/repo review with agent triage |
| `subagent-driven-development` | Parallel subagent execution |
| `dispatching-parallel-agents` | When and how to parallelize |
| `requesting-code-review` | Dispatch reviewer subagents |
| `receiving-code-review` | Handle review feedback |
| **Cross-AI** | |
| `interpeer` | Auto-detecting Claude↔Codex review |
| `prompterpeer` | Oracle prompt optimizer with human review |
| `winterpeer` | LLM Council multi-model consensus |
| `splinterpeer` | Turn model disagreements into tests and specs |
| `clodex` | Codex dispatch — megaprompt, parallel delegation, debate, Oracle escalation |
| **Knowledge & Docs** | |
| `beads-workflow` | Git-native issue tracking via `bd` CLI |
| `engineering-docs` | Capture solved problems as searchable docs |
| `file-todos` | File-based todo tracking across sessions |
| `agent-native-architecture` | Build agent-first applications |
| `distinctive-design` | Anti-AI-slop visual aesthetic |
| **Plugin Development** | |
| `create-agent-skills` | Write Claude Code skills and agents |
| `developing-claude-code-plugins` | Plugin development patterns |
| `working-with-claude-code` | Claude Code CLI reference |
| `writing-skills` | TDD for skill documentation |
| **Utilities** | |
| `using-clavain` | Bootstrap routing — maps tasks to the right component |
| `using-tmux-for-interactive-commands` | Interactive CLI tools in tmux |
| `slack-messaging` | Slack integration |
| `mcp-cli` | On-demand MCP server usage |
| `agent-mail-coordination` | Multi-agent coordination via MCP Agent Mail |
| `upstream-sync` | Track updates from upstream tool repos |

### Agents (28)

Agents are specialized execution units dispatched by skills and commands. They run as subagents with their own context window.

**Review (20):** Codebase-aware reviewers (architecture, code quality, performance, security, UX), language-specific reviewers (Go, Python, TypeScript, Shell), cross-cutting specialists (architecture, security, performance, concurrency, patterns, simplicity, agent-native), data specialists (migration, integrity), deployment verification, and plan review.

**Research (5):** Best practices, framework docs, git history analysis, institutional learnings, and repo structure analysis.

**Workflow (3):** PR comment resolution, spec flow analysis, and bug reproduction validation.

### Commands (27)

Slash commands are the user-facing entry points. Most of them load a skill underneath.

| Command | What it does |
|---------|-------------|
| `/lfg` | Full autonomous lifecycle — brainstorm through ship |
| `/setup` | Bootstrap the modpack — install plugins, disable conflicts, verify servers |
| `/brainstorm` | Explore before planning |
| `/write-plan` | Create implementation plan |
| `/flux-drive` | Multi-agent document/repo review |
| `/work` | Execute a plan autonomously |
| `/review` | Multi-agent code review |
| `/execute-plan` | Execute plan in batches with checkpoints |
| `/plan-review` | Parallel plan review |
| `/quality-gates` | Auto-select the right reviewers |
| `/repro-first-debugging` | Disciplined bug investigation |
| `/clodex-toggle` | Toggle codex-first execution mode |
| `/codex-first` | Toggle codex-first execution mode (long form) |
| `/debate` | Structured Claude↔Codex debate |
| `/interpeer` | Quick cross-AI peer review |
| `/migration-safety` | Data migration risk assessment |
| `/compound` | Document solved problems |
| `/changelog` | Generate changelog from recent merges |
| `/triage` | Categorize and prioritize findings |
| `/resolve-parallel` | Resolve TODOs in parallel |
| `/resolve-pr-parallel` | Resolve PR comments in parallel |
| `/resolve-todo-parallel` | Resolve file TODOs in parallel |
| `/agent-native-audit` | Agent-native architecture review |
| `/create-agent-skill` | Create new skills or agents |
| `/generate-command` | Generate new commands |
| `/heal-skill` | Fix broken skills |
| `/upstream-sync` | Check upstream repos for updates |

*(All commands are prefixed with `/clavain:` when invoked.)*

### Hooks (3)

- **PreToolUse** — Codex-first gate: blocks Edit/Write when codex-first mode is active, directing changes through Codex agents instead.
- **SessionStart** — Injects the `using-clavain` routing table into every session (start, resume, clear, compact). Also warns when upstream tracking is stale.
- **SessionEnd** — Syncs dotfile changes at end of session.

### MCP Servers (2)

- **context7** — Library documentation lookup via [Context7](https://context7.com)
- **mcp-agent-mail** — Multi-agent coordination, file reservations, and messaging via [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail)

## The Agent Rig

Clavain is designed as an **agent rig**, inspired by [PC game mod packs](https://en.wikipedia.org/wiki/Video_game_modding#Mod_packs). It is an opinionated integration layer that configures companion plugins into a cohesive rig. Instead of duplicating their capabilities, Clavain routes to them and wires them together.

### Required Companions

| Plugin | Why |
|--------|-----|
| [context7](https://context7.com) | Runtime doc fetching. Clavain's skills use it to pull library docs without bundling them. |
| [explanatory-output-style](https://github.com/claude-plugins-official) | Educational insights in output. Injected via SessionStart hook. |

### Recommended

| Plugin | What it adds |
|--------|-------------|
| [interdoc](https://github.com/interagency-marketplace) | AGENTS.md generation for any repo |
| [interclode](https://github.com/interagency-marketplace) | Codex CLI dispatch infrastructure — powers `/clodex` |
| [agent-sdk-dev](https://github.com/claude-plugins-official) | Agent SDK scaffolding |
| [plugin-dev](https://github.com/claude-plugins-official) | Plugin development tools |
| [serena](https://github.com/claude-plugins-official) | Semantic code analysis via LSP-like tools |
| [tool-time](https://github.com/interagency-marketplace) | Tool usage analytics across sessions |

### Disabled (Conflicts)

Clavain replaces these plugins with its own opinionated equivalents. Keeping both causes duplicate agents and confusing routing.

| Plugin | Clavain Replacement |
|--------|-------------------|
| code-review | `/review` + `/flux-drive` + 20 review agents |
| pr-review-toolkit | Same agent types exist in Clavain's review roster |
| code-simplifier | `code-simplicity-reviewer` agent |
| commit-commands | `landing-a-change` skill |
| feature-dev | `/work` + `/lfg` + `/brainstorm` |

## Customization

Clavain is opinionated but not rigid. A few things worth knowing:

**Tier 2 agents are project-specific.** `flux-drive` selects language reviewers based on your tech stack. If you're working in a language that doesn't have a Kieran reviewer (Rust, Java, etc.), it skips that tier gracefully.

**Skills can be overridden.** If you disagree with how `test-driven-development` works, you can create your own skill with the same name in a local plugin that loads after Clavain. Last-loaded wins.

**Codex-first mode is optional.** Everything works fine with Claude making changes directly. `/clodex` is there for when you want the orchestration pattern, not a requirement.

**Oracle requires setup.** The cross-AI features (`prompterpeer`, `winterpeer`, `flux-drive` Tier 4) need [Oracle](https://github.com/steipete/oracle) installed and configured. Without it, those features are simply skipped — nothing breaks.

## Architecture

```
clavain/
├── .claude-plugin/plugin.json    # Manifest
├── skills/                        # 34 discipline skills (SKILL.md each)
├── agents/
│   ├── review/                    # 20 code review agents
│   ├── research/                  # 5 research agents
│   └── workflow/                  # 3 workflow agents
├── commands/                      # 27 slash commands
├── hooks/
│   ├── hooks.json                 # Hook registration (PreToolUse + SessionStart + SessionEnd)
│   ├── autopilot.sh               # Codex-first mode gate (blocks writes when active)
│   ├── session-start.sh           # Context injection + staleness warning
│   ├── agent-mail-register.sh     # MCP Agent Mail session registration
│   └── dotfiles-sync.sh           # Dotfile sync on session end
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

### How the Routing Works

The `using-clavain` skill is injected into every session via the SessionStart hook. It provides a 3-layer routing system:

1. **Stage** — What phase are you in? (explore / plan / execute / debug / review / ship / meta)
2. **Domain** — What kind of work? (code / data / deploy / docs / research / workflow)
3. **Language** — What language? (go / python / typescript / shell / markdown)

This routes to the right skill, agent, or command for each task. You don't need to memorize the full list — the routing table is always in context.

## Credits

Built on the work of:

- **Jesse Vincent** ([@obra](https://github.com/obra)) — [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code)
- **Kieran Klaassen** ([@kieranklaassen](https://github.com/kieranklaassen)) — [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin) at [Every](https://every.to)
- **Steve Yegge** ([@steveyegge](https://github.com/steveyegge)) — [beads](https://github.com/steveyegge/beads)
- **Peter Steinberger** ([@steipete](https://github.com/steipete)) — [oracle](https://github.com/steipete/oracle)
- **Jeff Emanuel** ([@Dicklesworthstone](https://github.com/Dicklesworthstone)) — [mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail)

## License

MIT
