---
name: execute-plan
description: Execute plan in batches with review checkpoints
---

> **When to use this vs `/work`:** Use `/execute-plan` for detailed, multi-step implementation plans where you want batch execution with architect review checkpoints between batches. Use `/work` for shipping complete features from a spec or plan where you want autonomous execution with quality checks.

**Before starting execution**, record the phase transition:
```bash
PHASE_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-phase.sh"
BEAD_ID=$(phase_infer_bead "<plan_file_path>")
phase_set "$BEAD_ID" "executing" "Executing: <plan_file_path>"
```

Invoke the clavain:executing-plans skill and follow it exactly as presented to you
