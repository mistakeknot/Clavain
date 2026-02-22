---
name: write-plan
description: Create detailed implementation plan with bite-sized tasks
---

Invoke the clavain:writing-plans skill and follow it exactly as presented to you.

**After the plan is saved**, record the phase transition:
```bash
BEAD_ID=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-bead "<plan_file_path>")
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "$BEAD_ID" "planned" "Plan: <plan_file_path>" "<plan_file_path>"
```
