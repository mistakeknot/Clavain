# Quality Review: intercore lock module

Date: 2026-02-18
Reviewer: fd-quality (Flux-drive Quality & Style)
Full findings: `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/fd-quality.md`

## Summary

The intercore lock module (internal/lock/, cmd/ic/lock.go, lib-intercore.sh wrappers, lib-sprint.sh migration) is architecturally correct. The mkdir atomicity approach, owner verification, PID-liveness check in Clean, 3-way exit code split in shell wrappers, and lock/unlock symmetry across all four lib-sprint.sh callers are all sound. One HIGH severity issue, one MEDIUM with real behavioral impact, and several LOW/documentation findings.

## Key Findings

1. **HIGH — Path traversal in lock name/scope (Q-01)**: `filepath.Join(m.BaseDir, name, scope)` does not reject `..` segments. An input like `../../../../` as the name resolves outside BaseDir. Experimentally confirmed: `ic lock acquire '../../../../' testscope` attempts to create `/testscope` — succeeds when run as root (the documented Claude Code execution context). The existing `validateDBPath` in `cmd/ic/main.go:188` shows the project knows how to fix this; the lock CLI layer needs the same guard.

2. **MEDIUM — intercore_lock_clean fallback ignores $max_age parameter (Q-05)**: The shell fallback `find ... -not -newermt '5 seconds ago'` hardcodes the threshold regardless of the `$1=max_age` argument. Callers passing a non-default age get correct behavior only when the binary is present; on fallback, the parameter is silently ignored. File: `lib-intercore.sh:342`.

3. **MEDIUM — intercore_lock_available INTERCORE_BIN side-effect (Q-04)**: When `intercore_lock_available` runs before `intercore_available` in a shell session, it sets the global `INTERCORE_BIN` without a DB health check. Subsequent `intercore_available` calls short-circuit on the non-empty variable and skip their health validation, potentially routing DB-dependent operations to a binary when the DB is broken.

Additional: `context.Background()` substituted for forwarded ctx in Stale/Clean (Q-03); ignored `os.Remove` errors in Release and tryBreakStale (Q-02); documentation inaccuracies (created field format, retry interval, exit code table semantics) (Q-07, Q-08, Q-09); unchecked error returns in test setup (Q-10).

Verdict: **needs-changes** — the path traversal (Q-01) and the fallback age bug (Q-05) should be fixed before the module is considered production-hardened. The remaining issues are low risk in the current deployment context.
