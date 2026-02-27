# Refactor Safely (compact)

Execute significant refactors in small verified batches.

Core principle: Understand -> Protect -> Change -> Verify -> Simplify.

## Workflow

1. Define explicit refactor goal and blast radius.
2. Run duplication scan (`tldr-swinton:finding-duplicate-functions`) and `fd-architecture`.
3. Ensure protection: coverage check + characterization tests; use `test-driven-development`.
4. Establish green baseline before any structural edits.
5. Plan staged batches with `writing-plans`.
6. For each batch: change -> run affected tests -> run `fd-quality` -> commit.
7. Final pass: full suite, final `fd-quality`, complexity/footprint comparison, then `landing-a-change`.

## Non-Negotiable Rules

- Never refactor untested behavior.
- Never continue with red tests.
- Never mix feature/behavior changes with structural refactors in one commit.
- Keep batches small and independently reviewable.

## Quick Checks

- Green before first change.
- Green after each batch.
- Simpler end state than baseline.

---

*For expanded step guidance, common mistakes, and detailed agent usage, read SKILL.md.*
