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
