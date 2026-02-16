# Quality Review: Token-Efficient Skill Loading

**Reviewed Files:**
1. `/root/projects/Interverse/plugins/interwatch/scripts/interwatch-scan.py` (Python drift scanner)
2. `/root/projects/Interverse/scripts/gen-skill-compact.sh` (Bash LLM generator)
3. `/root/projects/Interverse/scripts/tests/skill_compact.bats` (Bats test suite)

**Reviewers:** flux-drive quality reviewer
**Date:** 2026-02-15

---

## Executive Summary

**Overall Quality:** High. The implementation demonstrates strong language-specific idioms, robust error handling, and thoughtful test coverage. The Python scanner follows modern Python patterns with type hints and clean separation of concerns. The Bash script adheres to strict mode with defensive quoting. The test suite provides comprehensive structural validation.

**Key Strengths:**
- Excellent separation of concerns (signal evaluators, dispatch table, tier mapping)
- Defensive error handling with meaningful fallbacks
- Type hints on all Python public APIs
- Shell strict mode (`set -euo pipefail`) with robust quoting
- Comprehensive test coverage for all three skill manifests

**Priority Issues:**
- P1: Python missing explicit exception chaining in several places
- P2: Bash lacks `trap`-based cleanup for error paths
- P2: Test suite missing behavioral validation (only structural checks)

**Low-Priority Improvements:**
- Python could benefit from dataclasses for structured results
- Bash could use more descriptive variable names in some places
- Tests could add edge case coverage (empty files, malformed YAML)

---

## Python: interwatch-scan.py

### Universal Quality

**Naming consistency: PASS**
- Function names are clear and follow `snake_case` convention
- Module-level constants use `SCREAMING_SNAKE_CASE` (`SIGNAL_EVALUATORS`)
- `Watchable`, `Signal`, `Tier` concepts are consistent with domain vocabulary

**File organization: PASS**
- Logical sectioning with ASCII comment separators
- Signal evaluators grouped together, then dispatch table, then main scan logic
- Imports follow stdlib/third-party grouping convention

**Error handling patterns: MIXED**
- ✅ Defensive subprocess calls with `TimeoutExpired`, `FileNotFoundError`, `OSError` handling
- ✅ Graceful degradation (return empty string or 0 on failure)
- ⚠️ Missing explicit error context chaining in several places (see Python-specific section)
- ⚠️ `sys.exit(2)` on missing PyYAML — could benefit from more helpful message about installation

**Test strategy: PARTIAL**
- No unit tests for individual signal evaluators
- No integration tests for full scan workflow
- Relies on manual testing via `--check` flag
- Test coverage gap noted in "Missing Test Coverage" section

**API design consistency: PASS**
- Clean CLI interface with argparse
- JSON output to stdout (standard Unix pattern)
- `--check` flag for single-doc filtering (composable)

**Complexity budget: PASS**
- Signal evaluators are simple, focused functions
- No over-abstraction — direct implementation of requirements
- Dispatch table avoids bloated conditionals

**Dependency discipline: PASS**
- Only external dep is PyYAML (standard, lightweight)
- Uses subprocess for shell commands (no external process libs)
- No unnecessary abstractions

### Python-Specific Checks

**Explicit error handling: PASS (with warnings)**
- ✅ No discarded errors — all exceptions are caught and handled
- ⚠️ **Missing exception chaining in several places:**
  - Line 85-88: `json.load(f)` → should use `except json.JSONDecodeError as e: ... from e`
  - Line 127-130: `open(doc_path)` → should preserve `OSError` context
  - Line 352-356: `yaml.safe_load()` → should chain exception on parse failure
- **Impact:** Loss of stack trace context makes debugging harder for users

**Error context propagation: PARTIAL**
- ✅ Most functions return sentinel values (empty string, 0) on failure
- ⚠️ Some error paths silently swallow exceptions without logging
- **Recommendation:** Add optional `--verbose` flag for stderr diagnostics

**5-second naming rule (public APIs): PASS**
- `scan_watchable`, `load_config`, `score_to_tier`, `tier_to_action` are all self-documenting
- CLI args (`--config`, `--check`) are clear

