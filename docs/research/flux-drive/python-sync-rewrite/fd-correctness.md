# fd-correctness Review

## Findings

### [P1] Namespace replacement is not order-independent

**File:** `scripts/clavain_sync/namespace.py:288-292`

The plan claims namespace replacement is "order-independent" but uses Python's `str.replace()` in iteration order, which is order-dependent when replacements overlap.

**Failure narrative:**

1. `namespace_replacements = {"/workflows:plan": "/clavain:write-plan", "/workflows:": "/clavain:"}`
2. Text: `"Run /workflows:plan first"`
3. First iteration: `/workflows:plan` → `/clavain:write-plan` → `"Run /clavain:write-plan first"`
4. Second iteration: `/workflows:` matches nothing (already replaced) → `"Run /clavain:write-plan first"` (correct)
5. Reverse order:
   - First iteration: `/workflows:` → `/clavain:` → `"Run /clavain:plan first"`
   - Second iteration: `/workflows:plan` matches nothing → `"Run /clavain:plan first"` (WRONG)

**Why this matters:** The bash version (line 148-152) has the same order-dependency bug. Both implementations assume dict iteration order matches insertion order (true in Python 3.7+, true in bash associative arrays), but upstreams.json doesn't specify an ordering contract. If replacements are reordered during a config refactor (e.g., alphabetically sorted), namespace replacement silently corrupts content.

**Recommendation:** Sort replacements by descending length of the old pattern before applying. This ensures longest-match-first semantics regardless of config order:

```python
def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """Apply all namespace replacements to text. Longest match first."""
    sorted_items = sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True)
    for old, new in sorted_items:
        text = text.replace(old, new)
    return text
```

Also add a test case:
```python
def test_apply_replacements_overlapping_patterns():
    text = "Run /workflows:plan then /workflows:work"
    # Deliberately reverse order to test robustness
    replacements = {
        "/workflows:": "/clavain:",
        "/workflows:plan": "/clavain:write-plan",
    }
    result = apply_replacements(text, replacements)
    # Should apply longest match first
    assert result == "Run /clavain:write-plan then /clavain:work"
```

---

### [P0] Git race: upstream file reads happen after fetch/reset, no snapshot lock

**Files:** `scripts/clavain_sync/__main__.py:1347-1400`, `scripts/clavain_sync/git_ops.py:1195-1204`

The orchestrator fetches/resets the clone, reads `HEAD` commit, lists changed files, then iterates and reads file content from the worktree. Between `fetch_and_reset()` and the file read loop, there is no git lock. If another process (e.g., manual `git pull`, parallel sync run, cron job) modifies the clone, classification sees inconsistent state.

**Failure narrative:**

1. `fetch_and_reset()` updates clone to commit `abc123` (line 1347)
2. `get_head_commit()` returns `abc123` (line 1348)
3. `get_changed_files()` diffs `lastSyncedCommit..abc123` → sees `file1.md` modified (line 1364)
4. **Another process runs `git pull` in the clone, advances HEAD to `abc124`**
5. Loop reads `upstream_file.read_text()` from worktree (line 1400) → reads content from `abc124`, not `abc123`
6. Classification compares:
   - `local_content`: from Clavain repo at time of read
   - `upstream_content`: from clone at `abc124` (not the commit we logged)
   - `ancestor_content`: from `lastSyncedCommit` via `git show` (correct)
7. If `abc124` introduced a breaking change, classification may incorrectly classify as COPY or AUTO when it should be CONFLICT
8. State update writes `abc123` to `upstreams.json` (line 1484) but we actually synced content from `abc124` → next sync sees zero changes, silently skips the real `abc124` changes

**Why this matters at 3am:** The clone directory is shared state. Weekly cron (`sync.yml`), manual testing, and stale tmux sessions can all touch it. If content from a newer commit leaks into a classification tagged with an older commit hash, the state machine permanently desynchronizes. The next sync will diff from the wrong baseline, causing either silent data loss (skipped changes) or spurious conflicts.

**Recommendation:** Read all upstream content via `git show <commit>:<path>` instead of reading from the worktree. This gives snapshot isolation. Replace:

