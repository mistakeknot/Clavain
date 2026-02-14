# fd-architecture Review: Diff Slicing Consolidation

**Bead:** Clavain-496k
**Phase:** brainstorm (architecture review)
**Date:** 2026-02-14
**Reviewer:** fd-architecture agent (Flux-drive Architecture & Design Reviewer)

## Verdict

**Safe to proceed** — the consolidation is architecturally sound. Module boundaries are clean, coupling is intentional, and the reference pattern eliminates the fragmentation without creating new problems.

---

## Summary

The plan consolidates scattered slicing logic (4 files, ~499 lines) into a single `phases/slicing.md` file (~350 lines). This is a pure markdown refactoring — no runtime behavior changes. The consolidation eliminates cross-file coupling for a feature (slicing) that was conceptually unitary but structurally fragmented. The new module boundary is clean: slicing.md owns all classification patterns, algorithms, contracts, and reporting templates. Phase files retain only orchestration logic and reference slicing.md where needed.

**Key strengths:**
1. **Single Responsibility** — slicing.md owns one feature end-to-end (routing patterns → algorithm → contracts → reporting)
2. **Clean Separation** — config (what matches) and procedure (how to slice) are unified in one place, eliminating the artificial split between diff-routing.md (patterns) and launch.md (algorithm)
3. **Progressive Loading Preserved** — phase files still load as needed; slicing.md is explicitly referenced when slicing activates (>= 1000 lines diff, >= 200 lines document)
4. **No Hidden Coupling** — the reference pattern (`See phases/slicing.md → Section Name`) makes dependencies explicit instead of requiring mental stitching across 4 files

**Minor risks addressed:**
- Large file size (~350 lines) is acceptable — launch.md is 477 lines; phase files can be substantial when they own a complete concern
- Mixing config (patterns) with procedure (algorithm) is justified — the patterns are meaningless without the algorithm that consumes them

---

## Findings Index

**P1-1** | "## Boundaries & Coupling" | Reference redirection creates temporal coupling during orchestrator execution
**P2-1** | "## Simplicity & YAGNI" | Per-agent temp file construction appears in two places after consolidation
**P2-2** | "## Pattern Analysis" | SKILL.md Step 1.2c simplification loses signal about document section mapping ownership

Verdict: safe

---

## Issues Found

### P1-1. MODERATE: Reference redirection creates temporal coupling during orchestrator execution

**Evidence:**
- launch.md Step 2.1b becomes a 3-line reference: "Read `phases/slicing.md`. It contains the complete slicing algorithm for both diff and document inputs."
- Orchestrator must read slicing.md mid-execution (during Phase 2 launch) to classify files and construct per-agent diffs
- This is different from shared-contracts.md, which is read upfront at skill entry

**Why this matters:**
The orchestrator (Claude Code session running flux-drive) processes phases sequentially. In the current state, launch.md Step 2.1b contains the classification algorithm inline — the orchestrator has all context needed to execute. After consolidation, the orchestrator must:
1. Reach Step 2.1b
2. Stop and read slicing.md
3. Parse routing patterns + algorithm + edge cases
4. Resume execution with that context

This is **temporal coupling** — Step 2.1b cannot execute without first loading slicing.md. It's not hidden (the reference is explicit), but it's a deviation from the current inline pattern.

**Mitigation:**
The plan already addresses this by adding slicing.md to the "read first" list in SKILL.md line 10 (Step 6 of the plan):
```markdown
**File organization:** This skill is split across phase files for readability. Read `phases/shared-contracts.md` and `phases/slicing.md` first...
```

This moves slicing.md into the upfront-load category, eliminating mid-execution dependency loading.

**Recommendation:**
Accept this mitigation — it's the correct solution. The temporal coupling is resolved by making slicing.md part of the progressive loading contract's "read upfront" set. Phase files then only reference sections within slicing.md, not the entire file.

**Severity rationale:** P1 (not P0) because the plan already includes the mitigation. This is a validation of the design choice, not a blocking issue.

---

## Improvements

### P2-1. Per-agent temp file construction appears in two places after consolidation

**Current plan:**
- slicing.md contains "Per-Agent Temp File Construction" under both "Diff Slicing" and "Document Slicing" sections
- launch.md Step 2.1c references these sections for Cases 2 and 4

