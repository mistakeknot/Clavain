---
name: execute-plan
description: Execute a plan continuously, with a ledger and a final independent review
---

> **When to use vs `/work`:** Use `/execute-plan` for multi-step plans executed task by task against a ledger, with one independent review at the end. Use `/work` for autonomous feature execution with quality checks.

<BEHAVIORAL-RULES>
1. **Execute tasks in order.** No skipping, reordering, or parallelizing unless plan explicitly marks tasks independent.
2. **Write artifacts to disk.** Later tasks and the validator read files, not chat.
3. **Execute continuously.** Do not pause between tasks. Stop only for the skill's stop list; a checkpoint the plan or user requires is on it and is never auto-approved.
4. **Never paper over failure.** A failing task records nothing in the ledger. Fix it within scope, or stop and report what failed, what succeeded, and options. No silent retry or skip.
5. **Executors resolve through the role table.** Offload spawns take their backend and model from `ic route dispatch --role`; naming a backend or model by hand is an override the plan declares.
6. **Never enter plan mode autonomously.** The plan already exists. A scope change mid-execution is a stop, not a ruling.
</BEHAVIORAL-RULES>

## Progress Tracking

`/execute-plan` is the **Act** leg of the OODARC loop, closed by one independent review (Validate). Display and update:

```
execute-plan (OODARC: Act — continuous):
- [ ] Enforce gate + record `executing` phase transition
- [ ] Execute each task, ledgering it    (Act)
- [ ] Final independent review + fixes   (Validate)
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

Invoke the `clavain:executing-plans` skill and follow it exactly. For offload runs (a fresh-context executor subagent plus a separate validator subagent), the executor and validator contracts are in `${CLAUDE_PLUGIN_ROOT}/skills/executing-plans/references/pattern-f-contracts.md`.

**On plan completion** (all tasks executed, final review resolved), record the routing outcome (capability-routing doctrine Rule 7 — silent, fail-open). Skip if `/clavain:quality-gates` ran for this plan — it already recorded the outcome. Set `_executor` to your model tier (`opus`/`sonnet`/`haiku`); `_author` to the plan author's tier (from the plan's frontmatter/provenance if recorded, else `unknown`); `_validator` to the final reviewer's tier (`self` only if the review was blocked). Count the plan's `<verify>` blocks into `_ct` and how many failed on final run into `_cf`:

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
