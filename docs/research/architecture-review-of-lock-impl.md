# Architecture Review — intercore Lock Module Implementation

**Date:** 2026-02-18
**Scope:** 8 files across intercore (Go CLI) and clavain (bash hooks)
**Reviewer:** fd-architecture (Flux-drive Architecture & Design Reviewer)
**Output contract file:** `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/fd-architecture.md`

---

## Overview

The lock module adds process-level mutual exclusion using POSIX `mkdir` atomicity to the intercore CLI. It is deliberately filesystem-only (no SQLite), which is the correct architectural decision: it allows locking to work even when the DB is broken or unavailable. The change covers a Go internal package (`internal/lock/`), a CLI command file (`cmd/ic/lock.go`), a bash wrapper layer update (`lib-intercore.sh` v0.4.0), hook migration in `hooks/lib-sprint.sh` (5 inline mkdir patterns migrated), and a synced copy in clavain's `hooks/lib-intercore.sh`.

---

## Boundaries and Coupling Analysis

### Module placement: correct

`internal/lock/` sits at the same level as `internal/db/`, `internal/sentinel/`, `internal/dispatch/`, `internal/phase/`, and `internal/runtrack/`. This is the established pattern. The lock package has zero imports from other internal packages and zero imports from cmd/. The dependency graph is a DAG: `cmd/ic/lock.go` → `internal/lock/` and nothing else. This is correct layering.

### CLI entry point integration: clean

`cmd/ic/main.go` routes `"lock"` to `cmdLock(ctx, subArgs)` in the same switch statement as `"dispatch"`, `"run"`, and `"compat"`. The pattern is identical to other subcommands. No shared state is introduced between `cmdLock` and other command files.

### Bash wrapper coupling: one genuine concern

`intercore_lock_available` and `intercore_available` both write to the shared global `INTERCORE_BIN`. `intercore_available` sets it to `""` when the DB health check fails. `intercore_lock_available` sets it to the binary path without a health check. If `intercore_available` runs first and nullifies `INTERCORE_BIN`, then `intercore_lock_available` re-discovers the binary and sets it to the real path. Any subsequent call to a non-lock wrapper that reads `INTERCORE_BIN` directly (without re-calling `intercore_available`) will now use a binary that was never health-checked for DB access. In practice, all non-lock wrappers call `intercore_available` first — but this is an invisible invariant maintained by convention, not by isolation. The fix is a separate variable (`INTERCORE_LOCK_BIN`) so the two resolution paths do not share state.

### Fallback path coupling: structural gap

The bash fallback in `intercore_lock` (for when the binary is absent or erroring) creates a lock directory at the same path the Go binary uses (`/tmp/intercore/locks/<name>/<scope>`) but writes no `owner.json`. The Go `Manager.Stale()` method skips locks with `Created.IsZero()`, which happens when `owner.json` is absent or unreadable. Result: fallback-acquired locks that are never released (process crash) become permanently orphaned — `ic lock clean` will never evict them, and `ic lock list` will show them with no metadata. The intercore and bash paths are coupled by filesystem path convention, but their cleanup semantics diverge silently.

---

## Pattern Analysis

### Design patterns used: consistent

Every existing `cmd/ic/*.go` file uses flag parsing via `strings.HasPrefix` + `strings.TrimPrefix`, positional argument collection into a slice, and error-to-exit-code mapping. `cmd/ic/lock.go` follows all of these patterns exactly. Error sentinel variables (`ErrTimeout`, `ErrNotOwner`, `ErrNotFound`) follow the `errors.go` pattern established in `internal/phase/errors.go` and `internal/runtrack/errors.go`. The lock package does not add an `errors.go` file (all sentinels are in `lock.go`), which is a minor deviation — acceptable for a small package but worth noting if the package grows.

### Exit code inconsistency: documented incorrectly

The AGENTS.md exit-code table maps: 0=success, 1=contention, 2=usage error. However `cmdLockRelease` returns exit 1 for both `ErrNotFound` and `ErrNotOwner`. These are semantically distinct conditions — "lock didn't exist" versus "lock held by someone else" — but the documentation conflates them with the contention code (1). No current bash caller distinguishes these on release (all use `|| true`), so there is no breakage today. The drift between the documented contract and the actual exit codes should be resolved before any new caller is written.

### Naming consistency: good

- Go: `Manager`, `Lock`, `ownerMeta`, `Acquire`, `Release`, `List`, `Stale`, `Clean` — clear, consistent, matches the domain vocabulary in AGENTS.md
- Bash: `intercore_lock`, `intercore_unlock`, `intercore_lock_clean`, `intercore_lock_available` — follows the `intercore_<noun>_<verb>` convention established by `intercore_sentinel_check`, `intercore_state_set`, etc.
- CLI: `ic lock acquire / release / list / stale / clean` — matches the pattern of `ic dispatch spawn / status / list / kill / prune` and `ic run create / status / advance / phase / agent / artifact`

