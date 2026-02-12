---
name: write-plan
description: Create detailed implementation plan with bite-sized tasks
---

Invoke the clavain:writing-plans skill and follow it exactly as presented to you.

**After the plan is saved**, record the phase transition:
```bash
PHASE_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-phase.sh"
BEAD_ID=$(phase_infer_bead "<plan_file_path>")
phase_set "$BEAD_ID" "planned" "Plan: <plan_file_path>"
```
