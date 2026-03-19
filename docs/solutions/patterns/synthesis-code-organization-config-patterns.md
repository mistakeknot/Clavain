---
title: "Code Organization and Configuration Patterns"
category: patterns
tags: [skill-md, library-pattern, testing, config-resolution, yaml-parsing, shell, sentinel-values]
date: 2026-03-19
synthesized_from:
  - 2026-02-19-extract-skillmd-inline-logic-to-library.md
  - patterns/2026-02-20-hierarchical-config-resolution.md
---

# Code Organization and Configuration Patterns

Two architectural patterns for keeping plugin codebases maintainable: extracting inline SKILL.md logic into testable libraries, and building hierarchical config resolution with sentinel values.

## Pattern 1: Extract SKILL.md Inline Logic into Library Functions

SKILL.md files are prompt templates that define workflow flow. When implementation details (function definitions, raw SQL) accumulate inline, they become untestable, duplicated, and fragile.

**Detection signals:**
1. Inline function definitions in SKILL.md bash blocks that are not in any library
2. Raw SQL in SKILL.md rather than library helper calls
3. Asymmetric pairs: `_foo_apply` exists in the library but `_foo_revert` is inline-only
4. Duplicate logic across multiple SKILL.md files

**Extraction pattern:** Follow the outer/inner function pair convention:
- Outer function: public API, handles argument parsing and reporting
- Inner function (flock): holds the lock, does the actual work, handles rollback

SKILL.md files call library functions instead of containing implementation:
```bash
# Before: 48 lines of inline logic with raw SQL
# After:
_interspect_revert_routing_override "$AGENT"
_interspect_blacklist_pattern "$AGENT" "User reverted via /interspect:revert"
```

**Benefit:** Functions are testable with bats, follow established patterns (flock/git/rollback), and changes to shared operations (e.g., schema changes) only need updating in one place.

## Pattern 2: Hierarchical Config Resolution with Sentinel Values

When configuration policy is scattered across multiple systems (agent frontmatter, dispatch tiers, profiler overrides), unify into a single YAML file with nested inheritance.

**Resolution chain:** `phases[phase].categories[cat] > phases[phase].model > defaults.categories[cat] > defaults.model`

**Key learnings:**

1. **Sentinel values need belt-and-suspenders interception.** The `inherit` sentinel means "no override at this level." Every public API function must intercept it before returning, AND a final guard must catch the case where ALL levels say `inherit`:
   ```bash
   [[ "$result" == "inherit" ]] && result="sonnet"  # Final fallback
   ```

2. **Phase names must match code, not display strings.** Config keys must use state machine names (`executing`) not display aliases (`quality-gates`). Callers pass `--phase executing`.

3. **After context compaction, check git before re-applying changes.** `git diff HEAD` reveals what is actually uncommitted vs. what the compacted summary claims is pending.

4. **Do not fight linter/hook enforcement.** If hooks re-add values you removed, let them. The config overlay works regardless of what the base values say.

## Shared Principle

Both patterns address the same tension: convenience of inline/scattered implementation vs. maintainability of structured/centralized implementation. The trigger to extract is when you see duplication, asymmetry, or multiple independent systems solving the same problem.
