"""mk ruling 2026-09-26: every Sol seat runs GPT-6 Sol at medium, except the
authority seats, which run at high (roster Rule 6 bars Sol-medium from
authority roles; mk-rpnv.17). Cross-lab review is headed by GPT-6 Sol at medium."""

from pathlib import Path

import yaml

AUTHORITY_SEATS = {"main-sol", "release-authority-sol"}


def _dispatch(project_root: Path) -> dict:
    return yaml.safe_load((project_root / "config/routing.yaml").read_text(encoding="utf-8"))["dispatch"]


def test_every_sol_seat_is_gpt6_sol_at_ruled_effort(project_root):
    tiers = _dispatch(project_root)["tiers"]
    sol = {name: t for name, t in tiers.items() if "sol" in str(t.get("model", ""))}
    assert sol, "no Sol seats found"
    assert AUTHORITY_SEATS <= sol.keys()
    for name, tier in sol.items():
        assert tier["model"] == "gpt-6-sol", name
        expected = "high" if name in AUTHORITY_SEATS else "medium"
        assert tier.get("reasoning_effort") == expected, name


def test_cross_lab_review_is_headed_by_gpt6_sol_medium(project_root):
    dispatch = _dispatch(project_root)
    head = dispatch["tiers"][dispatch["roles"]["cross-lab-review"]]
    assert (head["model"], head["reasoning_effort"]) == ("gpt-6-sol", "medium")
    assert "gpt-5.6-sol" not in dispatch.get("model_aliases", {}).values()