**File/module organization: PASS**
- 384 lines is appropriate for this scope
- Could split into `signals.py` + `scanner.py` + `cli.py` if it grows beyond 500 lines
- Current structure is fine for now

**Interface design: PASS**
- Functions accept simple types (`str`, `float`, `int`)
- Return types are primitive or dict (JSON-serializable)
- No interface bloat — only two public functions (`scan_watchable`, `load_config`)

**Type hints: EXCELLENT**
- ✅ All function signatures have type hints (`str | None`, `list[str]`, `dict`)
- ✅ Uses modern union syntax (`str | None` not `Optional[str]`)
- ✅ Return types specified for all functions

**Pythonic constructs: EXCELLENT**
- ✅ List comprehensions used appropriately (lines 65, 74, 167)
- ✅ Dict comprehensions avoided where they'd reduce clarity
- ✅ Context managers (`with open()`) for all file operations
- ✅ `for...else` construct used correctly (line 89)
- ✅ Generator expressions used for `sum()` (line 213)

**Exception handling specificity: EXCELLENT**
- ✅ Catches specific exceptions: `json.JSONDecodeError`, `OSError`, `subprocess.TimeoutExpired`, `FileNotFoundError`
- ✅ No bare `except:` clauses
- ✅ No silent failures — all exceptions produce meaningful fallbacks

**pytest-friendly structure: PARTIAL**
- ✅ Pure functions (no global state)
- ✅ Dependency injection (evaluators take `path`, `mtime`)
- ⚠️ No tests exist for individual evaluators
- **Recommendation:** Add `tests/test_signals.py` with table-driven tests for each evaluator

### Specific Findings

#### P1: Missing exception chaining

**Location:** Lines 85-88, 127-130, 352-356
**Issue:** Exception context is discarded instead of chained.

**Current:**
```python
try:
    with open(manifest) as f:
        plugin_version = json.load(f).get("version", "")
    break
except (json.JSONDecodeError, OSError):
    plugin_version = ""
```

**Recommended:**
```python
try:
    with open(manifest) as f:
        plugin_version = json.load(f).get("version", "")
    break
except (json.JSONDecodeError, OSError) as e:
    logger.debug(f"Failed to read {manifest}: {e}")  # If --verbose flag
    plugin_version = ""
```

**Impact:** Medium — reduces debuggability, but doesn't affect correctness.

#### P2: Hard-coded companion list is fragile

**Location:** Lines 201-206
**Issue:** Companion list will drift as plugins are added/removed.

**Current:**
```python
companions = [
    "interphase", "interline", "interflux", "interwatch", "interdoc",
    # ... 19 total
]
```

**Recommended:**
- Read from a manifest file (`config/companions.json`) or
- Scan `../plugins/*` directories dynamically

**Impact:** Low — signal will degrade silently over time.

#### P3: Regex import buried in function

**Location:** Line 100, 132
**Issue:** `import re` is inside functions, not at module level.

**Current:**
```python
def eval_version_bump(...):
    # ...
    import re
    match = re.search(...)
```

**Recommended:** Move `import re` to top of file (line 20).

**Impact:** Negligible — Python caches imports, but violates PEP 8.

#### P4: Magic number caps lack justification

**Location:** Lines 66, 142, 168, 196, 214, 227
**Issue:** Caps like `min(count, 10)` are unexplained.

**Current:**
```python
return min(len(lines), 10)  # Cap at 10 to avoid score explosion
```

**Recommended:** Extract to named constants with docstrings:
```python
# Signal caps to prevent score explosion
MAX_BEAD_CLOSED_SCORE = 10
MAX_COMPONENT_CHANGES = 3
MAX_FILE_CHANGES = 5
```

**Impact:** Low — readability improvement, no correctness issue.

---

## Shell: gen-skill-compact.sh

### Universal Quality

**Naming consistency: PASS**
- Function names are clear (`compute_manifest`, `check_freshness`, `generate_compact`)
- Variable names use `snake_case`
- Constants use `SCREAMING_SNAKE_CASE` (`KNOWN_SKILLS`, `LLM_CMD`)

**File organization: PASS**
- Script header with usage examples
- Helper functions first, main dispatch logic last
- Clear separation between check and generate modes