**Observation:**
The file construction logic (write priority content + context summaries to `/tmp/flux-drive-${INPUT_STEM}-${AGENT}-${TS}.{ext}`) is identical between diff and document modes — only the content format changes (hunks vs sections). The plan duplicates this procedure in two sections of slicing.md.

**Potential simplification:**
Create a "Per-Agent Temp File Construction" section at the top level of slicing.md (after "Overview"), then specialize the content format within Diff Slicing and Document Slicing sections:

```markdown
# Content Slicing — Diff and Document Routing

## Overview
[...]

## Per-Agent Temp File Construction (Common Pattern)
- File naming: /tmp/flux-drive-${INPUT_STEM}-${AGENT}-${TS}.{ext}
- Cross-cutting agents share one full-content file
- Domain-specific agents get individual files with priority content + context summaries
- Metadata line at top: "[{Mode} slicing active: P priority {units}, C context {units}]"

## Diff Slicing
### Content Format
[Priority section = full hunks, Context section = one-line summaries]

## Document Slicing
### Content Format
[Priority section = full sections, Context section = one-line summaries + pyramid]
```

**Impact:**
- Reduces duplication (~15 lines saved)
- Makes the common pattern (priority/context split, temp file naming) more visible
- Easier to maintain when the file construction logic changes

**Trade-off:**
Adds one more layer of indirection. Readers must understand the common pattern, then apply mode-specific formatting. The current plan's duplication is clearer for linear reading.

**Recommendation:**
**Optional improvement** — the duplication is acceptable given that diff and document slicing are conceptually parallel features. If implemented, keep the common section short (5-7 lines) and clearly signpost the mode-specific sections.

---

### P2-2. SKILL.md Step 1.2c simplification loses signal about document section mapping ownership

**Current plan (Step 5 of the plan):**
```markdown
### Step 1.2c: Document Section Mapping

**Trigger:** `INPUT_TYPE = file` AND document exceeds 200 lines.

Read `phases/slicing.md` → Document Slicing for the classification algorithm. Apply it to split the document into per-agent priority/context sections.

**For documents < 200 lines**, skip this step entirely — all agents receive the full document.

**Output**: A `section_map` per agent, used in Step 2.1c to write per-agent temp files.
```

