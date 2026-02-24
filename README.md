# Clavain

Clavain is an opinionated, self-improving Claude Code agent rig that codifies product and engineering discipline into composable workflows for building software from brainstorm to ship. It orchestrates heterogeneous AI models: Claude, Codex, GPT-5.2 Pro via Oracle: into a reliable system for getting things built, where the review phases matter more than the building phases. Through knowledge compounding, doc freshness monitoring, domain-aware agent generation, and session evidence capture, Clavain gets better at building your project the more you use it.

With 16 skills, 4 agents, 58 commands, 10 hooks, and 1 MCP server, there is a lot here (and it is constantly changing). Before installing, point Claude Code at this directory and ask it to review the plugin against how you like to work. It's especially helpful to [run `/insights` first](https://x.com/trq212/status/2019173731042750509) so Claude Code can evaluate Clavain against your actual historical usage patterns.

## Install

```bash
# Full rig install (recommended): installs Clavain + companions, MCP servers, env vars, and conflict resolution
npx @gensysven/agent-rig install mistakeknot/Clavain

# Plugin only (no companions or environment setup)
claude plugin install clavain@interagency-marketplace

# Local development
claude --plugin-dir /path/to/Clavain
```

## Codex install

Clavain can also run in Codex via native skill discovery and generated prompt wrappers.

Quick path:

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/Clavain/main/.codex/agent-install.sh | bash -s -- --update --json
```

Then restart Codex.

From a local clone:

```bash
make codex-refresh
make codex-doctor-json
```

Detailed guide: `docs/README.codex.md`  
Single-file bootstrap target: `.codex/INSTALL.md`

## Who this Is for

Clavain serves three concentric circles, inner circle first:

1. **Personal rig.** Optimized relentlessly for one product-minded engineer's workflow. The primary goal is to make a single person as effective as a full team without losing the fun parts of building.
2. **Reference implementation.** Shows what's possible with disciplined multi-agent engineering and sets conventions for plugin structure, skill design, and agent orchestration.
3. **Research artifact.** Demonstrates what disciplined human-AI collaboration looks like in practice by solving real problems under real constraints and publishing the results.

Clavain is not the best workflow for everyone, but it can, at the very least, provide some inspiration for your own approach to Claude Code.

## Philosophy

Most agent tools skip the product phases: brainstorm, strategy, specification: and jump straight to code generation. Clavain makes them first-class. The brainstorm and strategy phases are real product capabilities, not engineering context-setting.

A few operating principles that shape every design decision:

**Refinement > production.** The review phases matter more than the building phases. Resolving ambiguity during planning is far cheaper than dealing with it during execution.

**Composition > integration.** Small, focused tools composed together beat large integrated platforms. The inter-\* constellation, Unix philosophy, modpack metaphor: it's turtles all the way down.

**Human attention is the bottleneck.** Optimize for the human's time, not the agent's. Multi-agent output must be presented so humans can review quickly and confidently, not just cheaply.

**Multi-AI > single-vendor.** No one model is best at everything. Clavain is built on Claude Code and uses Codex and Oracle as complements: architecturally multi-model while remaining platform-native.

**Discipline before automation.** Encode judgment into checks before removing the human. Agents without discipline ship slop.

The full set of operating principles and the project roadmap live in [`docs/vision.md`](docs/vision.md).

## Development model

**Clavain-first, then generalize out.** Capabilities are built tightly integrated, battle-tested through real use, and only extracted into companion plugins when the patterns stabilize. The inter-\* constellation represents crystallized research outputs: each companion started as a tightly-coupled feature inside Clavain that earned its independence through repeated, successful use.

This inverts the typical "design the API first" approach: build too-tightly-coupled on purpose, discover the natural seams through practice, and only then extract.

| Companion | Crystallized Insight |
|---|---|
| interphase | Phase tracking and gates are generalizable |
| interflux | Multi-agent review is generalizable |
| interline | Statusline rendering is generalizable |
| interpath | Product artifact generation is generalizable |
| interwatch | Doc freshness monitoring is generalizable |

## What Clavain Is not

**Not a framework.** The inter-\* constellation offers composable pieces anyone can adopt independently, but Clavain itself is not designed to be "framework-agnostic" or "configurable for any workflow." It is an opinionated rig that also happens to produce reusable components.

**Not for non-builders.** Clavain is for people who build software with agents. It is not a no-code tool, not an AI assistant for non-technical users, not a chatbot framework.

**Platform-native, not vendor-neutral.** Clavain is built on Claude Code. It dispatches to Codex CLI, GPT-5.2 Pro (via Oracle), and other models as complements, but it is not trying to be a universal agent orchestrator for any LLM platform.

## Workflow

For simple requests, `/sprint add user export feature` orchestrates the full lifecycle: brainstorm, plan, review the plan with multiple subagents, implement, review the implementation, resolve issues, and run quality gates. The human focuses on the usual suspects: product strategy, user pain points, and finding new [leverage points](https://donellameadows.org/archives/leverage-points-places-to-intervene-in-a-system/).

For more complex endeavors (or new projects), each piece works standalone. The following review of the `/sprint` lifecycle provides a brief explanation of all the different parts of Clavain:

### The `/sprint` lifecycle

`/sprint` chains nine steps together. Each one can also be invoked standalone:

```
/brainstorm  →  /strategy  →  /write-plan  →  /work*  →  /flux-drive  →  /review  →  /resolve  →  /quality-gates  →  ship
   explore      structure       plan          execute     review plan     review code    fix issues    final check     commit

