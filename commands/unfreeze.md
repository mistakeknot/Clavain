---
name: unfreeze
description: Lift the /freeze scope lock — restore full edit permissions
---

# Unfreeze — Lift Scope Lock

Remove the freeze-scope rule written by `/clavain:freeze` and release any interlock reservations it made.

**Announce:** "Lifting freeze..."

## Steps

### 1. Remove the rule

Delete `.claude/hookify.freeze-scope.local.md` from the current project.

If the file does not exist, report "No freeze is active in this project." and stop — this is a clean no-op, not an error.

### 2. Release interlock reservations (best-effort)

If the interlock MCP is available and this session holds reservations matching the frozen paths, release them (`release_files` with the same patterns, or `my_reservations` first to check). Failure is non-fatal.

### 3. Confirm

Report: "Freeze lifted — full edit scope restored." Include the scope that was just released (read the rule's message body before deleting it).
