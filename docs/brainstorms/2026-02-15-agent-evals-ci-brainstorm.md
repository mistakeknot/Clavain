# Agent Evals as CI Harness

**Bead:** iv-705b
**Phase:** strategized (as of 2026-02-15T09:38:01Z)
**Date:** 2026-02-15
**Status:** Brainstorm

## What We're Building

A property-based agent evaluation harness that runs a curated golden dataset through agent topologies, scores results via interbench, and detects regressions in agent quality. Runs as CI (daily cron + on-push for agent config changes). Answers: did a prompt change reduce bug-catching rate? Did model routing increase slop escapes? Did topology changes degrade recall?

The harness is both a **topology benchmarker** (comparing T2/T4/T6/T8 across task types) and a **regression detector** (comparing current vs baseline when configs change).

## Why This Approach

### Property-based assertions over exact text matching
Agent outputs are non-deterministic — the same review may phrase findings differently on each run. Property-based assertions ("must find >= 1 P0 in security category", "architecture agent should flag coupling") capture the *intent* without requiring exact text. This reduces false positives from model non-determinism while catching genuine quality regressions.

### Interbench for storage over standalone JSONL
Interbench already has run capture, content-addressed artifact storage, scoring (`interbench score`), and comparison (`interbench compare`). Using it avoids reinventing comparison infrastructure. Galiana reads interbench results for KPI dashboard integration.

### Hybrid golden dataset (real + synthetic)
Real curated reviews capture authentic complexity. Synthetic fixtures with planted issues provide precise control over expected findings. Together they cover both breadth (real-world diversity) and depth (known-good expectations).

### Dual CI triggers (cron + on-change)
Daily cron catches gradual drift from model updates. On-push triggers for agent prompt/config changes provide fast feedback. Both write to interbench for unified comparison.

## Key Decisions

### 1. Golden Dataset Structure

Each eval fixture is a directory:
```
galiana/evals/golden/
├── code-review-coupling/
│   ├── input/              # Code to review (files, dirs, or symlinks)
│   ├── meta.json           # Task type, expected properties, tags
│   └── baseline.json       # Best-known findings (for recall scoring)
├── planning-prd-gaps/
│   ├── input/
│   ├── meta.json
│   └── baseline.json
└── ...
```

`meta.json` schema:
```json
{
  "task_type": "code_review",
  "description": "Go service with tight coupling between handler and database layer",
  "expected_properties": [
    {"agent": "fd-architecture", "min_findings": 1, "must_contain_keyword": "coupling"},
    {"agent": "fd-quality", "min_findings": 1},
    {"severity_at_least": "P1", "min_count": 2}
  ],
  "tags": ["go", "architecture", "coupling"],
  "source": "curated"
}
```

`baseline.json` follows the findings.json schema — the "best known" review output from production, used for recall/precision scoring.

### 2. Eval Runner Architecture

`galiana/eval.py` orchestrates:
1. Load golden fixtures from `galiana/evals/golden/`
2. For each fixture × topology: dispatch agents via `shadow-review.sh`
3. Score each run:
   - **Property pass rate**: % of expected_properties satisfied
   - **Recall vs baseline**: P0/P1 findings matched (same fuzzy overlap as experiment.py)
   - **Precision**: shadow findings that match baseline / total shadow findings
   - **False positive rate**: findings with no baseline match and no expected_property match
4. Store results in interbench: `interbench score <run_id> recall 0.85`
5. Compare against previous run: `interbench compare <current> <previous>`
6. Exit non-zero if any property fails or recall drops > 10% from baseline

### 3. CI Integration

Two GitHub Actions workflows:

**Daily benchmark** (`eval-daily.yml`):
- Cron: 4am UTC daily
- Runs full golden dataset × all topologies
- Stores in interbench as `eval-daily-YYYY-MM-DD`
- Compares against previous day's run
- Posts summary to a monitoring channel or issue

**On-change eval** (`eval-on-change.yml`):
- Triggers on push to paths: `agents/**`, `skills/flux-drive/**`, `config/dispatch/**`, `galiana/topologies.json`
- Runs golden dataset × topology affected by the change
- Compares against latest daily baseline
- Fails PR if recall drops > 10% or any P0 property fails