```python
# Current (line 1398-1400):
upstream_content = upstream_file.read_text()

# Safe version:
upstream_content = get_file_at_commit(
    clone_dir, head_commit, upstream.base_path, filepath
)
```

Add to `git_ops.py`:
```python
def get_file_at_commit(clone_dir: Path, commit: str, base_path: str, filepath: str) -> str:
    """Get file content at a specific commit from git object store.

    Uses git show, not worktree read, for snapshot isolation.
    Raises ValueError if file doesn't exist at that commit.
    """
    full_path = f"{base_path}/{filepath}" if base_path else filepath
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "show", f"{commit}:{full_path}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"File {full_path} not found at {commit}")
    return result.stdout
```

Then change line 1394-1395 to just verify the file exists in the diff (don't use `is_file()` since the worktree may have diverged):
```python
# Remove the worktree file check entirely — trust git diff output
```

---

### [P1] Empty file content edge case not tested

The test suite has no case for `local_content=""` (empty file exists) vs `local_content=None` (file doesn't exist). Bash version handles this (line 300: `[[ ! -f "$local_full" ]]`), but Python version uses `local_full.read_text() if local_full.is_file() else None` (line 1399). If a local file is empty, `read_text()` returns `""`, which is falsy in Python conditionals but not `None`.

**Failure narrative:**

1. Local file `skills/foo.md` exists but is empty (0 bytes): `local_content = ""`
2. Upstream has content: `upstream_content = "new content"`
3. Ancestor was empty: `ancestor_content = ""`
4. Classification logic at line 661: `if upstream_transformed == local_content:` → `"new content" == ""` → False
5. Line 672: `local_changed = local_content != ancestor_transformed` → `"" != ""` → False
6. Line 671: `upstream_changed = upstream_transformed != ancestor_transformed` → `"new content" != ""` → True
7. Line 674: `if upstream_changed and not local_changed:` → AUTO classification

This is correct! But the test suite doesn't verify this behavior. Add:

```python
def test_auto_applies_to_empty_local_file():
    """Verify empty local file (not deleted) can receive AUTO update."""
    result = classify_file(
        local_path="skills/foo.md",
        local_content="",  # Empty file exists
        upstream_content="new content",
        ancestor_content="",  # Was also empty at ancestor
        protected_files=set(),
        deleted_files=set(),
        namespace_replacements={},
        blocklist=[],
    )
    assert result == Classification.AUTO

def test_copy_preserves_empty_file():
    """Verify empty file that matches upstream after ns replacement is COPY."""
    result = classify_file(
        local_path="skills/foo.md",
        local_content="",
        upstream_content="",
        ancestor_content="anything",
        protected_files=set(),
        deleted_files=set(),
        namespace_replacements={},
        blocklist=[],
    )
    assert result == Classification.COPY
```

---

### [P2] Atomic state write doesn't preserve file permissions/ownership

**File:** `scripts/clavain_sync/state.py:1013-1020`

`NamedTemporaryFile` creates files with mode 0600 (owner-only read/write). After `tmp_path.rename(config_path)`, the file has restrictive permissions even if the original `upstreams.json` was world-readable. This breaks the `claude-user` ACL setup documented in `~/.claude/CLAUDE.md`.

**Failure narrative:**

1. `upstreams.json` has ACL `user:claude-user:rw` (set via `setfacl`)
2. Python sync runs as root, calls `update_synced_commit()`
3. `NamedTemporaryFile` creates `/root/projects/Clavain/upstreams.json.tmp` with mode 0600, owner root:root
4. `tmp_path.rename(config_path)` atomically replaces `upstreams.json`
5. New file has mode 0600, ACLs are lost (POSIX ACLs don't survive rename from a file created without ACLs)
6. Next `cc` (claude-user) session tries to read `upstreams.json` → EACCES

**Why this matters:** The plan assumes POSIX default ACLs on the parent directory will propagate to the temp file. This is true for files created via `open()`, but `tempfile.NamedTemporaryFile` explicitly sets mode=0600 via `os.open(flags=O_CREAT|O_EXCL, mode=0600)`, which masks the umask and ignores default ACLs.

**Recommendation:** Copy the original file's mode and ownership before rename:

```python
def update_synced_commit(config_path: Path, upstream_name: str, new_commit: str) -> None:
    """Atomically update lastSyncedCommit for an upstream.

    Uses tempfile + rename for crash safety.
    Preserves file mode and ownership.
    """
    with open(config_path) as f:
        data = json.load(f)

    # Preserve original file metadata
    original_stat = config_path.stat()

    updated = False
    for u in data["upstreams"]:
        if u["name"] == upstream_name:
            u["lastSyncedCommit"] = new_commit
            updated = True
            break

    if not updated:
        return  # Unknown upstream — noop

    parent = config_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w", dir=parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)

    # Restore original permissions and ownership
    tmp_path.chmod(original_stat.st_mode)
    try:
        os.chown(tmp_path, original_stat.st_uid, original_stat.st_gid)
    except PermissionError:
        pass  # Non-root can't chown, rely on default ACLs

    tmp_path.rename(config_path)
```

Also add a test:
```python
def test_update_preserves_file_mode(tmp_path):
    """Verify atomic write preserves original file permissions."""
    config = {"upstreams": [{"name": "test", "lastSyncedCommit": "old", "url": "", "branch": "main", "fileMap": {}}], "syncConfig": {}}
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    path.chmod(0o644)  # Readable by all

    update_synced_commit(path, "test", "new")

    # Should still be 0644
    assert path.stat().st_mode & 0o777 == 0o644
```

---

### [P2] Missing test: deleted file upstream (status D)

**File:** `scripts/clavain_sync/__main__.py:1376-1377`

The orchestrator explicitly skips deleted files (`if status == "D": continue`), but there's no test verifying this behavior. The bash version has the same logic (line 735), but neither version validates that deletions are ignored.

**Why this matters:** If a file is deleted upstream, the sync should preserve the local copy (general-purpose plugin principle: Clavain controls its own structure). The skip logic is correct, but without a test, future refactors might break it.

**Recommendation:** Add integration test (can't be pure unit test since it requires git diff):

```python
def test_deleted_file_upstream_is_skipped(tmp_path):
    """Verify files deleted upstream don't trigger local deletion."""
    # This would be a fixture-based test with a real git repo
    # showing that git diff --name-status returns "D\tpath/to/file.md"
    # and the orchestrator skips it
    # Placeholder for now — implement in Task 11 integration tests
    pass
```

---

### [P2] Test coverage gap: glob pattern edge cases

**File:** `scripts/clavain_sync/filemap.py:379-399`

Tests cover basic glob matching (`src/refs/*` → `skills/foo/references/*`), but miss edge cases:

1. **Multiple glob segments**: `docs/*/guides/*` → `skills/interpeer/references/*/guides/*`
2. **Glob at end with no suffix**: `src/*` matching `src/` (directory, not file)
3. **Question mark wildcards**: `src/file?.md`
4. **Bracket expressions**: `src/file[0-9].md`

The implementation uses `fnmatch.fnmatch()` which supports all of these, but only splits on `*` (line 394: `src_pattern.split("*")[0]`). This breaks for multi-segment globs.

**Failure narrative:**

1. fileMap: `{"docs/*/guides/*": "skills/interpeer/references/*/guides/*"}`
2. Changed file: `docs/oracle/guides/setup.md`
3. `fnmatch.fnmatch("docs/oracle/guides/setup.md", "docs/*/guides/*")` → True (match)
4. `src_prefix = "docs/*/guides/*".split("*")[0]` → `"docs/"`
5. `suffix = "docs/oracle/guides/setup.md"[len("docs/"):]` → `"oracle/guides/setup.md"`
6. `dst_prefix = "skills/interpeer/references/*/guides/*".split("*")[0]` → `"skills/interpeer/references/"`
7. `return "skills/interpeer/references/" + "oracle/guides/setup.md"` → `"skills/interpeer/references/oracle/guides/setup.md"` (WRONG)
8. Expected: `"skills/interpeer/references/oracle/guides/setup.md"` (happens to be correct by accident)
9. But if pattern was `docs/*/*` → `skills/*/*`, the logic breaks completely

**Recommendation:** Use a proper glob-to-path transformation library or implement proper wildcard handling. For now, document the limitation and add a test:

```python
def test_glob_multi_segment_not_supported():
    """Multi-segment globs are not fully supported — document limitation."""
    file_map = {"docs/*/guides/*": "skills/*/references/*"}
    # Current implementation will fail or produce wrong output
    # TODO: Implement proper multi-segment glob support or reject in config validation
    with pytest.raises(ValueError, match="Multi-segment globs not supported"):
        resolve_local_path("docs/oracle/guides/setup.md", file_map)
```

Or fix it properly (P2, not blocking):

```python
def resolve_local_path(changed_file: str, file_map: dict[str, str]) -> str | None:
    """Resolve an upstream-relative file path to its local path.

    Exact match first, then single-segment glob patterns.
    Multi-segment globs are not supported and will raise ValueError.
    """
    if changed_file in file_map:
        return file_map[changed_file]

    for src_pattern, dst_pattern in file_map.items():
        if "*" not in src_pattern and "?" not in src_pattern:
            continue

        # Reject multi-segment globs
        if src_pattern.count("*") > 1 or dst_pattern.count("*") > 1:
            raise ValueError(f"Multi-segment glob not supported: {src_pattern} → {dst_pattern}")

        if fnmatch.fnmatch(changed_file, src_pattern):
            src_prefix = src_pattern.split("*")[0]
            dst_prefix = dst_pattern.split("*")[0]
            suffix = changed_file[len(src_prefix):]
            return dst_prefix + suffix

    return None
```

---

### [P2] No validation of concurrent sync runs

The Python version has no protection against concurrent sync runs. The bash version doesn't either, but the Python version is more likely to be invoked in parallel (e.g., manual `python3 -m clavain_sync sync` while cron is running).

**Failure narrative:**

1. Process A: `fetch_and_reset()` on `beads` clone → HEAD at `abc123`
2. Process B: `fetch_and_reset()` on `beads` clone → HEAD at `abc124` (new commit arrived)
3. Process A: reads `get_changed_files()` → sees changes from `lastSync..abc123`
4. Process B: reads `get_changed_files()` → sees changes from `lastSync..abc124`
5. Both classify, both call `apply_file()` on overlapping files → last-writer-wins race
6. Process A: `update_synced_commit("beads", "abc123")`
7. Process B: `update_synced_commit("beads", "abc124")`
8. Final state: `upstreams.json` has `abc124`, but some files may have content from `abc123`

**Recommendation:** Add a lockfile (P2, nice-to-have, not blocking for initial release since cron is the only automated invoker):

```python
import fcntl

def acquire_sync_lock(project_root: Path) -> int:
    """Acquire exclusive lock for sync operation. Returns file descriptor."""
    lock_path = project_root / ".upstream-work" / ".sync.lock"
    lock_path.parent.mkdir(exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        print(f"{RED}ERROR: Another sync is already running{NC}", file=sys.stderr)
        sys.exit(1)

# In main():
lock_fd = acquire_sync_lock(project_root)
try:
    # ... sync logic ...
finally:
    os.close(lock_fd)  # Releases lock
```

---

## Summary

**Must fix before shipping (P0):**
- Git race condition (read upstream content from worktree instead of commit snapshot) — this can silently desync state and cause 3am data integrity failures

**Should fix before shipping (P1):**
- Namespace replacement order-dependency — can corrupt content if config is reordered
- Empty file edge case testing — behavior is correct but not validated
- Atomic state write loses file permissions — breaks claude-user ACL setup

**Nice to have (P2):**
- Deleted file upstream test
- Multi-segment glob support or explicit rejection
- Concurrent sync run protection

**Overall assessment:** The classification logic is correct and maps 1:1 to the bash version. The 7 paths are complete. Namespace replacement is applied correctly (upstream + ancestor only, not local). Test coverage is good for happy paths but missing edge cases. The critical flaw is reading upstream content from the worktree instead of using `git show <commit>:<path>`, which breaks snapshot isolation and can cause state desynchronization under concurrent access or manual git operations in the clone directory.

The atomic state write is correct for crash safety but wrong for permission preservation. Fix the P0 issue before execution, fix P1 issues before publish.
