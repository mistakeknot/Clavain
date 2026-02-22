---
name: codex-sprint
description: Run the full phase-gated sprint workflow in Codex, with explicit fallback when interphase hooks are unavailable
argument-hint: "[feature description or existing bead ID]"
---

Run the full `/clavain:sprint` workflow as an explicit Codex-safe sequence:

## 1. Optional phase backend bootstrap (fail-soft)

```bash
export CLAVAIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/.codex/clavain}"
export CLAVAIN_CLI="${CLAVAIN_ROOT}/bin/clavain-cli"
# Discovery still needs direct sourcing (not in dispatcher)
if [[ -f "$CLAVAIN_ROOT/hooks/lib-discovery.sh" ]]; then
  export DISCOVERY_PROJECT_DIR="."; source "$CLAVAIN_ROOT/hooks/lib-discovery.sh"
fi
```

No-op behavior is acceptable if helpers are missing; continue with manual phase notes in that case.

## 2. Resume or discover work

If `$ARGUMENTS` is a bead id, validate with:

```bash
bd show "$ARGUMENTS"
```

- If valid, set `CLAVAIN_BEAD_ID="$ARGUMENTS"` and continue from inferred phase.
- If invalid/missing:
  - Find an active sprint via `"$CLAVAIN_CLI" sprint-find-active` when available.
  - Otherwise run discovery (`discovery_scan_beads`) and prompt selection.
  - Otherwise fall back to `/clavain:brainstorm` for a fresh start.

If a bead is available from discovery, set it in `CLAVAIN_BEAD_ID`.

## 3. Execute sprint phases in order

Run these in sequence, enforcing gates before each transition where possible:

1. `brainstorm` → `/clavain:brainstorm`
2. `strategy` → `/clavain:strategy`
3. `write-plan` → `/clavain:write-plan`
4. `plan review` → `/interflux:flux-drive <plan>`
5. `work` → `/clavain:work <plan>`
6. `test & verify`
7. `quality-gates` → `/clavain:quality-gates`
8. `resolve` → `/clavain:resolve`
9. `ship` → `/clavain:land` (or `/clavain:landing-a-change` equivalent)

Use your existing flow from `/clavain:sprint`, but do it explicitly and keep Codex execution as the default implementation mode.

## 4. Phase checkpoints (Codex-first)

After each completed phase (when a bead is active), attempt:

```bash
"$CLAVAIN_CLI" advance-phase "$CLAVAIN_BEAD_ID" "<phase>" "<reason>" "<artifact>"
"$CLAVAIN_CLI" record-phase "$CLAVAIN_BEAD_ID" "<phase>"
"$CLAVAIN_CLI" set-artifact "$CLAVAIN_BEAD_ID" "<artifact_type>" "<artifact_path>"
```

If `CLAVAIN_BEAD_ID` is unavailable or helper functions are missing, continue without blocking.

`<phase>` uses:

- `brainstorm`
- `brainstorm-reviewed`
- `strategized`
- `planned`
- `plan-reviewed`
- `executing`
- `shipping`
- `done`

## 5. Gate behavior in Codex

Before executing work:

```bash
"$CLAVAIN_CLI" enforce-gate "$CLAVAIN_BEAD_ID" "executing" "<plan_path>"
```

Before shipping:

```bash
"$CLAVAIN_CLI" enforce-gate "$CLAVAIN_BEAD_ID" "shipping" ""
```

If gate checks fail, stop, fix the blockers, then rerun the blocked command.

## 6. Completion

When all phases pass, close the sprint/bead (`bd close "$CLAVAIN_BEAD_ID"`) and leave handoff notes.
