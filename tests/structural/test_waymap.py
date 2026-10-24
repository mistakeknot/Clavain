"""Waymap tests: the roadmap kind of the wayfind engine, against a real bd.

The plain wayfinder:map behaviour is covered by test_wayfind.py; the last tests here pin that it did not move.
"""
import json
import os
import shutil
import subprocess

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
def one_roadmap_at_a_time(beads):
    """A project holds one open roadmap, so close the previous test's before the next charts its own."""
    if BD is None:
        return
    bd = wayfind.Bd(directory=str(beads))
    for issue in bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0"):
        bd.run("close", issue["id"], "-r", "test teardown", "--force")


def run(beads, *argv):
    return wayfind.main(["-C", str(beads), *argv])


def chart_roadmap(beads, tmp_path, tickets, fog=("a later bet",)):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"tickets": tickets, "fog": list(fog)}))
    bd = wayfind.Bd(directory=str(beads))
    assert run(beads, "chart", "--kind", "roadmap", "--title", "Roadmap", "--destination",
               "A product people can adopt by Q-end.", "--out-of-scope", "- billing", "--source", "card pick",
               "--tickets", str(spec)) == 0
    map_id = bd.json("list", "--label", wayfind.ROADMAP_LABEL, "--limit", "0")[0]["id"]
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
    assert issue["labels"] == [wayfind.ROADMAP_LABEL]
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
    assert run(beads, "chart", "--kind", "roadmap", "--title", "Another", "--destination", "D",
               "--source", "s") == wayfind.EXIT_RULE
    assert {i["id"] for i in bd.json("list", "--all", "--limit", "0")} == before


@needs_bd
def test_roadmap_destination_is_one_line(beads):
    assert run(beads, "chart", "--kind", "roadmap", "--title", "t", "--destination", "line one\nline two",
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
