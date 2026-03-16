---
name: file-todos
description: This skill should be used when managing the file-based todo tracking system in the todos/ directory. It provides workflows for creating todos, managing status and dependencies, conducting triage, and integrating with slash commands and code review processes.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same file naming, YAML schema, and workflow instructions. -->

# File-Based Todo Tracking

`todos/` directory — markdown files with YAML frontmatter for tracking code review feedback, debt, features, and work items.

## File Naming

```
{issue_id}-{status}-{priority}-{description}.md
```
- `issue_id`: sequential 3-digit (001, 002...) — never reused
- `status`: `pending` (needs triage) | `ready` (approved) | `complete` (done)
- `priority`: `p1` (critical) | `p2` (important) | `p3` (nice-to-have)
- `description`: kebab-case

Examples: `001-pending-p1-mailer-test.md`, `002-ready-p1-fix-n-plus-1.md`, `005-complete-p2-refactor-csv.md`

## YAML Frontmatter

```yaml
---
status: ready              # pending | ready | complete
priority: p1               # p1 | p2 | p3
issue_id: "002"
tags: [rails, performance, database]
dependencies: ["001"]      # Issue IDs this is blocked by
---
```

## Required Sections

- **Problem Statement** — what is broken/missing
- **Findings** — investigation results, root cause
- **Proposed Solutions** — multiple options with pros/cons, effort, risk
- **Recommended Action** — filled during triage
- **Acceptance Criteria** — testable checklist
- **Work Log** — chronological record

Optional: Technical Details, Resources, Notes. Use template at `assets/todo-template.md`.

## Workflows

### Creating a Todo

```bash
# 1. Get next ID
ls todos/ | grep -o '^[0-9]\+' | sort -n | tail -1
# 2. Copy template
cp assets/todo-template.md todos/{NEXT_ID}-pending-{priority}-{description}.md
# 3. Fill required sections, add initial Work Log entry
```

**Create todo when:** >15-20 min work, needs research/planning, has dependencies, needs approval, part of larger feature, technical debt.
**Act immediately when:** <15 min, complete context, obvious solution, user requests it.

### Triaging Pending Items

```bash
ls todos/*-pending-*.md
# For each: read Problem + Solutions, decide approve/defer/reprioritize
# Approve: rename pending→ready, update frontmatter, fill Recommended Action
```
Use `/triage` for interactive workflow.

### Managing Dependencies

```bash
# What blocks this todo?
grep "^dependencies:" todos/003-*.md

# What does this todo block?
grep -l 'dependencies:.*"002"' todos/*.md

# Verify blockers complete before starting
for dep in 001 002 003; do
  [ -f "todos/${dep}-complete-*.md" ] || echo "Issue $dep not complete"
done
```

### Work Log Entry Format

```markdown
### YYYY-MM-DD - Session Title
**By:** Claude Code / Developer Name
**Actions:**
- Specific changes (include file:line refs), commands, tests, investigation results
**Learnings:**
- What worked/didn't, patterns discovered, key insights
```

### Completing a Todo

1. Verify all acceptance criteria checked off
2. Add final Work Log entry
3. `mv {file}-ready-{pri}-{desc}.md {file}-complete-{pri}-{desc}.md`
4. Update frontmatter: `status: complete`
5. Check for unblocked work: `grep -l 'dependencies:.*"002"' todos/*-ready-*.md`
6. `git commit -m "feat: resolve issue 002"`

## Quick Reference Commands

```bash
# Next issue ID
ls todos/ | grep -o '^[0-9]\+' | sort -n | tail -1 | awk '{printf "%03d", $1+1}'

# Unblocked p1 work
grep -l 'dependencies: \[\]' todos/*-ready-p1-*.md

# Pending triage
ls todos/*-pending-*.md

# Count by status
for status in pending ready complete; do
  echo "$status: $(ls -1 todos/*-$status-*.md 2>/dev/null | wc -l)"
done

# By tag / priority / full-text
grep -l "tags:.*rails" todos/*.md
ls todos/*-p1-*.md
grep -r "payment" todos/
```

## Integration

| Trigger | Flow |
|---------|------|
| Code review | `/clavain:quality-gates` → findings → `/clavain:triage` → todos |
| PR comments | `/clavain:resolve` → fixes + todos |
| Planning | brainstorm → create todo → work → complete |

## Key Distinctions

- **This system** (`todos/`): markdown files, dev/project tracking, used by humans + agents
- **Rails Todo model** (`app/models/todo.rb`): database model, user-facing feature — unrelated
- **TodoWrite tool**: in-memory session tracking only, not persisted
