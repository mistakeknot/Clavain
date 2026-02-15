# Topology Experiment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Bead:** iv-7z28

**Goal:** Build a continuous shadow-testing system that re-reviews real flux-drive tasks with fixed agent topologies (T2/T4/T6/T8) to determine optimal agent count per task type.

**Architecture:** A standalone Python experiment runner (`galiana/experiment.py`) scans yesterday's production `findings.json` files, dispatches review agents directly via shell (bypassing flux-drive's triage), collects findings into a standardized schema, computes precision/recall against the production baseline, and appends results to `~/.clavain/topology-results.jsonl`. A Galiana command (`/clavain:galiana experiment`) triggers it. No changes to flux-drive — shadow runs are independent.

**Tech Stack:** Python 3 (stdlib only), Bash, Claude Code Task tool (for agent dispatch)

---

### Task 1: Create the Topology Configuration

**Files:**
- Create: `hub/clavain/galiana/topologies.json`

**Step 1: Write topology definitions**

```json
{
  "T2": {
    "agents": ["interflux:review:fd-architecture", "interflux:review:fd-quality"],
    "label": "Core structural pair"
  },
  "T4": {
    "agents": [
      "interflux:review:fd-architecture",
      "interflux:review:fd-quality",
      "interflux:review:fd-safety",
      "interflux:review:fd-correctness"
    ],
    "label": "Trust + data integrity"
  },
  "T6": {
    "agents": [
      "interflux:review:fd-architecture",
      "interflux:review:fd-quality",
      "interflux:review:fd-safety",
      "interflux:review:fd-correctness",
      "interflux:review:fd-performance",
      "interflux:review:fd-user-product"
    ],
    "label": "Full cross-cutting"
  },
  "T8": {
    "agents": [
      "interflux:review:fd-architecture",
      "interflux:review:fd-quality",
      "interflux:review:fd-safety",
      "interflux:review:fd-correctness",
      "interflux:review:fd-performance",
      "interflux:review:fd-user-product",
      "interflux:review:fd-game-design",
      "clavain:review:data-migration-expert"
    ],
    "label": "Maximum coverage"
  }
}
```

**Step 2: Commit**

```bash
git add hub/clavain/galiana/topologies.json
git commit -m "feat(galiana): add fixed topology definitions for experiment"
```

---

### Task 2: Create the Experiment Runner

**Files:**
- Create: `hub/clavain/galiana/experiment.py` (~250 lines)

This is the core script. It:
1. Finds yesterday's production `findings.json` files
2. Selects up to 5 diverse tasks
3. For each task × topology: dispatches agents, collects findings, computes metrics
4. Appends results to `~/.clavain/topology-results.jsonl`

**Step 1: Write the experiment runner**

The runner needs these major functions:

```python
#!/usr/bin/env python3
"""Topology experiment runner for Galiana.

Finds recent production flux-drive reviews, re-runs them with fixed
topologies (T2/T4/T6/T8), and compares results.

Usage:
    python3 experiment.py [--date YYYY-MM-DD] [--topologies T2,T4] [--dry-run]
"""
```

**Function: `find_production_reviews(project_root, target_date)`**
- Glob for `**/docs/research/flux-drive/*/findings.json` (same pattern as analyze.py)
- Filter to reviews matching the target date (`reviewed` field)
- Return list of `(path, parsed_doc)` tuples

**Function: `classify_task_type(review_doc)`**
- Infer task type from the `input` path and findings content:
  - `input` contains "plan" or "PRD" → `planning`
  - `input` is a file path ending in `.md` → `docs`
  - `input` is a directory and findings mention "refactor" → `refactor`
  - findings mention "bug", "regression", "fix" → `bugfix`
  - default → `code_review`

**Function: `select_diverse_tasks(reviews, max_count=5)`**
- Group by task type
- Pick one from each type, then fill remaining slots from largest groups
- Prefer reviews with more findings (more signal to compare against)

**Function: `run_shadow_review(input_path, topology_name, topology_agents, output_dir)`**
- Create a temporary output directory under `~/.clavain/shadow-runs/`
- For each agent in the topology:
  - Build a review prompt: "Review the following for issues. Focus on P0/P1 severity findings. Input: {input_path}. Report findings in this exact JSON format: {schema}"
  - Write prompt to a temp file
  - Dispatch via: `codex exec --full-auto -f prompt_file -C project_dir -o output_file`
  - OR if codex unavailable, print the dispatch command for manual execution
- Parse agent outputs into findings format
- Return collected findings as a dict matching the `findings.json` schema

**Function: `compute_overlap_metrics(shadow_findings, production_findings)`**
- Match shadow findings to production findings by title similarity (fuzzy match: lowercase, strip punctuation, check for substring overlap or >60% word overlap)
- Compute:
  - `recall`: production P0/P1 findings matched by shadow / total production P0/P1
  - `precision`: shadow findings matching production / total shadow findings
  - `unique_discoveries`: shadow findings with no production match
- Return metrics dict

**Function: `run_experiment(project_root, target_date, topology_names, dry_run)`**
- Main orchestrator: find reviews → select tasks → run shadows → compute metrics → append results

