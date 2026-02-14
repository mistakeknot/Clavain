# Plan: Consolidate Diff/Document Slicing

**Bead:** Clavain-496k
**Phase:** executing (as of 2026-02-14T09:05:51Z)
**PRD:** docs/prds/2026-02-13-diff-slicing-consolidation.md

## Overview

Consolidate flux-drive's scattered slicing logic (4 files, ~499 lines) into a single `phases/slicing.md` file (~350 lines). Pure markdown refactoring — no behavior changes.

## Steps

### Step 1: Create `phases/slicing.md`

Create `skills/flux-drive/phases/slicing.md` with consolidated content from all 4 sources:

**Section structure:**
```
# Content Slicing — Diff and Document Routing

## Overview
[3-line summary: what slicing does, when it activates, two modes]

## Routing Patterns

### Cross-Cutting Agents (always full content)
[Table from diff-routing.md lines 9-17]

### Domain-Specific Agents
[Per-agent sections from diff-routing.md lines 20-101, each with:
 - Priority file patterns (glob syntax)
 - Priority hunk keywords
 Keep exact same content — no rewriting]

## Overlap Resolution
[From diff-routing.md lines 105-108]

## Thresholds
### 80% Overlap Threshold
[From diff-routing.md lines 110-114]

### Safety Override
[From diff-routing.md lines 141-142]

## Diff Slicing

### When It Activates
INPUT_TYPE = diff AND total diff lines >= 1000

### Classification Algorithm
[From launch.md Step 2.1b lines 258-268:
 1. Read routing patterns from this file
 2. Classify each file as priority or context per agent
 3. Cross-cutting agents always full
 4. Domain-specific agents get sliced content
 5. 80% threshold check]

### Per-Agent Diff Construction
[From launch.md lines 269-297:
 Priority section format, Context section format, Edge cases table]

### Per-Agent Temp File Construction
[From launch.md Step 2.1c Case 4 lines 130-137:
 File naming: /tmp/flux-drive-${INPUT_STEM}-fd-safety-${TS}.diff]

## Document Slicing

### When It Activates
INPUT_TYPE = file AND document exceeds 200 lines

### Section Classification
[From SKILL.md Step 1.2c lines 340-356:
 1. Split by ## headings
 2. Classify per agent using routing keywords
 3. Cross-cutting agents full
 4. Safety override
 5. 80% threshold]

### Section Heading Keywords
[From diff-routing.md lines 129-138: heading keyword table]

### Per-Agent Temp File Construction
[From launch.md Step 2.1c Case 2 lines 88-122:
 File naming, priority section format, context summary format, pyramid summary]

### Pyramid Summary (>= 500 lines)
[From SKILL.md lines 350-353]

### Output: section_map
[From SKILL.md lines 358-365]

## Synthesis Contracts

### Agent Content Access
[Combined diff + document tables from shared-contracts.md lines 59-64 and 93-99]

### Slicing Metadata
[From shared-contracts.md lines 66-79 and 103-113:
 slicing_map and section_map YAML examples]

### Synthesis Rules
[From shared-contracts.md lines 81-87 and 115-122:
 - Convergence adjustment
 - Out-of-scope findings
 - Slicing disagreements
 - No penalty for silence]

## Slicing Report Template
[From synthesize.md lines 177-191:
 Per-agent table, threshold, disagreements, routing improvements, out-of-scope discoveries]

## Extending Routing Patterns
[From diff-routing.md lines 149-166]
```

**Source files to read (for exact content):**
- `config/flux-drive/diff-routing.md` (all)
- `skills/flux-drive/phases/launch.md` (Step 2.1b lines 247-297, Step 2.1c lines 88-137)
- `skills/flux-drive/phases/shared-contracts.md` (lines 53-130)
- `skills/flux-drive/phases/synthesize.md` (lines 177-191)
- `skills/flux-drive/SKILL.md` (Step 1.2c lines 336-365)

**Verification:** After creating, check that slicing.md contains:
- All 7 agent names (fd-architecture through fd-game-design)
- "Cross-Cutting Agents" section
- "Domain-Specific Agents" section
- Both "Diff Slicing" and "Document Slicing" algorithms
- "Synthesis Contracts" with convergence rules
- "Slicing Report Template"
- "80% Overlap Threshold"

### Step 2: Update `phases/launch.md`

**Remove:**
- Step 2.1b entirely (lines 247-297, "Prepare diff content for agent prompts")
- Step 2.1c Case 2 content (lines 88-122, document slicing temp files)
- Step 2.1c Case 4 content (lines 130-137, diff slicing temp files)

**Add (replacing removed content):**

