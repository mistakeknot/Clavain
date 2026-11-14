# Component reference

## What's included

### Skills (28)

Skills are workflow disciplines: they guide **how** you work, not what tools to call. Each one is a markdown playbook that Claude follows step by step.

| Skill | What it does |
|-------|-------------|
| **Core Lifecycle** | |
| `writing-plans` | Create implementation plans with bite-sized tasks |
| `executing-plans` | Execute plans continuously with a ledger and final review |
| `landing-a-change` | Trunk-based finish checklist |
| **Code Discipline** | |
| `refactor-safely` | Disciplined refactoring with duplication detection |
| `gardener` | Repository upkeep: lint rule before cleanup, shrink-only baselines, docs-pins drift check |
| **Multi-Agent** | |
| `subagent-driven-development` | Parallel subagent execution |
| `dispatching-parallel-agents` | When and how to parallelize |
| `code-review-discipline` | Request reviews and handle feedback with technical rigor |
| `interserve` | Codex dispatch: megaprompt, parallel delegation, debate, Oracle escalation |
| **Knowledge & Docs** | |
| `engineering-docs` | Capture solved problems as searchable docs |
| `file-todos` | File-based todo tracking across sessions |
| **Setup** | |
| `project-onboard` | One-command project setup: introspect, scaffold, seed content |
| `remontoire` | Operate the portfolio agency with explicit approval boundaries |
| **Utilities** | |
| `using-clavain` | Bootstrap routing: maps tasks to the right component |
| `using-tmux-for-interactive-commands` | Interactive CLI tools in tmux |
| `upstream-sync` | Track updates from upstream tool repos |

Skills extracted to companion plugins: **interpeer** (cross-AI review: interpeer, prompterpeer, winterpeer, splinterpeer), **intertest** (quality disciplines: systematic-debugging, test-driven-development, verification-before-completion), **interdev** (meta-tooling: working-with-claude-code, developing-claude-code-plugins, create-agent-skills, writing-skills).

### Agents (6)

Agents are specialized execution units dispatched by skills and commands. They run as subagents with their own context window.

**Review:** specialized reviewers handle planning, migration, and code-quality tasks. Broader review and research swarms live in companion plugins such as **interflux** and **intercraft**.

**Workflow:** PR comment resolution and bug reproduction validation.

### Commands (66)

Slash commands are the user-facing entry points. Most of them load a skill underneath.

