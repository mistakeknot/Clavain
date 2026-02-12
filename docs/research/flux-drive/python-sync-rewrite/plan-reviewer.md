# Plan Review: Python Sync Rewrite

## Findings

### [P0] Glob expansion implementation is incomplete

**Description:** Task 3's `resolve_local_path()` uses Python's `fnmatch` for glob matching, but the bash version has additional logic in `expand_file_map()` (lines 175-202) that actually expands globs against the filesystem before applying mappings. The Python version only does pattern matching at resolution time, which may not handle all cases correctly.

The bash version calls Python to expand globs:
```python
# From bash lines 175-202
# Expands patterns like "references/*" by listing actual files in upstream dir
```

**Issue:** The Python filemap.py module doesn't expand globs against the upstream directory — it only does pattern matching. This could miss files if the upstream has new files that match a glob pattern.

**Recommendation:** Add a `expand_glob_patterns()` function in `filemap.py` that takes the clone directory and base path, lists actual files, and pre-expands glob patterns. OR: ensure that `get_changed_files()` in Task 8 returns ALL changed files and then filter through the fileMap (which is what the bash version does).

**Verdict:** The current approach in Task 8's `__main__.py` is actually correct — it gets changed files from git diff, then resolves each through `resolve_local_path()`. This matches the bash logic. **No blocker, but document this clearly in filemap.py.**

---

### [P0] Missing dependency chain validation for parallel execution

**Description:** The plan states Tasks 1-7 can run in parallel, but there are hidden dependencies:

- **Task 4 (classify.py)** imports from `namespace.py` (Task 2) and indirectly needs the classification enum that other modules depend on
- **Task 5 (resolve.py)** defines the `ConflictDecision` dataclass but doesn't import or use `classify.py`'s `Classification` enum
- **Task 7 (report.py)** imports `Classification` from `classify.py` (Task 4)

**Issue:** If Codex agents run Tasks 5 and 7 before Task 4 completes, they'll hit import errors during test runs.

**Recommendation:** 
1. Revise parallelization: Tasks 1-3 and 5 can run in parallel. Tasks 4, 6, 7 must run AFTER Task 4 is merged (because they import from it).
2. OR: Have each task's test use mocks/stubs for imports so they can run independently.
3. OR: Use a two-wave approach: Wave 1 (Tasks 1-3, 5), Wave 2 (Tasks 4, 6, 7), Wave 3 (Task 8).

**Verdict:** Actual dependency graph:
```
Wave 1: Tasks 1, 2, 3, 5, 6 (no cross-dependencies)
Wave 2: Task 4 (imports namespace from Task 2)
Wave 3: Task 7 (imports Classification from Task 4)
Wave 4: Task 8 (imports everything)
```

---

### [P0] PYTHONPATH handling is fragile

**Description:** All test commands use `PYTHONPATH=scripts` to make `clavain_sync` importable. This works for manual runs but breaks in several scenarios:

1. **pytest.ini or pyproject.toml config** — The plan has tests in `tests/pyproject.toml` but doesn't configure PYTHONPATH there
2. **IDE test runners** — Won't pick up PYTHONPATH from shell commands
3. **CI environments** — Requires explicit PYTHONPATH export in GitHub Actions

**Issue:** Tests will fail when run via `pytest` without explicit PYTHONPATH, causing confusion during review.

**Recommendation:** Add this to `tests/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["scripts"]
```

This makes PYTHONPATH implicit for all pytest runs.

---

### [P1] Missing integration test for namespace replacement edge cases

**Description:** The bash version applies namespace replacements in multiple places:
- To upstream content before comparison (line 294)
- To ancestor content before comparison (line 324)
- To files after copying (line 884 via `apply_namespace_replacements_to_file()`)

The Python version handles this in `classify.py` (lines 66-67) and `__main__.py` (lines 149-152), but there's no test verifying that:
1. Replacements are applied to BOTH upstream and ancestor (not local)
2. Replacements are applied during file copy
3. Multiple replacements are applied in correct order

**Issue:** test_classify.py has `test_namespace_replacement_applied_to_upstream_and_ancestor()`, but it only tests COPY classification, not the actual file write path.

