# Plan: M2 Phase Gates — F7 Tiered Enforcement + F8 Discovery Integration

**Bead:** Clavain-tayp
**Phase:** executing (as of 2026-02-13T22:47:08Z)
**Date:** 2026-02-13
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md
**Features:** Clavain-9tiv (F7), Clavain-y8ub (F8)

## Summary

Add tiered gate enforcement and phase-aware discovery scoring to the existing phase tracking infrastructure. F7 makes `check_phase_gate()` priority-aware (hard block for P0/P1, soft warn for P2/P3, skip for P4) and adds `--skip-gate` override with audit trail. F8 makes `discovery_scan_beads()` rank beads by phase advancement (executing > planned > brainstorm) and detects stale flux-drive reviews.

All code lives in interphase (`/root/projects/interphase/`). Clavain gets no code changes — only updated command docs that reference the new enforcement behavior.

## Architecture

```
check_phase_gate()          # existing — returns 0/1
  └── enforce_gate()        # NEW — wraps check_phase_gate with tier logic
        ├── get_enforcement_tier(priority) → hard|soft|none
        ├── check_review_staleness(bead_id, artifact) → stale|fresh
        └── log_enforcement_decision(bead_id, tier, decision, reason)

discovery_scan_beads()      # existing — priority-only ranking
  └── score_bead()          # NEW — multi-factor scoring
        ├── priority_score(priority) → 0-40
        ├── phase_score(phase) → 0-30
        ├── recency_score(updated_at) → 0-20
        └── staleness_penalty(stale) → -10
```

## Tasks

### Task 1: Enforcement tier function in lib-gates.sh

**File:** `/root/projects/interphase/hooks/lib-gates.sh`
**What:** Add `enforce_gate()` — wraps `check_phase_gate()` with priority-based tiering.

```bash
# Public API:
# enforce_gate <bead_id> <target_phase> [artifact_path] [--skip-gate --reason "..."]
#
# Returns:
#   0 = proceed (gate passed, or soft warn, or skipped, or P4 no-gate)
#   1 = hard block (P0/P1, gate failed, no --skip-gate)
#
# Side effects:
#   - Prints warning to stderr for soft gates
#   - Logs enforcement decision to telemetry
#   - Records --skip-gate in bead notes via bd update --notes
```

Implementation:
1. Add `get_enforcement_tier()` — reads bead priority via `bd show <id> --json | jq '.priority'`, returns `hard` (P0/P1), `soft` (P2/P3), or `none` (P4).
2. Add `enforce_gate()`:
   - Calls `check_phase_gate()` to validate transition
   - If valid → proceed (return 0)
   - If invalid + tier=hard + no --skip-gate → return 1 with error message
   - If invalid + tier=hard + --skip-gate → record skip in bead notes, return 0
   - If invalid + tier=soft → warn to stderr, record in bead notes, return 0
   - If tier=none → return 0 (no check)
3. Add `_gate_log_enforcement()` telemetry event with: bead, priority, tier, decision (pass/block/skip/warn), reason.

**Acceptance:** `enforce_gate "Clavain-xxx" "executing"` blocks for P0/P1 if phase isn't `plan-reviewed`, warns for P2/P3, skips for P4.

### Task 2: Stale review detection in lib-gates.sh

**File:** `/root/projects/interphase/hooks/lib-gates.sh`
**What:** Add `check_review_staleness()` — checks if flux-drive review is still current.

Implementation:
1. Add `check_review_staleness()`:
   - Args: `$1` = artifact path (the plan/brainstorm being reviewed)
   - Derives review dir: `docs/research/flux-drive/{stem}/findings.json`
   - Reads `"reviewed"` date from findings.json via jq
   - Checks git log for commits touching the artifact after the review date
   - Returns: `stale` if commits exist after review, `fresh` if not, `none` if no review found
2. Integrate into `enforce_gate()`: stale review = soft warning (not hard block) even for P0/P1 — user can re-run `/clavain:flux-drive`.

**Acceptance:** If `docs/plans/foo.md` was reviewed on 2026-02-12 and committed to on 2026-02-13, `check_review_staleness` returns `stale`.

### Task 3: Multi-factor scoring in lib-discovery.sh

**File:** `/root/projects/interphase/hooks/lib-discovery.sh`
**What:** Replace priority-only sort with `score_bead()` multi-factor scoring.

Implementation:
1. Add `score_bead()`:
   - `priority_score`: P0=40, P1=32, P2=24, P3=16, P4=8
   - `phase_score`: executing/shipping=30, plan-reviewed=24, planned=18, strategized=12, brainstorm-reviewed=8, brainstorm=4, none=0
   - `recency_score`: updated in last 24h=20, 24-48h=15, 48h-7d=10, >7d=5
   - `staleness_penalty`: stale=−10, not stale=0
   - Total = priority_score + phase_score + recency_score + staleness_penalty
