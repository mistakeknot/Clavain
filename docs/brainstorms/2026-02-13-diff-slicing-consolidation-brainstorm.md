# Diff/Document Slicing Consolidation Brainstorm

**Bead:** Clavain-496k
**Phase:** brainstorm (as of 2026-02-14T09:00:36Z)
**Date:** 2026-02-13
**Origin:** fd-architecture self-review P0-2 finding

## Problem Statement

Diff slicing and document slicing are a single conceptual feature ("content routing to agents based on relevance") but the implementation is scattered across 4 files:

1. **`config/flux-drive/diff-routing.md`** (166 lines) — Routing patterns: file globs, hunk keywords, section heading keywords per agent. Also defines cross-cutting agents, 80% threshold, overlap resolution, and document section routing.

2. **`skills/flux-drive/phases/launch.md`** Step 2.1b (lines 247-296) — Slicing algorithm: how to classify files as priority/context, build per-agent diffs, handle edge cases (binary, rename-only, multi-commit). Also Step 2.1c (lines 72-137) — Write per-agent temp files for both diff and document slicing.

3. **`skills/flux-drive/phases/shared-contracts.md`** (lines 53-130) — Convergence adjustment rules: don't count agents that only got context summaries, tag out-of-scope findings, track "Request full hunks" notes, no penalty for silence on context files. Also document slicing contract (lines 88-122).

4. **`skills/flux-drive/phases/synthesize.md`** (lines 177-191) — Slicing report template: per-agent mode/priority/context table, threshold, disagreements, routing improvements, out-of-scope discoveries.

## Current State Analysis

### What each file owns

| File | Responsibility | Lines | Type |
|------|---------------|-------|------|
| diff-routing.md | Pattern definitions (what matches) | 166 | Configuration |
| launch.md | Algorithm (how to slice) | ~75 | Procedure |
| shared-contracts.md | Rules (how slicing affects synthesis) | ~78 | Contract |
| synthesize.md | Reporting (how to present results) | ~14 | Template |

### Why this hurts

1. **To understand slicing**, you must read all 4 files and mentally stitch the feature together.
2. **To modify slicing** (e.g., add a new threshold, change convergence rules), you must touch 2-4 files and ensure they stay consistent.
3. **To test slicing**, there's no single surface to validate — patterns, algorithm, rules, and reporting are separate.
4. **Progressive loading claim** makes it worse — developers think phases are independent, but slicing creates hidden coupling between phases.

### What triggered this

The fd-architecture agent's P0-2 finding during the flux-drive self-review (docs/research/flux-drive/SKILL/fd-architecture.md). The finding recommended either:
- **Option A**: Create `config/flux-drive/slicing.md` consolidating all logic
- **Option B**: Extract a `SlicingEngine` abstraction with classify/build/adjust/report interface

## Design Constraints

1. **No executable code** — flux-drive is a prompt-engineering system (markdown instructions for LLMs), not a Python/Bash codebase. There's no actual `SlicingEngine` class to extract. The "module" is a conceptual reference document.
2. **Phase files are still read by orchestrators** — consolidation means the consolidated file gets read once, and phase files reference it instead of inlining the logic.
3. **Backward compatibility** — existing phase files (launch.md, shared-contracts.md, synthesize.md) must still function. The consolidated file should be referenced, not a replacement for entire files.
4. **Two slicing modes** — diff slicing (hunks) and document slicing (sections) share patterns but have different algorithms. The consolidation must handle both.
5. **diff-routing.md is already a config file** — it's the closest thing to a "slicing module" today. Consolidation could expand it or replace it.

## Approaches

### Approach A: Consolidate into `config/flux-drive/slicing.md`

Create a single reference document that collects all slicing logic:

