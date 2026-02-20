# Synthesis: intercore lock module quality-gates review

**Date:** 2026-02-18
**Output dir:** `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/`
**Mode:** quality-gates
**Context:** 8 files changed across 2 languages (Go, Bash). New filesystem-based mutex module (internal/lock/) with CLI commands, bash wrappers, and migration of 5 inline mkdir lock patterns in lib-sprint.sh.

---

## Validation

4 agent files found:
- `fd-architecture.md` — VALID: has Findings Index, Verdict: needs-changes
- `fd-correctness.md` — VALID: has Findings Index, Verdict: needs-changes
- `fd-quality.md` — VALID: has Findings Index, Verdict: needs-changes
- `fd-safety.md` — VALID: has Findings Index, Verdict: needs-changes

**Validation: 4/4 agents valid, 0 failed**

---

## Raw finding counts before deduplication

| Agent | HIGH | MEDIUM | LOW | INFO | Total |
|-------|------|--------|-----|------|-------|
| fd-architecture | 0 | 1 | 2 | 1 | 4 |
| fd-correctness | 2 | 3 | 3 | 1 | 9 |
| fd-quality | 1 | 4 | 4 | 0 | 9 (sic, 10 in index) |
| fd-safety | 0 | 2 | 3 | 1 | 6 |
| **Total raw** | 3 | 10 | 12 | 3 | 28 |

---

## Deduplication

### Convergent findings (multiple agents, same issue)

**Path traversal (name/scope -> BaseDir escape)**
- fd-quality Q-01 and fd-safety L1 both independently identified this
- fd-quality verified experimentally: `ic lock acquire '../../../../' testscope` attempts `mkdir /testscope`
- fd-safety noted the `tr '/' '-'` in checkpoint scope is currently safe but the Go layer has no defense for future callers
- Merged to single P1 finding with convergence 2/4

**TOCTOU race in tryBreakStale**
- fd-correctness C1 and fd-safety L2 both identified this
- fd-correctness provided the concrete 5-step interleaving showing how both goroutines end up holding the lock simultaneously
- fd-safety provided the simpler framing (operational risk, not just theoretical)
- Merged to single P1 finding with convergence 2/4

**INTERCORE_BIN shared global**
- fd-architecture A1 and fd-quality Q-04 both flagged this
- fd-architecture: focused on the ordering dependency risk (lock_available runs first, poisons state)
- fd-quality: focused on the DB health bypass consequence
- Merged to single P2 finding with convergence 2/4

**Fallback mkdir no owner.json**
- fd-architecture A2 and fd-correctness C5 both raised this, but from different angles:
  - A2: orphan cleanup failure (Clean cannot evict)
  - C5: cross-mode unlock hazard (ic releases a fallback-acquired lock without owner check)
- These are distinct enough to keep separate — both are P2

**AGENTS.md documentation drift**
- fd-architecture A3 and fd-quality Q-07/Q-08/Q-09 overlap on exit-code table inaccuracy
- fd-quality adds two additional doc bugs (RFC3339 vs int64, 50ms vs 100ms)
- Merged into single IMP entry

**Context.Context ignored**
- fd-correctness C9 and fd-quality Q-03 both raised this
- fd-quality more specific: identifies that Stale and Clean substitute context.Background()
- Merged to single IMP entry

### Unique findings (single agent)

- C2 Ghost lock permanent (fd-correctness) — P2
- C3 Release no owner check (fd-correctness) — P2
- C4 Clean PID==0 bypass (fd-correctness) — subsumed by C2; noted but not separately elevated
- Q-02 Ignored os.Remove errors (fd-quality) — P2
- Q-05 intercore_lock_clean hardcoded age (fd-quality) — P2
- C7 Nested lock undocumented (fd-correctness) — IMP
- C8 PID 99999 assumption (fd-correctness) — IMP
- L3 Caller-supplied PID spoofing (fd-safety) — IMP (trust boundary is cooperative)
- L5 PID reuse window (fd-safety) — IMP (known limitation)
- Q-06 errors.Is (fd-quality) — IMP

---

## Categorized findings after deduplication

