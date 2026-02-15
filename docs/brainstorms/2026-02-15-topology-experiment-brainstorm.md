# Topology Experiment: Continuous Shadow Testing

**Bead:** iv-7z28
**Date:** 2026-02-15
**Status:** Brainstorm

## What We're Building

A continuous shadow-testing system that re-reviews real flux-drive tasks with fixed agent topologies (2, 4, 6, 8 agents) to empirically determine the optimal agent count per task type. Runs daily as a background batch, comparing shadow results against production reviews.

This answers Oracle's #1 question: "What is the coordination tax? When do more agents hurt? What is the optimal agent count per task type?"

## Why This Approach

### Shadow mode over A/B testing
Production reviews stay untouched — users always get the full dynamic ceiling algorithm. Shadow topologies re-run the same inputs in the background. No risk to production quality, and we accumulate data continuously without remembering to trigger experiments.

### Daily batch over hook-based triggers
Flux-drive reviews can cascade (Stage 1 → expansion → Stage 2). A hook firing mid-cascade would create race conditions. A daily batch scans yesterday's completed reviews cleanly, picks 5 diverse tasks, and runs shadows during quiet hours.

### Automated overlap + LLM synthesis for comparison
Pure finding-overlap scoring gives precision/recall numbers. An LLM synthesis pass catches qualitative differences (e.g., "shadow-8 found an architectural issue no other topology caught"). Best of both: numbers for trends, qualitative insights for topology template design.

## Key Decisions

### 1. Fixed topology definitions (override dynamic ceiling)

| Topology | Agents | Rationale |
|----------|--------|-----------|
| **T2** | fd-architecture, fd-quality | Core structural pair — minimum viable review |
| **T4** | T2 + fd-safety, fd-correctness | Adds trust boundary and data integrity — matches quality-gates defaults |
| **T6** | T4 + fd-performance, fd-user-product | Full cross-cutting coverage — typical flux-drive Stage 1 |
| **T8** | T6 + fd-game-design, data-migration-expert | Maximum coverage — includes specialist agents |

Note: T8 includes domain-specific agents (game-design, data-migration-expert) that may score 0 on many tasks. This is intentional — the experiment measures whether including irrelevant agents adds noise or has no effect.

### 2. Task selection (5 per day)

From yesterday's `findings.json` files, select up to 5 tasks with diversity across:
- **Task type**: infer from the review input (plan doc → planning, diff → code review, etc.)
- **Complexity**: mix of simple (< 5 findings) and complex (> 10 findings) reviews
- **Domain**: prefer variety across detected domains

If fewer than 5 reviews happened yesterday, use all of them.

### 3. Measurement dimensions (per shadow run)

| Metric | Source | Formula |
|--------|--------|---------|
| **Recall** | findings overlap | `production P0/P1 findings also found by shadow / total production P0/P1` |
| **Precision** | findings overlap | `shadow findings that match production / total shadow findings` |
| **Unique discoveries** | findings diff | `shadow findings NOT in production` (may be noise or genuine misses) |
| **Cost** | tool-time events | `total tool calls + tokens for the shadow run` |
| **Time** | wall clock | `shadow run duration in seconds` |
| **Redundancy** | convergence | `findings with convergence > 1 / total findings` |

### 4. Output: topology-results.jsonl

Append one record per shadow run to `~/.clavain/topology-results.jsonl`:

```json
{
  "date": "2026-02-15",
  "task_id": "review-xyz",
  "task_type": "code_review",
  "topology": "T4",
  "agents": ["fd-architecture", "fd-quality", "fd-safety", "fd-correctness"],
  "metrics": {
    "recall": 0.85,
    "precision": 0.90,
    "unique_discoveries": 1,
    "total_findings": 8,
    "p0_findings": 1,
    "p1_findings": 3,
    "cost_tools": 45,
    "cost_tokens_approx": 150000,
    "duration_seconds": 120,
    "redundancy_ratio": 0.25
  },
  "production_baseline": {
    "topology": "dynamic",
    "agents_used": 6,
    "total_findings": 10,
    "p0_findings": 1,
    "p1_findings": 4
  },
  "llm_synthesis": "T4 captured all P0 findings and 3/4 P1 findings. Missed P1 about user flow friction (fd-user-product domain). T4 sufficient for code review tasks."
}
```

### 5. Analysis: derive topology templates

After accumulating ~50 data points (2-3 weeks of daily runs):

1. **Per task type**: plot recall vs. topology for each task type
2. **Diminishing returns curve**: identify where adding agents stops improving recall
3. **Cost efficiency**: compute recall-per-tool-call for each topology × task type
4. **Template derivation**: for each task type, recommend the topology where recall ≥ 90% of T8 at lowest cost

Expected templates (hypothesis to test):
- **Lean (T2)**: docs review, simple refactors
- **Standard (T4)**: code review, bugfix
- **Full (T6)**: planning, complex refactors, security-sensitive work

### 6. Integration with Galiana

The experiment runner writes to `topology-results.jsonl`. Galiana's analyze.py can be extended in v0.2 to:
- Read topology results as an additional data source
- Add a "topology efficiency" KPI to the dashboard
- Surface recommendations: "Based on 50 shadow runs, T4 is sufficient for code reviews (92% recall at 40% cost of T8)"

## Architecture

```
/clavain:galiana experiment          ← Command: trigger daily batch
    ↓
galiana/experiment.py                ← Script: find tasks, run shadows, compare
    ↓
flux-drive with --agents override    ← Shadow runs (fixed topology, not dynamic)
    ↓
~/.clavain/topology-results.jsonl    ← Raw results
    ↓
galiana/analyze.py (v0.2)            ← KPI extension: topology efficiency
```

## Open Questions

1. **How to override flux-drive's dynamic ceiling?** Options: (a) add `--agents` CLI flag to flux-drive, (b) pass agent list via environment variable, (c) create a separate shadow-review command. Decision deferred to planning.

2. **Should shadow runs use the same model tier as production?** Using cheaper models would confound the results (fewer agents might perform worse because of model quality, not agent count). Probably should match production model tier.

3. **How to classify task types automatically?** Options: (a) infer from file types in the review input, (b) tag in findings.json metadata, (c) use the session classification from tool-time. Decision deferred to planning.

4. **What's the minimum sample size for statistical significance?** With 5 tasks/day × 4 topologies = 20 data points/day, we get 100/week. Per task type (5 types), that's ~20/week/type. After 3 weeks, ~60/type — probably sufficient for trends but not for narrow confidence intervals.

5. **Should we test T1 (single agent)?** Could reveal whether even 2 agents are overkill for simple tasks. Low cost to include.

## What This Unlocks

- **iv-4xqu** (adaptive model routing): topology templates feed directly into the routing algorithm — "for this task type, use T4 with these specific agents"
- **iv-spad** (deep tldrs integration): if T2 proves sufficient for docs reviews, tldrs context can replace the 3rd/4th agent's full file reads
- **Flux-drive v2**: replace dynamic ceiling heuristics with empirically-derived templates