**Current SKILL.md Step 1.2c (lines 336-365):**
Contains:
- Section extraction algorithm (split by ## headings)
- Classification rules (priority vs context using routing keywords)
- Cross-cutting agent handling (always full)
- Safety override (auth/credentials always priority for fd-safety)
- 80% threshold (skip slicing if >= 80% is priority)
- Pyramid summary rules (>= 500 lines)
- Output format (section_map structure)

**What gets lost:**
The simplified version in the plan removes **all procedural detail** from SKILL.md Step 1.2c. A reader looking at SKILL.md to understand Phase 1 (Triage) will see only "Read slicing.md" without any inline context about what section mapping does or how it integrates with triage scoring.

**Why this matters:**
Step 1.2c is part of Phase 1 (Triage), not Phase 2 (Launch). The triage phase builds a `section_map` output that Phase 2 consumes. Removing all inline context from SKILL.md breaks the "phase files are self-contained procedural narratives" pattern — readers must jump to slicing.md to understand a Phase 1 output.

**Recommendation:**
Keep a 4-5 line summary in SKILL.md Step 1.2c that explains **what** section mapping does and **why** it matters, then reference slicing.md for the **how**:

```markdown
### Step 1.2c: Document Section Mapping

**Trigger:** `INPUT_TYPE = file` AND document exceeds 200 lines.

Section mapping classifies document sections (by ## headings) as priority or context per agent, enabling per-agent content slicing in Phase 2. Cross-cutting agents (fd-architecture, fd-quality) always get the full document. Domain-specific agents get priority sections in full + context summaries.

Read `phases/slicing.md` → Document Slicing for the classification algorithm (routing keywords, safety overrides, 80% threshold).

**Output**: A `section_map` per agent, used in Step 2.1c to write per-agent temp files.
```

**Impact:**
- Preserves inline context for Phase 1 readers
- Makes the triage → launch handoff explicit (section_map is a Phase 1 output, Phase 2 input)
- Keeps the reference to slicing.md for algorithmic details

**Lines added:** +3 (compared to the plan's version), still a net reduction from the current 30 lines.

---

## Pattern Analysis

### Module Boundaries: Clean

**Before consolidation:**
- diff-routing.md: routing patterns (config)
- launch.md: slicing algorithm (procedure)
- shared-contracts.md: synthesis rules (contract)
- synthesize.md: reporting template (template)

This is a **false separation** — the four files collectively define one feature (slicing), but no single file owns the feature. Adding a new routing pattern requires touching diff-routing.md (patterns) + launch.md (classification logic) + shared-contracts.md (convergence rules). The boundaries are artifactual, not semantic.

**After consolidation:**
- slicing.md: routing patterns + algorithm + contracts + reporting (single feature, single file)
- launch.md: orchestration (references slicing.md when slicing activates)
- shared-contracts.md: other contracts (trimming, completion signals, error stubs)
- synthesize.md: synthesis procedure (references slicing.md for slicing report template)

This is a **semantic boundary** — slicing.md owns the slicing feature end-to-end. Phase files own orchestration and reference slicing.md as a dependency. The boundary aligns with the conceptual model (one feature = one module).

**Validation:** The consolidation fixes the scattered ownership problem identified by the fd-architecture agent during the flux-drive self-review.

---

### Coupling: Intentional and Explicit

**Before consolidation:**
- Hidden coupling: launch.md Step 2.1b depends on diff-routing.md patterns, but the dependency is implicit ("Read diff-routing.md" at runtime)
- Hidden coupling: shared-contracts.md synthesis rules depend on diff-routing.md patterns (80% threshold, cross-cutting vs domain-specific classification)
- Hidden coupling: synthesize.md slicing report template depends on slicing_map structure from launch.md

**After consolidation:**
- Explicit coupling: launch.md Step 2.1b references slicing.md ("See `phases/slicing.md` → Diff Slicing → Classification Algorithm")
- Explicit coupling: SKILL.md Step 1.2c references slicing.md ("Read `phases/slicing.md` → Document Slicing")
- Explicit coupling: shared-contracts.md references slicing.md ("See `phases/slicing.md` for diff and document slicing contracts")
- No coupling between slicing.md and other modules — it's a leaf dependency (consumed by phase files, does not consume other modules)

**Validation:** The coupling graph simplifies from a mesh (4 files with circular dependencies) to a tree (3 phase files depend on 1 slicing file). The references are explicit and unidirectional.

---

### Anti-patterns: None Introduced

**God Module Risk:**
slicing.md is ~350 lines covering one feature (content routing to agents). This is **not** a god module — it's a feature module. It's large because the feature has 4 phases (patterns → algorithm → contracts → reporting), not because it's doing multiple things.

Comparison:
- launch.md: 477 lines, owns agent dispatch orchestration (multi-stage, monitoring, retry logic)
- slicing.md: ~350 lines, owns content routing (patterns + 2 algorithms + contracts + reporting)

Both are feature-sized modules with clear single responsibilities.

**Abstraction Leakage Risk:**
The plan preserves the right abstraction level:
- slicing.md defines **what matches** (patterns) and **how to slice** (algorithms)
- Phase files define **when to slice** (>= 1000 lines, >= 200 lines) and **how to orchestrate** (read slicing.md, apply algorithm, write temp files, dispatch agents)

The boundary is clean: slicing.md is declarative (rules + templates), phase files are imperative (orchestration steps).

---

### Naming Consistency

**File naming:**
- `phases/slicing.md` aligns with existing phase file naming (`phases/launch.md`, `phases/triage.md`, `phases/synthesize.md`)
- However, slicing.md is NOT a phase — it's a cross-phase concern (used in Phase 1 for document section mapping, Phase 2 for diff classification, Phase 3 for synthesis reporting)

**Alternative considered:**
- `config/flux-drive/slicing.md` (keeps it in config/ with other cross-phase files)
- Rejected by the brainstorm because "diff-routing.md is already in config/ — natural home" but "Reader must know to look in config/ for procedural logic (unusual)"

**Judgment:**
The plan's choice (`phases/slicing.md`) is acceptable but introduces a naming inconsistency: slicing.md sits in phases/ but is not a phase. This is a minor semantic drift — the file is a reference document, not a phase procedure.

**Recommendation:**
Accept the plan's choice. The alternative (`config/flux-drive/slicing.md`) is equally defensible but would require different references ("Read `config/flux-drive/slicing.md`" feels more like reading configuration than procedure). The phases/ location signals "this is orchestrator-facing logic" more clearly.

---

## Simplicity & YAGNI

### Abstraction Necessity

**Current state:**
The scattered implementation forces orchestrators to mentally abstract the slicing feature by reading 4 files. This is **accidental complexity** — the implementation structure (4 files) does not match the conceptual structure (1 feature).

**Proposed state:**
The consolidation matches implementation to concept. The abstraction cost is eliminated — readers see the feature as a unitary thing because it's in one file.

**Validation:** The consolidation removes accidental complexity without adding unnecessary abstraction. There's no new indirection (no new files, no new interfaces) — just rearrangement of existing content.

---

### Duplication Removal

**Before:** Convergence adjustment rules appear in both diff slicing contract (shared-contracts.md lines 81-87) and document slicing contract (lines 115-122). The rules are identical — copy-paste drift risk.

**After:** Convergence adjustment rules appear once in slicing.md under "Synthesis Contracts" section, covering both diff and document modes.

**Lines saved:** ~140 (per the brainstorm's net effect calculation). This is **real deduplication** — the same contract information was duplicated across diff and document sections.

---

### Premature Extensibility

**Test:** Are there any abstractions in the plan that don't serve current needs?

**Analysis:**
- No new configuration hooks or extension points
- No plugin interfaces or strategy patterns
- No generic frameworks

The plan is a straightforward consolidation: move existing content into one file, replace inline content with references. The only "extension" is the existing "Extending This Configuration" section from diff-routing.md, which remains unchanged (and is justified — projects do customize routing patterns).

**Validation:** No premature extensibility. The plan touches only what's necessary to consolidate.

---

## Critical Gaps

### Gap 1: SKILL.md "read first" instruction must be updated

**Plan Step 6:**
```markdown
**Update line 10** ("File organization" instruction) to include slicing.md:
```markdown
**File organization:** This skill is split across phase files for readability. Read `phases/shared-contracts.md` and `phases/slicing.md` first (defines output format, completion signals, and content routing), then read each phase file as you reach it.
```

**Validation:** This is correct and necessary. Without this change, orchestrators would reach launch.md Step 2.1b, see "Read slicing.md," and have to backtrack. The "read first" list ensures progressive loading includes slicing.md upfront.

**Status:** No gap — the plan addresses this.

---

### Gap 2: Test suite updates are comprehensive

**Plan Step 7:**
- Rename fixture: `diff_routing_path` → `slicing_path`
- Add tests: `test_slicing_file_exists`, `test_no_diff_routing_exists`, `test_slicing_has_both_modes`
- Update existing tests to validate against slicing.md content
- Update tests for launch.md, shared-contracts.md, synthesize.md to check for slicing.md references

**Missing test:**
`test_skill_md_references_slicing_in_read_first_list` — verify that SKILL.md line 10 includes slicing.md in the "read first" instruction.

**Recommendation:** Add this test to guard against regression if SKILL.md's file organization section is later refactored.

---

### Gap 3: Knowledge entry paths

**Plan Step 8:**
```
1. Scan `config/flux-drive/knowledge/` for any entries referencing diff-routing.md — update paths
```

**Risk:** Knowledge entries may reference diff-routing.md by path or mention "diff-routing.md" in their bodies. These references will break after Step 6 (delete diff-routing.md).

**Mitigation strategy:**
1. Grep for `diff-routing` in `config/flux-drive/knowledge/*.md`
2. Replace path references: `config/flux-drive/diff-routing.md` → `skills/flux-drive/phases/slicing.md`
3. Update prose references: "See diff-routing.md" → "See phases/slicing.md"

**Status:** Plan Step 8 includes this scan. Recommendation: Make it a verification step (fail if any references remain after update).

---

## Structural Recommendations

### 1. Consolidation order is correct

**Plan execution order:**
1. Create slicing.md (Step 1)
2. Update phase files to reference slicing.md (Steps 2-5)
3. Delete diff-routing.md (Step 6)
4. Update tests (Step 7)
5. Update knowledge entries (Step 8)

**Validation:** This is the correct order. Creating slicing.md first ensures all references point to a valid file. Deleting diff-routing.md last ensures no intermediate broken state.

---

### 2. Section ordering in slicing.md is logical

**Proposed structure (from plan Step 1):**
1. Overview
2. Routing Patterns (what matches)
3. Diff Slicing (algorithm)
4. Document Slicing (algorithm)
5. Synthesis Contracts (how slicing affects synthesis)
6. Slicing Report Template (how to report)
7. Overlap Resolution + Thresholds (edge cases)
8. Extending Routing Patterns (how to customize)

**Alternative structure (conceptual flow):**
1. Overview
2. Routing Patterns (what matches)
3. Overlap Resolution + Thresholds (edge cases for patterns)
4. Diff Slicing (algorithm using patterns)
5. Document Slicing (algorithm using patterns)
6. Synthesis Contracts (how slicing affects synthesis)
7. Slicing Report Template (how to report)
8. Extending Routing Patterns (how to customize)

**Reasoning:** Putting "Overlap Resolution + Thresholds" immediately after "Routing Patterns" keeps all pattern-related logic together before diving into mode-specific algorithms.

**Recommendation:** **Minor improvement** — adopt the alternative structure. It's a more logical flow: patterns → pattern edge cases → algorithms that consume patterns → synthesis + reporting → extension.

---

### 3. diff-routing.md deletion is safe

**Verification command (from plan Step 6):**
```bash
grep -r "diff-routing.md"
```

**Expected results:**
- `docs/research/`: historical references (OK — read-only)
- `.beads/`: bead metadata (OK — historical)
- `config/flux-drive/knowledge/`: update in Step 8
- No results in `skills/`, `agents/`, `commands/` (would be a problem)

**Recommendation:** Add this grep verification to Step 6 as a blocking check before deletion. If any references exist in `skills/`, `agents/`, or `commands/`, update them first.

---

## Final Recommendation

**SAFE TO PROCEED** with the following refinements:

1. **Adopt alternative section ordering** (P2 improvement): Move "Overlap Resolution + Thresholds" to immediately after "Routing Patterns" in slicing.md structure.

2. **Keep inline context in SKILL.md Step 1.2c** (P2-2): Add 3-4 lines explaining what section mapping does before referencing slicing.md for the algorithm.

3. **Add test for SKILL.md "read first" list** (Gap 2): Verify that slicing.md is included in the file organization instruction.

4. **Make knowledge entry scan a blocking verification** (Gap 3): Fail if any references to diff-routing.md remain after update.

5. **Consider extracting common temp file construction pattern** (P2-1, optional): If duplication bothers you, extract the common pattern to a top-level section. Otherwise, accept the duplication as clearer for linear reading.

All other aspects of the plan are architecturally sound. The consolidation:
- Fixes scattered ownership (module boundary problem)
- Makes coupling explicit (reference pattern)
- Removes duplication (synthesis contracts)
- Preserves progressive loading (slicing.md joins "read first" set)
- Introduces no new abstractions (pure refactoring)

The P1-1 temporal coupling concern is already mitigated by the plan's Step 6 (add slicing.md to "read first" list). The other findings are optional improvements or verification enhancements.

---

## Appendix: Boundary Diagram

```
Before Consolidation (4 files, mesh coupling):

┌──────────────────┐
│ diff-routing.md  │◄─────┐
│ (patterns)       │      │
└──────────────────┘      │
         △                │
         │                │
         │ implicit       │ circular
         │ dependency     │
         │                │
┌──────────────────┐      │
│   launch.md      │──────┘
│ (algorithm)      │◄─────┐
└──────────────────┘      │
         △                │
         │                │
         │ implicit       │
         │ dependency     │
         │                │
┌──────────────────┐      │
│ shared-contracts │──────┤
│ (synthesis rules)│      │
└──────────────────┘      │
         △                │
         │                │
         │ implicit       │
         │ dependency     │
         │                │
┌──────────────────┐      │
│  synthesize.md   │──────┘
│ (reporting)      │
└──────────────────┘

After Consolidation (1 file + 3 references, tree coupling):

                ┌──────────────────┐
                │   slicing.md     │ (leaf dependency)
                │  (feature owner) │
                └──────────────────┘
                         △
                         │
        ┌────────────────┼────────────────┐
        │ explicit       │ explicit       │ explicit
        │ reference      │ reference      │ reference
        │                │                │
┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│  launch.md   │  │  SKILL.md   │  │ synthesize   │
│ (orchestrate)│  │  (triage)   │  │ (reporting)  │
└──────────────┘  └─────────────┘  └──────────────┘

shared-contracts.md references slicing.md for contracts only
(not shown to reduce clutter)
```

The mesh becomes a tree. Coupling is unidirectional and explicit.
