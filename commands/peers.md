---
name: peers
description: Read-only viewer for detected peer agent rigs (superpowers, GSD, compound-engineering). Lists detection state and recommended bridge skills. Never makes changes.
argument-hint: "[no arguments]"
---

# Clavain Peer Status

Read-only diagnostic. Never makes changes — does not modify `~/.claude/settings.json`, any plugin file, or any project file.

## What This Does

Reports which peer agent rigs (alternative Claude Code rigs that share vocabulary with Clavain) are present on this system, whether they are active, and which bridge skill documents the methodology mapping. Mirrors the inspection pattern of `/clavain:doctor`.

Peer rigs are never auto-disabled by `/clavain:setup`. Users opt into Clavain alongside their existing rig; both coexist.

## How To Run

```bash
CLAVAIN_DIR=$(dirname "$(ls ~/.claude/plugins/cache/interagency-marketplace/clavain/*/agent-rig.json 2>/dev/null | head -1)")
RESULT=$(bash "$CLAVAIN_DIR/scripts/modpack-install.sh" --dry-run --quiet --category=peers)
echo "$RESULT" | jq
```

Parse the JSON output (`peers_detected`, `peers_active`) and present a row per peer declared in `agent-rig.json`. Cross-reference each peer source against `peers_detected` (installed?) and `peers_active` (enabled?), and surface the matching `bridge_skill`:

```
Detected peer rigs:
  - superpowers@superpowers-marketplace          [installed, active]      bridge: skills/interop-with-superpowers
  - compound-engineering@every-marketplace       [installed, disabled]    bridge: skills/interop-with-superpowers
  - gsd-plugin@jnuyens                           [not installed]          bridge: skills/interop-with-gsd

No peer rigs are auto-disabled by /clavain:setup. To inspect interop guidance for a detected peer:
  /clavain:help interop-with-superpowers
  /clavain:help interop-with-gsd
```

## Codex CLI

This command is Claude Code only. On Codex, use the equivalent invocation:

```bash
bash ~/.codex/clavain/scripts/modpack-install.sh --dry-run --quiet --category=peers | jq
```

## Output Contract

Read-only. Implementation MUST verify this by passing `--dry-run` to the underlying script and reading the JSON. Never call `claude plugin disable` or any other state-mutating command from this path.
