# Correctness Review: intercore lock module

**Reviewer:** Julik / fd-correctness
**Date:** 2026-02-18
**Target:** intercore `internal/lock/lock.go`, `cmd/ic/lock.go`, `lib-intercore.sh`, clavain `hooks/lib-sprint.sh`
**Primary output:** `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/fd-correctness.md`

---

## Invariants Identified

Before findings, these are the invariants the lock module is trying to maintain:

1. **Mutual exclusion:** At most one caller holds `<name>/<scope>` at any instant.
2. **Owner identity:** Only the process that acquired the lock can release it.
3. **Stale-lock recovery:** A lock held by a dead process is cleaned up without human intervention within `StaleAge` of the next contending caller.
4. **Filesystem atomicity:** `os.Mkdir` is the exclusive serialisation point — no other mechanism is used.
5. **Bash fallback transparency:** A lock acquired via the fallback `mkdir` path is semantically equivalent to one acquired via `ic lock acquire`.
6. **Fail-safe release:** Unlock failure never blocks the caller; it returns 0 and logs silently.

The HIGH findings are violations of invariants 1 and 2. The MEDIUM findings are violations of invariants 2, 3, and 5.

---

## Summary

The core design is well-chosen: POSIX `mkdir` atomicity is reliable on local filesystems, and the two-file layout (`<name>/<scope>/owner.json`) is clean. The stale-break mechanism is the correct approach for crash recovery. However, there are two TOCTOU races in the stale-break path that can produce transient double-ownership (HIGH), a Release code path that bypasses owner verification when owner.json is unreadable (MEDIUM), a stuck-lock scenario for crashes during the mkdir-to-owner.json write window (MEDIUM), and a silent mixed-mode hazard in the Bash fallback (MEDIUM). None of these will wake someone at 3 AM on a lightly-loaded system; on a loaded container environment with concurrent agents they are real.

The sprint hook migration from inline mkdir to intercore_lock is structurally correct. The pre-migration inline code had a more dangerous stale-break (it used `rm -rf` which could destroy a concurrently re-acquired lock; the new code uses the safer `os.Remove` pair). The nested lock in `sprint_advance` calling `sprint_record_phase_completion` is sound because the two lock names differ, but it is undocumented.

---

## Detailed Findings

### C1 (HIGH): TOCTOU in tryBreakStale allows spurious double-ownership

**Location:** `internal/lock/lock.go:277-295`

