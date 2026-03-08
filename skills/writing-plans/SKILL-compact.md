# Writing Plans (compact)

Write implementation plans with bite-sized tasks for engineers with zero codebase context.

## Header (required)

```markdown
# [Feature] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence]
**Architecture:** [2-3 sentences]
**Tech Stack:** [Key technologies]
```

Save to: `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Plan Header Extensions (optional)

**Frontmatter:** Add `requirements:` listing PRD feature IDs (F1, F2) when a PRD exists.

**Must-Haves section** (after Prior Learnings, before tasks): Derive from goal using goal-backward methodology. Three categories: **Truths** (observable behaviors), **Artifacts** (files that must exist with exports), **Key Links** (critical connections). Omit for trivial plans.

## Task Structure

Each step is one action (2-5 minutes). TDD order: write failing test → verify fails → implement → verify passes → commit.

Include: exact file paths, complete code (not "add validation"), exact commands with expected output.

**Verify block** (end of each task, optional): `<verify>` with `- run:` / `expect:` pairs. Two matchers: `exit 0`, `contains "string"`. Executor runs these automatically after task completion.

## Execution Handoff

After saving, analyze and recommend via AskUserQuestion:

| Signal | Points toward |
|--------|--------------|
| <3 tasks or shared files/state | Subagent-Driven |
| Exploratory/research/architectural | Subagent-Driven |
| 3+ independent with clear file lists | Codex Delegation |
| User wants manual checkpoints | Parallel Session |

Check `command -v codex` before recommending Codex. Put recommended option first with "(Recommended)".

**Execute based on choice:**
- Subagent-Driven → `clavain:subagent-driven-development`
- Parallel Session → `clavain:executing-plans`
- Codex Delegation → `clavain:interserve`

---

*For full task template with code examples or detailed execution handoff examples, read SKILL.md.*
