---
name: flux-drive
description: "Intelligent document review — triages relevant agents, launches only what matters in background mode"
user-invocable: true
argument-hint: "[path to file or directory]"
---

Use the `clavain:flux-drive` skill to review the document or directory specified by the user. Pass the file or directory path as context.

**After review completes**, if the reviewed file is in `docs/plans/`, record the phase transition:
```bash
GATES_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
BEAD_ID=$(phase_infer_bead "<reviewed_file_path>")
advance_phase "$BEAD_ID" "plan-reviewed" "Plan reviewed: <reviewed_file_path>" "<reviewed_file_path>"
```
Only set `plan-reviewed` for plan files. Do NOT set for brainstorm, PRD, or code reviews.
