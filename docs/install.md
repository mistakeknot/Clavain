# Other install options

The recommended full install is in the [README](../README.md#install).

## Uninstall

Run the Clavain uninstall commands from a local Clavain clone, not this docs directory.

```bash
# Remove Clavain + companions from Claude Code
bash scripts/uninstall.sh

# Remove Clavain only, keep companions
bash scripts/uninstall.sh --keep-companions

# Full platform uninstall (from Sylveste repo)
bash install.sh --uninstall
```

## Codex install

Clavain can also run in Codex via native skill discovery and generated prompt wrappers.

Quick path:

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/Clavain/main/.codex/agent-install.sh | bash -s -- --update --json
```

The script clones Clavain into `~/.codex/clavain` by default. When an existing
checkout is found, `--update` runs `git pull --ff-only` before installation.
If that pull fails, the script ignores the failure (`|| true`) and proceeds
with the existing checkout.
The URL above executes the current `main` script; inspect it before running it.
This default path also runs the companion installer and its backup-first legacy
artifact cleanup described below. Then restart Codex.

The default Codex bootstrap now installs the recommended Interverse companion set as well, not just Clavain itself.

> **Migrating from superpowers or compound-engineering?** The ecosystem installer (`install-codex-interverse.sh install`) automatically removes known legacy prompt wrappers, legacy `~/.codex/skills/*` artifacts (symlink or directory), and legacy superpowers clone artifacts with backup-first safety (`~/.codex/.clavain-backups/<timestamp>/`).

From a local clone:

```bash
make codex-refresh
make codex-doctor
make codex-doctor-json
```

Detailed guide: [Codex guide](README.codex.md)  
Single-file bootstrap target: [bootstrap guide](../.codex/INSTALL.md)

## Claude Code plugin only

This installs Clavain without companion or environment setup. Add the marketplace first:

```text
/plugin marketplace add mistakeknot/interagency-marketplace
/plugin install clavain@interagency-marketplace
```

Install the required companions listed in the [component reference](component-reference.md#required-companions).

## Local development

With Git and Claude Code installed:

```bash
git clone https://github.com/mistakeknot/Clavain.git
cd Clavain
claude --plugin-dir .
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development checks.

## Kimi Code

The rig declares a Kimi platform in [agent-rig.json](../agent-rig.json).
The [Kimi installer](../scripts/install-kimi.sh) provides `install`, `update`,
`doctor`, and `uninstall` actions for skill discovery, manifests, hooks, and MCP
setup. It currently assumes the Sylveste `os/Clavain` directory layout; inspect
its paths before using it from a standalone clone.

## Hermes

The [Hermes adapter](../adapters/hermes/plugin.yaml) has a dedicated activation
script, [sync-hermes-adapter.py](../scripts/sync-hermes-adapter.py).
Follow the [Hermes setup procedure](canon/reasoning-routing-operations.md#host-delivery-and-evidence)
using the selected Hermes virtualenv's Python with PyYAML and an existing profile.
The script supports `--dry-run` and `--check`; it links the adapter into that
profile and edits its plugin lists: it adds Clavain to `plugins.enabled` and
removes it from `plugins.disabled` when that list exists. See the
[canon procedure](canon/reasoning-routing-operations.md#host-delivery-and-evidence)
for the profile changes and setup checks.

## Full Sylveste platform

For the companion ecosystem, services and terminal tools, follow the
[Sylveste Quick Start](https://github.com/mistakeknot/Sylveste#quick-start).
The platform uninstall command above runs from that repository.
