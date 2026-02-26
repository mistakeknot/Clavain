# Implementation: Tasks 5+6 (Checkpoints + Claiming)

**Date:** 2026-02-25
**Plan:** `/home/mk/projects/Demarch/docs/plans/2026-02-25-clavain-cli-go-migration.md`
**Files modified:**
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/checkpoint.go`
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/claim.go`
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/checkpoint_test.go` (new)
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/claim_test.go` (new)

---

## Summary

Replaced stub implementations in `checkpoint.go` and `claim.go` with full working implementations matching the behavior of the Bash functions in `lib-sprint.sh` (lines 1121-1361). Created comprehensive test files for both modules.

Build: `go build -o /dev/null .` -- PASS
Tests: `go test -race -v -run "TestCheckpoint|TestClaim"` -- 13/13 PASS

---

## Task 5: Checkpoints (`checkpoint.go`)

### Functions Implemented

1. **`addCompletedStep(ckpt Checkpoint, step string) Checkpoint`** -- Deduplicated append to CompletedSteps, with `sort.Strings` for deterministic ordering (matching bash `jq 'unique'`).

2. **`addKeyDecision(ckpt Checkpoint, decision string) Checkpoint`** -- Deduplicated append, sorted, keeps last 5 (matching bash `.[-5:]`).

3. **`currentRunID() (string, error)`** -- New helper that calls `ic run current --project=<cwd>` as fallback when no bead_id is provided. Matches bash `intercore_run_current "$(pwd)"`.

4. **`readCheckpoint(runID string) Checkpoint`** -- Reads checkpoint from `ic state get checkpoint <run_id>` and returns empty Checkpoint on error.

5. **`cmdCheckpointWrite(args []string) error`** -- Args: `bead_id phase step [plan_path] [key_decision]`. Resolves run ID via `resolveRunID()` (defined in sprint.go with caching), reads existing checkpoint, merges fields, writes via `writeICState()` (defined in budget.go). Silently succeeds when ic unavailable (matches bash `|| return 0`).

6. **`cmdCheckpointRead(args []string) error`** -- Args: `[bead_id]`. Tries bead_id resolution, falls back to `currentRunID()`. Output: JSON or `"{}"`.

7. **`cmdCheckpointValidate(args []string) error`** -- Compares `git_sha` from checkpoint with current HEAD. Warns on stderr with short SHAs (8 chars). Always exits 0 (matches bash behavior).

8. **`cmdCheckpointClear(args []string) error`** -- Removes legacy `.clavain/checkpoint.json` file. Honors `CLAVAIN_CHECKPOINT_FILE` env var. Ignores errors.

9. **`cmdCheckpointCompletedSteps(args []string) error`** -- Outputs JSON array of completed step names, or `"[]"`.

10. **`cmdCheckpointStepDone(args []string) error`** -- Exit 0 if step found in completed_steps, `os.Exit(1)` if not.

### Design Decisions

- **No duplicate `resolveRunID`**: sprint.go already defines this with caching. checkpoint.go uses it directly.
- **`writeICState` reuse**: budget.go already defines a helper for piping JSON to `ic state set`. checkpoint.go uses it instead of manual `exec.Command` construction.
- **Empty checkpoint detection**: Uses `ckpt.Bead == "" && ckpt.Phase == ""` to detect an empty/uninitialized checkpoint, rather than comparing JSON strings.

### Tests (checkpoint_test.go) -- 7 tests

| Test | What it verifies |
|------|-----------------|
| `TestCheckpointMarshalRoundTrip` | JSON marshal/unmarshal preserves all fields |
| `TestCheckpointAddStep_Dedup` | Duplicate steps are not added |
| `TestCheckpointAddStep_SortsResults` | Steps are sorted after addition |
| `TestCheckpointAddStep_Empty` | Adding to empty slice works |
| `TestCheckpointAddKeyDecision_Dedup` | Duplicate decisions are not added |
| `TestCheckpointAddKeyDecision_MaxFive` | Decisions capped at 5 |
| `TestCheckpointEmptyJSON` | Empty checkpoint serializes with omitempty |

