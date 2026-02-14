---
name: write-plan
description: Create detailed implementation plan with bite-sized tasks
---

Invoke the clavain:writing-plans skill and follow it exactly as presented to you.

**After the plan is saved**, record the phase transition:
```bash
export GATES_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
BEAD_ID=$(phase_infer_bead "<plan_file_path>")
advance_phase "$BEAD_ID" "planned" "Plan: <plan_file_path>" "<plan_file_path>"
```
