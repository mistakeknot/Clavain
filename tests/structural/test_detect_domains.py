"""Tests for scripts/detect-domains.py domain detection."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Import the hyphenated module name via importlib
_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "detect-domains.py"
_spec = importlib.util.spec_from_file_location("detect_domains", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

CACHE_VERSION = _mod.CACHE_VERSION
DomainSpec = _mod.DomainSpec
STRUCTURAL_FILES = _mod.STRUCTURAL_FILES
check_stale = _mod.check_stale
compute_structural_hash = _mod.compute_structural_hash
detect = _mod.detect
gather_directories = _mod.gather_directories
gather_files = _mod.gather_files
gather_frameworks = _mod.gather_frameworks
gather_keywords = _mod.gather_keywords
load_index = _mod.load_index
read_cache = _mod.read_cache
score_domain = _mod.score_domain
write_cache = _mod.write_cache

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "detect-domains.py"
INDEX_PATH = ROOT / "config" / "flux-drive" / "domains" / "index.yaml"


class TestLoadIndex:
    def test_parses_real_index(self):
        """Parse real index.yaml - verify 11 domains, each with 4 signal categories."""
        domains = load_index(INDEX_PATH)
        assert len(domains) == 11

    def test_each_domain_has_signal_categories(self):
        domains = load_index(INDEX_PATH)
        for d in domains:
            assert isinstance(d.directories, list)
            assert isinstance(d.files, list)
            assert isinstance(d.frameworks, list)
            assert isinstance(d.keywords, list)
            assert d.profile  # non-empty name

    def test_domain_profiles_are_unique(self):
        domains = load_index(INDEX_PATH)
        names = [d.profile for d in domains]
        assert len(names) == len(set(names))


class TestScoring:
    def test_all_equal_halves(self):
        """score_domain(0.5, 0.5, 0.5, 0.5) == 0.5."""
        assert score_domain(0.5, 0.5, 0.5, 0.5) == pytest.approx(0.5)

    def test_all_zeros(self):
        assert score_domain(0.0, 0.0, 0.0, 0.0) == 0.0

    def test_all_ones(self):
        assert score_domain(1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_weighted_correctly(self):
        """Only directories signal present - score = 0.3."""
        assert score_domain(1.0, 0.0, 0.0, 0.0) == pytest.approx(0.3)

    def test_only_frameworks(self):
        """Only frameworks signal present - score = 0.3."""
        assert score_domain(0.0, 0.0, 1.0, 0.0) == pytest.approx(0.3)


class TestGatherDirectories:
    def test_matching_subdirs(self, tmp_path):
        (tmp_path / "game").mkdir()
        (tmp_path / "sim").mkdir()
        (tmp_path / "unrelated").mkdir()
        score = gather_directories(tmp_path, ["game", "sim", "ecs", "combat"])
        assert score == pytest.approx(0.5)  # 2 of 4

    def test_no_signals(self, tmp_path):
        assert gather_directories(tmp_path, []) == 0.0

    def test_nested_signal(self, tmp_path):
        (tmp_path / "ai").mkdir()
        (tmp_path / "ai" / "behavior").mkdir()
        score = gather_directories(tmp_path, ["ai/behavior", "ecs"])
        assert score == pytest.approx(0.5)  # 1 of 2

    def test_empty_project(self, tmp_path):
        score = gather_directories(tmp_path, ["game", "sim"])
        assert score == 0.0


class TestGatherFiles:
    def test_matching_files(self, tmp_path):
        (tmp_path / "game.toml").touch()
        (tmp_path / "balance.yaml").touch()
        score = gather_files(tmp_path, ["game.toml", "balance.yaml", "*.gd", "*.unity"])
        assert score == pytest.approx(0.5)  # 2 of 4

    def test_glob_pattern_matching(self, tmp_path):
        (tmp_path / "level1.gd").touch()
        score = gather_files(tmp_path, ["*.gd"])
        assert score == pytest.approx(1.0)

    def test_file_in_subdirectory(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "main.go").touch()
        score = gather_files(tmp_path, ["main.go"])
        assert score == pytest.approx(1.0)


class TestGatherFrameworks:
    def test_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"bevy": "0.1", "react": "18.0"}}),
            encoding="utf-8",
        )
        score = gather_frameworks(tmp_path, ["bevy", "godot", "unity"])
        assert score == pytest.approx(1 / 3)

    def test_cargo_toml(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "test"\n\n[dependencies]\nbevy = "0.12"\n',
            encoding="utf-8",
        )
        score = gather_frameworks(tmp_path, ["bevy", "macroquad"])
        assert score == pytest.approx(0.5)

    def test_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytorch>=2.0\nnumpy\n", encoding="utf-8")
        score = gather_frameworks(tmp_path, ["pytorch", "tensorflow", "keras"])
        assert score == pytest.approx(1 / 3)

    def test_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi>=0.100", "uvicorn"]\n',
            encoding="utf-8",
        )
        score = gather_frameworks(tmp_path, ["fastapi", "django", "flask"])
        assert score == pytest.approx(1 / 3)

    def test_no_build_files(self, tmp_path):
        score = gather_frameworks(tmp_path, ["bevy"])
        assert score == 0.0

    def test_empty_signals(self, tmp_path):
        assert gather_frameworks(tmp_path, []) == 0.0


class TestGatherKeywords:
    def test_finds_keywords_in_source(self, tmp_path):
        (tmp_path / "main.py").write_text("delta_time = 0.016\nfixed_update()\n", encoding="utf-8")
        score = gather_keywords(tmp_path, ["delta_time", "fixed_update", "navmesh", "pathfinding"])
        assert score == pytest.approx(0.5)  # 2 of 4

    def test_no_source_files(self, tmp_path):
        (tmp_path / "readme.md").write_text("just docs", encoding="utf-8")
        score = gather_keywords(tmp_path, ["delta_time"])
        assert score == 0.0


class TestCacheRoundtrip:
    def test_write_then_read(self, tmp_path):
        cache_path = tmp_path / ".claude" / "flux-drive.yaml"
        results = [
            {"name": "game-simulation", "confidence": 0.65, "primary": True},
            {"name": "cli-tool", "confidence": 0.35},
        ]
        write_cache(cache_path, results)
        cached = read_cache(cache_path)
        assert cached is not None
        assert len(cached["domains"]) == 2
        assert cached["domains"][0]["name"] == "game-simulation"
        assert cached["domains"][0]["confidence"] == 0.65
        assert cached["domains"][0]["primary"] is True
        assert cached["detected_at"]  # non-empty

    def test_read_missing_file(self, tmp_path):
        assert read_cache(tmp_path / "nonexistent.yaml") is None

    def test_cache_override_respected(self, tmp_path):
        """Cache with override: true preserves user intent."""
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            "override: true\ndomains:\n  - name: custom\n    confidence: 1.0\ndetected_at: '2026-01-01'\n",
            encoding="utf-8",
        )
        cached = read_cache(cache_path)
        assert cached is not None
        assert cached["override"] is True
        assert cached["domains"][0]["name"] == "custom"


class TestCacheV1:
    """Tests for cache format v1 features: cache_version, structural_hash, ISO timestamps."""

    def test_write_includes_cache_version(self, tmp_path):
        """write_cache() always includes cache_version in output."""
        cache_path = tmp_path / "flux-drive.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}])
        cached = read_cache(cache_path)
        assert cached is not None
        assert cached["cache_version"] == CACHE_VERSION

    def test_write_includes_structural_hash(self, tmp_path):
        """write_cache() with structural_hash param includes it in output."""
        cache_path = tmp_path / "flux-drive.yaml"
        test_hash = "sha256:abc123"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}], structural_hash=test_hash)
        cached = read_cache(cache_path)
        assert cached is not None
        assert cached["structural_hash"] == test_hash

    def test_write_without_structural_hash(self, tmp_path):
        """write_cache() without structural_hash param omits the key."""
        cache_path = tmp_path / "flux-drive.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}])
        cached = read_cache(cache_path)
        assert cached is not None
        assert "structural_hash" not in cached

    def test_write_iso_timestamp(self, tmp_path):
        """write_cache() emits full ISO 8601 timestamp with timezone."""
        cache_path = tmp_path / "flux-drive.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}])
        cached = read_cache(cache_path)
        assert cached is not None
        ts = cached["detected_at"]
        # Should contain T separator and timezone info
        assert "T" in ts
        assert "+" in ts or "Z" in ts

    def test_atomic_write_creates_parent_dirs(self, tmp_path):
        """write_cache() creates parent directories if needed."""
        cache_path = tmp_path / "deep" / "nested" / "flux-drive.yaml"
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}])
        assert cache_path.exists()
        cached = read_cache(cache_path)
        assert cached is not None


class TestStructuralHash:
    """Tests for compute_structural_hash()."""

    def test_empty_project_deterministic(self, tmp_path):
        """Empty project - consistent hash (all files absent)."""
        h1 = compute_structural_hash(tmp_path)
        h2 = compute_structural_hash(tmp_path)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_hash_changes_with_file(self, tmp_path):
        """Adding a structural file changes the hash."""
        h1 = compute_structural_hash(tmp_path)
        (tmp_path / "package.json").write_text('{"name": "test"}', encoding="utf-8")
        h2 = compute_structural_hash(tmp_path)
        assert h1 != h2

    def test_hash_stable_with_same_content(self, tmp_path):
        """Same file content - same hash regardless of mtime."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        h1 = compute_structural_hash(tmp_path)
        # Rewrite with identical content
        time.sleep(0.01)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
        h2 = compute_structural_hash(tmp_path)
        assert h1 == h2

    def test_hash_ignores_non_structural_files(self, tmp_path):
        """Non-structural files do not affect the hash."""
        h1 = compute_structural_hash(tmp_path)
        (tmp_path / "README.md").write_text("hello", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
        h2 = compute_structural_hash(tmp_path)
        assert h1 == h2

    def test_hash_prefix_format(self, tmp_path):
        """Hash output has sha256: prefix."""
        h = compute_structural_hash(tmp_path)
        assert h.startswith("sha256:")
        hex_part = h.split(":")[1]
        assert len(hex_part) == 64  # SHA-256 hex length

    def test_all_structural_files_considered(self, tmp_path):
        """Each STRUCTURAL_FILE independently affects the hash."""
        base_hash = compute_structural_hash(tmp_path)
        for name in sorted(STRUCTURAL_FILES):
            (tmp_path / name).write_text(f"content-{name}", encoding="utf-8")
            new_hash = compute_structural_hash(tmp_path)
            assert new_hash != base_hash, f"Adding {name} should change the hash"
            (tmp_path / name).unlink()


class TestStalenessCheck:
    """Tests for check_stale() and its tier functions."""

    def test_no_cache_returns_4(self, tmp_path):
        """No cache file - exit code 4."""
        result = check_stale(tmp_path, tmp_path / ".claude" / "flux-drive.yaml")
        assert result == 4

    def test_override_always_fresh(self, tmp_path):
        """Cache with override: true - exit code 0 regardless of staleness."""
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            "override: true\ncache_version: 1\ndomains:\n  - name: custom\n    confidence: 1.0\ndetected_at: '2026-01-01'\n",
            encoding="utf-8",
        )
        result = check_stale(tmp_path, cache_path)
        assert result == 0

    def test_missing_version_is_stale(self, tmp_path):
        """Cache without cache_version - exit code 3 (format upgrade)."""
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            "domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2026-01-01'\n",
            encoding="utf-8",
        )
        result = check_stale(tmp_path, cache_path)
        assert result == 3

    def test_old_version_is_stale(self, tmp_path):
        """Cache with version < current - exit code 3."""
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            "cache_version: 0\ndomains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2026-01-01'\n",
            encoding="utf-8",
        )
        result = check_stale(tmp_path, cache_path)
        assert result == 3

    def test_matching_hash_is_fresh(self, tmp_path):
        """Cache with matching structural hash - exit code 0."""
        current_hash = compute_structural_hash(tmp_path)
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            f"cache_version: {CACHE_VERSION}\nstructural_hash: '{current_hash}'\n"
            f"domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2026-01-01T00:00:00+00:00'\n",
            encoding="utf-8",
        )
        result = check_stale(tmp_path, cache_path)
        assert result == 0

    def test_mismatched_hash_is_stale(self, tmp_path):
        """Cache with different structural hash - exit code 3."""
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            f"cache_version: {CACHE_VERSION}\nstructural_hash: 'sha256:stale_hash_value'\n"
            f"domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2026-01-01T00:00:00+00:00'\n",
            encoding="utf-8",
        )
        result = check_stale(tmp_path, cache_path)
        assert result == 3

    def test_roundtrip_freshness(self, tmp_path):
        """Write cache with hash, immediately check - fresh."""
        cache_path = tmp_path / ".claude" / "flux-drive.yaml"
        current_hash = compute_structural_hash(tmp_path)
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}], structural_hash=current_hash)
        result = check_stale(tmp_path, cache_path)
        assert result == 0

    def test_roundtrip_stale_after_change(self, tmp_path):
        """Write cache, add structural file, check - stale."""
        cache_path = tmp_path / ".claude" / "flux-drive.yaml"
        current_hash = compute_structural_hash(tmp_path)
        write_cache(cache_path, [{"name": "test", "confidence": 0.5}], structural_hash=current_hash)
        # Add a structural file to change the hash
        (tmp_path / "package.json").write_text('{"name": "new"}', encoding="utf-8")
        result = check_stale(tmp_path, cache_path)
        assert result == 3

    def test_tier3_fresh_when_files_older(self, tmp_path):
        """Tier 3: structural files older than detection - fresh."""
        # Create a structural file with old mtime (1 year ago)
        (tmp_path / "go.mod").write_text("module test\n", encoding="utf-8")
        old_time = time.time() - 86400 * 365  # 1 year ago
        os.utime(tmp_path / "go.mod", (old_time, old_time))
        # Write cache without hash (forces tier 2/3 path), no .git (skips tier 2)
        # Use current time as detected_at to ensure file is clearly older
        import datetime as dt
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        cache_path = tmp_path / "flux-drive.yaml"
        cache_path.write_text(
            f"cache_version: {CACHE_VERSION}\n"
            f"domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '{now_iso}'\n",
            encoding="utf-8",
        )
        result = check_stale(tmp_path, cache_path)
        assert result == 0

    def test_tier3_stale_when_files_newer(self, tmp_path):
        """Tier 3: structural files newer than detection - stale."""
        cache_path = tmp_path / "flux-drive.yaml"
        # Detection was long ago
        cache_path.write_text(
            f"cache_version: {CACHE_VERSION}\n"
            f"domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2020-01-01T00:00:00+00:00'\n",
            encoding="utf-8",
        )
        # Create a structural file now (newer than detection)
        (tmp_path / "go.mod").write_text("module test\n", encoding="utf-8")
        result = check_stale(tmp_path, cache_path)
        assert result == 3


