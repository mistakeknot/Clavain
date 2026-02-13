"""Tests for detect-domains.py staleness detection, structural hash, and cache v1."""

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the hyphenated module name via importlib
_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "detect-domains.py"
_spec = importlib.util.spec_from_file_location("detect_domains", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

CACHE_VERSION = _mod.CACHE_VERSION
STRUCTURAL_FILES = _mod.STRUCTURAL_FILES
check_stale = _mod.check_stale
compute_structural_hash = _mod.compute_structural_hash
read_cache = _mod.read_cache
write_cache = _mod.write_cache
_check_stale_tier1 = _mod._check_stale_tier1
_check_stale_tier2 = _mod._check_stale_tier2
_check_stale_tier3 = _mod._check_stale_tier3
_parse_iso_datetime = _mod._parse_iso_datetime

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "detect-domains.py"


# ---------------------------------------------------------------------------
# Structural hash tests
# ---------------------------------------------------------------------------

class TestStructuralHash:
    def test_deterministic(self, tmp_path):
        """Same inputs produce same hash."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        h1 = compute_structural_hash(tmp_path)
        h2 = compute_structural_hash(tmp_path)
        assert h1 == h2

    def test_includes_algorithm_prefix(self, tmp_path):
        """Hash starts with 'sha256:'."""
        h = compute_structural_hash(tmp_path)
        assert h.startswith("sha256:")
        # hex digest after prefix
        hex_part = h.split(":", 1)[1]
        assert len(hex_part) == 64  # SHA-256 hex length

    def test_ignores_file_order(self, tmp_path):
        """Hash is independent of file creation order."""
        # Create in one order
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "Cargo.toml").write_text("[package]")
        h1 = compute_structural_hash(tmp_path)

        # Recreate in reverse order (same content)
        (tmp_path / "Cargo.toml").unlink()
        (tmp_path / "package.json").unlink()
        (tmp_path / "Cargo.toml").write_text("[package]")
        (tmp_path / "package.json").write_text("{}")
        h2 = compute_structural_hash(tmp_path)

        assert h1 == h2

    def test_file_deletion_changes_hash(self, tmp_path):
        """Removing a structural file changes the hash."""
        (tmp_path / "package.json").write_text("{}")
        h1 = compute_structural_hash(tmp_path)
        (tmp_path / "package.json").unlink()
        h2 = compute_structural_hash(tmp_path)
        assert h1 != h2

    def test_file_modification_changes_hash(self, tmp_path):
        """Modifying a structural file's content changes the hash."""
        (tmp_path / "package.json").write_text('{"name": "v1"}')
        h1 = compute_structural_hash(tmp_path)
        (tmp_path / "package.json").write_text('{"name": "v2"}')
        h2 = compute_structural_hash(tmp_path)
        assert h1 != h2

    def test_excludes_non_structural_files(self, tmp_path):
        """Non-structural files don't affect the hash."""
        h1 = compute_structural_hash(tmp_path)
        (tmp_path / "main.py").write_text("print('hello')")
        h2 = compute_structural_hash(tmp_path)
        assert h1 == h2

    def test_empty_project(self, tmp_path):
        """Empty project still produces a valid hash."""
        h = compute_structural_hash(tmp_path)
        assert h.startswith("sha256:")
        assert len(h.split(":", 1)[1]) == 64


# ---------------------------------------------------------------------------
# Cache v1 format tests
# ---------------------------------------------------------------------------

class TestCacheV1:
    def test_write_cache_includes_version(self, tmp_path):
        """write_cache includes cache_version: 1."""
        import yaml
        cache_path = tmp_path / "cache.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}], structural_hash="sha256:abc123")
        data = yaml.safe_load(cache_path.read_text())
        assert data["cache_version"] == 1

    def test_write_cache_includes_structural_hash(self, tmp_path):
        """write_cache includes the structural hash when provided."""
        import yaml
        cache_path = tmp_path / "cache.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}], structural_hash="sha256:abc123")
        data = yaml.safe_load(cache_path.read_text())
        assert data["structural_hash"] == "sha256:abc123"

    def test_write_cache_omits_hash_when_none(self, tmp_path):
        """write_cache omits structural_hash when not provided."""
        import yaml
        cache_path = tmp_path / "cache.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}])
        data = yaml.safe_load(cache_path.read_text())
        assert "structural_hash" not in data

    def test_cache_timestamp_is_full_iso8601(self, tmp_path):
        """detected_at includes time and timezone."""
        import yaml
        cache_path = tmp_path / "cache.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}])
        data = yaml.safe_load(cache_path.read_text())
        ts = data["detected_at"]
        # Should parse as full datetime, not just date
        parsed = dt.datetime.fromisoformat(ts)
        assert parsed.hour is not None or parsed.minute is not None  # has time component
        assert parsed.tzinfo is not None  # has timezone

    def test_write_cache_atomic_no_partial(self, tmp_path):
        """On write error, no partial cache file remains."""
        cache_dir = tmp_path / "cachedir"
        cache_dir.mkdir()
        cache_path = cache_dir / "cache.yaml"
        # Mock os.rename to simulate failure after write
        original_rename = os.rename
        def failing_rename(src, dst):
            raise OSError("simulated rename failure")
        with patch.object(_mod.os, "rename", side_effect=failing_rename):
            with pytest.raises(OSError):
                write_cache(cache_path, [{"name": "test"}], structural_hash="sha256:x")
        assert not cache_path.exists()
        # Verify temp file was cleaned up
        remaining = list(cache_dir.glob("*.tmp"))
        assert remaining == []

    def test_write_cache_roundtrip(self, tmp_path):
        """Cache can be written and read back."""
        cache_path = tmp_path / ".claude" / "flux-drive.yaml"
        results = [{"name": "game-simulation", "confidence": 0.65, "primary": True}]
        write_cache(cache_path, results, structural_hash="sha256:deadbeef")
        cached = read_cache(cache_path)
        assert cached is not None
        assert cached["cache_version"] == 1
        assert cached["structural_hash"] == "sha256:deadbeef"
        assert cached["domains"][0]["name"] == "game-simulation"


# ---------------------------------------------------------------------------
# ISO datetime parsing tests
# ---------------------------------------------------------------------------

class TestParseISODatetime:
    def test_full_iso(self):
        result = _parse_iso_datetime("2026-02-12T10:15:32+00:00")
        assert result is not None
        assert result.year == 2026

    def test_date_only(self):
        """v0 caches used date-only format."""
        result = _parse_iso_datetime("2026-02-12")
        assert result is not None
        assert result.year == 2026
        assert result.hour == 0

    def test_empty_string(self):
        assert _parse_iso_datetime("") is None

    def test_invalid(self):
        assert _parse_iso_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# Staleness check tests
# ---------------------------------------------------------------------------

class TestCheckStale:
    def test_no_cache_returns_4(self, tmp_path):
        """No cache file → exit 4."""
        result = check_stale(tmp_path, tmp_path / "nonexistent.yaml")
        assert result == 4

    def test_override_true_returns_0(self, tmp_path):
        """Cache with override: true → exit 0 (never stale)."""
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            "override: true\ndomains:\n  - name: custom\n    confidence: 1.0\ndetected_at: '2020-01-01'\n"
        )
        assert check_stale(tmp_path, cache_path) == 0

    def test_override_true_skips_hash(self, tmp_path):
        """override: true short-circuits before hash computation."""
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            "override: true\ndomains:\n  - name: custom\n    confidence: 1.0\ndetected_at: '2020-01-01'\n"
        )
        # Create structural changes that would make it stale
        (tmp_path / "package.json").write_text("{}")
        assert check_stale(tmp_path, cache_path) == 0

    def test_cache_version_mismatch_returns_3(self, tmp_path):
        """Old cache version → exit 3 (stale)."""
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            "cache_version: 0\ndomains:\n  - name: test\n    confidence: 0.5\n"
            "detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: 'sha256:abc'\n"
        )
        assert check_stale(tmp_path, cache_path) == 3

    def test_missing_cache_version_returns_3(self, tmp_path):
        """Missing cache_version (v0 format) → exit 3."""
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            "domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2026-02-12'\n"
        )
        assert check_stale(tmp_path, cache_path) == 3

    def test_fresh_hash_match_returns_0(self, tmp_path):
        """Tier 1: hash matches → exit 0."""
        # Write a cache with the current structural hash
        current_hash = compute_structural_hash(tmp_path)
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            f"cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            f"detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: '{current_hash}'\n"
        )
        assert check_stale(tmp_path, cache_path) == 0

    def test_structural_file_changed_returns_3(self, tmp_path):
        """Tier 1: structural file modified → hash mismatch → exit 3."""
        # Compute hash with no files
        old_hash = compute_structural_hash(tmp_path)
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            f"cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            f"detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: '{old_hash}'\n"
        )
        # Now add a structural file
        (tmp_path / "package.json").write_text('{"name": "new"}')
        assert check_stale(tmp_path, cache_path) == 3

    def test_non_structural_change_fresh(self, tmp_path):
        """Non-structural file changes don't affect hash → exit 0."""
        current_hash = compute_structural_hash(tmp_path)
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            f"cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            f"detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: '{current_hash}'\n"
        )
        # Add non-structural file
        (tmp_path / "main.py").write_text("print('hi')")
        assert check_stale(tmp_path, cache_path) == 0