---

## Task 6: Sprint + Bead Claiming (`claim.go`)

### Functions Implemented

1. **`isClaimStale(ageSeconds int64) bool`** -- Returns `true` if `ageSeconds > 7200`. Matches bash `if [[ $age_seconds -lt 7200 ]]` (note: bash uses `-lt`, so exactly 7200 is NOT stale; Go uses `>` for the same semantics).

2. **`cmdSprintClaim(args []string) error`** -- Args: `bead_id session_id`. Full flow:
   - Resolves run ID
   - Acquires ic lock (`ic lock acquire sprint-claim <bead_id> --timeout=500ms`) with directory-based fallback
   - Lists agents, filters active session agents
   - If same session: return 0 (idempotent)
   - If other session < 60 min: print conflict message on stderr, exit 1
   - If stale session > 60 min: mark old agent as `failed`, proceed
   - Registers new session agent via `ic run agent add`
   - Also calls `cmdBeadClaim` for cross-session visibility

3. **`cmdSprintRelease(args []string) error`** -- Args: `bead_id`. Releases bead claim first, then marks all active session agents as `completed`.

4. **`cmdBeadClaim(args []string) error`** -- Args: `bead_id [session_id]`. Advisory lock via `bd set-state`. Checks existing claim staleness (2h threshold). Falls back to `CLAUDE_SESSION_ID` env var for session ID.

5. **`cmdBeadRelease(args []string) error`** -- Args: `bead_id`. Clears `claimed_by` and `claimed_at` via `bd set-state`.

6. **`fallbackLock(name, scope string) error`** -- Directory-based lock fallback matching bash `intercore_lock()` fallback path (mkdir + owner.json).

7. **`fallbackUnlock(name, scope string)`** -- Removes owner.json + directory.

### Behavioral Contract (matching bash)

- Sprint claim uses 60-minute staleness for session conflicts (bash `$age_minutes -lt 60`)
- Bead claim uses 7200-second (2h) staleness threshold (bash `$age_seconds -lt 7200`)
- Sprint claim acquires `ic lock` with 500ms timeout, with `mkdir`-based fallback
- Sprint claim is idempotent for the same session ID
- Sprint claim auto-expires stale sessions and force-claims
- Bead claim checks `bd state <bead_id> claimed_by` and rejects fresh claims from other sessions
- Bead claim reads `(no claimed_by state set)` sentinel from bd and treats it as empty

### Tests (claim_test.go) -- 6 tests

| Test | What it verifies |
|------|-----------------|
| `TestClaimStaleness_Fresh` | 30min (1800s) -- NOT stale |
| `TestClaimStaleness_Old` | 3h (10800s) -- stale |
| `TestClaimStaleness_Boundary` | Exactly 7200s -- NOT stale (> not >=) |
| `TestClaimStaleness_JustOver` | 7201s -- stale |
| `TestClaimStaleness_Zero` | 0s -- NOT stale |
| `TestClaimStaleness_Negative` | -100s (clock skew) -- NOT stale |

---

## Key Differences from Bash

1. **No jq dependency**: All JSON processing is native Go `encoding/json`.
2. **Type safety**: `Checkpoint` struct with typed fields instead of ad-hoc jq transformations.
3. **Caching**: `resolveRunID` in sprint.go caches bead-to-run mappings in `runIDCache` map.
4. **`writeICState` helper**: Shared with budget.go for piping JSON to `ic state set`.
5. **Fallback lock**: Go implementation matches bash `intercore_lock()` fallback: `os.Mkdir` with retry loop + `owner.json`.

## Pre-existing Test Failure

The test suite has one pre-existing failure in `TestClassifyComplexityEdgeCases/trivial_at_20_words` (in complexity_test.go) which is unrelated to this change. All checkpoint and claim tests pass.
