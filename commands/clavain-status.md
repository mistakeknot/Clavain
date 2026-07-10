---
name: clavain-status
description: Unified status view across Clavain, artifact generation, doc drift, and coordination
argument-hint: "[all|clavain|interpath|interwatch|interlock]"
---

# Unified Status

Use this as the canonical status entry point.

## Scope resolution

Read `--scope` (or the first argument) and route accordingly:

- `--scope=clavain` (default): Clavain core + companion presence snapshot.
- `--scope=interpath`: artifact/product status.
- `--scope=interwatch`: doc drift status.
- `--scope=interlock`: multi-agent coordination status.
- `--scope=all` or missing scope: run all available scoped statuses and show one merged report.

## Behavior

1. For `clavain` scope, report:
   - Key dependencies: `clavain`, `interdoc`, `interphase`, `interline`, `interpath`, `interwatch`, `interlock`, `qmd`, `oracle`, `tool-time`.
   - Whether `/clavain:clavain-doctor` checks can be run successfully.
   - Nested subproject repo freshness (when in the Sylveste monorepo): run
     `scripts/nested-repo-freshness.sh --quiet` (or the plugin-cache copy) and
     report any nested plugin repos that are behind upstream, dirty, diverged,
     missing a remote, or on an unexpected branch. Highlight stale critical
     plugins and surface the printed `git -C <dir> pull --ff-only` commands.
2. For each additional scope, execute the delegated command:
   - `interpath`: `/interpath:interpath-status`
   - `interwatch`: `/interwatch:interwatch-status`
   - `interlock`: `/interlock:interlock-status`
3. Keep output short and structured:
   - `PASS` / `WARN` / `FAIL`
   - Immediate next action for each `WARN` or `FAIL`.
4. Include the A:L3 no-touch calibration streak by running:
   ```bash
   clavain-cli calibration-streak status
   ```
   Manual intervention means an explicit `/reflect` calibration, a direct human invocation of a calibration command, or a manual edit to routing/gate/phase calibration thresholds. Record such resets with `clavain-cli calibration-streak record-manual <routing|gate_threshold|phase_cost> <reason>`.

5. Surface the microrouter architecture-decision deferral tier (sylveste-s3z6.19.10) by running:
   ```bash
   bash "$CLAUDE_PLUGIN_ROOT/scripts/microrouter-deferral-status.sh"
   ```
   The script reads the bead's deferral state fields (`deferral_check_in`, `deferral_deadline`, `decision_authority_primary/backup`, `auto_revert_action`, `d2_result`) and prints a `PASS`/`WARN`/`FAIL` section with the active check-in and deadline tier for today's date. It is fail-open and silent when the bead or its deferral fields are unavailable, so omit the microrouter section if the script prints nothing. Treat a `FAIL` (stale check-in, exceeded deadline, or `d2_result=kill-epic`) as an immediate next-action: run `/clavain:route sylveste-s3z6.19.10`.

If a delegated command is missing, add a one-line remediation and continue.
