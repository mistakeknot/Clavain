# Python Sync Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite scripts/sync-upstreams.sh (1,020 lines of bash) as a Python package (`scripts/clavain_sync/`) with testable modules, preserving all 7 classification outcomes.

**Architecture:** 7-module Python package under `scripts/clavain_sync/`. Each module maps to a logical layer of the bash script. `classify.py` is pure functions (no I/O), making it trivially testable. AI conflict resolution stays as `claude -p` subprocess call. `upstreams.json` schema unchanged.

**Tech Stack:** Python 3.12+ (stdlib only — no pip dependencies), pytest for tests, subprocess for `git` and `claude` CLI calls.

**PRD:** `docs/prds/2026-02-12-p2-batch-sync-and-discoverability.md`
**Bead:** Clavain-swio

**Parallelization:** Tasks have import dependencies. Use wave-based execution:
- **Wave 1:** Tasks 1, 2, 3, 5, 6 (truly independent — no cross-imports)
- **Wave 2:** Task 4 (imports namespace.py from Task 2)
- **Wave 3:** Task 7 (imports Classification from Task 4)
- **Wave 4:** Tasks 8, 9, 10, 11 (integration — imports everything, run sequentially)

**Flux-Drive Review Notes:**
- Fixed: namespace replacement uses longest-match-first (not dict order)
- Fixed: upstream content read via `git show` for snapshot isolation (not worktree)
- Fixed: `apply_file()` accepts content string (not file path) to avoid redundant reads
- Fixed: PYTHONPATH configured in pyproject.toml, not manual env var
- Review outputs: `docs/research/flux-drive/python-sync-rewrite/`

---

### Task 1: Package scaffold + config loader

**Files:**
- Create: `scripts/clavain_sync/__init__.py`
- Create: `scripts/clavain_sync/config.py`
- Test: `tests/structural/test_clavain_sync/test_config.py`

**Step 1: Create package directory, __init__.py, and update pytest config**

```bash
mkdir -p scripts/clavain_sync
mkdir -p tests/structural/test_clavain_sync
```

Update `tests/pyproject.toml` to add `../scripts` to pythonpath so `clavain_sync` is importable without manual `PYTHONPATH`:

```toml
# tests/pyproject.toml — update the pythonpath line:
pythonpath = ["structural", "../scripts"]
```

```python
# scripts/clavain_sync/__init__.py
"""Clavain upstream sync — Python rewrite of sync-upstreams.sh."""
```

```python
# tests/structural/test_clavain_sync/__init__.py
```

**Step 2: Write the failing test for config loading**

```python
# tests/structural/test_clavain_sync/test_config.py
"""Tests for config.py — loading and validating upstreams.json."""
import json
import pytest
from pathlib import Path

# We'll import after creating the module
from clavain_sync.config import load_config, UpstreamConfig


FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "clavain_sync"


@pytest.fixture
def sample_config(tmp_path):
    """Minimal valid upstreams.json for testing."""
    config = {
        "upstreams": [
            {
                "name": "test-upstream",
                "url": "https://github.com/example/repo.git",
                "branch": "main",
                "lastSyncedCommit": "abc123" * 7 + "ab",
                "basePath": "",
                "fileMap": {
                    "src/foo.md": "skills/foo/SKILL.md",
                    "src/refs/*": "skills/foo/references/*"
                }
            }
        ],
        "syncConfig": {
            "protectedFiles": ["commands/lfg.md"],
            "deletedLocally": [],
            "namespaceReplacements": {
                "/old-ns:": "/clavain:"
            },
            "contentBlocklist": ["rails_model", "Every.to"]
        }
    }
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(config, indent=2))
    return path


def test_load_config_returns_upstream_list(sample_config):
    cfg = load_config(sample_config)
    assert len(cfg.upstreams) == 1
    assert cfg.upstreams[0].name == "test-upstream"


def test_load_config_parses_sync_config(sample_config):
    cfg = load_config(sample_config)
    assert "commands/lfg.md" in cfg.protected_files
    assert "/old-ns:" in cfg.namespace_replacements
    assert cfg.namespace_replacements["/old-ns:"] == "/clavain:"
    assert "rails_model" in cfg.blocklist


def test_load_config_parses_file_map(sample_config):
    cfg = load_config(sample_config)
    u = cfg.upstreams[0]
    assert u.file_map["src/foo.md"] == "skills/foo/SKILL.md"
    assert u.file_map["src/refs/*"] == "skills/foo/references/*"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/upstreams.json"))


def test_load_config_invalid_json(tmp_path):
    path = tmp_path / "upstreams.json"
    path.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        load_config(path)


def test_load_config_missing_upstreams_key(tmp_path):
    path = tmp_path / "upstreams.json"
    path.write_text('{"syncConfig": {}}')
    with pytest.raises(KeyError):
        load_config(path)
```

**Step 3: Run test to verify it fails**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_config.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

**Step 4: Write config.py**

```python
# scripts/clavain_sync/config.py
"""Load and validate upstreams.json configuration."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Upstream:
    """One upstream repository configuration."""
    name: str
    url: str
    branch: str
    last_synced_commit: str
    base_path: str
    file_map: dict[str, str]


@dataclass
class UpstreamConfig:
    """Full parsed configuration from upstreams.json."""
    upstreams: list[Upstream]
    protected_files: set[str]
    deleted_files: set[str]
    namespace_replacements: dict[str, str]
    blocklist: list[str]
    _raw_path: Path = field(repr=False, default=Path())


def load_config(path: Path) -> UpstreamConfig:
    """Load upstreams.json and return parsed config.

    Raises FileNotFoundError, json.JSONDecodeError, or KeyError
    for invalid/missing data.
    """
    with open(path) as f:
        data = json.load(f)

    upstreams = []
    for u in data["upstreams"]:
        upstreams.append(Upstream(
            name=u["name"],
            url=u["url"],
            branch=u.get("branch", "main"),
            last_synced_commit=u["lastSyncedCommit"],
            base_path=u.get("basePath", ""),
            file_map=u.get("fileMap", {}),
        ))

    sync_cfg = data.get("syncConfig", {})
    return UpstreamConfig(
        upstreams=upstreams,
        protected_files=set(sync_cfg.get("protectedFiles", [])),
        deleted_files=set(sync_cfg.get("deletedLocally", [])),
        namespace_replacements=dict(sync_cfg.get("namespaceReplacements", {})),
        blocklist=list(sync_cfg.get("contentBlocklist", [])),
        _raw_path=path,
    )
```

