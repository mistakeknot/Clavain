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

    # Both unchanged but content differs — defensive branch.
    # This can only trigger if namespace replacement is non-deterministic
    # or if content was modified outside the sync process. Flags for human review.
    return Classification.REVIEW_UNEXPECTED
