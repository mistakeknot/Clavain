# fd-architecture Review

## Findings

### [P0] Module circular dependency risk in classify.py
**Location:** Task 4, `classify.py` imports from `namespace.py`

The classification module imports `apply_replacements` and `has_blocklist_term` from `namespace.py`. While this is a clean abstraction today, the plan puts both modules in Tasks 2 and 4 with independent execution. If classification logic ever needs to be called from namespace processing (e.g., for validation during replacement), you create a circular dependency.

**Recommendation:** Document in `classify.py` that it is a *consumer* of namespace operations, never a provider. Consider marking `namespace.py` as a "leaf" module in comments to prevent future imports from it.

**Risk if unfixed:** Low immediate risk (current design is clean), but medium long-term risk if modules evolve without clear dependency direction.

---

### [P1] File map resolution lacks basePath-stripping contract clarity
**Location:** Task 3, `filemap.py` function signature and bash comparison (lines 214-260)

The bash version strips `basePath` *before* calling `resolve_local_path` (line 700-702 in bash script), but the Python `resolve_local_path` receives `changed_file` with no explicit contract about whether basePath has already been removed. The plan's `__main__.py` (lines 1379-1381) also strips basePath before calling `resolve_local_path`, meaning the function assumes pre-stripped input.

However, the test suite in Task 3 (`test_filemap.py`) has no test case covering basePath-prefixed input to verify the function rejects or handles it correctly. The glob expansion logic in `filemap.py` also doesn't account for basePath at all — it just does pattern matching on whatever string is passed.

**Recommendation:**
1. Add a docstring to `resolve_local_path` explicitly stating: "changed_file MUST be relative to basePath (caller strips basePath before calling this function)".
2. Add a test case: `test_basepath_already_stripped` that documents expected behavior if basePath is accidentally left in the input.
3. Consider adding an assertion or validation in `resolve_local_path` to detect and reject paths containing the basePath prefix (requires passing basePath as a parameter for validation).

**Risk if unfixed:** Medium — wrong file mappings if basePath stripping is forgotten in a new call site.

---

### [P1] Missing glob expansion boundary — fileMap patterns with multiple wildcards
**Location:** Task 3, `filemap.py` lines 390-398

The glob matching logic splits on `*` and uses `split("*")[0]` to extract prefix/suffix. This breaks for patterns with multiple wildcards like `"docs/*/guides/*"` → `"skills/foo/*/references/*"`. The bash version uses `fnmatch.fnmatch` (line 249 in bash) but then does simple string prefix logic (lines 252-256) which also breaks for multi-wildcard patterns.

The test suite has `test_glob_nested` but it's testing a *single-level* glob (`docs/*` matching `docs/debug/remote-chrome.md`), not a multi-wildcard pattern. The bash version's actual fileMap entries in `upstreams.json` don't use multi-wildcard patterns today, but the plan doesn't document this as a known limitation.

**Recommendation:**
1. Add a comment to `filemap.py` documenting the limitation: "Only supports single-wildcard patterns (e.g., `src/*`). Multi-wildcard patterns like `src/*/nested/*` are not supported."
2. Add a test case `test_multi_wildcard_not_supported` that documents the expected failure mode.
3. OR: Implement proper multi-wildcard support using `pathlib.Path.match()` instead of `fnmatch.fnmatch + string splitting`.

**Risk if unfixed:** Low immediate (no multi-wildcard patterns in current fileMap), High if future upstreams add nested globs.

---

### [P1] Task independence claim is false for Tasks 1-6
**Location:** Plan overview, "can Tasks 1-7 truly run independently?"

The plan states Tasks 1-7 can run independently, but:
- Task 4 (`classify.py`) imports `namespace` from Task 2 — **cannot run until Task 2 completes**
- Task 4 tests import `Classification` enum — tests will fail if `classify.py` doesn't exist
- Task 8 (`__main__.py`) imports from *all* modules Tasks 1-7 — cannot run until all prior tasks complete

The only truly independent tasks are Tasks 1-6 *in linear order*, and Task 7 (report.py) which depends on Task 4's `Classification` enum but is otherwise isolated.