**Step 5: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_config.py -v`
Expected: All 6 tests PASS

**Step 6: Commit**

```bash
git add scripts/clavain_sync/__init__.py scripts/clavain_sync/config.py tests/structural/test_clavain_sync/
git commit -m "feat(sync): add clavain_sync package scaffold + config loader"
```

---

### Task 2: Namespace replacement module

**Files:**
- Create: `scripts/clavain_sync/namespace.py`
- Test: `tests/structural/test_clavain_sync/test_namespace.py`

**Step 1: Write the failing test**

```python
# tests/structural/test_clavain_sync/test_namespace.py
"""Tests for namespace.py — text replacement and blocklist checking."""
from clavain_sync.namespace import apply_replacements, has_blocklist_term


def test_apply_replacements_single():
    text = "Use /compound-engineering:review for reviews"
    replacements = {"/compound-engineering:": "/clavain:"}
    result = apply_replacements(text, replacements)
    assert result == "Use /clavain:review for reviews"


def test_apply_replacements_multiple():
    text = "Run /workflows:plan then /workflows:work"
    replacements = {
        "/workflows:plan": "/clavain:write-plan",
        "/workflows:work": "/clavain:work",
    }
    result = apply_replacements(text, replacements)
    assert "/clavain:write-plan" in result
    assert "/clavain:work" in result
    assert "/workflows:" not in result


def test_apply_replacements_no_match():
    text = "No replacements needed here"
    result = apply_replacements(text, {"/old:": "/new:"})
    assert result == text


def test_apply_replacements_empty_text():
    assert apply_replacements("", {"/a:": "/b:"}) == ""


def test_apply_replacements_empty_replacements():
    assert apply_replacements("hello", {}) == "hello"


def test_apply_replacements_overlapping_patterns():
    """Longest match wins regardless of dict order."""
    text = "Run /workflows:plan then /workflows:work"
    replacements = {
        "/workflows:": "/clavain:",
        "/workflows:plan": "/clavain:write-plan",
    }
    result = apply_replacements(text, replacements)
    assert result == "Run /clavain:write-plan then /clavain:work"


def test_has_blocklist_term_found():
    text = "This mentions rails_model in context"
    blocklist = ["rails_model", "Every.to"]
    found = has_blocklist_term(text, blocklist)
    assert found == "rails_model"


def test_has_blocklist_term_not_found():
    text = "Clean text with no banned terms"
    blocklist = ["rails_model", "Every.to"]
    found = has_blocklist_term(text, blocklist)
    assert found is None


def test_has_blocklist_term_empty_blocklist():
    assert has_blocklist_term("anything", []) is None
```

**Step 2: Run test to verify it fails**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_namespace.py -v`
Expected: FAIL with ImportError

**Step 3: Write namespace.py**

```python
# scripts/clavain_sync/namespace.py
"""Namespace replacement and content blocklist checking."""
from __future__ import annotations


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """Apply all namespace replacements to text. Longest match first."""
    sorted_items = sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True)
    for old, new in sorted_items:
        text = text.replace(old, new)
    return text


def has_blocklist_term(text: str, blocklist: list[str]) -> str | None:
    """Return the first blocklist term found in text, or None."""
    for term in blocklist:
        if term in text:
            return term
    return None
```

**Step 4: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_namespace.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add scripts/clavain_sync/namespace.py tests/structural/test_clavain_sync/test_namespace.py
git commit -m "feat(sync): add namespace replacement + blocklist module"
```

---

### Task 3: File map resolution

**Files:**
- Create: `scripts/clavain_sync/filemap.py`
- Test: `tests/structural/test_clavain_sync/test_filemap.py`

**Step 1: Write the failing test**

```python
# tests/structural/test_clavain_sync/test_filemap.py
"""Tests for filemap.py — resolving upstream paths to local paths."""
from clavain_sync.filemap import resolve_local_path


def test_exact_match():
    file_map = {"src/foo.md": "skills/foo/SKILL.md"}
    assert resolve_local_path("src/foo.md", file_map) == "skills/foo/SKILL.md"


def test_glob_match():
    file_map = {"src/refs/*": "skills/foo/references/*"}
    assert resolve_local_path("src/refs/bar.md", file_map) == "skills/foo/references/bar.md"


def test_glob_nested():
    file_map = {"docs/*": "skills/interpeer/references/oracle-docs/*"}
    result = resolve_local_path("docs/debug/remote-chrome.md", file_map)
    assert result == "skills/interpeer/references/oracle-docs/debug/remote-chrome.md"


def test_no_match():
    file_map = {"src/foo.md": "skills/foo/SKILL.md"}
    assert resolve_local_path("src/bar.md", file_map) is None


def test_exact_takes_precedence_over_glob():
    file_map = {
        "src/foo.md": "exact/path.md",
        "src/*": "glob/path/*",
    }
    assert resolve_local_path("src/foo.md", file_map) == "exact/path.md"


def test_empty_file_map():
    assert resolve_local_path("anything", {}) is None
```

**Step 2: Run test to verify it fails**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_filemap.py -v`
Expected: FAIL with ImportError

**Step 3: Write filemap.py**

```python
# scripts/clavain_sync/filemap.py
"""Resolve upstream file paths to local paths using fileMap."""
from __future__ import annotations

import fnmatch


def resolve_local_path(changed_file: str, file_map: dict[str, str]) -> str | None:
    """Resolve an upstream-relative file path to its local path.

    Tries exact match first, then glob patterns.
    Returns None if no mapping found.
    """
    # Exact match
    if changed_file in file_map:
        return file_map[changed_file]

    # Glob match
    for src_pattern, dst_pattern in file_map.items():
        if "*" not in src_pattern and "?" not in src_pattern:
            continue
        if fnmatch.fnmatch(changed_file, src_pattern):
            src_prefix = src_pattern.split("*")[0]
            dst_prefix = dst_pattern.split("*")[0]
            suffix = changed_file[len(src_prefix):]
            return dst_prefix + suffix

    return None
```

**Step 4: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_filemap.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add scripts/clavain_sync/filemap.py tests/structural/test_clavain_sync/test_filemap.py
git commit -m "feat(sync): add file map resolution module"
```

---

### Task 4: Three-way classification (the core algorithm)

**Files:**
- Create: `scripts/clavain_sync/classify.py`
- Test: `tests/structural/test_clavain_sync/test_classify.py`

This is the most important module. Maps to bash lines 283-362. Pure functions — takes content strings, returns classification. No I/O.

**Step 1: Write the failing tests — all 7 classification paths + edge cases**

```python
# tests/structural/test_clavain_sync/test_classify.py
"""Tests for classify.py — the 7-outcome three-way classification."""
from clavain_sync.classify import classify_file, Classification


