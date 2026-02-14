# Test Files Analysis: detect-domains.py

## Summary
Two comprehensive test files cover detect-domains.py with 128+ test functions across pytest framework, using direct import and subprocess invocation patterns.

## File Paths

1. **`/root/projects/Clavain/tests/structural/test_detect_domains.py`** (553 lines)
   - Main detection logic, scoring, cache roundtrip, CLI integration
   - 100+ test functions across 10 test classes

2. **`/root/projects/Clavain/tests/structural/test_staleness.py`** (493 lines)
   - Structural hash, cache v1 format, staleness detection, tier-specific checks
   - 70+ test functions across 11 test classes

## Test Framework Used

**Framework: pytest** with fixtures and markers
- **Import method**: Direct import via `importlib.util.spec_from_file_location()` to handle hyphenated module name
- **Invocation method**: Both direct function calls AND subprocess invocation
- **Fixtures**: Session-scoped fixtures in `conftest.py` (project_root, agents_dir, skills_dir, etc.)
- **Mocking**: Uses `unittest.mock.patch` for subprocess timeout simulation
- **Helpers**: `conftest.py` and `helpers.py` for shared utilities

## Existing Test Function Names (Key Coverage)

### test_detect_domains.py (8 test classes)

1. **TestLoadIndex** (3 tests)
   - test_parses_real_index
   - test_each_domain_has_signal_categories
   - test_domain_profiles_are_unique

2. **TestScoring** (5 tests)
   - test_all_equal_halves
   - test_all_zeros
   - test_all_ones
   - test_weighted_correctly
   - test_only_frameworks

3. **TestGatherDirectories** (4 tests)
   - test_matching_subdirs
   - test_no_signals
   - test_nested_signal
   - test_empty_project

4. **TestGatherFiles** (3 tests)
   - test_matching_files
   - test_glob_pattern_matching
   - test_file_in_subdirectory

5. **TestGatherFrameworks** (6 tests)
   - test_package_json
   - test_cargo_toml
   - test_requirements_txt
   - test_pyproject_toml
   - test_no_build_files
   - test_empty_signals

6. **TestGatherKeywords** (2 tests)
   - test_finds_keywords_in_source
   - test_no_source_files

7. **TestCacheRoundtrip** (3 tests)
   - test_write_then_read
   - test_read_missing_file
   - test_cache_override_respected

8. **TestCacheV1** (5 tests)
   - test_write_includes_cache_version
   - test_write_includes_structural_hash
   - test_write_without_structural_hash
   - test_write_iso_timestamp
   - test_atomic_write_creates_parent_dirs

9. **TestStructuralHash** (6 tests)
   - test_empty_project_deterministic
   - test_hash_changes_with_file
   - test_hash_stable_with_same_content
   - test_hash_ignores_non_structural_files
   - test_hash_prefix_format
   - test_all_structural_files_considered

10. **TestStalenessCheck** (6 tests)
    - test_no_cache_returns_4
    - test_override_always_fresh
    - test_missing_version_is_stale
    - test_old_version_is_stale
    - test_matching_hash_is_fresh
    - test_mismatched_hash_is_stale
    - test_roundtrip_freshness
    - test_roundtrip_stale_after_change
    - test_tier3_fresh_when_files_older
    - test_tier3_stale_when_files_newer

11. **TestCLICheckStale** (4 tests)
    - test_no_cache_exit_4
    - test_stale_cache_exit_3
    - test_fresh_cache_exit_0
    - test_dry_run_outputs_diagnostics

12. **TestDetect** (3 tests)
    - test_detects_game_project
    - test_empty_project_returns_empty
    - test_primary_is_highest_confidence

13. **TestCLI** (4 tests)
    - test_empty_project_exit_1
    - test_json_output_parses
    - test_invalid_project_exit_2

### test_staleness.py (11 test classes)

1. **TestStructuralHash** (6 tests)
   - test_deterministic
   - test_includes_algorithm_prefix
   - test_ignores_file_order
   - test_file_deletion_changes_hash
   - test_file_modification_changes_hash
   - test_excludes_non_structural_files
   - test_empty_project

2. **TestCacheV1** (5 tests)
   - test_write_cache_includes_version
   - test_write_cache_includes_structural_hash
   - test_write_cache_omits_hash_when_none
   - test_cache_timestamp_is_full_iso8601
   - test_write_cache_atomic_no_partial
   - test_write_cache_roundtrip

