# Flux-Drive Quality Review: Diff Slicing Consolidation Plan

**Reviewed**: 2026-02-14 | **Agent**: fd-quality | **Verdict**: needs-changes

## Findings Index
- P1 | Q-1 | "Step 1" | Inconsistent section heading depth in slicing.md structure
- P1 | Q-2 | "Step 2" | launch.md reference uses wrong step numbering
- P2 | Q-3 | "Step 1" | Missing newlines in markdown spec violates phase file conventions
- P2 | Q-4 | "Step 7" | Test file naming doesn't match target file renaming
- IMP-1 | "Step 1" | Consider more explicit "when to read" guidance in slicing.md structure
- IMP-2 | "Step 5" | SKILL.md update should preserve existing step numbering context
- IMP-3 | "Execution Notes" | Add verification commands to execution notes

Verdict: needs-changes

## Summary

The plan is well-structured with clear consolidation goals and comprehensive coverage of source files. However, there are naming consistency issues in the proposed slicing.md structure, incorrect step numbering in references to launch.md, and minor violations of phase file markdown conventions. The test updates correctly target structural validation but miss a renaming detail. Overall approach is sound — fix the structural and naming issues before execution.

## Issues Found

### Q-1. P1: Inconsistent section heading depth in slicing.md structure

The proposed structure mixes H2 and H3 headings inconsistently within the same logical layer:

```markdown
## Diff Slicing
### When It Activates
### Classification Algorithm
### Per-Agent Diff Construction
### Per-Agent Temp File Construction

## Document Slicing
### When It Activates
### Section Classification
```

But then shifts to H3 under "Synthesis Contracts":

```markdown
## Synthesis Contracts
### Agent Content Access
### Slicing Metadata
### Synthesis Rules
```

**Evidence**: Plan lines 46-106 show "Diff Slicing" and "Document Slicing" as H2 with H3 subsections, then "Synthesis Contracts" also as H2 with H3 subsections. However, "Routing Patterns" (line 24) is H2 with H3 subsections ("Cross-Cutting Agents", "Domain-Specific Agents") — this is correct. But the logical structure treats "Agent Content Access" (synthesis) the same way as "When It Activates" (diff slicing), which have different hierarchical relationships.

**Reference pattern** from launch.md: Phases use H3 for numbered steps (lines 3, 17, 72, 139, etc.), but within each step use H4 for sub-cases ("#### Case 1", line 81). synthesize.md follows the same convention (H3 for Step N.N, H4 for subsections like "#### For file inputs", line 54).

**Fix**: Make all mode-specific subsections consistent. Use H3 for major sections ("Diff Slicing", "Document Slicing", "Synthesis Contracts") and H4 for their subsections ("When It Activates", "Classification Algorithm", etc.). This matches the phase file convention where top-level sections are H3 (steps) and subsections are H4 (cases/details).

Suggested structure:
```markdown
# Content Slicing — Diff and Document Routing

## Overview

## Routing Patterns
### Cross-Cutting Agents
### Domain-Specific Agents

## Overlap Resolution

## Thresholds
### 80% Overlap Threshold
### Safety Override

## Diff Slicing
#### When It Activates
#### Classification Algorithm
#### Per-Agent Diff Construction
#### Per-Agent Temp File Construction

## Document Slicing
#### When It Activates
#### Section Classification
#### Section Heading Keywords
#### Per-Agent Temp File Construction
#### Pyramid Summary
#### Output: section_map

## Synthesis Contracts
#### Agent Content Access
#### Slicing Metadata
#### Synthesis Rules

## Slicing Report Template

## Extending Routing Patterns
```

Alternative: Keep H3 for subsections but then use H4 consistently within each subsection. Either approach works — consistency is the requirement.

### Q-2. P1: launch.md reference uses wrong step numbering

Plan Step 2 (lines 132-163) says "Remove Step 2.1b entirely (lines 247-297)" but the proposed replacement text references "Step 2.1c" which is a different step.

**Evidence**: Plan line 135 says "Remove Step 2.1b entirely", then line 141 says "At the location where Step 2.1b was" and inserts "Step 2.1b: Prepare sliced content". But then line 155 says "At Step 2.1c, simplify to only Cases 1 and 3" — this is step renumbering that isn't documented.

**Reference**: Current launch.md has Step 2.1b (line 247) as "Prepare diff content for agent prompts" and Step 2.1c (line 72) as "Write document to temp file(s)". The plan removes 2.1b entirely and modifies 2.1c, but doesn't clarify whether 2.1c becomes 2.1b or stays 2.1c.

**Fix**: Clarify step renumbering. If Step 2.1b is deleted, does Step 2.1c become the new 2.1b? Or does the plan keep the numbering gap (2.1a → 2.1c)? Most likely, the intent is:
- Old Step 2.1b (diff slicing prep) → deleted
- Old Step 2.1c (temp file construction) → stays as 2.1c but references slicing.md for Cases 2 and 4
- New Step 2.1b (generic slicing trigger) → inserted before 2.1c

Document this renumbering explicitly in the plan: "Insert new Step 2.1b before the existing Step 2.1c (which remains at 2.1c). Delete the old Step 2.1b (diff content prep, lines 247-297)."

### Q-3. P2: Missing newlines in markdown spec violates phase file conventions

The proposed slicing.md structure (plan lines 18-114) shows section headers without blank lines between them in the spec, but the reference phase files use consistent spacing.

