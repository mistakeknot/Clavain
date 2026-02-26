# Task 4: Phase Transitions + Gate Enforcement — Implementation Report

**Date:** 2026-02-25
**Bead:** iv-5b6wu (F3)
**Files Modified:** `phase.go`, `types.go`
**Files Created:** `phase_test.go`

## Summary

Replaced all 10 stub implementations in `phase.go` with full working functions that mirror the Bash `lib-sprint.sh` (lines 643-956), `lib-gates.sh`, `lib-phase.sh`, and `lib-discovery.sh` behavior. Added `RunAction` type to `types.go`. Created `phase_test.go` with 14 table-driven tests covering all pure functions and bead inference.

## Functions Implemented

### Pure Functions (fully testable, no subprocess)

1. **`nextStep(phase string) string`** — Static fallback phase-to-step mapping. 9 canonical phases + default ("brainstorm"). Matches the Bash `sprint_next_step()` fallback case statement exactly.

2. **`commandToStep(cmd string) string`** — Maps kernel action command names (e.g., `/clavain:strategy`) to step names (e.g., `"strategy"`). Handles the `/reflect` and `/clavain:reflect` dual mapping.

3. **`phaseToAction(phase string) string`** — Maps phases to action names for `infer-action`. Mirrors the phase-aware branch of `infer_bead_action()` in interphase's `lib-discovery.sh`.

4. **`beadPattern` (regexp)** — Compiled regex matching `**Bead:** iv-xxx`, `Bead: iv-xxx`, `**Bead**: iv-xxx` patterns in artifact files.

5. **`findBeadArtifact(beadID, dir string) string`** — Filesystem scan for markdown files referencing a bead ID, with word-boundary matching (no substring matches).

### Command Functions (subprocess-dependent)

6. **`cmdSprintNextStep(args)`** — First tries `ic --json run action list` for the bead's run (if `CLAVAIN_BEAD_ID` env set), maps highest-priority action command to step name via `commandToStep()`. Falls back to `nextStep()` static mapping. Returns step NAME (e.g., "strategy"), never the command path.

7. **`cmdSprintAdvance(args)`** — Full advance sequence:
   - Budget check via `ic run budget` (unless `CLAVAIN_SKIP_BUDGET` set)
   - `ic --json run advance` with `--priority=0`
   - On success: `invalidateCaches()`, `recordPhaseTokens()`, stderr message `"Phase: from -> to (auto-advancing)"`
   - On failure: structured pause reasons on stdout:
     - `budget_exceeded|<phase>|<spent>/<budget> billing tokens`
     - `gate_blocked|<phase>|Gate prerequisites not met`
     - `manual_pause|<phase>|auto_advance=false`
     - `stale_phase|<phase>|Phase already advanced to <actual>`

8. **`cmdSprintShouldPause(args)`** — Checks gate via `ic gate check`. Exit 0 with structured trigger on stdout if pause needed, exit 1 (error) if should continue.

9. **`cmdEnforceGate(args)`** — Gate enforcement:
   - Respects `CLAVAIN_SKIP_GATE` env var (log to stderr, return 0)
   - Fail-open: no ic run or ic unavailable = gates pass
   - Calls `ic gate check <run_id>`

10. **`cmdSetArtifact(args)`** — Resolves run_id, gets current phase via `ic run phase`, calls `ic run artifact add`. Fail-safe (no error on failure).

11. **`cmdGetArtifact(args)`** — Resolves run_id, calls `ic --json run artifact list`, filters by type arg, outputs path.

12. **`cmdRecordPhase(args)`** — Just calls `invalidateCaches()`. With ic, phase events are auto-recorded by the kernel.

13. **`cmdAdvancePhase(args)`** — Legacy gate/phase command. Delegates to `cmdEnforceGate()` + `cmdRecordPhase()`.

14. **`cmdInferAction(args)`** — Phase-aware action inference:
    - First: resolve run_id, get phase from ic, use `phaseToAction()` mapping
    - Fallback: filesystem scan of `docs/plans/`, `docs/prds/`, `docs/brainstorms/` for bead references
    - Output format: `"<action>|<artifact_path>"`

15. **`cmdInferBead(args)`** — 3-strategy bead extraction:
    1. `CLAVAIN_BEAD_ID` env var (authoritative)
    2. Grep file for `**Bead:**` pattern (warns on multiple matches)
    3. Empty string (no bead tracking)

