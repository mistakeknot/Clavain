# Clavain — Codex Integration & Companion Plugins

## Runbooks

- Codex sync operations: `docs/runbooks/codex-sync.md`
- Optional automated Codex refresh job: `scripts/codex-auto-refresh.sh` (cron/systemd/launchd examples in `docs/runbooks/codex-sync.md`)
- GitHub web PR agent commands (`/clavain:claude-review`, `/clavain:codex-review`, `/clavain:dual-review`) are documented in `docs/runbooks/codex-sync.md`
- GitHub issue command `/clavain:upstream-sync` (for `upstream-sync` issues) is documented in `docs/runbooks/codex-sync.md`

## Interserve Dispatch

- dispatch.sh does NOT support `--template` — use `--prompt-file`
- Codex CLI v0.101.0: `--approval-mode` replaced by `-s`/`--sandbox`. Prompt is positional, NOT `-p`

## Operational Notes

- Uses pnpm, not npm
- `docs-sp-reference/` is read-only historical archive
- Full routing tables in `skills/using-clavain/references/routing-tables.md`
- gen-catalog.py expects pattern `\d+ skills, \d+ agents, and \d+ commands`

### Upstream Sync

- Sync state in `upstreams.json` (commit hashes per upstream + fileMap)
- **sprint.md is canonical pipeline command** (renamed from lfg.md). lfg.md is alias
- **Post-sync checklist**: grep `compound-engineering:|/workflows:|ralph-wiggum:|/deepen-plan` in agents/commands/skills

## Modpack — Companion Plugins

Clavain is a modpack: an opinionated integration layer that configures companion plugins into a cohesive engineering rig. It doesn't duplicate their capabilities — it routes to them and wires them together.

### Required

These must be installed for Clavain to function fully.

| Plugin | Source | Why Required |
|--------|--------|-------------|
| **context7** | claude-plugins-official | Runtime doc fetching. Clavain's MCP server. Skills use it to pull upstream docs without bundling them. |
| **explanatory-output-style** | claude-plugins-official | Educational insights in output. Injected via SessionStart hook. |

### Companion Plugins

Extracted subsystems that Clavain delegates to via namespace routing.

| Plugin | Source | What It Provides |
|--------|--------|-----------------|
| **interflux** | interagency-marketplace | Multi-agent review + research engine. 7 fd-* review agents, 5 research agents, flux-drive/flux-research skills, qmd + exa MCP servers. |
| **interphase** | interagency-marketplace | Phase tracking, gates, and work discovery. lib-phase.sh, lib-gates.sh, lib-discovery.sh. Clavain shims delegate to interphase when installed. |
| **interspect** | interagency-marketplace | Agent profiler — evidence collection, classification, routing overrides, canary monitoring. |
| **interline** | interagency-marketplace | Statusline renderer. Shows dispatch state, bead context, workflow phase, interserve mode. |
| **interwatch** | interagency-marketplace | Doc freshness monitoring. Auto-discovers watchable docs, detects drift via 14 signals, dispatches to interpath/interdoc for refresh. Triggered by `auto-stop-actions.sh` when signal weight >= 3. |

### Recommended

These enhance the rig significantly but aren't hard dependencies.

| Plugin | Source | What It Adds |
|--------|--------|-------------|
| **agent-sdk-dev** | claude-plugins-official | Agent SDK scaffolding: `/new-sdk-app` command, Python + TS verifier agents. |
| **plugin-dev** | claude-plugins-official | Plugin development: 7 skills, 3 agents including agent-creator and skill-reviewer. |
| **interdoc** | interagency-marketplace | AGENTS.md generation for any repo. |
| **tool-time** | interagency-marketplace | Tool usage analytics across sessions. |
| **security-guidance** | claude-plugins-official | Security warning hooks on file edits. Complements fd-safety agent. |
| **serena** | claude-plugins-official | Semantic code analysis via LSP-like tools. |

### Infrastructure (language servers)

Enable based on which languages you work with.

| Plugin | Language |
|--------|----------|
| **gopls-lsp** | Go |
| **pyright-lsp** | Python |
| **typescript-lsp** | TypeScript |
| **rust-analyzer-lsp** | Rust |

### Conditional (domain-specific)

| Plugin | Enable When |
|--------|------------|
| **supabase** | Working with Supabase backends |
| **vercel** | Deploying to Vercel |
| **tldrs** + **tldr-swinton** | Hitting context limits, want token-efficient exploration |
| **tuivision** | Building or testing terminal UI apps |

### Conflicts — Disabled by Clavain

Plugins that overlap with Clavain's equivalents (duplicate agents cause confusing routing):

code-review, pr-review-toolkit, code-simplifier, commit-commands, feature-dev, claude-md-management, frontend-design, hookify. Full rationale: `docs/plugin-audit.md`
