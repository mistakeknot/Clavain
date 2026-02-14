"""Tests for skill directories and SKILL.md files."""

import re
from pathlib import Path

import pytest

from helpers import parse_frontmatter as _parse_frontmatter


def _get_skill_dirs():
    """Get all skill directories containing SKILL.md at collection time."""
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    return sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


SKILL_DIRS = _get_skill_dirs()


def test_skill_count(skills_dir):
    """Total skill count matches expected value."""
    dirs = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
    assert len(dirs) == 27, (
        f"Expected 27 skills, found {len(dirs)}: {[d.name for d in dirs]}"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_skillmd(skill_dir):
    """Every skill directory contains SKILL.md."""
    assert (skill_dir / "SKILL.md").exists(), (
        f"{skill_dir.name}/ is missing SKILL.md"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_frontmatter(skill_dir):
    """Each SKILL.md has YAML frontmatter."""
    fm, _ = _parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md is missing frontmatter"


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_frontmatter_required_fields(skill_dir):
    """Frontmatter has 'name' and 'description'."""
    fm, _ = _parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md has no frontmatter"
    for field in ("name", "description"):
        assert field in fm, (
            f"{skill_dir.name}/SKILL.md frontmatter missing: {field}"
        )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_name_matches_dirname(skill_dir):
    """Frontmatter 'name' matches directory name."""
    fm, _ = _parse_frontmatter(skill_dir / "SKILL.md")
    assert fm is not None, f"{skill_dir.name}/SKILL.md has no frontmatter"
    expected = skill_dir.name
    actual = fm.get("name", "")
    assert actual == expected, (
        f"Name mismatch in {skill_dir.name}/SKILL.md: "
        f"frontmatter says {actual!r}, dirname says {expected!r}"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_dirname_kebab_case(skill_dir):
    """Skill directory names follow kebab-case convention."""
    name = skill_dir.name
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name), (
        f"Skill directory {name!r} is not kebab-case"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_body_nonempty(skill_dir):
    """Body after frontmatter is at least 50 characters."""
    _, body = _parse_frontmatter(skill_dir / "SKILL.md")
    body_stripped = body.strip()
    assert len(body_stripped) >= 50, (
        f"{skill_dir.name}/SKILL.md body is too short ({len(body_stripped)} chars)"
    )


def test_no_orphan_skill_dirs(skills_dir):
    """No empty directories in skills/."""
    for d in skills_dir.iterdir():
        if d.is_dir():
            contents = list(d.iterdir())
            assert len(contents) > 0, f"Orphan (empty) skill directory: {d.name}/"