**Recommendation:** Update the plan overview to clarify: "Tasks 1-7 must be executed in order due to import dependencies. Task 7 (report) and Task 6 (state) can be parallelized after Task 4 completes. Task 8 integrates all modules and must run last."

**Risk if unfixed:** Low (plan executor will discover this immediately when tests fail), but misleading documentation.

---

### [P1] AI conflict resolution has hidden subprocess dependency on `claude` CLI
**Location:** Task 5, `resolve.py` lines 880-902

The `analyze_conflict` function shells out to `claude -p` but has no fallback if the `claude` binary is not in PATH or fails to execute. The test mocks this (line 732-736), but the production code will crash with `FileNotFoundError` if `claude` is missing, not return the `_FALLBACK` decision.

The bash version (lines 418-421) captures the exit code and falls back on error, but the Python version uses `subprocess.run(..., check=False)` inside a try/except that only catches `Exception` *after* the subprocess call succeeds. If `subprocess.run` itself raises `FileNotFoundError`, it will be caught, but if `claude` exits non-zero, `result.stdout` may be empty and `json.loads("")` will raise `JSONDecodeError`, which *is* caught.

**Recommendation:** Add an explicit check for `claude` binary existence before subprocess call:
```python
if not shutil.which("claude"):
    return _FALLBACK
```
Or document in `resolve.py` that `claude` CLI is a hard requirement.

**Risk if unfixed:** Low (test environments have `claude` installed), Medium in CI/production if `claude` is not in PATH.

---

### [P2] State management uses tempfile in parent dir without permission handling
**Location:** Task 6, `state.py` lines 1012-1020

The atomic write logic creates a tempfile in `config_path.parent` (line 1014), but if that directory is not writable or has ACL issues (common on the ethics-gradient server based on the claude-user ACL setup described in `~/.claude/CLAUDE.md`), `tempfile.NamedTemporaryFile` will raise `PermissionError`.

The bash version (lines 940-948) uses Python's `json.dump` with `f.seek(0) / f.truncate()` which rewrites the file in-place, avoiding tempfile entirely. This is less crash-safe but doesn't require write access to the parent directory.

**Recommendation:** Wrap the tempfile creation in a try/except and fall back to in-place rewrite if tempfile creation fails:
```python
try:
    with tempfile.NamedTemporaryFile(...) as tmp:
        ...
except (PermissionError, OSError):
    # Fallback: in-place rewrite (less safe but works with restrictive ACLs)
    with open(config_path, "r+") as f:
        data = json.load(f)
        # ... update logic ...
        f.seek(0); json.dump(data, f, indent=2); f.write("\n"); f.truncate()
```

**Risk if unfixed:** Low (upstreams.json is typically in a writable project directory), Medium on servers with restrictive ACLs.

---

### [P2] Git operations module has no error handling for subprocess failures
**Location:** Task 8, `git_ops.py` lines 1195-1263

All git subprocess calls use `check=False` (lines 1199, 1203, 1220, 1241), meaning they silently swallow errors. The `get_head_commit` and `count_new_commits` functions use `check=True` (lines 1211, 1229), which will raise `CalledProcessError` on failure, but no caller in `__main__.py` wraps these in try/except.

If `git rev-parse HEAD` fails (e.g., corrupted repo), the entire sync will crash instead of logging the error and moving to the next upstream. The bash version (lines 667-687) checks reachability and skips the upstream on error, but the Python version will propagate the exception.

**Recommendation:** Wrap all `check=True` subprocess calls in try/except in `__main__.py` or change them to `check=False` and validate output explicitly.

**Risk if unfixed:** Medium — one corrupted upstream clone will kill the entire sync run instead of skipping that upstream.

---

### [P2] Report generation has hardcoded classification categories
**Location:** Task 7, `report.py` lines 1114-1129

The report counts only specific classification values: `COPY`, `AUTO`, `KEEP-LOCAL`, `CONFLICT`, `SKIP`, `REVIEW`. If a new classification is added to `Classification` enum (e.g., `SKIP_BINARY` or `REVIEW_SECURITY`), the report will silently drop those entries into the wrong bucket or lose them entirely.