class TestCLICheckStale:
    """Tests for --check-stale CLI flag."""

    def test_no_cache_exit_4(self, tmp_path):
        """--check-stale on project with no cache - exit code 4."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-stale", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 4

    def test_stale_cache_exit_3(self, tmp_path):
        """--check-stale on project with outdated cache - exit code 3."""
        cache_dir = tmp_path / ".claude"
        cache_dir.mkdir()
        (cache_dir / "flux-drive.yaml").write_text(
            "domains:\n  - name: test\n    confidence: 0.5\ndetected_at: '2026-01-01'\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-stale", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 3

    def test_fresh_cache_exit_0(self, tmp_path):
        """--check-stale on project with fresh cache - exit code 0."""
        # Create enough signals for detection
        (tmp_path / ".claude-plugin").mkdir(exist_ok=True)
        (tmp_path / "skills").mkdir(exist_ok=True)
        (tmp_path / "agents").mkdir(exist_ok=True)
        (tmp_path / "commands").mkdir(exist_ok=True)
        (tmp_path / "hooks").mkdir(exist_ok=True)
        (tmp_path / "plugin.json").touch()
        (tmp_path / "SKILL.md").touch()
        # Run detection with caching enabled
        subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        # Now check staleness
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-stale", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0

    def test_dry_run_outputs_diagnostics(self, tmp_path):
        """--check-stale --dry-run produces diagnostic output."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-stale", "--dry-run", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        # Should have some output (even if just "No cache found.")
        assert result.stdout.strip() or result.returncode == 4


