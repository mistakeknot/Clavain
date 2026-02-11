---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
disable-model-invocation: true
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** This should be run in a dedicated worktree (created by brainstorming skill).

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Task Structure

```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
```

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits

## Execution Handoff

After saving the plan, analyze it to recommend an execution approach using `AskUserQuestion`.

### Step 1: Analyze the Plan

Evaluate the plan you just wrote:

| Signal | Points toward |
|--------|--------------|
| <3 tasks, or tasks share files/state | Subagent-Driven |
| Tasks are exploratory/research/architectural | Subagent-Driven |
| User wants manual checkpoints between batches | Parallel Session |
| 3+ independent implementation tasks | Codex Delegation |
| Tasks have clear file lists + test commands | Codex Delegation |
| Codex CLI not available (`which codex` fails) | Subagent-Driven |

### Step 2: Check Codex Availability

Before recommending Codex Delegation, verify: `which codex`

If Codex is not installed, exclude option 3 and recommend between options 1 and 2 only.

### Step 3: Present Choice via AskUserQuestion

Use `AskUserQuestion` with the recommended option listed first (with "(Recommended)"
in the label). Tailor the descriptions to this specific plan.

**Example** (when recommending Codex Delegation for a plan with 5 independent tasks):

```
AskUserQuestion:
  question: "Plan saved to docs/plans/<filename>.md. How should we execute it?"
  header: "Execution"
  options:
    - label: "Codex Delegation (Recommended)"
      description: "5 independent tasks with clear file boundaries — Codex agents
        execute in parallel, Claude reviews. Fastest for this plan shape."
    - label: "Subagent-Driven"
      description: "Fresh Claude subagent per task in this session, with spec +
        quality review after each. Serial but thorough."
    - label: "Parallel Session"
      description: "Open separate session with executing-plans skill. Batch
        execution with human checkpoints between groups."
```

**Example** (when recommending Subagent-Driven for a plan with 2 coupled tasks):

```
AskUserQuestion:
  question: "Plan saved to docs/plans/<filename>.md. How should we execute it?"
  header: "Execution"
  options:
    - label: "Subagent-Driven (Recommended)"
      description: "2 tightly coupled tasks that share state — best handled
        sequentially with full Claude reasoning per task."
    - label: "Codex Delegation"
      description: "Dispatch Codex agents for parallel execution. Less ideal here
        since tasks share files, but possible if split carefully."
    - label: "Parallel Session"
      description: "Open separate session with executing-plans skill. Batch
        execution with human checkpoints."
```

**Key rules for the AskUserQuestion call:**
- Always put the recommended option first with "(Recommended)" in the label
- Write descriptions that reference *this plan's* specific task count, coupling, and characteristics
- If Codex is unavailable, show only 2 options (Subagent-Driven and Parallel Session)
- The "Other" option is automatically available for users who want something different

### Step 4: Execute Based on Choice

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use clavain:subagent-driven-development
- Stay in this session
- Fresh subagent per task + code review

**If Parallel Session chosen:**
- Guide them to open new session in worktree
- **REQUIRED SUB-SKILL:** New session uses clavain:executing-plans

**If Codex Delegation chosen:**
- **REQUIRED SUB-SKILL:** Use clavain:clodex
- Claude stays as orchestrator — planning, dispatching, reviewing, integrating
- Codex agents execute tasks in parallel sandboxes
- Best when tasks are independent, well-scoped, and benefit from parallel execution
- When running under `/lfg`, this step subsumes `/work` — the plan is executed here via Codex, so `/lfg` skips the `/work` step
- The subsequent `/flux-drive` step also dispatches review agents through Codex when clodex mode is active, creating a consistent Codex pipeline