The bash version (lines 556-564) has the same issue — it pattern-matches on enum prefixes, which is slightly more flexible but still fragile.

**Recommendation:** Change the counting logic to iterate over all `Classification` enum members and group them by prefix:
```python
counts: dict[str, int] = defaultdict(int)
for _, cls in self.entries:
    prefix = cls.value.split(":")[0] if ":" in cls.value else cls.value
    counts[prefix] += 1
```

**Risk if unfixed:** Low (classification categories are stable), Medium if new categories are added without updating report.py.

---

### [P2] Main CLI has no validation that upstreams directory exists before sync
**Location:** Task 8, `__main__.py` lines 1304-1313

The `find_upstreams_dir` function checks two locations and exits with `sys.exit(1)` if neither exists, but the error message says "Run scripts/clone-upstreams.sh first" (line 1312). However, the function is called *after* config loading (line 1544), meaning if `upstreams.json` is valid but the clones are missing, the error message will be misleading (config was parsed successfully, but clones are gone).

The bash version checks this earlier (lines 86-89) before any config parsing.

**Recommendation:** Move the `find_upstreams_dir` call before `load_config` so the error message is displayed before attempting to parse upstreams.json.

**Risk if unfixed:** Low — error message is slightly misleading but still actionable.

---

### [P2] Classification logic missing edge case: deleted upstream file with local modifications
**Location:** Task 4, `classify.py` lines 621-689 and bash lines 736-738

The bash script skips deleted upstream files with `if [[ "$status" == "D" ]]; then continue; fi` (line 736), but there's no classification for "upstream deleted this file, but local has modifications." The Python version inherits this gap.

If upstream deletes `src/foo.md` (fileMap → `skills/foo.md`), and local has modified `skills/foo.md` since last sync, the classification will be `SKIP_NOT_PRESENT` (because upstream file doesn't exist), but the local changes will be silently preserved with no warning.

**Recommendation:** Add a new classification: `REVIEW_UPSTREAM_DELETED` for the case where:
- Upstream status is `D`
- Local file exists and differs from ancestor

This requires passing the status from `get_changed_files` into `classify_file`.

**Risk if unfixed:** Low (rare edge case), Medium if upstreams frequently delete/rename files.

---

## Summary

The plan's 7-module decomposition is **sound and well-separated**, with clean boundaries between config, namespace, filemap, classify, resolve, state, and report. The core algorithm (classify.py) is correctly isolated as pure functions, making it trivially testable.

**Critical issues (P0):**
- No blocking issues, but the circular dependency risk in classify.py should be documented to prevent future regressions.

**High-priority issues (P1):**
- File map resolution lacks basePath-stripping contract clarity and multi-wildcard support
- Task independence claim is misleading (tasks must run in order)
- AI conflict resolution will crash if `claude` CLI is missing
- Git operations will crash the entire sync on subprocess failure instead of skipping bad upstreams

**Medium-priority issues (P2):**
- State management tempfile creation may fail on restrictive ACLs
- Report generation hardcodes classification categories
- Missing edge case for upstream-deleted files with local modifications

**Preserved semantics:** The plan **correctly preserves all 7 classification outcomes** from the bash version (COPY, AUTO, KEEP-LOCAL, CONFLICT, 3 SKIP variants, 3 REVIEW variants). The three-way classification algorithm is a faithful port of bash lines 283-362.

**Missing abstractions:** None — the 7-module split is appropriately granular. Each module has a single, clear responsibility.

**Unnecessary complexity:** None — the plan avoids premature optimization (no caching, no async, no plugin system). The only subprocess calls are `git` and `claude`, which matches the bash version.

**Integration layer (Task 8):** The `__main__.py` orchestrator correctly ties all modules together, with the same loop structure as bash lines 604-1020. The contamination check and report generation are properly separated into helper functions.

**Recommendation:** Fix P1 issues before execution. P2 issues can be deferred to a cleanup pass after the initial rewrite is verified to work. Document the P0 circular dependency risk to prevent future violations.
