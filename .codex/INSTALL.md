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
- To keep legacy behavior too, set `CLAVAIN_LEGACY_SKILLS_LINK=1` (adds `~/.codex/skills/clavain`).
- When legacy mode is off, install now removes an existing `~/.codex/skills/clavain` symlink automatically.
- It validates helper/script coverage on `doctor`.
- Wrapper generation is self-healing: stale wrappers for removed/renamed commands are removed.

For Demarch (`clavain + interverse` Codex skills), run:

```bash
bash ~/.codex/clavain/scripts/install-codex-interverse.sh install
```

This installs Clavain plus curated Interverse Codex skills using native `~/.agents/skills` discovery:
- `interdoc`
- `tool-time` (Codex skill variant)
- `tldrs-agent-workflow`

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
- `~/.codex/skills/clavain` is only expected when `CLAVAIN_LEGACY_SKILLS_LINK=1`
- A symlink at `~/.codex/skills/clavain` is cleaned up automatically when legacy mode is off.
- Prompt wrappers exist in `~/.codex/prompts/clavain-*.md`
- Stale wrapper cleanup happens automatically during install.
- `install-codex.sh doctor` exits with success when links/helpers/wrappers are in sync.
- `install-codex-interverse.sh doctor` verifies companion Interverse skill links.

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
   - Removes legacy skill symlinks from `~/.codex/skills/`
   - Warns about the superpowers clone directory

2. Remove the old bootstrap block in `~/.codex/AGENTS.md` that references `superpowers-codex bootstrap` or legacy bootstrap commands.
3. Optionally remove the superpowers clone: `rm -rf ~/.codex/superpowers`
4. Verify `~/.agents/skills/*` links.
5. Restart Codex.

For Claude Code users: the Demarch root installer (`install.sh`) also removes the `superpowers-marketplace` and `every-marketplace` from Claude Code's known marketplaces.

The ecosystem installer only removes symlinks and known prompt wrappers (it does not delete real directories or unknown files).

## Uninstall

```bash
bash ~/.codex/clavain/scripts/install-codex.sh uninstall
```

Optionally remove the clone:

```bash
rm -rf ~/.codex/clavain
```
