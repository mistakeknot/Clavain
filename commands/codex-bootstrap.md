---
name: codex-bootstrap
description: Bootstrap or check Clavain Codex installation health (install + wrapper sync + doctor)
---

# Clavain Codex Bootstrap

Run this first in a Codex session or after changing Clavain command/skill files.

```bash
SCRIPT_PATH="${CLAVAIN_SOURCE_DIR:-$HOME/.codex/clavain}/scripts/codex-bootstrap.sh"
if [[ ! -f "$SCRIPT_PATH" ]]; then
  # fallback for local clone locations commonly used during development
  for candidate in \
    "$HOME/projects/Interverse/hub/clavain/scripts/codex-bootstrap.sh" \
    "$HOME/projects/Clavain/scripts/codex-bootstrap.sh" \
    "$HOME/.codex/clavain/scripts/codex-bootstrap.sh"; do
    if [[ -f "$candidate" ]]; then
      SCRIPT_PATH="$candidate"
      break
    fi
  done
fi

if [[ -z "$SCRIPT_PATH" || ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: codex-bootstrap.sh not found. Re-run agent install."
  echo "Set CLAVAIN_SOURCE_DIR to the Clavain checkout that contains scripts/codex-bootstrap.sh."
  exit 1
fi

# Direct automation-friendly bootstrap entrypoint for Codex agents
bash "$SCRIPT_PATH"
```

## JSON health output (automation)

For machine-readable output, run:

```bash
bash "$SCRIPT_PATH" --json
```

For read-only checks without modifying state:

```bash
bash "$SCRIPT_PATH" --check-only --json
```