| Command | What it does |
|---------|-------------|
| `/sprint` | Full autonomous lifecycle: brainstorm through ship |
| `/project-onboard` | Set up a new/existing project with full automation (beads, docs, observability) |
| `/setup` | Bootstrap the modpack: install plugins, disable conflicts, verify servers |
| `/wayfind` | Chart or work a multi-session decision map in beads; hands a cleared map to `/strategy` |
| `/prototype` | Build disposable code for one design question, record the answer, then remove or quarantine the experiment |
| `/waymap` | Chart or work a project's Now / Next / Later roadmap in beads as capped bets; renders `docs/roadmap.md` |
| `/grill-me` | Interview the user round by round over a plan's decision tree until it is settled; `--docs` records a glossary and decision records |
| `/blast-radius` | Find what a change could break outside the diff and prove the one fact it is safe because of by running real code |
| `/retro` | Read a session, a PR or a week of merged PRs and propose ranked environment changes (checks first, standards lines second); proposes only |
| `/correct` | Turn a mistake agents keep repeating into an architecture, type, lint or test barrier, then record the rule |
| `/show-me-your-work` | Keep a TSV decision trail for long or unattended runs, audited against the transcript and reviewed independently |
| `/brainstorm` | Explore before planning |
| `/strategy` | Structure brainstorm into PRD with trackable beads |
| `/write-plan` | Create implementation plan |
| `/flux-drive` | Multi-agent document/repo review |
| `/work` | Execute a plan autonomously |
| `/clavain:clavain-review` | Multi-agent code review |
| `/review-discipline` | Disciplined code review and feedback triage |
| `/execute-plan` | Execute a plan continuously with a final review |
| `/plan-review` | Parallel plan review |
| `/quality-gates` | Gate orchestrator — delegates review to flux-drive, enforces pass/fail |
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
| `/clodex-toggle` | Toggle Codex-first execution mode |
| `/model-routing` | Toggle subagent model tier (economy vs quality) |
| `/codex-bootstrap` | Refresh Codex discovery links and run health checks |
| `/todos` | Manage file-based todo tracking |
| `/land` | Run landing checklist for trunk-based handoff |
| `/triage` | Categorize and prioritize findings |
| `/resolve` | Resolve findings from any source (auto-detects TODOs, PR comments, or todo files) |
| `/remontoire` | Operate Remontoire on its scheduler host: status, shadow, proposal, decisions, resume, receipts |
| `/create-agent-skill` | Create new skills or agents |
| `/generate-command` | Generate new commands |
| `/heal-skill` | Fix broken skills |
| `/pr-triage` | Triage open PR backlog with parallel review agents, or run one follow-up pass on your own PR (`/pr-triage owner/repo#N`) |
| `/review-doc` | Quick single-pass document refinement (lighter than flux-drive) |
| `/upstream-sync` | Check upstream repos for updates |
| `/sprint-status` | Deep scan of sprint workflow state: sessions, pipeline, beads |
| `/flux-gen` | Generate project-specific review agents from detected domain profiles |
| `/clavain:clavain-help` | Show Clavain commands organized by daily drivers first |
| `/clavain:clavain-doctor` | Quick health check: MCP servers, tools, beads, plugin conflicts |
| `/next-goal` | Generate a Next-goal block (leverage-ranked candidates + recommendation) — invoke manually after a goal completes |
| `/goal-form` | Goal-formation ritual: research-first inter-elicitation → charter → lint → `ic goal` mint → `/goal` handoff |

Use `/clavain:` for local commands; companion commands use their own namespace, for example `/interflux:flux-drive`. The complete source inventory below gives current names; the overview table above retains workflow shorthand.

Remontoire is a separate L2 portfolio agency, not a Clavain fleet worker.
Clavain provides only its operator facade; Remontoire and Intercore remain the
owners of cycle behavior and durable state.

Normal use is exception-driven. Remontoire runs its scheduled cycles on its scheduler host,
and Claude Code or Codex stays silent at session start unless the latest cycle
needs a principal decision, an explicit resume, receipt recovery, or diagnosis.
Completed experiments do not create startup noise. Their ready promotion beads
join `/clavain:next-goal` ranking, where measured evidence is one leverage signal
rather than an automatic winner. Use `/goal` only after choosing a promotion for
normal implementation; `/goal` never approves or resumes a Remontoire cycle.

Common explicit operator flows are:

```text
/clavain:remontoire doctor
/clavain:remontoire status
/clavain:remontoire shadow
/clavain:remontoire proposal
/clavain:remontoire inspect CYCLE_ID
/clavain:remontoire approve CYCLE_ID --actor=PRINCIPAL
/clavain:remontoire resume CYCLE_ID
/clavain:remontoire receipt show CYCLE_ID
```

Codex uses the generated `/prompts:clavain-remontoire` and
`/prompts:clavain-next-goal` forms for the same workflows.

Approval records a principal decision and stops. Execution requires the
separate `resume` command. Remontoire never pushes, merges, deploys, or
publishes experiment output.

### Hooks

- **SessionStart**: Injects the `using-clavain` routing table and silently checks Remontoire for exception states (start, resume, clear, compact). When interserve mode is active, injects the behavioral contract for Codex delegation (`session-start.sh`).
- **PreToolUse**: Guards `~/.claude/plugins/cache/` from accidental edits (`guard-plugin-cache.sh`).
- **PostToolUse**: Auto-publish on `git push` in plugin repos (`auto-publish.sh`). Bead-agent binding on Bash (`bead-agent-bind.sh`). Catalog reminder on file edits (`catalog-reminder.sh`). Plugin edit validation (`validate-plugin-edit.sh`).
- **Stop**: Auto-stop actions: entity-backed goal audit (flags real defects — dormant, stuck-closing, closed-without-successor), compound check, self-dispatch, drift check, shadow-tracker warning (`auto-stop-actions.sh`).
- **SessionEnd**: Syncs dotfile changes at end of session (`dotfiles-sync.sh`).

