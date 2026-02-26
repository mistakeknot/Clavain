# Task 8: Children Management Implementation

## Summary

Replaced the stub implementations in `children.go` with full children management logic matching the Bash `sprint_close_children` and `sprint_close_parent_if_done` functions from `lib-sprint.sh`. Created `children_test.go` with 47 subtests across 5 test functions. All 55 tests pass (50 existing + 5 new test functions).

## Files Modified

- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/children.go` — Full implementation (was 7-line stub, now ~190 lines)
- `/home/mk/projects/Demarch/os/clavain/cmd/clavain-cli/children_test.go` — New file with comprehensive tests

## Implementation Details

### Parsing Helpers (pure functions, fully testable)

1. **`extractSection(output, section string) []string`** — Generic section extractor. Recognizes all `bd show` section headers (BLOCKS, CHILDREN, PARENT, DESCRIPTION, LABELS, NOTES, COMMENTS, DEPENDS ON). A section ends at a blank line or another section header.

2. **`parseBlockedIDs(output string) []string`** — Extracts open bead IDs from the BLOCKS section. Looks for lines containing `← ○` (open indicator), extracts the ID between `← ○ ` and the first `:`, validates against `^[A-Za-z]+-[A-Za-z0-9.]+$`.

3. **`parseParentID(output string) string`** — Extracts parent bead ID from the PARENT section. Looks for lines containing `↑`, skips the status icon rune (○, ◐, ●, ✓, ❄), extracts ID before the first `:`, validates same regex.

4. **`countOpenChildren(output string) int`** — Counts lines matching `↳ ○` or `↳ ◐` in the CHILDREN section (open or in-progress).

### Command Functions

1. **`cmdCloseChildren(args []string) error`**
   - Args: `<epic_id> [reason]`, default reason: `"Auto-closed: parent epic <id> shipped"`
   - Outputs `"0"` if bd unavailable or no open blocked beads
   - Parses `bd show <epic_id>` BLOCKS section for open beads
   - Closes each with `bd close <id> --reason="<reason>"`, counts successes
   - Calls `cmdCloseParentIfDone` to propagate upward (matching Bash behavior)
   - Always returns nil (non-fatal errors)

2. **`cmdCloseParentIfDone(args []string) error`**
   - Args: `<bead_id> [reason]`, default reason: `"Auto-closed: all children completed"`
   - Silently returns nil if bd unavailable, no parent found, parent not OPEN/IN_PROGRESS, or open children remain
   - Outputs parent ID if successfully closed
   - Always returns nil

### Design Decisions

- **Bead ID regex includes dots**: `^[A-Za-z]+-[A-Za-z0-9.]+$` supports dotted sub-bead IDs like `iv-1xtgd.1`. The Bash original used `[A-Za-z0-9]+` without dots, which was a bug — dotted IDs would be silently dropped.
- **Section extraction as shared helper**: Rather than duplicating awk-like section parsing in each function, `extractSection` is a reusable pure function that all three parsers share.
- **Unicode handling**: The parent ID parser uses `[]rune` slicing to correctly handle multi-byte status icon characters (○, ◐, ●, ✓, ❄).
- **Non-fatal errors**: Both commands always return nil, matching the Bash functions which always `return 0`. Errors from `bd` subprocess calls are silently swallowed.

## Test Coverage

### TestParseBlockedIDs (9 subtests)
- Typical mixed open/closed BLOCKS section
- All closed (no open beads) -> nil
- Empty output -> nil
- No BLOCKS section -> nil
- Dotted bead IDs (iv-1xtgd.1, iv-1xtgd.2)
- Single open bead
- BLOCKS followed by another section (LABELS)
- Mixed status icons (○, ◐, ●, ✓, ❄) — only ○ extracted
- BLOCKS with trailing blank line

### TestParseParentID (10 subtests)
- All 5 status icons (○, ◐, ●, ✓, ❄) in PARENT line
- No parent section -> ""
- Empty output -> ""
- Parent section with no arrow line -> ""
- Dotted parent ID
- PARENT followed by another section (NOTES)

### TestCountOpenChildren (9 subtests)
- Mix of open, in-progress, closed, deferred
- All closed -> 0
- All open -> 3
- All in-progress -> 2
- Empty output -> 0
- No CHILDREN section -> 0
- Single open/closed child
- Deferred-only children -> 0

### TestExtractSection (5 subtests)
- DESCRIPTION, CHILDREN, BLOCKS, PARENT sections
- Nonexistent section -> empty

### TestBeadIDRegex (14 subtests)
- Valid: `iv-abc`, `iv-1xtgd`, `iv-1xtgd.1`, `FOO-bar2`, `A-b`, `iv-abc.1.2`
- Invalid: `abc` (no dash), `-abc` (starts with dash), `123-abc` (starts with digit), `iv-` (empty after dash), empty string, contains space, contains colon

## Verification

```
$ go build -o /dev/null .    # Clean build
$ go test -race -count=1 ./...
ok      github.com/mistakeknot/clavain-cli    1.046s   # 55 tests pass (50 existing + 5 new)
```

No other `.go` files were modified. The existing 50 tests continue to pass.
