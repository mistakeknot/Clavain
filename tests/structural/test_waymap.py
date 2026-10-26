"""Waymap tests: the roadmap kind of the wayfind engine, against a real bd.

The plain wayfinder:map behaviour is covered by test_wayfind.py; the last tests here pin that it did not move.
"""
import contextlib
import json
import os
import shutil
import subprocess
import time

import pytest

import wayfind

BD = shutil.which("bd")
needs_bd = pytest.mark.skipif(BD is None, reason="bd not installed")


@pytest.fixture(scope="module")
def beads(tmp_path_factory):
    root = tmp_path_factory.mktemp("waymap-beads")
    with pytest.MonkeyPatch.context() as mp:
        for name in [k for k in os.environ if k.startswith("BEADS_")]:
            mp.delenv(name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run([str(BD), "init", "-q", "-p", "wm"], cwd=root, check=True, capture_output=True)
        yield root


@pytest.fixture(autouse=True)
def private_runtime_dir(tmp_path_factory, monkeypatch):
    """Keep each test's lock files out of the real home directory."""
    monkeypatch.setenv("WAYFIND_LOCK_DIR", str(tmp_path_factory.mktemp("run") / "locks"))


@pytest.fixture(autouse=True)
def one_roadmap_at_a_time(request):
    """A project holds one open roadmap, so close the previous test's before the next charts its own.

    The tests that need no bd (the label and lock-directory checks) must not build the bd workspace, so
    it is requested only when bd is installed."""
    if BD is None:
        return
    beads = request.getfixturevalue("beads")
    bd = wayfind.Bd(directory=str(beads))
    for issue in bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0"):
        bd.run("close", issue["id"], "-r", "test teardown", "--force")


def run(beads, *argv):
    return wayfind.main(["-C", str(beads), *argv])


def chart_roadmap(beads, tmp_path, tickets, fog=("a later bet",), project="wm"):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"tickets": tickets, "fog": list(fog)}))
    bd = wayfind.Bd(directory=str(beads))
    assert run(beads, "chart", "--kind", "roadmap", "--project", project, "--title", f"{project} roadmap",
               "--destination", "A product people can adopt by Q-end.", "--out-of-scope", "- billing",
               "--source", "card pick", "--tickets", str(spec)) == 0
    map_id = next(i["id"] for i in bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0")
                  if wayfind.PROJECT_LABEL_PREFIX + project in i["labels"])
    return bd, map_id


def bet_id(bd, map_id, title):
    return next(t["id"] for t in wayfind.map_tickets(bd, map_id) if t["title"] == title)


def commit(beads, bd, map_id, title, horizon="next", *extra):
    return run(beads, "resolve", bet_id(bd, map_id, title), "--answer", f"Build {title}.",
               "--source", "card pick", "--decision", "commit", "--horizon", horizon, *extra)


def make_child(beads, bet, title):
    out = subprocess.run([BD, "create", title, "--parent", bet, "-t", "task", "--json"], cwd=beads,
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    return (data[0] if isinstance(data, list) else data)["id"]


def close_issue(beads, issue):
    subprocess.run([BD, "close", issue, "-r", "done"], cwd=beads, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_map_kind_reads_either_label():
    assert wayfind.map_kind({"labels": ["wayfinder:map"]}) == "map"
    assert wayfind.map_kind({"labels": ["wayfinder:roadmap"]}) == "roadmap"
    assert wayfind.map_kind({"labels": ["other"]}) is None


def test_bet_is_a_roadmap_only_hitl_type():
    assert "bet" in wayfind.KIND_TYPES["roadmap"] and "bet" not in wayfind.KIND_TYPES["map"]
    assert "bet" in wayfind.HITL_TYPES
    assert wayfind.DEFAULT_BET_CAP == wayfind.DEFAULT_CAP == 7


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------


@needs_bd
def test_chart_roadmap_labels_the_epic_and_types_the_bets(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B1"}, {"type": "research", "title": "R1"}])
    issue = bd.show(map_id)
    assert sorted(issue["labels"]) == sorted([wayfind.ROADMAP_LABEL, "waymap:project:wm"])
    assert wayfind.ticket_type(bd.show(bet_id(bd, map_id, "B1"))) == "bet"
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["kind"] == "roadmap" and report["errors"] == [] and report["cleared"] is False


@needs_bd
def test_roadmap_charts_are_not_listed_as_plain_maps(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B1"}])
    assert map_id not in {i["id"] for i in bd.json("list", "--label", wayfind.MAP_LABEL, "--limit", "0")}


@needs_bd
def test_a_plain_map_refuses_bets_and_a_roadmap_accepts_them(beads, tmp_path):
    spec = tmp_path / "bet.json"
    spec.write_text(json.dumps({"tickets": [{"type": "bet", "title": "B"}]}))
    bd = wayfind.Bd(directory=str(beads))
    before = {i["id"] for i in bd.json("list", "--all", "--limit", "0")}
    assert run(beads, "chart", "--title", "t", "--destination", "D", "--source", "s",
               "--tickets", str(spec)) == wayfind.EXIT_RULE
    assert {i["id"] for i in bd.json("list", "--all", "--limit", "0")} == before


@needs_bd
def test_one_open_roadmap_per_project(beads, tmp_path):
    chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B1"}])
    bd = wayfind.Bd(directory=str(beads))
    before = {i["id"] for i in bd.json("list", "--all", "--limit", "0")}
    assert run(beads, "chart", "--kind", "roadmap", "--project", "wm", "--title", "Another", "--destination", "D",
               "--source", "s") == wayfind.EXIT_RULE
    assert {i["id"] for i in bd.json("list", "--all", "--limit", "0")} == before


def all_ids(bd):
    return {i["id"] for i in bd.json("list", "--all", "--limit", "0")}


def chart_unscoped_legacy_roadmap(beads, tmp_path):
    """A roadmap as charted before project scoping: the roadmap label and no project label."""
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "L1"}, {"type": "bet", "title": "L2"}],
                               project="legacy")
    for issue in [map_id] + [t["id"] for t in wayfind.map_tickets(bd, map_id)]:
        bd.remove_label(issue, "waymap:project:legacy")
    assert wayfind.project_names(bd.show(map_id)) == []
    return bd, map_id


def test_project_names_are_normalised_and_label_safe():
    assert wayfind.normalize_project(" Aleph ") == "aleph"
    assert wayfind.project_names({"labels": ["wayfinder:roadmap", "waymap:project:aleph", "x"]}) == ["aleph"]
    for bad in (None, "", "a b", "a:b", "-x", "x" * 65):
        with pytest.raises(wayfind.WayfindError):
            wayfind.normalize_project(bad)


@needs_bd
def test_two_projects_can_each_chart_a_roadmap_in_one_database(beads, tmp_path):
    bd_a, aleph = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "A1"}], project="aleph")
    bd_u, undersketch = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "U1"}], project="undersketch")
    assert aleph != undersketch
    assert wayfind.project_names(bd_a.show(aleph)) == ["aleph"]
    assert wayfind.project_names(bd_u.show(undersketch)) == ["undersketch"]
    for map_id in (aleph, undersketch):
        report = wayfind.evaluate(bd_a, map_id, 7, 14)
        assert report["errors"] == [] and report["warnings"] == [
            "Now has no live child: no committed Now bet; commit one, or the roadmap is stale"]
    # Each roadmap's work stays on its own tickets.
    assert [t["title"] for t in wayfind.map_tickets(bd_a, aleph)] == ["A1"]
    assert [t["title"] for t in wayfind.map_tickets(bd_a, undersketch)] == ["U1"]


