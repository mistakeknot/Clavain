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
```

Expected:
- `~/.agents/skills/clavain` points to `~/.codex/clavain/skills`
- `~/.codex/skills/clavain` is only expected when `CLAVAIN_LEGACY_SKILLS_LINK=1`
- A symlink at `~/.codex/skills/clavain` is cleaned up automatically when legacy mode is off.
- Prompt wrappers exist in `~/.codex/prompts/clavain-*.md`
- Stale wrapper cleanup happens automatically during install.
- `install-codex.sh doctor` exits with success when links/helpers/wrappers are in sync.

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
```

## Uninstall

```bash
bash ~/.codex/clavain/scripts/install-codex.sh uninstall
```

Optionally remove the clone:

```bash
rm -rf ~/.codex/clavain
```
