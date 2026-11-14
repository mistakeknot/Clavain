# Clavain

[![Tests](https://github.com/mistakeknot/Clavain/actions/workflows/test.yml/badge.svg)](https://github.com/mistakeknot/Clavain/actions/workflows/test.yml)

Clavain helps your coding agent plan, build, test, and review software, with reusable workflows that keep the work organized and ready for you to inspect.

For example, install Clavain, open your project in Claude Code, and run
`/clavain:sprint "add CSV export"`. It walks through requirements, a plan,
implementation, tests, and review before preparing the change to ship.

## What you get

- A guided path from feature idea to tested, reviewed code.
- Standalone commands for planning, debugging, review, and finishing a change.
- Written plans and review findings you can inspect in your repository.
- Optional second opinions from other models through companion plugins.

Clavain runs on Claude Code, Codex, Hermes, and Kimi Code; Claude Code is the
primary path. See [other host setups](docs/install.md). It is an opinionated personal workflow, useful both as a daily
tool and as a reference for building your own. Read the
[background and design principles](docs/background.md) for its goals and limits.

## Install

**Recommended: the full Claude Code install.** This installs Clavain and its
companions and configures MCP servers (tools the agent can call). It also
configures environment settings and resolves conflicting plugins; review the
installer's proposed changes.

Have these ready **before** running the installer:

- [Claude Code](https://code.claude.com/docs/en/overview), installed and signed in.
- [Node.js 20+](https://nodejs.org/en/download), including `npx`.
- [Go](https://go.dev/dl/) for `clavain-cli`: the CLI currently declares **Go 1.25.0**
  in its module. Use the module requirement when choosing a Go toolchain.
- Git and a project you can work in.

**Required companions:** `context7` (library documentation) and
`explanatory-output-style` (explanations in agent output).
**Recommended companions:** `interphase` (phase tracking), `interflux` (review),
`intertest` (testing discipline), and `interpeer` (second opinions).
The full installer handles companions; plugin-only installation requires setup.
See the [companion reference](docs/component-reference.md#the-agent-rig) for the
larger ecosystem and conflicts.

Run in your terminal:

```bash
npx @gensysven/agent-rig install mistakeknot/Clavain
```

Restart Claude Code in your project directory. Verify the installation inside
Claude Code:

```text
/clavain:clavain-doctor
```

Resolve any reported missing tools or companions before starting a sprint.
Then run `/clavain:clavain-help` to confirm the command menu is available.
[Installation troubleshooting](docs/troubleshooting.md) covers marketplace and
stale plugin-cache errors.

## First 10 minutes

Start with a small change in an existing project. These are **Claude Code slash
commands**, not terminal commands. The `/clavain:` prefix makes the plugin explicit.

1. Check the available workflows:

   ```text
   /clavain:clavain-help
   ```

2. Ask Clavain to plan and build one small feature:

   ```text
   /clavain:sprint "add CSV export"
   ```

   It clarifies requirements, structures the work, writes and reviews a plan,
   implements it, runs tests, reviews quality, resolves findings, and records
   lessons before the ship step. Answer its questions and inspect the artifacts
   as it goes. Approval checkpoints and your repository's rules still apply.

3. Inspect the work's current state:

   ```text
   /clavain:sprint-status
   ```

4. For a planning-only session, start with:

   ```text
   /clavain:brainstorm "how should CSV export work?"
   ```

A sprint can take longer than ten minutes; the aim here is to start one and
understand its checkpoints. For a new repository, `/clavain:project-onboard`
sets up tracking and documentation before your first sprint.

## Choose a workflow

| You want to… | Start with |
|---|---|
| Build a feature through the full lifecycle | `/clavain:sprint` |
| Test a design question with disposable code | `/clavain:prototype` (`/prototype`) |
| Explore an idea before committing to it | `/clavain:brainstorm` |
| Write an implementation plan | `/clavain:write-plan` |
| Review a document or repository | `/interflux:flux-drive` |
| Check your setup | `/clavain:clavain-doctor` |

The [workflow guide](docs/workflow-guide.md) explains the lifecycle, review,
optional Codex delegation, and authorization setup. The
[component reference](docs/component-reference.md) lists skills, agents, commands,
hooks, customization, and routing. Advanced permission handoffs are covered in
[scoped delegation tokens](docs/delegation-tokens.md).

## Other install options

For **plugin-only**, **local development**, **Codex**, the full **Sylveste**
platform, or **uninstalling**, see [Other install options](docs/install.md).
Codex uses native skill discovery and generated prompt wrappers; restart it
after installation. Additional model tools such as Codex CLI and Oracle are
optional for the Claude Code path.

## Contributing and background

- [Contributing](CONTRIBUTING.md): local setup and existing validation commands.
- [Philosophy, development model, and limits](docs/background.md).
- [Vision and roadmap](docs/vision.md).
- [Troubleshooting](docs/troubleshooting.md).

## Credits

Named after one of the protagonists from Alastair Reynolds's [Revelation Space series](https://en.wikipedia.org/wiki/Revelation_Space_series). Built on the work of:

- **Jesse Vincent** ([@obra](https://github.com/obra)): [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code)
- **Kieran Klaassen** ([@kieranklaassen](https://github.com/kieranklaassen)): [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin) at [Every](https://every.to)
- **Steve Yegge** ([@steveyegge](https://github.com/steveyegge)): [beads](https://github.com/steveyegge/beads)
- **Peter Steinberger** ([@steipete](https://github.com/steipete)): [oracle](https://github.com/steipete/oracle)
- **Tobi Lütke** ([@tobi](https://github.com/tobi)): [qmd](https://github.com/tobi/qmd)

## License

MIT. Adapted third-party content and its licences are listed in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
