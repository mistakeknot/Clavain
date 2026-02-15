---
name: galiana
description: Discipline analytics — view KPIs, report defects, or reset cache
---

# Galiana Command

<subcommand> #$ARGUMENTS </subcommand>

Route by subcommand:

1. No args: invoke `Skill("galiana")` to render discipline analytics.
2. `report-defect <bead-id>`: collect defect metadata and log it with Galiana.
3. `reset`: delete KPI cache to force regeneration on next run.

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
[[ -z "$GALIANA_LIB" ]] && GALIANA_LIB=$(find ~/projects -path '*/hub/clavain/galiana/lib-galiana.sh' 2>/dev/null | head -1)
if [[ -z "$GALIANA_LIB" ]]; then
  echo "Error: Could not locate galiana/lib-galiana.sh" >&2
  exit 1
fi
source "$GALIANA_LIB"
galiana_log_defect "$BEAD_ID" "$DEFECT_TYPE" "$SEVERITY" "$ESCAPED_GATE" "$REVIEWED_AGENTS" "$MISSED_AGENTS"
```

## reset workflow

If subcommand is `reset`, run:

```bash
rm -f ~/.clavain/galiana-kpis.json
echo "Galiana KPI cache reset. Re-run /clavain:galiana to regenerate."
```
