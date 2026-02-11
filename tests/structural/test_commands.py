"""Tests for command markdown files."""

import re
from pathlib import Path

import pytest

from helpers import parse_frontmatter as _parse_frontmatter


def _get_command_files():
    """Get all command .md files at collection time."""
    commands_dir = Path(__file__).resolve().parent.parent.parent / "commands"
    return sorted(commands_dir.glob("*.md"))


COMMAND_FILES = _get_command_files()


def test_command_count(commands_dir):
    """Total command count matches expected value."""
    files = sorted(commands_dir.glob("*.md"))
    assert len(files) == 24, (
        f"Expected 24 commands, found {len(files)}: {[f.stem for f in files]}"
    )


@pytest.mark.parametrize("cmd_file", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_has_frontmatter(cmd_file):
    """Each command .md has YAML frontmatter."""
    fm, _ = _parse_frontmatter(cmd_file)
    assert fm is not None, f"{cmd_file.name} is missing YAML frontmatter"


@pytest.mark.parametrize("cmd_file", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_frontmatter_required_fields(cmd_file):
    """Frontmatter has 'name' and 'description'."""
    fm, _ = _parse_frontmatter(cmd_file)
    assert fm is not None, f"{cmd_file.name} has no frontmatter"
    for field in ("name", "description"):
        assert field in fm, (
            f"{cmd_file.name} frontmatter missing: {field}"
        )


@pytest.mark.parametrize("cmd_file", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_name_matches_filename(cmd_file):
    """Frontmatter 'name' matches filename without .md extension."""
    fm, _ = _parse_frontmatter(cmd_file)
    assert fm is not None, f"{cmd_file.name} has no frontmatter"
    expected = cmd_file.stem
    actual = fm.get("name", "")
    assert actual == expected, (
        f"Name mismatch in {cmd_file.name}: "
        f"frontmatter says {actual!r}, filename says {expected!r}"
    )


@pytest.mark.parametrize("cmd_file", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_filenames_kebab_case(cmd_file):
    """Command filenames follow kebab-case convention."""
    stem = cmd_file.stem
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", stem), (
        f"Command filename {cmd_file.name!r} is not kebab-case"
    )


@pytest.mark.parametrize("cmd_file", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_body_nonempty(cmd_file):
    """Body after frontmatter is at least 10 characters."""
    _, body = _parse_frontmatter(cmd_file)
    body_stripped = body.strip()
    assert len(body_stripped) >= 10, (
        f"{cmd_file.name} body is too short ({len(body_stripped)} chars)"
    )
