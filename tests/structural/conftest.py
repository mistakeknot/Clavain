"""Shared fixtures for Clavain structural tests."""

import json
import shutil
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# `ic`-dependent selection (Sylveste-psey)
#
# tests/structural/test_claude_usage.py drives scripts/claude_usage.py, whose
# meter calls `ic --json route identity` and fails closed when the binary is
# missing. A hosted runner has no `ic`, so from 75fed68 those 28 cases turned
# Tier 1 red and Tier 2 bats was never reached again -- 872 shell assertions
# stopped running for eleven days behind a failure that had nothing to do with
# them.
#
# Deselecting them where `ic` is absent MOVES that coverage; it must not lose
# it. Three rules make the difference:
#   1. The deselection is announced, with the count, the reason, and where the
#      coverage now runs. A silent skip is the downgrade this estate refuses.
#   2. --require-ic makes the same absence an ERROR, so the designated host
#      cannot report success while quietly carrying none of it.
#   3. Presence is the key, not health: a present-but-broken `ic` stays
#      selected and fails normally. Otherwise a broken binary buys silence.
# ---------------------------------------------------------------------------

_IC_MARKER = "requires_ic"
_IC_HELD_BACK = "_clavain_ic_held_back"


def pytest_addoption(parser):
    parser.addoption(
        "--require-ic",
        action="store_true",
        default=False,
        help="Fail collection when `ic` is absent instead of deselecting the "
             "tests that need it. Use on hosts that are supposed to carry this "
             "coverage, so its absence cannot pass as success.",
    )


def pytest_collection_modifyitems(config, items):
    ic_path = shutil.which("ic")
    if ic_path:
        return

    marked = [item for item in items if item.get_closest_marker(_IC_MARKER)]

    if config.getoption("--require-ic"):
        raise pytest.UsageError(
            f"--require-ic was given but no `ic` executable is on PATH; "
            f"{len(marked)} tests marked {_IC_MARKER} cannot run here. "
            f"This host is designated to carry that coverage, so its absence "
            f"is an error rather than a deselection."
        )

    if not marked:
        return

    remaining = [item for item in items if item not in marked]
    config.hook.pytest_deselected(items=marked)
    items[:] = remaining
    setattr(config, _IC_HELD_BACK, len(marked))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    held = getattr(config, _IC_HELD_BACK, 0)
    if not held:
        return
    terminalreporter.write_line(
        f"{held} tests deselected: {_IC_MARKER}; ic executable not found on "
        f"PATH; covered by zklw clavain-structural"
    )


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