### MCP servers (via companions)

MCP server capability comes from companion plugins in the rig:

- **context7**: Library documentation lookup via [Context7](https://context7.com) *(required companion)*
- **qmd**: Semantic search *(lives in the **interflux** companion plugin)*

## The agent rig

Clavain is designed as an **agent rig**, inspired by [PC game mod packs](https://en.wikipedia.org/wiki/Video_game_modding#Mod_packs). It is an opinionated integration layer that configures companion plugins into a cohesive rig. Instead of duplicating their capabilities, Clavain routes to them and wires them together.

### Required companions

| Plugin | Why |
|--------|-----|
| [context7](https://context7.com) | Runtime doc fetching. Clavain's skills use it to pull library docs without bundling them. |
| [explanatory-output-style](https://github.com/anthropics/claude-plugins-official) | Educational insights in output. Injected via SessionStart hook. |

### Recommended

| Plugin | What it adds |
|--------|-------------|
| [interpeer](https://github.com/mistakeknot/interpeer) | Cross-AI peer review: quick, deep (Oracle), council, mine |
| [intertest](https://github.com/mistakeknot/intertest) | Quality disciplines: TDD, systematic debugging, verification gates |
| [interdev](https://github.com/mistakeknot/interdev) | Developer tooling: Claude Code reference, skill/plugin authoring |
| [interdoc](https://github.com/mistakeknot/interagency-marketplace) | AGENTS.md generation for any repo |
| [interclode](https://github.com/mistakeknot/interagency-marketplace) | Codex CLI dispatch infrastructure: powers `/interserve` |
| [agent-sdk-dev](https://github.com/anthropics/claude-plugins-official) | Agent SDK scaffolding |
| [plugin-dev](https://github.com/anthropics/claude-plugins-official) | Plugin development tools |
| [tldr-swinton](https://github.com/mistakeknot/tldr-swinton) | Token-efficient code reconnaissance before broad reads and refactors |
| [tool-time](https://github.com/mistakeknot/interagency-marketplace) | Tool usage analytics across sessions |

### Disabled (Conflicts)

Clavain replaces these plugins with its own opinionated equivalents. Keeping both causes duplicate agents and confusing routing.

| Plugin | Clavain Replacement |
|--------|-------------------|
| superpowers | Clavain is the successor — all skills, commands, and workflows superseded |
| compound-engineering | Clavain is the successor — all workflows superseded |
| code-review | `/clavain:clavain-review` + `/flux-drive` + 2 review agents |
| pr-review-toolkit | Same agent types exist in Clavain's review roster |
| code-simplifier | `interflux:review:fd-quality` agent |
| commit-commands | `landing-a-change` skill |
| feature-dev | `/work` + `/sprint` + `/brainstorm` |
| claude-md-management | `engineering-docs` skill |
| frontend-design | `interform:distinctive-design` skill |
| hookify | Clavain manages hooks directly |

## Customization

Clavain is opinionated but not rigid. A few things worth knowing:

**Reviewers are auto-selected.** `flux-drive` picks from 7 core review agents based on the document profile. Each agent auto-detects language and project conventions. Additional specialists (plan-reviewer, data-migration-expert, and intercraft's agent-native-reviewer) are available for direct use via `/clavain:clavain-review` and `/quality-gates`.

**Skills can be overridden.** If you disagree with how `test-driven-development` works, you can create your own skill with the same name in a local plugin that loads after Clavain. Last-loaded wins.

**Codex dispatch is optional.** Everything works fine with Claude making changes directly. `/interserve` is there for when you want the orchestration pattern, not a requirement.

**Oracle requires setup.** The cross-AI features (`/interpeer deep`, `/interpeer council`, `flux-drive` Cross-AI) need [Oracle](https://github.com/steipete/oracle) installed and configured. Without it, those features are simply skipped: nothing breaks.

## Architecture

```
skills/       # discipline skills (SKILL.md each)
agents/       # review and workflow agents
commands/     # slash commands
hooks/        # Claude Code hook registrations
config/       # dispatch routing
scripts/      # debate, codex dispatch, codex auto-refresh, upstream sync
```

Full directory tree and component conventions: see [AGENTS.md](../AGENTS.md).

### How the routing works

The `using-clavain` skill is injected into every session via the SessionStart hook. It provides a 3-layer routing system:

1. **Stage**: What phase are you in? (explore / plan / execute / debug / review / ship / meta)
2. **Domain**: What kind of work? (code / data / deploy / docs / research / workflow)
3. **Concern**: What review concern? (architecture / safety / correctness / quality / user-product / performance)

This routes to the right skill, agent, or command for each task. You don't need to memorize the full list: the routing table is always in context.

## Complete source inventory

The following tables enumerate the source tree for this revision.

### All skills (28)

| Component | Description |
|---|---|
| [bug-reproduction-validator](../skills/bug-reproduction-validator/SKILL.md) | Reproduce and validate a bug report to confirm whether the reported behavior is an actual bug. |
| [code-review-discipline](../skills/code-review-discipline/SKILL.md) | Request code review, and assess received feedback from people, PR comments, or agent and cross-lab reviewers; verify findings before implementing and preserve required review gates. |
| [codex-delegate](../skills/codex-delegate/SKILL.md) | Delegate well-scoped implementation, exploration, search, test-generation, or code-review tasks to Codex CLI. Not for architecture or interactive work. |
| [data-migration-expert](../skills/data-migration-expert/SKILL.md) | Validate one migration, backfill, ID mapping, column rename, enum conversion, or schema change against production reality, as a single focused reviewer. For a full multi-agent pre-deploy assessment, use /migration-safety. |
| [dispatching-parallel-agents](../skills/dispatching-parallel-agents/SKILL.md) | Use for 2+ independent tasks with no shared state or sequential dependency. |
| [engineering-docs](../skills/engineering-docs/SKILL.md) | Document a solved problem as a searchable solution with YAML frontmatter. |
| [executing-plans](../skills/executing-plans/SKILL.md) | Execute a written implementation plan task by task, continuously, with a final independent review; native mode keeps a progress ledger. This is the execution engine; /execute-plan is the gated entry that wraps it. |
| [file-todos](../skills/file-todos/SKILL.md) | Manage an existing todos/ file tracker with status, dependencies, and review triage. |
| [full-stop](../skills/full-stop/SKILL.md) | Use when told "full stop", or when asked to own a change end to end up to a merge-ready pull request. Verify, cross-lab review, open the PR ready, register the watcher, fix CI, escalate, then stop. Never merges. |
| [galiana](../skills/galiana/SKILL.md) | Inspect engineering discipline metrics, defect escapes, overrides, cost, and agent scorecards. |
| [gardener](../skills/gardener/SKILL.md) | Use for repository upkeep — turning a recurring bad pattern into a lint rule before cleaning it up, shrink-only baselines, one-dependency-family commits, and a docs-pins check for versions quoted in AGENTS.md and READMEs. |
| [interop-with-gsd](../skills/interop-with-gsd/SKILL.md) | Recognize /gsd:* requests and map the GSD framework to Clavain. Informational unless gsd-plugin is installed. |
| [interop-with-superpowers](../skills/interop-with-superpowers/SKILL.md) | Recognize /superpowers:* requests and map the superpowers rig to Clavain. Informational unless installed. |
| [interserve-engine](../skills/interserve-engine/SKILL.md) | Internal engine for /clavain:interserve: dispatch bounded coding tasks with debate and review gates. |
| [landing-a-change](../skills/landing-a-change/SKILL.md) | Land verified work on trunk, or finish a feature branch or worktree, after tests and required review; preserve release authority. |
| [lane](../skills/lane/SKILL.md) | Manage thematic Beads work lanes, tags, velocity, and starvation. |
| [plan-reviewer](../skills/plan-reviewer/SKILL.md) | Review a completed project step against its implementation plan and coding standards. |
| [pr-comment-resolver](../skills/pr-comment-resolver/SKILL.md) | Resolve PR review comments with verified code changes and per-comment outcomes. |
| [project-onboard](../skills/project-onboard/SKILL.md) | Set up a Sylveste project, new or existing — introspect, create repo, scaffold docs/automation/observability, seed via interpath. |
| [refactor-safely](../skills/refactor-safely/SKILL.md) | Use for significant refactoring — duplication detection, characterization tests, staged execution, simplicity review. |
| [remontoire](../skills/remontoire/SKILL.md) | Operate the Remontoire portfolio agency — status, shadow/proposal cycles, approval decisions, resuming approved work, verifying receipts. |
| [ship](../skills/ship/SKILL.md) | Use when work is done and you need to commit, push, close beads, and sync in one shot. The quick session-close ceremony. |
| [subagent-driven-development](../skills/subagent-driven-development/SKILL.md) | Use when executing implementation plans with independent tasks in the current session |
| [ui-polish](../skills/ui-polish/SKILL.md) | Targeted frontend polish — tooltips, labels, layout, spacing, mobile, chart styling — from a screenshot or URL plus a natural-language instruction. |
| [upstream-sync-engine](../skills/upstream-sync-engine/SKILL.md) | Internal engine for /clavain:upstream-sync: inspect upstream changes and produce an upgrade checklist. |
| [using-clavain](../skills/using-clavain/SKILL.md) | Route substantive coding, research, planning, documentation, and review through Sylveste OODARCS. Skip trivial requests. |
| [using-tmux-for-interactive-commands](../skills/using-tmux-for-interactive-commands/SKILL.md) | Drive interactive CLI tools needing a real terminal (vim, git rebase -i, REPLs) via detached tmux send-keys/capture-pane. |
| [writing-plans](../skills/writing-plans/SKILL.md) | Plan multi-step implementation from a spec or requirements before editing code. |

### All agents (6)

| Component | Description |
|---|---|
| [data-migration-expert](../agents/review/data-migration-expert.md) | Validates data migrations, backfills, and production data transformations against reality. Use when PRs involve ID mappings, column renames, enum conversions, or schema changes. |
| [plan-reviewer](../agents/review/plan-reviewer.md) | Use this agent when a major project step has been completed and needs to be reviewed against the original plan and coding standards. |
| [bug-reproduction-validator](../agents/workflow/bug-reproduction-validator.md) | Systematically reproduces and validates bug reports to confirm whether reported behavior is an actual bug. Use when you receive a bug report or issue that needs verification. |
| [codex-delegate](../agents/workflow/codex-delegate.md) | Delegates well-scoped tasks to Codex CLI for cost-efficient execution. Use proactively for implementation, exploration, search, test generation, and code review when the task has clear scope and success criteria. Keep architecture, brainstorming, and interactive work in Claude. |
| [pr-comment-resolver](../agents/workflow/pr-comment-resolver.md) | Addresses PR review comments by implementing requested changes and reporting resolutions. Use when code review feedback needs to be resolved with code changes. |
| [ui-polish](../agents/workflow/ui-polish.md) | Iterates on UI refinements — tooltips, labels, layouts, mobile fixes, spacing, chart styling. Takes a screenshot or URL + natural language instruction and makes targeted frontend edits. Use when the user provides visual feedback about a web or TUI interface. |

### All commands (66)

| Component | Description |
|---|---|
| [bead-sweep](../commands/bead-sweep.md) | Scan open beads for stale trackers already implemented — deterministic checks then LLM verification. |
| [blast-radius](../commands/blast-radius.md) | Find what a change could break somewhere else before it ships, and prove the one fact it is safe because of by running real code |
| [brainstorm](../commands/brainstorm.md) | Collaborative brainstorm — assess clarity, research repo, explore approaches, capture design. Auto-handoff to /write-plan. |
| [campaign](../commands/campaign.md) | Orchestrate epic execution — read children, topo-sort by dependencies, dispatch phases sequentially with parallel features |
| [changelog](../commands/changelog.md) | Create engaging changelogs for recent merges to main branch |
| [clavain-doctor](../commands/clavain-doctor.md) | Quick health check — verifies MCP servers, external tools, beads, and plugin configuration without making changes |
| [clavain-help](../commands/clavain-help.md) | Show Clavain commands organized by daily drivers first, then by workflow stage |
| [clavain-init](../commands/clavain-init.md) | Scaffold .clavain/ agent memory directory in the current project |
| [clavain-review](../commands/clavain-review.md) | Perform exhaustive code reviews using multi-agent analysis and deep inspection |
| [clavain-status](../commands/clavain-status.md) | Unified status view across Clavain, artifact generation, doc drift, and coordination |
| [clodex-toggle](../commands/clodex-toggle.md) | Toggle interserve execution mode |
| [codex-bootstrap](../commands/codex-bootstrap.md) | Bootstrap or check Clavain Codex installation health (install + wrapper sync + doctor) |
| [compound](../commands/compound.md) | Document a recently solved problem to compound your team's knowledge |
| [correct](../commands/correct.md) | Find the mistakes agents keep repeating in this repo and make each one impossible, at the highest level that works |
| [create-agent-skill](../commands/create-agent-skill.md) | Create or edit Claude Code skills with expert guidance on structure and best practices |
| [debate](../commands/debate.md) | Run a structured Claude↔Codex debate before implementing a complex task |
| [deepen](../commands/deepen.md) | Rewrite an ask as a deeper version, not a bigger one: name the top practitioner's method, the rawest source, the real instruments and the external evidence that would prove the result |
| [describe-pr](../commands/describe-pr.md) | Generate PR title and description from current branch commits |
| [distill](../commands/distill.md) | Synthesize accumulated docs into categorized solutions and generate missing SKILL-compact.md files |
| [execute-plan](../commands/execute-plan.md) | Slash-command entry that enforces the pre-execution gate, records the phase transition, then runs a written plan via the executing-plans skill. Use the executing-plans skill directly when no gate or phase tracking is wanted. |
| [fixbuild](../commands/fixbuild.md) | Run build, capture error, fix it, re-run — fast loop for type errors and build failures without heavyweight debugging |
| [freeze](../commands/freeze.md) | Restrict file edits to declared paths — scope-lock for parallel-session safety |
| [galiana](../commands/galiana.md) | Discipline analytics — view KPIs, report defects, or reset cache |
| [generate-command](../commands/generate-command.md) | Create a new custom slash command following conventions and best practices |
| [goal-form](../commands/goal-form.md) | Collaborative goal-formation ritual: research-first inter-elicitation → charter → stakes-routed review → mint (ic goal) → /goal handoff |
| [grill-me](../commands/grill-me.md) | Interview the user relentlessly about a plan or design until every branch of the decision tree is settled |
| [handoff](../commands/handoff.md) | Generate a concise session handoff summary as a dated markdown file, grounded in intercore run state |
| [heal-skill](../commands/heal-skill.md) | Fix incorrect SKILL.md files when a skill has wrong instructions or outdated API references |
| [interserve](../commands/interserve.md) | Run Codex-first execution flow for larger scope work |
| [land](../commands/land.md) | Run the landing workflow for trunk-based handoff |
| [migration-safety](../commands/migration-safety.md) | Slash-command entry that fans out three parallel agents for a full pre-deploy safety assessment of a DB migration or data change. For a single-reviewer validation of migration code against production data, use the data-migration-expert skill instead. |
| [model-routing](../commands/model-routing.md) | Toggle subagent model routing between economy (smart defaults) and quality (all opus) mode |
| [next-goal](../commands/next-goal.md) | Generate a Next-goal block (2-4 leverage-ranked candidates + recommendation + ready-to-paste /goal text) — invoke manually after a /goal completes or whenever you want a fresh set of candidates |
| [peers](../commands/peers.md) | Read-only viewer for detected peer agent rigs (superpowers, GSD, compound-engineering). Lists detection state and recommended bridge skills. Never makes changes. |
| [plan-review](../commands/plan-review.md) | Have multiple specialized agents review a plan in parallel |
| [pr-triage](../commands/pr-triage.md) | Triage all open PRs — batch by theme, review with parallel agents, generate report, walk through decisions. With a PR reference, run one follow-up pass on your own PR after a watcher update. |
| [prototype](../commands/prototype.md) | Build disposable code to answer one design question, record the evidence and answer, then remove or quarantine the experiment |
| [quality-gates](../commands/quality-gates.md) | Gate orchestrator — prepares diff, delegates review to flux-drive, enforces pass/fail gate |
| [recall](../commands/recall.md) | Search across all knowledge systems — curated docs, memory files, legacy entries |
| [refactor](../commands/refactor.md) | Plan and execute safe refactors with explicit risk controls |
| [reflect](../commands/reflect.md) | Capture sprint learnings and register the reflection artifact |
| [remontoire](../commands/remontoire.md) | Operate the Remontoire portfolio agency across hosts with explicit approval and receipt boundaries |
| [repro-first-debugging](../commands/repro-first-debugging.md) | Disciplined bug investigation — reproduce first, then diagnose. Composes debugging agents. |
| [resolve](../commands/resolve.md) | Resolve findings from any source — auto-detects TODOs, PR comments, or todo files, then resolves in parallel |
| [retro](../commands/retro.md) | Read a session, a PR with its session, or a week of merged PRs and propose ranked changes to the environment that would have stopped repeated mistakes |
| [review-discipline](../commands/review-discipline.md) | Run disciplined code review and feedback triage |
| [review-doc](../commands/review-doc.md) | Quick single-pass document refinement — assess clarity, score quality, fix issues, offer iteration |
| [route](../commands/route.md) | Universal entry point — discovers work, resumes sprints, classifies tasks, and dispatches to /sprint or /work |
| [setup](../commands/setup.md) | Bootstrap Clavain for the active runtime (Codex or Claude Code) and verify health |
| [show-me-your-work](../commands/show-me-your-work.md) | Keep a reviewable decision trail for long-running or unattended work, one TSV row per decision |
| [smoke-test](../commands/smoke-test.md) | Run smoke tests against a running app — detect dev server, walk critical user journeys, report results |
| [sprint-dag](../commands/sprint-dag.md) | Visualize sprint execution as a DAG — shows phases, dispatches, and artifacts |
| [sprint-status](../commands/sprint-status.md) | Deep sprint workflow scan — session continuity, pipeline, plan, beads, recommendations. |
| [sprint](../commands/sprint.md) | Phase sequencer — brainstorm, strategize, plan, execute, review, ship. Use /route for smart dispatch. |
| [strategy](../commands/strategy.md) | Structure brainstorm output into a PRD with features, create beads for tracking, and validate before detailed planning |
| [tdd](../commands/tdd.md) | Run disciplined test-driven development (RED-GREEN-REFACTOR) for a task |
| [todos](../commands/todos.md) | Create and maintain file-based todo tracking |
| [triage](../commands/triage.md) | Triage and categorize findings for the CLI todo system |
| [unfreeze](../commands/unfreeze.md) | Lift the /freeze scope lock — restore full edit permissions |
| [update-check](../commands/update-check.md) | Conservative update check — reports available Sylveste/Clavain/Codex updates without changing anything |
| [upstream-sync](../commands/upstream-sync.md) | Check upstream repos (beads, oracle, superpowers, compound-engineering) for updates and generate upgrade checklist |
| [verify](../commands/verify.md) | Run completion verification before claiming work is done |
| [wayfind](../commands/wayfind.md) | Chart or work a decision map in beads for an effort whose destination is known but whose route spans many sessions |
| [waymap](../commands/waymap.md) | Chart or work a project's Now / Next / Later roadmap in beads, as bets the coordinator commits, defers or drops |
| [work](../commands/work.md) | Execute work plans efficiently while maintaining quality and finishing features |
| [write-plan](../commands/write-plan.md) | Create detailed implementation plan with bite-sized tasks |
