---
name: execute-plan
description: Execute plan in batches with review checkpoints
---

> **When to use vs `/work`:** Use `/execute-plan` for multi-step plans with architect review checkpoints between batches. Use `/work` for autonomous feature execution with quality checks.

<BEHAVIORAL-RULES>
1. **Execute tasks in order.** No skipping, reordering, or parallelizing unless plan explicitly marks tasks independent.
2. **Write output to files, read from files.** Every task producing code/artifacts MUST write to disk.
3. **Stop at checkpoints for user approval.** Batch review checkpoints are mandatory — never auto-approve.
4. **Halt on failure.** Stop immediately on failure; report what failed, what succeeded, and options. No silent retry or skip.
5. **Local agents by default.** Use Task tool for dispatch. External agents (Codex, interserve) require explicit user opt-in.
6. **Never enter plan mode autonomously.** The plan already exists. Stop and ask if scope changes mid-execution.
</BEHAVIORAL-RULES>

**Before starting execution**, enforce the gate and record phase transition:
```bash
BEAD_ID=$(clavain-cli infer-bead "<plan_file_path>")
if ! clavain-cli enforce-gate "$BEAD_ID" "executing" "<plan_file_path>"; then
    echo "Gate blocked: run /interflux:flux-drive on the plan first, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop — do NOT proceed
fi
clavain-cli advance-phase "$BEAD_ID" "executing" "Executing: <plan_file_path>" "<plan_file_path>"
```

Invoke the `clavain:executing-plans` skill and follow it exactly.
