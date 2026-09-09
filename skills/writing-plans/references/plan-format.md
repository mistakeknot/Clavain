# Plan format and execution manifests

## Plan Document Header

```markdown
---
artifact_type: plan
bead: <CLAVAIN_BEAD_ID or "none">
stage: design
requirements:
  - F1: <feature name from PRD>
---
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Bead:** <bead_id>
**Goal:** [One sentence]

**Architecture:** [2-3 sentences]

**Tech Stack:** [Key technologies]

**Prior Learnings:** [Relevant docs found. Omit if none.]

---
```

`requirements` links tasks to PRD feature IDs. Omit when no PRD exists.

## Must-Haves Section

After plan header, before first task:

```markdown
## Must-Haves

**Truths** (observable behaviors):
- [User can do X / System responds with Y]

**Artifacts** (files with specific exports):
- [`path/to/file.py`] exports [`function_name`, `class_name`]

**Key Links** (connections where breakage cascades):
- [Component A calls Component B before Component C]
```

Derive by: (1) state goal as outcome not task, (2) list 3-7 user-perspective truths, (3) identify required artifacts per truth, (4) identify key links per artifact. Omit for trivial plans (complexity 1-2). executing-plans validates these after all tasks.

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

<verify>
- run: `pytest tests/path/test.py -v`
  expect: exit 0
- run: `python -c "from src.module import func; print(func('test'))"`
  expect: contains "expected_output"
</verify>
````

`<verify>` rules: place at end of task; `run:` + `expect:`; matchers: `exit 0` or `contains "string"`; omit for pure docs/config tasks. executing-plans runs these automatically.

## Execution Manifest

Save companion `.exec.yaml` alongside the plan. Choose `mode`:

| Plan shape | Mode |
|-----------|------|
| 3+ tasks with declared dependencies | `dependency-driven` |
| All tasks share state or files heavily | `all-sequential` |
| All tasks fully independent | `all-parallel` |
| Mixed with clear stage boundaries | `manual-batching` |

```yaml
version: 1
mode: dependency-driven     # or all-parallel, all-sequential, manual-batching
tier: deep                   # fast or deep
max_parallel: 5
timeout_per_task: 300

stages:
  - name: "Stage Name"
    tasks:
      - id: task-1
        title: "Short task description"
        files: [path/to/file.go]
        depends: []
      - id: task-2
        title: "Another task"
        files: [path/to/other.go]
        depends: [task-1]
        tier: fast             # override; use fast for verify-only tasks
```

Rules: IDs match `task-N`, unique. `depends` is additive to stage barriers. `tier` uses `fast`/`deep`, not model names. Skip manifest for <3 tasks or tightly coupled — executing-plans falls back to direct execution.

## Auto-Manifest Generation

After writing the plan file, count tasks with no inter-dependencies. If 3 or more exist, generate the `.exec.yaml` manifest automatically alongside the plan — do not wait for the user to request it.

**Algorithm:**
1. Scan all tasks in the plan for declared `depends` relationships
2. Group tasks into waves: tasks with no unresolved dependencies go in the first wave; tasks whose dependencies are all in earlier waves go in subsequent waves
3. If wave 1 has 3+ tasks (or total independent tasks ≥ 3 across all waves), write the manifest

**Wave format:**
```yaml
version: 1
mode: dependency-driven     # or all-parallel if all tasks are independent
tier: deep
max_parallel: 5
timeout_per_task: 300

stages:
  - name: "Wave 1 — independent"
    tasks:
      - id: task-1
        title: "Short task description"
        files: [path/to/file.py]
        depends: []
      - id: task-2
        title: "Another task"
        files: [path/to/other.py]
        depends: []
  - name: "Wave 2 — after Wave 1"
    tasks:
      - id: task-3
        title: "Depends on task-1 and task-2"
        files: [path/to/dependent.py]
        depends: [task-1, task-2]
```

When all tasks are fully independent, use `mode: all-parallel` and a single stage. When the manifest is generated, note it in the Execution Handoff step and recommend "Orchestrated Delegation" as the default option.

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits
- Write explicit handoff and acceptance criteria. If verification still needs frontier reasoning, keep frontier involvement and record why; do not manufacture a cheap gauge to justify handoff.

