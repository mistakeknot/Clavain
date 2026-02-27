---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same plan structure, task template, and execution handoff protocol. -->

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** This should be run in a dedicated worktree (created by brainstorming skill).

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

**Save execution manifest to:** `docs/plans/YYYY-MM-DD-<feature-name>.exec.yaml` (generated alongside the plan — see "Execution Manifest" section below)

## Step 0: Search Institutional Learnings

Before writing any tasks, spawn a learnings-researcher to surface relevant prior solutions:

1. Launch `Task(subagent_type="interflux:learnings-researcher")` with the feature description/spec as the prompt
2. Read the returned learnings
3. If **strong or moderate** relevance matches found:
   - Add a `## Prior Learnings` section to the plan document header (after Architecture, before the first task)
   - List each relevant learning: file path, key insight, and how it affects the plan
   - Encode any must-know gotchas directly into the relevant task steps (e.g., "Note: see docs/solutions/patterns/wal-protocol-completeness-20260216.md — every write path needs WAL protection")
4. If no relevant learnings found: proceed without mention

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

**Prior Learnings:** [If learnings-researcher found relevant docs, list them here. Otherwise omit this section.]

---
```

## Task Structure

````markdown
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
````

## Execution Manifest

After saving the plan markdown, also generate a companion `.exec.yaml` manifest at the same path (replacing `.md` with `.exec.yaml`). This manifest tells `orchestrate.py` how to dispatch Codex agents for the plan.

**Choose `mode` based on plan analysis:**

| Plan shape | Mode |
|-----------|------|
| 3+ tasks with declared dependencies | `dependency-driven` |
| All tasks share state or files heavily | `all-sequential` |
| All tasks fully independent, no deps | `all-parallel` |
| Mixed, but stages are clear boundaries | `manual-batching` |

**Manifest template:**

```yaml
version: 1
mode: dependency-driven     # or all-parallel, all-sequential, manual-batching
tier: deep                   # default tier: fast or deep
max_parallel: 5              # max concurrent agents (1-10)
timeout_per_task: 300        # seconds

stages:
  - name: "Stage Name"
    tasks:
      - id: task-1
        title: "Short task description"
        files: [path/to/file.go]     # files this task reads/modifies
        depends: []                   # explicit deps (additive to stage barrier)
      - id: task-2
        title: "Another task"
        files: [path/to/other.go]
        depends: [task-1]            # intra-stage dependency
        tier: fast                   # override default tier
```

**Rules:**
- Task IDs must match `task-N` pattern and be unique
- `depends` is additive to stage barriers — every task implicitly depends on ALL tasks from prior stages
- Group tasks into stages by natural workflow phases
- Use `tier: fast` for verification-only tasks (tests, linting)
- The `tier` field uses dispatch.sh values (`fast`/`deep`), NOT model names (`sonnet`/`opus`)
- If the plan has <3 tasks or all tasks are tightly coupled, skip the manifest — the executing-plans skill will fall back to direct execution

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
| 3+ tasks with dependencies + `.exec.yaml` generated | Orchestrated Delegation |
| 3+ independent implementation tasks (no manifest) | Codex Delegation |
| Tasks have clear file lists + test commands | Codex Delegation or Orchestrated |
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

**If Orchestrated Delegation chosen (manifest exists):**
- The executing-plans skill auto-detects the `.exec.yaml` manifest and invokes `orchestrate.py`
- The orchestrator handles dependency ordering, parallel dispatch, output routing between tasks, and failure propagation
- Claude reviews the orchestrator's summary and handles any failures
- Best when tasks have declared dependencies and benefit from mixed sequential/parallel execution

**If Codex Delegation chosen (no manifest):**
- **REQUIRED SUB-SKILL:** Use clavain:interserve
- Claude stays as orchestrator — planning, dispatching, reviewing, integrating
- Codex agents execute tasks in parallel sandboxes
- Best when tasks are independent, well-scoped, and benefit from parallel execution
- When running under `/sprint`, this step subsumes `/work` — the plan is executed here via Codex, so `/sprint` skips the `/work` step
- The subsequent `/flux-drive` step also dispatches review agents through Codex when interserve mode is active, creating a consistent Codex pipeline
