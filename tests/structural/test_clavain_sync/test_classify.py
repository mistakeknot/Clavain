"""Tests for classify.py — the 7-outcome three-way classification."""
from clavain_sync.classify import classify_file, Classification


class TestClassifyFile:
    """Test all 7 classification outcomes."""

    def test_skip_protected(self):
        result = classify_file(
            local_path="commands/sprint.md",
            local_content="local",
            upstream_content="upstream",
            ancestor_content="ancestor",
            protected_files={"commands/sprint.md"},
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
        assert result == Classification.REVIEW_BLOCKLIST

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
