---
module: Galiana
date: 2026-02-15
problem_type: integration_issue
component: tooling
symptoms:
  - "analyze.py returns 0 findings and empty agent scorecard despite 5 findings.json files existing"
  - "redundant_work_ratio shows null with 0/0 convergent/total"
  - "Advisory 'No flux-drive findings for redundancy analysis' appears when findings exist"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [glob, monorepo, findings, python, path-discovery]
---

# Troubleshooting: Glob Pattern Misses Subproject Files in Monorepo

## Problem
Galiana's `find_findings_files()` found 0 `findings.json` files when run from the Interverse monorepo root, even though 5 files existed under subprojects like `hub/clavain/docs/research/flux-drive/` and `plugins/interkasten/docs/research/flux-drive/`.

## Environment
- Module: Galiana (hub/clavain/galiana/analyze.py)
- Python: 3.x with `glob.glob(recursive=True)`
- Affected Component: KPI analysis — redundant_work_ratio and agent_scorecard
- Date: 2026-02-15

## Symptoms
- `python3 analyze.py` produces valid JSON but with empty findings data
- `redundant_work_ratio.total` = 0 despite flux-drive reviews having been run
- `agent_scorecard` is `{}` despite 15 agents having produced findings

## What Didn't Work

**Direct solution:** The problem was identified on first investigation by checking the glob pattern against actual file paths.

## Solution

The glob pattern assumed `findings.json` would be directly under `$PROJECT_ROOT/docs/research/flux-drive/*/findings.json`. In a monorepo, findings are scattered across subprojects.

**Code changes:**
```python
# Before (broken — only finds files at project root level):
pattern = project_root / "docs" / "research" / "flux-drive" / "**" / "findings.json"

# After (fixed — finds files under any subproject):
pattern = project_root / "**" / "docs" / "research" / "flux-drive" / "**" / "findings.json"
```

The leading `**` allows the glob to match at any depth within the project tree:
- `hub/clavain/docs/research/flux-drive/Clavain/findings.json`
- `plugins/interkasten/docs/research/flux-drive/PRD-MVP/findings.json`

## Why This Works

Python's `glob.glob(pattern, recursive=True)` expands `**` to match zero or more directories. Without the leading `**`, the pattern is anchored to `$PROJECT_ROOT/docs/...` which only works for flat project structures. In Interverse's monorepo layout, each subproject has its own `docs/` directory nested under `hub/`, `plugins/`, or `services/`.

The double `**` (one at the start, one before `findings.json`) handles both:
1. Subproject nesting depth (any number of intermediate dirs)
2. Multiple research topics (each gets its own dir under `flux-drive/`)

## Prevention

- When writing glob patterns for monorepo file discovery, always prefix with `**` to search at any depth
- Test glob patterns against actual file locations: `python3 -c "import glob; print(glob.glob('pattern', recursive=True))"`
- In monorepos, never assume a fixed depth between the project root and the target file structure

## Related Issues

No related issues documented yet.
