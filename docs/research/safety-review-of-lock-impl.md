# Safety Review: intercore Lock Module

**Date:** 2026-02-18
**Reviewer:** fd-safety agent (Clavain flux-drive)
**Scope:** `internal/lock/lock.go`, `cmd/ic/lock.go`, `lib-intercore.sh` lock wrappers, `hooks/lib-sprint.sh` callers
**Output written to:** `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/fd-safety.md`

---

## Threat Model Assessment

**System posture:** Local-only, single-host, single-user multi-agent coordination tool. All callers are cooperating shell hooks or Go processes owned by the same OS user. No network exposure. No authentication boundary between callers. `/tmp` is local tmpfs.

**Untrusted inputs:** None in the strict sense. Lock `name`, `scope`, and `--owner` values originate from shell variables in hook scripts (`$$`, `$(hostname -s)`, sprint IDs, checkpoint file paths transformed by `tr '/' '-'`). These are internally generated but not validated before reaching the Go lock layer.

**Credentials/sensitive data:** None involved in the lock module. `owner.json` contains PID and hostname only.

**Deployment path:** In-process Go CLI, sourced bash library. No staged rollout; changes deploy atomically with binary rebuild.

**Change risk classification:** Medium — new filesystem mutation code path with stale-break logic affecting multi-agent coordination correctness.

---

## Architecture Overview

The lock module implements a POSIX `mkdir`-based mutex under `/tmp/intercore/locks/<name>/<scope>/`. Acquiring a lock creates the scope directory atomically; releasing it removes `owner.json` then the directory. A separate `owner.json` file records identity metadata (PID, hostname, opaque owner string, Unix timestamp). Stale locks are broken by age (default 5s) during the Acquire spin-wait, and by age + PID liveness during `ic lock clean`.

The bash wrappers in `lib-intercore.sh` delegate to the `ic` binary and fall back to raw `mkdir` if the binary errors. Callers in `lib-sprint.sh` use the wrappers for three critical sections: sprint state update, phase completion recording, and sprint claim serialization.

---

## Findings Summary

### MEDIUM — L1: Path traversal via unsanitized name/scope parameters

`lockDir()` constructs the lock path as `filepath.Join(m.BaseDir, name, scope)` with no validation of the `name` or `scope` inputs. `filepath.Join` cleans the path but does not remove `..` components — it resolves them. A caller supplying `name="../evil"` would produce `/tmp/intercore/evil` as the lock directory, escaping the intended namespace.

In the current codebase, names are hardcoded strings like `"sprint"`, `"checkpoint"`, `"sprint-claim"`, and `"sprint-advance"`. The scope for checkpoints is derived from `echo "$CHECKPOINT_FILE" | tr '/' '-'`, which replaces all slashes with hyphens before passing to the Go layer — this specific case is safe. However, the Go `Manager.Acquire` API accepts arbitrary strings with no guard, making any future caller that passes unsanitized user input a traversal vector.

**File references:**
- `internal/lock/lock.go:65-67` — `lockDir` function
- `hooks/lib-sprint.sh:342-343` — checkpoint scope derivation
- `lib-intercore.sh:305` — bash fallback path construction (same issue)

**Impact:** Incorrectly scoped lock directories could be created or removed anywhere under `/tmp` that the process has write access to. No privilege escalation. Blast radius is limited to /tmp state corruption.

**Mitigation:** Add input validation in `lockDir()`:
```go
func (m *Manager) lockDir(name, scope string) (string, error) {
    if strings.ContainsAny(name, "/") || strings.Contains(name, "..") {
        return "", fmt.Errorf("invalid lock name: %q", name)
    }
    if strings.ContainsAny(scope, "/") || strings.Contains(scope, "..") {
        return "", fmt.Errorf("invalid lock scope: %q", scope)
    }
    return filepath.Join(m.BaseDir, name, scope), nil
}
```

---

### MEDIUM — L2: Race window in tryBreakStale allows live lock eviction

`tryBreakStale` performs three non-atomic operations: read `owner.json`, check age, then `os.Remove(owner.json)` + `os.Remove(lockDir)`. If two waiters simultaneously observe a stale lock and both pass the age check, the following sequence is possible:

