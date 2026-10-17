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
    with pytest.raises(wayfind.RuleError, match="without a cited source"):
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


def test_empty_out_of_scope_hashes_like_its_placeholder():
    body = wayfind.render_body({"Destination": "D", "Out of scope": ""}, "ruling")
    wayfind.check_targets("m", body, wayfind.parse_body(body))


@pytest.mark.parametrize("tickets, match", [
    ([{"key": "a", "type": "task", "title": "A"}, {"key": "a", "type": "task", "title": "B"}], "duplicate key"),
    ([{"type": "task", "title": "A", "blocked_by": ["nope"]}], "neither a spec key"),
    ([{"key": "a", "type": "task", "title": "A", "blocked_by": ["b"]},
      {"key": "b", "type": "task", "title": "B", "blocked_by": ["a"]}], "cycle"),
    ([{"type": "task", "title": 7}], "title must be a string"),
    ([{"type": "task", "title": "A", "extra": 1}], "unknown key"),
])
def test_bad_spec_is_refused_before_ordering(tmp_path, tickets, match):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"tickets": tickets}))
    with pytest.raises(wayfind.WayfindError, match=match):
        wayfind.creation_order(wayfind.load_spec(str(spec))["tickets"], set())


def test_creation_order_puts_blockers_first(tmp_path):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"tickets": [{"key": "b", "type": "task", "title": "B", "blocked_by": ["a"]},
                                            {"key": "a", "type": "task", "title": "A"}]}))
    order = wayfind.creation_order(wayfind.load_spec(str(spec))["tickets"], set())
    assert [t["key"] for t in order] == ["a", "b"]


def test_bd_timeout_exits_as_usage_error(monkeypatch, capsys):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 120)
    monkeypatch.setattr(wayfind.subprocess, "run", slow)
    assert wayfind.main(["lint", "wf-1"]) == wayfind.EXIT_USAGE
    assert "timed out" in capsys.readouterr().err


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


def all_ids(bd):
    return {i["id"] for i in bd.json("list", "--all", "--limit", "0")}


def ticket_id(bd, map_id, title):
    return next(t["id"] for t in wayfind.map_tickets(bd, map_id) if t["title"] == title)


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
    assert run(beads, "chart", "--title", "t", "--destination", "D") == wayfind.EXIT_RULE
    assert "--source" in capsys.readouterr().err


@needs_bd
def test_chart_refuses_over_cap(beads, tmp_path):
    spec = tmp_path / "many.json"
    spec.write_text(json.dumps({"tickets": [{"type": "research", "title": f"r{i}"} for i in range(8)]}))
    bd = wayfind.Bd(directory=str(beads))
    before = all_ids(bd)
    assert run(beads, "chart", "--title", "t", "--destination", "D", "--source", "s",
               "--tickets", str(spec)) == wayfind.EXIT_RULE
    assert all_ids(bd) == before


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
    assert run(beads, "resolve", ticket, "--answer", "Team A.") == wayfind.EXIT_RULE
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
    assert run(beads, "resolve", b, "--answer", "x") == wayfind.EXIT_RULE
    assert bd.show(b)["status"] != "closed"


