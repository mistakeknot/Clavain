# Task 7: Complexity Classification Implementation

**Date:** 2026-02-25
**Task:** Port complexity classification heuristics from Bash (lib-sprint.sh lines 958-1119) to Go
**Status:** Complete -- build passes, all tests pass with `-race`

---

## Files Modified

1. **`/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/complexity.go`** -- Replaced stub with full implementation
2. **`/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/complexity_test.go`** -- Created with 52 table-driven test cases
3. **`/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/budget.go`** -- Removed duplicate `resolveRunID` (pre-existing build error fix)
4. **`/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/checkpoint.go`** -- Removed unused `os/exec` import (pre-existing build error fix)
5. **`/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/phase.go`** -- Removed unused `encoding/json` import (pre-existing build error fix)

---

## Implementation Details

### Pure Functions

#### `classifyComplexity(desc string) int`

Faithful port of `sprint_classify_complexity()` from lib-sprint.sh. The heuristic pipeline:

1. **Empty check** -- empty string returns 3 (moderate, the safe default)
2. **Word count** -- `strings.Fields()` for word splitting (matches `wc -w` behavior). `<5` words returns 3 (too short to classify)
3. **Keyword extraction** -- `regexp.MustCompile("[a-zA-Z][a-zA-Z0-9-]*")` matches the Bash `gsub(/[^a-zA-Z-]/, "")` pattern, extracting clean words for case-insensitive keyword matching
4. **Trivial check** -- keywords `{rename, format, typo, bump, reformat, formatting}` with `<20` words returns 1
5. **Research check** -- keywords `{explore, investigate, research, brainstorm, evaluate, survey, analyze}` with `>1` matches returns 5
6. **Base score** -- word count tiers: `<30` = 2, `<100` = 3, `>=100` = 4
7. **Ambiguity adjustment** -- signals `{or, vs, versus, alternative, tradeoff, trade-off, either, approach, option}` with `>2` matches adds +1
8. **Simplicity adjustment** -- signals `{like, similar, existing, just, simple, straightforward}` with `>2` matches adds -1
9. **Clamp** -- result clamped to [1, 5]

**Note:** The Bash version also has a `file_count` parameter for file-count-based adjustments. The Go `classifyComplexity` function is a pure heuristic on the description text only. The `cmdClassifyComplexity` command function handles the override chain (ic run status -> bd state -> heuristic) which matches the Bash `sprint_classify_complexity()` outer logic.

#### `complexityLabel(score int) string`

Direct mapping: 1=trivial, 2=simple, 3=moderate, 4=complex, 5=research. Out-of-range defaults to "moderate".

#### `complexityLabelFromString(s string) string`

Handles both numeric strings and legacy string values. Tries `strconv.Atoi` first, then matches legacy strings case-insensitively: "simple"->simple, "medium"->moderate, "complex"->complex. Unknown defaults to "moderate".

### Command Functions

#### `cmdClassifyComplexity(args []string) error`

Arguments: `<bead_id> <description...>`

Override chain (matches Bash):
1. If `icAvailable()`, tries `ic run status --scope <beadID>` and checks `Run.Complexity > 0`
2. If `bdAvailable()`, tries `bd state <beadID> complexity`
3. Falls back to `classifyComplexity(description)` heuristic

#### `cmdComplexityLabel(args []string) error`

Arguments: `<score>`

Uses `complexityLabelFromString` to handle both numeric and legacy string inputs, matching the Bash `case` statement behavior.

---

## Test Coverage

### `TestClassifyComplexity` (20 cases)

