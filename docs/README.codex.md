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
It also manages a Clavain block in `~/.codex/AGENTS.md`, syncs MCP servers into `~/.codex/config.toml`, and writes conversion diagnostics to `~/.codex/prompts/.clavain-conversion-report.json`.
Wrapper conversion also normalizes `AskUserQuestion` references to a Codex elicitation adapter policy:
use `request_user_input` when available (Plan mode), otherwise ask in chat with numbered options and pause for response.

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

For the full ecosystem install (all recommended Interverse plugins from `agent-rig.json` + linked Codex skills like `flux-drive`, `interpeer`, and `systematic-debugging`):

```bash
bash ~/.codex/clavain/scripts/install-codex-interverse.sh install
bash ~/.codex/clavain/scripts/install-codex-interverse.sh doctor --json
```

This ecosystem install also generates Interverse command wrappers in `~/.codex/prompts` (for example `interflux-flux-drive`, `interpath-roadmap`, `interlock-interlock-status`) and adapter-rewrites Clavain wrappers to use those prompts.
It applies the same elicitation adapter normalization for companion prompts.

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
3. Use generated Interverse prompt wrappers when you want command-style companion invocation:
   - `/prompts:interflux-flux-drive`
   - `/prompts:interflux-flux-research`
   - `/prompts:interpath-roadmap`
   - `/prompts:interlock-interlock-status`
4. Use `scripts/dispatch.sh` when you want Codex-agent delegation behavior from `codex`.
5. Use the Codex helper CLI for discovery/bootstrap:
   - `~/.codex/clavain/.codex/clavain-codex bootstrap`
   - `~/.codex/clavain/.codex/clavain-codex find-skills`
   - `~/.codex/clavain/.codex/clavain-codex use-skill using-clavain`

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
- Legacy `~/.codex/skills/clavain` path is absent (clean-break migration)
- Prompt wrappers in `~/.codex/prompts` (including stale/missing checks)
- Conversion report in `~/.codex/prompts/.clavain-conversion-report.json`
- Managed Clavain block in `~/.codex/AGENTS.md`
- Managed Clavain MCP block in `~/.codex/config.toml`
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
   Confirm legacy path is removed:
   ```bash
   ls -la ~/.codex/skills/clavain
   # expected: No such file or directory
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

### Legacy artifacts and backups

Legacy superpowers/compound artifacts are removed automatically during ecosystem install:

```bash
bash ~/.codex/clavain/scripts/install-codex-interverse.sh install
```

Removed artifacts are preserved in:

```bash
~/.codex/.clavain-backups/<timestamp>/
```
