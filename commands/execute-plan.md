---
name: execute-plan
description: Execute plan in batches with review checkpoints
---

> **When to use this vs `/work`:** Use `/execute-plan` for detailed, multi-step implementation plans where you want batch execution with architect review checkpoints between batches. Use `/work` for shipping complete features from a spec or plan where you want autonomous execution with quality checks.

<BEHAVIORAL-RULES>
These rules are non-negotiable for this orchestration command:

1. **Execute tasks in order.** Do not skip, reorder, or parallelize tasks unless the plan explicitly marks them as independent. Each task's output feeds into later tasks.
2. **Write output to files, read from files.** Every task that produces code or artifacts MUST write to disk. Later tasks and review checkpoints read from files, not from conversation context.
3. **Stop at checkpoints for user approval.** Batch review checkpoints between task groups are mandatory. Never auto-approve on behalf of the user.
4. **Halt on failure and present error.** If a task fails (test failure, gate block, tool error), stop immediately. Report what failed, what succeeded before it, and what the user can do. Do not retry silently or skip the failed task.
5. **Local agents by default.** Use local subagents (Task tool) for dispatch. External agents (Codex, interserve) require explicit user opt-in or an active interserve-mode flag. Never silently escalate to external dispatch.
6. **Never enter plan mode autonomously.** Do not call EnterPlanMode during execution. The plan already exists. If scope changes mid-execution, stop and ask the user.
</BEHAVIORAL-RULES>

**Before starting execution**, enforce the gate and record the phase transition:
```bash
BEAD_ID=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-bead "<plan_file_path>")
if ! "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" enforce-gate "$BEAD_ID" "executing" "<plan_file_path>"; then
    echo "Gate blocked: run /interflux:flux-drive on the plan first, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop and tell user — do NOT proceed to execution
fi
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "$BEAD_ID" "executing" "Executing: <plan_file_path>" "<plan_file_path>"
```

Invoke the clavain:executing-plans skill and follow it exactly as presented to you