@needs_bd
def test_the_same_project_twice_is_refused_and_changes_nothing(beads, tmp_path, capsys):
    bd, first = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "A1"}], project="aleph")
    chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "U1"}], project="undersketch")
    before = all_ids(bd)
    capsys.readouterr()
    assert run(beads, "chart", "--kind", "roadmap", "--project", "ALEPH", "--title", "Again", "--destination", "D",
               "--source", "s") == wayfind.EXIT_RULE
    err = capsys.readouterr().err
    assert "project aleph already has an open roadmap" in err and first in err
    assert all_ids(bd) == before


@needs_bd
def test_a_closed_roadmap_frees_its_project(beads, tmp_path):
    bd, first = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "A1"}], project="aleph")
    bd.run("close", first, "-r", "ended", "--force")
    _, second = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "A2"}], project="aleph")
    assert second != first


@needs_bd
def test_a_new_roadmap_needs_a_project_and_a_plain_map_refuses_one(beads, tmp_path, capsys):
    bd = wayfind.Bd(directory=str(beads))
    before = all_ids(bd)
    capsys.readouterr()
    assert run(beads, "chart", "--kind", "roadmap", "--title", "t", "--destination", "D",
               "--source", "s") == wayfind.EXIT_USAGE
    assert "needs --project" in capsys.readouterr().err
    assert run(beads, "chart", "--title", "t", "--destination", "D", "--source", "s",
               "--project", "aleph") == wayfind.EXIT_USAGE
    assert run(beads, "chart", "--kind", "roadmap", "--project", "a b", "--title", "t", "--destination", "D",
               "--source", "s") == wayfind.EXIT_USAGE
    assert all_ids(bd) == before


@needs_bd
def test_dry_run_reports_the_project_and_writes_nothing(beads, capsys):
    bd = wayfind.Bd(directory=str(beads))
    before = all_ids(bd)
    capsys.readouterr()
    assert run(beads, "chart", "--kind", "roadmap", "--project", "Aleph", "--title", "t", "--destination", "D",
               "--source", "s", "--dry-run") == 0
    assert json.loads(capsys.readouterr().out)["project"] == "aleph"
    assert all_ids(bd) == before


@needs_bd
def test_an_unlabeled_legacy_roadmap_blocks_no_project_and_lint_warns(beads, tmp_path, capsys):
    bd, legacy = chart_unscoped_legacy_roadmap(beads, tmp_path)
    capsys.readouterr()
    report = wayfind.evaluate(bd, legacy, 7, 14)
    assert report["errors"] == [] and any("no project label" in w and "adopt-roadmap" in w for w in report["warnings"])
    # A project can still chart its own roadmap, with a warning that names the legacy one.
    _, other = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "U1"}], project="undersketch")
    assert other != legacy
    assert legacy in capsys.readouterr().err
    assert wayfind.project_names(bd.show(legacy)) == []
    assert wayfind.evaluate(bd, other, 7, 14)["errors"] == []


@needs_bd
def test_adopt_roadmap_labels_the_map_and_its_tickets_and_then_the_project_is_taken(beads, tmp_path, capsys):
    bd, legacy = chart_unscoped_legacy_roadmap(beads, tmp_path)
    ticket_ids = [t["id"] for t in wayfind.map_tickets(bd, legacy)]
    assert len(ticket_ids) == 2
    capsys.readouterr()
    assert run(beads, "adopt-roadmap", legacy, "--project", "Aleph", "--dry-run") == 0
    assert "would label 3 of 3" in capsys.readouterr().out
    assert wayfind.project_names(bd.show(legacy)) == []
    assert run(beads, "adopt-roadmap", legacy, "--project", "Aleph") == 0
    assert "labelled 3 of 3" in capsys.readouterr().out
    for issue_id in [legacy] + ticket_ids:
        assert wayfind.project_names(bd.show(issue_id)) == ["aleph"]
    assert wayfind.ROADMAP_LABEL in bd.show(legacy)["labels"]
    assert wayfind.evaluate(bd, legacy, 7, 14)["errors"] == []
    assert not any("no project label" in w for w in wayfind.evaluate(bd, legacy, 7, 14)["warnings"])
    # Idempotent, and the project is now taken while another project is free.
    assert run(beads, "adopt-roadmap", legacy, "--project", "aleph") == 0
    assert "labelled 0 of 3" in capsys.readouterr().out
    assert run(beads, "chart", "--kind", "roadmap", "--project", "aleph", "--title", "Again", "--destination", "D",
               "--source", "s") == wayfind.EXIT_RULE
    _, other = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "U1"}], project="undersketch")
    assert other != legacy


@needs_bd
def test_adopt_roadmap_refuses_a_second_project_a_plain_map_and_a_taken_project(beads, tmp_path, capsys):
    bd, legacy = chart_unscoped_legacy_roadmap(beads, tmp_path)
    _, taken = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "T1"}], project="yaoirioware")
    capsys.readouterr()
    assert run(beads, "adopt-roadmap", legacy, "--project", "yaoirioware") == wayfind.EXIT_RULE
    assert "already has an open roadmap" in capsys.readouterr().err
    assert wayfind.project_names(bd.show(legacy)) == []
    assert run(beads, "adopt-roadmap", taken, "--project", "aleph") == wayfind.EXIT_RULE
    assert "already belongs to project yaoirioware" in capsys.readouterr().err
    assert wayfind.project_names(bd.show(taken)) == ["yaoirioware"]
    plain = bd.create("[map] plain", "## Destination\nD\n", [wayfind.MAP_LABEL], issue_type="epic")
    assert run(beads, "adopt-roadmap", plain, "--project", "aleph") == wayfind.EXIT_RULE
    assert wayfind.project_names(bd.show(plain)) == []
    assert run(beads, "adopt-roadmap", legacy, "--project", "bad name") == wayfind.EXIT_USAGE
    bd.run("close", plain, "-r", "test teardown", "--force")


@needs_bd
def test_lint_errors_when_a_project_has_two_open_roadmaps_or_a_roadmap_two_projects(beads, tmp_path):
    bd, first = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "A1"}], project="aleph")
    _, second = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "U1"}], project="undersketch")
    bd.add_label(second, "waymap:project:aleph")  # a hand edit that bypasses chart
    report = wayfind.evaluate(bd, second, 7, 14)
    assert any("carries 2 project labels" in e for e in report["errors"])
    bd.remove_label(second, "waymap:project:undersketch")
    report = wayfind.evaluate(bd, first, 7, 14)
    assert any("more than one open roadmap" in e for e in report["errors"])


