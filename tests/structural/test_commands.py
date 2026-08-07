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


def test_command_count(commands_dir, plugin_json):
    """Command count on filesystem matches plugin.json manifest."""
    files = sorted(commands_dir.glob("*.md"))
    expected = len(plugin_json.get("commands", []))
    assert len(files) == expected, (
        f"plugin.json lists {expected} commands, filesystem has {len(files)}: {[f.stem for f in files]}"
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


def test_next_goal_merges_remontoire_promotions_without_forcing(project_root):
    """Measured Remontoire promotions enter ranking but never bypass it."""
    content = (project_root / "commands" / "next-goal.md").read_text()

    assert "remontoire-attention.sh" in content
    assert "--format=json" in content
    assert "remontoire-promotion" in content
    assert "unique_by(.id)" in content
    assert "must not automatically win" in content
    assert "dependent_count" in content


def test_next_goal_reads_candidates_through_the_helper(project_root):
    """Cross-tracker lookup is code, not an instruction to go looking.

    The prose version of this ("if you know of other reachable bead roots...
    merge results before ranking") was what bead mk-fx3 closed on, and it never
    ran: bd resolves from $PWD and stops at the nearest git root, so from a
    Sylveste subproject the command saw no tracker at all.
    """
    content = (project_root / "commands" / "next-goal.md").read_text()
    helper = project_root / "scripts" / "next-goal-candidates.sh"

    assert helper.exists(), "the cross-tracker lookup helper is missing"
    assert helper.stat().st_mode & 0o111, "helper is not executable"
    assert "next-goal-candidates.sh" in content
    assert "TRACKER_REACHABLE" in content
    # The old formulation collapsed "could not look" into "nothing there".
    assert 'LOCAL_READY_JSON=$(bd ready --json --limit 20 2>/dev/null)' not in content


def test_next_goal_degraded_path_names_which_degradation(project_root):
    """An improvised block must be distinguishable from a tracker-ranked one.

    Both produce candidates in the same format; only the wording tells a reader
    whether the backlog was consulted. Without this the block is unauditable
    after the fact, which is how it came to need double-checking.
    """
    content = (project_root / "commands" / "next-goal.md").read_text()

    # The exact string the emitted block must carry when lookup failed.
    assert "no tracker reachable" in content
    # ...and the opposite case, which is a real fact rather than a failure.
    assert "trackers reachable, nothing ready" in content
    assert "LOOKUP_FAILURES" in content


def test_next_goal_ranks_roadmap_only_when_fresh(project_root):
    """A stale roadmap is withdrawn from ranking, not quietly ranked on."""
    content = (project_root / "commands" / "next-goal.md").read_text()

    assert 'roadmap.status == "fresh"' in content
    # Freshness comes from the embedded stamp. Sylveste's roadmap.json carried
    # an mtime eight days newer than its generated_at, so an mtime check called
    # a 25-day-old artifact fresh.
    assert "generated_at" in content
    assert "mtime" in content
    # Unknown freshness is its own state, never "fresh".
    assert "undated" in content