**Recommendation:** Add to Task 8's integration tests:
```python
def test_namespace_replacements_applied_on_copy(tmp_path):
    # Create mock upstream with old namespace
    # Run sync
    # Verify local file has new namespace
```

---

### [P1] AI conflict resolution prompt differs from bash version

**Description:** Compare bash prompt (lines 429-452) vs Python prompt in Task 5 (resolve.py):

**Bash version includes:**
- Three-way content display (ancestor/local/upstream)
- Blocklist check instruction
- Decision enum (accept_upstream/keep_local/needs_human)
- Risk enum (low/medium/high)

**Python version includes:** Same, BUT:
- Uses `f-string` for prompt construction, which is cleaner
- Uses `--json-schema` with structured output (better than bash's plain JSON parse)
- Uses `--max-turns 1` (bash doesn't specify)

**Issue:** The prompts are functionally equivalent, but the bash version has more context about "orthogonal changes" which could affect AI quality.

**Recommendation:** Ensure the Python prompt matches bash verbatim, or document why it differs. The current Python prompt is actually BETTER (shorter, clearer), but reviewers may flag the difference.

---

### [P1] Contamination check runs before report generation

**Description:** In the bash version (lines 971-1003), contamination check runs BEFORE the final summary and report. In the Python version (Task 8, __main__.py lines 386-405), it runs in the same order.

**Issue:** This is correct, but the bash version prints contamination warnings to stdout, which pollutes the report if `--report` is used without a file. The Python version should write contamination warnings to stderr, not stdout.

**Recommendation:** In `run_contamination_check()`, ensure all print statements go to stderr (already done in the provided code via explicit print calls, but verify).

---

### [P1] Missing --upstream filter validation

**Description:** The bash version (line 649) checks if `FILTER_UPSTREAM` is non-empty and skips upstreams that don't match. The Python version does the same (line 335). BUT: neither version validates that the specified upstream name exists in the config.

**Issue:** Running `sync-upstreams.sh --upstream nonexistent` will silently do nothing instead of erroring.

**Recommendation:** In Task 8's `main()`, after loading config, validate `args.upstream` against `cfg.upstreams[*].name` and error if not found:
```python
if args.upstream:
    names = [u.name for u in cfg.upstreams]
    if args.upstream not in names:
        print(f"ERROR: Unknown upstream '{args.upstream}'. Available: {', '.join(names)}", file=sys.stderr)
        sys.exit(1)
```

---

### [P1] Regression test comparison is too loose

**Description:** Task 10's `test_python_matches_bash_classifications()` uses regex to extract `(COPY|AUTO|KEEP|SKIP|CONFLICT|REVIEW)\s+(\S+)` from both outputs and compares sets.

**Issue:** This won't catch:
1. Different classification reasons (e.g., `SKIP:protected` vs `SKIP:deleted-locally`)
2. Different file counts in summaries
3. AI decision differences

**Recommendation:** Enhance the regex to capture full classification strings:
```python
cls_pattern = re.compile(r"(COPY|AUTO|KEEP|SKIP:[^\\s]+|CONFLICT|REVIEW:[^\\s]+)\\s+(\\S+)")
```

Also add a separate count comparison:
```python
bash_summary = re.search(r"(\d+) copied.* (\d+) auto.* (\d+) kept.* (\d+) conflict", bash_result.stdout)
python_summary = re.search(r"(\d+) copied.* (\d+) auto.* (\d+) kept.* (\d+) conflict", python_result.stdout)
assert bash_summary.groups() == python_summary.groups()
```

---

### [P2] No test for interactive mode fallback

**Description:** Task 8's `handle_conflict_interactive()` logic is not implemented in the initial Python version (the bash version has it at lines 481-574). The plan notes "Interactive mode: would need tty handling (not implemented in first iteration)" (line 348).

**Issue:** This means `--auto` mode is fully covered, but interactive mode will fall through. The plan should either:
1. Implement a basic interactive handler in Task 8
2. Add a SKIP or NotImplementedError for interactive mode
3. Document this as a known limitation

**Recommendation:** Add to Task 8's `sync_upstream()` in the CONFLICT handler:
```python
elif mode == "interactive":
    print(f"  {YELLOW}(interactive mode not yet implemented — skipping){NC}")
```

OR: Implement `handle_conflict_interactive()` in a separate Task 8.5 after the core logic is verified.

---

### [P2] Missing fileMap validation on load

**Description:** The bash version doesn't validate fileMap entries, but the Python version could. Invalid patterns (e.g., missing `*` in dst when src has `*`) will cause silent failures.

**Issue:** A fileMap like `"src/*": "dst"` (no `*` in dst) will break glob expansion. The bash version doesn't validate this either, so it's not a regression, but it's an opportunity for improvement.

**Recommendation:** In `config.py`'s `load_config()`, add validation:
```python
for src, dst in u.file_map.items():
    if "*" in src and "*" not in dst:
        raise ValueError(f"Invalid fileMap in {u.name}: '{src}' has glob but '{dst}' does not")
```

This would catch config errors early instead of silently failing during sync.

---

### [P2] No test for empty or malformed ancestor content

**Description:** The bash version calls `get_ancestor_content()` (line 159) which returns empty string if the file doesn't exist at that commit. The Python version in Task 8 (git_ops.py) does the same (returns None on error).

**Issue:** test_classify.py has `test_review_new_upstream_file()` which tests `ancestor_content=None`, but there's no test for the edge case where `ancestor_content=""` (empty file at ancestor).

**Recommendation:** Add to test_classify.py:
```python
def test_auto_with_empty_ancestor():
    result = classify_file(
        local_path="file.md",
        local_content="",  # Empty locally
        upstream_content="new content",
        ancestor_content="",  # Empty at ancestor
        protected_files=set(),
        deleted_files=set(),
        namespace_replacements={},
        blocklist=[],
    )
    assert result == Classification.AUTO
```

---

### [P2] Deprecation notice placement

**Description:** Task 9 adds a deprecation notice to the top of `sync-upstreams.sh` (lines 1-5). This is good, but the bash version has 1,020 lines. Reviewers may not see the notice if they jump into the middle of the file.

**Issue:** The deprecation notice should also appear in the script's help text (lines 56-74 in the bash version).

**Recommendation:** In Task 9, update the help text to include:
```bash
echo "DEPRECATED: Use 'python3 -m clavain_sync sync' instead (faster, testable)."
echo "Legacy bash version available via 'pull-upstreams.sh --sync --legacy'."
echo ""
```

---

## Missing Coverage Analysis

### Bash features NOT covered in the plan:

1. **Interactive mode diff navigation** (bash lines 538-556): The Python version doesn't implement the `(3)-way view` option or the `(d)iff again` loop for REVIEW files. This is noted as "not implemented in first iteration" but should be tracked as a follow-up.

2. **Color handling via NO_COLOR env var** (bash line 31-38): The Python version checks `NO_COLOR` (Task 8, line 21) ✅

3. **Upstreams directory auto-detection** (bash lines 20-27): The Python version implements this (Task 8, lines 60-68) ✅

4. **lastSyncedCommit unreachable error** (bash lines 723-729): The Python version implements this (Task 8, lines 279-282) ✅

5. **Report generation** (bash lines 606-651): The Python version implements this (Task 7) ✅

6. **AI decision metadata in report** (bash lines 634-642): The Python version implements this (Task 7, lines 58-64) ✅

7. **Blocklist term detection in upstream** (bash lines 366-371): The Python version implements this (Task 4, classify.py lines 82-86) ✅

8. **Protected file skip** (bash lines 287-290): The Python version implements this (Task 4, classify.py lines 53-54) ✅

9. **Deleted file skip** (bash lines 293-296): The Python version implements this (Task 4, classify.py lines 56-57) ✅

10. **Not-present-locally skip** (bash lines 299-302): The Python version implements this (Task 4, classify.py lines 59-60) ✅

**Verdict:** All major bash features are covered except interactive mode prompts. This is acceptable for a first iteration.

---

## Task Dependency Validation

### Can Tasks 1-7 truly run in parallel?

**Analysis:**

- **Task 1** (config.py): No dependencies ✅
- **Task 2** (namespace.py): No dependencies ✅
- **Task 3** (filemap.py): No dependencies ✅
- **Task 4** (classify.py): **Imports namespace.py (Task 2)** ❌
- **Task 5** (resolve.py): No dependencies ✅
- **Task 6** (state.py): No dependencies ✅
- **Task 7** (report.py): **Imports classify.py (Task 4)** ❌

**Correct parallelization:**
- **Wave 1:** Tasks 1, 2, 3, 5, 6 (true parallel)
- **Wave 2:** Task 4 (after Task 2 merges)
- **Wave 3:** Task 7 (after Task 4 merges)
- **Wave 4:** Task 8 (after all previous tasks merge)

**OR:** Use mocked imports in tests to avoid blocking (e.g., Task 7's tests mock `Classification` until Task 4 is merged).

---

## Test Adequacy Assessment

### Are all 7 classification paths tested?

From test_classify.py (Task 4):

1. ✅ `test_skip_protected` → `Classification.SKIP_PROTECTED`
2. ✅ `test_skip_deleted_locally` → `Classification.SKIP_DELETED`
3. ✅ `test_skip_not_present_locally` → `Classification.SKIP_NOT_PRESENT`
4. ✅ `test_copy_identical_after_replacement` → `Classification.COPY`
5. ✅ `test_auto_upstream_only_changed` → `Classification.AUTO`
6. ✅ `test_keep_local_only_changed` → `Classification.KEEP_LOCAL`
7. ✅ `test_conflict_both_changed` → `Classification.CONFLICT`
8. ✅ `test_review_new_upstream_file` → `Classification.REVIEW_NEW`
9. ✅ `test_auto_blocked_by_blocklist` → `Classification.REVIEW_BLOCKLIST` (via name check)

**Verdict:** All paths covered. Edge case tests also present (namespace replacement, empty maps, etc.).

---

## Integration Gaps

### Does Task 8 properly import and use all modules?

**Checklist:**

- ✅ Imports `classify.py` (line 15)
- ✅ Imports `config.py` (line 16)
- ✅ Imports `filemap.py` (line 17)
- ✅ Imports `git_ops.py` (line 18)
- ✅ Imports `namespace.py` (line 27)
- ✅ Imports `report.py` (line 28)
- ✅ Imports `resolve.py` (line 29)
- ✅ Imports `state.py` (line 30)

**Usage validation:**

- `load_config()` — called at line 322 ✅
- `resolve_local_path()` — called at line 297 ✅
- `fetch_and_reset()` — called at line 272 ✅
- `classify_file()` — called at line 315 ✅
- `apply_replacements()` — called at line 152 ✅
- `SyncReport()` — instantiated at line 330 ✅
- `analyze_conflict()` — called at line 352 ✅
- `update_synced_commit()` — called at line 382 ✅

**Verdict:** All modules are imported and used correctly in Task 8.

---

## Summary

**Overall Assessment:** The plan is **well-structured and comprehensive**, covering all major bash functionality except interactive mode (which is deferred). The TDD approach ensures testability, and the 7-outcome classification logic is properly preserved.

**Critical issues (P0):**
1. Task dependencies are not truly parallel — requires wave-based execution or mocked imports
2. PYTHONPATH handling needs pytest.ini config for robustness

**Important improvements (P1):**
5. Namespace replacement integration test needed
6. AI prompt should match bash verbatim (or document differences)
7. `--upstream` filter should validate against config
8. Regression test should capture full classification strings, not just types

**Nice-to-haves (P2):**
4. Interactive mode should have a "not implemented" stub
5. FileMap validation on load
6. Empty ancestor content edge case test
7. Deprecation notice in help text

**Recommendation:** Address P0 issues before parallel execution. P1 issues can be fixed during review. P2 issues are enhancements, not blockers.

**Execution approach:** Use 3-wave parallelization:
- **Wave 1:** Tasks 1, 2, 3, 5, 6 (parallel)
- **Wave 2:** Task 4 (after Wave 1 merges)
- **Wave 3:** Task 7 (after Task 4 merges)
- **Wave 4:** Tasks 8-11 (sequential, integration phase)
