# Bead Lifecycle Reliability — Auto-Close Parents + Universal Bead Claiming
**Bead:** iv-kpoz8

## What We're Building

Two reliability improvements to Clavain's bead lifecycle management:

1. **Auto-close parent beads** — When a sprint bead ships and all children of its parent bead are closed, automatically close the parent. Today sprint beads (e.g., iv-i1i3) get closed at ship time but their parent feature beads (e.g., iv-lx00) are orphaned. This causes phantom open beads that look like unfinished work.

2. **Universal bead claiming** — Allow any session to "claim" a bead via `bd set-state`, not just sprints via `ic run agent`. Discovery should filter or annotate claimed beads so two sessions don't accidentally work on the same thing.

## Why This Approach

### Problem 1: Orphaned parent beads

The sprint skill's Step 10 (Ship) calls `close-children` to close beads **blocked by** the sprint. But it never checks upward — if the sprint bead is a child of a parent feature bead, and all siblings are done, the parent should auto-close.

**Real examples found today:**
- iv-asfy (C1: Agency specs) — fully implemented, never closed
- iv-lx00 (C2: Fleet registry) — shipped under sprint iv-i1i3, parent never closed

Both blocked downstream beads (C3, C4) that appeared stuck.

**Fix location:** `sprint_close_children()` in `lib-sprint.sh` — add upward traversal after the existing downward sweep. Also add a new `clavain-cli close-parent-if-done` subcommand.

### Problem 2: No claim mechanism outside sprints

`sprint_claim()` in `lib-sprint.sh` registers a "session" agent on an `ic run`. But:
- Only works for sprint beads (requires an ic run)
- Ad-hoc `/work` or `/brainstorm` on a bead has no claim
- Discovery (`lib-discovery.sh` in interphase) has zero claim awareness
- Two sessions can pick the same bead from discovery

**Fix approach:** Use `bd set-state` for claims (syncs with beads DB, visible in `bd show`, works across machines). Discovery checks claim state and either filters claimed beads or shows them as "(in use by session X, Nm ago)".

**Claim lifecycle:**
- Set on: sprint claim, brainstorm start, work start, any `/route` dispatch
- Clear on: sprint ship, session end hook, or stale timeout (2h)
- Check in: `discovery_scan_beads()`, sprint resume

## Key Decisions

1. **bd set-state for claims** (not ic lock) — durable, visible, syncs across machines. Stale claims cleaned by age check (2h default).

2. **Upward traversal is bounded** — only check one level up (parent). Don't recursively close grandparent epics — that's a different decision with different risk.

3. **Claim is advisory, not blocking** — Discovery shows "(in use)" but doesn't hard-block. User can force-claim. This avoids deadlocks from crashed sessions.

4. **Stale claim timeout: 2 hours** — matches typical session duration. Sessions that crash without cleanup get their claims auto-expired on next discovery scan.

5. **Session-end hook clears claims** — `session-end-handoff.sh` (or a new hook) calls `bd set-state <bead_id> claimed_by=` to release.

## Files to Modify

| File | Plugin | Change |
|------|--------|--------|
| `hooks/lib-sprint.sh` | clavain | Add `sprint_close_parent_if_done()`, call from ship step |
| `bin/clavain-cli` | clavain | Add `close-parent-if-done` subcommand |
| `hooks/lib-discovery.sh` | interphase | Add claim checking in `discovery_scan_beads()` |
| `hooks/session-end-handoff.sh` | clavain | Release claim on session end |
| `skills/sprint/SKILL.md` | clavain | Update Step 10 to call close-parent-if-done |

## Open Questions

- Should we also add claiming to the `/brainstorm` and `/work` skills directly, or only via `/sprint` and `/route`?
- Should claimed beads be completely hidden from discovery, or shown with a visual indicator?
