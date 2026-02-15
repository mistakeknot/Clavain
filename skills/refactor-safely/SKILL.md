---
name: refactor-safely
description: Use when performing significant refactoring — guides a disciplined process that leverages duplication detection, characterization tests, staged execution, and continuous simplicity review
---

# Refactor Safely

## Overview

Guide disciplined refactoring that minimizes risk through tests, staged execution, and continuous review.

**Core principle:** Understand → Protect → Change → Verify → Simplify.

**Announce at start:** "I'm using the refactor-safely skill to guide this refactoring."

## The Process

### Step 1: Understand the Scope

Before touching code:

1. **Identify what's being refactored and why** — not just "clean up" but a specific goal (extract module, remove duplication, simplify interface, etc.)
2. **Run `tldr-swinton:finding-duplicate-functions`** skill to detect semantic duplication in the affected area
3. **Run `fd-architecture`** agent to understand existing patterns and the "house style"
4. **Map the blast radius** — which files, tests, and consumers are affected?

### Step 2: Protect with Tests

Before any changes:

1. **Check existing test coverage** — are the affected code paths tested?
2. **Add characterization tests** for any untested behavior you're about to change
3. **Use `test-driven-development`** skill to ensure tests exist for the target behavior
4. **Run all tests** — establish a green baseline

**If tests are missing:** Write them first. Don't refactor untested code.

### Step 3: Create a Refactor Plan

Use `writing-plans` to create a staged plan:

1. Break the refactoring into small, independent batches
2. Each batch should leave tests green
3. Order batches to minimize WIP — finish one before starting the next
4. Identify any batch that changes public interfaces (higher risk)

### Step 4: Execute in Batches

For each batch:

1. Make the change
2. Run affected tests
3. **Run `fd-quality`** agent — is the result actually simpler?
4. Commit with a descriptive message

**After each batch, verify:**
- Tests still pass
- The change makes the code objectively simpler (fewer lines, clearer intent, less coupling)
- No behavior has changed (unless that was the explicit goal)

### Step 5: Final Verification

After all batches:

1. Run the full test suite
2. Run `fd-quality` on the complete change
3. Compare before/after metrics: lines of code, number of files, cyclomatic complexity
4. Use `landing-a-change` to ship the result

## Key Agents to Leverage

| Agent | When to Use |
|-------|-------------|
| `tldr-swinton:finding-duplicate-functions` | Step 1 — identify duplication targets |
| `fd-architecture` | Step 1 — understand house patterns, module boundaries |
| `fd-quality` | Step 4 & 5 — verify each batch is simpler, idiom compliance |

## Common Mistakes

**Refactoring without tests**
- **Problem:** Break behavior you don't know about
- **Fix:** Step 2 is non-negotiable. Write characterization tests first.

**Big-bang refactoring**
- **Problem:** 500-line diff that's impossible to review
- **Fix:** Stage into small batches, each independently verifiable

**"Improving" code that works**
- **Problem:** Refactoring stable code without a clear goal
- **Fix:** Every refactoring needs a specific, articulable benefit

**Changing behavior during refactoring**
- **Problem:** "While I'm in here, let me also fix this bug..."
- **Fix:** Separate behavior changes from structural changes. Different commits.

## Red Flags

**Never:**
- Refactor without running tests first
- Make a batch that leaves tests red
- Combine refactoring with feature work in the same commit
- Refactor code you don't understand yet

**Always:**
- Establish a green baseline before starting
- Keep each batch small enough to review
- Verify simplicity after each batch
- Commit after each successful batch
