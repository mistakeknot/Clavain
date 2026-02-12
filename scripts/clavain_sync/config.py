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
    _raw_path: Path = field(repr=False, default_factory=Path)


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
