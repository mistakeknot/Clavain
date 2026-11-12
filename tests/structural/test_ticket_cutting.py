"""Planning entry points preserve the ticket-cutting contract (mk-7k5v0.2)."""

import pytest


@pytest.mark.parametrize("relative_path", [
    "commands/strategy.md",
    "skills/writing-plans/SKILL.md",
])
def test_ticket_cutting_guidance(project_root, relative_path):
    text = " ".join((project_root / relative_path).read_text().split()).lower()
    for guidance in (
        "thin end-to-end slice",
        "demonstrated on its own",
        "one fresh session",
        "blockers",
        "preparatory refactors first",
    ):
        assert guidance in text, f"{relative_path} lacks {guidance}"
