"""Resolve upstream file paths to local paths using fileMap."""
from __future__ import annotations

import fnmatch


def resolve_local_path(changed_file: str, file_map: dict[str, str]) -> str | None:
    """Resolve an upstream-relative file path to its local path.

    changed_file MUST be relative to basePath (caller strips basePath
    before calling this function).

    Tries exact match first, then single-wildcard glob patterns.
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
