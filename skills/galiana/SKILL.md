---
name: galiana
description: Show discipline analytics — defect escape rate, override rate, cost metrics, and agent scorecard
---

# Galiana — Discipline Analytics

## Step 1: Run analyzer

```bash
GALIANA_SCRIPT=$(find ~/.claude/plugins/cache -path '*/clavain/*/galiana/analyze.py' 2>/dev/null | head -1)
[[ -z "$GALIANA_SCRIPT" ]] && GALIANA_SCRIPT=$(find ~/projects -path '*/os/clavain/galiana/analyze.py' 2>/dev/null | head -1)
```

If found: `python3 "$(dirname "$(dirname "$GALIANA_SCRIPT")")/galiana/analyze.py"`

If not found: explain Galiana is not installed and stop.

## Step 2: Read KPI cache

Read `~/.clavain/galiana-kpis.json`. If missing or no KPI payload, show a getting-started message explaining KPI events come from disciplined review/testing workflows and defect logging.

## Step 3: Present results

```text
Galiana — Discipline Analytics
════════════════════════════════
Period: YYYY-MM-DD to YYYY-MM-DD
Beads shipped: N | Events analyzed: N

KPIs (diagnostic-first)
────────────────────────
[worst metric first, healthiest last]
Format: KPI Name: value (numerator/denominator)

Agent Scorecard
────────────────
Agent             Findings  P0  P1
fd-architecture   5         0   2
fd-quality        3         1   1

Advisories
──────────
- [info] ...
- [warn] ...
```

## Topology Experiment Results

If `topology_efficiency.available` is true:

```text
Topology Efficiency (recall vs production)
──────────────────────────────────────────
Task Type      T2    T4    T6    T8    Samples
code_review    0.60  0.85  0.95  0.95  12
```

Highlight the smallest topology achieving >=90% recall ("sweet spot"). If < 20 total experiments: "Data still accumulating."

## Eval Harness Health

If `eval_health.available` is true:

```text
Eval Harness Health
──────────────────────────────────────────
Overall: 85% property pass rate | Avg recall: 0.92 | 20 total runs

Fixture                  Pass Rate  Recall  Runs
synth-sql-injection      1.00       0.95    4
```

Highlight any fixture with `pass_rate < 1.0`. If < 10 total runs: "Limited data."

## Offer drill-down

After report: `Want per-bead analytics? Run Galiana with --bead <id>.`
