# Plan: Clavain-2kf — Default to summary.md for file inputs, opt-in for inline annotations

## Context
Currently flux-drive Phase 3 (synthesize.md) writes findings both as a summary section at the top of the INPUT_FILE and as inline `> **Flux Drive** ({agent-name}): ...` annotations throughout the document. This modifies the user's original document with inline noise. For repo reviews, a separate `summary.md` is already the default. This bead aligns file inputs to also default to a standalone summary file, making inline annotations opt-in.

## Current State
- `skills/flux-drive/phases/synthesize.md` Step 3.4 (lines 44-86):
  - **File inputs**: Adds "Flux Drive Enhancement Summary" section at top of INPUT_FILE + inline `> **Flux Drive**` blockquotes per section
  - **Repo reviews**: Writes `{OUTPUT_DIR}/summary.md` (does NOT modify repo files)
- Users have no way to choose between summary-only vs inline annotation modes

## Implementation Plan

### Step 1: Change default for file inputs in synthesize.md
**File:** `skills/flux-drive/phases/synthesize.md`

In Step 3.4, modify the "For file inputs" section:

1. **Default behavior (summary-only)**:
   - Write findings to `{OUTPUT_DIR}/summary.md` (same format as repo reviews)
   - Do NOT modify INPUT_FILE
   - Print: `Summary written to {OUTPUT_DIR}/summary.md`

2. **Opt-in inline mode**:
   - After writing summary.md, ask user via AskUserQuestion:
     ```
     "Would you also like inline annotations added to the original document?"
     Options: ["Yes, add inline annotations", "No, summary only (Recommended)"]
     ```
   - If user opts in, apply the existing inline annotation logic (add Enhancement Summary header + per-section blockquotes to INPUT_FILE)

### Step 2: Update SKILL.md Phase 3 description
**File:** `skills/flux-drive/SKILL.md`

Update the Phase 3 description to reflect:
- Default: standalone summary.md for all input types
- Opt-in: inline annotations for file inputs (user must confirm)

### Step 3: Unify summary format
Both file inputs and repo reviews should produce the same `summary.md` format:
- Enhancement Summary header with agent count and date
- Divergence warning if detected
- Key Findings (top 3-5 with convergence counts)
- Issues to Address checklist (with severity, agent attribution, convergence)
- Improvements Suggested
- Link to individual agent reports in OUTPUT_DIR

## Design Decisions
- **summary.md as default**: Non-destructive. User's document stays clean. They can read findings separately.
- **AskUserQuestion for opt-in**: Explicit consent before modifying user's file. Low friction (one click).
- **Same format for file and repo**: Reduces cognitive load. Users learn one format.
- **Recommended = summary-only**: Inline annotations are noisy for most use cases.

## Files Changed
1. `skills/flux-drive/phases/synthesize.md` — Restructure Step 3.4 to default to summary.md, make inline opt-in
2. `skills/flux-drive/SKILL.md` — Update Phase 3 description

## Estimated Scope
~20-30 lines changed in synthesize.md. Minor update to SKILL.md.

## Acceptance Criteria
- [ ] File input reviews produce `{OUTPUT_DIR}/summary.md` by default
- [ ] INPUT_FILE is NOT modified unless user explicitly opts in
- [ ] User is asked whether to add inline annotations after summary is written
- [ ] Repo reviews are unchanged (already use summary.md)
- [ ] Summary format is consistent between file and repo input types