class TestClassifyFile:
    """Test all 7 classification outcomes."""

    def test_skip_protected(self):
        result = classify_file(
            local_path="commands/lfg.md",
            local_content="local",
            upstream_content="upstream",
            ancestor_content="ancestor",
            protected_files={"commands/lfg.md"},
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.SKIP_PROTECTED

    def test_skip_deleted_locally(self):
        result = classify_file(
            local_path="old/file.md",
            local_content="local",
            upstream_content="upstream",
            ancestor_content="ancestor",
            protected_files=set(),
            deleted_files={"old/file.md"},
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.SKIP_DELETED

    def test_skip_not_present_locally(self):
        result = classify_file(
            local_path="missing.md",
            local_content=None,  # None means file doesn't exist locally
            upstream_content="upstream",
            ancestor_content="ancestor",
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.SKIP_NOT_PRESENT

    def test_copy_identical_after_replacement(self):
        result = classify_file(
            local_path="skills/foo.md",
            local_content="Use /clavain:review",
            upstream_content="Use /old-ns:review",
            ancestor_content="old ancestor",
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={"/old-ns:": "/clavain:"},
            blocklist=[],
        )
        assert result == Classification.COPY

    def test_auto_upstream_only_changed(self):
        ancestor = "original content"
        result = classify_file(
            local_path="skills/foo.md",
            local_content="original content",  # same as ancestor (after ns replacement)
            upstream_content="updated content",
            ancestor_content=ancestor,
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.AUTO

    def test_auto_blocked_by_blocklist(self):
        ancestor = "original content"
        result = classify_file(
            local_path="skills/foo.md",
            local_content="original content",
            upstream_content="updated with rails_model reference",
            ancestor_content=ancestor,
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=["rails_model"],
        )
        assert result.name.startswith("REVIEW")

    def test_keep_local_only_changed(self):
        ancestor = "original content"
        result = classify_file(
            local_path="skills/foo.md",
            local_content="locally modified content",
            upstream_content=ancestor,  # upstream hasn't changed
            ancestor_content=ancestor,
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.KEEP_LOCAL

    def test_conflict_both_changed(self):
        result = classify_file(
            local_path="skills/foo.md",
            local_content="locally changed",
            upstream_content="upstream changed",
            ancestor_content="original",
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.CONFLICT

    def test_review_new_upstream_file(self):
        result = classify_file(
            local_path="skills/foo.md",
            local_content="local version",
            upstream_content="new upstream version",
            ancestor_content=None,  # None means no ancestor (new file)
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        assert result == Classification.REVIEW_NEW

    def test_review_unexpected_divergence(self):
        """Both unchanged vs ancestor but content differs — shouldn't happen."""
        result = classify_file(
            local_path="skills/foo.md",
            local_content="version A",
            upstream_content="version A",  # same as local after replacement
            ancestor_content="version A",  # same as both
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={},
            blocklist=[],
        )
        # When all three match after replacement, it's COPY (content identical)
        assert result == Classification.COPY

    def test_namespace_replacement_applied_to_upstream_and_ancestor(self):
        """Verify namespace replacement is applied to upstream AND ancestor, not local."""
        result = classify_file(
            local_path="skills/foo.md",
            local_content="Use /clavain:review for reviews",  # local already has correct ns
            upstream_content="Use /old-ns:review for reviews",  # upstream has old ns
            ancestor_content="Use /old-ns:review for reviews",  # ancestor has old ns
            protected_files=set(),
            deleted_files=set(),
            namespace_replacements={"/old-ns:": "/clavain:"},
            blocklist=[],
        )
        # After ns replacement, upstream == ancestor == local → COPY
        assert result == Classification.COPY
```

**Step 2: Run test to verify it fails**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_classify.py -v`
Expected: FAIL with ImportError

**Step 3: Write classify.py**

```python
# scripts/clavain_sync/classify.py
"""Three-way file classification for upstream sync.

Pure functions — no I/O. Takes content strings, returns classification.
Maps to sync-upstreams.sh lines 283-362.
"""
from __future__ import annotations

from enum import Enum

from .namespace import apply_replacements, has_blocklist_term


class Classification(Enum):
    """All 7 possible outcomes of three-way classification."""
    SKIP_PROTECTED = "SKIP:protected"
    SKIP_DELETED = "SKIP:deleted-locally"
    SKIP_NOT_PRESENT = "SKIP:not-present-locally"
    COPY = "COPY"
    AUTO = "AUTO"
    KEEP_LOCAL = "KEEP-LOCAL"
    CONFLICT = "CONFLICT"
    REVIEW_NEW = "REVIEW:new-upstream-file"
    REVIEW_BLOCKLIST = "REVIEW:blocklist-in-upstream"
    REVIEW_UNEXPECTED = "REVIEW:unexpected-divergence"


def classify_file(
    *,
    local_path: str,
    local_content: str | None,
    upstream_content: str,
    ancestor_content: str | None,
    protected_files: set[str],
    deleted_files: set[str],
    namespace_replacements: dict[str, str],
    blocklist: list[str],
) -> Classification:
    """Classify a file using three-way comparison.

    Args:
        local_path: Relative path in the Clavain project.
        local_content: Current local file content, or None if file doesn't exist.
        upstream_content: Raw upstream file content (before namespace replacement).
        ancestor_content: Content at lastSyncedCommit, or None if new file.
        protected_files: Set of paths that should never be overwritten.
        deleted_files: Set of paths intentionally deleted locally.
        namespace_replacements: Old→new string replacements.
        blocklist: Terms that should not appear in synced content.

    Returns:
        Classification enum value.
    """
    # SKIP checks (no content comparison needed)
    if local_path in protected_files:
        return Classification.SKIP_PROTECTED

    if local_path in deleted_files:
        return Classification.SKIP_DELETED

    if local_content is None:
        return Classification.SKIP_NOT_PRESENT

    # Apply namespace replacements to upstream
    upstream_transformed = apply_replacements(upstream_content, namespace_replacements)

    # If content matches after replacement, it's identical
    if upstream_transformed == local_content:
        return Classification.COPY

    # Three-way: need ancestor
    if ancestor_content is None:
        return Classification.REVIEW_NEW

    ancestor_transformed = apply_replacements(ancestor_content, namespace_replacements)

    # Determine who changed
    upstream_changed = upstream_transformed != ancestor_transformed
    local_changed = local_content != ancestor_transformed

    if upstream_changed and not local_changed:
        # Check blocklist before auto-applying
        bad_term = has_blocklist_term(upstream_transformed, blocklist)
        if bad_term:
            return Classification.REVIEW_BLOCKLIST
        return Classification.AUTO

    if not upstream_changed and local_changed:
        return Classification.KEEP_LOCAL

    if upstream_changed and local_changed:
        return Classification.CONFLICT

    # Both unchanged but content differs — shouldn't happen
    return Classification.REVIEW_UNEXPECTED
```

**Step 4: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_classify.py -v`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add scripts/clavain_sync/classify.py tests/structural/test_clavain_sync/test_classify.py
git commit -m "feat(sync): add three-way classification module (7 outcomes)"
```

---

### Task 5: AI conflict resolution module

**Files:**
- Create: `scripts/clavain_sync/resolve.py`
- Test: `tests/structural/test_clavain_sync/test_resolve.py`

This module shells out to `claude -p`. Tests mock the subprocess call.

**Step 1: Write the failing test**

```python
# tests/structural/test_clavain_sync/test_resolve.py
"""Tests for resolve.py — AI conflict resolution via claude -p."""
import json
from unittest.mock import patch, MagicMock
from clavain_sync.resolve import analyze_conflict, ConflictDecision


def _mock_claude_result(decision="accept_upstream", risk="low", rationale="test"):
    return json.dumps({
        "decision": decision,
        "risk": risk,
        "rationale": rationale,
        "blocklist_found": [],
    })


@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_returns_parsed_decision(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_mock_claude_result("accept_upstream", "low", "Changes are orthogonal"),
    )
    result = analyze_conflict(
        local_path="skills/foo.md",
        local_content="local version",
        upstream_content="upstream version",
        ancestor_content="ancestor version",
        blocklist=["rails_model"],
    )
    assert result.decision == "accept_upstream"
    assert result.risk == "low"


@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_falls_back_on_failure(mock_run):
    mock_run.side_effect = Exception("claude not found")
    result = analyze_conflict(
        local_path="skills/foo.md",
        local_content="local",
        upstream_content="upstream",
        ancestor_content="ancestor",
        blocklist=[],
    )
    assert result.decision == "needs_human"
    assert result.risk == "high"


@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_falls_back_on_bad_json(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="not json")
    result = analyze_conflict(
        local_path="skills/foo.md",
        local_content="local",
        upstream_content="upstream",
        ancestor_content="ancestor",
        blocklist=[],
    )
    assert result.decision == "needs_human"


@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_passes_blocklist_to_prompt(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_mock_claude_result(),
    )
    analyze_conflict(
        local_path="skills/foo.md",
        local_content="local",
        upstream_content="upstream",
        ancestor_content="ancestor",
        blocklist=["rails_model", "Every.to"],
    )
    # Verify the prompt sent to claude includes blocklist
    call_args = mock_run.call_args
    stdin_text = call_args.kwargs.get("input", "") or call_args[1].get("input", "")
    assert "rails_model" in stdin_text
    assert "Every.to" in stdin_text
```

**Step 2: Run test to verify it fails**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_resolve.py -v`
Expected: FAIL with ImportError

**Step 3: Write resolve.py**

```python
# scripts/clavain_sync/resolve.py
"""AI-powered conflict resolution via claude -p subprocess."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass
class ConflictDecision:
    """Result from AI conflict analysis."""
    decision: str  # accept_upstream | keep_local | needs_human
    risk: str  # low | medium | high
    rationale: str
    blocklist_found: list[str]


_FALLBACK = ConflictDecision(
    decision="needs_human",
    risk="high",
    rationale="AI analysis failed",
    blocklist_found=[],
)

_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept_upstream", "keep_local", "needs_human"]},
        "rationale": {"type": "string"},
        "blocklist_found": {"type": "array", "items": {"type": "string"}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["decision", "rationale", "risk"],
})


def analyze_conflict(
    *,
    local_path: str,
    local_content: str,
    upstream_content: str,
    ancestor_content: str,
    blocklist: list[str],
) -> ConflictDecision:
    """Analyze a conflict using Claude AI.

    Shells out to `claude -p` with structured JSON output.
    Falls back to needs_human on any failure.
    """
    blocklist_str = ", ".join(blocklist) if blocklist else "(none)"

    prompt = f"""You are analyzing a file conflict during an upstream sync for the Clavain plugin.
Three versions exist: ancestor (at last sync), local (Clavain's version), upstream (new).

Context:
- Clavain is a general-purpose engineering plugin (no Rails/Ruby/Every.to)
- Namespace: /clavain: (not /compound-engineering: or /workflows:)
- Blocklist terms that should NOT appear: {blocklist_str}

File: {local_path}

ANCESTOR (at last sync):
{ancestor_content}

LOCAL (Clavain's current version):
{local_content}

UPSTREAM (new version, after namespace replacement):
{upstream_content}

Analyze: What did each side change? Are the changes orthogonal or conflicting?
Should Clavain accept upstream, keep local, or does this need human review?
Check for blocklist terms in the upstream changes."""

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--output-format", "json",
                "--json-schema", _SCHEMA,
                "--model", "haiku",
                "--max-turns", "1",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        data = json.loads(result.stdout)
        return ConflictDecision(
            decision=data.get("decision", "needs_human"),
            risk=data.get("risk", "high"),
            rationale=data.get("rationale", ""),
            blocklist_found=data.get("blocklist_found", []),
        )
    except Exception:
        return _FALLBACK
```

**Step 4: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_resolve.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add scripts/clavain_sync/resolve.py tests/structural/test_clavain_sync/test_resolve.py
git commit -m "feat(sync): add AI conflict resolution module"
```

---

### Task 6: State management (read/write lastSyncedCommit)

**Files:**
- Create: `scripts/clavain_sync/state.py`
- Test: `tests/structural/test_clavain_sync/test_state.py`

**Step 1: Write the failing test**

```python
# tests/structural/test_clavain_sync/test_state.py
"""Tests for state.py — atomic updates to lastSyncedCommit in upstreams.json."""
import json
from pathlib import Path
from clavain_sync.state import update_synced_commit


def test_update_synced_commit(tmp_path):
    config = {
        "upstreams": [
            {"name": "beads", "lastSyncedCommit": "old_hash", "url": "", "branch": "main", "fileMap": {}},
            {"name": "oracle", "lastSyncedCommit": "other_hash", "url": "", "branch": "main", "fileMap": {}},
        ],
        "syncConfig": {}
    }
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(config, indent=2))

    update_synced_commit(path, "beads", "new_hash_abc123")

    data = json.loads(path.read_text())
    assert data["upstreams"][0]["lastSyncedCommit"] == "new_hash_abc123"
    assert data["upstreams"][1]["lastSyncedCommit"] == "other_hash"


def test_update_preserves_formatting(tmp_path):
    """Verify atomic write preserves JSON formatting (2-space indent + trailing newline)."""
    config = {"upstreams": [{"name": "test", "lastSyncedCommit": "old", "url": "", "branch": "main", "fileMap": {}}], "syncConfig": {}}
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(config, indent=2) + "\n")

    update_synced_commit(path, "test", "new")

    content = path.read_text()
    assert content.endswith("\n")
    # Should be parseable
    json.loads(content)


def test_update_unknown_upstream_is_noop(tmp_path):
    config = {"upstreams": [{"name": "beads", "lastSyncedCommit": "old", "url": "", "branch": "main", "fileMap": {}}], "syncConfig": {}}
    path = tmp_path / "upstreams.json"
    path.write_text(json.dumps(config, indent=2))

    update_synced_commit(path, "nonexistent", "new_hash")

    data = json.loads(path.read_text())
    assert data["upstreams"][0]["lastSyncedCommit"] == "old"
```

**Step 2: Run test to verify it fails**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_state.py -v`

**Step 3: Write state.py**

```python
# scripts/clavain_sync/state.py
"""Atomic state management for lastSyncedCommit in upstreams.json."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


def update_synced_commit(config_path: Path, upstream_name: str, new_commit: str) -> None:
    """Atomically update lastSyncedCommit for an upstream.

    Uses tempfile + rename for crash safety.
    """
    with open(config_path) as f:
        data = json.load(f)

    updated = False
    for u in data["upstreams"]:
        if u["name"] == upstream_name:
            u["lastSyncedCommit"] = new_commit
            updated = True
            break

    if not updated:
        return  # Unknown upstream — noop

    # Atomic write: temp file in same directory, then rename
    parent = config_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w", dir=parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)

    tmp_path.rename(config_path)
```

**Step 4: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_state.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add scripts/clavain_sync/state.py tests/structural/test_clavain_sync/test_state.py
git commit -m "feat(sync): add atomic state management for lastSyncedCommit"
```

---

### Task 7: Report generation

**Files:**
- Create: `scripts/clavain_sync/report.py`
- Test: `tests/structural/test_clavain_sync/test_report.py`

**Step 1: Write the failing test**

```python
# tests/structural/test_clavain_sync/test_report.py
"""Tests for report.py — markdown sync report generation."""
from clavain_sync.report import SyncReport
from clavain_sync.classify import Classification


def test_empty_report():
    report = SyncReport()
    output = report.generate()
    assert "Clavain Upstream Sync Report" in output
    assert "| COPY" in output


def test_report_counts_classifications():
    report = SyncReport()
    report.add_entry("file1.md", Classification.COPY)
    report.add_entry("file2.md", Classification.AUTO)
    report.add_entry("file3.md", Classification.AUTO)
    report.add_entry("file4.md", Classification.CONFLICT)
    output = report.generate()
    # Verify counts appear (exact format may vary)
    assert "COPY" in output
    assert "AUTO" in output


def test_report_includes_ai_decisions():
    report = SyncReport()
    report.add_ai_decision("file.md", "accept_upstream", "low", "Changes are safe")
    output = report.generate()
    assert "AI Decisions" in output
    assert "accept_upstream" in output
    assert "file.md" in output
```

**Step 2: Run test to verify it fails, then write report.py**

```python
# scripts/clavain_sync/report.py
"""Markdown sync report generation."""
from __future__ import annotations

from dataclasses import dataclass, field

from .classify import Classification


@dataclass
class _AiEntry:
    file: str
    decision: str
    risk: str
    rationale: str


@dataclass
class SyncReport:
    """Collects sync results and generates a markdown report."""
    entries: list[tuple[str, Classification]] = field(default_factory=list)
    ai_decisions: list[_AiEntry] = field(default_factory=list)

    def add_entry(self, file: str, classification: Classification) -> None:
        self.entries.append((file, classification))

    def add_ai_decision(self, file: str, decision: str, risk: str, rationale: str) -> None:
        self.ai_decisions.append(_AiEntry(file, decision, risk, rationale))

    def generate(self) -> str:
        """Generate the markdown report string."""
        counts: dict[str, int] = {
            "COPY": 0, "AUTO": 0, "KEEP-LOCAL": 0,
            "CONFLICT": 0, "SKIP": 0, "REVIEW": 0,
        }
        ai_resolved = 0

        for _, cls in self.entries:
            val = cls.value
            if val.startswith("SKIP"):
                counts["SKIP"] += 1
            elif val.startswith("REVIEW"):
                counts["REVIEW"] += 1
            elif val.startswith("CONFLICT"):
                counts["CONFLICT"] += 1
            elif val in counts:
                counts[val] += 1

        for entry in self.ai_decisions:
            if entry.decision != "needs_human":
                ai_resolved += 1

        lines = [
            "",
            "═══ Clavain Upstream Sync Report ═══",
            "",
            "## Classification Summary",
            "| Category    | Count | Description                      |",
            "|-------------|-------|----------------------------------|",
            f"| COPY        | {counts['COPY']}     | Content identical                 |",
            f"| AUTO        | {counts['AUTO']}     | Upstream-only, auto-applied       |",
            f"| KEEP-LOCAL  | {counts['KEEP-LOCAL']}     | Local-only, preserved             |",
            f"| CONFLICT    | {counts['CONFLICT']}     | Both changed — {ai_resolved} AI-resolved       |",
            f"| SKIP        | {counts['SKIP']}    | Protected/deleted                 |",
            f"| REVIEW      | {counts['REVIEW']}     | Needs manual review               |",
            "",
        ]

        if self.ai_decisions:
            lines.append("## AI Decisions")
            for entry in self.ai_decisions:
                lines.append(f"- {entry.file}: **{entry.decision}** (risk: {entry.risk})")
                if entry.rationale:
                    lines.append(f'  "{entry.rationale}"')
            lines.append("")

        return "\n".join(lines)
```

**Step 3: Run test to verify it passes**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_report.py -v`
Expected: All 3 tests PASS

**Step 4: Commit**

```bash
git add scripts/clavain_sync/report.py tests/structural/test_clavain_sync/test_report.py
git commit -m "feat(sync): add markdown report generation module"
```

---

### Task 8: Main CLI + sync orchestrator

**Files:**
- Create: `scripts/clavain_sync/__main__.py`
- Create: `scripts/clavain_sync/git_ops.py`

This is the integration layer — reads config, iterates upstreams, calls git, runs classification, applies changes. Maps to the bash main loop (lines 604-1020).

**Step 1: Write git_ops.py (git subprocess helper)**

```python
# scripts/clavain_sync/git_ops.py
"""Git operations via subprocess — fetch, diff, show ancestor content."""
from __future__ import annotations

import subprocess
from pathlib import Path


def fetch_and_reset(clone_dir: Path, branch: str) -> None:
    """Fetch origin and hard-reset to latest."""
    subprocess.run(
        ["git", "-C", str(clone_dir), "fetch", "origin", "--quiet"],
        capture_output=True, check=False,
    )
    subprocess.run(
        ["git", "-C", str(clone_dir), "reset", "--hard", f"origin/{branch}", "--quiet"],
        capture_output=True, check=False,
    )


def get_head_commit(clone_dir: Path) -> str:
    """Return full HEAD commit hash."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def commit_is_reachable(clone_dir: Path, commit: str) -> bool:
    """Check if a commit exists in the repo."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "cat-file", "-e", commit],
        capture_output=True, check=False,
    )
    return result.returncode == 0


def count_new_commits(clone_dir: Path, since_commit: str) -> int:
    """Count commits between since_commit and HEAD."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-list", "--count", f"{since_commit}..HEAD"],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def get_changed_files(clone_dir: Path, since_commit: str, diff_path: str = ".") -> list[tuple[str, str]]:
    """Return list of (status, filepath) changed since commit.

    Status is one of: A (added), M (modified), D (deleted).
    """
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "diff", "--name-status", since_commit, "HEAD", "--", diff_path],
        capture_output=True, text=True, check=False,
    )
    entries = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1]))
    return entries


def get_ancestor_content(clone_dir: Path, commit: str, base_path: str, filepath: str) -> str | None:
    """Get file content at a specific commit. Returns None if not found."""
    full_path = f"{base_path}/{filepath}" if base_path else filepath
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "show", f"{commit}:{full_path}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout
```

**Step 2: Write __main__.py (CLI + orchestrator)**

This is the largest file — it ties all modules together. Maps to bash lines 604-1020.

```python
# scripts/clavain_sync/__main__.py
"""CLI entry point: python3 -m clavain_sync sync [--upstream NAME] [--dry-run] [--auto] [--no-ai] [--report [FILE]]"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .classify import Classification, classify_file
from .config import load_config, Upstream
from .filemap import resolve_local_path
from .git_ops import (
    commit_is_reachable,
    count_new_commits,
    fetch_and_reset,
    get_ancestor_content,
    get_changed_files,
    get_head_commit,
)
from .namespace import apply_replacements
from .report import SyncReport
from .resolve import analyze_conflict
from .state import update_synced_commit

# Colors (respects NO_COLOR env)
if os.environ.get("NO_COLOR"):
    RED = GREEN = YELLOW = CYAN = BOLD = NC = ""
else:
    RED, GREEN, YELLOW, CYAN = "\033[0;31m", "\033[0;32m", "\033[0;33m", "\033[0;36m"
    BOLD, NC = "\033[1m", "\033[0m"


def find_upstreams_dir(project_root: Path) -> Path:
    """Find the upstreams clone directory."""
    work_dir = project_root / ".upstream-work"
    if work_dir.is_dir():
        return work_dir
    default = Path("/root/projects/upstreams")
    if default.is_dir():
        return default
    print(f"ERROR: No upstreams directory found. Run scripts/clone-upstreams.sh first.", file=sys.stderr)
    sys.exit(1)


def apply_file(upstream_content: str, local_file: Path, namespace_replacements: dict[str, str]) -> None:
    """Write upstream content to local path, applying namespace replacements."""
    local_file.parent.mkdir(parents=True, exist_ok=True)
    content = apply_replacements(upstream_content, namespace_replacements)
    local_file.write_text(content)


def sync_upstream(
    upstream: Upstream,
    *,
    project_root: Path,
    upstreams_dir: Path,
    config_path: Path,
    namespace_replacements: dict[str, str],
    protected_files: set[str],
    deleted_files: set[str],
    blocklist: list[str],
    mode: str,
    use_ai: bool,
    report: SyncReport,
) -> list[str]:
    """Sync a single upstream. Returns list of modified local file paths."""
    clone_dir = upstreams_dir / upstream.name
    if not (clone_dir / ".git").is_dir():
        print(f"  {RED}Clone not found at {clone_dir}{NC}")
        return []

    # Fetch latest
    fetch_and_reset(clone_dir, upstream.branch)
    head_commit = get_head_commit(clone_dir)
    head_short = head_commit[:7]

    if head_commit == upstream.last_synced_commit:
        print(f"  {GREEN}No new commits (HEAD: {head_short}){NC}")
        return []

    if not commit_is_reachable(clone_dir, upstream.last_synced_commit):
        print(f"  {RED}Last synced commit {upstream.last_synced_commit} not reachable — skipping{NC}")
        return []

    new_count = count_new_commits(clone_dir, upstream.last_synced_commit)
    print(f"  {CYAN}{new_count} new commits{NC} ({upstream.last_synced_commit[:7]} → {head_short})")

    # Get changed files
    diff_path = upstream.base_path if upstream.base_path else "."
    changed_files = get_changed_files(clone_dir, upstream.last_synced_commit, diff_path)

    if not changed_files:
        print("  No mapped files changed")
        if mode != "dry-run":
            update_synced_commit(config_path, upstream.name, head_commit)
        return []

    modified: list[str] = []
    counts = {"copy": 0, "auto": 0, "keep": 0, "conflict": 0, "skip": 0, "review": 0}

    for status, filepath in changed_files:
        if status == "D":
            continue

        # Strip basePath prefix
        if upstream.base_path and filepath.startswith(f"{upstream.base_path}/"):
            filepath = filepath[len(upstream.base_path) + 1:]

        # Resolve to local path
        local_path = resolve_local_path(filepath, upstream.file_map)
        if local_path is None:
            continue

        # Read contents using git object store for snapshot isolation
        # (avoids TOCTOU race if another process modifies the clone)
        local_full = project_root / local_path
        local_content = local_full.read_text() if local_full.is_file() else None
        upstream_content = get_ancestor_content(
            clone_dir, head_commit, upstream.base_path, filepath
        )
        if upstream_content is None:
            continue  # File listed in diff but not readable at commit
        ancestor_content = get_ancestor_content(
            clone_dir, upstream.last_synced_commit, upstream.base_path, filepath
        )

        # Classify
        classification = classify_file(
            local_path=local_path,
            local_content=local_content,
            upstream_content=upstream_content,
            ancestor_content=ancestor_content,
            protected_files=protected_files,
            deleted_files=deleted_files,
            namespace_replacements=namespace_replacements,
            blocklist=blocklist,
        )

        report.add_entry(local_path, classification)

        if classification in (Classification.SKIP_PROTECTED, Classification.SKIP_DELETED, Classification.SKIP_NOT_PRESENT):
            reason = classification.value.split(":", 1)[1]
            print(f"  {YELLOW}SKIP{NC}  {local_path:<50} ({reason})")
            counts["skip"] += 1

        elif classification == Classification.COPY:
            print(f"  {GREEN}COPY{NC}  {local_path}")
            counts["copy"] += 1
            if mode != "dry-run":
                apply_file(upstream_content, local_full, namespace_replacements)
                modified.append(local_path)

        elif classification == Classification.AUTO:
            print(f"  {GREEN}AUTO{NC}  {local_path:<50} (upstream-only change)")
            counts["auto"] += 1
            if mode != "dry-run":
                apply_file(upstream_content, local_full, namespace_replacements)
                modified.append(local_path)

        elif classification == Classification.KEEP_LOCAL:
            print(f"  {GREEN}KEEP{NC}  {local_path:<50} (local-only changes)")
            counts["keep"] += 1

        elif classification == Classification.CONFLICT:
            print(f"  {RED}CONFLICT{NC} {local_path}")
            counts["conflict"] += 1

            if mode == "dry-run":
                pass  # No action
            elif mode == "auto" and use_ai:
                print("           Analyzing with AI...")
                upstream_transformed = apply_replacements(upstream_content, namespace_replacements)
                ancestor_transformed = apply_replacements(ancestor_content or "", namespace_replacements)
                ai_result = analyze_conflict(
                    local_path=local_path,
                    local_content=local_content or "",
                    upstream_content=upstream_transformed,
                    ancestor_content=ancestor_transformed,
                    blocklist=blocklist,
                )
                report.add_ai_decision(local_path, ai_result.decision, ai_result.risk, ai_result.rationale)

                if ai_result.decision == "accept_upstream" and ai_result.risk == "low":
                    apply_file(upstream_content, local_full, namespace_replacements)
                    modified.append(local_path)
                    print(f"           {GREEN}AI: accept_upstream (risk: low) — auto-applied{NC}")
                elif ai_result.decision == "keep_local" and ai_result.risk == "low":
                    print(f"           {GREEN}AI: keep_local (risk: low) — preserved{NC}")
                else:
                    print(f"           {YELLOW}AI: {ai_result.decision} (risk: {ai_result.risk}) — skipped{NC}")
            elif mode == "auto":
                print(f"           {YELLOW}(skipped in --auto --no-ai mode){NC}")
            # Interactive mode: would need tty handling (not implemented in first iteration)

        elif classification.value.startswith("REVIEW"):
            reason = classification.value.split(":", 1)[1]
            print(f"  {CYAN}REVIEW{NC} {local_path:<50} ({reason})")
            counts["review"] += 1

    print(f"  Summary: {GREEN}{counts['copy']} copied{NC}, {GREEN}{counts['auto']} auto{NC}, "
          f"{GREEN}{counts['keep']} kept{NC}, {RED}{counts['conflict']} conflict{NC}, "
          f"{YELLOW}{counts['skip']} skipped{NC}, {CYAN}{counts['review']} review{NC}")

    # Update lastSyncedCommit
    if mode != "dry-run":
        update_synced_commit(config_path, upstream.name, head_commit)

    return modified


def run_contamination_check(
    modified_files: list[str],
    project_root: Path,
    blocklist: list[str],
    namespace_replacements: dict[str, str],
) -> int:
    """Check modified files for blocklist terms and raw namespace patterns."""
    print(f"\n{BOLD}─── Contamination Check ───{NC}")
    found = 0

    for file_path in modified_files:
        full = project_root / file_path
        if not full.is_file():
            continue
        content = full.read_text()

        for term in blocklist:
            if term in content:
                print(f"  {RED}WARN{NC} {file_path} contains blocklisted term: {BOLD}{term}{NC}")
                found += 1

        for old in namespace_replacements:
            if old in content:
                print(f"  {RED}WARN{NC} {file_path} still contains raw namespace: {BOLD}{old}{NC}")
                found += 1

    if found == 0:
        print(f"  {GREEN}No contamination detected{NC}")
    else:
        print(f"  {RED}{found} contamination warning(s){NC}")

    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Clavain upstream sync")
    sub = parser.add_subparsers(dest="command")

    sync_parser = sub.add_parser("sync", help="Sync upstreams to local")
    sync_parser.add_argument("--dry-run", action="store_true", help="Preview only")
    sync_parser.add_argument("--auto", action="store_true", help="Non-interactive (CI)")
    sync_parser.add_argument("--upstream", type=str, default="", help="Sync single upstream")
    sync_parser.add_argument("--no-ai", action="store_true", help="Disable AI conflict analysis")
    sync_parser.add_argument("--report", nargs="?", const=True, default=False, help="Generate report")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "sync":
        # Resolve paths
        script_dir = Path(__file__).resolve().parent.parent
        project_root = script_dir.parent
        config_path = project_root / "upstreams.json"
        upstreams_dir = find_upstreams_dir(project_root)

        if args.dry_run:
            mode = "dry-run"
        elif args.auto:
            mode = "auto"
        else:
            mode = "interactive"

        # Load config
        cfg = load_config(config_path)

        print(f"\n{BOLD}═══ Clavain Upstream Sync ═══{NC}")
        print(f"Mode: {CYAN}{mode}{NC}  AI: {not args.no_ai}  Report: {bool(args.report)}")
        print(f"Upstreams dir: {upstreams_dir}\n")

        all_modified: list[str] = []
        report = SyncReport()

        for upstream in cfg.upstreams:
            if args.upstream and upstream.name != args.upstream:
                continue

            print(f"{BOLD}─── {upstream.name} ───{NC}")
            modified = sync_upstream(
                upstream,
                project_root=project_root,
                upstreams_dir=upstreams_dir,
                config_path=config_path,
                namespace_replacements=cfg.namespace_replacements,
                protected_files=cfg.protected_files,
                deleted_files=cfg.deleted_files,
                blocklist=cfg.blocklist,
                mode=mode,
                use_ai=not args.no_ai,
                report=report,
            )
            all_modified.extend(modified)
            print()

        # Contamination check
        if all_modified:
            run_contamination_check(all_modified, project_root, cfg.blocklist, cfg.namespace_replacements)

        # Summary
        print(f"\n{BOLD}═══ Summary ═══{NC}")
        if mode == "dry-run":
            print(f"  {YELLOW}(dry-run — no files were modified){NC}")

        # Report
        if args.report:
            output = report.generate()
            if isinstance(args.report, str):
                Path(args.report).write_text(output)
                print(f"\n  Report written to: {CYAN}{args.report}{NC}")
            else:
                print(output)


if __name__ == "__main__":
    main()
```

**Step 3: Smoke test the CLI**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m clavain_sync sync --dry-run 2>&1 | head -30`
Expected: Should show upstream names, commit counts, and classifications without modifying files.

**Step 4: Commit**

```bash
git add scripts/clavain_sync/__main__.py scripts/clavain_sync/git_ops.py
git commit -m "feat(sync): add CLI orchestrator + git operations module"
```

---

### Task 9: Integration — update pull-upstreams.sh + deprecate bash version

**Files:**
- Modify: `scripts/pull-upstreams.sh:37-44` (add `--legacy` flag, default to Python)
- Modify: `scripts/sync-upstreams.sh:1-5` (add deprecation notice)

**Step 1: Add --legacy flag to pull-upstreams.sh**

In `scripts/pull-upstreams.sh`, replace the `--sync` handler (lines 37-45):

```bash
# Before (line 37-45):
if [[ "$mode" == "--sync" ]]; then
  echo "=== Pull + Sync Mode ==="
  echo ""
  "$0" --pull
  echo ""
  echo "=== Running sync-upstreams.sh ==="
  exec "$SCRIPT_DIR/sync-upstreams.sh" "${@:2}"
fi

# After:
if [[ "$mode" == "--sync" ]]; then
  echo "=== Pull + Sync Mode ==="
  echo ""
  "$0" --pull
  echo ""
  # Check for --legacy flag
  legacy=false
  remaining_args=()
  for arg in "${@:2}"; do
    if [[ "$arg" == "--legacy" ]]; then
      legacy=true
    else
      remaining_args+=("$arg")
    fi
  done
  if [[ "$legacy" == true ]]; then
    echo "=== Running sync-upstreams.sh (legacy bash) ==="
    exec "$SCRIPT_DIR/sync-upstreams.sh" "${remaining_args[@]}"
  else
    echo "=== Running clavain_sync (Python) ==="
    exec python3 -m clavain_sync sync "${remaining_args[@]}"
  fi
fi
```

**Step 2: Add deprecation notice to sync-upstreams.sh**

Add after line 1:

```bash
# DEPRECATED: This script has been replaced by the Python package clavain_sync.
# Use: python3 -m clavain_sync sync [--dry-run] [--auto] [--upstream NAME]
# Or:  pull-upstreams.sh --sync (defaults to Python version)
# To use this legacy version: pull-upstreams.sh --sync --legacy
```

**Step 3: Verify bash syntax**

Run: `bash -n scripts/pull-upstreams.sh && bash -n scripts/sync-upstreams.sh && echo "Both OK"`

**Step 4: Commit**

```bash
git add scripts/pull-upstreams.sh scripts/sync-upstreams.sh
git commit -m "feat(sync): wire Python sync into pull-upstreams.sh, deprecate bash"
```

---

### Task 10: Regression test — bash vs Python parity

**Files:**
- Create: `tests/structural/test_clavain_sync/test_regression.py`

This captures a dry-run from the bash version and verifies the Python version produces matching classifications.

**Step 1: Write the regression test**

```python
# tests/structural/test_clavain_sync/test_regression.py
"""Regression test: verify Python sync produces same classifications as bash.

This test runs both versions in dry-run mode against the real upstreams
and compares their classification output. Requires upstreams to be cloned.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _has_upstreams():
    """Check if upstream clones exist."""
    for d in [PROJECT_ROOT / ".upstream-work", Path("/root/projects/upstreams")]:
        if d.is_dir():
            return True
    return False


@pytest.mark.skipif(not _has_upstreams(), reason="Upstream clones not available")
def test_python_matches_bash_classifications():
    """Run both bash and Python in dry-run, compare classification counts."""
    # Run bash version
    bash_result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "sync-upstreams.sh"), "--dry-run"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        env={**os.environ, "NO_COLOR": "1"},
    )

    # Run Python version
    python_result = subprocess.run(
        ["python3", "-m", "clavain_sync", "sync", "--dry-run"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "scripts"), "NO_COLOR": "1"},
    )

    # Extract classification lines from both
    cls_pattern = re.compile(r"(COPY|AUTO|KEEP|SKIP|CONFLICT|REVIEW)\s+(\S+)")

    bash_cls = set(cls_pattern.findall(bash_result.stdout))
    python_cls = set(cls_pattern.findall(python_result.stdout))

    # They should produce the same classifications
    missing_in_python = bash_cls - python_cls
    extra_in_python = python_cls - bash_cls

    assert not missing_in_python, f"Bash had these but Python didn't: {missing_in_python}"
    assert not extra_in_python, f"Python had these but bash didn't: {extra_in_python}"
```

**Step 2: Run the regression test**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/test_regression.py -v`
Expected: PASS (or SKIP if upstreams not cloned)

**Step 3: Commit**

```bash
git add tests/structural/test_clavain_sync/test_regression.py
git commit -m "test(sync): add regression test comparing bash vs Python output"
```

---

### Task 11: Run full test suite + final verification

**Step 1: Run all clavain_sync unit tests**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m pytest tests/structural/test_clavain_sync/ -v`
Expected: All tests PASS

**Step 2: Run existing test suites (no regressions)**

Run: `cd /root/projects/Clavain && uv run pytest tests/structural/ -v`
Expected: All existing 512+ tests PASS

Run: `bats tests/shell/`
Expected: All 46 shell tests PASS

**Step 3: Smoke test the Python CLI end-to-end**

Run: `cd /root/projects/Clavain && PYTHONPATH=scripts python3 -m clavain_sync sync --dry-run`
Expected: Classifications for all 6 upstreams, no errors

**Step 4: Verify pull-upstreams.sh integration**

Run: `cd /root/projects/Clavain && bash scripts/pull-upstreams.sh --sync --dry-run`
Expected: Pulls upstreams, then runs Python sync in dry-run mode

Run: `cd /root/projects/Clavain && bash scripts/pull-upstreams.sh --sync --legacy --dry-run`
Expected: Pulls upstreams, then runs bash sync in dry-run mode

**Step 5: Final commit + update bead**

```bash
bd update Clavain-swio --status=in_progress
# After all tests pass:
bd close Clavain-swio --reason="Python sync rewrite complete, all tests pass, regression verified"
git add -A && git commit -m "feat(sync): complete Python sync rewrite (Clavain-swio)"
```
