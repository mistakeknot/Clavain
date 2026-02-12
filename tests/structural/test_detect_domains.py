"""Tests for scripts/detect-domains.py domain detection."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Import the hyphenated module name via importlib
_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "detect-domains.py"
_spec = importlib.util.spec_from_file_location("detect_domains", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

DomainSpec = _mod.DomainSpec
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
        """Parse real index.yaml — verify 11 domains, each with 4 signal categories."""
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
        """Only directories signal present → score = 0.3."""
        assert score_domain(1.0, 0.0, 0.0, 0.0) == pytest.approx(0.3)

    def test_only_frameworks(self):
        """Only frameworks signal present → score = 0.3."""
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


class TestDetect:
    def test_detects_game_project(self, tmp_path):
        """A project with game signals should detect game-simulation."""
        # Create enough signals to exceed min_confidence (0.3)
        # Directories: 6/17 = 0.35 → 0.35*0.3 = 0.105
        for d in ("game", "sim", "ecs", "combat", "inventory", "procgen"):
            (tmp_path / d).mkdir()
        # Files: 3/11 = 0.27 → 0.27*0.2 = 0.054
        (tmp_path / "game.toml").touch()
        (tmp_path / "balance.yaml").touch()
        (tmp_path / "project.godot").touch()
        # Frameworks: 2/12 = 0.17 → 0.17*0.3 = 0.050
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "test"\n\n[dependencies]\nbevy = "0.12"\nggez = "0.9"\n',
            encoding="utf-8",
        )
        # Keywords: source file with hits → 4/15 = 0.27 → 0.27*0.2 = 0.053
        (tmp_path / "main.rs").write_text(
            "fn fixed_update() { let dt = delta_time; }\nfn tick_rate() {}\nstruct BehaviorTree;",
            encoding="utf-8",
        )
        # Add more dirs and a keyword file to push over min_confidence
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
        # Create enough signals for multiple domains
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
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1

    def test_json_output_parses(self, tmp_path):
        """JSON output is valid and has expected keys."""
        # Create enough signals to trigger detection
        (tmp_path / ".claude-plugin").mkdir()
        (tmp_path / "skills").mkdir()
        (tmp_path / "agents").mkdir()
        (tmp_path / "commands").mkdir()
        (tmp_path / "hooks").mkdir()
        (tmp_path / "plugin.json").touch()
        (tmp_path / "SKILL.md").touch()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(tmp_path), "--json", "--no-cache"],
            capture_output=True,
            text=True,
            timeout=30,
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
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 2