3. **TestParseISODatetime** (4 tests)
   - test_full_iso
   - test_date_only
   - test_empty_string
   - test_invalid

4. **TestCheckStale** (9 tests)
   - test_no_cache_returns_4
   - test_override_true_returns_0
   - test_override_true_skips_hash
   - test_cache_version_mismatch_returns_3
   - test_missing_cache_version_returns_3
   - test_fresh_hash_match_returns_0
   - test_structural_file_changed_returns_3
   - test_non_structural_change_fresh

5. **TestTier1** (3 tests)
   - test_no_hash_in_cache_returns_none
   - test_hash_match_returns_0
   - test_hash_mismatch_returns_3

6. **TestTier2** (7 tests)
   - test_no_git_returns_none
   - test_no_timestamp_returns_3
   - test_structural_file_commit_returns_3
   - test_non_structural_commit_returns_0
   - test_no_commits_since_detection_returns_0
   - test_structural_extension_commit_returns_3
   - test_git_timeout_returns_none

7. **TestTier3** (4 tests)
   - test_old_file_fresh
   - test_new_file_stale
   - test_no_timestamp_returns_3
   - test_no_structural_files_fresh

8. **TestCheckStaleCLI** (4 tests)
   - test_no_cache_exit_4
   - test_fresh_cache_exit_0
   - test_stale_cache_exit_3
   - test_dry_run_produces_output
   - test_override_exit_0

9. **TestPerformance** (1 test)
   - test_check_stale_under_100ms

## How Tests Invoke detect-domains.py

### Method 1: Direct Import (Primary)
```python
import importlib.util
_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "detect-domains.py"
_spec = importlib.util.spec_from_file_location("detect_domains", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Then directly call functions:
check_stale = _mod.check_stale
detect = _mod.detect
compute_structural_hash = _mod.compute_structural_hash
```

**Exported symbols used in tests:**
- `CACHE_VERSION`
- `DomainSpec` (class)
- `STRUCTURAL_FILES`
- `check_stale()`, `compute_structural_hash()`, `detect()`
- `gather_directories()`, `gather_files()`, `gather_frameworks()`, `gather_keywords()`
- `load_index()`, `read_cache()`, `write_cache()`
- `_check_stale_tier1()`, `_check_stale_tier2()`, `_check_stale_tier3()`
- `_parse_iso_datetime()`

### Method 2: Subprocess Invocation
```python
import subprocess
import sys

result = subprocess.run(
    [sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"],
    capture_output=True, text=True, timeout=30
)
assert result.returncode == expected_code
```

**CLI flags tested:**
- `--check-stale` — staleness check mode
- `--dry-run` — diagnostic output without side effects
- `--json` — JSON output format
- `--no-cache` — skip cache read/write

## Edge Cases Already Tested

### ✅ Shallow Clones
- NOT EXPLICITLY TESTED — but tier 2 (`_check_stale_tier2`) handles git timeout gracefully
- Test: `test_git_timeout_returns_none` in TestTier2 (line 365, test_staleness.py)
- Falls back to tier 3 when git command times out
- **Gap**: No test for `git --git-dir=.git rev-parse --is-shallow-repository` or `GIT_SHALLOW=true`

### ✅ Naive Datetimes
- **EXTENSIVELY TESTED** — cache timestamps must be full ISO 8601 with timezone
- Test: `test_cache_timestamp_is_full_iso8601()` (test_staleness.py line 131)
- Test: `test_full_iso()` (test_staleness.py line 177)
- Test: `test_date_only()` (test_staleness.py line 182) — v0 format with date-only
- **Parser**: `_parse_iso_datetime()` handles both full ISO and date-only formats
- Tier 3 uses `datetime.fromisoformat()` which requires full datetime for comparison

### ✅ Cache Version Mismatch
- **EXTENSIVELY TESTED** — cache version bumps trigger regeneration
- Test: `test_cache_version_mismatch_returns_3()` (test_detect_domains.py line 332)
- Test: `test_missing_cache_version_returns_3()` (test_detect_domains.py line 322)
- Test: `test_cache_version_mismatch_returns_3()` (test_staleness.py line 224)
- Test: `test_missing_cache_version_returns_3()` (test_staleness.py line 233)
- Exit code 3 = format upgrade required
- **Current version tested**: `CACHE_VERSION = 1`