@needs_bd
def test_an_abbreviated_roadmap_id_is_not_its_own_twin(beads, tmp_path, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "A1"}], project="probe")
    short = map_id.split("-", 1)[1]
    assert bd.show(short)["id"] == map_id
    for spelling in (map_id, short):
        assert wayfind.evaluate(bd, spelling, 7, 14)["errors"] == []
        assert run(beads, "lint", spelling) == 0
    capsys.readouterr()
    assert run(beads, "adopt-roadmap", short, "--project", "probe") == 0  # not refused as a rival of itself
    assert f"roadmap {map_id}:" in capsys.readouterr().out  # reported under its canonical id
    assert wayfind.project_names(bd.show(map_id)) == ["probe"]
    assert run(beads, "chart", "--kind", "roadmap", "--project", "probe", "--title", "x", "--destination", "D",
               "--source", "s") == wayfind.EXIT_RULE  # chart finds the project by label, not by ID
    _, twin = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "U1"}], project="other")
    bd.add_label(twin, "waymap:project:probe")  # a hand edit: a real twin is still reported under either spelling
    for spelling in (map_id, short):
        assert any("more than one open roadmap" in e for e in wayfind.evaluate(bd, spelling, 7, 14)["errors"])


@needs_bd
def test_roadmap_destination_is_one_line(beads):
    assert run(beads, "chart", "--kind", "roadmap", "--project", "wm", "--title", "t",
               "--destination", "line one\nline two",
               "--source", "s") == wayfind.EXIT_RULE


# ---------------------------------------------------------------------------
# Bet resolution
# ---------------------------------------------------------------------------


@needs_bd
def test_bet_resolution_needs_a_source_and_a_decision(beads, tmp_path, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B1"}])
    b = bet_id(bd, map_id, "B1")
    assert run(beads, "resolve", b, "--answer", "yes", "--decision", "commit",
               "--horizon", "now") == wayfind.EXIT_RULE                                   # no --source
    assert "source" in capsys.readouterr().err
    assert run(beads, "resolve", b, "--answer", "yes", "--source", "card pick") == wayfind.EXIT_RULE   # no decision
    assert run(beads, "resolve", b, "--answer", "yes", "--source", "card pick",
               "--decision", "commit") == wayfind.EXIT_RULE                              # no horizon
    assert run(beads, "resolve", b, "--answer", "yes", "--source", "card pick",
               "--decision", "defer", "--horizon", "now") == wayfind.EXIT_RULE           # horizon only with commit
    assert bd.show(b)["status"] != "closed"


@needs_bd
def test_commit_labels_the_bet_and_defer_and_drop_do_not(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": t} for t in ("C", "D", "X")])
    assert commit(beads, bd, map_id, "C", "now") == 0
    for title, decision in (("D", "defer"), ("X", "drop")):
        assert run(beads, "resolve", bet_id(bd, map_id, title), "--answer", "n/a", "--source", "card pick",
                   "--decision", decision) == 0
    assert "waymap:now" in bd.show(bet_id(bd, map_id, "C"))["labels"]
    for title in ("D", "X"):
        assert not [l for l in bd.show(bet_id(bd, map_id, title))["labels"] if l.startswith("waymap:")]
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == []
    assert {d["decision"] for d in report["decisions"]} == {"commit", "defer", "drop"}


@needs_bd
def test_decision_flags_are_refused_on_other_ticket_types(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "research", "title": "R"}])
    assert run(beads, "resolve", bet_id(bd, map_id, "R"), "--answer", "found", "--decision", "commit",
               "--horizon", "now") == wayfind.EXIT_RULE


# ---------------------------------------------------------------------------
# The cap
# ---------------------------------------------------------------------------


@needs_bd
def test_eighth_committed_bet_is_refused_and_lint_catches_a_forced_one(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(7)])
    for i in range(7):
        assert commit(beads, bd, map_id, f"B{i}", "now" if i == 0 else "next") == 0
    assert wayfind.evaluate(bd, map_id, 7, 14)["errors"] == []
    # An eighth bet is chartable (the chart cap counts open tickets) but cannot be committed.
    spec = tmp_path / "eighth.json"
    spec.write_text(json.dumps({"tickets": [{"type": "bet", "title": "B7"}]}))
    assert run(beads, "chart", "--map", map_id, "--tickets", str(spec)) == 0
    assert commit(beads, bd, map_id, "B7") == wayfind.EXIT_RULE
    assert "waymap:next" not in bd.show(bet_id(bd, map_id, "B7"))["labels"]
    # Lint refuses a roadmap that is over the cap, whatever got it there (here: a lower cap).
    assert run(beads, "lint", map_id, "--bet-cap", "6") == wayfind.EXIT_RULE
    assert run(beads, "lint", map_id) == 0


@needs_bd
def test_a_delivered_bet_frees_a_slot(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(3)])
    cap = ["--bet-cap", "2"]
    assert commit(beads, bd, map_id, "B0", "now", *cap) == 0
    assert commit(beads, bd, map_id, "B1", "next", *cap) == 0
    assert commit(beads, bd, map_id, "B2", "next", *cap) == wayfind.EXIT_RULE
    child = make_child(beads, bet_id(bd, map_id, "B1"), "ship it")
    close_issue(beads, child)
    assert wayfind.bet_work(bd, bd.show(bet_id(bd, map_id, "B1")))["delivered"]
    assert commit(beads, bd, map_id, "B2", "next", *cap) == 0


@needs_bd
def test_superseded_bet_frees_a_slot_and_a_rerun_is_idempotent(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}, {"type": "revisit", "title": "Rev"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    assert run(beads, "resolve", bet_id(bd, map_id, "Rev"), "--answer", "Drop B0.", "--source", "ruling",
               "--supersedes", bet_id(bd, map_id, "B0")) == 0
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == [] and report["roadmap"]["active"] == 0


@needs_bd
def test_the_cap_covers_a_half_resolved_bet_and_its_retry(beads, tmp_path, monkeypatch):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(3)])
    cap = ["--bet-cap", "2"]
    assert commit(beads, bd, map_id, "B0", "now", *cap) == 0
    # B1's record is written, then closing fails: the bet is half resolved.
    real_close = wayfind.Bd.close

    def failing_close(self, ticket, reason):
        raise wayfind.WayfindError("bd close failed: simulated")

    monkeypatch.setattr(wayfind.Bd, "close", failing_close)
    assert commit(beads, bd, map_id, "B1", "next", *cap) == wayfind.EXIT_USAGE
    monkeypatch.setattr(wayfind.Bd, "close", real_close)
    assert bd.show(bet_id(bd, map_id, "B1"))["status"] != "closed"
    # B1 still holds its slot, so B2 cannot take the last one ...
    assert commit(beads, bd, map_id, "B2", "next", *cap) == wayfind.EXIT_RULE
    assert "waymap:next" not in bd.show(bet_id(bd, map_id, "B2"))["labels"]
    # ... and the retry of B1 finishes it, leaving exactly two active bets.
    assert commit(beads, bd, map_id, "B1", "next", *cap) == 0
    assert wayfind.evaluate(bd, map_id, 7, 14, bet_cap=2)["roadmap"]["active"] == 2


