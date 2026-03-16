---
name: triage
description: Triage and categorize findings for the CLI todo system
argument-hint: "[findings list or source type]"
---

- Set /model to Haiku
- Read all pending todos in `todos/`

Process findings one by one, deciding whether to add each to the CLI todo system.

**DO NOT CODE DURING TRIAGE.** For: code review findings, security audit results, performance analysis, any categorized findings needing tracking.

## Step 1: Present Each Finding

```
---
Issue #X: [Brief Title]
Severity: 🔴 P1 (CRITICAL) / 🟡 P2 (IMPORTANT) / 🔵 P3 (NICE-TO-HAVE)
Category: [Security/Performance/Architecture/Bug/Feature/etc.]
Description: [Detailed explanation]
Location: [file_path:line_number]
Problem Scenario: [Step by step]
Proposed Solution: [How to fix]
Estimated Effort: [Small (<2h) / Medium (2-8h) / Large (>8h)]
---
Do you want to add this to the todo list?
1. yes - create todo file
2. next - skip this item
3. custom - modify before creating
```

## Step 2: Handle Decision

**"yes":**

If todo exists (from code review):
- Rename: `{id}-pending-{priority}-{desc}.md` → `{id}-ready-{priority}-{desc}.md`
- Update frontmatter: `status: pending` → `status: ready`

If new todo, filename: `{next_id}-ready-{priority}-{desc}.md`
Priority: 🔴→`p1`, 🟡→`p2`, 🔵→`p3`

YAML frontmatter:
```yaml
---
status: ready
priority: p1
issue_id: "042"
tags: [category, relevant-tags]
dependencies: []
---
```

File body:
```markdown
# [Issue Title]

## Problem Statement
[Description]

## Findings
- [Key discoveries]
- Location: [file_path:line_number]

## Proposed Solutions

### Option 1: [Primary solution]
- **Pros**: [Benefits]
- **Cons**: [Drawbacks]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

## Recommended Action
[Specific action plan]

## Technical Details
- **Affected Files**: [List]
- **Related Components**: [Components]
- **Database Changes**: [Yes/No]

## Resources
- Original finding: [Source]
- Related issues: [If any]

## Acceptance Criteria
- [ ] [Specific criteria]
- [ ] Tests pass
- [ ] Code reviewed

## Work Log

### {date} - Approved for Work
**By:** Claude Triage System
**Actions:**
- Issue approved during triage session
- Status changed from pending → ready

**Learnings:**
- [Context and insights]

## Notes
Source: Triage session on {date}
```

Confirm: "✅ Approved: `{new_filename}` (Issue #{issue_id}) - Status: **ready**"

**"next":** Delete the todo file from `todos/`. Skip to next item.

**"custom":** Ask what to modify → update → present revised → ask again.

## Step 3: Continue Until All Processed

- Process all items one by one
- Track with TodoWrite for visibility
- Don't wait for approval between items

## Step 4: Final Summary

```markdown
## Triage Complete

**Total:** [X] | **Approved (ready):** [Y] | **Skipped:** [Z]

### Approved Todos:
- `042-ready-p1-transaction-boundaries.md` - Transaction boundary issue

### Skipped (Deleted):
- Item #5: [reason]

### Status Changes:
- **Pending → Ready:** frontmatter updated
- **Deleted:** skipped finding files removed
```

Next steps:
```bash
ls todos/*-ready-*.md       # view approved todos
/clavain:resolve             # work on approved items
```

Progress tracking: include `Progress: X/Y completed | ~N min remaining` in each finding header.

---

**Triage rules:**
- Present findings only
- Update todo files (rename, frontmatter, work log)
- DO NOT implement fixes or write code — that's `/clavain:resolve`

---

When done, offer:
```markdown
What would you like to do next?
1. run /clavain:resolve to resolve the todos
2. commit the todos
3. nothing, go chill
```
