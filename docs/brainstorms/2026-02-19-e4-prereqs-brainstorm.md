# E4 Prereqs: Session-Run Bridge + Interspect Kernel Events — Brainstorm

**Bead:** iv-w5ui
**Phase:** brainstorm (as of 2026-02-19)

## What We're Building

Close the gap between Interspect's bash-based evidence collection and the Intercore kernel's durable event store. Four prereqs (E4.3–E4.6) enable Interspect to read from and write to the kernel, creating the foundation for Level 3 Adapt (the E4 epic itself).

## Current State

### What's Already Implemented (code exists, beads not closed)

| Item | Status | Evidence |
|------|--------|----------|
| E4.1 (iv-3sns) | **Closed** | `interspect_events` table (schema v7), `AddInterspectEvent`/`ListInterspectEvents`/`MaxInterspectEventID` in `event/store.go` |
| E4.2 (iv-shra) | **Closed** | Durable cursor registration, `IsDurable` method, TTL=0 preservation |
| E4.3 (iv-s9vb) | **Implemented, bead open** | `interspect-session.sh` calls `ic run current` and stores `run_id`; `_interspect_ensure_db` has migration |
| E4.5 (iv-njct) | **Implemented, bead open** | `_interspect_consume_kernel_events()` in `lib-interspect.sh` — one-shot consumer at session start |
| E4.4 (iv-ula6) | **Partially implemented** | `/interspect:correction` has dual-write section, but uses `ic state set` workaround (not `ic interspect record`) |
| E4.6 (iv-dzbz) | **Not implemented** | Analysis commands read only from `interspect.db`, no kernel-side query |

### Critical Gap: Binary Stale

The installed `ic` binary is **v0.3.0 at schema v6**. The source has:
- Schema v7 (`interspect_events` table)
- `interspect.go` with `ic interspect record` and `ic interspect query` commands

But the binary was **never rebuilt**. This means:
- E4.3's `ic run current` works (existed in v0.3.0)
- E4.5's `ic events tail --consumer=interspect-consumer` works (existed in v0.3.0)
- But `ic interspect record/query` fail silently
- The `interspect_events` table may not exist in production DBs (v6 → v7 migration hasn't run)

### Key Architecture Insight

The dual-write in `/interspect:correction` currently uses `ic state set interspect-correction "$KEY"` — this stores corrections in the **generic state table**, not in `interspect_events`. Once we rebuild `ic` and run `ic init` (which auto-migrates to v7), the correction command should use `ic interspect record` instead.

## Approach: Rebuild + Wire + Verify

### Step 1: Rebuild `ic` binary

Rebuild from source to get schema v7 + `ic interspect` commands. Run `ic init` in all project DBs to auto-migrate.

### Step 2: Wire E4.4 properly

Replace the `ic state set` workaround in `/interspect:correction` with `ic interspect record --agent=<name> --type=correction --reason=<reason> --session=<id> --project=<dir>`.

### Step 3: Add E4.6 dual-read

Add kernel-side query to `/interspect` analysis command. Pattern: query `ic interspect query --agent=<name> --limit=100` → merge with legacy `interspect.db` evidence → dedup by agent+timestamp.

### Step 4: Ensure durable cursor registration

Add `ic events cursor register interspect-consumer --durable` call to `_interspect_ensure_db` or a new `_interspect_ensure_cursor` helper. Without this, the consumer cursor expires after 24h of inactivity.

### Step 5: Verify + close beads

Verify E4.3 (session-run bridge) and E4.5 (kernel event consumer) are working end-to-end with the new binary. Close all four prereq beads.

## Key Decisions

1. **Rebuild-first**: Binary rebuild is the prerequisite for everything else. No code changes needed in Go — just `go build`.
2. **Replace state-set workaround**: The correction dual-write should use `ic interspect record`, not `ic state set`. This puts corrections in the proper table with proper indexes.
3. **Merge strategy for dual-read**: Kernel-first, legacy-fallback. `interspect.db` becomes read-optimized cache during migration. Full retirement is post-E4.
4. **Durable cursor**: Register once, preserved forever. Prevents position loss during weekends/vacations.

## Open Questions

1. **Existing state-set corrections**: There may be correction records stored via `ic state set interspect-correction ...` from the workaround period. Should we migrate them to `interspect_events`? (Probably no — they're also in `interspect.db` via the primary write.)
2. **Schema v7 migration on all DBs**: How many project DBs exist that need migration? (Answer: `ic init` auto-migrates, so just run it in each project root.)

## Scope

~2-3 hours. No new Go code needed — just rebuild + bash edits + verification.
