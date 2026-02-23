# File-Based Todo Tracking (compact)

Manage work items as markdown files in `todos/` with YAML frontmatter.

## File Naming

`{issue_id}-{status}-{priority}-{description}.md`
- issue_id: sequential (001, 002...), never reused
- status: `pending` | `ready` | `complete`
- priority: `p1` (critical) | `p2` (important) | `p3` (nice-to-have)

## YAML Frontmatter

```yaml
---
status: ready
priority: p1
issue_id: "002"
tags: [performance, database]
dependencies: ["001"]
---
```

## Required Sections

Problem Statement, Findings, Proposed Solutions, Recommended Action, Acceptance Criteria, Work Log.

Template: `assets/todo-template.md`

## Workflows

**Create:** Determine next ID → copy template → fill sections → set status (`pending` needs triage, `ready` pre-approved). Create when >15 min work or needs planning. Act immediately for trivial fixes.

**Triage:** List `*-pending-*.md` → review each → approve (rename to `ready`, fill Recommended Action) or defer.

**Complete:** Verify acceptance criteria → update Work Log → rename to `complete` → check for unblocked work → commit.

**Dependencies:** `dependencies: ["002", "005"]` means blocked by those issues. Check: `grep -l 'dependencies:.*"002"' todos/*.md`

## Quick Commands

```bash
ls todos/*-pending-*.md              # Pending items
ls todos/*-ready-p1-*.md             # P1 ready work
grep -l 'dependencies: \[\]' todos/*-ready-*.md  # Unblocked ready
```

---

*For work log format, integration table, or key distinctions (file-todos vs TodoWrite vs Rails), read SKILL.md.*
