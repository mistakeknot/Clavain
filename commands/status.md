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
   - Whether `/clavain:doctor` checks can be run successfully.
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

If a delegated command is missing, add a one-line remediation and continue.