**CLI:**
```
python3 experiment.py [--date YYYY-MM-DD] [--topologies T2,T4,T6,T8] [--dry-run] [--project PATH]
```

- `--date`: Target date for finding production reviews (default: yesterday)
- `--topologies`: Comma-separated topology names to test (default: all)
- `--dry-run`: Print what would be done without running agents
- `--project`: Project root for finding findings.json (default: CWD)

**Output:** Append one record per (task, topology) pair to `~/.clavain/topology-results.jsonl`:

```json
{
  "date": "2026-02-15",
  "task_id": "flux-drive/Clavain",
  "task_type": "docs",
  "input": "/root/projects/Clavain",
  "topology": "T4",
  "agents_dispatched": ["fd-architecture", "fd-quality", "fd-safety", "fd-correctness"],
  "agents_completed": ["fd-architecture", "fd-quality", "fd-safety", "fd-correctness"],
  "metrics": {
    "recall": 0.85,
    "precision": 0.90,
    "unique_discoveries": 1,
    "total_findings": 8,
    "p0_findings": 1,
    "p1_findings": 3,
    "duration_seconds": 120,
    "redundancy_ratio": 0.25
  },
  "production_baseline": {
    "agents_used": 6,
    "total_findings": 12,
    "p0_findings": 1,
    "p1_findings": 4
  }
}
```

**Step 2: Verify syntax**

```bash
python3 -c "import py_compile; py_compile.compile('hub/clavain/galiana/experiment.py', doraise=True)"
```

**Step 3: Test with --dry-run**

```bash
python3 hub/clavain/galiana/experiment.py --dry-run --project /root/projects/Interverse/hub/clavain
```

Expected: Lists found reviews and planned shadow runs without dispatching agents.

**Step 4: Commit**

```bash
git add hub/clavain/galiana/experiment.py
git commit -m "feat(galiana): add topology experiment runner"
```

---

### Task 3: Create the Shadow Review Dispatcher

**Files:**
- Create: `hub/clavain/galiana/shadow-review.sh` (~60 lines)

Shell script that dispatches a single review agent against a target input and captures its findings output. Called by `experiment.py` for each agent in a topology.

**Step 1: Write the dispatcher**

```bash
#!/usr/bin/env bash
# shadow-review.sh — dispatch a single review agent and capture findings
#
# Usage: shadow-review.sh <agent_subtype> <input_path> <output_file>
#
# Dispatches the agent via Claude Code Task tool pattern (codex exec),
# captures structured findings output.

set -euo pipefail

AGENT="$1"
INPUT="$2"
OUTPUT="$3"

# Agent display name (strip prefix)
AGENT_NAME="${AGENT##*:}"

PROMPT_FILE=$(mktemp /tmp/shadow-review-XXXXXX.md)

cat > "$PROMPT_FILE" << PROMPT_EOF
You are a code review agent. Review the following input and report findings.

**Input to review:** $INPUT

**Instructions:**
1. Read the input (file or directory)
2. Identify issues by severity: P0 (critical/wrong), P1 (important/should fix), P2 (minor/nice to have)
3. Focus on your domain expertise as $AGENT_NAME

**Output format (JSON only, no other text):**
\`\`\`json
{
  "agent": "$AGENT_NAME",
  "findings": [
    {"severity": "P0", "title": "description", "section": "where"},
    {"severity": "P1", "title": "description", "section": "where"}
  ]
}
\`\`\`
PROMPT_EOF

# Dispatch via codex exec
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
if [[ -z "$DISPATCH" ]]; then
    DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
fi

if [[ -n "$DISPATCH" ]]; then
    bash "$DISPATCH" \
        --prompt-file "$PROMPT_FILE" \
        -C "$(dirname "$INPUT")" \
        --name "shadow-${AGENT_NAME}" \
        -o "$OUTPUT" \
        -s workspace-read \
        --tier fast \
        2>/dev/null || true
else
    echo "WARN: dispatch.sh not found, skipping agent $AGENT_NAME" >&2
fi

rm -f "$PROMPT_FILE"
```

**Step 2: Make executable and commit**

```bash
chmod +x hub/clavain/galiana/shadow-review.sh
git add hub/clavain/galiana/shadow-review.sh
git commit -m "feat(galiana): add shadow review dispatcher script"
```

---

### Task 4: Add Experiment Command to Galiana

**Files:**
- Modify: `hub/clavain/commands/galiana.md` — add `experiment` subcommand

**Step 1: Update the command file**

Add the `experiment` subcommand routing after the existing `reset` section:

