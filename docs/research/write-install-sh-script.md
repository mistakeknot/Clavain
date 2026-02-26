# Research: install.sh Script for Demarch

## Task

Create a curl-fetchable bash installer at `/home/mk/projects/Demarch/install.sh` for the Clavain + Interverse plugin ecosystem.

## Style Reference

The script follows the conventions established in `os/clavain/scripts/modpack-install.sh`:
- `#!/usr/bin/env bash` shebang
- `set -euo pipefail`
- TTY-aware color variables (check if stdout is a terminal before using ANSI codes)
- `log()` function for user-facing output
- Flag parsing via `for arg in "$@"` loop with `case` statements
- Idempotent operations with `|| true` fallbacks

## Design Decisions

### TTY-Aware Colors
The modpack-install.sh uses a simple `log()` function but doesn't do TTY-aware colors itself (it outputs JSON to stdout, progress to stderr). For this user-facing installer, I adopted a pattern where colors are set based on `[ -t 1 ]` (stdout is a terminal). When piped or redirected, colors are empty strings so output remains clean.

### Flag Parsing
Three flags:
- `--help`: prints usage block and exits 0
- `--dry-run`: sets `DRY_RUN=true`, prefixes all actions with `[DRY RUN]`, does not execute
- `--verbose`: sets `VERBOSE=true`, enables debug-level output via `debug()` function

### Prerequisites Check Order
1. `claude` CLI (REQUIRED) - the entire installer depends on it
2. `jq` (REQUIRED) - needed for JSON parsing by companion plugins
3. `git` (WARN) - useful but not strictly needed for plugin install
4. `bd` (OPTIONAL) - Beads CLI for project initialization

### Installation Steps
1. Add marketplace (idempotent via `|| true`)
2. Install clavain plugin (idempotent via `|| true`)
3. Conditional `bd init` if in a git repo AND bd is available

### Verification
Check for `~/.claude/plugins/cache/interagency-marketplace/clavain/` directory existence as the success indicator.

### Dry Run Behavior
In dry-run mode:
- Prerequisites are still checked (they don't modify anything)
- Each action step is printed with `[DRY RUN]` prefix instead of executing
- The final success/failure message shows what WOULD be printed
- The "next steps" block is always shown

## Implementation

The script was written to `/home/mk/projects/Demarch/install.sh` and made executable with `chmod +x`.

### Key Implementation Details

- **`run()` helper**: Wraps command execution. In dry-run mode, prints the command; in live mode, executes it. This keeps the main flow clean.
- **`check_cmd()`**: Reusable prerequisite checker that takes a command name, required/optional flag, and help text.
- **Unicode checkmarks/crosses**: Uses `\u2713` (checkmark) and `\u2717` (cross) for visual feedback, colored green/red respectively.
- **Exit codes**: 0 on success, 1 on missing required prerequisite or failed installation.
- **stderr vs stdout**: All output goes to stdout (this is a user-facing installer, not a machine-parseable tool like modpack-install.sh).

## Files Modified

- `/home/mk/projects/Demarch/install.sh` (created, chmod +x)