1. Waiter A removes `owner.json`
2. Waiter B's `os.Remove(owner.json)` fails silently (already gone)
3. Waiter A calls `os.Remove(lockDir)` — succeeds (dir now empty)
4. Waiter A immediately calls `os.Mkdir(lockDir)` — succeeds, acquires lock
5. Waiter A writes its `owner.json`
6. Waiter B calls `os.Remove(lockDir)` — succeeds because `rmdir` on Linux removes a directory only if it is empty, but the new `owner.json` makes it non-empty... except `os.Remove` for a directory calls `unlinkat` with no children check on some implementations.

The actual Linux behavior is that `rmdir` (which `os.Remove` uses for directories) fails with `ENOTEMPTY` if the directory contains any files, so step 6 would fail. However, step 3 creates a window where a fresh lock holder's directory is empty for the duration between A writing its `os.Mkdir` and A writing `owner.json` (the `writeOwner` call). If B's `os.Remove(lockDir)` lands in that window, B can evict a live newly-acquired lock.

The AGENTS.md documents this concern ("no `os.RemoveAll` — prevents destroying concurrently re-acquired locks") but the two-step remove is not itself atomic.

**File references:**
- `internal/lock/lock.go:277-296` — `tryBreakStale`
- `internal/lock/lock.go:92-102` — Acquire: Mkdir then writeOwner gap

**Impact:** Under concurrent load with stale locks present, a live lock holder can be evicted, allowing two agents to simultaneously hold the same lock. For the sprint state and checkpoint use cases, this means lost-update races that the lock was designed to prevent.

**Mitigation:** Make eviction atomic by renaming before removing:
```go
tmp := ld + ".evicting-" + strconv.FormatInt(time.Now().UnixNano(), 36)
if err := os.Rename(ld, tmp); err != nil {
    return false // Someone else won the eviction race
}
os.Remove(filepath.Join(tmp, "owner.json"))
os.Remove(tmp)
return true
```
`os.Rename` is atomic on the same filesystem. Any concurrent `Mkdir(ld)` would succeed immediately after the rename, and the subsequent `os.Remove(tmp)` only touches the renamed path.

---

### LOW — L3: Caller-supplied PID trusted for liveness checks

`writeOwner` parses the PID out of the `--owner` string (`strings.SplitN(owner, ":", 2); strconv.Atoi(parts[0])`). This means the PID stored in `owner.json` — and later used by `pidAlive()` in `Clean` — is caller-controlled.

An agent that acquires a lock with `--owner=1:hostname` writes PID 1 (init/systemd) to `owner.json`. `pidAlive(1)` always returns true on any running Linux system. The lock becomes permanently immune to `ic lock clean`, regardless of whether the real holder is still alive.

Current callers use `$$:$(hostname -s)` which gives the shell's actual PID, so the risk is not exercised today. But the API design invites this bypass.

**File references:**
- `internal/lock/lock.go:240-245` — PID parsing from owner string
- `internal/lock/lock.go:220` — `pidAlive(l.PID)` in Clean
- `cmd/ic/lock.go:48` — `--owner=` flag acceptance

**Impact:** Stale lock immunity, requiring manual removal. No privilege escalation.

**Mitigation:** Always write `os.Getpid()` as the PID field, independent of the caller-supplied owner string. The `Owner` field retains the opaque identity for ownership verification; `PID` should always be the actual process that executed `ic lock acquire`.

---

### LOW — L4: Bash fallback path construction interpolates unsanitized name/scope

The bash fallback in `intercore_lock` (activated when the `ic` binary returns exit 2+) constructs:
```bash
local lock_dir="/tmp/intercore/locks/${name}/${scope}"
```
Bash word splitting and globbing are not a concern because the variables are quoted. However, if `name` or `scope` contains a `/` character, the path silently acquires extra depth. The same pattern appears in `intercore_unlock`'s fallback block.

The `intercore_lock_clean` fallback uses `find ... -mindepth 2 -maxdepth 2`, which limits cleanup depth and would not visit extra-deep directories created by a traversal-polluted fallback acquire.

