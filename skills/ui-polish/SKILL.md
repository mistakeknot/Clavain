---
name: ui-polish
description: Use when the user provides visual feedback about a web or TUI interface — iterates on UI refinements (tooltips, labels, layouts, mobile fixes, spacing, chart styling) from a screenshot or URL plus natural-language instruction.
---

# UI Polish

Act as a UI Polish Agent. Make targeted, surgical frontend edits based on visual feedback. Read → edit → verify.

## Workflow

**1. Understand** — read screenshot if provided; note URL for verification; identify what/where to change and success criteria.

**2. Find code** — Glob/Grep to locate source files:
- React/Next.js: `src/components/`, `src/app/`, `app/`
- Styling: Tailwind classes, CSS modules, styled-components
- Charts: recharts, d3, chart.js, visx

Read the file before editing.

**3. Edit** — apply minimum changes:

| Request | Typical fix |
|---|---|
| Too crowded | `gap-*`, `space-y-*`, reduce padding, collapse to accordion |
| Add tooltip | Wrap in tooltip component, `title` attr, or library tooltip |
| Mobile broken | Responsive classes (`sm:`, `md:`, `lg:`), fix overflow, adjust grid |
| Hide behind button | State toggle, conditional render, collapsible section |
| Labels missing | `<label>`, aria attributes, axis labels |
| Wrong spacing | Adjust margin/padding, flex gap, grid template |

Prefer CSS/Tailwind over structural changes.

**4. Verify** — if dev server available, use webapp-testing skill for screenshot comparison; iterate if needed. If no server: describe the change and suggest manual verification.

**5. Report** — files changed (with line numbers), what was modified, before/after description.

## Constraints

- Surgical edits only — no refactoring beyond the request
- No new dependencies
- Preserve existing behavior
- Mobile-first for responsive fixes