| Case | Input Pattern | Expected | Rationale |
|------|--------------|----------|-----------|
| empty string | `""` | 3 | Empty defaults to moderate |
| too short (1 word) | `"fix"` | 3 | <5 words, too short to classify |
| too short (4 words) | `"fix the bug now"` | 3 | <5 words |
| trivial rename | `"rename the variable..."` | 1 | Trivial keyword + <20 words |
| trivial typo | `"fix typo in the..."` | 1 | Trivial keyword + <20 words |
| trivial bump | `"bump the version..."` | 1 | Trivial keyword + <20 words |
| trivial format | `"reformat the code..."` | 1 | Trivial keyword + <20 words |
| trivial formatting | `"formatting changes..."` | 1 | Trivial keyword + <20 words |
| trivial but long | 20+ words with "rename" | 2 | Trivial keyword but >=20 words, falls to word-count tier |
| research (2 keywords) | `"explore...investigate..."` | 5 | >1 research keyword |
| research (2 keywords) | `"explore...brainstorm..."` | 5 | >1 research keyword |
| research (3 keywords) | `"research...evaluate...analyze..."` | 5 | >1 research keyword |
| research (1 keyword) | `"explore..."` | 2 | Only 1 research keyword, uses word count |
| short simple | `"add a button..."` | 2 | <30 words |
| short moderate | `"implement the user login..."` | 2 | <30 words |
| long complex | 100+ word description | 4 | >=100 words |
| ambiguity bump | 3+ ambiguity signals | 3 | Base 2 + 1 from ambiguity |
| simplicity bump | 3+ simplicity signals | 1 | Base 2 - 1 from simplicity |
| 5 words | `"add the new user button"` | 2 | Exactly 5 words (boundary, not too-short) |
| 30+ words | Moderate-length description | 3 | 30-99 words = moderate |

### `TestComplexityLabel` (9 cases)

All scores 1-5 plus out-of-range (0, -1, 6, 99).

### `TestComplexityLabelFromString` (16 cases)

Numeric inputs (1-5, 0), legacy strings (simple, medium, complex, trivial, research, moderate), case-insensitive variants, unknown/empty defaults.

### `TestCountMatches` (6 cases)

Helper function: no matches, one/two/three matches, case insensitivity, empty input, duplicates.

### `TestClassifyComplexityEdgeCases` (6 cases)

Boundary conditions: exactly 4 vs 5 words, exactly 19 vs 20 words with trivial keyword, clamping to 1, mixed ambiguity + simplicity signals canceling out.

---

## Pre-Existing Build Fixes

The project had three pre-existing build errors that prevented compilation:

1. **`resolveRunID` redeclared** -- Defined in `budget.go`, `checkpoint.go` (already commented out), and `sprint.go`. The `sprint.go` version has caching and is the most complete. Removed the `budget.go` duplicate, replaced with a comment pointing to `sprint.go`.

2. **Unused `os/exec` import in `checkpoint.go`** -- The `resolveRunID` function was previously removed from this file but the import wasn't cleaned up. Removed.

3. **Unused `encoding/json` import in `phase.go`** -- Same pattern: function was moved/removed but import wasn't cleaned. Removed.

These were not introduced by Task 7 but blocked the build. The duplicate `phaseToStage` in phase.go was already resolved (replaced with a comment pointing to budget.go).

---

## Behavioral Parity with Bash

The Go implementation matches the Bash `sprint_classify_complexity()` and `sprint_complexity_label()` exactly, with one deliberate omission:

- **File count adjustment** -- The Bash function accepts a `file_count` parameter and adjusts score based on file count (0-1 files = -1, 10+ files = +1). The Go `classifyComplexity` pure function omits this because the CLI command `classify-complexity` takes `<bead_id> <description>` (no file count argument). The file count adjustment can be added later if needed, or the command can be extended to accept an optional third argument.

- **Override chain** -- The `cmdClassifyComplexity` function implements the full override chain: ic run status -> bd state -> heuristic, matching the Bash behavior.

---

## Build & Test Results

```
$ go build -o /dev/null .
# success (exit 0)

$ go test -race -v
PASS
ok  github.com/mistakeknot/clavain-cli  1.044s
# 56 tests pass (all existing + 52 new complexity tests)
```
