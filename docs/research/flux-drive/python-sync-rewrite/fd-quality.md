# fd-quality Review

## Findings

### [P0] Missing pytest configuration in tests/pyproject.toml
Task 1 Step 2 (line 42-124) imports from `clavain_sync.config` but PYTHONPATH is set in bash commands, not in pytest config. The existing project test suite uses `tests/pyproject.toml` (per MEMORY.md) with `uv run pytest` commands. However, the plan shows raw `python3 -m pytest` commands with `PYTHONPATH=scripts` environment variable instead of proper pytest configuration.

Recommendation: Add a pytest.ini or update tests/pyproject.toml to configure `pythonpath = ["scripts"]` so tests can import clavain_sync modules without manual PYTHONPATH setup. Check existing tests/pyproject.toml for pattern.

### [P1] Test fixture organization inconsistent with project convention
The plan creates fixtures inline in test modules (lines 56-83, sample_config fixture). The project uses a centralized conftest.py pattern (see tests/structural/conftest.py) with session-scoped fixtures. For consistency, common test fixtures like `sample_config`, `FIXTURE_DIR` paths, and mock helpers should be in tests/structural/test_clavain_sync/conftest.py rather than defined in individual test files.

Recommendation: Create tests/structural/test_clavain_sync/conftest.py with shared fixtures and constants. Individual test files should import from conftest where appropriate.

### [P1] Inconsistent parametrize usage
The plan uses pytest.mark.parametrize in test_classify.py (lines 432-584) with a class wrapper (`class TestClassifyFile:`) but doesn't parametrize the actual test functions — each test case is a separate function. The project convention (see test_skills.py lines 34-90) is to use parametrize decorators at function level when testing multiple inputs, and to use descriptive test function names for single-case tests.

The classify tests would be clearer as either:
1. Multiple parametrized tests grouped by concern (e.g., `test_skip_outcomes` with 3 cases, `test_three_way_outcomes` with 4 cases)
2. Keep as separate functions but remove the class wrapper (not used elsewhere in project)

Recommendation: Remove the `class TestClassifyFile:` wrapper. Either keep as separate functions with descriptive names (current style is acceptable) or refactor into parametrized tests grouped by classification category.

### [P1] Import ordering not specified
The plan shows import blocks but doesn't follow a consistent ordering pattern. The project uses standard Python import conventions but the plan mixes stdlib, third-party, and local imports without clear separation.

Recommendation: Enforce import ordering in all modules:
```python
# stdlib
from __future__ import annotations
import json
from pathlib import Path

# third-party (none in this package)

# local
from .config import load_config
from .namespace import apply_replacements
```

### [P1] Error messages lack context in state.py
Line 1008-1009 shows a silent noop when an unknown upstream is passed to `update_synced_commit`. This could hide bugs where a typo in upstream name prevents state updates.

Recommendation: Either log a warning or raise ValueError for unknown upstream names. If silent noop is intentional, add a comment explaining why (e.g., "defensive programming — caller may not know which upstreams exist").

### [P2] Test naming convention inconsistency
Most test functions use underscores (test_load_config_missing_file) which is correct. However, some test names are verbose where project convention prefers concise names. Compare:
- Plan: `test_load_config_returns_upstream_list` (line 86)
- Project: `test_plugin_json_valid` (test_plugin_manifest.py line 7)

Recommendation: Shorten test names where the assertion makes intent clear. E.g., `test_load_config_returns_upstream_list` → `test_load_config_parses_upstreams`.

### [P2] Docstrings missing from test functions
The project test suite uses consistent docstrings for all test functions (see test_skills.py, test_plugin_manifest.py). The plan shows docstrings for module-level and some test classes but not all test functions.

Recommendation: Add brief docstrings to all test functions describing what they verify, matching project style:
```python
def test_load_config_missing_file():
    """Config loader raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/upstreams.json"))
```

