---
name: update-check
description: Conservative update check — reports available Sylveste/Clavain/Codex updates without changing anything
argument-hint: "[optional: --full --refresh]"
---

# Update Check

Run the conservative update checker. This command is read-only.

## Behavior

- Default: light check
  - current Sylveste checkout, if detectable
  - `~/.codex/clavain`
  - installed Claude plugin version vs local Codex clone
- `--full`: also checks recommended `~/.codex/*` companion repos against origin
- `--refresh`: ignores cache and runs the network checks now

## Command

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/check-install-updates.sh $ARGUMENTS
```

Summarize the results for the user and call out the exact update command to run when drift is detected.