### Helper Functions

16. **`invalidateCaches()`** — Lists all scopes for `discovery_brief` ic state key and deletes them. Mirrors `sprint_invalidate_caches()`.

17. **`recordPhaseTokens(beadID, phase)`** — Delegates to `cmdRecordPhaseTokens()` (defined in budget.go).

18. **`findArtifactForPhase(beadID, phase)`** — Looks up artifacts from ic for a given phase.

## Type Added

**`RunAction`** in `types.go` — represents a kernel phase action from `ic run action list`:
```go
type RunAction struct {
    Command  string `json:"command"`
    Phase    string `json:"phase"`
    Mode     string `json:"mode,omitempty"`
    Priority int    `json:"priority,omitempty"`
    Args     string `json:"args,omitempty"`
}
```

## Existing Functions Reused (Not Duplicated)

The linter correctly identified and removed two functions I initially wrote that already existed:

- **`resolveRunID()`** — already defined in `sprint.go` with caching via `runIDCache` map
- **`phaseToStage()`** — already defined in `budget.go` (maps phases to macro-stages: discover/design/build/ship/reflect/done)

## Tests Created (phase_test.go)

14 tests, all passing with `-race`:

| Test | Coverage |
|------|----------|
| `TestNextStep` | All 9 phases + "unknown" + "" (11 cases) |
| `TestPhaseSequence` | 9-phase chain completeness check |
| `TestCommandToStep` | 10 command-to-step mappings including `/reflect` dual form |
| `TestPhaseToStage` | 11 phase-to-stage mappings including unknown/empty |
| `TestPhaseToAction` | 10 phase-to-action mappings including unknown/empty |
| `TestBeadPattern` | 6 regex match cases (bold, plain, variant, no-match, trailing text) |
| `TestCmdInferBead_EnvVar` | CLAVAIN_BEAD_ID env var takes precedence |
| `TestCmdInferBead_FromFile` | Grep extracts bead from markdown file |
| `TestCmdInferBead_NoMatch` | Returns empty string when no bead found |
| `TestFindBeadArtifact_NotExist` | Nonexistent directory returns empty |
| `TestFindBeadArtifact_Match` | Finds file referencing the bead |
| `TestFindBeadArtifact_NoMatch` | No false positive for different bead ID |
| `TestFindBeadArtifact_WordBoundary` | `iv-abc` does NOT match `iv-abcdef` |
| `TestNextStep_AllPhasesUnique` | No canonical phase falls through to default |

## Build & Test Results

```
$ go build -o /dev/null .
# (success, no errors)

$ go test -race -v
# 56 tests total (14 new phase tests + 42 existing tests)
# All PASS
# ok  github.com/mistakeknot/clavain-cli  1.036s
```

## Behavioral Contract Verification

| Contract | Status |
|----------|--------|
| `sprint-advance` structured pause reasons (4 types) | Implemented |
| `enforce-gate` respects `CLAVAIN_SKIP_GATE` | Implemented |
| `sprint-next-step` returns step NAME not command | Implemented |
| All gate enforcement is fail-open | Implemented |
| `infer-bead` 3-strategy fallback chain | Implemented |
| `infer-action` phase-aware then filesystem fallback | Implemented |
| `record-phase` just invalidates caches | Implemented |
| `advance-phase` delegates to enforce-gate + record-phase | Implemented |

## Design Decisions

1. **No duplicate `resolveRunID`**: The sprint.go implementation (with `runIDCache` map) is the single source. phase.go references it via a comment.

2. **No duplicate `phaseToStage`**: budget.go owns this function. phase.go references it via a comment. Task 8 (children) will also use it.

3. **Bead pattern regex uses Go's `regexp` (RE2)**: The Bash version uses `grep -oP` (Perl regex) for `\K` lookahead. Go's RE2 doesn't support `\K`, so the pattern uses a capture group `([A-Za-z]+-[A-Za-z0-9]+)` instead. Semantically equivalent.

4. **`cmdSprintShouldPause` returns error for "continue"**: The Bash version returns exit code 1 for "continue" (no pause). In Go, returning `fmt.Errorf("continue")` produces exit 1 via the `main()` error handler, matching the Bash contract exactly.

5. **`findBeadArtifact` uses `filepath.Walk`**: Replaces the Bash `grep -rl` with Go's directory walker. Only scans `.md` files and uses a compiled regex with `\b` (word boundary) to prevent substring matches.
