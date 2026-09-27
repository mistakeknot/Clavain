# Task Reviewer Prompt Template

Use this template when dispatching a task reviewer. One seat returns two
verdicts, spec compliance first and then quality. This is a task-scoped gate;
the whole-branch review happens after the last task.

```
Task tool (general-purpose):
  description: "Review Task N (spec + quality)"
  model: [MODEL — REQUIRED: the validation seat resolved through routing]
  prompt: |
    You are reviewing one task's implementation: first whether it matches its
    requirements, then whether it is well-built.

    ## Inputs

    - Task brief (what was requested): [BRIEF_FILE]
    - Global constraints that bind this task: [GLOBAL_CONSTRAINTS]
    - Implementer's report (claims, not facts): [REPORT_FILE]
    - Review package, [BASE_SHA]..[HEAD_SHA]: [DIFF_FILE]

    Read the package once: commit list, stat and diff with context. Do not
    re-run git commands or crawl the codebase. Look outside the diff only to
    check a concrete risk you name (a changed contract, lock order or shared
    state justifies checking call sites). Your review is read-only: never
    touch the working tree, index, HEAD or branches. Do not dispatch
    subagents; review in passes yourself if the diff is large.

    ## Do Not Trust the Report

    Verify every claim against the diff. A stated rationale ("per YAGNI",
    "kept simple") is the implementer grading their own work and never lowers
    a finding's severity.

    ## Tests

    The report carries the test evidence. Do not re-run the suite. Run one
    focused test only for a specific doubt no existing run answers. Warnings
    or noise in reported output are findings. Missing or garbled evidence is
    a gap to report, not grounds to re-run.

    ## Part 1: Spec Compliance

    - **Missing:** requirements skipped or claimed without implementation
    - **Extra:** unrequested features or over-engineering
    - **Misunderstood:** the right feature built the wrong way

    For a batched brief, every listed file needs its hunk. A requirement you
    cannot verify from this diff (unchanged code, cross-task) is a ⚠️ item.

    ## Part 2: Quality

    Separation of concerns, error handling, DRY without premature
    abstraction, edge cases; tests that verify real behavior and cover the
    task's edge cases; files with one responsibility that follow the plan's
    structure; what this change contributed to file growth.

    ## Calibration

    Important means the task cannot be trusted until fixed: wrong or fragile
    behavior, a missed requirement, or damage you would block a merge over
    (duplicated logic blocks, swallowed errors, tests that assert nothing).
    Polish and broader coverage are Minor. If the plan mandates something
    this rubric calls a defect, report it as Important, labeled
    plan-mandated. Cite file:line for every finding.

    ## Output Format

    Begin directly with the verdict; no preamble or narration.

    ### Spec Compliance
    - ✅ Spec compliant | ❌ Issues found: [missing/extra/misunderstood, file:line]
    - ⚠️ Cannot verify from diff: [requirement and what the controller should check]

    ### Strengths
    ### Issues
    #### Critical (Must Fix)
    #### Important (Should Fix)
    #### Minor (Nice to Have)

    ### Assessment
    **Task quality:** [Approved | Needs fixes]
    **Reasoning:** [1-2 sentences]
```

**Placeholders:** `[BRIEF_FILE]` from `scripts/task-brief`; `[GLOBAL_CONSTRAINTS]`
copied verbatim from the plan or spec (exact values, formats, stated
relationships); `[REPORT_FILE]` the implementer's report; `[DIFF_FILE]` the path
`scripts/review-package PLAN_FILE BASE HEAD` printed.
