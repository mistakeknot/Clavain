# Clavain for Codex

Clavain is designed first as a Claude Code plugin, but it can also run in Codex using native skill discovery plus prompt wrappers.

This guide gives a Codex-native setup path similar to superpowers and compound.

## Quick Install

Tell Codex:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/mistakeknot/Clavain/main/.codex/INSTALL.md
```

For quick bootstrap, run:

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/Clavain/main/.codex/agent-install.sh | bash -s -- --update --json
```

Or set up manually:

```bash
cd ~/.codex
git clone https://github.com/mistakeknot/Clavain.git clavain
bash ~/.codex/clavain/.codex/agent-install.sh --update --json
```

Restart Codex after install. The installer is idempotent and removes stale `clavain-*.md` wrappers.

If you only want skill discovery (no generated prompt wrappers):

```bash
bash ~/.codex/clavain/scripts/install-codex.sh install --no-prompts
```

From a local checkout of this repo, you can also run:

```bash
make codex-refresh
# Human-readable output:
make codex-doctor
# Machine-readable output:
make codex-doctor-json
make codex-bootstrap       # install/repair + doctor
# Machine-readable bootstrap:
make codex-bootstrap-json
```

For unattended updates, use the new autonomous helper:

```bash
bash scripts/codex-auto-refresh.sh
```

## Windows (PowerShell)

```powershell
git clone https://github.com/mistakeknot/Clavain.git "$env:USERPROFILE\.codex\clavain"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills" | Out-Null
cmd /c mklink /J "$env:USERPROFILE\.agents\skills\clavain" "$env:USERPROFILE\.codex\clavain\skills"
```

Then restart Codex.

## What Works in Codex

| Component | Codex Status | Notes |
|-----------|--------------|-------|
| Skills (`skills/*/SKILL.md`) | Full | Installed via symlink for native discovery |
| Command workflows | High | Installer generates `~/.codex/prompts/clavain-*.md` wrappers from `commands/*.md` |
| Codex dispatch scripts | Full | `scripts/dispatch.sh` and `scripts/debate.sh` are native shell tools |
| Claude hooks (`hooks/*.sh`) | N/A | Claude-only hook system |
| Claude plugin manifest (`.claude-plugin/plugin.json`) | N/A | Claude-only plugin loading |

## Usage Pattern

1. Use Clavain skills directly in Codex (native discovery from `~/.agents/skills/clavain`).
2. Use generated prompt wrappers for command-style workflows:
   - `clavain-lfg`
   - `clavain-brainstorm`
   - `clavain-write-plan`
   - `clavain-work`
   - `clavain-review`
3. Use `scripts/dispatch.sh` when you want Codex-agent delegation behavior from `codex`.

If commands, skills, or dispatch/debate helpers change, run:

```bash
make codex-refresh
# Human-readable output:
make codex-doctor
# Machine-readable output:
make codex-doctor-json
make codex-bootstrap       # quick refresh + health check
```
and restart Codex.

## Verify

```bash
bash ~/.codex/clavain/scripts/install-codex.sh doctor
```

For automation, use JSON output:

```bash
bash ~/.codex/clavain/scripts/install-codex.sh doctor --json
bash ~/.codex/clavain/scripts/codex-bootstrap.sh --json
```

Checks:
- Primary skill link in `~/.agents/skills/clavain`
- Optional legacy skill link in `~/.codex/skills/clavain` (only when `CLAVAIN_LEGACY_SKILLS_LINK=1`)
- Prompt wrappers in `~/.codex/prompts` (including stale/missing checks)
- Codex CLI availability
- For Codex sessions, you can run `make codex-bootstrap` to repair + validate state before work.

If checks fail, `install-codex.sh doctor` exits non-zero.

From this repo checkout, the preferred refresh path is:

```bash
make codex-refresh
# Human-readable output:
make codex-doctor
# Machine-readable output:
make codex-doctor-json
make codex-bootstrap       # repair + doctor in one step
```

## Update

```bash
bash ~/.codex/clavain/.codex/agent-install.sh --update --json
```

## Uninstall

```bash
bash ~/.codex/clavain/scripts/install-codex.sh uninstall
rm -rf ~/.codex/clavain
```

## Troubleshooting

### Skills not showing up

1. Check primary link exists:
   ```bash
   ls -la ~/.agents/skills/clavain
   ```
   If you enabled the legacy link, also verify:
   ```bash
   ls -la ~/.codex/skills/clavain
   ```
2. Re-run installer:
   ```bash
   bash ~/.codex/clavain/.codex/agent-install.sh --update --json
   ```
3. Restart Codex.

### Prompt wrappers missing

Regenerate wrappers:

```bash
bash ~/.codex/clavain/.codex/agent-install.sh --update --json
ls ~/.codex/prompts/clavain-*.md
```

### Existing non-symlink path blocks install

If you already have a real directory/file at `~/.agents/skills/clavain` (or `~/.codex/skills/clavain` when legacy mode is enabled), move it aside first, then run install again.

When legacy mode is off, the installer now removes an existing `~/.codex/skills/clavain` symlink automatically.