At the location where Step 2.1b was:
```markdown
### Step 2.1b: Prepare sliced content for agent prompts

**Skip this step if no slicing is active** (small diff < 1000 lines, or small document < 200 lines).

Read `phases/slicing.md` now. It contains the complete slicing algorithm for both diff and document inputs:
- Classification of files/sections as priority vs context per agent
- Per-agent content construction (priority in full + context summaries)
- Edge cases and thresholds

Apply the appropriate algorithm (Diff Slicing or Document Slicing) based on `INPUT_TYPE`.
```

At Step 2.1c, simplify to only Cases 1 and 3 (no-slicing cases). For sliced cases, reference slicing.md:
```markdown
#### Case 2: File inputs — document slicing active (>= 200 lines)
See `phases/slicing.md` → Document Slicing → Per-Agent Temp File Construction.

#### Case 4: Diff inputs — with per-agent slicing (>= 1000 lines)
See `phases/slicing.md` → Diff Slicing → Per-Agent Temp File Construction.
```

### Step 3: Update `phases/shared-contracts.md`

**Remove:**
- "## Diff Slicing Contract" section (lines 53-87)
- "## Document Slicing Contract" section (lines 88-122)

**Add (replacing removed content):**
```markdown
## Content Slicing Contracts

See `phases/slicing.md` for complete diff and document slicing contracts, including:
- Agent content access rules (which agents get full vs sliced content)
- Slicing metadata format (slicing_map, section_map)
- Synthesis implications (convergence adjustment, out-of-scope findings, no penalty for silence)
```

### Step 4: Update `phases/synthesize.md`

**Remove:**
- Diff Slicing Report section from the report template (lines 177-191)
- The `slicing_map` reference in Step 3.3 line 44

**Add (at the report template location):**
```markdown
### Diff Slicing Report

[Include this section only when INPUT_TYPE = diff AND slicing was active (diff >= 1000 lines).]

See `phases/slicing.md` → Slicing Report Template for the full format.
```

**Keep** the Step 3.3 bullet point about diff slicing awareness (line 44-48) but simplify:
```markdown
6. **Diff slicing awareness**: See `phases/slicing.md` → Synthesis Contracts for convergence adjustment rules when slicing is active.
```

### Step 5: Update `skills/flux-drive/SKILL.md`

**Simplify Step 1.2c** (lines 336-365) to:
```markdown
### Step 1.2c: Document Section Mapping

**Trigger:** `INPUT_TYPE = file` AND document exceeds 200 lines.

Read `phases/slicing.md` → Document Slicing for the classification algorithm. Apply it to split the document into per-agent priority/context sections.

**For documents < 200 lines**, skip this step entirely — all agents receive the full document.

**Output**: A `section_map` per agent, used in Step 2.1c to write per-agent temp files.
```

**Update line 10** ("File organization" instruction) to include slicing.md:
```markdown
**File organization:** This skill is split across phase files for readability. Read `phases/shared-contracts.md` and `phases/slicing.md` first (defines output format, completion signals, and content routing), then read each phase file as you reach it.
```

### Step 6: Delete `config/flux-drive/diff-routing.md`

Delete the file. All content has been moved to `phases/slicing.md`.

**Verification:** Run `grep -r "diff-routing.md"` and confirm only docs/research/ and .beads/ files reference it (historical/read-only).

### Step 7: Update tests

Update `tests/structural/test_diff_slicing.py`:

1. **Rename fixture**: `diff_routing_path` → `slicing_path` pointing to `skills/flux-drive/phases/slicing.md`
2. **Add fixture**: `slicing_content` that reads the file
3. **Update all tests** to validate against slicing.md instead of diff-routing.md
4. **Add new test**: `test_slicing_file_exists` — verifies slicing.md exists
5. **Add new test**: `test_no_diff_routing_exists` — verifies diff-routing.md does NOT exist (regression guard)
6. **Add new test**: `test_slicing_has_both_modes` — verifies both "Diff Slicing" and "Document Slicing" sections
7. **Keep all existing assertion content** (agent names, cross-cutting section, priority patterns, etc.) — just retarget from diff-routing.md content to slicing.md content
8. **Update tests for other files** (launch, shared-contracts, synthesize) to check they contain references to slicing.md instead of inline slicing logic

### Step 8: Check knowledge entries and docs references

1. Scan `config/flux-drive/knowledge/` for any entries referencing diff-routing.md — update paths
2. Scan `docs/research/` and `docs/solutions/` — these are historical, add a note if needed but don't block on them

## Execution Notes

- Steps 1-6 are sequential (each depends on understanding the previous)
- Step 7 (tests) can run after Step 6
- Step 8 is independent
- Total estimated file changes: 7 files modified/created/deleted
- No bash scripts, Python code, or hooks affected — pure markdown refactoring