2. Read phase for each bead: call `bd state <id> phase` (already have `phase_get` from lib-phase.sh)
3. Replace `jq 'sort_by(.priority, .updated_at, .id)'` with shell-side scoring loop that appends `score` field
4. Sort by score DESC, then id ASC (deterministic tiebreaker)

**Acceptance:** An in-progress P2 bead at `executing` phase scores higher than an open P2 bead at `brainstorm` phase.

### Task 4: Phase display in discovery results

**File:** `/root/projects/interphase/hooks/lib-discovery.sh`
**What:** Add `phase` field to discovery JSON output and update action verb logic.

Implementation:
1. Read phase via `phase_get "$id"` in the scan loop (after `infer_bead_action`)
2. Add `"phase"` key to the JSON result objects
3. Update `infer_bead_action()`: if phase is set, use it to determine action more precisely:
   - phase=plan-reviewed + has plan → `execute` (not `continue`)
   - phase=brainstorm → `strategize` (not `brainstorm`)
4. Add `/lfg <bead-id>` direct routing: when invoked as `/lfg Clavain-xxx`, look up phase and route directly

**Acceptance:** Discovery JSON includes `"phase": "plan-reviewed"` for beads with phase state. `/lfg Clavain-xxx` routes to the right command based on phase.

### Task 5: Update Clavain command docs for enforcement

**File:** `/root/projects/Clavain/commands/lfg.md` + other workflow commands
**What:** Add enforcement gate calls before `advance_phase()` in command docs.

Implementation:
1. In `lfg.md`: before routing to a command, call `enforce_gate` with the target phase
2. In `quality-gates.md`: before setting `shipping` phase, check gate
3. In `work.md` / `execute-plan.md`: before setting `executing`, check gate
4. Pattern for each command:
   ```bash
   GATES_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
   if ! enforce_gate "$CLAVAIN_BEAD_ID" "<target_phase>" "<artifact_path>"; then
       echo "Gate blocked: run /clavain:flux-drive first or use --skip-gate --reason '...'"
       # Stop and tell user
   fi
   ```
5. Commands that already call `advance_phase` gain a preceding `enforce_gate` check

**Acceptance:** `/clavain:work` on a P1 bead that hasn't been plan-reviewed prints a hard block message.

### Task 6: Tests

**File:** `/root/projects/interphase/tests/shell/gates.bats` + `discovery.bats`
**What:** Add tests for enforcement tiers, stale review detection, and multi-factor scoring.

Tests to add:
- **gates.bats** (~15 tests):
  - `enforce_gate`: hard block on P0, P1
  - `enforce_gate`: soft warn on P2, P3
  - `enforce_gate`: no gate on P4
  - `enforce_gate`: --skip-gate overrides hard block
  - `enforce_gate`: --skip-gate records in notes
  - `enforce_gate`: valid transition passes regardless of tier
  - `get_enforcement_tier`: returns correct tier for each priority
  - `check_review_staleness`: fresh review
  - `check_review_staleness`: stale review (artifact newer than review)
  - `check_review_staleness`: no review found
  - `check_review_staleness`: no findings.json
  - `_gate_log_enforcement`: valid JSONL telemetry event
  - `enforce_gate`: stale review = soft warning even for P0
  - `enforce_gate`: fail-safe on missing bead
  - `enforce_gate`: fail-safe on bd unavailable

- **discovery.bats** (~8 tests):
  - `score_bead`: priority scoring
  - `score_bead`: phase scoring (executing > brainstorm)
  - `score_bead`: recency scoring
  - `score_bead`: staleness penalty
  - `discovery_scan_beads`: results sorted by score DESC
  - `discovery_scan_beads`: includes phase field in output
  - `infer_bead_action`: phase-aware action inference
  - Direct bead-id routing test

**Acceptance:** All new tests pass. Existing 80 interphase tests still pass. Clavain 76 shell tests still pass.

### Task 7: Publish

Bump interphase 0.2.0 → 0.3.0, Clavain 0.5.9 → 0.5.10. Update marketplace.

## Execution Order

Tasks 1-2 (enforcement) and Tasks 3-4 (discovery) are independent — can be parallelized.
Task 5 depends on Task 1 (needs enforce_gate API defined).
Task 6 should run after Tasks 1-4 (tests verify all new code).
Task 7 after all tests pass.

```
[Task 1: enforce_gate] ──┐
[Task 2: stale review]  ─┤── [Task 5: command docs] ── [Task 6: tests] ── [Task 7: publish]
[Task 3: scoring]  ──────┤
[Task 4: phase display] ─┘
```

## Risk Mitigation

- **Performance**: `bd state <id> phase` adds one `bd` call per bead in discovery. For 40 beads, this is ~2s. Acceptable for on-demand discovery but may need caching in F4 brief scan path.
- **Backwards compatibility**: `enforce_gate` is a new function — existing `check_phase_gate` unchanged. No breakage.
- **bd unavailable**: All new functions inherit the fail-safe pattern (return 0 on error). Enforcement degrades to no-gate.
- **--skip-gate abuse**: `bd update --notes` appends to notes field for audit trail. Telemetry logs all skips.