@needs_bd
def test_a_retry_is_refused_when_its_slot_was_taken_meanwhile(beads, tmp_path, monkeypatch):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(2)])
    assert commit(beads, bd, map_id, "B0", "now", "--bet-cap", "2") == 0

    def failing_close(self, ticket, reason):
        raise wayfind.WayfindError("bd close failed: simulated")

    with monkeypatch.context() as mp:
        mp.setattr(wayfind.Bd, "close", failing_close)
        assert commit(beads, bd, map_id, "B1", "next", "--bet-cap", "2") == wayfind.EXIT_USAGE
    # The cap is lowered before the retry: the retry is checked, not waved through.
    assert commit(beads, bd, map_id, "B1", "next", "--bet-cap", "1") == wayfind.EXIT_RULE
    assert "waymap:next" not in bd.show(bet_id(bd, map_id, "B1"))["labels"]


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


@needs_bd
def test_lint_warns_when_now_has_no_live_child_and_clears_it_with_one(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    b = bet_id(bd, map_id, "B0")
    warned = wayfind.evaluate(bd, map_id, 7, 14)["warnings"]
    assert any("Now has no live child" in w for w in warned)
    make_child(beads, b, "Do the thing")
    assert not [w for w in wayfind.evaluate(bd, map_id, 7, 14)["warnings"] if "Now has no live child" in w]
    assert run(beads, "lint", map_id) == 0


@needs_bd
def test_lint_catches_a_horizon_label_without_its_record(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}, {"type": "bet", "title": "B1"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    subprocess.run([BD, "update", bet_id(bd, map_id, "B1"), "--add-label", "waymap:next"], cwd=beads, check=True,
                   capture_output=True)
    assert run(beads, "lint", map_id) == wayfind.EXIT_RULE
    subprocess.run([BD, "update", bet_id(bd, map_id, "B1"), "--remove-label", "waymap:next"], cwd=beads, check=True,
                   capture_output=True)
    subprocess.run([BD, "update", bet_id(bd, map_id, "B0"), "--remove-label", "waymap:now"], cwd=beads, check=True,
                   capture_output=True)
    assert run(beads, "lint", map_id) == wayfind.EXIT_RULE


@needs_bd
def test_roadmap_keeps_the_existing_lint_rules(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    body = bd.show(map_id)["description"]
    bd.set_description(map_id, body.replace("A product people can adopt by Q-end.", "Everything, now."))
    assert run(beads, "lint", map_id) == wayfind.EXIT_RULE          # destination changed without a source
    assert run(beads, "resolve", bet_id(bd, map_id, "B0"), "--answer", "x", "--source", "s",
               "--decision", "drop") == wayfind.EXIT_RULE           # and it blocks resolve
    assert run(beads, "chart", "--map", map_id, "--destination", "Everything, now.", "--source", "ruling") == 0
    assert run(beads, "lint", map_id) == 0


@needs_bd
def test_a_roadmap_never_clears(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}], fog=())
    assert run(beads, "resolve", bet_id(bd, map_id, "B0"), "--answer", "x", "--source", "s",
               "--decision", "drop") == 0
    assert wayfind.evaluate(bd, map_id, 7, 14)["cleared"] is False


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


@needs_bd
def test_render_lists_committed_bets_with_progress_and_keeps_later_as_fog(beads, tmp_path, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}, {"type": "bet", "title": "B1"},
                                                 {"type": "bet", "title": "Skipped"}], fog=("a later bet",))
    assert commit(beads, bd, map_id, "B0", "now") == 0
    assert commit(beads, bd, map_id, "B1", "next") == 0
    a = make_child(beads, bet_id(bd, map_id, "B0"), "Part A")
    make_child(beads, bet_id(bd, map_id, "B0"), "Part B")
    close_issue(beads, a)
    capsys.readouterr()
    assert run(beads, "render", map_id, "--stdout") == 0
    text = capsys.readouterr().out
    assert text.startswith(wayfind.RENDER_MARKER)
    assert "Destination: A product people can adopt by Q-end." in text
    now = text.split("## Now")[1].split("## Next")[0]
    assert "B0" in now and "1/2 done" in now and "[x]" in now and "[ ]" in now
    assert "B1" in text.split("## Next")[1] and "no work started" in text
    assert "Skipped" not in text
    assert "## Not yet specified\n\n- a later bet" in text


@needs_bd
def test_render_writes_checks_and_detects_drift(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    out = tmp_path / "docs" / "roadmap.md"
    assert run(beads, "render", map_id, "--out", str(out), "--check") == wayfind.EXIT_RULE    # missing
    assert run(beads, "render", map_id, "--out", str(out)) == 0
    first = out.read_text()
    assert run(beads, "render", map_id, "--out", str(out), "--check") == 0
    assert run(beads, "render", map_id, "--out", str(out)) == 0 and out.read_text() == first   # deterministic
    make_child(beads, bet_id(bd, map_id, "B0"), "New work")
    assert run(beads, "render", map_id, "--out", str(out), "--check") == wayfind.EXIT_RULE    # stale
    out.write_text("# hand written\n")
    assert run(beads, "render", map_id, "--out", str(out)) == wayfind.EXIT_RULE               # not ours: refused


@needs_bd
def test_render_refuses_a_plain_map(beads, tmp_path):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"tickets": [{"type": "task", "title": "T"}]}))
    bd = wayfind.Bd(directory=str(beads))
    before = {i["id"] for i in bd.json("list", "--all", "--limit", "0")}
    assert run(beads, "chart", "--title", "t", "--destination", "D", "--source", "s", "--tickets", str(spec)) == 0
    map_id = next(i["id"] for i in bd.json("list", "--all", "--limit", "0")
                  if i["id"] not in before and wayfind.MAP_LABEL in (i.get("labels") or []))
    assert run(beads, "render", map_id, "--stdout") == wayfind.EXIT_RULE


