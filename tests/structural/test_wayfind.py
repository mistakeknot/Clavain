"""Wayfind tests: body helpers in isolation, then the four subcommands against a real bd."""
import datetime as dt
import json
import os
import shutil
import subprocess

import pytest

import wayfind


# ---------------------------------------------------------------------------
# Body helpers
# ---------------------------------------------------------------------------


def test_render_parse_round_trip_keeps_sections_and_source():
    sections = {"Destination": "A spec for X.", "Out of scope": "- billing", "Notes": "",
                "Decisions so far": "- wf-1 Q: yes", "Not yet specified": "- storage\n- auth"}
    body = wayfind.render_body(sections, "card pick 2026-10-17")
    parsed = wayfind.parse_body(body)
    assert parsed["Destination"] == "A spec for X."
    assert wayfind.bullets(parsed["Not yet specified"]) == ["storage", "auth"]
    digest, source = wayfind.targets_marker(body)
    assert source == "card pick 2026-10-17"
    assert digest == wayfind.targets_digest(parsed)


def test_target_digest_ignores_non_target_sections():
    a = {"Destination": "D", "Out of scope": "O", "Notes": "one"}
    b = {"Destination": "D", "Out of scope": "O", "Notes": "two", "Decisions so far": "- x"}
    assert wayfind.targets_digest(a) == wayfind.targets_digest(b)
    assert wayfind.targets_digest(a) != wayfind.targets_digest({**a, "Destination": "D2"})


def test_source_cannot_close_the_marker_comment():
    body = wayfind.render_body({"Destination": "D"}, "evil --> <!-- x\nnewline")
    assert wayfind.targets_marker(body)[1] == "evil  <!-- x newline"


def test_check_targets_refuses_edited_destination():
    body = wayfind.render_body({"Destination": "D", "Out of scope": "O"}, "ruling")
    edited = body.replace("## Destination\nD", "## Destination\nD, and also build it")
    with pytest.raises(wayfind.WayfindError, match="without a cited source"):
        wayfind.check_targets("m", edited, wayfind.parse_body(edited))


def test_ticket_type_requires_exactly_one_label():
    assert wayfind.ticket_type({"labels": ["wayfinder:research"]}) == "research"
    assert wayfind.ticket_type({"labels": ["wayfinder:research", "wayfinder:task"]}) is None
    assert wayfind.ticket_type({"labels": None}) is None


def test_spec_rejects_unknown_type(tmp_path):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"tickets": [{"type": "build", "title": "do it"}]}))
    with pytest.raises(wayfind.WayfindError, match="type must be one of"):
        wayfind.load_spec(str(spec))


# ---------------------------------------------------------------------------
# Real bd
# ---------------------------------------------------------------------------

BD = shutil.which("bd")
needs_bd = pytest.mark.skipif(BD is None, reason="bd not installed")


@pytest.fixture(scope="module")
def beads(tmp_path_factory):
    """One embedded beads database for the module; each test charts its own map."""
    root = tmp_path_factory.mktemp("beads")
    with pytest.MonkeyPatch.context() as mp:
        for name in [k for k in os.environ if k.startswith("BEADS_")]:
            mp.delenv(name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run([str(BD), "init", "-q", "-p", "wf"], cwd=root, check=True, capture_output=True)
        yield root


def run(beads, *argv):
    return wayfind.main(["-C", str(beads), *argv])


def chart_map(beads, tmp_path, tickets, fog=("storage layout",), source="card pick"):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"tickets": tickets, "fog": list(fog)}))
    bd = wayfind.Bd(directory=str(beads))
    before = {i["id"] for i in bd.json("list", "--all", "--limit", "0")}
    assert run(beads, "chart", "--title", "spec for X", "--destination", "A spec for X.",
               "--out-of-scope", "- billing", "--source", source, "--tickets", str(spec)) == 0
    new = [i for i in bd.json("list", "--all", "--limit", "0") if i["id"] not in before]
    map_id = next(i["id"] for i in new if wayfind.MAP_LABEL in (i.get("labels") or []) and not i.get("parent"))
    return bd, map_id


@needs_bd
def test_chart_creates_typed_tickets_with_deps_and_no_map_label(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [
        {"key": "q", "type": "grilling", "title": "Who owns X?"},
        {"key": "r", "type": "research", "title": "Prior art for X", "blocked_by": ["q"]},
    ])
    kids = {t["title"]: t for t in wayfind.map_tickets(bd, map_id)}
    assert kids["Who owns X?"]["labels"] == ["wayfinder:grilling"]
    assert kids["Prior art for X"]["labels"] == ["wayfinder:research"]
    blockers = [d["depends_on_id"] for d in kids["Prior art for X"].get("dependencies") or [] if d["type"] == "blocks"]
    assert blockers == [kids["Who owns X?"]["id"]]
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == [] and report["warnings"] == []
    assert report["fog"] == 1 and report["open"] == 2


@needs_bd
def test_new_map_needs_source(beads, capsys):
    assert run(beads, "chart", "--title", "t", "--destination", "D") == wayfind.EXIT_USAGE
    assert "--source" in capsys.readouterr().err


