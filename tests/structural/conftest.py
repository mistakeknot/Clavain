"""Shared fixtures for Clavain structural tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Path to the Clavain repository root."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def agents_dir(project_root: Path) -> Path:
    return project_root / "agents"


@pytest.fixture(scope="session")
def skills_dir(project_root: Path) -> Path:
    return project_root / "skills"


@pytest.fixture(scope="session")
def commands_dir(project_root: Path) -> Path:
    return project_root / "commands"


@pytest.fixture(scope="session")
def hooks_dir(project_root: Path) -> Path:
    return project_root / "hooks"


@pytest.fixture(scope="session")
def all_agent_files(agents_dir: Path) -> list[Path]:
    """All agent .md files from explicit category dirs (excludes references/)."""
    agent_files = []
    for category in ["review", "research", "workflow"]:
        category_dir = agents_dir / category
        if category_dir.is_dir():
            agent_files.extend(sorted(category_dir.glob("*.md")))
    return agent_files


@pytest.fixture(scope="session")
def all_skill_dirs(skills_dir: Path) -> list[Path]:
    """All skill directories that contain a SKILL.md file."""
    return sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


@pytest.fixture(scope="session")
def all_command_files(commands_dir: Path) -> list[Path]:
    """All command .md files."""
    return sorted(commands_dir.glob("*.md"))


@pytest.fixture(scope="session")
def plugin_json(project_root: Path) -> dict:
    """Parsed plugin.json."""
    with open(project_root / ".claude-plugin" / "plugin.json") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def hooks_json(project_root: Path) -> dict:
    """Parsed hooks.json."""
    with open(project_root / "hooks" / "hooks.json") as f:
        return json.load(f)
