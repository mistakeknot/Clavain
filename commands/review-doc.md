---
name: review-doc
description: Quick single-pass document refinement — assess clarity, score quality, fix issues, offer iteration
argument-hint: "[document path]"
---

# /review-doc

Lightweight document review — cheaper and faster than `/flux-drive`. Single-pass refinement for brainstorm outputs, PRDs, plans, or any markdown document.

**Use this** for quick polish before handing off to the next workflow step.
**Use `/flux-drive`** for comprehensive multi-agent quality gates.

## Input

<review_doc_input> #$ARGUMENTS </review_doc_input>

## Step 1: Read the Document

Read the target file. If no argument provided, look for the most recent file in:
1. `docs/brainstorms/*.md` (brainstorm output)
2. `docs/prds/*.md` (PRD)
3. `docs/plans/*.md` (implementation plan)

Report: "Reviewing <filename> (<N> lines)"

## Step 2: Assess

Identify issues in these categories:

- **Unclear** — vague language, undefined terms, ambiguous requirements
- **Unnecessary** — sections that don't contribute to the document's purpose, over-engineering, YAGNI violations
- **Missing** — gaps in requirements, unaddressed edge cases, missing acceptance criteria
- **Structural** — poor organization, redundant sections, missing headers

List the top 5 issues found, ranked by impact.

## Step 3: Score

Rate the document on 4 dimensions (1-5 scale):

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Clarity** | X/5 | Can someone implement this without asking questions? |
| **Completeness** | X/5 | Are edge cases and error paths covered? |
| **Specificity** | X/5 | Are requirements testable and measurable? |
| **YAGNI** | X/5 | Does it avoid premature complexity? (5 = lean and focused) |

**Overall: X/20**

## Step 4: Fix

For each issue from Step 2:

- **Minor issues** (grammar, formatting, structure) → fix directly without asking
- **Substantive issues** (missing requirements, scope changes, architectural decisions) → propose the change and ask for approval

Apply fixes to the document.

## Step 5: Offer Next Action

After fixes are applied:

> Document score: **X/20** (was Y/20 before fixes)
>
> Options:
> 1. **Refine again** — run another pass (recommended if score < 15)
> 2. **Proceed** — hand off to the next workflow step

Cap at 2 refinement rounds. If score is still <12 after 2 rounds, recommend a full `/flux-drive` review instead.