@needs_bd
def test_render_refuses_a_roadmap_that_lint_rejects(beads, tmp_path, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}, {"type": "bet", "title": "B1"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    assert commit(beads, bd, map_id, "B1", "next") == 0
    out = tmp_path / "roadmap.md"
    assert run(beads, "render", map_id, "--out", str(out)) == 0
    published = out.read_text()
    # Forced over the cap: lint rejects it, so render must not publish it (file, check or stdout).
    assert run(beads, "render", map_id, "--out", str(out), "--bet-cap", "1") == wayfind.EXIT_RULE
    assert run(beads, "render", map_id, "--stdout", "--bet-cap", "1") == wayfind.EXIT_RULE
    # An unsourced Destination change is rejected the same way.
    bd.set_description(map_id, bd.show(map_id)["description"].replace("A product people can adopt by Q-end.",
                                                                       "Everything, now."))
    capsys.readouterr()
    assert run(beads, "render", map_id, "--out", str(out)) == wayfind.EXIT_RULE
    assert run(beads, "render", map_id, "--stdout") == wayfind.EXIT_RULE
    assert "Everything, now." not in capsys.readouterr().out
    assert out.read_text() == published


@needs_bd
def test_render_will_not_write_through_a_dangling_symlink(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    outside = tmp_path / "outside" / "escaped.md"
    outside.parent.mkdir()
    docs = beads / "docs"
    docs.mkdir(exist_ok=True)
    link = docs / "roadmap.md"
    link.unlink(missing_ok=True)
    link.symlink_to(outside)
    try:
        assert run(beads, "render", map_id) == wayfind.EXIT_RULE
        assert not outside.exists() and link.is_symlink()
    finally:
        link.unlink(missing_ok=True)
        shutil.rmtree(docs, ignore_errors=True)


@needs_bd
def test_render_will_not_write_through_a_symlinked_directory_out_of_the_project(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    docs = beads / "docs"
    shutil.rmtree(docs, ignore_errors=True)
    docs.symlink_to(outside, target_is_directory=True)
    try:
        assert run(beads, "render", map_id) == wayfind.EXIT_RULE
        assert list(outside.iterdir()) == []
    finally:
        docs.unlink(missing_ok=True)


@needs_bd
def test_render_writes_atomically_and_leaves_no_temp_file(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    out = tmp_path / "docs" / "roadmap.md"
    assert run(beads, "render", map_id, "--out", str(out)) == 0
    assert [p.name for p in out.parent.iterdir()] == ["roadmap.md"]


@needs_bd
def test_render_with_a_relative_project_directory_writes_under_it_once(beads, tmp_path, monkeypatch):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert commit(beads, bd, map_id, "B0", "now") == 0
    monkeypatch.chdir(beads.parent)
    docs = beads / "docs"
    shutil.rmtree(docs, ignore_errors=True)
    try:
        assert wayfind.main(["-C", beads.name, "render", map_id]) == 0
        assert (docs / "roadmap.md").is_file() and not (beads / beads.name).exists()
        # An explicit relative --out is relative to the current directory, so the shell's own path works.
        assert wayfind.main(["-C", beads.name, "render", map_id, "--out", f"{beads.name}/docs/other.md"]) == 0
        assert (docs / "other.md").is_file() and not (beads / beads.name).exists()
    finally:
        shutil.rmtree(docs, ignore_errors=True)


# ---------------------------------------------------------------------------
# Plain maps do not move
# ---------------------------------------------------------------------------


@needs_bd
def test_plain_map_keeps_its_label_types_and_bet_flags_are_refused(beads, tmp_path):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"tickets": [{"type": "grilling", "title": "G"}, {"type": "research", "title": "R"}]}))
    bd = wayfind.Bd(directory=str(beads))
    before = {i["id"] for i in bd.json("list", "--all", "--limit", "0")}
    assert run(beads, "chart", "--title", "plain", "--destination", "D", "--source", "s", "--tickets", str(spec)) == 0
    map_id = next(i["id"] for i in bd.json("list", "--all", "--limit", "0")
                  if i["id"] not in before and wayfind.MAP_LABEL in (i.get("labels") or []))
    assert bd.show(map_id)["labels"] == [wayfind.MAP_LABEL]
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert "roadmap" not in report and report.get("kind") is None and report["errors"] == []
    r = bet_id(bd, map_id, "R")
    assert run(beads, "resolve", r, "--answer", "x", "--decision", "commit", "--horizon", "now") == wayfind.EXIT_RULE
    assert run(beads, "resolve", r, "--answer", "found it") == 0
    assert bd.show(map_id)["labels"] == [wayfind.MAP_LABEL]
    assert not [l for l in bd.show(r)["labels"] if l.startswith("waymap:")]


# ---------------------------------------------------------------------------
# Concurrent writers
# ---------------------------------------------------------------------------

_RACER = """
import os, sys, time
sys.path.insert(0, os.path.dirname(sys.argv[1]))
import wayfind
# A slow bd, simulated: each rule check returns its answer, then the process stalls before it writes.
# Without serialization both racers read the same state; with it the second reads after the first wrote.
for name in ("active_commitments", "pending_commitments", "map_tickets"):
    real = getattr(wayfind, name)
    def slow(*a, _real=real, **k):
        out = _real(*a, **k)
        time.sleep(2)
        return out
    setattr(wayfind, name, slow)
while not os.path.exists(sys.argv[2]):
    time.sleep(0.001)
sys.exit(wayfind.main(sys.argv[3:]))
"""


def race(beads, tmp_path, *commands, envs=None):
    """Start every wayfind command at once, behind a barrier file, and return their exit codes.

    envs, if given, is one dict of environment changes per command (a value of None unsets it)."""
    script = tmp_path / "racer.py"
    script.write_text(_RACER)
    barrier = tmp_path / "go"
    def environment(changes):
        env = dict(os.environ)
        for name, value in (changes or {}).items():
            env.pop(name, None) if value is None else env.__setitem__(name, value)
        return env

    procs = [subprocess.Popen(["python3", str(script), wayfind.__file__, str(barrier), "-C", str(beads), *argv],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              env=environment((envs or [None] * len(commands))[n]))
             for n, argv in enumerate(commands)]
    barrier.write_text("go")
    results = [(p.wait(timeout=300), p.stderr.read()) for p in procs]
    for p in procs:
        p.stdout.close()
        p.stderr.close()
    return results


@needs_bd
def test_two_concurrent_resolves_cannot_commit_an_eighth_bet(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(7)])
    for i in range(6):
        assert commit(beads, bd, map_id, f"B{i}", "now" if i == 0 else "next") == 0
    assert len(wayfind.active_commitments(bd, map_id)) == 6
    more = tmp_path / "more.json"
    more.write_text(json.dumps({"tickets": [{"type": "bet", "title": "B7"}]}))
    assert run(beads, "chart", "--map", map_id, "--tickets", str(more)) == 0
    argv = [["resolve", bet_id(bd, map_id, title), "--answer", f"Build {title}.", "--source", "card pick",
             "--decision", "commit", "--horizon", "next"] for title in ("B6", "B7")]
    codes = sorted(code for code, _ in race(beads, tmp_path, *argv))
    assert codes == [wayfind.EXIT_OK, wayfind.EXIT_RULE]
    assert len(wayfind.active_commitments(bd, map_id)) == 7
    assert wayfind.evaluate(bd, map_id, 7, 14)["errors"] == []


