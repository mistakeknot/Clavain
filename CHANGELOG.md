# Changelog

## Unreleased

### Added
- **`scripts/plan-gauge-lint.py` — mechanical gauge dry-run, blocking as step 0 of `/plan-review`.** Applies a plan's own edits to a virtual copy of the tree, then runs the plan's verify commands against the result and compares with the plan's stated expectations. Five codes: `GAUGE001` self-match (a verify forbids text the plan itself writes) · `GAUGE002` unescaped metacharacter in a literal search · `GAUGE003` emitted text breaks the target file's shell quoting · `GAUGE004` a `cargo test` verify that cannot compile the tests it asserts on · `GAUGE005` a verify that runs a build artifact rebuilt only when absent. `--self-test` replays all six defects observed in shadow-work pilot 1 plus a clean control; `--json` for machines. Validated against the two real pilot plans: it flags all four round-1/round-2 strikes before any execution, and a repair clears exactly the repaired class while the unrepaired class survives. Covered by `tests/structural/test_plan_gauge_lint.py` (10 tests).
- Agent-to-skill ports for cross-host use (Kimi Code / Codex): the 6 custom subagents (`plan-reviewer`, `data-migration-expert`, `bug-reproduction-validator`, `codex-delegate`, `pr-comment-resolver`, `ui-polish`) are now also available as skills under `skills/<name>/SKILL.md`, discoverable via `~/.agents/skills/clavain`. Original `agents/*/*.md` definitions are unchanged — Claude Code continues to use them. Skill count 20 → 26.
- Structural goal-cadence (mk-fx3): a completed `/goal` or goal-scale milestone now forces the session's completion message to end with a "Next goal" block. New `goal-completed` signal in `hooks/lib-signals.sh`; new highest-priority tier in `hooks/auto-stop-actions.sh` that blocks the turn with an instruction to run the new `/clavain:next-goal` command, which ranks `bd ready` candidates by leverage (dependent_count, priority, momentum) and emits 2-4 candidates + a recommendation + ready-to-paste `/goal` text. Fail-open: degrades to a bd-free recommendation if beads is unavailable. Per-repo opt-out via `.claude/clavain.no-goalcadence`.

### Changed
- Routing-table v2 rule 9 upgraded from "gauge review before freeze" to **"gauge DRY-RUN before freeze"**, and the role table's gauge row now names the linter as the mechanical half. Pilot 1 struck out both arms on gauge defects in round 1; those gauges were repaired; round 2 struck out both arms *again*, on a third gauge defect each. Six in total, five of one shape — the plan's emitted text is simultaneously the artifact and an input to a checker the same author wrote. Two frontier-tier authors, a frontier-tier reviewer, and the harness each shipped an instance, while ~60 edits applied byte-exact with zero drift across all four executions. Reading a gauge is not a control for this; executing it is.
- Routing docs: added capability-routing doctrine for frontier-tier sessions — codifies when the frontier model plans/reviews vs. executes, and how Sonnet/Opus split execution and validation.

## 0.6.255

### Changed
- `calibrate-gate-tiers` now uses SQLite-backed state at `.clavain/gate.db` instead of JSON-only storage. Same data source (`ic gate signals`); new per-theme keying, window partitioning at tier change, consecutive-stable precondition (3 windows), small-n safety. Backward-compat JSON regenerated automatically — no consumer changes required. v1 JSON archived as `.v1.json.bak` on first run.
- New `--auto` flag distinguishes SessionEnd-triggered drains from manual `/reflect` invocations (recorded in `drain_log.invoker`).

### Added
- SessionEnd hook `hooks/gate-calibration-session-end.sh` — calibration runs automatically without manual invocation.
