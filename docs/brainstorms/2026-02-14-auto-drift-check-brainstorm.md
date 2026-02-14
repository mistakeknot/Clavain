# Auto-Drift-Check After Major Workflows

**Bead:** Clavain-iwuy
**Phase:** brainstorm (as of 2026-02-14T21:08:11Z)
**Date:** 2026-02-14
**Status:** Ready for planning

## What We're Building

A Stop hook in Clavain that detects "shipped work" signals (git commits, bead closures, version bumps, test recovery) and auto-triggers `/interwatch:watch` to scan for doc drift. This closes the loop between "work happened" and "docs need updating" — getting the doc trilogy (roadmap, PRD, vision, AGENTS.md) from integration level L2 (routed) to L4 (auto-triggered).

## Why This Approach

### Architecture: Hub Pattern with Shared Signals

**Decision:** All inter-module hooks live in Clavain (hub). Companions (interwatch, interpath, etc.) stay passive — skills and commands only, no hooks. This was chosen because:

- Clavain already owns all hook orchestration (7 hooks across 4 event types)
- Companions work standalone without hook dependency (graceful degradation)
- Signal detection stays consolidated in one place (no duplication)
- One place to debug hook timing/conflicts

**Demo hooks for companions:** Each companion repo should include example/demo hook scripts showing how to compose signals → actions, so other users can adapt the pattern without needing Clavain.

### Structure: Shared Signals, Separate Actions

**Decision:** Extract signal detection from `auto-compound.sh` into a shared library (`hooks/lib-signals.sh`), then both `auto-compound.sh` and `auto-drift-check.sh` source it independently.

**Why:** Both hooks fire on Stop and scan the same transcript for the same signals. Without extraction:
- Duplicate grep patterns across two scripts
- Two separate transcript scans per Stop event
- Signal weight definitions diverge over time

With `lib-signals.sh`:
- Single source of truth for signal definitions and weights
- Each consumer picks its own threshold and response
- Future Stop hooks (e.g., auto-summary) plug in trivially
- Transcript is scanned once, results cached in variables

### Signal Flow

```
Stop event
  → lib-signals.sh: scan transcript → SIGNALS, WEIGHT
  → auto-compound.sh: if weight >= 3 → block + "evaluate /compound"
  → auto-drift-check.sh: if weight >= 2 → block + "run /interwatch:watch"
```

The drift-check has a **lower threshold** (weight >= 2) because doc staleness is cheaper to check than compounding knowledge. A simple commit + bead-close (weight 2) should trigger a drift scan even if it's not worth compounding.

## Key Decisions

1. **Hook location:** Clavain (hub pattern), not interwatch or shared
2. **Signal extraction:** `lib-signals.sh` shared library, sourced by both auto-compound and auto-drift-check
3. **Lower threshold:** Weight >= 2 for drift check (vs >= 3 for compound)
4. **Separate throttle:** Own throttle sentinel (`clavain-drift-last-*`), separate from compound's 5-min throttle. Drift check throttle: 10 minutes (scans take longer, less urgency)
5. **Graceful degradation:** If interwatch not installed, drift-check hook exits silently (uses `_discover_interwatch_plugin()` from lib.sh)
6. **Block+reason pattern:** Same as auto-compound — returns JSON telling Claude to evaluate and run `/interwatch:watch` if appropriate
7. **Demo hooks:** Add `examples/hooks/` to interwatch repo with a standalone drift-check example

## Signals and Weights

| Signal | Weight | Detection Pattern |
|--------|--------|-------------------|
| Git commit | 1 | `"git commit"` in transcript |
| Bead closed | 1 | `"bd close"` in transcript |
| Version bump | 2 | `bump-version\|interpub:release` in transcript |
| Debugging resolution | 2 | Resolution phrases ("that worked", "it's fixed") |
| Investigation language | 2 | Root cause phrases ("the issue was", "turned out") |
| Build/test recovery | 2 | FAIL → pass pattern |
| Insight block | 1 | `★ Insight` marker |

**Drift-check cares most about:** commit, bead-closed, version-bump (work shipped signals). Resolution/investigation are secondary but still relevant (if you fixed a bug, docs might reference the old behavior).

## Guards (Following auto-compound.sh Pattern)

1. **stop_hook_active** — prevent infinite loop if drift-check triggers another Stop
2. **Cross-hook sentinel** — `/tmp/clavain-stop-${SESSION_ID}` (shared with auto-compound)
3. **Per-repo opt-out** — `.claude/clavain.no-driftcheck`
4. **Throttle** — `/tmp/clavain-drift-last-${SESSION_ID}`, 10-minute window
5. **Interwatch discovery** — exit 0 if not installed

## What This Unblocks

- **Clavain-1626** (P2): Version-bump → Interwatch signal — can use the version_bump signal from lib-signals.sh
- **Clavain-444d** (P2): Catalog-reminder → Interwatch escalation — catalog changes trigger drift check
- **Clavain-mqm4** (P2): Session-start drift summary injection — complementary (session start shows stale state, Stop hook triggers refresh)

## Open Questions

1. **Sentinel sharing:** Should auto-compound and auto-drift-check share the cross-hook sentinel (`clavain-stop-*`)? Currently auto-compound writes it, which would block drift-check. Option: each writes its own sentinel, or use a counter instead of a flag.
2. **Ordering in hooks.json:** Both hooks fire on Stop. Does order matter? Claude Code runs Stop hooks sequentially — auto-compound should probably fire first (it's more important), drift-check second.
3. **Dry-run mode:** Should drift-check support `CLAVAIN_DRIFTCHECK_DRY_RUN=1` for testing signal detection without triggering interwatch?

## Non-Goals (YAGNI)

- Auto-refresh without user confirmation (interwatch's confidence tiers handle this)
- Real-time file watching (inotify) — overkill for a session-based tool
- Cross-session drift tracking (interwatch state in `.interwatch/` handles this)
- Webhook/external notification on drift detection