@needs_bd
def test_two_concurrent_charts_cannot_pass_the_open_ticket_cap(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(5)])
    argv = []
    for n in range(2):
        spec = tmp_path / f"more{n}.json"
        spec.write_text(json.dumps({"tickets": [{"type": "task", "title": f"T{n}a"}, {"type": "task", "title": f"T{n}b"}]}))
        argv.append(["chart", "--map", map_id, "--tickets", str(spec)])
    codes = sorted(code for code, _ in race(beads, tmp_path, *argv))
    assert codes == [wayfind.EXIT_OK, wayfind.EXIT_RULE]
    assert len([t for t in wayfind.map_tickets(bd, map_id) if t.get("status") != "closed"]) == 7


@needs_bd
def test_two_spellings_of_one_map_serialize_on_one_lock(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(5)])
    short = map_id.split("-", 1)[1]  # bd resolves "abc" to "wm-abc"
    assert bd.show(short)["id"] == map_id
    argv = []
    for n, spelling in enumerate((map_id, short)):
        spec = tmp_path / f"spelled{n}.json"
        spec.write_text(json.dumps({"tickets": [{"type": "task", "title": f"S{n}a"}, {"type": "task", "title": f"S{n}b"}]}))
        argv.append(["chart", "--map", spelling, "--tickets", str(spec)])
    codes = sorted(code for code, _ in race(beads, tmp_path, *argv))
    assert codes == [wayfind.EXIT_OK, wayfind.EXIT_RULE]
    assert len([t for t in wayfind.map_tickets(bd, map_id) if t.get("status") != "closed"]) == 7


@needs_bd
def test_chart_locks_the_canonical_map_id_whatever_the_spelling(beads, tmp_path, monkeypatch):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    seen = []
    real = wayfind.map_lock

    @contextlib.contextmanager
    def spy(bd, scope):
        seen.append(scope)
        with real(bd, scope):
            yield

    monkeypatch.setattr(wayfind, "map_lock", spy)
    for n, spelling in enumerate((map_id, map_id.split("-", 1)[1])):
        spec = tmp_path / f"t{n}.json"
        spec.write_text(json.dumps({"tickets": [{"type": "task", "title": f"T{n}"}]}))
        assert run(beads, "chart", "--map", spelling, "--tickets", str(spec)) == 0
    assert seen == [map_id, map_id]


