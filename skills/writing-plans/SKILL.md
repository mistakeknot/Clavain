---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same plan structure, task template, and execution handoff protocol. -->

# Writing Plans

Write comprehensive implementation plans assuming zero codebase context and questionable taste. Document every file to touch, code, tests, and how to verify. Bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** Run after `/brainstorm` has captured the design.

**Save plan to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`
**Save manifest to:** `docs/plans/YYYY-MM-DD-<feature-name>.exec.yaml`

## Step 0: Prior Art & Institutional Learnings

**Prior art check (REQUIRED):**
```bash
grep -ril "<2-3 keywords>" docs/research/assess-*.md 2>/dev/null
ls interverse/*/CLAUDE.md 2>/dev/null | xargs grep -li "<keywords>" 2>/dev/null
```
If an external tool has an "adopt" verdict, default to integration over reimplementation. Surface to user before proceeding.

**Institutional learnings (deterministic):**
1. Extract 2-4 keywords from the spec
2. Search `docs/solutions/` for matching frontmatter:
   ```bash
   Grep: pattern="(title|tags|module):.*<keyword>" path=docs/solutions/ output_mode=files_with_matches -i=true
   ```
   Also read `docs/solutions/patterns/critical-patterns.md` if it exists.
3. Search past sessions: `cass search "<keywords>" --limit 3 --json --fast-only 2>/dev/null`
4. If matches found: read frontmatter (limit:30 lines), add `## Prior Learnings` section after Architecture, encode gotchas into relevant task steps
5. No matches: proceed without mention
6. Fallback if both unavailable: spawn `Task(subagent_type="interflux:learnings-researcher")`

## Bite-Sized Task Granularity

Each step = one action (2-5 min):
- "Write the failing test" / "Run it to confirm it fails" / "Write minimal implementation" / "Run tests to confirm pass" / "Commit"

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

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits

## Execution Handoff

After saving, analyze the plan and recommend execution via `AskUserQuestion`.

### Step 1: Analyze

| Signal | Points toward |
|--------|--------------|
| <3 tasks, or tasks share files/state | Subagent-Driven |
| Exploratory/research/architectural tasks | Subagent-Driven |
| User wants manual checkpoints | Parallel Session |
| 3+ tasks with deps + `.exec.yaml` generated | Orchestrated Delegation |
| 3+ independent implementation tasks (no manifest) | Codex Delegation |
| Clear file lists + test commands | Codex Delegation or Orchestrated |
| `command -v codex` fails | Subagent-Driven |

### Step 2: Check Codex

`command -v codex` — if unavailable, exclude Codex option, show only Subagent-Driven and Parallel Session.

### Step 3: AskUserQuestion

Put recommended option first with "(Recommended)". Tailor descriptions to this plan's task count and coupling.

**Example (5 independent tasks → Codex Delegation):**
```
AskUserQuestion:
  question: "Plan saved to docs/plans/<filename>.md. How should we execute it?"
  header: "Execution"
  options:
    - label: "Codex Delegation (Recommended)"
      description: "5 independent tasks with clear file boundaries — Codex agents
        execute in parallel, Claude reviews. Fastest for this plan shape."
    - label: "Subagent-Driven"
      description: "Fresh Claude subagent per task, with spec + quality review
        after each. Serial but thorough."
    - label: "Parallel Session"
      description: "Open separate session with executing-plans skill. Batch
        execution with human checkpoints between groups."
```

**Example (2 coupled tasks → Subagent-Driven):**
```
AskUserQuestion:
  question: "Plan saved to docs/plans/<filename>.md. How should we execute it?"
  header: "Execution"
  options:
    - label: "Subagent-Driven (Recommended)"
      description: "2 tightly coupled tasks that share state — best handled
        sequentially with full Claude reasoning per task."
    - label: "Codex Delegation"
      description: "Dispatch Codex agents. Less ideal since tasks share files,
        but possible if split carefully."
    - label: "Parallel Session"
      description: "Open separate session with executing-plans skill."
```

### Step 4: Execute

**Subagent-Driven:** REQUIRED SUB-SKILL: `clavain:subagent-driven-development` — stay in session, fresh subagent per task + code review.

**Parallel Session:** Guide to new session in worktree. REQUIRED SUB-SKILL: `clavain:executing-plans`.

**Orchestrated Delegation (manifest exists):** executing-plans auto-detects `.exec.yaml`, invokes `orchestrate.py` — handles dependency ordering, parallel dispatch, output routing, failure propagation. Claude reviews summary and handles failures.

**Codex Delegation (no manifest):** REQUIRED SUB-SKILL: `clavain:interserve` — Claude orchestrates, Codex agents execute in parallel sandboxes. Under `/sprint`, this subsumes `/work`; `/flux-drive` also dispatches review agents through Codex for a consistent pipeline.
