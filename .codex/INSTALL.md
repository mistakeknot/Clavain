# Installing Clavain for Codex

Enable Clavain in Codex using native skill discovery, plus optional command prompt wrappers.

## Prerequisites

- Git
- Codex CLI

## Installation

1. Install with one command (from anywhere):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/mistakeknot/Clavain/main/.codex/agent-install.sh | bash -s -- --update --json
   ```

If this is your first time, this script clones `https://github.com/mistakeknot/Clavain.git` into `~/.codex/clavain` and runs the Codex installer.

- The install script links `~/.agents/skills/clavain` and generates wrappers under `~/.codex/prompts/clavain-*.md`.
- It manages a Clavain block in `~/.codex/AGENTS.md` and an MCP block in `~/.codex/config.toml`.
- It writes a conversion report to `~/.codex/prompts/.clavain-conversion-report.json`.
- It enforces clean-break migration by removing `~/.codex/skills/clavain` (symlink or directory) with backup-first safety.
- It validates helper/script coverage on `doctor`.
- Wrapper generation is self-healing: stale wrappers for removed/renamed commands are removed.
- Wrapper generation normalizes `AskUserQuestion` references to a Codex elicitation adapter policy (`request_user_input` when available, otherwise numbered chat elicitation fallback).

Codex bootstrap helper:

```bash
~/.codex/clavain/.codex/clavain-codex bootstrap
```

For Demarch (`clavain + interverse` Codex skills), run:

```bash
bash ~/.codex/clavain/scripts/install-codex-interverse.sh install
```

This installs Clavain plus the full **recommended Interverse plugin set** (from `agent-rig.json`) and links Codex-usable companion skills into native `~/.agents/skills` discovery.

Notable linked skills include:
- `flux-drive` / `flux-research` (interflux)
- `interpeer`
- `systematic-debugging`, `test-driven-development`, `verification-before-completion` (intertest)
- `interdoc`
- `tool-time` (Codex skill variant)
- `tldrs-agent-workflow`

It also generates Interverse command wrappers in `~/.codex/prompts` as:
- `/prompts:interflux-flux-drive`
- `/prompts:interflux-flux-research`
- `/prompts:interpath-roadmap`
- `/prompts:interlock-interlock-status`

During ecosystem install, Clavain wrappers are adapter-rewritten so references like `/interflux:flux-drive` become Codex-safe `/prompts:interflux-flux-drive`.
Companion prompts get the same elicitation adapter normalization.

3. Restart Codex (quit and relaunch the CLI).

## Windows (PowerShell)

The installer script is Bash-oriented. On Windows, set links manually:

```powershell
git clone https://github.com/mistakeknot/Clavain.git "$env:USERPROFILE\.codex\clavain"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills" | Out-Null
cmd /c mklink /J "$env:USERPROFILE\.agents\skills\clavain" "$env:USERPROFILE\.codex\clavain\skills"
```

Restart Codex after creating the junction.

## Verify

```bash
bash ~/.codex/clavain/scripts/install-codex.sh doctor
```

For CI and scripts, use:

```bash
bash ~/.codex/clavain/scripts/install-codex.sh doctor --json
bash ~/.codex/clavain/scripts/install-codex-interverse.sh doctor --json
```

Expected:
- `~/.agents/skills/clavain` points to `~/.codex/clavain/skills`
- `~/.codex/skills/clavain` does not exist (clean-break path)
- Prompt wrappers exist in `~/.codex/prompts/clavain-*.md`
- Stale wrapper cleanup happens automatically during install.
- Conversion report exists at `~/.codex/prompts/.clavain-conversion-report.json`
- `~/.codex/AGENTS.md` includes the managed Clavain block markers
- `~/.codex/config.toml` includes the managed Clavain MCP block markers
- `install-codex.sh doctor` exits with success when links/helpers/wrappers are in sync.
- `install-codex-interverse.sh doctor` verifies recommended Interverse repo installs plus companion skill links.

From this repo checkout, keep Codex views fresh with:

```bash
make codex-refresh
# Human-readable output:
make codex-doctor
# Machine-readable output:
make codex-doctor-json
make codex-bootstrap       # install/repair + health check
# Machine-readable bootstrap:
make codex-bootstrap-json
```

## Update

```bash
bash ~/.codex/clavain/.codex/agent-install.sh --update --json
bash ~/.codex/clavain/scripts/install-codex-interverse.sh install
```

## Migrating from superpowers / compound-engineering

If you previously used **superpowers**, **compound-engineering**, or the old `~/.codex/skills/*` bootstrap patterns:

1. Run:
   ```bash
   bash ~/.codex/clavain/scripts/install-codex-interverse.sh install
   ```
   This automatically:
   - Removes superpowers prompt wrappers from `~/.codex/prompts/`
   - Removes known legacy skill paths from `~/.codex/skills/` (symlink or directory)
   - Removes legacy `~/.codex/superpowers` clone path
   - Moves removed legacy artifacts into `~/.codex/.clavain-backups/<timestamp>/`

2. Remove the old bootstrap block in `~/.codex/AGENTS.md` that references `superpowers-codex bootstrap` or legacy bootstrap commands.
3. Verify `~/.agents/skills/*` links.
4. Restart Codex.

For Claude Code users: the Demarch root installer (`install.sh`) also removes the `superpowers-marketplace` and `every-marketplace` from Claude Code's known marketplaces.

The ecosystem installer removes only known legacy artifacts and preserves them in backup snapshots before deletion.

## Uninstall

```bash
bash ~/.codex/clavain/scripts/install-codex.sh uninstall
```

Optionally remove the clone:

```bash
rm -rf ~/.codex/clavain
```