### 4. Scoring Dimensions

| Metric | Formula | Threshold |
|--------|---------|-----------|
| Property pass rate | properties_satisfied / total_properties | >= 80% |
| Recall (P0/P1) | baseline P0/P1 matched / total baseline P0/P1 | >= 85% |
| Precision | shadow matching baseline / total shadow | informational |
| False positive rate | unmatched shadow / total shadow | <= 30% |
| Agent completion rate | agents_completed / agents_dispatched | >= 90% |

### 5. Seeding Strategy (v0.1)

**5 real curated fixtures (re-run for agent attribution):**

Re-run existing review inputs through current flux-drive to get proper agent-attributed findings.json baselines. Only 1 of 5 existing reviews has per-agent attribution — the others predate that feature.

| Fixture | Original Review | Task Type | Input |
|---------|----------------|-----------|-------|
| `real-clavain-docs` | Clavain/ | docs | `/root/projects/Clavain` |
| `real-prd-mvp` | PRD-MVP/ | planning | interkasten PRD-MVP.md |
| `real-strongdm` | strongdm-techniques/ | code_review | pyramid-mode/auto-inject/shift-work docs |
| `real-fd-v2-diff` | fd-v2-validation-diff/ | code_review | fd-v2-validation-diff.patch |
| `real-test-design` | 2026-02-10-test-suite-design/ | planning | test-suite-design plan |

**5 synthetic fixtures (domain-balanced + task-type-diverse):**

| # | Fixture Name | Task Type | Domain | Planted Issue | Must-Find Agent |
|---|-------------|-----------|--------|---------------|-----------------|
| 1 | `synth-sql-injection` | code_review | security | Go handler with unsanitized SQL | fd-safety |
| 2 | `synth-n-plus-one` | code_review | performance | Python service with N+1 query loop | fd-performance |
| 3 | `synth-tight-coupling` | refactor | architecture | Monolith function, 5 responsibilities | fd-architecture |
| 4 | `synth-contradictory-prd` | planning | correctness | PRD with conflicting requirements | fd-correctness |
| 5 | `synth-stale-docs` | docs | quality | README with outdated API examples | fd-quality |

This gives 3 code reviews (different domains), 1 planning, 1 docs, 1 refactor — matching topology experiment task types. Each exercises a different primary agent.

### 6. Interbench Integration

Each eval run creates an interbench run:
```bash
interbench start --command "galiana eval" --args "--topology T4 --fixture code-review-coupling"
# ... agent dispatch happens ...
interbench score $RUN_ID recall 0.85
interbench score $RUN_ID precision 0.90
interbench score $RUN_ID property_pass_rate 1.0
interbench score $RUN_ID false_positive_rate 0.15
interbench finish $RUN_ID
```

Regression detection:
```bash
interbench compare $TODAY_RUN $YESTERDAY_RUN
# Outputs: recall +0.05, precision -0.02, ...
```

## Open Questions

1. **Model tier for evals**: Should evals use the same model tier as production (expensive but accurate) or a fixed tier (cheaper but may diverge from production behavior)?

2. **Fixture maintenance**: As agents improve, baselines need updating. Should baseline updates be automated (accept current output when recall >= 95%) or always manual?

3. **Interbench CLI availability in CI**: Interbench is a Go binary at `infra/interbench/`. CI needs it compiled and available. Should we pre-build and cache, or compile per-run?

4. **Synthetic fixture quality**: How realistic do synthetic fixtures need to be? A 20-line Go file with SQL injection is clear but may not exercise agents the way a 500-line production service would.

5. **Non-determinism budget**: How much run-to-run variance is acceptable before flagging a regression? Model non-determinism means recall may fluctuate ±5% between identical runs.

## What This Unlocks

- **iv-4xqu** (adaptive model routing): eval harness measures whether routing to cheaper models degrades quality
- **iv-spad** (deep tldrs integration): eval harness measures whether tldrs context improves defects-per-token
- **Topology experiment v2**: eval data feeds back into topology template refinement
- **Agent prompt iteration**: safe to refine agent prompts because regressions are caught automatically
