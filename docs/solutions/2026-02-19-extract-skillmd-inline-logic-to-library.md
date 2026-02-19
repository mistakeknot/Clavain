---
title: "Extract SKILL.md Inline Logic into Testable Library Functions"
category: architecture
tags: [skill-md, testing, library-pattern, flock, interspect]
severity: P2
discovery: implementation
applies_to: [clavain, interspect]
date: 2026-02-19
---

# Extract SKILL.md Inline Logic into Testable Library Functions

## Problem

A SKILL.md command file (`interspect-revert.md`) contained a complete inline function definition (`_interspect_revert_override_locked`) and raw SQL statements for blacklist operations. While the command worked correctly — Claude reads the SKILL.md and executes the described logic — this created three issues:

1. **Untestable**: The function existed only as pseudocode in a markdown file. No bats test could call it because it wasn't defined in the sourced library.
2. **Duplicated pattern**: The apply path (`_interspect_apply_routing_override` → `_interspect_apply_override_locked`) had proper library functions, but the revert path was ad-hoc inline code. This asymmetry made the codebase harder to reason about.
3. **Fragile SQL**: Raw `INSERT OR REPLACE INTO blacklist` statements appeared in two separate SKILL.md files (`interspect-revert.md` and `interspect-unblock.md`), creating divergence risk if the schema changed.

## Root Cause

SKILL.md files serve as **prompt templates** that define the workflow flow (disambiguation → action → decision → report). When the first version of a command is written, it's natural to put the implementation details inline — especially when the library doesn't have the function yet. But as the codebase matures, inline logic should be extracted into the shared library where it follows established patterns (flock/git/rollback) and can be tested.

The asymmetry emerged because the *apply* path was implemented first as a library function (needed by the propose command), while the *revert* path was written later directly in the revert command SKILL.md.

## Solution

Extract the outer/inner function pair following the established codebase pattern:

| Layer | Apply (existed) | Revert (added) |
|-------|-----------------|----------------|
| Outer | `_interspect_apply_routing_override` | `_interspect_revert_routing_override` |
| Inner (flock) | `_interspect_apply_override_locked` | `_interspect_revert_override_locked` |

Also extract shared operations into standalone helpers:
- `_interspect_blacklist_pattern` — replaces inline SQL in two SKILL.md files
- `_interspect_unblacklist_pattern` — replaces inline SQL in unblock command

The SKILL.md files then call library functions instead of containing implementation:
```bash
# Before: 48 lines of inline logic
# After:
_interspect_revert_routing_override "$AGENT"
_interspect_blacklist_pattern "$AGENT" "User reverted via /interspect:revert"
```

## Detection Pattern

Look for these signals that inline SKILL.md logic should be extracted:

1. **Inline function definitions** in SKILL.md (functions defined in bash blocks that aren't in any library)
2. **Raw SQL** in SKILL.md rather than library helper calls
3. **Asymmetric pairs**: if `_foo_apply` exists in the library but `_foo_revert` only exists inline
4. **Duplicate logic** across multiple SKILL.md files (same SQL, same validation, same git flow)

## Verification

- 59/59 routing bats tests pass (9 new)
- 43/43 overlay integration tests pass
- `bash -n lib-interspect.sh` succeeds
