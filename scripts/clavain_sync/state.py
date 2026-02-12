"""Atomic state management for lastSyncedCommit in upstreams.json."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


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

    # Atomic write: temp file in same directory, then rename
    parent = config_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w", dir=parent, suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)

    # Restore original permissions
    tmp_path.chmod(original_stat.st_mode)
    try:
        os.chown(tmp_path, original_stat.st_uid, original_stat.st_gid)
    except PermissionError:
        pass  # Non-root can't chown, rely on default ACLs

    tmp_path.rename(config_path)