**Error handling patterns: GOOD**
- ✅ `set -euo pipefail` enforces strict mode
- ✅ Meaningful exit codes (0=success, 1=stale, 2=error)
- ✅ Error messages to stderr
- ⚠️ No `trap`-based cleanup (see Shell-specific section)

**Test strategy: GOOD**
- Comprehensive Bats tests for all three skills
- Edge case coverage (missing manifest, missing compact, bad hashes)
- CLI usage tests (no args, --help, invalid paths)

**API design consistency: PASS**
- Unix-style flags (`--check`, `--check-all`, `--help`)
- Environment variable override (`GEN_COMPACT_CMD`)
- Composes well with shell pipes (JSON output via `jq`)

**Complexity budget: PASS**
- 180 lines for a non-trivial generator
- Three focused functions, no over-abstraction
- Main dispatch is a simple case statement

**Dependency discipline: PASS**
- Uses standard tools (`jq`, `sha256sum`, `basename`)
- LLM command is pluggable via env var
- No external dependencies beyond coreutils

### Shell-Specific Checks

**Strict mode: EXCELLENT**
- ✅ `set -euo pipefail` at line 18
- ✅ No unsafe expansions — all variables quoted
- ✅ Uses `${var:?msg}` for required args (line 151)

**Quoting and expansion: EXCELLENT**
- ✅ All file paths double-quoted: `"$skill_dir"`, `"$manifest_path"`
- ✅ Command substitution properly quoted: `hash=$(sha256sum "$f" | cut -d' ' -f1)`
- ✅ No unquoted `$@` or `$*`

**Portability: GOOD**
- ✅ `#!/usr/bin/env bash` shebang (not `#!/bin/bash`)
- ✅ Uses bash-specific features (arrays, `[[ ]]`, `${BASH_SOURCE[0]}`)
- ⚠️ `sha256sum` is GNU coreutils — won't work on BSD/macOS (use `shasum -a 256`)
- **Impact:** Low — this is a monorepo tool, not distributed software

**Cleanup handling: MISSING**
- ⚠️ No `trap` to clean up on error or interrupt
- **Issue:** If LLM call times out or user Ctrl+C's, partial files could be written
- **Recommended:**
  ```bash
  cleanup() { rm -f "$tmpfile"; }
  trap cleanup EXIT
  output=$(mktemp)
  echo "$prompt" | $LLM_CMD > "$output" 2>/dev/null
  mv "$output" "$skill_dir/SKILL-compact.md"
  ```
- **Impact:** Medium — could leave stale/partial compact files

**Injection safety: GOOD**
- ✅ No `eval` usage
- ✅ LLM command expansion is safe (user controls `GEN_COMPACT_CMD`)
- ✅ No untrusted input in command construction

### Specific Findings

#### P2: Missing trap-based cleanup

**Location:** Lines 119-134 (generate_compact function)
**Issue:** If LLM call fails or is interrupted, partial output could corrupt files.

**Current:**
```bash
output=$(echo "$prompt" | $LLM_CMD 2>/dev/null)
echo "$output" > "$skill_dir/SKILL-compact.md"
```

**Recommended:**
```bash
tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

if ! echo "$prompt" | $LLM_CMD > "$tmpfile" 2>/dev/null; then
    echo "Error: LLM command failed" >&2
    return 2
fi

mv "$tmpfile" "$skill_dir/SKILL-compact.md"
```

**Impact:** Medium — data integrity issue on failure.

#### P3: diff output unguarded

**Location:** Line 77
**Issue:** `diff` returns exit 1 when files differ, which would normally fail `set -e`, but `|| true` swallows it.

**Current:**
```bash
diff <(echo "$saved" | jq -S '.') <(echo "$current" | jq -S '.') >&2 || true
```

**Why this works:** The `|| true` prevents `set -e` from aborting, but it's implicit.

**Recommended:** Add a comment:
```bash
# Show diff (exit 1 is expected when stale, so || true to prevent set -e abort)
diff <(...) <(...) >&2 || true
```

**Impact:** Low — readability/maintenance.

#### P4: Relative path resolution fragile

**Location:** Lines 153-155, 174-176
**Issue:** Converts relative to absolute by prefixing `$INTERVERSE_ROOT`, but doesn't validate result.

**Current:**
```bash
if [[ ! "$skill_dir" = /* ]]; then
    skill_dir="$INTERVERSE_ROOT/$skill_dir"
fi
```

