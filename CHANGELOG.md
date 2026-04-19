# Changelog

## Unreleased

### Changed
- `calibrate-gate-tiers` now uses SQLite-backed state at `.clavain/gate.db` instead of JSON-only storage. Same data source (`ic gate signals`); new per-theme keying, window partitioning at tier change, consecutive-stable precondition (3 windows), small-n safety. Backward-compat JSON regenerated automatically — no consumer changes required. v1 JSON archived as `.v1.json.bak` on first run.
- New `--auto` flag distinguishes SessionEnd-triggered drains from manual `/reflect` invocations (recorded in `drain_log.invoker`).

### Added
- SessionEnd hook `hooks/gate-calibration-session-end.sh` — calibration runs automatically without manual invocation.
