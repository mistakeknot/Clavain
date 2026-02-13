# Hooks Cleanup Batch — Brainstorm

**Date:** 2026-02-11
**Beads:** Clavain-8t5l, Clavain-azlo, Clavain-gw0h

## What We're Building

A parallel Codex batch that fixes 3 hooks-related issues:

1. **Clavain-8t5l** (bug): Add shared sentinel between Stop hooks to prevent compound-after-handoff loop. Both `auto-compound.sh` and `session-handoff.sh` run on Stop. When handoff commits, compound detects the commit signal and fires again. Fix: shared `/tmp/clavain-stop-<SESSION_ID>` sentinel checked by both hooks.

2. **Clavain-azlo** (feature): Narrow auto-compound triggers + add per-repo opt-out. Currently fires on routine commits during `/work`. Fix: require resolution+commit co-occurrence, add `.claude/clavain.no-autocompound` opt-out file check, add throttle (at most once per 5 minutes via timestamp sentinel).

3. **Clavain-gw0h** (task): Simplify `escape_for_json` control character loop in `lib.sh`. The 26-iteration loop scanning for control chars that never appear in markdown can be replaced with a simpler approach. Saves ~50% of function time.

## Why This Approach

- All 3 are small, well-scoped changes to hooks/
- The bug (8t5l) blocks the feature (azlo) since both modify auto-compound.sh
- gw0h touches only lib.sh — fully independent, safe for parallel execution
- No user-facing behavior changes (hooks are invisible when working correctly)

## Parallelism Structure

```
Lane 1 (lib.sh):     gw0h ─────────────────── done
Lane 2 (hooks):       8t5l ──→ azlo ────────── done
                                                  ↓
                                           merge → test → ship
```

**Lane 1** (Codex agent): Simplify escape_for_json in lib.sh
**Lane 2** (Claude direct or Codex sequential): Fix sentinel bug, then narrow triggers

## Key Decisions

- **Sentinel location**: `/tmp/clavain-stop-<SESSION_ID>` — ephemeral, auto-cleans on reboot
- **Both hooks check the sentinel**: First hook to fire writes it, second hook sees it and exits
- **Opt-out mechanism**: Check for `.claude/clavain.no-autocompound` file (not env var — persists across sessions)
- **Throttle**: Timestamp-based sentinel `/tmp/clavain-compound-last-<SESSION_ID>`, skip if <5 minutes old
- **escape_for_json simplification**: Remove the for-loop, keep only the explicit char replacements (\\, ", \b, \f, \n, \r, \t). Control chars 1-7, 11, 14-31 never appear in markdown content injected by hooks.

## Open Questions

None — all 3 beads have clear specifications from prior review analysis.

## Next

Run `/clavain:write-plan` to create the implementation plan with Codex dispatch structure.