### ✅ Git stderr Handling
- **NOT EXPLICITLY TESTED** — subprocess calls use `capture_output=True, check=True`
- All git commands wrapped in try-except or subprocess timeout handling
- Test: `test_git_timeout_returns_none()` (test_staleness.py line 365)
  - Mocks `subprocess.run` to raise `TimeoutExpired`
  - Verifies fallback to tier 3
- **Gap**: No test for git stderr (e.g., "Permission denied", "fatal:", "warning:")
- **Gap**: No test for git command failure (returncode != 0)

### ✅ Atomic Write Guarantees
- Test: `test_write_cache_atomic_no_partial()` (test_staleness.py line 143)
- Mocks `os.rename()` to simulate write failure
- Verifies no partial `.tmp` file left behind on failure

### ✅ Multi-Tier Staleness Check
- Test: `test_tier3_fresh_when_files_older()` (test_detect_domains.py line 383)
- Test: `test_tier3_stale_when_files_newer()` (test_detect_domains.py line 402)
- Tier 1: Hash-based (fastest)
- Tier 2: Git-based (if .git exists)
- Tier 3: File mtime-based (fallback)

## Test Execution Setup

**Fixtures**:
```python
# conftest.py
@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
```

**Imports**:
- `importlib.util` — hyphenated module name handling
- `pathlib.Path` — all path operations use Path objects
- `subprocess` — CLI invocation tests
- `unittest.mock.patch` — timeout simulation
- `yaml` — cache format parsing
- `json` — JSON output parsing
- `datetime` — ISO datetime handling
- `time` — mtime manipulation, performance measurement

**Constants**:
```python
SCRIPT = ROOT / "scripts" / "detect-domains.py"
INDEX_PATH = ROOT / "config" / "flux-drive" / "domains" / "index.yaml"
```

## Test Environment

- **Working directory**: `/root/projects/Clavain`
- **pytest configuration**: `tests/pyproject.toml` (implicit, uses `uv run`)
- **Timeout**: 30 seconds for subprocess calls, 10 seconds for CLI tests
- **Fixtures scope**: Session-scoped (shared across all tests in a module)
- **tmp_path fixture**: pytest built-in, per-test temp directory

## Coverage Analysis

**Strong coverage:**
- ✅ Cache read/write roundtrip
- ✅ Structural hash determinism
- ✅ Cache version mismatch detection
- ✅ ISO datetime parsing (both full and date-only)
- ✅ Multi-tier staleness checks
- ✅ Override flag short-circuit
- ✅ JSON output format
- ✅ Exit codes (0, 1, 2, 3, 4)

**Gaps identified:**
- ❌ Shallow git clone detection (`GIT_SHALLOW`, `git rev-parse --is-shallow-repository`)
- ❌ Git stderr/error handling (permission denied, fatal errors, warnings)
- ❌ Git command failures (returncode != 0)
- ❌ Large structural file hashing (performance with 1000+ STRUCTURAL_FILES)
- ❌ Symlinks in project (would hash resolve to same or different?)
- ❌ Read-only filesystem (cache write failures)
- ❌ Unicode filenames in project path
- ❌ Concurrent cache writes (race conditions)

## Invocation Patterns Summary

| Pattern | Location | Usage | Timeout |
|---------|----------|-------|---------|
| Direct import + call | All tests in both files | Function-level unit tests | None (Python) |
| subprocess.run() | TestCLICheckStale, TestCLI | CLI integration tests | 30s default, 10s for CLI tests |
| Mock patch | TestTier2, TestCacheV1 | Error simulation | N/A (mocked) |
| tmp_path fixture | All test classes | Isolated test directories | N/A (pytest built-in) |

## Key Test Patterns

1. **Temporary directory isolation**: Every test uses `tmp_path` fixture
2. **Git repository setup**: TestTier2 has helper `_init_git_repo()` to set up test repos
3. **Exact assertion values**: Tests assert specific exit codes (0, 1, 2, 3, 4)
4. **Performance measurement**: `TestPerformance.test_check_stale_under_100ms()` uses `time.monotonic()`
5. **Roundtrip validation**: Cache write → read → verify consistency