### Hook migration quality: good

The 5 inline mkdir patterns in `hooks/lib-sprint.sh` were correctly replaced with `intercore_lock / intercore_unlock` calls. The migration correctly preserves the fail-safe semantics: `sprint_set_artifact` and `checkpoint_write` use `|| return 0` (fail-safe, give up silently), while `sprint_claim` and `sprint_advance` use `|| return 1` (not fail-safe, signal failure to caller). The old code had the same semantic split — the migration preserved intent. The comment in `sprint_claim` that says "NOT fail-safe" was updated to reference intercore locking rather than mkdir. This is accurate and sufficient.

### Stale-break dual mechanism: acceptable but undocumented

`tryBreakStale` fires automatically during `Acquire` spin-wait using `m.StaleAge` (hardcoded 5s in the binary). The `ic lock stale` and `ic lock clean` commands use `--older-than` (default 5s) as a separate, manually-triggered or scheduled mechanism. These are two independent stale-eviction paths with the same default threshold but no documented relationship. An operator who sets `--older-than=30s` in a clean cronjob will not realize that Acquire is still breaking locks at 5s. This is not a bug — the separation is intentional and architecturally sound — but it should be documented.

---

## Simplicity and YAGNI Assessment

### Lock struct: appropriately sized

`Lock` exposes `Name`, `Scope`, `Owner`, `PID`, `Host`, `Created`. `ownerMeta` (the on-disk format) adds `PID` and `Host` as parsed fields separate from the opaque `Owner` string. This duplication between the string `owner` field ("PID:host") and the parsed `PID`/`Host` fields exists so the bash wrappers can pass the owner as a single opaque string while the Go code can still perform PID-liveness checks on Clean. This is intentional and justified.

### No speculative extensibility

`NewManager` takes a `baseDir` string (empty = default) and returns a `*Manager` with `BaseDir` and `StaleAge`. There is no interface, no plugin hook, no registry. The Manager is used directly by all five cmd functions. This is appropriately minimal.

### context.Context threading: correct but unused

All `Manager` methods accept `context.Context` as the first argument and name the parameter `_` (underscore, unused). This is the right pattern for a v1 implementation that does not yet need cancellation — it preserves the option to add cancellation later without breaking callers. The spin-wait loop in `Acquire` does not check `ctx.Done()`, which means a context cancellation during Acquire will not interrupt the wait. For the current use case (short timeouts, bash callers) this is acceptable.

### Test coverage: adequate for the mechanism

8 unit tests cover: acquire/release round-trip, contention timeout, stale-breaking, owner verification, not-found, list, clean with PID check, and concurrent acquire with race detector. The fallback bash path has no unit tests (expected — it is bash). The integration test exercises the CLI interface of all five subcommands. One gap: no test covers `List` returning entries with unreadable `owner.json` (the branch at `internal/lock/lock.go` lines 689-693). This is a minor coverage gap, not a structural issue.

---

## Key Findings Summary

1. **MEDIUM (A1):** `intercore_lock_available` and `intercore_available` share `INTERCORE_BIN` with incompatible validation semantics. Separate the lock binary variable to eliminate the shared-state coupling. File: `/root/projects/Interverse/infra/intercore/lib-intercore.sh` lines 16, 22-30, 283-286.

2. **LOW (A2):** Bash fallback path in `intercore_lock` creates a lock dir with no `owner.json`, making fallback-acquired locks invisible to `ic lock clean`. Write minimal metadata in the fallback path. File: `/root/projects/Interverse/infra/intercore/lib-intercore.sh` lines 207-215; `/root/projects/Interverse/infra/intercore/internal/lock/lock.go` lines 710-723.

3. **LOW (A3):** AGENTS.md exit-code table for lock commands documents code 2 as "usage error" but `cmdLockRelease` returns 1 for both ErrNotFound and ErrNotOwner, conflating distinct conditions. Update the table or add a separate exit code for ErrNotOwner. File: `/root/projects/Interverse/infra/intercore/cmd/ic/lock.go` lines 421-435; `/root/projects/Interverse/infra/intercore/AGENTS.md` lock exit-code table.

4. **INFO (A4):** Acquire stale-break threshold (hardcoded in binary, 5s) and `--older-than` (CLI flag, 5s default) are independent mechanisms with no documented relationship. Add a sentence to AGENTS.md.

**Verdict: needs-changes** — A1 and A2 are pre-load-bearing fixes; A3 is documentation correctness. None block the migration from old inline mkdir patterns, which is already correct.
