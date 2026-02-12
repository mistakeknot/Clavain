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
