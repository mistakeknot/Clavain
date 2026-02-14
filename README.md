# Clavain

Clavain, named after one of the protagonists from Alastair Reynolds's [Revelation Space series](https://en.wikipedia.org/wiki/Revelation_Space_series), is a **highly** opinionated Claude Code agent rig that encapsulates how I personally like to use Claude Code to build things. An agent rig, as I define it, is a collection of plugins, skills, and integrations that serves as a cohesive system for working with agents.

I do not think Clavain is the best workflow for everyone, but it works very well for me and I hope it can, at the very least, provide some inspiration for your own experiences with Claude Code.

With 27 skills, 10 agents, 36 commands, 7 hooks, and 1 MCP servers, there is a lot here (and it is constantly changing). Before installing, I recommend you point Claude Code to this directory and ask it to review this plugin against how you like to work. It's especially helpful if [you run `/insights` first](https://x.com/trq212/status/2019173731042750509) so Claude Code can evaluate Clavain against your actual historical usage patterns.

Merged, modified, and maintained with updates from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Install

```bash
# From marketplace
claude plugin install clavain@interagency-marketplace

# Local development
claude --plugin-dir /path/to/Clavain
```

## Codex Install

Clavain can also run in Codex via native skill discovery and generated prompt wrappers.

Quick path:

```bash
git clone https://github.com/mistakeknot/Clavain.git ~/.codex/clavain
bash ~/.codex/clavain/scripts/install-codex.sh install
```

Then restart Codex.

From a local clone:

```bash
make codex-refresh
make codex-doctor
```

Detailed guide: `docs/README.codex.md`  
Single-file bootstrap target: `.codex/INSTALL.md`

## My Workflow

