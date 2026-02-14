"""Tests for config.py — loading and validating upstreams.json."""
import json
import pytest
from pathlib import Path

from clavain_sync.config import load_config, UpstreamConfig


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
            "protectedFiles": ["commands/sprint.md"],
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
    assert "commands/sprint.md" in cfg.protected_files
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
