---
name: refactor-safely
description: Use for significant refactoring — duplication detection, characterization tests, staged execution, simplicity review.
---

# Refactor Safely

Understand → Protect → Change → Verify → Simplify.

**Announce:** "I'm using the refactor-safely skill to guide this refactoring."

## Step 1: Understand the Scope

- Identify the specific goal (not just "clean up" — extract module, remove duplication, simplify interface, etc.)
- Run `tldr-swinton:finding-duplicate-functions` to detect semantic duplication in the affected area
- Run `fd-architecture` to understand existing patterns and house style
- Map blast radius: which files, tests, and consumers are affected?

## Step 2: Protect with Tests

- Check existing test coverage for affected code paths
- Add characterization tests for any untested behavior you're about to change
- Use `test-driven-development` skill to ensure tests exist for the target behavior
- Run all tests — establish a green baseline

**If tests are missing: write them first. Don't refactor untested code.**

## Step 3: Create a Refactor Plan

Use `writing-plans` to create a staged plan:
- Break into small, independent batches — each must leave tests green
- Order to minimize WIP — finish one before starting the next
- Flag any batch that changes public interfaces (higher risk)

## Step 4: Execute in Batches

For each batch:
1. Make the change
2. Run affected tests
3. Run `fd-quality` — is the result actually simpler?
4. Commit with a descriptive message

After each batch verify: tests pass, code is objectively simpler (fewer lines, clearer intent, less coupling), no unintended behavior changes.

## Step 5: Final Verification

1. Run full test suite
2. Run `fd-quality` on the complete change
3. Compare before/after: lines of code, file count, cyclomatic complexity
4. Use `landing-a-change` to ship

## Key Agents

| Agent | When |
|-------|------|
| `tldr-swinton:finding-duplicate-functions` | Step 1 — duplication targets |
| `fd-architecture` | Step 1 — house patterns, module boundaries |
| `fd-quality` | Steps 4 & 5 — simplicity and idiom compliance |

## Red Flags

**Never:**
- Refactor without running tests first
- Leave a batch with red tests
- Combine refactoring + feature work in the same commit
- Refactor code you don't understand yet

**Always:**
- Green baseline before starting
- Each batch small enough to review
- Verify simplicity after each batch
- Separate behavior changes from structural changes — different commits
