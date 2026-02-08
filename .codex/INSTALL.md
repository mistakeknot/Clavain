# Installing Clavain for Codex

Enable Clavain in Codex using native skill discovery, plus optional command prompt wrappers.

## Prerequisites

- Git
- Codex CLI

## Installation

1. Clone Clavain:
   ```bash
   git clone https://github.com/mistakeknot/Clavain.git ~/.codex/clavain
   ```

2. Run the installer:
   ```bash
   bash ~/.codex/clavain/scripts/install-codex.sh install
   ```

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

Expected:
- `~/.agents/skills/clavain` points to `~/.codex/clavain/skills`
- Prompt wrappers exist in `~/.codex/prompts/clavain-*.md`

## Update

```bash
cd ~/.codex/clavain && git pull --ff-only
bash ~/.codex/clavain/scripts/install-codex.sh install
```

## Uninstall

```bash
bash ~/.codex/clavain/scripts/install-codex.sh uninstall
```

Optionally remove the clone:

```bash
rm -rf ~/.codex/clavain
```