**Evidence**: Plan line 24 shows:
```
## Routing Patterns

### Cross-Cutting Agents (always full content)
[Table from diff-routing.md lines 9-17]

### Domain-Specific Agents
```

But reference pattern from launch.md shows blank lines between all major sections (e.g., line 1-2, 139-140).

**Not blocking**: This is a spec formatting issue, not file content. The actual slicing.md should follow phase file conventions (blank line before each H2/H3). The plan spec is just shorthand. Mention in Step 1 verification: "Use blank lines between sections per phase file conventions."

### Q-4. P2: Test file naming doesn't match target file renaming

Plan Step 7 (line 227-237) says "Update `tests/structural/test_diff_slicing.py`" but doesn't address renaming the test file itself.

**Evidence**: The test file is named `test_diff_slicing.py` (from context), but the source file is being renamed from `diff-routing.md` to `slicing.md` and the feature is consolidating both diff AND document slicing. Keeping the test filename as `test_diff_slicing.py` is misleading — it now tests both diff and document slicing from a single file.

**Fix**: Consider renaming the test file to `test_slicing.py` (or `test_content_slicing.py`) to match the new consolidated scope. Update the plan to include:
```
**Rename test file**: `tests/structural/test_diff_slicing.py` → `tests/structural/test_slicing.py`
```

Not a blocker if the test content is updated correctly, but naming consistency improves discoverability.

## Improvements Suggested

### IMP-1: Consider more explicit "when to read" guidance in slicing.md structure

The proposed slicing.md structure (plan lines 18-114) shows content organized by mode (Diff Slicing, Document Slicing, Synthesis Contracts), but doesn't have a "How to Use This File" section that tells readers which sections to read for their use case.

**Rationale**: Phase files like shared-contracts.md start with clear scope ("referenced by launch.md and launch-codex.md"). slicing.md will be referenced from multiple locations (launch.md Step 2.1b, SKILL.md Step 1.2c, synthesize.md Step 3.3). Adding a quick navigation guide at the top would improve usability.

**Suggestion**: Add a "How to Use This File" section after Overview:
```markdown
## How to Use This File

This file is referenced from multiple flux-drive phases:
- **launch.md Step 2.1b**: Read "Diff Slicing" or "Document Slicing" based on INPUT_TYPE
- **SKILL.md Step 1.2c**: Read "Document Slicing → Section Classification"
- **synthesize.md Step 3.3**: Read "Synthesis Contracts" for convergence rules
- **Extending patterns**: Read "Extending Routing Patterns" at the end
```

### IMP-2: SKILL.md update should preserve existing step numbering context

Plan Step 5 (lines 200-218) shows the simplified Step 1.2c text but doesn't show the surrounding context (Steps 1.2a, 1.2b, 1.2d if they exist).

**Rationale**: When modifying a step in a multi-step sequence, confirming the step numbering and flow is unchanged helps catch integration issues. The plan should verify that Step 1.2c is still the correct step number after the update (no insertions/deletions earlier in SKILL.md).

**Suggestion**: Add to Step 5 verification: "Confirm Step 1.2c is still the document section mapping step (no renumbering from previous edits)."

### IMP-3: Add verification commands to execution notes

Plan "Execution Notes" (lines 244-250) describe dependencies but don't include verification commands to confirm the refactoring is correct.

**Rationale**: Pure markdown refactoring is low-risk but high-value verification commands catch regressions. Add grep/count checks to confirm no references to the old file remain and all new references resolve.

**Suggestion**: Add a verification step to Execution Notes:
```bash
# After Step 6 (delete diff-routing.md), verify:
grep -r "diff-routing.md" skills/ config/ tests/ --exclude-dir=.beads --exclude-dir=docs/research
# Should return ONLY test file references (which will be updated in Step 7)

# After Step 7 (update tests), verify:
grep -r "diff-routing.md" skills/ config/ tests/ --exclude-dir=.beads --exclude-dir=docs/research
# Should return ZERO results

# After Step 5 (SKILL.md update), verify slicing.md is referenced:
grep -c "slicing.md" skills/flux-drive/SKILL.md
# Should return 2 (once in line 10 file org, once in Step 1.2c)

# Structural test still passes:
uv run --project tests/ pytest tests/structural/test_slicing.py -v
```

## Convention Adherence

**Phase file naming**: slicing.md matches existing pattern (launch.md, synthesize.md) — good.

**Section structure**: Proposed structure mostly follows phase file conventions (H1 title, H2 major sections, H3 subsections) but has the inconsistency noted in Q-1. Fix that and it's aligned.

**Markdown formatting**: Plan spec doesn't show blank lines between sections but this is expected to be added in actual implementation (phase files use blank lines consistently).

**Cross-references**: Plan correctly uses backtick paths for file references (`phases/slicing.md`, `config/flux-drive/diff-routing.md`) matching existing phase file style.

**Contract definitions**: The "Synthesis Contracts" section follows the pattern from shared-contracts.md (Agent Content Access table, Metadata format, Synthesis Implications) — good consistency.

**Step numbering**: Plan uses "Step N" format matching the project's plan conventions (see other plans in docs/plans/).

## Overall Assessment

Solid consolidation plan with clear scope and comprehensive coverage. The structural issues (heading depth, step numbering ambiguity) are fixable before execution. Test updates are thorough but should include file renaming for consistency. The improvements are optional but would enhance usability. Execute after fixing Q-1 and Q-2.
