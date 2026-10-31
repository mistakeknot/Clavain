---
name: ui-polish
description: Targeted frontend polish — tooltips, labels, layout, spacing, mobile, chart styling — from a screenshot or URL plus a natural-language instruction.
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

**Basics when the edit touches motion or states** (add none unasked; these only keep a requested change from regressing the UI; the `ui-craft` skill has the full bar when installed):
- Give any new transition or animation a stated purpose. Do not animate keyboard-driven or very frequent actions.
- Enter and exit with ease-out, never ease-in. Keep interface transitions under 300ms. Name the properties (`transition-colors`, `transition-transform`), never `transition: all`. Animate `transform` and `opacity` rather than layout properties.
- Start entering elements from about 0.95 scale with zero opacity, not from 0.
- Honor `prefers-reduced-motion` (`motion-reduce:` in Tailwind): keep opacity and color changes, drop travel and scale.
- Check the edit against long text, empty and many-item states before reporting it done.

**4. Verify** — if dev server available, use webapp-testing skill for screenshot comparison; iterate if needed. If no server: describe the change and suggest manual verification.

**5. Report** — files changed (with line numbers), what was modified, before/after description.

## Constraints

- Surgical edits only — no refactoring beyond the request
- No new dependencies
- Preserve existing behavior
- Mobile-first for responsive fixes