@needs_bd
def test_chart_refuses_over_cap(beads, tmp_path):
    spec = tmp_path / "many.json"
    spec.write_text(json.dumps({"tickets": [{"type": "research", "title": f"r{i}"} for i in range(8)]}))
    assert run(beads, "chart", "--title", "t", "--destination", "D", "--source", "s",
               "--tickets", str(spec)) == wayfind.EXIT_USAGE


@needs_bd
def test_ready_holds_second_hitl_ticket_while_one_is_claimed(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [
        {"type": "grilling", "title": "G1"}, {"type": "prototype", "title": "P1"},
        {"type": "research", "title": "R1"},
    ])
    capsys.readouterr()
    assert run(beads, "ready", map_id, "--json") == 0
    assert {t["title"] for t in json.loads(capsys.readouterr().out)["frontier"]} == {"G1", "P1", "R1"}
    g1 = next(t for t in wayfind.map_tickets(bd, map_id) if t["title"] == "G1")
    bd.claim(g1["id"])
    assert run(beads, "ready", map_id, "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert [t["title"] for t in out["frontier"]] == ["R1"]
    assert out["hitl_in_flight"] == [g1["id"]]


@needs_bd
def test_resolve_hitl_needs_source_then_records_decision(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "Who owns X?"}])
    ticket = wayfind.map_tickets(bd, map_id)[0]["id"]
    assert run(beads, "resolve", ticket, "--answer", "Team A.") == wayfind.EXIT_USAGE
    assert run(beads, "resolve", ticket, "--answer", "Team A owns it.\nMore detail.",
               "--source", "card pick") == 0
    closed = bd.show(ticket)
    assert closed["status"] == "closed" and "source: card pick" in closed["close_reason"]
    body = bd.show(map_id)["description"]
    assert f"- {ticket} Who owns X?: Team A owns it." in body
    assert wayfind.evaluate(bd, map_id, 7, 14)["errors"] == []


@needs_bd
def test_resolve_refuses_blocked_ticket(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [
        {"key": "a", "type": "research", "title": "A"},
        {"key": "b", "type": "research", "title": "B", "blocked_by": ["a"]},
    ])
    b = next(t["id"] for t in wayfind.map_tickets(bd, map_id) if t["title"] == "B")
    assert run(beads, "resolve", b, "--answer", "x") == wayfind.EXIT_USAGE
    assert bd.show(b)["status"] != "closed"


@needs_bd
def test_edited_destination_is_a_lint_error_and_blocks_resolve(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    body = bd.show(map_id)["description"]
    bd.set_description(map_id, body.replace("A spec for X.", "A spec for X, then build it."))
    assert run(beads, "lint", map_id) == wayfind.EXIT_RULE
    ticket = wayfind.map_tickets(bd, map_id)[0]["id"]
    assert run(beads, "resolve", ticket, "--answer", "found it") == wayfind.EXIT_USAGE
    # Recording the change with a source makes the map valid again.
    assert run(beads, "chart", "--map", map_id, "--destination", "A spec for X, then build it.",
               "--source", "ruling r1") == 0
    assert run(beads, "lint", map_id) == 0


@needs_bd
def test_graduate_fog_and_supersede(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}], fog=("storage", "auth"))
    r = wayfind.map_tickets(bd, map_id)[0]["id"]
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == 0
    spec = tmp_path / "next.json"
    spec.write_text(json.dumps({"graduate": ["storage"],
                                "tickets": [{"type": "revisit", "title": "Revisit storage"}]}))
    assert run(beads, "chart", "--map", map_id, "--tickets", str(spec)) == 0
    assert wayfind.evaluate(bd, map_id, 7, 14)["fog"] == 1
    rev = next(t["id"] for t in wayfind.map_tickets(bd, map_id) if t["title"] == "Revisit storage")
    assert run(beads, "resolve", rev, "--answer", "Use SQLite.", "--supersedes", r) == 0
    body = bd.show(map_id)["description"]
    assert f"{r} R: Use Postgres. (superseded by {rev})" in body
    assert wayfind.SUPERSEDED_LABEL in bd.show(r)["labels"]


@needs_bd
def test_divergence_alarm_and_stale_alarm(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": f"R{i}"} for i in range(4)])
    ids = [t["id"] for t in wayfind.map_tickets(bd, map_id)]
    assert run(beads, "resolve", ids[0], "--answer", "kept") == 0
    for t in ids[1:3]:
        assert run(beads, "resolve", t, "--answer", "moot", "--invalidated") == 0
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["invalidated"] == 2 and report["resolved"] == 1
    assert any(a.startswith("diverging") for a in report["alarms"])
    assert run(beads, "lint", map_id) == wayfind.EXIT_ALARM
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
    assert any(a.startswith("stale") for a in wayfind.evaluate(bd, map_id, 7, 14, now=later)["alarms"])


@needs_bd
def test_cleared_map_points_to_strategy(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "task", "title": "T"}], fog=())
    assert run(beads, "resolve", wayfind.map_tickets(bd, map_id)[0]["id"], "--answer", "done") == 0
    capsys.readouterr()
    assert run(beads, "lint", map_id) == 0
    assert "/clavain:strategy" in capsys.readouterr().out