* When interserve mode is active, /write-plan executes via Codex Delegation and /work is skipped.
```

Even with clear requirements, starting with `/brainstorm` forces articulation of requirements and user journeys before touching code: Clavain often catches edge cases that weren't considered. `/strategy` then structures the brainstorm into a PRD with discrete features and creates beads for tracking: this convergent step catches scope creep and missing acceptance criteria before any planning starts. After that, `/write-plan` creates a structured implementation plan: and when interserve mode is active, it also dispatches execution through Codex agents, making the `/work` step unnecessary. `/flux-drive` then reviews the plan (or, under interserve, the executed result) with up to 4 tiers of agents before the code review phase.

### Reviewing things with `/flux-drive`

`/flux-drive`, named after the [Flux Review](https://read.fluxcollective.org/), is the most versatile standalone command. You can point it at a file, a plan, or an entire repo and it determines which reviewer agents are relevant for the given context. It selects from three categories of review agents:

- **Project Agents**: Per-project `fd-*.md` agents that live in your repo and know your specific codebase (bootstrapped via Codex when interserve mode is active)
- **Plugin Agents**: 7 core agents (Architecture & Design, Safety, Correctness, Quality & Style, User & Product, Performance, Game Design) that auto-detect project docs: when CLAUDE.md/AGENTS.md exist, they provide codebase-aware analysis; otherwise they fall back to general best practices
- **Cross-AI (Oracle)**: GPT-5.2 Pro for cross-model perspective on complex decisions

It only launches what's relevant. A simple markdown doc might get 2 agents; a full repo review might get 8. The agents run in parallel in the background, and you get a synthesized report with findings prioritized by severity. Over time, flux-drive builds a knowledge layer from review findings: patterns discovered in one review are injected as context into future reviews.

When Oracle is part of the review, `flux-drive` chains into the **interpeer stack**: comparing what Claude-based agents found against what GPT-5.2 Pro found, flagging disagreements, and optionally escalating critical decisions to a full multi-model council.

### Cross-Agent review with `/interpeer`

Different models and agents genuinely see different things, and the disagreements between them are often more valuable than what either finds alone. Cross-agent review with `/interpeer` is especially valuable after a `flux-drive` run.

The `/interpeer` stack escalates in depth:

| Mode | What it does | Speed |
|------|-------------|-------|
| `/interpeer` | Quick Claude↔Codex second opinion | Seconds |
| `/interpeer deep` | Oracle analysis with prompt optimization and human review | Minutes |
| `/interpeer council` | Full LLM Council: multi-model consensus | Slow |
| `/interpeer mine` | Post-processor: turns disagreements into tests and specs | N/A |

`/interpeer` defaults to quick mode: it auto-detects whether you're running in Claude Code or Codex CLI and calls the other one. For deeper analysis, `deep` mode builds optimized prompts for Oracle (GPT-5.2 Pro) and shows you the enhanced prompt before sending. `council` mode runs a full multi-model review when the stakes are high: critical architecture or security decisions where you want genuine consensus, not just one model's opinion.

`mine` mode is particularly useful for complex, ambiguous contexts. It takes the *disagreements* between models and converts them into concrete artifacts: tests that would prove one side right, spec clarifications that would resolve ambiguity, and stakeholder questions that surface hidden assumptions.

### Token efficiency with `/interserve`

Because Codex CLI has far higher usage limits than Claude Code, `/interserve` lets Claude orchestrate while Codex does the heavy lifting. Claude reads, plans, and writes detailed prompts: then dispatches to Codex agents for implementation. Claude crafts a megaprompt, dispatches it, reads the verdict from Codex, and decides if it's acceptable. Claude plays the tech lead, Codex plays the engineering team.

For multi-task work, `/interserve` parallelizes naturally. Five independent changes get five Codex agents dispatched simultaneously. Claude collects the results and commits.

### Structured debate

`/debate` runs a structured 2-round argument between Claude and Codex before implementing a complex task. Each writes an independent position, then responds to the other's. If they fundamentally disagree on architecture or security, Oracle gets called in as a tiebreaker. The output is a synthesis with clear options for you to choose from.

Worth running before any architectural decision with genuine uncertainty. The debate itself costs less than building the wrong thing.

## What's included

### Skills (16)

Skills are workflow disciplines: they guide **how** you work, not what tools to call. Each one is a markdown playbook that Claude follows step by step.

| Skill | What it does |
|-------|-------------|
| **Core Lifecycle** | |
| `brainstorming` | Structured exploration before planning |
| `writing-plans` | Create implementation plans with bite-sized tasks |
| `executing-plans` | Execute plans with review checkpoints |
| `landing-a-change` | Trunk-based finish checklist |
| **Code Discipline** | |
| `refactor-safely` | Disciplined refactoring with duplication detection |
| **Multi-Agent** | |
| `subagent-driven-development` | Parallel subagent execution |
| `dispatching-parallel-agents` | When and how to parallelize |
| `code-review-discipline` | Request reviews and handle feedback with technical rigor |
| `interserve` | Codex dispatch: megaprompt, parallel delegation, debate, Oracle escalation |
| **Knowledge & Docs** | |
| `engineering-docs` | Capture solved problems as searchable docs |
| `file-todos` | File-based todo tracking across sessions |
| **Utilities** | |
| `using-clavain` | Bootstrap routing: maps tasks to the right component |
| `using-tmux-for-interactive-commands` | Interactive CLI tools in tmux |
| `upstream-sync` | Track updates from upstream tool repos |

Skills extracted to companion plugins: **interpeer** (cross-AI review: interpeer, prompterpeer, winterpeer, splinterpeer), **intertest** (quality disciplines: systematic-debugging, test-driven-development, verification-before-completion), **interdev** (meta-tooling: working-with-claude-code, developing-claude-code-plugins, create-agent-skills, writing-skills).

### Agents (4)

Agents are specialized execution units dispatched by skills and commands. They run as subagents with their own context window.

**Review (2):** plan-reviewer and data-migration-expert for specialized review tasks. The 7 core fd-* review agents and 5 research agents live in **interflux**. The agent-native-reviewer lives in **intercraft**.

**Workflow (2):** PR comment resolution and bug reproduction validation.

### Commands (58)

Slash commands are the user-facing entry points. Most of them load a skill underneath.

| Command | What it does |
|---------|-------------|
| `/sprint` | Full autonomous lifecycle: brainstorm through ship |
| `/codex-sprint` | Codex-safe phase-gated sprint workflow |
| `/setup` | Bootstrap the modpack: install plugins, disable conflicts, verify servers |
| `/brainstorm` | Explore before planning |
| `/strategy` | Structure brainstorm into PRD with trackable beads |
| `/write-plan` | Create implementation plan |
| `/flux-drive` | Multi-agent document/repo review |
| `/work` | Execute a plan autonomously |
| `/review` | Multi-agent code review |
| `/code-review` | Disciplined code review and feedback triage |
| `/execute-plan` | Execute plan in batches with checkpoints |
| `/plan-review` | Parallel plan review |
| `/quality-gates` | Auto-select the right reviewers |
| `/interserve` | Run Codex-first execution flow for larger scope work |
| `/fixbuild` | Fast build-error fix loop: run, parse, fix, re-run |
| `/tdd` | Run RED-GREEN-REFACTOR for a task before coding |
| `/smoke-test` | End-to-end smoke test: detect app, walk user journeys, report results |
| `/repro-first-debugging` | Disciplined bug investigation |
| `/debate` | Structured Claude↔Codex debate |
| `/refactor` | Plan and execute safe refactors with risk controls |
| `/interpeer` | Quick cross-AI peer review |
| `/verify` | Run completion verification before declaring work done |
| `/migration-safety` | Data migration risk assessment |
| `/compound` | Document solved problems |
| `/changelog` | Generate changelog from recent merges |
| `/docs` | Capture engineering knowledge in searchable docs |
| `/clodex-toggle` | Toggle Codex-first execution mode |
| `/model-routing` | Toggle subagent model tier (economy vs quality) |
| `/codex-bootstrap` | Refresh Codex discovery links and run health checks |
| `/todos` | Manage file-based todo tracking |
| `/land` | Run landing checklist for trunk-based handoff |
| `/triage` | Categorize and prioritize findings |
| `/resolve` | Resolve findings from any source (auto-detects TODOs, PR comments, or todo files) |
| `/create-agent-skill` | Create new skills or agents |
| `/generate-command` | Generate new commands |
| `/heal-skill` | Fix broken skills |
| `/triage-prs` | Triage open PR backlog with parallel review agents |
| `/review-doc` | Quick single-pass document refinement (lighter than flux-drive) |
| `/upstream-sync` | Check upstream repos for updates |
| `/sprint-status` | Deep scan of sprint workflow state: sessions, pipeline, beads |
| `/flux-gen` | Generate project-specific review agents from detected domain profiles |
| `/help` | Show Clavain commands organized by daily drivers first |
| `/doctor` | Quick health check: MCP servers, tools, beads, plugin conflicts |

*(All commands are prefixed with `/clavain:` when invoked.)*

### Hooks (10)

- **SessionStart**: Injects the `using-clavain` routing table into every session (start, resume, clear, compact). When interserve mode is active, injects the behavioral contract for Codex delegation (`session-start.sh`).
- **PostToolUse**: Interserve audit: logs source code writes when interserve mode is active for post-session review (`interserve-audit.sh`). Auto-publish: detects `git push` in plugin repos and auto-bumps version + syncs marketplace (`auto-publish.sh`).
- **Stop**: Auto-compound check: detects compoundable signals and prompts knowledge capture (`auto-compound.sh`). Session handoff: detects uncommitted work or in-progress beads and prompts HANDOFF.md creation (`session-handoff.sh`).
- **SessionEnd**: Syncs dotfile changes at end of session (`dotfiles-sync.sh`).

### MCP servers (1)

- **context7**: Library documentation lookup via [Context7](https://context7.com)

*(qmd semantic search lives in the **interflux** companion plugin.)*

## The agent rig

Clavain is designed as an **agent rig**, inspired by [PC game mod packs](https://en.wikipedia.org/wiki/Video_game_modding#Mod_packs). It is an opinionated integration layer that configures companion plugins into a cohesive rig. Instead of duplicating their capabilities, Clavain routes to them and wires them together.

### Required companions

| Plugin | Why |
|--------|-----|
| [context7](https://context7.com) | Runtime doc fetching. Clavain's skills use it to pull library docs without bundling them. |
| [explanatory-output-style](https://github.com/claude-plugins-official) | Educational insights in output. Injected via SessionStart hook. |

### Recommended

| Plugin | What it adds |
|--------|-------------|
| [interpeer](https://github.com/mistakeknot/interpeer) | Cross-AI peer review: quick, deep (Oracle), council, mine |
| [intertest](https://github.com/mistakeknot/intertest) | Quality disciplines: TDD, systematic debugging, verification gates |
| [interdev](https://github.com/mistakeknot/interdev) | Developer tooling: Claude Code reference, skill/plugin authoring |
| [interdoc](https://github.com/interagency-marketplace) | AGENTS.md generation for any repo |
| [interclode](https://github.com/interagency-marketplace) | Codex CLI dispatch infrastructure: powers `/interserve` |
| [agent-sdk-dev](https://github.com/claude-plugins-official) | Agent SDK scaffolding |
| [plugin-dev](https://github.com/claude-plugins-official) | Plugin development tools |
| [serena](https://github.com/claude-plugins-official) | Semantic code analysis via LSP-like tools |
| [tool-time](https://github.com/interagency-marketplace) | Tool usage analytics across sessions |

### Disabled (Conflicts)

Clavain replaces these plugins with its own opinionated equivalents. Keeping both causes duplicate agents and confusing routing.

| Plugin | Clavain Replacement |
|--------|-------------------|
| code-review | `/review` + `/flux-drive` + 2 review agents |
| pr-review-toolkit | Same agent types exist in Clavain's review roster |
| code-simplifier | `interflux:review:fd-quality` agent |
| commit-commands | `landing-a-change` skill |
| feature-dev | `/work` + `/sprint` + `/brainstorm` |
| claude-md-management | `engineering-docs` skill |
| frontend-design | `interform:distinctive-design` skill |
| hookify | Clavain manages hooks directly |

## Customization

Clavain is opinionated but not rigid. A few things worth knowing:

**Reviewers are auto-selected.** `flux-drive` picks from 7 core review agents based on the document profile. Each agent auto-detects language and project conventions. Additional specialists (plan-reviewer, data-migration-expert, and intercraft's agent-native-reviewer) are available for direct use via `/review` and `/quality-gates`.

**Skills can be overridden.** If you disagree with how `test-driven-development` works, you can create your own skill with the same name in a local plugin that loads after Clavain. Last-loaded wins.

**Codex dispatch is optional.** Everything works fine with Claude making changes directly. `/interserve` is there for when you want the orchestration pattern, not a requirement.

**Oracle requires setup.** The cross-AI features (`/interpeer deep`, `/interpeer council`, `flux-drive` Cross-AI) need [Oracle](https://github.com/steipete/oracle) installed and configured. Without it, those features are simply skipped: nothing breaks.

## Architecture

```
skills/       # 16 discipline skills (SKILL.md each)
agents/       # 4 agents (review/ + workflow/)
commands/     # 58 slash commands
hooks/        # 7 hooks (SessionStart, PostToolUse×2, Stop×2, SessionEnd×2)
config/       # dispatch routing
scripts/      # debate, codex dispatch, codex auto-refresh, upstream sync
```

Full directory tree and component conventions: see `AGENTS.md`.

### How the routing works

The `using-clavain` skill is injected into every session via the SessionStart hook. It provides a 3-layer routing system:

1. **Stage**: What phase are you in? (explore / plan / execute / debug / review / ship / meta)
2. **Domain**: What kind of work? (code / data / deploy / docs / research / workflow)
3. **Concern**: What review concern? (architecture / safety / correctness / quality / user-product / performance)

This routes to the right skill, agent, or command for each task. You don't need to memorize the full list: the routing table is always in context.

## Credits

Named after one of the protagonists from Alastair Reynolds's [Revelation Space series](https://en.wikipedia.org/wiki/Revelation_Space_series). Built on the work of:

- **Jesse Vincent** ([@obra](https://github.com/obra)): [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code)
- **Kieran Klaassen** ([@kieranklaassen](https://github.com/kieranklaassen)): [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin) at [Every](https://every.to)
- **Steve Yegge** ([@steveyegge](https://github.com/steveyegge)): [beads](https://github.com/steveyegge/beads)
- **Peter Steinberger** ([@steipete](https://github.com/steipete)): [oracle](https://github.com/steipete/oracle)
- **Tobi Lütke** ([@tobi](https://github.com/tobi)): [qmd](https://github.com/tobi/qmd)

## License

MIT