class TestDetect:
    def test_detects_game_project(self, tmp_path):
        """A project with game signals should detect game-simulation."""
        for d in ("game", "sim", "ecs", "combat", "inventory", "procgen"):
            (tmp_path / d).mkdir()
        (tmp_path / "game.toml").touch()
        (tmp_path / "balance.yaml").touch()
        (tmp_path / "project.godot").touch()
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "test"\n\n[dependencies]\nbevy = "0.12"\nggez = "0.9"\n',
            encoding="utf-8",
        )
        (tmp_path / "main.rs").write_text(
            "fn fixed_update() { let dt = delta_time; }\nfn tick_rate() {}\nstruct BehaviorTree;",
            encoding="utf-8",
        )
        for d in ("narrative", "crafting", "worldgen", "tick", "drama"):
            (tmp_path / d).mkdir()
        domains = load_index(INDEX_PATH)
        results = detect(tmp_path, domains, skip_keywords_threshold=False)
        names = [r["name"] for r in results]
        assert "game-simulation" in names

    def test_empty_project_returns_empty(self, tmp_path):
        domains = load_index(INDEX_PATH)
        results = detect(tmp_path, domains)
        assert results == []

    def test_primary_is_highest_confidence(self, tmp_path):
        """The highest-confidence domain is marked primary."""
        (tmp_path / "game").mkdir()
        (tmp_path / "cmd").mkdir()
        (tmp_path / "game.toml").touch()
        domains = load_index(INDEX_PATH)
        results = detect(tmp_path, domains, skip_keywords_threshold=False)
        if len(results) > 0:
            assert results[0].get("primary") is True
            for r in results[1:]:
                assert "primary" not in r or r["primary"] is not True


class TestCLI:
    def test_empty_project_exit_1(self, tmp_path):
        """Running on an empty project returns exit code 1."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--json", "--no-cache"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 1

    def test_json_output_parses(self, tmp_path):
        """JSON output is valid and has expected keys."""
        (tmp_path / ".claude-plugin").mkdir()
        (tmp_path / "skills").mkdir()
        (tmp_path / "agents").mkdir()
        (tmp_path / "commands").mkdir()
        (tmp_path / "hooks").mkdir()
        (tmp_path / "plugin.json").touch()
        (tmp_path / "SKILL.md").touch()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--json", "--no-cache"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "domains" in data
        assert "detected_at" in data
        assert isinstance(data["domains"], list)
        assert len(data["domains"]) > 0
        assert "name" in data["domains"][0]
        assert "confidence" in data["domains"][0]

    def test_invalid_project_exit_2(self):
        """Running on a nonexistent path returns exit code 2."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "/nonexistent/path/xyz", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 2
