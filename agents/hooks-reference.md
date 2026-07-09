# Clavain — Hooks Reference

## Hook Conventions

- Registration in `hooks/hooks.json` — specifies event, matcher regex, and command
- Scripts in `hooks/` — use `${CLAUDE_PLUGIN_ROOT}` for portable paths
- Scripts must output valid JSON to stdout
- Use `set -euo pipefail` in all hook scripts

## Active Hooks

- **SessionStart** (matcher: `startup|resume|clear|compact`):
  - `session-start.sh` — injects `using-clavain` skill content, interserve behavioral contract (when active), upstream staleness warnings. Sources `sprint-scan.sh` for sprint awareness. On compact: injects mandatory recovery protocol (re-read CLAUDE.md, confirm conventions, check in-progress beads).
- **PreToolUse** (matcher: `Edit|Write|MultiEdit`):
  - `guard-plugin-cache.sh` — blocks edits to `~/.claude/plugins/cache/` (cached copies overwritten on install; directs to source repo)
- **PostToolUse** (matcher: `Edit|Write|MultiEdit|NotebookEdit`):
  - `interserve-audit.sh` — logs source code writes when interserve mode is active (audit only, no denial)
- **PostToolUse** (matcher: `Edit|Write|MultiEdit`):
  - `catalog-reminder.sh` — reminds about catalog updates when components change
- **PostToolUse** (matcher: `Bash`):
  - `auto-publish.sh` — detects `git push` in plugin repos, auto-bumps patch version if needed, syncs marketplace, syncs GitHub repo description with current component counts
  - `bead-agent-bind.sh` — binds agent identity to beads claimed with bd update/claim (warns on overlap, notifies other agent)
- **Stop**:
  - `auto-stop-actions.sh` — unified post-turn actions: detects signals via lib-signals.sh; goal-completed signal triggers the goal-cadence tier (/clavain:next-goal, highest priority), weight >= 4 triggers /clavain:compound, bead-closed + opt-in triggers self-dispatch, weight >= 3 triggers /interwatch:watch
- **SessionEnd**:
  - `dotfiles-sync.sh` — syncs dotfile changes at end of session

## Hook Libraries

Sourced by hook scripts, not registered as hooks themselves:

| Library | Purpose |
|---------|---------|
| `lib.sh` | Shared utilities (escape_for_json, plugin path discovery) |
| `lib-intercore.sh` | Intercore CLI wrappers (ic run/state/sprint/coordination) |
| `lib-compose.sh` | Thin bridge to `clavain-cli compose` — provides `compose_dispatch()` and `compose_available()` (in `scripts/`, not `hooks/`) |
| `lib-sprint.sh` | Sprint state queries (phase, gate, budget, artifact); exports `CLAVAIN_COMPOSE_PLAN` after phase advance |
| `lib-signals.sh` | Signal detection engine for auto-stop-actions |
| `lib-spec.sh` | Agency spec loader — reads `config/agency-spec.yaml` at runtime |
| `lib-verdict.sh` | Verdict file write/read utilities for structured agent handoffs |
| `lib-gates.sh` | Phase gate shim — delegates to interphase when installed, no-op stub otherwise |
| `lib-discovery.sh` | Plugin discovery shim — delegates to interphase when installed, no-op stub otherwise |
