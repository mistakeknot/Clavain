# Changelog

## Unreleased

### Added
- Structural goal-cadence (mk-fx3): a completed `/goal` or goal-scale milestone now forces the session's completion message to end with a "Next goal" block. New `goal-completed` signal in `hooks/lib-signals.sh`; new highest-priority tier in `hooks/auto-stop-actions.sh` that blocks the turn with an instruction to run the new `/clavain:next-goal` command, which ranks `bd ready` candidates by leverage (dependent_count, priority, momentum) and emits 2-4 candidates + a recommendation + ready-to-paste `/goal` text. Fail-open: degrades to a bd-free recommendation if beads is unavailable. Per-repo opt-out via `.claude/clavain.no-goalcadence`.

### Changed
- Routing docs: added capability-routing doctrine for frontier-tier sessions — codifies when the frontier model plans/reviews vs. executes, and how Sonnet/Opus split execution and validation.

## 0.6.255

### Changed
- `calibrate-gate-tiers` now uses SQLite-backed state at `.clavain/gate.db` instead of JSON-only storage. Same data source (`ic gate signals`); new per-theme keying, window partitioning at tier change, consecutive-stable precondition (3 windows), small-n safety. Backward-compat JSON regenerated automatically — no consumer changes required. v1 JSON archived as `.v1.json.bak` on first run.
- New `--auto` flag distinguishes SessionEnd-triggered drains from manual `/reflect` invocations (recorded in `drain_log.invoker`).

### Added
- SessionEnd hook `hooks/gate-calibration-session-end.sh` — calibration runs automatically without manual invocation.