@needs_bd
@pytest.mark.parametrize("bad", [None, "", 7, ["wm-x"]], ids=["null", "empty", "number", "list"])
def test_chart_of_an_existing_map_refuses_an_unusable_id_from_bd(beads, tmp_path, monkeypatch, capsys, bad):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    spec = tmp_path / "more.json"
    spec.write_text(json.dumps({"tickets": [{"type": "task", "title": "T"}]}))
    before = sorted(t["id"] for t in wayfind.map_tickets(bd, map_id))
    epics = len(bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0"))
    real = wayfind.Bd.show
    monkeypatch.setattr(wayfind.Bd, "show", lambda self, issue_id: dict(real(self, issue_id), id=bad))
    capsys.readouterr()
    assert run(beads, "chart", "--map", map_id, "--kind", "roadmap", "--title", "Fallthrough",
               "--destination", "A destination that must not be created.", "--out-of-scope", "- x",
               "--source", "card pick", "--tickets", str(spec)) == wayfind.EXIT_USAGE
    assert "did not report an ID" in capsys.readouterr().err
    monkeypatch.undo()
    assert sorted(t["id"] for t in wayfind.map_tickets(bd, map_id)) == before
    assert len(bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0")) == epics  # no new map


@needs_bd
def test_a_bare_suffix_retry_after_a_close_failure_is_not_counted_against_the_cap(beads, tmp_path, monkeypatch, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(7)])
    for i in range(6):
        assert commit(beads, bd, map_id, f"B{i}", "now" if i == 0 else "next") == 0
    last = bet_id(bd, map_id, "B6")
    real = wayfind.Bd.close

    def failing_close(self, issue_id, reason):
        raise wayfind.WayfindError("bd close failed: temporary")

    monkeypatch.setattr(wayfind.Bd, "close", failing_close)
    assert commit(beads, bd, map_id, "B6") == wayfind.EXIT_USAGE  # the record is written, the ticket stays open
    monkeypatch.setattr(wayfind.Bd, "close", real)
    assert [t["id"] for t in wayfind.pending_commitments(bd, map_id)] == [last]
    suffix = last.split("-", 1)[1]
    capsys.readouterr()
    assert run(beads, "resolve", suffix, "--answer", "Build B6.", "--source", "card pick",
               "--decision", "commit", "--horizon", "next") == 0
    assert len(wayfind.active_commitments(bd, map_id)) == 7


@needs_bd
def test_a_write_waits_for_the_lock_then_fails_clearly_and_leaves_nothing_tracked(beads, tmp_path, monkeypatch, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    monkeypatch.setenv("WAYFIND_LOCK_TIMEOUT", "0.3")
    with wayfind.map_lock(bd, map_id):
        assert commit(beads, bd, map_id, "B0", "now") == wayfind.EXIT_USAGE
    assert "another wayfind command has held the lock" in capsys.readouterr().err
    assert "waymap:now" not in bd.show(bet_id(bd, map_id, "B0"))["labels"]
    assert commit(beads, bd, map_id, "B0", "now") == 0  # the lock was released
    assert not str(wayfind.lock_path(bd, map_id)).startswith(str(beads))
    assert oct(os.stat(wayfind.lock_path(bd, map_id).parent).st_mode & 0o777) == "0o700"
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=beads,
                            capture_output=True, text=True, check=True).stdout
    assert "lock" not in status


# ---------------------------------------------------------------------------
# The lock trusts nothing on disk
# ---------------------------------------------------------------------------


def no_lock_directory():
    """Charting already made the lock directory; start from none so a test can plant its own."""
    directory = wayfind.lock_dir()
    if directory.exists():
        shutil.rmtree(directory)
    return directory


def refused_without_committing(beads, bd, map_id, capsys, fragment):
    capsys.readouterr()
    assert commit(beads, bd, map_id, "B0", "now") == wayfind.EXIT_USAGE
    assert fragment in capsys.readouterr().err
    assert "waymap:now" not in bd.show(bet_id(bd, map_id, "B0"))["labels"]


def test_the_lock_directory_does_not_depend_on_the_xdg_variables(tmp_path, monkeypatch):
    import pwd
    monkeypatch.delenv("WAYFIND_LOCK_DIR")
    expected = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".local", "state", "clavain-wayfind")
    for env in ({}, {"XDG_RUNTIME_DIR": str(tmp_path)}, {"XDG_STATE_HOME": str(tmp_path)},
                {"XDG_RUNTIME_DIR": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "s"), "HOME": str(tmp_path)}):
        for name in ("XDG_RUNTIME_DIR", "XDG_STATE_HOME"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        assert str(wayfind.lock_dir()) == expected


@needs_bd
def test_a_planted_symlink_at_the_lock_path_is_refused(beads, tmp_path, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    path = wayfind.lock_path(bd, map_id)
    no_lock_directory().mkdir(mode=0o700)
    target = tmp_path / "elsewhere"
    target.write_text("keep")
    path.symlink_to(target)
    refused_without_committing(beads, bd, map_id, capsys, "cannot be opened")
    assert target.read_text() == "keep"


@needs_bd
def test_a_symlinked_lock_directory_is_refused(beads, tmp_path, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    real = tmp_path / "planted"
    real.mkdir(mode=0o700)
    no_lock_directory().symlink_to(real)
    refused_without_committing(beads, bd, map_id, capsys, "is not usable")
    assert list(real.iterdir()) == []


@needs_bd
@pytest.mark.parametrize("mode", [0o755, 0o770, 0o777, 0o500])
def test_a_lock_directory_with_the_wrong_mode_is_refused(beads, tmp_path, capsys, mode):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    directory = no_lock_directory()
    directory.mkdir(mode=0o700)
    directory.chmod(mode)
    try:
        refused_without_committing(beads, bd, map_id, capsys, "mode 0700")
    finally:
        directory.chmod(0o700)


@needs_bd
@pytest.mark.parametrize("mode", [0o664, 0o666, 0o622])
def test_a_lock_file_others_can_write_is_refused(beads, tmp_path, capsys, mode):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    path = wayfind.lock_path(bd, map_id)
    no_lock_directory().mkdir(mode=0o700)
    path.touch()
    path.chmod(mode)
    refused_without_committing(beads, bd, map_id, capsys, "no one else can write")


@needs_bd
def test_a_lock_directory_or_file_owned_by_another_user_is_refused(beads, tmp_path, monkeypatch, capsys):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    path = wayfind.lock_path(bd, map_id)
    no_lock_directory().mkdir(mode=0o700)
    path.touch(mode=0o600)
    real = os.getuid()
    # chown needs root, so claim to be someone else instead. Calls, in order: the lock directory, then
    # the lock file; the first `trusted` of them see the real owner.
    for trusted, fragment in ((0, "owned by you with mode 0700"), (1, "regular file owned by you")):
        calls = iter([real] * trusted)
        monkeypatch.setattr(wayfind, "current_uid", lambda: next(calls, real + 1))
        refused_without_committing(beads, bd, map_id, capsys, fragment)


@needs_bd
def test_a_lock_file_left_by_a_crashed_run_does_not_block_the_next_one(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    script = ("import sys, time; sys.path.insert(0, sys.argv[1]); import wayfind\n"
              "bd = wayfind.Bd(directory=sys.argv[2])\n"
              "with wayfind.map_lock(bd, sys.argv[3]):\n    print('held', flush=True); time.sleep(600)\n")
    holder = subprocess.Popen(["python3", "-c", script, os.path.dirname(wayfind.__file__), str(beads), map_id],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        holder.kill()  # no cleanup runs: the lock file stays behind
        holder.wait(timeout=30)
    finally:
        holder.stdout.close()
    assert wayfind.lock_path(bd, map_id).exists()
    assert commit(beads, bd, map_id, "B0", "now") == 0


# ---------------------------------------------------------------------------
# One lock namespace, and creation shares it
# ---------------------------------------------------------------------------


@needs_bd
def test_writers_with_and_without_xdg_runtime_dir_still_exclude_each_other(beads, tmp_path):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": f"B{i}"} for i in range(7)])
    for i in range(6):
        assert commit(beads, bd, map_id, f"B{i}", "now" if i == 0 else "next") == 0
    more = tmp_path / "more.json"
    more.write_text(json.dumps({"tickets": [{"type": "bet", "title": "B7"}]}))
    assert run(beads, "chart", "--map", map_id, "--tickets", str(more)) == 0
    argv = [["resolve", bet_id(bd, map_id, title), "--answer", f"Build {title}.", "--source", "card pick",
             "--decision", "commit", "--horizon", "next"] for title in ("B6", "B7")]
    elsewhere = tmp_path / "xdg"
    elsewhere.mkdir()
    # The same lock directory (as every writer of one workspace shares it), but one process sees an
    # XDG_RUNTIME_DIR and XDG_STATE_HOME and the other sees neither.
    codes = sorted(code for code, _ in race(
        beads, tmp_path, *argv,
        envs=[{"XDG_RUNTIME_DIR": str(elsewhere), "XDG_STATE_HOME": str(elsewhere)},
              {"XDG_RUNTIME_DIR": None, "XDG_STATE_HOME": None}]))
    assert codes == [wayfind.EXIT_OK, wayfind.EXIT_RULE]
    assert len(wayfind.active_commitments(bd, map_id)) == 7


_CREATOR = """
import os, sys, time
sys.path.insert(0, os.path.dirname(sys.argv[1]))
import wayfind
# Pause right after the new epic exists, before creation looks at it again.
real = wayfind.Bd.create
def create(self, *a, **k):
    out = real(self, *a, **k)
    if k.get("issue_type") == "epic":
        open(sys.argv[2], "w").write(out)
        while not os.path.exists(sys.argv[3]):
            time.sleep(0.05)
    return out
wayfind.Bd.create = create
sys.exit(wayfind.main(sys.argv[4:]))
"""


@needs_bd
def test_creating_a_map_and_adding_to_it_meanwhile_cannot_pass_the_cap(beads, tmp_path):
    bd = wayfind.Bd(directory=str(beads))
    before = {i["id"] for i in bd.json("list", "--all", "--limit", "0")}
    script, made, resume = tmp_path / "creator.py", tmp_path / "made", tmp_path / "resume"
    script.write_text(_CREATOR)
    five = tmp_path / "five.json"
    five.write_text(json.dumps({"tickets": [{"type": "task", "title": f"C{i}"} for i in range(5)]}))
    three = tmp_path / "three.json"
    three.write_text(json.dumps({"tickets": [{"type": "task", "title": f"A{i}"} for i in range(3)]}))
    creator = subprocess.Popen(
        ["python3", str(script), wayfind.__file__, str(made), str(resume), "-C", str(beads), "chart",
         "--title", "Race", "--destination", "Ship it.", "--source", "card pick", "--tickets", str(five)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 120
        while not made.exists():
            assert time.monotonic() < deadline and creator.poll() is None, "creation never reached the pause"
            time.sleep(0.05)
        map_id = made.read_text().strip()
        assert map_id not in before
        assert run(beads, "chart", "--map", map_id, "--tickets", str(three)) == 0  # adds 3 while creation is paused
        resume.write_text("go")
        code, err = creator.wait(timeout=300), creator.stderr.read()
    finally:
        creator.kill()
        creator.stdout.close()
        creator.stderr.close()
    assert code == wayfind.EXIT_RULE and "exceeds the cap of 7" in err
    assert len([t for t in wayfind.map_tickets(bd, map_id) if t.get("status") != "closed"]) == 3


@needs_bd
def test_creating_a_map_holds_the_new_maps_lock_while_it_adds_tickets(beads, tmp_path, monkeypatch):
    # The ordinary path: creation takes both locks, in order, and releases them for the next writer.
    seen = []
    real = wayfind.map_lock

    @contextlib.contextmanager
    def spy(bd, scope):
        seen.append(scope)
        with real(bd, scope):
            yield

    monkeypatch.setattr(wayfind, "map_lock", spy)
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert seen == ["new-map", map_id]
    more = tmp_path / "more.json"
    more.write_text(json.dumps({"tickets": [{"type": "task", "title": "T"}]}))
    assert run(beads, "chart", "--map", map_id, "--tickets", str(more)) == 0


# ---------------------------------------------------------------------------
# The lock namespace is one stable absolute path, or the write is refused
# ---------------------------------------------------------------------------


def test_a_relative_lock_directory_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("WAYFIND_LOCK_DIR", "locks")
    with pytest.raises(wayfind.WayfindError, match="absolute path"):
        wayfind.lock_dir()


@pytest.mark.parametrize("home", ["", "relative/home"])
def test_an_empty_or_relative_home_directory_is_refused(monkeypatch, home):
    import pwd
    monkeypatch.delenv("WAYFIND_LOCK_DIR")
    record = pwd.getpwuid(os.getuid())
    fake = pwd.struct_passwd((record.pw_name, record.pw_passwd, record.pw_uid, record.pw_gid,
                              record.pw_gecos, home, record.pw_shell))
    monkeypatch.setattr(wayfind.pwd, "getpwuid", lambda uid: fake)
    with pytest.raises(wayfind.WayfindError, match="absolute home directory"):
        wayfind.lock_dir()


@needs_bd
def test_two_writers_with_one_relative_lock_directory_are_both_refused(beads, tmp_path, monkeypatch):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}, {"type": "bet", "title": "B1"}])
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
    argv = [["resolve", bet_id(bd, map_id, title), "--answer", f"Build {title}.", "--source", "card pick",
             "--decision", "commit", "--horizon", "next"] for title in ("B0", "B1")]
    script = tmp_path / "racer.py"
    script.write_text(_RACER)
    barrier = tmp_path / "go"
    env = dict(os.environ, WAYFIND_LOCK_DIR="locks")  # the same relative value, a different cwd each
    procs = [subprocess.Popen(["python3", str(script), wayfind.__file__, str(barrier), "-C", str(beads), *a],
                              cwd=tmp_path / name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
             for name, a in zip(("one", "two"), argv)]
    barrier.write_text("go")
    results = [(p.wait(timeout=300), p.stderr.read()) for p in procs]
    for p in procs:
        p.stdout.close()
        p.stderr.close()
    assert [code for code, _ in results] == [wayfind.EXIT_USAGE, wayfind.EXIT_USAGE]
    assert all("must be an absolute path" in err for _, err in results)
    assert not (tmp_path / "one" / "locks").exists() and not (tmp_path / "two" / "locks").exists()
    assert wayfind.active_commitments(bd, map_id) == []


def refuse_the_workspace_identity(monkeypatch, answer):
    """Make bd where --json fail (an exception) or answer something unusable; every other bd call is real."""
    real = wayfind.Bd.run

    def run_bd(self, *args, **kwargs):
        if args[:1] == ("where",):
            if isinstance(answer, Exception):
                raise answer
            return answer
        return real(self, *args, **kwargs)

    monkeypatch.setattr(wayfind.Bd, "run", run_bd)


UNREADABLE_IDENTITY = [
    wayfind.WayfindError("bd where failed: no beads directory"),
    "not json",
    "[]",
    "{}",
    '{"error": "no_beads_directory"}',
    '{"path": ""}',
    '{"path": "relative/.beads"}',
    '{"path": 7}',
]


@needs_bd
@pytest.mark.parametrize("answer", UNREADABLE_IDENTITY, ids=range(len(UNREADABLE_IDENTITY)))
def test_writes_are_refused_when_the_workspace_identity_is_unreadable(beads, tmp_path, monkeypatch, capsys, answer):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    before = sorted(t["id"] for t in wayfind.map_tickets(bd, map_id))
    more = tmp_path / "more.json"
    more.write_text(json.dumps({"tickets": [{"type": "task", "title": "T"}]}))
    new = tmp_path / "new.json"
    new.write_text(json.dumps({"tickets": [{"type": "bet", "title": "N0"}]}))
    refuse_the_workspace_identity(monkeypatch, answer)
    epics = lambda: len(bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0"))
    epics_before = epics()
    locks_before = sorted(os.listdir(wayfind.lock_dir()))
    capsys.readouterr()
    for argv in (
        ["resolve", bet_id(bd, map_id, "B0"), "--answer", "Build B0.", "--source", "card pick",
         "--decision", "commit", "--horizon", "now"],
        ["chart", "--map", map_id, "--tickets", str(more)],
        ["chart", "--kind", "roadmap", "--project", "other", "--title", "Second", "--destination", "A second destination here.",
         "--out-of-scope", "- x", "--source", "card pick", "--tickets", str(new)],
    ):
        assert run(beads, *argv) == wayfind.EXIT_USAGE
        assert "cannot tell which beads workspace this is" in capsys.readouterr().err
    assert sorted(os.listdir(wayfind.lock_dir())) == locks_before  # no lock under a guessed name
    monkeypatch.undo()
    assert sorted(t["id"] for t in wayfind.map_tickets(bd, map_id)) == before
    assert epics() == epics_before
    assert "waymap:now" not in bd.show(bet_id(bd, map_id, "B0"))["labels"]


@needs_bd
def test_reads_still_work_when_the_workspace_identity_is_unreadable(beads, tmp_path, monkeypatch):
    bd, map_id = chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    spec = tmp_path / "dry.json"
    spec.write_text(json.dumps({"tickets": [{"type": "task", "title": "T"}]}))
    refuse_the_workspace_identity(monkeypatch, wayfind.WayfindError("bd where failed"))
    assert run(beads, "lint", map_id) == 0
    assert run(beads, "ready", map_id) == 0
    assert run(beads, "chart", "--map", map_id, "--tickets", str(spec), "--dry-run") == 0
    assert run(beads, "render", map_id, "--out", str(tmp_path / "ROADMAP.md")) == 0


@needs_bd
def test_creation_reads_the_workspace_identity_once(beads, tmp_path, monkeypatch):
    # It must not become unreadable between the first lock and the new map's lock, after the epic exists.
    calls = []
    real = wayfind.Bd.run

    def counting(self, *args, **kwargs):
        calls.append(args[:1])
        return real(self, *args, **kwargs)

    monkeypatch.setattr(wayfind.Bd, "run", counting)
    chart_roadmap(beads, tmp_path, [{"type": "bet", "title": "B0"}])
    assert calls.count(("where",)) == 1