### [P2] Type hints on test functions
The plan omits return type hints (`-> None`) on test functions. This is acceptable (pytest doesn't require it) but for consistency with potential future type checking, consider adding them.

Recommendation: Add `-> None` to all test functions for consistency, or explicitly decide not to (both are valid Python conventions).

### [P2] Magic numbers in test data
Line 64 shows `"lastSyncedCommit": "abc123" * 7 + "ab"` to generate a 40-char hash. This is clever but obscure. The project prefers readable test data.

Recommendation: Use explicit hash strings or a named constant:
```python
FAKE_COMMIT_HASH = "a" * 40  # Git SHA-1
```

### [P2] Fixture naming style
The plan uses leading underscores for private test helpers (`_mock_claude_result` line 723, `_AiEntry` line 1093). The project uses leading underscores for module-private functions (helpers.py line 6, `parse_frontmatter` is public, no examples of private test helpers). Pytest convention is that test helper functions should not have leading underscores unless truly internal.

Recommendation: Rename `_mock_claude_result` → `mock_claude_result`, keep `_AiEntry` as-is (it's a private dataclass in report.py).

### [P2] Parametrize IDs missing
Test parametrize decorators in the project use explicit `ids` (test_skills.py line 34: `ids=lambda p: p.name`). The plan's parametrize examples don't show IDs, which would make test output less readable.

Recommendation: If refactoring to parametrize, add explicit `ids` parameters for readable pytest output.

### [P2] NO_COLOR handling
The __main__.py module (lines 1297-1301) checks NO_COLOR environment variable but doesn't strip ANSI codes from subprocess output. If Claude Code sets NO_COLOR, the Python script respects it, but underlying git commands may still emit color codes.

Recommendation: Consider passing `--no-color` to git commands or using `git -c color.ui=never` when NO_COLOR is set. This is a minor polish issue.

### [P2] Subprocess timeout consistency
The resolve.py module uses `timeout=120` (line 891) but git_ops.py has no timeouts on subprocess.run calls. For defensive programming, long-running git operations (fetch, diff) should have timeouts.

Recommendation: Add reasonable timeouts to git commands (e.g., 300s for fetch, 60s for diff/show).

### [P2] Path handling uses / operator but inconsistent str() casting
Most code uses Path objects throughout (good), but git_ops.py casts to str in some places (line 1198: `str(clone_dir)`) but not others (line 1256 builds string path instead of using Path). Be consistent: either use Path throughout and only cast at subprocess boundary, or cast early.

Recommendation: Cast to str only in subprocess.run arguments for clarity. Keep Path objects until then.

### [P2] Dataclass default_factory usage
The report.py module uses `field(default_factory=list)` correctly (line 1103-1104), but config.py uses mutable defaults incorrectly avoided via explicit defaults. However, _raw_path uses `field(repr=False, default=Path())` which creates a single shared Path instance (line 162). This should be `default_factory=Path`.

Recommendation: Change line 162 to `_raw_path: Path = field(repr=False, default_factory=Path)`.

## Summary

The plan demonstrates solid Python 3.12+ style with dataclasses, type hints, and comprehensive test coverage. Code organization into 7 modules is clean and follows single-responsibility principles. Test coverage is thorough with 40+ test cases covering all classification paths.

Main quality improvements needed:
1. **P0**: Pytest configuration must use project's pyproject.toml or pytest.ini, not manual PYTHONPATH
2. **P1**: Centralize test fixtures in conftest.py to match project convention
3. **P1**: Add error handling for unknown upstream names in state management
4. **P1**: Standardize import ordering across all modules

The code quality is production-ready after addressing P0/P1 issues. P2 items are polish — they improve consistency with project conventions but don't block implementation. The modular design (pure classify.py, testable components) is excellent and significantly better than the 1,020-line bash script.

Type hints are modern (using `|` union syntax, `dict[str, str]` generics) which requires Python 3.10+. The plan specifies 3.12+ so this is correct. Dataclass usage is idiomatic. Error handling is appropriate (explicit raises, fallback patterns in AI resolution).

Test patterns are slightly more verbose than project convention but comprehensive. After addressing fixture organization and pytest config, the test suite will integrate cleanly with existing structural tests.
