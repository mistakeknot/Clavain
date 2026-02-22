---
name: galiana
description: Discipline analytics — view KPIs, report defects, or reset cache
---

# Galiana Command

<subcommand> #$ARGUMENTS </subcommand>

Route by subcommand:

1. No args: invoke `Skill("galiana")` to render discipline analytics.
2. `report-defect <bead-id>`: collect defect metadata and log it with Galiana.
3. `experiment [--date YYYY-MM-DD] [--topologies T2,T4] [--dry-run]`: run topology shadow experiments.
4. `eval [--topologies T2,T4,T6,T8] [--fixtures PATTERN] [--dry-run] [--no-interbench]`: run property-based agent eval harness against golden fixtures.
5. `reset`: delete KPI cache to force regeneration on next run.

## report-defect workflow

If subcommand is `report-defect <bead-id>`:

1. Require a bead id. If missing, print usage and stop.
2. Ask the user for:
   - `defect_type` (`logic`, `regression`, `integration`, `perf`, `security`)
   - `severity` (`P0`, `P1`, `P2`, `P3`, `P4`)
   - `escaped_gate` (`review`, `testing`, `staging`, `none`)
   - `reviewed_agents` (comma-separated agents that reviewed)
   - `missed_agents` (comma-separated agents that missed)
3. Source `lib-galiana.sh` and call `galiana_log_defect`.

```bash
GALIANA_LIB=$(find ~/.claude/plugins/cache -path '*/clavain/*/galiana/lib-galiana.sh' 2>/dev/null | head -1)
[[ -z "$GALIANA_LIB" ]] && GALIANA_LIB=$(find ~/projects -path '*/os/clavain/galiana/lib-galiana.sh' 2>/dev/null | head -1)
if [[ -z "$GALIANA_LIB" ]]; then
  echo "Error: Could not locate galiana/lib-galiana.sh" >&2
  exit 1
fi
source "$GALIANA_LIB"
galiana_log_defect "$BEAD_ID" "$DEFECT_TYPE" "$SEVERITY" "$ESCAPED_GATE" "$REVIEWED_AGENTS" "$MISSED_AGENTS"
```

## experiment workflow

If subcommand is `experiment` (with optional flags):

1. Locate the experiment script:
   ```bash
   EXPERIMENT_SCRIPT=$(find ~/.claude/plugins/cache -path '*/clavain/*/galiana/experiment.py' 2>/dev/null | head -1)
   [[ -z "$EXPERIMENT_SCRIPT" ]] && EXPERIMENT_SCRIPT=$(find ~/projects -path '*/os/clavain/galiana/experiment.py' 2>/dev/null | head -1)
   ```

2. Run it with any provided flags:
   ```bash
   python3 "$EXPERIMENT_SCRIPT" $FLAGS
   ```

3. If `--dry-run` was NOT passed, read `~/.clavain/topology-results.jsonl` and present a summary table of the latest batch:
   ```
   Topology Experiment Results
   ════════════════════════════
   Task          Type        T2    T4    T6    T8
   Clavain       docs        0.60  0.85  0.95  0.95
   PRD-MVP       planning    0.70  0.90  0.90  0.92
   ...
   (recall values shown)
   ```

4. Offer to run LLM synthesis on the results.

## eval workflow

If subcommand is `eval` (with optional flags):

1. Locate the eval script:
   ```bash
   EVAL_SCRIPT=$(find ~/.claude/plugins/cache -path '*/clavain/*/galiana/eval.py' 2>/dev/null | head -1)
   [[ -z "$EVAL_SCRIPT" ]] && EVAL_SCRIPT=$(find ~/projects -path '*/os/clavain/galiana/eval.py' 2>/dev/null | head -1)
   ```

2. Run it with any provided flags:
   ```bash
   python3 "$EVAL_SCRIPT" $FLAGS
   ```

3. Present the output summary table. If any property checks failed (exit code 1), highlight the failures. If regression detected (exit code 2), flag it prominently.

4. If `--dry-run` was NOT passed, read `~/.clavain/eval-results.jsonl` and present the latest results with fixture-level detail.

## reset workflow

If subcommand is `reset`, run:

```bash
rm -f ~/.clavain/galiana-kpis.json
echo "Galiana KPI cache reset. Re-run /clavain:galiana to regenerate."
```
