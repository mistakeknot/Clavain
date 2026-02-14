# PRD: Consolidate Diff/Document Slicing into Single Module

**Bead:** Clavain-496k
**Status:** Draft
**Priority:** P3 (blocks P2 Clavain-0etu: flux-drive extraction Phase 3)

## Problem

Flux-drive's content slicing feature (routing diffs and documents to agents based on relevance patterns) is scattered across 4 files totaling ~499 lines. Understanding, modifying, or testing slicing requires reading all 4 files and mentally stitching the feature together. This was flagged as P0-2 in the fd-architecture self-review.

**Current locations:**
1. `config/flux-drive/diff-routing.md` (166 lines) — routing patterns
2. `skills/flux-drive/phases/launch.md` Step 2.1b + 2.1c (75 lines) — slicing algorithm
3. `skills/flux-drive/phases/shared-contracts.md` (78 lines) — synthesis contracts
4. `skills/flux-drive/phases/synthesize.md` (14 lines) — report template

Plus SKILL.md Step 1.2c (30 lines) — document section mapping trigger.

## Solution

Create `skills/flux-drive/phases/slicing.md` consolidating all slicing logic into one file. Delete `config/flux-drive/diff-routing.md`. Replace slicing sections in launch.md, shared-contracts.md, and synthesize.md with short references.

## Scope

### In Scope
- Consolidate all slicing logic into `phases/slicing.md`
- Delete `config/flux-drive/diff-routing.md`
- Update launch.md, shared-contracts.md, synthesize.md, SKILL.md with references
- Update `tests/structural/test_diff_slicing.py` to validate new structure
- Check and update any knowledge entries referencing diff-routing.md

### Out of Scope
- Changing slicing behavior (thresholds, patterns, algorithms)
- Adding new routing patterns or agents
- Token instrumentation (separate bead Clavain-i1u6)
- Executable slicing engine (this is markdown instructions, not code)

## Success Criteria

1. All slicing logic in one file (`phases/slicing.md`)
2. No content duplication between slicing.md and other phase files
3. All structural tests pass (updated for new file structure)
4. No references to `diff-routing.md` remain in skill/config files
5. Phase files are shorter and cleaner (net ~140 lines removed via deduplication)

## Tasks

1. **Create `phases/slicing.md`** — Consolidate routing patterns, diff slicing algorithm, document slicing algorithm, synthesis contracts, and report template into structured sections.

2. **Update `phases/launch.md`** — Remove Step 2.1b (diff slicing algorithm), remove sliced cases from Step 2.1c, add reference to slicing.md.

3. **Update `phases/shared-contracts.md`** — Remove Diff Slicing Contract and Document Slicing Contract sections (lines 53-130), add reference.

4. **Update `phases/synthesize.md`** — Remove Diff Slicing Report template (lines 177-191), add reference.

5. **Update `skills/flux-drive/SKILL.md`** — Simplify Step 1.2c to a trigger condition + reference. Update "read phases/shared-contracts.md first" instruction to include slicing.md.

6. **Delete `config/flux-drive/diff-routing.md`** — All content moved to slicing.md.

7. **Update tests** — Modify `test_diff_slicing.py` to point at new file locations. All existing assertions should still pass against slicing.md content.

8. **Update references** — Check docs/research/ and docs/solutions/ for stale diff-routing.md references. Update path references.

## Risk Assessment

- **Low risk**: Pure markdown refactoring — no runtime behavior changes, no executable code affected.
- **Test impact**: Straightforward fixture path updates.
- **Knowledge entries**: May need path updates if any reference diff-routing.md.