`tryBreakStale` performs three non-atomic steps: (1) read owner.json, (2) `os.Remove(owner.json)`, (3) `os.Remove(lockDir)`. Two concurrent callers can both observe the stale timestamp, both proceed to step (2), and both succeed (the second Remove of owner.json gets ENOENT which is discarded). Then both call `os.Remove(lockDir)`. The first succeeds and the caller re-acquires via `os.Mkdir`. The second also succeeds (the dir was just recreated by the first caller's next `os.Mkdir` call).

Concrete bad interleaving with two goroutines (A and B), both contending on the same stale lock:

```
A: readOwner → stale timestamp confirmed
B: readOwner → stale timestamp confirmed
A: os.Remove(owner.json) → OK
B: os.Remove(owner.json) → ENOENT, discarded
A: os.Remove(lockDir) → OK. tryBreakStale returns true.
A: os.Mkdir(lockDir) → acquired. writeOwner → done. A holds the lock.
B: os.Remove(lockDir) → OK (removes A's freshly-written dir). tryBreakStale returns true.
B: os.Mkdir(lockDir) → acquired. writeOwner → done. B holds the lock.
// Both A and B believe they hold "the" lock. Invariant 1 violated.
```

The window is sub-millisecond on a local filesystem, but on concurrent agent runs with 10+ goroutines hitting the same lock (as in `TestConcurrentAcquire`), the probability is non-negligible.

**Fix:** Make the stale-break atomic. The simplest approach is to rename the lock directory to a randomly-named temp dir before removing it. `os.Rename` on Linux is atomic. Only the goroutine whose rename succeeds proceeds to re-acquire:

```go
func (m *Manager) tryBreakStale(name, scope string) bool {
    meta, err := m.readOwner(name, scope)
    if err != nil {
        return false
    }
    if time.Since(time.Unix(meta.Created, 0)) < m.StaleAge {
        return false
    }
    // Atomic claim: rename the stale dir to a unique temp name.
    ld := m.lockDir(name, scope)
    tmp := ld + ".breaking-" + strconv.FormatInt(time.Now().UnixNano(), 36)
    if err := os.Rename(ld, tmp); err != nil {
        return false // Another goroutine won the race.
    }
    os.RemoveAll(tmp) // Now safe: we own tmp.
    return true
}
```

`os.RemoveAll` is safe here because `tmp` is a uniquely-named directory that only this goroutine knows about. The concern documented in the code ("no `os.RemoveAll` — prevents destroying concurrently re-acquired locks") is addressed because we rename first.

---

### C2 (HIGH): Ghost lock — crash between mkdir and writeOwner creates permanent stuck lock

**Location:** `internal/lock/lock.go:92-103`

After `os.Mkdir` succeeds, there is a window before `writeOwner` completes during which the lock directory exists with no `owner.json`. If the process dies in this window (OOM kill, SIGKILL, power failure), the resulting ghost lock:

- Appears in `List` with PID==0 and Created==zero time.
- Is excluded from `Stale` by the `!l.Created.IsZero()` guard.
- Is skipped by `Clean` because `l.PID > 0` is false when PID==0.
- Is skipped by `tryBreakStale` because `readOwner` fails and it returns false with the comment "might be mid-creation".

The ghost lock is permanent. `ic lock clean` with any `--older-than` value will not remove it. Manual `rm -rf /tmp/intercore/locks/<name>/<scope>` is required.

The window is tiny (~1ms on local disk) but the impact is a permanently stuck lock until manual intervention.

**Fix:** In `Clean`, when a lock has PID==0 and zero Created time, fall back to the directory mtime as the age source:

```go
if l.PID == 0 && l.Created.IsZero() {
    // Ghost lock: no owner.json. Use directory mtime as age proxy.
    info, err := os.Stat(m.lockDir(l.Name, l.Scope))
    if err == nil && time.Since(info.ModTime()) > maxAge {
        // Old enough to be a crash artifact, not a mid-creation ghost.
        os.Remove(m.lockDir(l.Name, l.Scope))
        removed++
    }
    continue
}
```

Also remove the `!l.Created.IsZero()` exclusion from `Stale` and instead use the directory mtime as a fallback there too.

---

### C3 (MEDIUM): Release removes lock dir when owner.json is unreadable, bypassing owner check

**Location:** `internal/lock/lock.go:126-134`

```go
meta, err := m.readOwner(name, scope)
if err != nil {
    if os.IsNotExist(err) {
        return ErrNotFound
    }
    // owner.json missing but dir exists — treat as unlocked.
    os.Remove(ld)
    return nil
}
```

`os.IsNotExist` from `os.ReadFile` is true when owner.json (not the lock dir itself) is absent. When owner.json is absent but the lock dir exists (ghost lock, corrupt state, or NFS glitch), the code removes the lock dir and returns nil — without verifying the caller's owner. Any caller with any owner string can trigger this path.

The severity is MEDIUM rather than HIGH because this requires an already-corrupted state (missing owner.json with an existing lock dir). But an admin running `ic lock release <name> <scope> --owner=admin:host` expecting to see an error would instead silently destroy a potentially live lock held by a different process (if that process is in the C2 ghost-lock window).

**Fix:** Return `ErrCorrupt` (or a new sentinel) when the lock dir exists but owner.json is unreadable, rather than silently removing:

```go
if os.IsNotExist(err) {
    return ErrNotFound
}
return fmt.Errorf("lock release: corrupt lock (no owner.json): %w", ErrNotFound)
```

Direct repair should go through `ic lock clean`, which has the PID-liveness check.

---

### C4 (MEDIUM): PID==0 bypasses liveness check in Clean

**Location:** `internal/lock/lock.go:220`

```go
if l.PID > 0 && pidAlive(l.PID) {
    continue
}
```

When PID is 0, the condition short-circuits and the lock is evicted without any liveness check. Currently ghost locks (the main source of PID==0) are excluded from the Stale list before reaching Clean, so this is not currently exploitable. But the logic is fragile: any future code path that creates a `Lock` struct with PID==0 and a non-zero Created time will be unconditionally evicted by Clean. The guard should be made explicit:

```go
if l.PID > 0 {
    if pidAlive(l.PID) {
        continue // Live process — skip.
    }
} else {
    // PID unknown (ghost lock or legacy format) — use mtime fallback (see C2 fix).
    // Do not evict blindly.
    continue
}
```

---

### C5 (MEDIUM): Bash fallback — mode mismatch creates uncloseable lock

**Location:** `lib-intercore.sh:196-232`

`intercore_lock` may use raw `mkdir` if the `ic` binary exits with code 2+ (binary error). The raw-mkdir lock creates the lock directory with no `owner.json`. Later, `intercore_unlock` always tries the `ic` path first if the binary is available. `ic lock release` calls `Release()`, which calls `readOwner`, gets an error (no owner.json), hits C3's silent-remove path, and removes the lock — without verifying the caller owns it. This is the "correct" outcome accidentally.

The more dangerous scenario is the reverse: if `ic lock acquire` is used (creating owner.json with the caller's PID), but the binary subsequently becomes unavailable, `intercore_unlock` falls back to `rm -f owner.json && rmdir <lockdir>`, which succeeds without any owner check. Any process that can call `intercore_unlock` can release any lock.

Neither scenario is currently likely in practice, but the two fallback paths are semantically incompatible. They share the same directory structure but have different semantics for what constitutes a valid lock.

**Fix:** Write a `.fallback` marker file alongside the lock dir in the raw-mkdir path:

```bash
mkdir "$lock_dir" 2>/dev/null && touch "$lock_dir/.fallback"
```

In `intercore_unlock`, check for the marker:

```bash
if [[ -f "${lock_dir}/.fallback" ]]; then
    rm -f "${lock_dir}/.fallback" "${lock_dir}/owner.json" 2>/dev/null || true
    rmdir "${lock_dir}" 2>/dev/null || true
else
    # Use ic release (owner-verified)
    "$INTERCORE_BIN" lock release "$name" "$scope" --owner="$_owner" ...
fi
```

---

### C6 (LOW): Deadline checked after sleep — effective timeout exceeds stated maxWait

**Location:** `internal/lock/lock.go:110-117`

```go
if m.tryBreakStale(name, scope) {
    continue
}
if time.Now().After(deadline) {
    return ErrTimeout
}
time.Sleep(DefaultRetryWait)
```

If `tryBreakStale` returns false and the deadline has just passed, the goroutine sleeps `DefaultRetryWait` (100ms) before checking the deadline at the top of the next loop iteration. Actual maximum wait is `maxWait + ~tryBreakStale latency + DefaultRetryWait`. For a 300ms test timeout this means the test can take up to 400ms before failing. `TestAcquireContention` uses 300ms and may be flaky on slow CI.

**Fix:** Move the deadline check to immediately after the failed `os.Mkdir`:

```go
if !os.IsExist(err) {
    return fmt.Errorf(...)
}
if time.Now().After(deadline) {
    return ErrTimeout
}
if m.tryBreakStale(name, scope) {
    continue
}
time.Sleep(DefaultRetryWait)
```

---

### C7 (LOW): sprint_advance holds sprint-advance lock while calling sprint_record_phase_completion which acquires sprint lock

**Location:** `hooks/lib-sprint.sh`, `sprint_advance` function (post-migration)

`sprint_advance` acquires `intercore_lock "sprint-advance" "$sprint_id"` and then calls `sprint_record_phase_completion "$sprint_id" "$next_phase"`. That function acquires `intercore_lock "sprint" "$sprint_id"`. Lock-ordering is:

```
sprint-advance/$sprint_id → sprint/$sprint_id
```

This is safe as long as no other code path acquires `sprint` before `sprint-advance`. Currently `sprint_set_artifact` acquires only `sprint/$sprint_id` and never calls into `sprint_advance`. The lock ordering is consistent. However, the nesting is invisible in the calling code and is not documented.

If someone adds a call from `sprint_set_artifact` to `sprint_advance` (or any function that calls `sprint_advance`), the result is a deadlock:

```
sprint_set_artifact: acquires sprint/$id
  → calls sprint_advance
    → tries to acquire sprint-advance/$id ... OK
      → calls sprint_record_phase_completion
        → tries to acquire sprint/$id ... DEADLOCKED (already held by sprint_set_artifact)
```

**Fix:** Add a comment above the `sprint_record_phase_completion` call in `sprint_advance`:

```bash
# NOTE: sprint_record_phase_completion acquires "sprint/$sprint_id" internally.
# Lock ordering: sprint-advance/$id → sprint/$id.
# Never call sprint_advance from a context holding sprint/$id.
sprint_record_phase_completion "$sprint_id" "$next_phase"
```

---

### C8 (LOW): Integration test assumes PID 99999 is dead

**Location:** `test-integration.sh:285-294`

The stale-lock cleanup test uses PID 99999 and asserts that `ic lock clean` removes the lock because "PID 99999 should not exist". On a system with a high PID namespace or on a long-running container, PID 99999 may be a live process. When it is, `pidAlive(99999)` returns true, `Clean` skips the lock, and the test fails with "stale lock not cleaned".

**Fix:** Use a PID that is guaranteed dead. On Linux, `kill -0 $$` always succeeds for the current process. Use the current PID +1 modulo a small prime and verify it is dead before using it, or use the approach of writing `{"pid":0}` and relying on the zero-PID cleanup path (once C4 is fixed):

```bash
# Find a guaranteed-dead PID
DEAD_PID=$(python3 -c "import os; print(os.getpid() + 1000000)" 2>/dev/null || echo 99999)
```

Or simply use a hostname that cannot match a real process (PID check is primary; hostname is secondary):

```bash
# On Linux, max PID is /proc/sys/kernel/pid_max (default 32768 or 4194304).
# Use pid_max + 1.
DEAD_PID=$(( $(cat /proc/sys/kernel/pid_max 2>/dev/null || echo 32767) + 1 ))
```

---

### C9 (INFO): context.Context accepted but not checked — cancellation silently ignored

**Location:** `internal/lock/lock.go:77` and all Manager methods

All methods name the context parameter `_` explicitly. For CLI use (where `context.Background()` is always passed) this is fine. If the package is ever used from a service, signal-cancelled contexts will not interrupt the spin-wait. The spin-wait sleeps 100ms per iteration; with a 5s timeout and no cancellation, a cancelled context still waits up to 5s.

**Fix for service use:** Add a `select` in the spin-wait:

```go
select {
case <-ctx.Done():
    return ctx.Err()
case <-time.After(DefaultRetryWait):
}
```

At minimum, rename the parameter from `_` to `ctx` and add a comment: "context cancellation not yet propagated; callers requiring cancellation should set a short maxWait."

---

## Test Coverage Assessment

The 8 unit tests cover the happy paths and basic contention well. Missing coverage:

- **No test for the ghost-lock scenario (C2)**: crash between mkdir and writeOwner. Add a test that creates a lock dir with no owner.json and verifies `Clean` eventually removes it (after the C2 fix is applied).
- **TestConcurrentAcquire does not verify stale-break under concurrency**: the stale-break TOCTOU (C1) is not exercised. Add a test with a pre-planted stale lock and N goroutines simultaneously discovering it.
- **No test for the corrupt owner.json Release path (C3)**: easy to add — acquire, corrupt owner.json, attempt release with any owner string, assert error.
- **No test for context cancellation (C9)**: if context support is added, add a test that cancels the context while waiting for a contended lock.

The integration test in `test-integration.sh` is good but the PID 99999 assumption (C8) should be fixed before CI runs on containers.

---

## Summary Table

| ID | Severity | Invariant violated | Fix complexity |
|----|----------|--------------------|---------------|
| C1 | HIGH | Mutual exclusion | Medium — rename-before-remove in tryBreakStale |
| C2 | HIGH | Stale recovery | Low — mtime fallback in Clean and Stale |
| C3 | MEDIUM | Owner identity | Low — return ErrCorrupt instead of silent remove |
| C4 | MEDIUM | Stale recovery | Low — make PID==0 explicit, use mtime fallback |
| C5 | MEDIUM | Fallback transparency | Medium — mode marker file |
| C6 | LOW | Timeout accuracy | Trivial — move deadline check |
| C7 | LOW | Lock ordering documented | Trivial — add comment |
| C8 | LOW | Test reliability | Low — use /proc/sys/kernel/pid_max |
| C9 | INFO | Cancellation | Low — add select on ctx.Done |
