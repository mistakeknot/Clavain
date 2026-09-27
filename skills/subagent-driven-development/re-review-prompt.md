# Scoped Re-Review Prompt Template

Use this template after each fix round. The re-reviewer verdicts the previous
findings and checks the fix diff for new breakage. It is not a fresh review.

```
Task tool (general-purpose):
  description: "Re-review Task N fix round R"
  model: [MODEL — REQUIRED: the validation seat resolved through routing]
  prompt: |
    You are re-reviewing one task's fix round. Verdict each finding and
    inspect the fix diff, nothing else.

    ## Inputs

    - Task brief: [BRIEF_FILE]
    - Findings under verification: [FINDINGS]
    - Implementer's report (fix reports appended at the end): [REPORT_FILE]
    - Fix package, [FIX_BASE_SHA]..[HEAD_SHA]: [DIFF_FILE]

    Read the package once. Your review is read-only on this checkout. Do not
    dispatch subagents.

    ## Scope

    Verdict every finding. Flag problems the fix itself introduced. An issue
    entirely outside the fix diff is an out-of-scope observation: it does
    not block this task.

    The report's test evidence is an unverified claim: confirm it names the
    covering tests and shows their output, and check it against the diff. Do
    not re-run the suite; run one focused test only for a specific doubt.

    ## Output Format

    Begin directly with the first verdict.

    ### Finding Verdicts
    - **[finding]** — ADDRESSED | NOT ADDRESSED, with file:line evidence.
      Attempted is not addressed: the defect must be gone.

    ### New Breakage in the Fix Diff
    Severity (Critical/Important/Minor) and file:line, or "None".

    ### Out-of-Scope Observations
    Non-blocking; the controller defers them to the ledger. Or "None".

    ### Verdict
    **Fix round:** All findings addressed, no new Critical/Important breakage |
    Findings remain open: [list]
```

**Placeholders:** `[FINDINGS]` the previous review's Critical/Important findings
and spec gaps, verbatim, one per bullet; `[FIX_BASE_SHA]` the head the previous
review saw; `[DIFF_FILE]` the path `scripts/review-package PLAN_FILE FIX_BASE HEAD`
printed.