**Recommended:** Add validation:
```bash
if [[ ! "$skill_dir" = /* ]]; then
    skill_dir="$INTERVERSE_ROOT/$skill_dir"
fi
if [[ ! -d "$skill_dir" ]]; then
    echo "Error: skill directory not found: $skill_dir" >&2
    exit 2
fi
```

**Impact:** Low — improves error messages.

#### Minor: Variable naming

**Location:** Line 67
**Suggestion:** Rename `current` → `current_manifest`, `saved` → `saved_manifest` for clarity.

---

## Bats: skill_compact.bats

### Universal Quality

**Test organization: GOOD**
- ✅ Three test sections: manifest format, compact file existence, freshness checks
- ✅ Test names follow clear pattern: `category: assertion`
- ✅ Proper use of bats-assert and bats-support libraries

**Test coverage: PARTIAL**
- ✅ Structural tests: JSON validity, required keys, hash format
- ✅ Freshness checks: all three known skills verified
- ✅ Edge cases: missing manifest, missing compact, stale detection
- ⚠️ **Missing behavioral tests:** No validation that `--check-all` actually runs checks, or that staleness is detected correctly when hashes differ (beyond synthetic test)
- ⚠️ **No generation tests:** Script can check freshness, but no tests for `generate_compact` (requires LLM)

**API testing: GOOD**
- ✅ CLI arg tests (`--help`, no args, `--check` with bad path)
- ✅ Exit code validation (0 for fresh, 1 for stale, 2 for error)

**Naming: EXCELLENT**
- Test names are descriptive: `"manifest: doc-watch manifest is valid JSON"`
- No abbreviated test names

### Bats-Specific Checks

**bats-support/bats-assert usage: CORRECT**
- ✅ Loaded via npm global discovery (lines 9-19)
- ✅ Uses `assert_success`, `assert_failure`, `assert_output --partial`
- ✅ Falls back gracefully if not installed (test still runs, just no helpers)

**Setup/teardown: MINIMAL**
- ✅ `setup()` function finds and loads helpers
- ⚠️ No `teardown()` — but no state to clean up, so acceptable

**Test isolation: GOOD**
- ✅ Each test uses fresh `mktemp -d` for synthetic tests (lines 111-128)
- ✅ No shared state between tests

**Assertions: GOOD**
- ✅ Uses `run` to capture output and exit codes
- ✅ Checks both stdout (`assert_output`) and status (`assert_success`)
- ✅ Direct bash conditionals for file checks (`[[ -f ... ]]`)

### Specific Findings

#### P2: Missing behavioral validation

**Location:** Lines 103-106 (`--check-all` test)
**Issue:** Test only checks exit code, not that all skills were actually checked.

**Current:**
```bash
@test "freshness: --check-all reports all fresh" {
    run bash "$SCRIPT" --check-all
    assert_success
}
```

**Recommended:**
```bash
@test "freshness: --check-all reports all fresh" {
    run bash "$SCRIPT" --check-all
    assert_success
    # Verify all three skills appear in output
    assert_output --partial "doc-watch"
    assert_output --partial "artifact-gen"
    assert_output --partial "flux-drive"
}
```

**Impact:** Low — test is too coarse-grained.

#### P3: No generation smoke test

**Location:** Missing test
**Issue:** No test that `generate_compact` actually runs (would require mock LLM).

**Recommended:** Add a test with `GEN_COMPACT_CMD="cat"` (identity function):
```bash
@test "generation: can generate compact with mock LLM" {
    local tmpdir=$(mktemp -d)
    echo "# Test Skill" > "$tmpdir/SKILL.md"

    export GEN_COMPACT_CMD="cat"  # Mock LLM — just echo input
    run bash "$SCRIPT" "$tmpdir"
    assert_success
    [[ -f "$tmpdir/SKILL-compact.md" ]]
    [[ -f "$tmpdir/.skill-compact-manifest.json" ]]

    rm -rf "$tmpdir"
}
```

**Impact:** Low — nice-to-have, not critical.

#### Minor: Setup library discovery could be more robust

**Location:** Lines 9-19
**Suggestion:** Check for `bats-support` in more locations (user npm global, project-local `node_modules`).