**File references:**
- `lib-intercore.sh:305` — fallback lock_dir construction
- `lib-intercore.sh:327-328` — fallback unlock path

**Impact:** Same as L1 at the bash level. Currently not exploitable given how callers generate names and scopes.

**Mitigation:** Add a guard before the fallback:
```bash
[[ "$name" =~ ^[a-zA-Z0-9_-]+$ && "$scope" =~ ^[a-zA-Z0-9_-]+$ ]] || return 2
```

---

### LOW — L5: PID reuse window in liveness detection

`pidAlive` uses `syscall.Kill(pid, 0)` which queries whether a process with that PID currently exists. Linux recycles PIDs. The sequence:

1. Process A (PID 12345) holds a lock and crashes
2. PID 12345 is reassigned to unrelated process B within the stale age window
3. `ic lock clean --older-than=5s` runs, calls `pidAlive(12345)` → true (process B is alive)
4. Lock is not removed; it is permanently orphaned until manual intervention

The 5-second `StaleAge` default means the lock must survive 5 seconds after creation before `Clean` examines it. PID reuse within 5 seconds is uncommon on a lightly-loaded system but not impossible under rapid agent spawning.

**File references:**
- `internal/lock/lock.go:299-301` — `pidAlive`

**Impact:** Orphaned locks requiring manual removal. No security consequence.

**Mitigation:** Document this limitation explicitly in AGENTS.md and provide a `--force` flag on `ic lock clean` that skips `pidAlive` for manual recovery. Alternatively, record the lock file's inode or creation time in `owner.json` and cross-reference with `/proc/<pid>/` start time for a more reliable liveness check (Linux-specific).

---

### INFO — L6: tryBreakStale evicts by age alone, not age + PID liveness

`Clean` checks both age and `pidAlive` before evicting. `tryBreakStale` (called during the Acquire spin-wait) checks age only. A process holding a lock for more than 5 seconds — even if alive and actively executing its critical section — will have its lock broken by the next waiter.

This means StaleAge is a hard upper bound on critical section duration. For the current use cases (sprint state updates, checkpoint writes) this is probably fine: these operations are sub-second under normal conditions. But it is a correctness risk for any future caller that takes a lock around a slow operation.

**File references:**
- `internal/lock/lock.go:277-296` — `tryBreakStale` (no `pidAlive`)
- `internal/lock/lock.go:218-230` — `Clean` (uses `pidAlive`)

**Mitigation:** Either document the hard 5-second SLA prominently in the lock module godoc, or optionally add `pidAlive` check to `tryBreakStale` (accepting that a dead process can hold a lock forever if its PID is recycled, which is the same trade-off as L5).

---

## Deployment Safety Assessment

The lock module is filesystem-only (no SQLite schema changes). Deployment is safe to roll back by reverting the binary — no persistent state is created except in `/tmp`, which does not survive reboots. The bash wrappers in `lib-sprint.sh` replace three inline `mkdir`-loop patterns with `intercore_lock`/`intercore_unlock` calls. If the `ic` binary is absent or errors (exit 2+), the wrappers fall through to the original `mkdir` fallback pattern, preserving behavioral continuity.

**Rollback:** Replace binary with previous version. Existing locks in `/tmp/intercore/locks/` are compatible (directory-based mutex, same path scheme). No migration required.

**Pre-deploy checks:**
- `go test -race ./internal/lock/...` passes
- `bash test-integration.sh` lock section passes
- `ic lock list` returns empty after `rm -rf /tmp/intercore/locks`

**First-hour monitoring:** Watch for lock-related stderr in hook logs. A surge in `lock acquire: timed out` messages indicates the stale-break race (L2) is triggering. A permanently non-empty `ic lock list` after all agents complete indicates orphaned lock from L5.

---

## Verdict

**needs-changes**

Two medium findings (path traversal and stale-break race) should be fixed before the module is used in high-concurrency scenarios. The path traversal fix is a one-line guard. The stale-break atomic rename is a four-line change. The low findings are acceptable as documented limitations in a single-user local-only tool but should be acknowledged in code comments or AGENTS.md.