```markdown
## experiment workflow

If subcommand is `experiment` (with optional flags):

1. Locate the experiment script:
   ```bash
   EXPERIMENT_SCRIPT=$(find ~/.claude/plugins/cache -path '*/clavain/*/galiana/experiment.py' 2>/dev/null | head -1)
   [[ -z "$EXPERIMENT_SCRIPT" ]] && EXPERIMENT_SCRIPT=$(find ~/projects -path '*/hub/clavain/galiana/experiment.py' 2>/dev/null | head -1)
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
```

**Step 2: Commit**

```bash
git add hub/clavain/commands/galiana.md
git commit -m "feat(galiana): add experiment subcommand to galiana"
```

---

### Task 5: Add Topology Results to Galiana Analyzer

**Files:**
- Modify: `hub/clavain/galiana/analyze.py` — add topology results reading and KPI

**Step 1: Add topology results loader**

Add after the existing `compute_findings_metrics` function:

```python
TOPOLOGY_RESULTS_FILE = CLAVAIN_DIR / "topology-results.jsonl"

def load_topology_results(since: datetime, until: datetime) -> list[dict[str, Any]]:
    """Load topology experiment results from topology-results.jsonl."""
    if not TOPOLOGY_RESULTS_FILE.exists():
        return []
    results = []
    for record in iter_jsonl(TOPOLOGY_RESULTS_FILE):
        date_str = record.get("date", "")
        ts = parse_timestamp(date_str)
        if ts is None:
            continue
        if ts < since or ts > until:
            continue
        results.append(record)
    return results


def compute_topology_efficiency(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-topology recall statistics."""
    if not results:
        return {"available": False, "note": "No topology experiment data yet. Run /clavain:galiana experiment."}

    by_topology: dict[str, list[float]] = defaultdict(list)
    by_task_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for r in results:
        topology = r.get("topology", "unknown")
        recall = r.get("metrics", {}).get("recall")
        task_type = r.get("task_type", "unknown")
        if recall is not None:
            by_topology[topology].append(recall)
            by_task_type[task_type][topology].append(recall)

    summary = {}
    for topo in sorted(by_topology):
        values = by_topology[topo]
        summary[topo] = {
            "avg_recall": round(sum(values) / len(values), 4),
            "samples": len(values),
        }

    breakdown = {}
    for task_type in sorted(by_task_type):
        breakdown[task_type] = {}
        for topo in sorted(by_task_type[task_type]):
            values = by_task_type[task_type][topo]
            breakdown[task_type][topo] = {
                "avg_recall": round(sum(values) / len(values), 4),
                "samples": len(values),
            }

    return {
        "available": True,
        "summary": summary,
        "by_task_type": breakdown,
        "total_experiments": len(results),
    }
```

**Step 2: Wire into run_analysis**

In the `run_analysis` function, after `redundant_work_ratio` computation, add:

```python
    topology_results = load_topology_results(since, until)
    topology_efficiency = compute_topology_efficiency(topology_results)
```

And add to the return dict's `kpis`:

```python
        "kpis": {
            ...existing KPIs...,
            "topology_efficiency": topology_efficiency,
        },
```

**Step 3: Add advisory for topology data**

```python
    if not topology_results:
        advisories.append({
            "level": "info",
            "message": "No topology experiment data. Run /clavain:galiana experiment to start collecting.",
        })
```

**Step 4: Verify**

```bash
python3 -c "import py_compile; py_compile.compile('hub/clavain/galiana/analyze.py', doraise=True)"
python3 hub/clavain/galiana/analyze.py
python3 -m json.tool ~/.clavain/galiana-kpis.json | grep -A5 topology
```

**Step 5: Commit**

```bash
git add hub/clavain/galiana/analyze.py
git commit -m "feat(galiana): add topology efficiency KPI to analyzer"
```

---

### Task 6: Update Galiana Skill to Show Topology Results

**Files:**
- Modify: `hub/clavain/skills/galiana/SKILL.md` — add topology results section

**Step 1: Add topology rendering**

After the Agent Scorecard section in the skill, add:

```markdown
## Topology Experiment Results

If `topology_efficiency.available` is true in the KPI data:

Show a recall heatmap table:

```text
Topology Efficiency (recall vs production)
──────────────────────────────────────────
Task Type      T2    T4    T6    T8    Samples
code_review    0.60  0.85  0.95  0.95  12
planning       0.70  0.90  0.92  0.92  8
docs           0.55  0.80  0.90  0.92  10
refactor       0.65  0.88  0.93  0.94  6
bugfix         0.75  0.92  0.95  0.95  4
```

Highlight the "sweet spot" — the smallest topology that achieves ≥90% recall.

If fewer than 20 total experiments, add note: "Data still accumulating — run more experiments for reliable patterns."
```

**Step 2: Commit**

```bash
git add hub/clavain/skills/galiana/SKILL.md
git commit -m "feat(galiana): add topology results to skill presentation"
```

---

## Verification

After all tasks complete:

1. **Config**: `cat hub/clavain/galiana/topologies.json | python3 -m json.tool` — valid JSON
2. **Experiment dry-run**: `python3 hub/clavain/galiana/experiment.py --dry-run` — lists tasks and topologies
3. **Shadow dispatcher**: `bash -n hub/clavain/galiana/shadow-review.sh` — no syntax errors
4. **Analyzer**: `python3 hub/clavain/galiana/analyze.py` — includes topology_efficiency in output
5. **Command**: galiana.md includes experiment routing
6. **Skill**: SKILL.md includes topology rendering section
