# P3 Beads Issues — Created 2026-02-11

## Summary

Created 4 P3 beads issues for Clavain covering skill consolidation, performance, quality consistency, and a new command.

## Issues Created

| # | Issue ID | Type | Title |
|---|----------|------|-------|
| 1 | `Clavain-i82q` | task | Merge requesting-code-review + receiving-code-review into one skill |
| 2 | `Clavain-gw0h` | task | Simplify escape_for_json control character loop in lib.sh |
| 3 | `Clavain-gomw` | task | Standardize hook invocation style + shebangs across all scripts |
| 4 | `Clavain-l8zk` | feature | Add /clavain:describe-pr command for quick PR descriptions |

## Details

### 1. Clavain-i82q — Merge code review skills
- **Type:** task | **Priority:** P3
- **Description:** UX review: requesting-code-review and receiving-code-review are two sides of the same workflow. Merge into code-review-discipline with requesting and receiving sections. Reduces skill count by 1.
- **Impact:** Skill count would drop from 33 to 32. Tests in `tests/structural/` that hardcode count=33 would need updating.

### 2. Clavain-gw0h — Simplify escape_for_json in lib.sh
- **Type:** task | **Priority:** P3
- **Description:** Performance: the 26-iteration loop in `escape_for_json` scans for control characters that never appear in markdown input. Can be replaced with a single `tr -d` pipe or removed entirely. Saves ~50% of function execution time. Since this runs in the async session-start hook, there is no user-visible latency impact.

### 3. Clavain-gomw — Standardize hook invocation + shebangs
- **Type:** task | **Priority:** P3
- **Description:** Quality: hooks.json mixes bash quoted and bare invocation styles. Two scripts use `#!/bin/bash` instead of `#!/usr/bin/env bash`. Pick one style and apply consistently across all 5 hook scripts.

### 4. Clavain-l8zk — Add /clavain:describe-pr command
- **Type:** feature | **Priority:** P3
- **Description:** UX review: generate PR title + description from current branch commits. Daily utility that fits Clavain's engineering discipline angle. Would bring command count from 25 to 26.

## Notes
- All issues created at P3 priority (low/nice-to-have)
- The `beads.role` warning on each create is cosmetic — `bd init` has not been run in this project to set a role