@needs_bd
def test_edited_destination_is_a_lint_error_and_blocks_resolve(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    body = bd.show(map_id)["description"]
    bd.set_description(map_id, body.replace("A spec for X.", "A spec for X, then build it."))
    assert run(beads, "lint", map_id) == wayfind.EXIT_RULE
    ticket = wayfind.map_tickets(bd, map_id)[0]["id"]
    assert run(beads, "resolve", ticket, "--answer", "found it") == wayfind.EXIT_RULE
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
    rev = ticket_id(bd, map_id, "Revisit storage")
    # A revisit is HITL: it needs the owner's answer and the decision it replaces.
    assert run(beads, "resolve", rev, "--answer", "Use SQLite.", "--supersedes", r) == wayfind.EXIT_RULE
    assert run(beads, "resolve", rev, "--answer", "Use SQLite.", "--source", "ruling") == wayfind.EXIT_RULE
    assert run(beads, "resolve", rev, "--answer", "Use SQLite.", "--source", "ruling",
               "--supersedes", rev) == wayfind.EXIT_RULE
    assert bd.show(rev)["status"] != "closed"
    assert run(beads, "resolve", rev, "--answer", "Use SQLite.", "--source", "ruling", "--supersedes", r) == 0
    body = bd.show(map_id)["description"]
    assert f"{r} R: Use Postgres. (superseded by {rev})" in body
    assert wayfind.SUPERSEDED_LABEL in bd.show(r)["labels"]
    assert wayfind.evaluate(bd, map_id, 7, 14)["errors"] == []


@needs_bd
def test_supersedes_must_name_a_resolved_ticket_of_the_same_map(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"},
                                             {"type": "revisit", "title": "Rev"}])
    _, other_map = chart_map(beads, tmp_path, [{"type": "research", "title": "Elsewhere"}])
    r, rev = ticket_id(bd, map_id, "R"), ticket_id(bd, map_id, "Rev")
    elsewhere = ticket_id(bd, other_map, "Elsewhere")
    assert run(beads, "resolve", elsewhere, "--answer", "x") == 0
    base = ["resolve", rev, "--answer", "y", "--source", "ruling"]
    assert run(beads, *base, "--supersedes", r) == wayfind.EXIT_RULE          # still open
    assert run(beads, *base, "--supersedes", elsewhere) == wayfind.EXIT_RULE  # other map
    assert run(beads, *base, "--supersedes", r, "--invalidated") == wayfind.EXIT_USAGE
    assert bd.show(rev)["status"] != "closed"


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
def test_empty_out_of_scope_lints_clean(beads, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"tickets": [{"type": "task", "title": "T"}]}))
    bd = wayfind.Bd(directory=str(beads))
    before = all_ids(bd)
    assert run(beads, "chart", "--title", "t", "--destination", "D", "--source", "s", "--tickets", str(spec)) == 0
    map_id = next(i for i in all_ids(bd) - before if wayfind.MAP_LABEL in (bd.show(i).get("labels") or []))
    assert run(beads, "lint", map_id) == 0


@needs_bd
def test_bad_spec_writes_nothing_even_without_dry_run(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"key": "a", "type": "task", "title": "A"}])
    spec = tmp_path / "cycle.json"
    spec.write_text(json.dumps({"tickets": [{"key": "x", "type": "task", "title": "X", "blocked_by": ["y"]},
                                            {"key": "y", "type": "task", "title": "Y", "blocked_by": ["x"]}]}))
    before, body = all_ids(bd), bd.show(map_id)["description"]
    for extra in (["--dry-run"], []):
        assert run(beads, "chart", "--map", map_id, "--tickets", str(spec), *extra) == wayfind.EXIT_USAGE
    assert all_ids(bd) == before and bd.show(map_id)["description"] == body