# ---------------------------------------------------------------------------
# Tier-specific tests
# ---------------------------------------------------------------------------

class TestTier1:
    def test_no_hash_in_cache_returns_none(self, tmp_path):
        """Missing structural_hash → None (try next tier)."""
        cache = {"cache_version": 1, "domains": [{"name": "test"}], "detected_at": "2026-02-12T10:00:00+00:00"}
        assert _check_stale_tier1(tmp_path, cache) is None

    def test_hash_match_returns_0(self, tmp_path):
        h = compute_structural_hash(tmp_path)
        cache = {"structural_hash": h}
        assert _check_stale_tier1(tmp_path, cache) == 0

    def test_hash_mismatch_returns_3(self, tmp_path):
        cache = {"structural_hash": "sha256:definitely_wrong"}
        assert _check_stale_tier1(tmp_path, cache) == 3


class TestTier3:
    def test_old_file_fresh(self, tmp_path):
        """Structural file older than detected_at → fresh."""
        (tmp_path / "package.json").write_text("{}")
        # Set mtime to the past
        past = time.time() - 86400
        os.utime(tmp_path / "package.json", (past, past))
        cache = {"detected_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        assert _check_stale_tier3(tmp_path, cache) == 0

    def test_new_file_stale(self, tmp_path):
        """Structural file newer than detected_at → stale."""
        (tmp_path / "package.json").write_text("{}")
        # detected_at in the past
        cache = {"detected_at": "2020-01-01T00:00:00+00:00"}
        assert _check_stale_tier3(tmp_path, cache) == 3

    def test_no_timestamp_returns_3(self, tmp_path):
        """Missing detected_at → stale (can't verify)."""
        cache = {"detected_at": ""}
        assert _check_stale_tier3(tmp_path, cache) == 3

    def test_no_structural_files_fresh(self, tmp_path):
        """No structural files exist → fresh."""
        cache = {"detected_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        assert _check_stale_tier3(tmp_path, cache) == 0


# ---------------------------------------------------------------------------
# CLI tests for --check-stale
# ---------------------------------------------------------------------------

class TestCheckStaleCLI:
    def test_no_cache_exit_4(self, tmp_path):
        """CLI: --check-stale on project with no cache → exit 4."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 4

    def test_fresh_cache_exit_0(self, tmp_path):
        """CLI: --check-stale with fresh cache → exit 0."""
        current_hash = compute_structural_hash(tmp_path)
        cache_dir = tmp_path / ".claude"
        cache_dir.mkdir()
        (cache_dir / "flux-drive.yaml").write_text(
            f"cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            f"detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: '{current_hash}'\n"
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_stale_cache_exit_3(self, tmp_path):
        """CLI: --check-stale with stale cache → exit 3."""
        cache_dir = tmp_path / ".claude"
        cache_dir.mkdir()
        (cache_dir / "flux-drive.yaml").write_text(
            "cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            "detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: 'sha256:wrong'\n"
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 3

    def test_dry_run_produces_output(self, tmp_path):
        """CLI: --check-stale --dry-run prints diagnostic info."""
        current_hash = compute_structural_hash(tmp_path)
        cache_dir = tmp_path / ".claude"
        cache_dir.mkdir()
        (cache_dir / "flux-drive.yaml").write_text(
            f"cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            f"detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: '{current_hash}'\n"
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--check-stale", "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Tier 1" in result.stdout
        assert "FRESH" in result.stdout

    def test_override_exit_0(self, tmp_path):
        """CLI: --check-stale with override: true → exit 0."""
        cache_dir = tmp_path / ".claude"
        cache_dir.mkdir()
        (cache_dir / "flux-drive.yaml").write_text(
            "override: true\ndomains:\n  - name: custom\n    confidence: 1.0\ndetected_at: '2020-01-01'\n"
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_check_stale_under_100ms(self, tmp_path):
        """--check-stale Tier 1 should complete in <100ms on simple project."""
        # Set up a cache with matching hash
        current_hash = compute_structural_hash(tmp_path)
        cache_path = tmp_path / "cache.yaml"
        cache_path.write_text(
            f"cache_version: 1\ndomains:\n  - name: test\n    confidence: 0.5\n"
            f"detected_at: '2026-02-12T10:00:00+00:00'\nstructural_hash: '{current_hash}'\n"
        )
        start = time.monotonic()
        result = check_stale(tmp_path, cache_path)
        elapsed = time.monotonic() - start
        assert result == 0
        assert elapsed < 0.1, f"check_stale took {elapsed:.3f}s, expected <100ms"
