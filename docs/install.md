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

Then restart Codex.

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

## Full Sylveste platform

For the companion ecosystem, services and terminal tools, follow the
[Sylveste Quick Start](https://github.com/mistakeknot/Sylveste#quick-start).
The platform uninstall command above runs from that repository.
