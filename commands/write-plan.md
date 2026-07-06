---
name: write-plan
description: Create detailed implementation plan with bite-sized tasks
---

## Progress Tracking

This command is the **Decide** leg of the OODARC loop — it commits to an implementation approach. Display and update:

```
write-plan (OODARC: Decide):
- [ ] Resolve input context (brainstorm/PRD artifacts)
- [ ] Invoke clavain:writing-plans skill
- [ ] Register plan artifact + advance phase to `planned`
```

**Before invoking the skill**, resolve input context:
```bash
brainstorm_path=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "brainstorm" 2>/dev/null) || brainstorm_path=""
prd_path=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "prd" 2>/dev/null) || prd_path=""
```
If `prd_path` exists, read it as primary input. If only `brainstorm_path`, read that. Pass as context to the skill.

Invoke the clavain:writing-plans skill and follow it exactly as presented to you.

**After the plan is saved**, register the artifact and record the phase transition:
```bash
BEAD_ID=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-bead "<plan_file_path>")
clavain-cli set-artifact "$BEAD_ID" "plan" "<plan_file_path>" 2>/dev/null || true
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "$BEAD_ID" "planned" "Plan: <plan_file_path>" "<plan_file_path>"
```

**Then extract and seal the acceptance criteria** (fc5.3 — the validator's rubric):

The plan MUST contain a `## Acceptance Criteria` section: numbered items, each stating one observable, checkable outcome. Prefer machine-checkable items — append a fenced block to an item to make it executable:

```
1. All routing tests pass.
   ```check
   cd core/intercore && go test ./internal/routing/
   ```
```

Extract that section verbatim to `<plan_path minus .md>.criteria.md`, then register and seal it:

```bash
criteria_path="${plan_path%.md}.criteria.md"
awk '/^## Acceptance Criteria/{f=1} f && /^## /&& !/^## Acceptance Criteria/{f=0} f' "$plan_path" > "$criteria_path"
if [[ -s "$criteria_path" ]]; then
  clavain-cli set-artifact "$BEAD_ID" "acceptance-criteria" "$criteria_path"
  bd set-state "$BEAD_ID" "plan_author_model=${CLAUDE_MODEL:-${ANTHROPIC_MODEL:-unknown}}" 2>/dev/null || true
else
  echo "WARNING: plan has no '## Acceptance Criteria' section — validator will have no rubric (doctrine Rule 3)" >&2
fi
```

The seal (`.seal` sidecar) makes the criteria write-once: an escalation-triggered re-plan cannot silently rewrite the standard after seeing why execution failed. Re-sealing requires explicit `CLAVAIN_RESEAL=1`.
