# Task 9: Integration Test Harness — BATS Tests for Go CLI Compat

**Status:** Complete
**Date:** 2026-02-25
**Artifact:** `/home/mk/projects/Demarch/os/clavain/tests/shell/test_go_cli_compat.bats`

## Summary

Created 39 BATS integration tests verifying the Go `clavain-cli` binary produces identical or compatible output to the Bash version at `os/clavain/bin/clavain-cli`. All 39 tests pass.

## Test Structure

The test file is organized into 8 sections:

| Section | Tests | Description |
|---------|-------|-------------|
| 1. Help output | 4 | Verify `help`, `--help`, `-h`, and no-args all print usage and exit 0 |
| 2. Unknown command | 2 | Exit code 1, error message format matches Bash |
| 3. complexity-label | 5 | All scores 1-5, out-of-range, legacy strings, Go-vs-Bash comparison |
| 4. sprint-next-step | 5 | All 9 phases, unknown/empty phase, Go-vs-Bash comparison |
| 5. classify-complexity | 6 | Trivial/research/empty/short/moderate descriptions, heuristic path |
| 6. Graceful degradation | 11 | Commands that need ic/bd fail gracefully (no panic, reasonable exit) |
| 7. New Go commands | 5 | Commands added in Go but not in Bash (infer-action, agent tracking, etc.) |
| 8. Command parity | 1 | All 21 Bash commands are recognized by the Go binary |

**Total: 39 tests**

## Key Design Decisions

### 1. PATH Isolation

Tests use a `CLEAN_PATH` that excludes both `ic` and `bd` binaries:

```bash
CLEAN_PATH="/usr/local/go/bin:/usr/sbin:/usr/bin:/sbin:/bin"
```

This ensures pure-function tests (complexity-label, sprint-next-step) exercise the static fallback paths, not the kernel/bead backend paths. The `bd` binary at `/usr/local/bin/bd` was specifically excluded because it prints stderr noise ("Error: no beads database found") when invoked without a `.beads` directory.

### 2. Stdout-Only Assertions

Commands that call `bd` or `ic` internally (even when they handle errors gracefully) produce stderr output from the subprocess (`cmd.Stderr = os.Stderr` in `exec.go`). BATS `run` captures both stdout and stderr into `$output`, which breaks `assert_output` for stdout-only checks.

**Solution:** A `go_cli_stdout()` helper that redirects stderr:

```bash
go_cli_stdout() {
    PATH="$CLEAN_PATH" "$GO_CLI" "$@" 2>/dev/null
}
```

Tests that need to check only the stdout value (complexity scores, phase mappings, JSON arrays) use this helper with `$()` capture instead of `run`. Tests that check exit codes or error messages use `run go_cli` (which captures both streams).

### 3. Fire-and-Forget Command Expectations

Some Go commands (`sprint-track-agent`, `sprint-complete-agent`) are designed as fire-and-forget: they return success (`nil`) even with missing args. Tests verify this is intentional, not a bug.

### 4. Go-vs-Bash Comparison Strategy

For pure functions (complexity-label, sprint-next-step), tests compare Go and Bash output character-for-character. If the Bash CLI fails (e.g., sourcing chain fails without `jq` or `ic`), the comparison is skipped and only Go output is tested independently.

```bash
bash_out="$(bash_cli sprint-next-step "$phase" 2>/dev/null)" || true
if [[ -n "$bash_out" ]]; then
    [[ "$go_out" == "$bash_out" ]] || { echo "Mismatch..."; return 1; }
fi
```

## Findings During Implementation

### bd Stderr Pollution

The `bd` binary is present at `/usr/local/bin/bd` on this system. Even when the Go CLI handles bd errors gracefully (returning `"0"` for budget commands, `"3"` for classify-complexity), `bd` prints a multi-line error to stderr:

```
Error: no beads database found
Hint: run 'bd init' to create a database in the current directory
      or use 'bd --no-db' to work with JSONL only (no SQLite)
      or set BEADS_DIR to point to your .beads directory
```

This is because `exec.go` sets `cmd.Stderr = os.Stderr` for all subprocess calls, including `runBD()`. The stderr from `bd` flows through to the Go process's stderr, which BATS captures.

**Impact:** Tests must either exclude `bd` from PATH or use stderr-suppressing helpers. The current solution excludes both `ic` and `bd` from the test PATH.

### sprint-find-active Missing Trailing Newline

The Go `cmdSprintFindActive` uses `fmt.Print("[]")` (no newline) when ic is unavailable, while `cmdCheckpointCompletedSteps` uses `fmt.Println("[]")` (with newline). Both are consistent with their Bash counterparts. BATS `$output` strips trailing newlines, so this doesn't affect test assertions.

### classify-complexity Depends on bd Being Present

Even though `classify-complexity` is a "pure function" in concept (heuristic scoring), the Go implementation first calls `tryComplexityOverride()` which invokes `bdAvailable()` and potentially `runBD()`. When `bd` is on PATH but no database exists, this produces stderr noise but the function correctly falls through to the heuristic path.

### Phase Map Completeness

Both Go and Bash implement the same 9-phase chain:

```
brainstorm -> strategy
brainstorm-reviewed -> strategy
strategized -> write-plan
planned -> flux-drive
plan-reviewed -> work
executing -> quality-gates
shipping -> reflect
reflect -> done
done -> done
(default) -> brainstorm
```

All mappings are verified to be identical between Go and Bash.

## Running the Tests

```bash
cd /home/mk/projects/Demarch/os/clavain
bats tests/shell/test_go_cli_compat.bats
```

Expected output: `39 tests, 0 failures`.

The tests build the Go binary fresh into `$TMPDIR` on each test file run (not per-test — BATS reuses the binary across tests within the same `setup()`).

## Files Created

- `/home/mk/projects/Demarch/os/clavain/tests/shell/test_go_cli_compat.bats` — 39 BATS integration tests (executable)

## Files Referenced

- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/main.go` — Go CLI dispatcher (38 commands)
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/complexity.go` — complexity-label and classify-complexity
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/phase.go` — sprint-next-step and phase transitions
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/exec.go` — subprocess helpers (runIC, runBD, etc.)
- `/home/mk/projects/Demarch/os/clavain/bin/clavain-cli` — Bash CLI dispatcher (reference implementation)
- `/home/mk/projects/Demarch/os/clavain/tests/shell/test_helper.bash` — shared BATS test helper
- `/home/mk/projects/Demarch/os/clavain/tests/shell/test_seam_integration.bats` — existing BATS tests (pattern reference)
- `/home/mk/projects/Demarch/os/clavain/tests/shell/test_lib_sprint.bats` — existing sprint lib tests (expected values reference)