### P1 — CRITICAL (2 findings)

1. **PATH-TRAVERSAL** — Path traversal: name/scope not validated against BaseDir
   - `internal/lock/lock.go:65-66`, `cmd/ic/lock.go:74`
   - Convergence: fd-quality, fd-safety (2/4)
   - Exploitable as root (default for this project). `validateDBPath` in `main.go:188-204` is the existing pattern to follow.

2. **TOCTOU-STALE-BREAK** — TOCTOU race in tryBreakStale allows spurious double-ownership
   - `internal/lock/lock.go:277-296`
   - Convergence: fd-correctness, fd-safety (2/4)
   - Interleaving allows two goroutines to both hold the same lock simultaneously. Fix: atomic rename-then-rmdir.

### P2 — IMPORTANT (7 findings)

3. **RELEASE-NO-OWNER-CHECK** — Release removes lock dir unconditionally when owner.json missing
   - `internal/lock/lock.go:126-134`
   - Any caller can release a lock they do not own when owner.json is absent/corrupt.

4. **INTERCORE-BIN-SHARED-STATE** — INTERCORE_BIN shared state bypasses DB health check
   - `lib-intercore.sh:22,284-286`
   - Convergence: fd-architecture, fd-quality (2/4)

5. **FALLBACK-NO-OWNER-JSON** — Bash fallback acquires lock with no owner.json
   - `lib-intercore.sh:207-215`
   - Convergence: fd-architecture, fd-safety (2/4)
   - Orphan locks survive forever; `ic lock clean` cannot evict them.

6. **MIXED-MODE-UNLOCK** — Mixed fallback/ic unlock mode hazard
   - `lib-intercore.sh:196-232`
   - If binary reappears mid-session, unlock mode mismatches acquire mode, creating stuck locks.

7. **GHOST-LOCK-PERMANENT** — Ghost lock after crash in acquire window becomes permanent
   - `internal/lock/lock.go:92-102`
   - ~1ms window between mkdir and writeOwner. PID==0, Created==zero → never cleaned.

8. **LOCK-CLEAN-HARDCODED-AGE** — intercore_lock_clean fallback hardcodes "5 seconds ago"
   - `lib-intercore.sh:342`
   - $max_age parameter accepted but ignored in fallback path.

9. **IGNORED-REMOVE-ERRORS** — os.Remove errors silently discarded in Release, Clean, tryBreakStale
   - `lock.go:132,140,226,293`
   - Release can return nil (success) while lock dir still exists.

### IMP — Improvements (6 items)

- AGENTS.md documentation drift: created field format, retry interval, exit code table
- Nested lock in sprint_advance undocumented
- context.Context not forwarded (Stale, Clean substitute context.Background())
- PID reuse window in pidAlive — document known limitation
- Integration test PID 99999 assumption
- errors.Is vs == for sentinel errors

---

## Conflicts

**Stale-break severity disagreement:** fd-safety rates L2 as MEDIUM, fd-correctness rates C1 as HIGH. Both framings correct for their domain. Resolved: retain as P1 because the worst-case outcome (double-ownership) is functionally a mutex violation.

**Ghost lock treatment:** fd-correctness C2 (ghost from Go crash) and fd-architecture A2 / fd-correctness C5 (bash fallback no owner.json) produce similar symptoms but via different mechanisms. Kept as separate P2 findings.

No fundamental disagreements between agents.

---

## Overall verdict: needs-changes

- Any P1 → verdict is "needs-changes" (no P0 found → not "risky")
- Gate: FAIL on P1 count > 0
- All 4 agents agree: needs-changes

---

## Output files written

- `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/synthesis.md`
- `/root/projects/Interverse/infra/intercore/.clavain/quality-gates/findings.json`
- `/root/projects/Interverse/infra/intercore/.clavain/verdicts/fd-architecture.json`
- `/root/projects/Interverse/infra/intercore/.clavain/verdicts/fd-correctness.json`
- `/root/projects/Interverse/infra/intercore/.clavain/verdicts/fd-quality.json`
- `/root/projects/Interverse/infra/intercore/.clavain/verdicts/fd-safety.json`
