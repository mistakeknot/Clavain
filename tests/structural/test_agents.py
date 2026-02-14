"""Tests for agent markdown files."""

import re

import pytest

from helpers import parse_frontmatter as _parse_frontmatter


def _get_agent_files(agents_dir):
    """Get all agent .md files from explicit category dirs."""
    agent_files = []
    for category in ["review", "research", "workflow"]:
        category_dir = agents_dir / category
        if category_dir.is_dir():
            agent_files.extend(sorted(category_dir.glob("*.md")))
    return agent_files


def test_agent_count(agents_dir):
    """Total agent count matches expected value."""
    agent_files = _get_agent_files(agents_dir)
    assert len(agent_files) == 10, (
        f"Expected 10 agents, found {len(agent_files)}: "
        f"{[f.stem for f in agent_files]}"
    )


@pytest.fixture(scope="module")
def agent_files_for_param(request):
    """Get agent files for parametrize — uses indirect fixture."""
    pass


def _agent_ids():
    """Generate agent file paths for parametrize at collection time."""
    from pathlib import Path
    agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
    files = []
    for category in ["review", "research", "workflow"]:
        category_dir = agents_dir / category
        if category_dir.is_dir():
            files.extend(sorted(category_dir.glob("*.md")))
    return files


AGENT_FILES = _agent_ids()


@pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_has_frontmatter(agent_file):
    """Each agent .md has YAML frontmatter between --- markers."""
    fm, _ = _parse_frontmatter(agent_file)
    assert fm is not None, f"{agent_file.name} is missing YAML frontmatter"


@pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_frontmatter_required_fields(agent_file):
    """Frontmatter has 'name' and 'description'."""
    fm, _ = _parse_frontmatter(agent_file)
    assert fm is not None, f"{agent_file.name} has no frontmatter"
    for field in ("name", "description"):
        assert field in fm, (
            f"{agent_file.name} frontmatter missing required field: {field}"
        )


@pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_name_matches_filename(agent_file):
    """Frontmatter 'name' matches filename without .md extension."""
    fm, _ = _parse_frontmatter(agent_file)
    assert fm is not None, f"{agent_file.name} has no frontmatter"
    expected = agent_file.stem
    actual = fm.get("name", "")
    assert actual == expected, (
        f"Name mismatch in {agent_file.name}: "
        f"frontmatter says {actual!r}, filename says {expected!r}"
    )


@pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_filenames_kebab_case(agent_file):
    """Agent filenames follow kebab-case convention."""
    stem = agent_file.stem
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", stem), (
        f"Filename {agent_file.name!r} is not kebab-case"
    )


@pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_model_valid(agent_file):
    """If model is present in frontmatter, it must be 'inherit' or 'haiku'."""
    fm, _ = _parse_frontmatter(agent_file)
    if fm is None:
        return
    model = fm.get("model")
    if model is not None:
        assert model in ("inherit", "haiku", "sonnet"), (
            f"{agent_file.name} has invalid model: {model!r}"
        )


@pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_body_nonempty(agent_file):
    """Body after frontmatter is at least 50 characters."""
    _, body = _parse_frontmatter(agent_file)
    body_stripped = body.strip()
    assert len(body_stripped) >= 50, (
        f"{agent_file.name} body is too short ({len(body_stripped)} chars)"
    )


def test_agent_top_level_subdirectories_valid(agents_dir):
    """Only review/, research/, workflow/ as top-level subdirs of agents/."""
    allowed = {"review", "research", "workflow"}
    actual = {
        d.name for d in agents_dir.iterdir()
        if d.is_dir()
    }
    unexpected = actual - allowed
    assert not unexpected, (
        f"Unexpected top-level agent directories: {unexpected}"
    )
