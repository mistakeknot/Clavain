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


def test_skill_count(skills_dir, plugin_json):
    """Skill count on filesystem matches plugin.json manifest."""
    dirs = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
    expected = len(plugin_json.get("skills", []))
    assert len(dirs) == expected, (
        f"plugin.json lists {expected} skills, filesystem has {len(dirs)}: {[d.name for d in dirs]}"
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


# --- Description budget, references links and coverage (bead mk-yvmw9.7) ---

DESCRIPTION_CAP = 1024
_LINK_RE = re.compile(r"\]\(\s*(references/[^)\s#]+)(?:#[^)]*)?\s*\)")


def _unfolded_description(skill_md):
    """Description after YAML unfolding, or None when absent."""
    fm, _ = _parse_frontmatter(skill_md)
    if not fm:
        return None
    desc = fm.get("description")
    return None if desc is None else str(desc).strip()


def _dead_reference_links(skill_md):
    """Relative SKILL.md links into references/ whose target is missing."""
    text = skill_md.read_text(encoding="utf-8")
    return [
        rel for rel in _LINK_RE.findall(text)
        if not (skill_md.parent / rel).exists()
    ]


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_description_within_cap(skill_dir):
    """Unfolded description fits the cap; truncation drops the routing tail."""
    desc = _unfolded_description(skill_dir / "SKILL.md")
    assert desc, f"{skill_dir.name}/SKILL.md has no description"
    assert len(desc) <= DESCRIPTION_CAP, (
        f"{skill_dir.name} description is {len(desc)} chars, cap {DESCRIPTION_CAP}"
    )


def test_description_parser_is_not_vacuous():
    """Positive control: some real description is long enough that a broken
    parser returning short or empty strings would be caught."""
    lengths = [len(_unfolded_description(d / "SKILL.md") or "") for d in SKILL_DIRS]
    assert max(lengths) > 200, f"longest description is only {max(lengths)} chars"


def test_description_cap_catches_planted_overlong(tmp_path):
    """Planted fixture: a folded description over the cap is measured as over."""
    d = tmp_path / "planted"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: planted\ndescription: >\n  " + "word " * 300 + "\n---\n" + "body " * 20
    )
    assert len(_unfolded_description(d / "SKILL.md")) > DESCRIPTION_CAP


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_references_links_resolve(skill_dir):
    """Every relative link from SKILL.md into references/ exists."""
    dead = _dead_reference_links(skill_dir / "SKILL.md")
    assert not dead, f"{skill_dir.name}/SKILL.md has dead references links: {dead}"


def test_reference_link_check_catches_planted_dead_link(tmp_path):
    """Planted fixture: a dead link is reported, a live one is not."""
    d = tmp_path / "planted"
    (d / "references").mkdir(parents=True)
    (d / "references" / "ok.md").write_text("x")
    (d / "SKILL.md").write_text(
        "---\nname: planted\ndescription: x\n---\n"
        "[ok](references/ok.md) [bad](references/missing.md#a)\n"
    )
    assert _dead_reference_links(d / "SKILL.md") == ["references/missing.md"]


def test_every_skill_dir_is_covered(skills_dir):
    """Every directory under skills/ is in the parametrized set, so a new
    skill cannot escape the per-skill checks above."""
    on_disk = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
    covered = sorted(d.name for d in SKILL_DIRS)
    assert on_disk == covered, (
        f"skill dirs without SKILL.md or not collected: {sorted(set(on_disk) ^ set(covered))}"
    )
