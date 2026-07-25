---
name: clodex-toggle
description: Toggle interserve execution mode
allowed-tools:
  - Bash
---

# Interserve Mode Toggle

Run the toggle script and display its output:

```bash
SCRIPT_PATH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/clodex-toggle.sh' 2>/dev/null | head -1)
[[ -z "$SCRIPT_PATH" ]] && SCRIPT_PATH=$(find ~/projects/Clavain -name clodex-toggle.sh -path '*/scripts/*' 2>/dev/null | head -1)
if [[ -z "$SCRIPT_PATH" ]]; then
  echo "Error: Could not locate clodex-toggle.sh" >&2
  exit 1
fi
PROJECT_DIR="$(pwd)" bash "$SCRIPT_PATH"
```
