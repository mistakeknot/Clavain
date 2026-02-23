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

## Task Structure

Each step is one action (2-5 minutes). TDD order: write failing test → verify fails → implement → verify passes → commit.

Include: exact file paths, complete code (not "add validation"), exact commands with expected output.

## Execution Handoff

After saving, analyze and recommend via AskUserQuestion:

| Signal | Points toward |
|--------|--------------|
| <3 tasks or shared files/state | Subagent-Driven |
| Exploratory/research/architectural | Subagent-Driven |
| 3+ independent with clear file lists | Codex Delegation |
| User wants manual checkpoints | Parallel Session |

Check `which codex` before recommending Codex. Put recommended option first with "(Recommended)".

**Execute based on choice:**
- Subagent-Driven → `clavain:subagent-driven-development`
- Parallel Session → `clavain:executing-plans`
- Codex Delegation → `clavain:interserve`

---

*For full task template with code examples or detailed execution handoff examples, read SKILL.md.*
