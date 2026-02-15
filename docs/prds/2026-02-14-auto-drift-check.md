# PRD: Auto-Drift-Check After Major Workflows

**Bead:** Clavain-iwuy

## Problem

After shipping work (commits, bead closures, version bumps), documentation can silently go stale. Users must remember to manually run `/interwatch:watch` — and they don't. The doc trilogy (roadmap, PRD, vision, AGENTS.md) sits at integration level L2 (routed but not auto-triggered).

## Solution

A Stop hook in Clavain that detects shipped-work signals and auto-triggers `/interwatch:watch`. Shared signal detection library (`lib-signals.sh`) ensures auto-compound and auto-drift-check both consume the same signals without duplication. Demo hooks in interwatch show the pattern for reuse.

## Features

### F1: Extract lib-signals.sh (shared signal detection library)

**What:** Extract the weighted signal detection logic from `auto-compound.sh` into `hooks/lib-signals.sh`, then refactor `auto-compound.sh` to source it.

**Acceptance criteria:**
- [ ] `hooks/lib-signals.sh` exists with a `detect_signals()` function
- [ ] `detect_signals()` takes transcript text as input, sets `CLAVAIN_SIGNALS` (comma-separated) and `CLAVAIN_SIGNAL_WEIGHT` (integer)
- [ ] All 7 signal patterns from auto-compound.sh are preserved (commit, resolution, investigation, bead-closed, insight, recovery, version-bump)
- [ ] `auto-compound.sh` sources `lib-signals.sh` and uses its output instead of inline grep patterns
- [ ] `auto-compound.sh` behavior is identical before and after refactor (same threshold, same guards, same output)
- [ ] `bash -n hooks/lib-signals.sh` passes (syntax check)
- [ ] Existing tests pass unchanged

### F2: Build auto-drift-check.sh (Stop hook)

**What:** New Stop hook that sources `lib-signals.sh`, applies a lower threshold (weight >= 2), discovers interwatch, and outputs a block+reason JSON telling Claude to run `/interwatch:watch`.

**Acceptance criteria:**
- [ ] `hooks/auto-drift-check.sh` exists and is registered in `hooks/hooks.json` as a Stop hook
- [ ] Sources `lib-signals.sh` for signal detection (no duplicate grep patterns)
- [ ] Threshold: weight >= 2 (lower than compound's >= 3)
- [ ] Guards: stop_hook_active, per-repo opt-out (`.claude/clavain.no-driftcheck`), 10-min throttle (`clavain-drift-last-*`), interwatch discovery
- [ ] Graceful degradation: exits 0 silently if interwatch not installed
- [ ] Output: JSON `{"decision":"block","reason":"...run /interwatch:watch..."}` matching auto-compound pattern
- [ ] Cross-hook sentinel resolved: each Stop hook checks but does not block other hooks (sentinel is per-hook, not shared)
- [ ] Ordering in hooks.json: auto-compound first, auto-drift-check second, session-handoff last
- [ ] `bash -n hooks/auto-drift-check.sh` passes
- [ ] CLAUDE.md quick commands updated with new syntax check

### F3: Demo hooks for interwatch (reuse examples)

**What:** Add `examples/hooks/` to the interwatch repo with a standalone drift-check hook example that others can adapt.

**Acceptance criteria:**
- [ ] `examples/hooks/auto-drift-check-example.sh` exists in interwatch repo
- [ ] Self-contained: no dependency on Clavain's lib-signals.sh (inline signal detection)
- [ ] Documented with comments explaining the pattern and customization points
- [ ] README section in interwatch explaining the hook example

## Non-goals

- Auto-refresh without user confirmation (interwatch confidence tiers handle this)
- Real-time file watching (inotify) — overkill for session-based tool
- Cross-session drift tracking (interwatch state in `.interwatch/` handles this)
- Dry-run mode (can add later if needed)

## Dependencies

- interwatch plugin installed (graceful degradation if not)
- `_discover_interwatch_plugin()` in `hooks/lib.sh` (already exists)
- interwatch `/interwatch:watch` skill (already exists)

## Open Questions

1. **Sentinel sharing resolved:** Each Stop hook gets its own sentinel (`clavain-stop-compound-*`, `clavain-stop-drift-*`) instead of the current shared `clavain-stop-*`. This lets both hooks fire in the same Stop cycle without blocking each other. The shared sentinel in auto-compound.sh will be renamed.
