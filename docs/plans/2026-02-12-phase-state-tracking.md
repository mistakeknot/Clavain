# Plan: F5 — Phase State Tracking

**Bead:** Clavain-z661
**Epic:** Clavain-tayp
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md (F5 section)
**Priority:** P2

## Goal

Add `bd set-state phase=<value>` calls to all workflow commands so every bead automatically tracks its lifecycle phase. No enforcement — tracking only. Entry point inferred from first action (not upfront classification).

## Phase Model

```
brainstorm → brainstorm-reviewed → strategized → planned → plan-reviewed → executing → shipping → done
```

## Command → Phase Mapping

Each workflow command sets the phase when it **completes** successfully:

| Command | Sets phase to | Reason |
|---------|--------------|--------|
| `/brainstorm` | `brainstorm` | Brainstorm doc created |
| `/review-doc` (on brainstorm) | `brainstorm-reviewed` | Brainstorm polished |
| `/strategy` | `strategized` | PRD created, beads created |
| `/write-plan` | `planned` | Implementation plan created |
| `/flux-drive` (on plan) | `plan-reviewed` | Plan reviewed before execution |
| `/work` or `/execute-plan` | `executing` | Execution started (set at start, not end) |
| `/quality-gates` | `shipping` | Quality review passed |
| `/lfg` Step 9 (ship) | `done` | Work landed on main |

**Exception:** `/work` sets phase at the **start** (executing) because it's a long-running command. All others set phase at completion.

## Architecture

### New file: `hooks/lib-phase.sh`

Shared library sourced by commands. Keeps all phase logic in one place for future F6 (gate library) to build on.

```
Functions:
  phase_set <bead_id> <phase> [--reason "..."]
    - Calls: bd set-state <bead_id> phase=<phase> --reason "..."
    - Silent on failure (phase tracking must never block workflow)
    - Logs failures to stderr for debugging

  phase_get <bead_id>
    - Calls: bd state <bead_id> phase
    - Returns current phase or empty string

  phase_infer_bead <arguments>
    - Extracts bead ID from command arguments or environment
    - Strategy: check $CLAVAIN_BEAD_ID env var first, then grep args for bead pattern
    - Returns bead ID or empty string (no bead tracking for this run)
```

### Bead ID Resolution Strategy

Commands don't currently accept bead IDs. We need a lightweight way to associate a command run with a bead. Strategy:

1. **Environment variable `CLAVAIN_BEAD_ID`** — set by `/lfg` discovery when routing to a command. Already have this context in `lfg.md` discovery flow.
2. **Artifact grep** — if no env var, grep the command's target file (brainstorm/plan/PRD) for `**Bead:** Clavain-XXXX` pattern. Same pattern `lib-discovery.sh` already uses.
3. **No bead** — if neither works, skip phase tracking silently. Not all command runs are bead-tracked.

### Changes to existing commands

Each command gets a small addition: source `lib-phase.sh` and call `phase_set` at the appropriate point. The changes are minimal — typically 3-5 lines per command.

## Tasks

### Task 1: Create `hooks/lib-phase.sh`
- [x] Implement `phase_set()` — wraps `bd set-state` with error suppression
- [x] Implement `phase_get()` — wraps `bd state` with fallback to empty string
- [x] Implement `phase_infer_bead()` — env var → artifact grep → empty
- [x] Define `CLAVAIN_PHASES` array for valid phase values (used by F6 later)
- [x] Add bash -n syntax check to CLAUDE.md quick commands
- [x] Add telemetry logging to `phase_set()` (from review feedback)
- [x] Add multi-bead detection with warning in `phase_infer_bead()` (from review feedback)
- [x] Add concurrency assumption documentation (from review feedback)

**Reference:** `hooks/lib-discovery.sh` for patterns (guard against double-sourcing, error handling style)

### Task 2: Update `/lfg` to set `CLAVAIN_BEAD_ID`
- [x] When discovery routes to a command, set `CLAVAIN_BEAD_ID=<selected_bead_id>` in environment context
- [x] Add instruction in `commands/lfg.md` to pass bead context to routed commands
- [x] Add phase tracking instructions after each /lfg step

### Task 3: Update `/brainstorm` to set `phase=brainstorm`
- [x] After Phase 3 (Capture the Design), call `phase_set` with the bead ID
- [x] Use `phase_infer_bead` to find bead ID from brainstorm doc or env var
- [x] Include `--reason "Brainstorm: <doc_path>"` in the set-state call

### Task 4: Update `/review-doc` to set `phase=brainstorm-reviewed`
- [x] After Step 4 (Fix), if the reviewed doc is in `docs/brainstorms/`, set `phase=brainstorm-reviewed`
- [x] Only set this phase for brainstorm docs (not PRDs or plans)

### Task 5: Update `/strategy` to set `phase=strategized`
- [x] After Phase 3 (Create Beads), set `phase=strategized` on the epic bead
- [x] Also set on each child feature bead created
- [x] Include `--reason "PRD: <prd_path>"` in the set-state call

### Task 6: Update `/write-plan` to set `phase=planned`
- [x] Add phase tracking instruction after plan file is written
- [x] Include `--reason "Plan: <plan_path>"` in the set-state call

### Task 7: Update `/flux-drive` to set `phase=plan-reviewed`
- [x] After review completes, if target is a plan file, set `phase=plan-reviewed`
- [x] Only set this phase for plan files (not code reviews)

### Task 8: Update `/work` to set `phase=executing`
- [x] At the START of Phase 2 (Execute), set `phase=executing`
- [x] Include `--reason "Executing: <plan_path>"` in the set-state call

### Task 8b: Update `/execute-plan` to set `phase=executing`
- [x] Before starting execution, set `phase=executing`

### Task 9: Update `/quality-gates` to set `phase=shipping`
- [x] After Phase 5 (Synthesize Results), if gate result is PASS, set `phase=shipping`
- [x] Do NOT set phase if gate result is FAIL

### Task 10: Update `/lfg` Step 9 to set `phase=done`
- [x] After successful ship, set `phase=done` on the bead
- [x] Also close the bead with `bd close`

### Task 11: Verification
- [x] Run `bash -n hooks/lib-phase.sh` to verify syntax
- [x] Manual test: run `bd set-state` and `bd state` to verify API works
- [x] Run structural tests: `cd /root/projects/Clavain && uv run pytest tests/structural/ -x` — 620 passed
- [x] Verify all commands still parse correctly (36 commands, 30 skills, 17 agents)
- [x] End-to-end integration tests: 9 tests passed (set/get, infer single/multi/empty/env, telemetry, edge cases)

## Design Decisions

1. **Phase set at completion, not start** (except `/work`) — avoids setting a phase for a command that fails halfway through.
2. **Silent failure** — `phase_set` never blocks or errors. Phase tracking is observability, not enforcement (that's F7).
3. **No migration of existing beads** — existing beads without phase labels simply have no phase. Discovery already works without phases.
4. **Artifact grep as fallback** — reuses the `**Bead:** Clavain-XXXX` pattern that `lib-discovery.sh` already searches for. Commands should include this in their output docs.

## Out of scope

- Phase enforcement (F7)
- Dual persistence to artifact headers (F6)
- Phase-aware discovery ranking (F8)
- Valid transition checks (F6)
- `--skip-gate` mechanism (F7)