---

## Missing Test Coverage

### Python: interwatch-scan.py

**Unit tests needed:**
- Signal evaluators with known inputs/outputs (table-driven tests)
- Edge cases: empty git repos, missing `.beads` directory, malformed plugin.json
- Confidence tier mapping logic (boundary conditions)

**Example pytest structure:**
```python
# tests/test_signals.py
import pytest
from interwatch_scan import eval_bead_closed, eval_version_bump

@pytest.mark.parametrize("bd_output,expected", [
    ("✓ Task 1\n✓ Task 2", 2),
    ("", 0),
    ("⚠ Warning\n✓ Task 1", 1),
])
def test_eval_bead_closed(bd_output, expected, monkeypatch):
    monkeypatch.setattr("interwatch_scan.run_cmd", lambda cmd: bd_output)
    assert eval_bead_closed("doc.md", 1234567890.0) == expected
```

### Shell: gen-skill-compact.sh

**Integration tests needed:**
- Full generation workflow with mock LLM
- Manifest consistency after regeneration
- Staleness detection with known hash mismatches

**Behavioral tests needed:**
- Verify `--check-all` actually iterates all known skills
- Verify relative path resolution works from different CWDs

### Bats: skill_compact.bats

**Tests to add:**
- Validate manifest contains all expected files (not just `SKILL.md`)
- Check that stale detection triggers when phase files change
- Verify JSON output format from `--check` (could be parsed by other tools)

---

## Recommendations by Priority

### P0: None
All critical functionality is correct.

### P1: Python exception chaining
**Where:** `interwatch-scan.py` lines 85-88, 127-130, 352-356
**What:** Add `from e` to exception handlers to preserve context
**Why:** Improves debuggability for users

### P2: Shell cleanup trap
**Where:** `gen-skill-compact.sh` lines 119-134
**What:** Add `trap 'rm -f "$tmpfile"' EXIT` and use temp file for LLM output
**Why:** Prevents partial file writes on failure/interrupt

### P2: Test behavioral coverage
**Where:** `skill_compact.bats` line 103-106
**What:** Verify `--check-all` output contains all skill names
**Why:** Ensures test validates behavior, not just exit code

### P3: Python regex import location
**Where:** `interwatch-scan.py` lines 100, 132
**What:** Move `import re` to module level
**Why:** PEP 8 compliance, clarity

### P3: Shell path validation
**Where:** `gen-skill-compact.sh` lines 153-155, 174-176
**What:** Add directory existence check after path resolution
**Why:** Better error messages

### P4: Python magic number constants
**Where:** `interwatch-scan.py` lines 66, 142, 168, 196, 214, 227
**What:** Extract to named constants
**Why:** Readability

---

## Language-Specific Idiom Compliance

### Python: 9/10
- ✅ Type hints throughout
- ✅ Context managers for file I/O
- ✅ List/generator comprehensions
- ✅ Modern union syntax (`str | None`)
- ✅ Specific exception handling
- ⚠️ Exception chaining missing in a few places
- ⚠️ No dataclasses (dict return types are acceptable, but could be more structured)

### Shell: 8/10
- ✅ Strict mode (`set -euo pipefail`)
- ✅ Defensive quoting
- ✅ Meaningful exit codes
- ✅ No `eval` or unsafe expansions
- ⚠️ Missing `trap`-based cleanup
- ⚠️ `sha256sum` portability (GNU-specific)

### Bats: 8/10
- ✅ Proper use of `run`, `assert_success`, `assert_output`
- ✅ Test isolation with `mktemp`
- ✅ Descriptive test names
- ⚠️ Missing behavioral validation in some tests
- ⚠️ No generation smoke test

---

## Conclusion

This is high-quality production code. The Python scanner demonstrates excellent use of modern Python idioms (type hints, specific exceptions, comprehensions). The Bash generator properly uses strict mode and defensive quoting. The test suite provides comprehensive structural validation.

**The main gap is around error context and cleanup:**
- Python could benefit from explicit exception chaining (`from e`)
- Shell needs `trap`-based cleanup to prevent partial writes
- Tests could add more behavioral coverage beyond structural checks

**No blocking issues.** All findings are refinements, not correctness bugs.

**Approval:** PASS with recommendations.
