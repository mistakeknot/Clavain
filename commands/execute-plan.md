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

## Progress Tracking

`/execute-plan` is the **Act** leg of the OODARC loop, run in review-gated batches (each checkpoint is a mini Validate). Display and update:

```
execute-plan (OODARC: Act — batched):
- [ ] Enforce gate + record `executing` phase transition
- [ ] Execute batch (≤3 tasks)        (Act)
- [ ] Architect review checkpoint     (Validate — pause for approval)
- [ ] Repeat until plan complete
```

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

**On plan completion** (all tasks executed, final checkpoint approved), record the routing outcome (capability-routing doctrine Rule 7 — silent, fail-open). Skip if `/clavain:quality-gates` ran for this plan — it already recorded the outcome. Set `_executor` to your model tier (`fable`/`opus`/`sonnet`/`haiku`); `_author` to the plan author's tier (from the plan's frontmatter/provenance if recorded, else `unknown`); `_validator` to the tier that validated (`self` when the review checkpoints were the only validation). Count the plan's `<verify>` blocks into `_ct` and how many failed on final run into `_cf`:

```bash
if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib.sh" 2>/dev/null; then
  interspect_root=$(_discover_interspect_plugin 2>/dev/null) || interspect_root=""
  if [[ -n "$interspect_root" ]] && source "${interspect_root}/hooks/lib-interspect.sh" 2>/dev/null; then
    _ctx=$(jq -nc --arg a "${_author}" --arg e "${_executor}" --arg v "${_validator:-self}" \
      --argjson ct "${_ct:-0}" --argjson cf "${_cf:-0}" --arg bead "${BEAD_ID:-}" \
      '{author_model:$a, executor_model:$e, validator_model:$v, criteria_total:$ct, criteria_failed:$cf, pass:($cf==0), escalation_count:0, session_source:"normal", bead:$bead, path:"execute-plan"}')
    _interspect_insert_evidence "${CLAUDE_SESSION_ID:-unknown}" "execute-plan" "plan_execution_outcome" "" "$_ctx" 2>/dev/null || true
  fi
fi
```
