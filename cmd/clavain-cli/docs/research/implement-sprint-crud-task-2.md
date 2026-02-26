# Task 2: Sprint CRUD Commands Implementation

## Summary

Replaced all 8 stub implementations in `sprint.go` with full working code that matches the Bash `lib-sprint.sh` behavioral contracts. Created `sprint_test.go` with table-driven tests. Also fixed duplicate symbol conflicts with `checkpoint.go` and `phase.go` from prior tasks.

## Files Modified

- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/sprint.go` -- full implementations of all 8 functions
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/sprint_test.go` -- new, 5 test functions
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/checkpoint.go` -- removed duplicate `resolveRunID`, added `os/exec` import
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/phase.go` -- removed duplicate `resolveRunID` and `phaseToStage`

## Functions Implemented

### 1. `resolveRunID(beadID string) (string, error)`
- Calls `bd state <beadID> ic_run_id`
- Caches results in package-level `runIDCache` map
- Handles empty, "null", and "(no " prefix responses
- Returns error for empty bead ID input

### 2. `defaultBudget(complexity int) int64`
- Switch on complexity: 1->50000, 2->100000, 3->250000, 4->500000, default->1000000
- Matches `_sprint_default_budget` in lib-sprint.sh exactly
- Default case covers 5 and any out-of-range values (matching Bash `5|*` pattern)

### 3. `cmdSprintCreate(args []string) error`
- Args: `<title> [complexity] [lane]`
- Creates bd epic via `bd create --title=<title> --type=epic --priority=2`
- Parses bead ID from output using regex `[A-Za-z]+-[a-z0-9]+` (matches Bash awk pattern)
- Creates ic run with phases, scope_id, token budget, and default actions
- Verifies run starts at "brainstorm" phase
- Stores `ic_run_id` and `token_budget` on bead
- Loads agency specs from `CLAVAIN_CONFIG_DIR/agency` if available
- Outputs bead ID (NOT run ID) as plain text on stdout
- Full rollback on failure: cancels ic run, sets bead status to cancelled

### 4. `cmdSprintFindActive(args []string) error`
- Calls `ic --json run list --active`
- Enriches with bd titles (falls back to "Untitled")
- Outputs JSON array `[{id, title, phase, run_id}]`
- Outputs `[]` (not error) when ic unavailable
- Caps at 100 results (matching Bash loop guard)

### 5. `cmdSprintReadState(args []string) error`
- Assembles SprintState from 5 ic queries:
  1. `ic --json run status <runID>` -- phase, complexity, auto_advance, token_budget
  2. `ic --json run artifact list <runID>` -- artifacts map (type->path)
  3. `ic --json run events <runID>` -- history map (phase_at->timestamp)
  4. `ic --json run agent list <runID>` -- active_session (first active agent name)
  5. `ic --json run tokens <runID>` -- tokens_spent (input + output)
- Outputs `{}` for unknown/unresolvable bead IDs
- All sub-queries are fail-safe (missing data yields empty defaults)

### 6. `cmdSprintTrackAgent(args []string) error`
- Args: `<bead_id> <agent_name> [agent_type] [dispatch_id]`
- Calls `ic run agent add <runID> --type=<type> [--name=<name>] [--dispatch-id=<id>]`
- Defaults agent_type to "claude"
- Fail-safe: returns nil on any error

### 7. `cmdSprintCompleteAgent(args []string) error`
- Args: `<agent_id> [status]`
- Calls `ic run agent update <agentID> --status=<status>`
- Defaults status to "completed"
- Fail-safe: returns nil on any error

### 8. `cmdSprintInvalidateCaches(args []string) error`
- Lists all scopes via `ic state list discovery_brief`
- Deletes each via `ic state delete discovery_brief <scope>`
- Matches Bash `intercore_state_delete_all "discovery_brief"` behavior
- Fail-safe: returns nil on any error

## Behavioral Contracts Verified

| Contract | Implementation |
|----------|---------------|
| sprint-create outputs bead ID (not run ID) | `fmt.Print(sprintID)` on line 213 |
| sprint-find-active outputs `[]` when ic unavailable | Early return on line 221-223 |
| sprint-read-state outputs `{}` for unknown beads | Early return on lines 292-294, 299-302, 307-309 |
| All functions fail-safe except sprint-claim | All return nil on error (no non-zero exit codes) |

## Tests

5 test functions in `sprint_test.go`:

1. **TestResolveRunID_Empty** -- verifies error on empty bead ID
2. **TestDefaultBudget** -- table-driven, 8 cases covering tiers 1-5 plus out-of-range (0, 99, -1)
3. **TestRunIDCache** -- verifies cache hit returns stored value without calling bd
4. **TestBeadIDPattern** -- regex pattern matching against realistic bd output strings
5. **TestMustGetwd** -- sanity check that working directory resolution works

## Cross-File Conflict Resolution

Prior tasks (checkpoint, phase, budget) each independently defined `resolveRunID` and/or `phaseToStage`. This task consolidated:

- **`resolveRunID`**: canonical definition in `sprint.go` (with caching). Removed from `checkpoint.go` (line 41) and `phase.go` (line 65). Both now have a comment pointing to sprint.go.
- **`phaseToStage`**: canonical definition in `budget.go` (line 42). Removed duplicate from `phase.go` (line 595). Comment added.
- **`execCommand`**: was undefined in `checkpoint.go` -- was already fixed to `writeICState` by a prior modification, but the `os/exec` import was needed for other uses. Added import.

## Build and Test Results

```
$ go build -o /dev/null .
# Success (no output)

$ go vet ./...
# Success (no output)

$ go test -race -v -run "TestResolveRunID|TestDefaultBudget|TestRunIDCache|TestBeadIDPattern|TestMustGetwd"
=== RUN   TestResolveRunID_Empty
--- PASS: TestResolveRunID_Empty (0.00s)
=== RUN   TestDefaultBudget
--- PASS: TestDefaultBudget (0.00s)
=== RUN   TestRunIDCache
--- PASS: TestRunIDCache (0.00s)
=== RUN   TestBeadIDPattern
--- PASS: TestBeadIDPattern (0.00s)
=== RUN   TestMustGetwd
--- PASS: TestMustGetwd (0.00s)
PASS
```

Note: One pre-existing test failure exists in `complexity_test.go` (`TestClassifyComplexityEdgeCases/trivial_at_20_words`) -- the test expects complexity 2 for a 20-word string with trivial keyword, but the implementation uses `< 20` (strict less than), so 20 words still triggers the trivial path returning 1. This is not related to sprint CRUD changes.