@needs_bd
def test_chart_failure_part_way_leaves_the_body_unchanged(beads, tmp_path, monkeypatch, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "task", "title": "A"}], fog=("storage", "auth"))
    body = bd.show(map_id)["description"]
    spec = tmp_path / "next.json"
    spec.write_text(json.dumps({"graduate": ["storage"], "tickets": [
        {"key": "p", "type": "research", "title": "P"}, {"key": "q", "type": "research", "title": "Q"}]}))
    real_create, calls = wayfind.Bd.create, []

    def flaky(self, *args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise wayfind.WayfindError("bd create failed: injected")
        return real_create(self, *args, **kwargs)
    monkeypatch.setattr(wayfind.Bd, "create", flaky)
    capsys.readouterr()
    assert run(beads, "chart", "--map", map_id, "--tickets", str(spec)) == wayfind.EXIT_USAGE
    assert "the map body is unchanged" in capsys.readouterr().err
    assert bd.show(map_id)["description"] == body
    assert wayfind.evaluate(bd, map_id, 7, 14)["fog"] == 2


@needs_bd
def test_resolve_finishes_a_partial_run_and_is_idempotent(beads, tmp_path, monkeypatch, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    r = ticket_id(bd, map_id, "R")
    real_set = wayfind.Bd.set_description

    def broken(self, issue_id, body):
        raise wayfind.WayfindError("bd update failed: injected")
    monkeypatch.setattr(wayfind.Bd, "set_description", broken)
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == wayfind.EXIT_USAGE
    monkeypatch.setattr(wayfind.Bd, "set_description", real_set)
    assert bd.show(r)["status"] == "closed"
    errors = wayfind.evaluate(bd, map_id, 7, 14)["errors"]
    assert any("missing from Decisions so far" in e for e in errors)
    # A retry with the same arguments finishes the job, then has nothing left to do.
    capsys.readouterr()
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == 0
    assert "finished an earlier partial run" in capsys.readouterr().out
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == 0
    assert "nothing to do" in capsys.readouterr().out
    assert len([c for c in bd.comments(r) if c["text"].startswith("Resolution:")]) == 1
    assert wayfind.evaluate(bd, map_id, 7, 14)["errors"] == []
    # A different answer is a reversal, not a retry.
    assert run(beads, "resolve", r, "--answer", "Use SQLite.") == wayfind.EXIT_RULE


@needs_bd
def test_resolve_refuses_a_ticket_closed_outside_wayfind(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    r = ticket_id(bd, map_id, "R")
    bd.close(r, "done by hand")
    assert run(beads, "resolve", r, "--answer", "x") == wayfind.EXIT_RULE
    assert any("missing from Decisions" in e for e in wayfind.evaluate(bd, map_id, 7, 14)["errors"])


@needs_bd
def test_ready_claim_resumes_the_callers_own_ticket(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R1"},
                                             {"type": "research", "title": "R2"}])
    capsys.readouterr()
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    first = json.loads(capsys.readouterr().out)
    assert first["claimed"] and not first["resumed"]
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    again = json.loads(capsys.readouterr().out)
    assert again["claimed"] == first["claimed"] and again["resumed"]
    assert again["in_progress"] == [{"id": first["claimed"], "type": "research", "assignee": "agent-a"}]
    assert run(beads, "--actor", "agent-b", "ready", map_id, "--claim", "--json") == 0
    other = json.loads(capsys.readouterr().out)
    assert other["claimed"] not in (None, first["claimed"]) and not other["resumed"]


@needs_bd
def test_simultaneous_hitl_claims_keep_exactly_one(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "G1"},
                                             {"type": "grilling", "title": "G2"}])
    low, high = sorted(t["id"] for t in wayfind.map_tickets(bd, map_id))
    a, b = wayfind.Bd(directory=str(beads), actor="agent-a"), wayfind.Bd(directory=str(beads), actor="agent-b")
    # Both saw an empty HITL slot; agent-b claimed the smaller id first.
    b.claim(low)
    claimed, held = wayfind.claim_one(a, map_id, [bd.show(high)])
    assert claimed is None and low in held
    assert bd.show(high)["status"] == "open" and not bd.show(high).get("assignee")
    claimed, held = wayfind.claim_one(b, map_id, [bd.show(low)])
    assert claimed["id"] == low and held is None
    assert wayfind.evaluate(bd, map_id, 7, 14)["hitl_in_flight"] == [low]


@needs_bd
def test_cleared_map_points_to_strategy(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "task", "title": "T"}], fog=())
    assert run(beads, "resolve", wayfind.map_tickets(bd, map_id)[0]["id"], "--answer", "done") == 0
    capsys.readouterr()
    assert run(beads, "lint", map_id) == 0
    assert "/clavain:strategy" in capsys.readouterr().out
