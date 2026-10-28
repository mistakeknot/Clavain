"""Structural invariants for the full-stop skill and the describe-pr review footer."""

import json
from pathlib import Path


def _read(project_root: Path, relative: str) -> str:
    return (project_root / relative).read_text(encoding="utf-8")


def test_full_stop_skill_is_registered(project_root):
    plugin = json.loads(_read(project_root, ".claude-plugin/plugin.json"))
    assert "./skills/full-stop" in plugin["skills"]
    assert (project_root / "skills/full-stop/SKILL.md").is_file()
    assert (project_root / "skills/full-stop/SKILL-compact.md").is_file()


def test_full_stop_states_hard_limits_and_loop(project_root):
    for relative in ("skills/full-stop/SKILL.md", "skills/full-stop/SKILL-compact.md"):
        text = _read(project_root, relative).lower()
        for needle in (
            "never merge",
            "auto-merge",
            "force-push",
            "not draft",
            "sonnerie register",
            "cross-lab-review",
            "block",
            "decision card",
            "-s read-only",
            "producer-identity",
            "code-review-discipline",
        ):
            assert needle in text, (relative, needle)


def test_describe_pr_has_review_footer(project_root):
    text = _read(project_root, "commands/describe-pr.md")
    assert "## Review" in text
    for field in ("Rounds:", "Reviewer model:", "Verdicts by round:", "Final verdict:"):
        assert field in text, field
    assert "BLOCK" in text and "none run" in text
