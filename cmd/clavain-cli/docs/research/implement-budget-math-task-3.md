# Task 3: Budget Math Engine — Implementation Analysis

**Date:** 2026-02-25
**Bead:** iv-udul3 (F2)
**Status:** Implemented and tested

## Summary

Replaced stub implementations in `budget.go` with full working budget math engine. Created `budget_test.go` with table-driven tests. All 4 pure functions and 7 command functions implemented. Build passes, all 73 tests pass with `-race`.

## Files Modified

- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/budget.go` — 530 lines (was 12-line stub)
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/budget_test.go` — 189 lines (new)
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/exec.go` — added `execCommand` var and `runCommandExec` helper
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/checkpoint.go` — removed duplicate `resolveRunID` (now uses sprint.go's cached version)

## Pure Functions Implemented

All use `int64` arithmetic exclusively. No `float64`, no truncation.

### 1. `phaseCostEstimate(phase string) int64`

Switch-based mapping matching `_sprint_phase_cost_estimate()` in lib-sprint.sh:

| Phase | Tokens |
|-------|--------|
| brainstorm | 30,000 |
| brainstorm-reviewed | 15,000 |
| strategized | 25,000 |
| planned | 35,000 |
| plan-reviewed | 50,000 |
| executing | 150,000 |
| shipping | 100,000 |
| reflect | 10,000 |
| done | 5,000 |
| default | 30,000 |

Total sprint estimate: 420,000 tokens (verified by test).

### 2. `phaseToStage(phase string) string`

Switch-based mapping matching `_sprint_phase_to_stage()` in lib-sprint.sh:

- brainstorm -> discover
- brainstorm-reviewed, strategized, planned, plan-reviewed -> design
- executing -> build
- shipping -> ship
- reflect -> reflect
- done -> done
- default -> unknown

### 3. `budgetRemaining(budget, spent int64) int64`

Simple subtraction with clamp to >= 0. Handles overspend (spent > budget) by returning 0 instead of negative.

### 4. `stageAllocation(totalBudget int64, sharePct int, minTokens int64) int64`

Computes `max(totalBudget * sharePct / 100, minTokens)`. The min_tokens floor ensures every stage gets at least a minimum allocation even with tiny budgets.

## Command Functions Implemented

### 5. `cmdBudgetRemaining(args)` — `sprint-budget-remaining`

Reads run budget via `ic --json run budget <runID>`. Outputs remaining tokens as integer. Returns "0" for unknown beads (not an error — matches bash behavior).

### 6. `cmdBudgetTotal(args)` — `budget-total`

Reads `token_budget` from `ic --json run status <runID>`. Outputs integer. "0" for unknown.

### 7. `cmdBudgetStage(args)` — `sprint-budget-stage`

Per-stage allocation with spec support. Without agency spec, returns total budget (no breakdown). With spec, computes allocation via `stageAllocation()` and applies the overallocation cap: if all stages' allocations exceed total budget, scales down proportionally.

The overallocation cap formula: `allocated = allocated * totalBudget / uncappedSum`

### 8. `cmdBudgetStageRemaining(args)` — `sprint-budget-stage-remaining`

`allocated - spent`, clamped to >= 0. Uses `getBudgetStage()` and `getStageTokensSpent()` internal helpers.

### 9. `cmdBudgetStageCheck(args)` — `sprint-budget-stage-check`

Exits 0 if within budget. Exits 1 with `budget_exceeded|<stage>|stage budget depleted` on stderr if exceeded. Matches bash `sprint_budget_stage_check()` exactly.

### 10. `cmdStageTokensSpent(args)` — `sprint-stage-tokens-spent`

Sums phase tokens for all phases belonging to a stage. Reads phase_tokens from `ic state get phase_tokens <runID>`, iterates keys, maps each phase to its stage via `phaseToStage()`, sums `input_tokens + output_tokens` for matching phases.

### 11. `cmdRecordPhaseTokens(args)` — `sprint-record-phase-tokens`

Records phase token usage to ic state. Two-tier data source:
1. **Actual data** from interstat via `sqlite3` CLI query (session-scoped billing tokens)
2. **Estimate** from `phaseCostEstimate()` when interstat unavailable

Splits tokens 60/40 (input/output) matching bash behavior. Merges with existing phase_tokens JSON via `ic state set phase_tokens <runID>`.

## Supporting Infrastructure Added

### `resolveRunID` Deduplication

Found `resolveRunID` was defined in 3 files (sprint.go, checkpoint.go, budget.go). The sprint.go version is canonical (with `runIDCache` for process-lifetime caching). Removed duplicates from checkpoint.go and budget.go.

### `execCommand` / `runCommandExec` in exec.go

Added `execCommand` as a package-level `var` (pointing to `exec.Command`) for testability, and `runCommandExec` as a generic command runner. Used by:
- `budget.go:writeICState()` — writes JSON to ic state set via stdin pipe
- `budget.go:cmdRecordPhaseTokens()` — runs sqlite3 queries
- `checkpoint.go:cmdCheckpointWrite()` — already used this pattern

### Agency Spec Integration

Minimal spec support for budget commands:
- `findSpecPath()` — resolves agency-spec.yaml location (project override or CLAVAIN_DIR default)
- `specAvailable()` — checks if spec file exists
- `specGetBudget(stage)` — delegates to `ic spec get-budget <stage>` (ic handles YAML parsing, avoiding a Go YAML dependency)
- `sumAllStageAllocations(totalBudget)` — iterates all 5 stages for the overallocation cap

## Test Coverage

### Table-Driven Tests in budget_test.go (10 tests)

| Test | Cases | Key coverage |
|------|-------|-------------|
| `TestPhaseCostEstimate` | 13 | All 9 phases + default + empty + unknown + case-sensitivity |
| `TestPhaseToStage_BudgetCases` | 12 | All 9 phases + default + empty + case-sensitivity |
| `TestBudgetRemaining` | 9 | Normal, zero, overspent clamp, edge cases, max int64 |
| `TestStageAllocation` | 10 | Normal, min floor, zero budget, 100%/0% share, tiny budget |
| `TestStageAllocationInt64` | 1 | 10 billion tokens to verify int64 (no int32 truncation) |
| `TestBudgetRemainingClampNeverNegative` | 1 | Extreme overspend (0 budget, MaxInt64 spent) |
| `TestAllStages` | 5 | Canonical ordering: discover, design, build, ship, reflect |
| `TestPhaseToStageCoversAllPhases` | 9 | Every known phase maps to a non-"unknown" stage |
| `TestPhaseCostEstimateAllPositive` | 11 | Every phase (including default) has positive cost |
| `TestPhaseCostEstimateSumsToReasonableTotal` | 1 | Full sprint = 420,000 tokens |

### Test naming note

Renamed `TestPhaseToStage` to `TestPhaseToStage_BudgetCases` because `phase_test.go` already had `TestPhaseToStage` testing the same function. Both test suites cover the function from different angles (budget context vs phase transition context).

## Behavioral Contract Verification

1. **"0" for unknown beads** — all `cmd*` functions return "0" (not error) when bead lookup fails
2. **Exit 1 for exceeded** — `cmdBudgetStageCheck` calls `os.Exit(1)` with stderr message matching `budget_exceeded|<stage>|stage budget depleted` format
3. **int64 everywhere** — verified by `TestStageAllocationInt64` (10B tokens) and `TestBudgetRemainingClampNeverNegative` (MaxInt64)
4. **60/40 split** — `cmdRecordPhaseTokens` splits `inTokens = total * 60 / 100`, `outTokens = total - inTokens` (integer math, no rounding loss)

## Deviations from Plan

1. **Removed `readSprintState` helper** — was in my first draft but unused by any command function (the cmd functions call `resolveRunID` + `runICJSON` directly)
2. **Spec loading via `ic spec get-budget`** — plan didn't specify the mechanism. Chose to delegate YAML parsing to ic binary rather than adding a Go YAML dependency, keeping the zero-dependency constraint
3. **`runCommand`/`writeICState` helpers** — not in the plan but necessary for `cmdRecordPhaseTokens` (sqlite3 query) and state writing (stdin pipe to ic)

## Build Verification

```
$ go build -o /dev/null .   # OK
$ go test -race -v ./...    # 73 tests PASS (1.042s)
```