For simple requests, I use `/lfg add user export feature` and Clavain orchestrates Claude Code via hooks, commands, skills, and subagents to brainstorm the approach, write a plan, review the plan with multiple subagents, implement the code, review the implementation, resolve any issues, and run quality gates. While Clavain runs through all of these phases, I focus on the usual suspects: product strategy, user pain points, and finding new [leverage points](https://donellameadows.org/archives/leverage-points-places-to-intervene-in-a-system/).

For more complex endeavors (or new projects), I use Clavain's pieces individually depending on what I'm doing. The following review of the `/lfg` lifecycle provides a brief explanation of all the different parts of Clavain:

### The `/lfg` Lifecycle

`/lfg` chains nine steps together. Each one can also be invoked standalone:

```
/brainstorm  →  /strategy  →  /write-plan  →  /work*  →  /flux-drive  →  /review  →  /resolve  →  /quality-gates  →  ship
   explore      structure       plan          execute     review plan     review code    fix issues    final check     commit

* When clodex mode is active, /write-plan executes via Codex Delegation and /work is skipped.
```

Even when I think I know what I want, I usually start with `/brainstorm` because it forces me to articulate and trace through requirements and user journeys before touching code; Clavain often catches edge cases I hadn't considered. `/strategy` then structures the brainstorm into a PRD with discrete features and creates beads for tracking — this convergent step catches scope creep and missing acceptance criteria before any planning starts. After that, `/write-plan` creates a structured implementation plan — and when clodex mode is active, it also dispatches execution through Codex agents, making the `/work` step unnecessary. `/flux-drive` then reviews the plan (or, under clodex, the executed result) with up to 4 tiers of agents before the code review phase.

### Reviewing Things with `/flux-drive`

`/flux-drive`, named after the [Flux Review](https://read.fluxcollective.org/), is probably the command I use most often on its own. You can point it at a file, a plan, or an entire repo and it determines which reviewer agents are relevant for the given context. It selects from three categories of review agents:

- **Project Agents** — Per-project `fd-*.md` agents that live in your repo and know your specific codebase (bootstrapped via Codex when clodex mode is active)
- **Plugin Agents** — 7 core agents (Architecture & Design, Safety, Correctness, Quality & Style, User & Product, Performance, Game Design) that auto-detect project docs: when CLAUDE.md/AGENTS.md exist, they provide codebase-aware analysis; otherwise they fall back to general best practices
- **Cross-AI (Oracle)** — GPT-5.2 Pro for cross-model perspective on complex decisions

It only launches what's relevant. A simple markdown doc might get 2 agents; a full repo review might get 8. The agents run in parallel in the background, and you get a synthesized report with findings prioritized by severity. Over time, flux-drive builds a knowledge layer from review findings — patterns discovered in one review are injected as context into future reviews.

When Oracle is part of the review, `flux-drive` chains into the **interpeer stack** — comparing what Claude-based agents found against what GPT-5.2 Pro found, flagging disagreements, and optionally escalating critical decisions to a full multi-model council.

### Cross-Agent Review with `/interpeer`

Because different models and agents genuinely see different things, and the disagreements between them are often more valuable than what either finds alone, I find cross-agent review with `/interpeer` to be incredibly valuable, especially after a `flux-drive` run.

The `/interpeer` stack escalates in depth:

| Mode | What it does | Speed |
|------|-------------|-------|
| `/interpeer` | Quick Claude↔Codex second opinion | Seconds |
| `/interpeer deep` | Oracle analysis with prompt optimization and human review | Minutes |
| `/interpeer council` | Full LLM Council — multi-model consensus | Slow |
| `/interpeer mine` | Post-processor — turns disagreements into tests and specs | N/A |

`/interpeer` defaults to quick mode — it auto-detects whether you're running in Claude Code or Codex CLI and calls the other one. For deeper analysis, `deep` mode builds optimized prompts for Oracle (GPT-5.2 Pro) and shows you the enhanced prompt before sending. `council` mode runs a full multi-model review when the stakes are high — critical architecture or security decisions where you want genuine consensus, not just one model's opinion.

I find `mine` mode to be particularly useful for complex, ambiguous contexts. It takes the *disagreements* between models and converts them into concrete artifacts: tests that would prove one side right, spec clarifications that would resolve ambiguity, and stakeholder questions that surface hidden assumptions.

### Token Efficiency with `/clodex`

Because Codex CLI has far higher usage limits than Claude Code, `/clodex` lets Claude orchestrate while Codex does the heavy lifting. Claude reads, plans, and writes detailed prompts — then dispatches to Codex agents for implementation. Claude crafts a megaprompt, dispatches it, reads the verdict from Codex, and decides if it's acceptable. Claude plays the tech lead, Codex plays the engineering team.

For multi-task work, `/clodex` parallelizes naturally. Five independent changes get five Codex agents dispatched simultaneously. Claude collects the results and commits.

### Structured Debate

`/debate` runs a structured 2-round argument between Claude and Codex before implementing a complex task. Each writes an independent position, then responds to the other's. If they fundamentally disagree on architecture or security, Oracle gets called in as a tiebreaker. The output is a synthesis with clear options for you to choose from.

I use this before any architectural decision I'm uncertain about. The debate itself costs less than building the wrong thing.

## What's Included

### Skills (27)

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
| `code-review-discipline` | Request reviews and handle feedback with technical rigor |
| **Cross-AI** | |
| `interpeer` | Cross-AI peer review with 4 modes: quick, deep (Oracle), council (multi-model), mine (disagreement extraction) |
| `prompterpeer` | Oracle prompt optimizer — builds and reviews prompts for GPT-5.2 Pro (interpeer deep mode) |
| `winterpeer` | LLM Council review — multi-model consensus for critical decisions (interpeer council mode) |
| `splinterpeer` | Disagreement mining — extracts model conflicts into tests, specs, and questions (interpeer mine mode) |
| `clodex` | Codex dispatch — megaprompt, parallel delegation, debate, Oracle escalation |
| **Knowledge & Docs** | |
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
| `upstream-sync` | Track updates from upstream tool repos |

### Agents (10)

Agents are specialized execution units dispatched by skills and commands. They run as subagents with their own context window.

**Review (3):** plan-reviewer, agent-native-reviewer, and data-migration-expert for specialized review tasks. The 7 core fd-* review agents now live in the **interflux** companion plugin.

**Research (5):** Best practices, framework docs, git history analysis, institutional learnings, and repo structure analysis.

**Workflow (2):** PR comment resolution and bug reproduction validation.

### Commands (36)

Slash commands are the user-facing entry points. Most of them load a skill underneath.

| Command | What it does |
|---------|-------------|
| `/lfg` | Full autonomous lifecycle — brainstorm through ship |
| `/setup` | Bootstrap the modpack — install plugins, disable conflicts, verify servers |
| `/brainstorm` | Explore before planning |
| `/strategy` | Structure brainstorm into PRD with trackable beads |
| `/write-plan` | Create implementation plan |
| `/flux-drive` | Multi-agent document/repo review |
| `/work` | Execute a plan autonomously |
| `/review` | Multi-agent code review |
| `/execute-plan` | Execute plan in batches with checkpoints |
| `/plan-review` | Parallel plan review |
| `/quality-gates` | Auto-select the right reviewers |
| `/fixbuild` | Fast build-error fix loop — run, parse, fix, re-run |
| `/smoke-test` | End-to-end smoke test — detect app, walk user journeys, report results |
| `/repro-first-debugging` | Disciplined bug investigation |
| `/debate` | Structured Claude↔Codex debate |
| `/interpeer` | Quick cross-AI peer review |
| `/migration-safety` | Data migration risk assessment |
| `/compound` | Document solved problems |
| `/changelog` | Generate changelog from recent merges |
| `/clodex-toggle` | Toggle Codex-first execution mode |
| `/model-routing` | Toggle subagent model tier (economy vs quality) |
| `/triage` | Categorize and prioritize findings |
| `/resolve` | Resolve findings from any source (auto-detects TODOs, PR comments, or todo files) |
| `/agent-native-audit` | Agent-native architecture review |
| `/create-agent-skill` | Create new skills or agents |
| `/generate-command` | Generate new commands |
| `/heal-skill` | Fix broken skills |
| `/triage-prs` | Triage open PR backlog with parallel review agents |
| `/review-doc` | Quick single-pass document refinement (lighter than flux-drive) |
| `/upstream-sync` | Check upstream repos for updates |
| `/sprint-status` | Deep scan of sprint workflow state — sessions, pipeline, beads |
| `/flux-gen` | Generate project-specific review agents from detected domain profiles |
| `/deep-review` | Alias for `/flux-drive` |
| `/full-pipeline` | Alias for `/lfg` |
| `/cross-review` | Alias for `/interpeer` |
| `/help` | Show Clavain commands organized by daily drivers first |
| `/doctor` | Quick health check — MCP servers, tools, beads, plugin conflicts |

*(All commands are prefixed with `/clavain:` when invoked.)*

### Hooks (7)

- **SessionStart** — Injects the `using-clavain` routing table into every session (start, resume, clear, compact). When clodex mode is active, injects the behavioral contract for Codex delegation (`session-start.sh`).
- **PostToolUse** — Clodex audit: logs source code writes when clodex mode is active for post-session review (`clodex-audit.sh`). Auto-publish: detects `git push` in plugin repos and auto-bumps version + syncs marketplace (`auto-publish.sh`).
- **Stop** — Auto-compound check: detects compoundable signals and prompts knowledge capture (`auto-compound.sh`). Session handoff: detects uncommitted work or in-progress beads and prompts HANDOFF.md creation (`session-handoff.sh`).
- **SessionEnd** — Syncs dotfile changes at end of session (`dotfiles-sync.sh`).

### MCP Servers (2)

- **context7** — Library documentation lookup via [Context7](https://context7.com)
- **qmd** — Semantic search over indexed project documentation via [qmd](https://github.com/tobi/qmd)

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
| code-review | `/review` + `/flux-drive` + 3 review agents |
| pr-review-toolkit | Same agent types exist in Clavain's review roster |
| code-simplifier | `interflux:review:fd-quality` agent |
| commit-commands | `landing-a-change` skill |
| feature-dev | `/work` + `/lfg` + `/brainstorm` |
| claude-md-management | `engineering-docs` skill |
| frontend-design | `distinctive-design` skill |
| hookify | Clavain manages hooks directly |

## Customization

Clavain is opinionated but not rigid. A few things worth knowing:

**Reviewers are auto-selected.** `flux-drive` picks from 7 core review agents based on the document profile. Each agent auto-detects language and project conventions. Additional specialists (plan-reviewer, agent-native-reviewer, data-migration-expert) are available for direct use via `/review` and `/quality-gates`.

**Skills can be overridden.** If you disagree with how `test-driven-development` works, you can create your own skill with the same name in a local plugin that loads after Clavain. Last-loaded wins.

**Codex dispatch is optional.** Everything works fine with Claude making changes directly. `/clodex` is there for when you want the orchestration pattern, not a requirement.

**Oracle requires setup.** The cross-AI features (`/interpeer deep`, `/interpeer council`, `flux-drive` Cross-AI) need [Oracle](https://github.com/steipete/oracle) installed and configured. Without it, those features are simply skipped — nothing breaks.

## Architecture

```
skills/       # 27 discipline skills (SKILL.md each)
agents/       # 10 agents (review/ + research/ + workflow/)
commands/     # 36 slash commands
hooks/        # 7 hooks (SessionStart, PostToolUse×2, Stop×2, SessionEnd×2)
config/       # dispatch routing
scripts/      # debate, codex dispatch, codex auto-refresh, upstream sync
```

Full directory tree and component conventions: see `AGENTS.md`.

### How the Routing Works

The `using-clavain` skill is injected into every session via the SessionStart hook. It provides a 3-layer routing system:

1. **Stage** — What phase are you in? (explore / plan / execute / debug / review / ship / meta)
2. **Domain** — What kind of work? (code / data / deploy / docs / research / workflow)
3. **Concern** — What review concern? (architecture / safety / correctness / quality / user-product / performance)

This routes to the right skill, agent, or command for each task. You don't need to memorize the full list — the routing table is always in context.

## Credits

Built on the work of:

- **Jesse Vincent** ([@obra](https://github.com/obra)) — [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code)
- **Kieran Klaassen** ([@kieranklaassen](https://github.com/kieranklaassen)) — [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin) at [Every](https://every.to)
- **Steve Yegge** ([@steveyegge](https://github.com/steveyegge)) — [beads](https://github.com/steveyegge/beads)
- **Peter Steinberger** ([@steipete](https://github.com/steipete)) — [oracle](https://github.com/steipete/oracle)
- **Tobi Lütke** ([@tobi](https://github.com/tobi)) — [qmd](https://github.com/tobi/qmd)

## License

MIT
