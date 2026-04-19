# Gate calibration v2

## Summary

Gate threshold calibration now uses a SQLite store (`.clavain/gate.db`) while preserving the `ic gate check` contract through automatic backward-compat JSON export. The data source remains unchanged (`ic gate signals --since-id=<cursor>`), but state is now persisted in `tier_state` and can be updated incrementally by theme-aware windows with concurrency-safe drains.

Reference docs:
- [PRD](../../../docs/prds/2026-04-18-gate-threshold-calibration-v2.md)
- [Brainstorm](../../../docs/plans/2026-04-19-gate-threshold-calibration-v2.md)

## Storage layout

The calibration state is stored in `.clavain/gate.db` with:

- `tier_state`
- `drain_log`
- `signals_cache`

`gate.db` is colocated with `.clavain/gate-tier-calibration.json`, and the command discovers it via the existing `.clavain/intercore.db` walk-up logic.

## Command: `calibrate-gate-tiers`

```bash
clavain-cli calibrate-gate-tiers [--auto] [--dry-run]
```

- `--auto`: marks the drain as automation-originated (`drain_log.invoker='auto'`) so sessions can distinguish SessionEnd runs.
- `--dry-run`: runs fetch + drain but skips v1 JSON regeneration.

Exit behavior:

- `0` on successful drain/export path.
- `2` when no new signals are available.
- `1` on hard failure.

## SessionEnd automation

`hooks/gate-calibration-session-end.sh` runs at SessionEnd and executes:

```bash
clavain-cli calibrate-gate-tiers --auto
```

The hook is registered in `hooks/hooks.json` under `SessionEnd` and is designed to be non-blocking for session shutdown.

## Backward compatibility

After each successful non-dry-run drain, `calibrate-gate-tiers` regenerates:
- `.clavain/gate-tier-calibration.json`

Shape stays compatible with existing users of `ic gate check`.

Migration behavior:

- On first successful run with v1 data present, `gate.db` is created from `.clavain/gate-tier-calibration.json`.
- v1 is archived as `.v1.json.bak` immediately after import.
- Migration is idempotent; subsequent runs do not duplicate rows.

## Algorithm note

See the linked brainstorm section: "Algorithm (v2 on top of v1 formulas)." The v2 path applies theme-aware rolling windows, consecutive-stable promotion, small-n guards, and weighted decay when evaluating transitions.
