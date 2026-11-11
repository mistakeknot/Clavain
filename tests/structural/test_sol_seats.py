"""mk ruling 2026-09-29 (mk-v4ao): every Sol seat is gpt-6.1-sol at the effort it
had under the 2026-09-26 ruling below; only the model moved.

mk ruling 2026-09-26: every Sol seat runs GPT-6 Sol at medium, except the
authority seats, which run at high (roster Rule 6 bars Sol-medium from
authority roles; mk-rpnv.17). Cross-lab review is headed by GPT-6 Sol at medium.

mk-42j9.27: planning is a judgment role, which Rule 6 also bars from Sol-medium,
so it gets its own Sol seat at high instead of borrowing routine-sol. The
deep-execution Sol seats stay at high (effort study mk-42j9.26 verdict item 2:
the hard-task tail was never ruled down to medium)."""

from pathlib import Path

import yaml

AUTHORITY_SEATS = {"main-sol", "release-authority-sol"}
JUDGMENT_SEATS = {"planning-sol"}
DEEP_SEATS = {"deep", "deep-clavain", "deep-sol", "deep-exec-sol"}
# mk-mhuo2.1: the default execution seats are Sol at high (routine included).
EXECUTION_SOL_SEATS = {"routine-exec-sol", "deep-exec-sol"}
HIGH_SEATS = AUTHORITY_SEATS | JUDGMENT_SEATS | DEEP_SEATS | EXECUTION_SOL_SEATS
# Roster Rule 6 classes (scripts/roster/generate.py ROLE_CLASS) barred from Sol-medium.
RULE6_BARRED_ROLES = {"main-integrator", "release-authority", "frontier-planning", "escalation", "planning"}


def _dispatch(project_root: Path) -> dict:
    return yaml.safe_load((project_root / "config/routing.yaml").read_text(encoding="utf-8"))["dispatch"]


def test_every_sol_seat_is_gpt61_sol_at_ruled_effort(project_root):
    tiers = _dispatch(project_root)["tiers"]
    sol = {name: t for name, t in tiers.items() if "sol" in str(t.get("model", ""))}
    assert sol, "no Sol seats found"
    assert HIGH_SEATS <= sol.keys()
    for name, tier in sol.items():
        assert tier["model"] == "gpt-6.1-sol", name
        expected = "high" if name in HIGH_SEATS else "medium"
        assert tier.get("reasoning_effort") == expected, name


def test_cross_lab_review_is_headed_by_gpt61_sol_medium(project_root):
    dispatch = _dispatch(project_root)
    head = dispatch["tiers"][dispatch["roles"]["cross-lab-review"]]
    assert (head["model"], head["reasoning_effort"]) == ("gpt-6.1-sol", "medium")
    assert "gpt-5.6-sol" not in dispatch.get("model_aliases", {}).values()


def test_no_rule6_role_is_headed_by_sol_medium(project_root):
    dispatch = _dispatch(project_root)
    for role in RULE6_BARRED_ROLES:
        head = dispatch["tiers"][dispatch["roles"][role]]
        assert (head["model"], head["reasoning_effort"]) != ("gpt-6.1-sol", "medium"), role


def test_planning_has_its_own_sol_seat(project_root):
    dispatch = _dispatch(project_root)
    # Opus 5.5 plans first; the Sol seat stays as the last fallback.
    assert dispatch["roles"]["planning"] == "planning-opus"
    assert "planning-sol" in dispatch["tiers"]["planning-opus"]["fallbacks"]
    seat = dispatch["tiers"]["planning-sol"]
    assert seat["role"] == "planning"
    assert seat.get("fallbacks") == dispatch["tiers"]["routine-sol"].get("fallbacks")


def test_execution_roles_default_to_sol_high_with_sonnet_high_fallback(project_root):
    """bead mk-mhuo2.1: routine-execution and deep-execution resolve to
    gpt-6.1-sol at high first, and the ordered fallbacks reach a Sonnet 5.5
    high seat."""
    dispatch = _dispatch(project_root)
    tiers = dispatch["tiers"]
    for role, head_name in (("routine-execution", "routine-exec-sol"), ("deep-execution", "deep-exec-sol")):
        assert dispatch["roles"][role] == head_name
        head = tiers[head_name]
        assert (head["backend"], head["model"], head["reasoning_effort"], head["service_tier"]) == (
            "codex", "gpt-6.1-sol", "high", "standard"), role
        assert head["role"] == role
        # Walk the fallback chain from the head; it must reach Sonnet 5.5 at high.
        seen, queue, chain = {head_name}, list(head.get("fallbacks", [])), []
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            chain.append(name)
            queue.extend(tiers[name].get("fallbacks", []))
        sonnet = [n for n in chain if tiers[n]["model"] == "claude-sonnet-5-5"]
        assert sonnet, role
        assert tiers[sonnet[0]]["reasoning_effort"] == "high", role
        assert tiers[sonnet[0]]["backend"] == "claude", role
        # Sonnet is the first fallback behind the Sol head.
        assert chain[0] == sonnet[0], role
