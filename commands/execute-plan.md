---
name: execute-plan
description: Execute plan in batches with review checkpoints
---

> **When to use this vs `/work`:** Use `/execute-plan` for detailed, multi-step implementation plans where you want batch execution with architect review checkpoints between batches. Use `/work` for shipping complete features from a spec or plan where you want autonomous execution with quality checks.

**Before starting execution**, enforce the gate and record the phase transition:
```bash
GATES_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
BEAD_ID=$(phase_infer_bead "<plan_file_path>")
if ! enforce_gate "$BEAD_ID" "executing" "<plan_file_path>"; then
    echo "Gate blocked: run /clavain:flux-drive on the plan first, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop and tell user — do NOT proceed to execution
fi
advance_phase "$BEAD_ID" "executing" "Executing: <plan_file_path>" "<plan_file_path>"
```

Invoke the clavain:executing-plans skill and follow it exactly as presented to you
