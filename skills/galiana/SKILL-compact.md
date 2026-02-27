# Galiana Discipline Analytics (compact)

Render Galiana KPIs from local cache in a diagnostic-first report.

## Core Workflow

1. Locate `galiana/analyze.py` in plugin cache, fallback to local checkout.
2. If analyzer is missing, report Galiana is not installed and stop.
3. Run analyzer.
4. Read `~/.clavain/galiana-kpis.json`.
5. If payload is missing, show a brief getting-started note.
6. Render report sections in required order.

## Quick Commands

```bash
GALIANA_SCRIPT=$(find ~/.claude/plugins/cache -path '*/clavain/*/galiana/analyze.py' 2>/dev/null | head -1)
[[ -z "$GALIANA_SCRIPT" ]] && GALIANA_SCRIPT=$(find ~/projects -path '*/os/clavain/galiana/analyze.py' 2>/dev/null | head -1)
python3 "$(dirname "$(dirname "$GALIANA_SCRIPT")")/galiana/analyze.py"
```

## Output Rules

- Render: header -> KPIs (worst to best) -> scorecard -> advisories.
- KPI format: `KPI Name: value (numerator/denominator)`.
- Preserve advisory labels (`[info]`, `[warn]`, `[critical]`).
- If `topology_efficiency.available`: add recall heatmap and smallest topology with `>=90%` recall.
- If `eval_health.available`: add fixture pass/recall table and flag pass rate `< 1.0`.
- Add limited-data notes for <20 topology experiments or <10 eval runs.
- Offer drill-down: `Run Galiana with --bead <id>.`

---

*For full report examples, section templates, and extended handling rules, read SKILL.md.*