**What moves:**
- diff-routing.md patterns → slicing.md "Routing Patterns" section
- launch.md Step 2.1b algorithm → slicing.md "Diff Slicing Algorithm" section
- launch.md Step 2.1c cases 2+4 → slicing.md "Per-Agent File Construction" section (Step 2.1c cases 1+3 stay — they're "no slicing" cases)
- shared-contracts.md lines 53-130 → slicing.md "Synthesis Rules" section
- synthesize.md lines 177-191 → slicing.md "Slicing Report Template" section

**What stays in original files:**
- launch.md: A 3-line reference: "For diff slicing, read `config/flux-drive/slicing.md`. Apply the algorithm in the 'Diff Slicing Algorithm' section."
- shared-contracts.md: A 2-line reference: "See `config/flux-drive/slicing.md` for diff/document slicing contracts."
- synthesize.md: A 2-line reference: "For the Diff Slicing Report, use the template in `config/flux-drive/slicing.md`."

**Pros:**
- Single file to read for the complete slicing feature
- diff-routing.md is already in config/ — natural home
- Minimal disruption to phase file structure
- Phase files become simpler (lose ~150 lines total across 3 files)

**Cons:**
- Large file (~300 lines) mixing config, algorithm, contracts, and templates
- Still not "testable" in any executable sense
- Reader must know to look in config/ for procedural logic (unusual)

### Approach B: Keep diff-routing.md as config, create `phases/slicing.md` as procedure

Split the concern into two:
- **diff-routing.md** stays as-is: routing patterns (pure config)
- **phases/slicing.md** (new): algorithm + contracts + reporting (procedural reference)

**What moves to phases/slicing.md:**
- launch.md Step 2.1b algorithm
- launch.md Step 2.1c cases 2+4 (per-agent file construction for sliced cases)
- shared-contracts.md slicing contracts (both diff and document)
- synthesize.md slicing report template
- SKILL.md Step 1.2c document section mapping

**What stays:**
- diff-routing.md: untouched (patterns only)
- launch.md: reference to slicing.md for algorithm
- shared-contracts.md: reference to slicing.md for contracts
- synthesize.md: reference to slicing.md for report template
- SKILL.md: reference to slicing.md for section mapping

**Pros:**
- Clean separation: config (what matches) vs procedure (how to slice)
- phases/ is where orchestrators look for procedural instructions
- diff-routing.md stays small and focused
- Consistent with existing phases/ pattern

**Cons:**
- Routing patterns and algorithm are still in different files (you need both to understand slicing)
- Two files instead of one (but better than four)

### Approach C: Merge diff-routing.md INTO the new phases/slicing.md

Everything in one place:

**phases/slicing.md** contains:
1. Routing Patterns (from diff-routing.md)
2. Diff Slicing Algorithm (from launch.md)
3. Document Slicing Algorithm (from SKILL.md Step 1.2c)
4. Per-Agent File Construction (from launch.md Step 2.1c)
5. Synthesis Contracts (from shared-contracts.md)
6. Slicing Report Template (from synthesize.md)

Delete diff-routing.md.

**Pros:**
- One file = complete feature. Maximum consolidation.
- No ambiguity about where slicing logic lives
- Easier to maintain and review changes

**Cons:**
- ~350 lines — large for a single phase file
- Mixing pure config (glob patterns, keywords) with procedural logic
- diff-routing.md deletion requires updating any references to it (SKILL.md, launch.md)

## Recommendation

**Approach C** — Full consolidation into `phases/slicing.md`.

Rationale:
1. The whole point of this bead is "scattered across 4 files — consolidate." Half-measures (A, B) still leave the feature split.
2. 350 lines is manageable — launch.md is already 477 lines. Phase files can be substantial.
3. Mixing config with procedure is acceptable when the config is tightly coupled to the procedure (routing patterns are meaningless without the slicing algorithm that consumes them).
4. The progressive loading architecture already requires reading shared-contracts.md upfront. Adding one more file to the "read first" list is no worse.

### Proposed Structure for phases/slicing.md

```
# Content Slicing — Diff and Document Routing

## Overview
[3-line summary of what slicing does and when it activates]

## Routing Patterns
### Cross-Cutting Agents (always full content)
### Domain-Specific Agents
[Per-agent file patterns + hunk keywords — from diff-routing.md]

## Diff Slicing Algorithm
### When it activates (>= 1000 lines)
### Classification (priority vs context)
### Per-agent diff construction
### Edge cases
[From launch.md Step 2.1b]

## Document Slicing Algorithm
### When it activates (>= 200 lines)
### Section classification
### Per-agent file construction
### Pyramid Summary (>= 500 lines)
[From SKILL.md Step 1.2c + launch.md Step 2.1c cases 2+4]

## Synthesis Contracts
### Agent Content Access (diff + document tables)
### Slicing Metadata
### Convergence Adjustment Rules
### Out-of-Scope Findings
[From shared-contracts.md]

## Slicing Report Template
[From synthesize.md]

## Overlap Resolution + Thresholds
### 80% Threshold
### Safety Override
[From diff-routing.md]

## Extending Routing Patterns
[From diff-routing.md]
```

## Impact Assessment

### Files modified (remove slicing logic, add reference)
- `skills/flux-drive/phases/launch.md` — Remove Step 2.1b (49 lines), simplify Step 2.1c (remove cases 2+4, ~40 lines). Add 3-line reference.
- `skills/flux-drive/phases/shared-contracts.md` — Remove diff/document slicing contracts (lines 53-130, ~78 lines). Add 2-line reference.
- `skills/flux-drive/phases/synthesize.md` — Remove slicing report template (lines 177-191, ~14 lines). Add 2-line reference.
- `skills/flux-drive/SKILL.md` — Remove/simplify Step 1.2c (lines 336-365, ~30 lines). Add reference.

### Files created
- `skills/flux-drive/phases/slicing.md` — ~350 lines (consolidated)

### Files deleted
- `config/flux-drive/diff-routing.md` — Moved into slicing.md

### Net effect
- Before: 4 files, ~333 lines of slicing logic scattered + 166 lines of routing config = ~499 lines across 5 locations
- After: 1 file, ~350 lines. References in 4 files (~10 lines total).
- Lines saved: ~140 (deduplication of contracts that appeared in both diff and document slicing sections)
- Files touched: 6 (1 created, 1 deleted, 4 modified)

### Risk
- **Low**: This is a refactoring of markdown instructions, not executable code. No runtime behavior changes.
- **Test impact**: Update structural tests that count files or check for diff-routing.md existence.
- **Knowledge entries**: Check if any `config/flux-drive/knowledge/` entries reference diff-routing.md paths.

## Open Questions

1. Should `phases/slicing.md` be mentioned in the SKILL.md "read phases/shared-contracts.md first" instruction? (Probably yes — it's a shared concern.)
2. Should the SKILL.md Step 1.2c section mapping stay in SKILL.md or move entirely to slicing.md? The section mapping is part of triage (Phase 1) but its rules come from routing patterns. Leaning toward: keep a 3-line trigger condition in SKILL.md, move the algorithm to slicing.md.
3. Any existing beads/plans that reference diff-routing.md by path? (Need to check.)
