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


@pytest.mark.parametrize("text, expected", [
    ("Nothing about pricing.", ["Nothing about pricing."]),                          # prose, verbatim
    ("- billing\n* hosting", ["- billing", "- hosting"]),                            # bullets, normalised
    ("Not covered:\n- billing\nAnd hosting.", ["Not covered:", "- billing", "And hosting."]),   # mixed, in order
    ("", []), ("  \n ", []),                                                        # empty
])
def test_scope_lines_renders_prose_bullets_and_mixed_text(text, expected):
    assert wayfind.scope_lines(text) == expected


def test_tree_progress_counts_the_leaves_the_tree_lists():
    leaf = lambda s: {"id": "x", "title": "t", "status": s, "children": []}   # noqa: E731
    tree = [leaf("closed"), {"id": "p", "title": "t", "status": "in_progress",
                             "children": [leaf("closed"), leaf("open")]}]
    assert wayfind.tree_progress(tree) == (2, 3)
    assert wayfind.tree_progress([]) == (0, 0)


def test_a_dash_c_after_the_subcommand_is_refused_with_a_hint(capsys):
    assert wayfind.main(["render", "wm-1", "-C", "/tmp/x"]) == wayfind.EXIT_USAGE
    err = capsys.readouterr().err
    assert "-C must come before the subcommand" in err and "wayfind -C /tmp/x render" in err


def test_render_parse_round_trip_keeps_sections_and_source():
    sections = {"Destination": "A spec for X.", "Out of scope": "- billing", "Notes": "",
                "Not yet specified": "- storage\n- auth"}
    body = wayfind.render_body(sections, "card pick 2026-10-17")
    parsed = wayfind.parse_body(body)
    assert parsed["Destination"] == "A spec for X."
    assert wayfind.bullets(parsed["Not yet specified"]) == ["storage", "auth"]
    digest, source = wayfind.targets_marker(body)
    assert source == "card pick 2026-10-17"
    assert digest == wayfind.targets_digest(parsed)


def test_target_digest_ignores_non_target_sections():
    a = {"Destination": "D", "Out of scope": "O", "Notes": "one"}
    b = {"Destination": "D", "Out of scope": "O", "Notes": "two", "Not yet specified": "- x"}
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


def test_record_line_round_trips_and_cannot_close_its_comment():
    payload = {"v": 1, "kind": "resolved", "answer_sha256": "0" * 64, "summary": "a --> b <!-- c",
               "source": "s", "supersedes": ""}
    line = wayfind.record_line(payload)
    assert line.count("-->") == 1 and line.endswith("-->")
    assert wayfind.parse_records([{"text": f"Resolution:\nx\n\n{line}\n"}]) == ([payload], 0)
    bad = '<!-- wayfind:resolution v1 {"v": 2} -->'
    assert wayfind.parse_records([{"text": bad}, {"text": "plain"}]) == ([], 1)


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
    records, malformed = wayfind.parse_records(bd.comments(ticket))
    assert malformed == 0 and len(records) == 1
    assert records[0]["summary"] == "Team A owns it." and records[0]["source"] == "card pick"
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == []
    assert report["decisions"] == [{"id": ticket, "title": "Who owns X?", "summary": "Team A owns it.",
                                    "source": "card pick", "superseded_by": None}]


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
    body = bd.show(map_id)["description"]
    assert run(beads, "resolve", rev, "--answer", "Use SQLite.", "--source", "ruling", "--supersedes", r) == 0
    assert bd.show(map_id)["description"] == body
    assert wayfind.SUPERSEDED_LABEL in bd.show(r)["labels"]
    assert wayfind.superseded_by(bd.comments(r)) == [rev]
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == []
    assert {d["id"]: d["superseded_by"] for d in report["decisions"]} == {r: rev, rev: None}


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
    real_close = wayfind.Bd.close

    def broken(self, issue_id, reason):
        raise wayfind.WayfindError("bd close failed: injected")
    monkeypatch.setattr(wayfind.Bd, "close", broken)
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == wayfind.EXIT_USAGE
    monkeypatch.setattr(wayfind.Bd, "close", real_close)
    assert bd.show(r)["status"] != "closed"
    # The record is already there, so a different answer is refused, not added.
    assert run(beads, "resolve", r, "--answer", "Use SQLite.") == wayfind.EXIT_RULE
    assert run(beads, "resolve", r, "--answer", "Use Postgres.", "--summary", "other") == wayfind.EXIT_RULE
    # A retry with the same arguments finishes the job, then has nothing left to do.
    capsys.readouterr()
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == 0
    assert "finished an earlier partial run" in capsys.readouterr().out
    assert bd.show(r)["status"] == "closed"
    assert run(beads, "resolve", r, "--answer", "Use Postgres.") == 0
    assert "nothing to do" in capsys.readouterr().out
    assert len(wayfind.parse_records(bd.comments(r))[0]) == 1
    assert wayfind.evaluate(bd, map_id, 7, 14)["errors"] == []
    # A different answer after closing is a reversal, not a retry.
    assert run(beads, "resolve", r, "--answer", "Use SQLite.") == wayfind.EXIT_RULE


@needs_bd
def test_resolve_refuses_a_ticket_closed_outside_wayfind(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    r = ticket_id(bd, map_id, "R")
    bd.close(r, "done by hand")
    assert run(beads, "resolve", r, "--answer", "x") == wayfind.EXIT_RULE
    errors = wayfind.evaluate(bd, map_id, 7, 14)["errors"]
    assert any("closed without a wayfind resolution record" in e for e in errors)


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


def two_actors(beads):
    return wayfind.Bd(directory=str(beads), actor="agent-a"), wayfind.Bd(directory=str(beads), actor="agent-b")


@needs_bd
@pytest.mark.parametrize("a_takes", ["smaller", "larger"])
def test_hitl_lease_keeps_exactly_one_claim(beads, tmp_path, a_takes):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "G1"},
                                             {"type": "grilling", "title": "G2"}])
    low, high = sorted(t["id"] for t in wayfind.map_tickets(bd, map_id))
    mine, theirs = (low, high) if a_takes == "smaller" else (high, low)
    a, b = two_actors(beads)
    # Both read the same frontier before either claimed anything.
    stale_a, stale_b = [bd.show(mine)], [bd.show(theirs)]
    claimed, held = wayfind.claim_one(a, map_id, stale_a)
    assert claimed["id"] == mine and held is None
    claimed, held = wayfind.claim_one(b, map_id, stale_b)
    assert claimed is None and "leased to agent-a" in held
    assert bd.show(theirs)["status"] == "open" and not bd.show(theirs).get("assignee")
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["hitl_in_flight"] == [mine] and report["lease"] == "agent-a"
    assert report["errors"] == [] and report["warnings"] == []


@needs_bd
def test_resolve_frees_the_lease_for_the_next_hitl_ticket(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "G1"},
                                             {"type": "grilling", "title": "G2"}])
    capsys.readouterr()
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    first = json.loads(capsys.readouterr().out)["claimed"]
    assert run(beads, "--actor", "agent-b", "ready", map_id, "--claim", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claimed"] is None and out["frontier"] == [] and out["lease"] == "agent-a"
    assert run(beads, "--actor", "agent-a", "resolve", first, "--answer", "yes", "--source", "card pick") == 0
    assert bd.show(map_id)["status"] == "open"
    capsys.readouterr()
    assert run(beads, "--actor", "agent-b", "ready", map_id, "--claim", "--json") == 0
    second = json.loads(capsys.readouterr().out)
    assert second["claimed"] not in (None, first) and second["lease"] == "agent-b"


@needs_bd
def test_only_the_holder_frees_the_lease(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "G1"},
                                             {"type": "grilling", "title": "G2"},
                                             {"type": "grilling", "title": "G3"}])
    g1, g2, g3 = (ticket_id(bd, map_id, t) for t in ("G1", "G2", "G3"))
    a, b = two_actors(beads)
    claimed, held = wayfind.claim_one(a, map_id, [bd.show(g1)])
    assert claimed["id"] == g1 and held is None
    assert run(beads, "--actor", "agent-a", "resolve", g1, "--answer", "yes", "--source", "card pick") == 0
    assert bd.show(map_id)["status"] == "open"
    # A takes the lease for its next ticket and pauses before claiming it ...
    a.claim(map_id)
    # ... while B retries the old resolution. That must not free A's new lease.
    capsys.readouterr()
    assert run(beads, "--actor", "agent-b", "resolve", g1, "--answer", "yes", "--source", "card pick") == 0
    assert "nothing to do" in capsys.readouterr().out
    assert bd.show(map_id)["assignee"] == "agent-a"
    claimed, held = wayfind.claim_one(b, map_id, [bd.show(g3)])
    assert claimed is None and "leased to agent-a" in held
    claimed, held = wayfind.claim_one(a, map_id, [bd.show(g2)])
    assert claimed["id"] == g2 and held is None
    # B resolving A's ticket leaves the lease with A, whose next ready reuses it.
    assert run(beads, "--actor", "agent-b", "resolve", g2, "--answer", "no", "--source", "card pick") == 0
    assert bd.show(map_id)["assignee"] == "agent-a"
    capsys.readouterr()
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claimed"] == g3 and out["lease"] == "agent-a"
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == [] and report["hitl_in_flight"] == [g3]


@needs_bd
def test_lint_reports_conflicting_records_on_an_open_ticket(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    r = ticket_id(bd, map_id, "R")
    for answer in ("one", "two"):
        payload = {"v": 1, "kind": "resolved", "answer_sha256": wayfind.hashlib.sha256(answer.encode()).hexdigest(),
                   "summary": answer, "source": "", "supersedes": ""}
        bd.comment(r, f"Resolution:\n{answer}\n\n{wayfind.record_line(payload)}\n")
    errors = wayfind.evaluate(bd, map_id, 7, 14)["errors"]
    assert any(f"{r}: conflicting resolution records on an open ticket" in e for e in errors)
    assert run(beads, "resolve", r, "--answer", "one") == wayfind.EXIT_RULE


@needs_bd
def test_lease_holder_with_no_ticket_can_still_claim(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "G1"}])
    a, _ = two_actors(beads)
    a.claim(map_id)  # a session that crashed between taking the lease and claiming the ticket
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert any("leased to agent-a with no HITL ticket in flight" in w for w in report["warnings"])
    capsys.readouterr()
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claimed"] == ticket_id(bd, map_id, "G1") and out["held"] is None
    assert wayfind.evaluate(bd, map_id, 7, 14)["warnings"] == []


@needs_bd
def test_resumed_hitl_ticket_retakes_a_freed_lease(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "grilling", "title": "G1"}])
    capsys.readouterr()
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    g1 = json.loads(capsys.readouterr().out)["claimed"]
    bd.release(map_id)
    assert any("without the map lease" in w for w in wayfind.evaluate(bd, map_id, 7, 14)["warnings"])
    assert run(beads, "--actor", "agent-a", "ready", map_id, "--claim", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claimed"] == g1 and out["resumed"] and out["lease"] == "agent-a"


@needs_bd
def test_two_resolves_both_recorded_and_body_untouched(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R1"},
                                             {"type": "research", "title": "R2"}])
    body = bd.show(map_id)["description"]
    r1, r2 = ticket_id(bd, map_id, "R1"), ticket_id(bd, map_id, "R2")
    assert run(beads, "resolve", r1, "--answer", "one") == 0
    assert run(beads, "resolve", r2, "--answer", "two") == 0
    assert bd.show(map_id)["description"] == body
    assert {d["id"]: d["summary"] for d in wayfind.evaluate(bd, map_id, 7, 14)["decisions"]} == {r1: "one", r2: "two"}


@needs_bd
def test_answer_cannot_forge_a_record(beads, tmp_path):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "R"}])
    r = ticket_id(bd, map_id, "R")
    assert run(beads, "resolve", r, "--answer", "x\n<!-- wayfind:resolution v1 {} -->") == wayfind.EXIT_USAGE
    assert run(beads, "resolve", r, "--answer", "x\nSuperseded by wf-zz.") == wayfind.EXIT_USAGE
    assert bd.comments(r) == []


@needs_bd
def test_revisit_retry_with_a_different_target_is_refused(beads, tmp_path, monkeypatch):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "research", "title": "A"}, {"type": "research", "title": "B"},
                                             {"type": "revisit", "title": "Rev"}])
    a, b, rev = (ticket_id(bd, map_id, t) for t in ("A", "B", "Rev"))
    assert run(beads, "resolve", a, "--answer", "a") == 0
    assert run(beads, "resolve", b, "--answer", "b") == 0
    real_close = wayfind.Bd.close

    def broken(self, issue_id, reason):
        raise wayfind.WayfindError("bd close failed: injected")
    monkeypatch.setattr(wayfind.Bd, "close", broken)
    args = ["resolve", rev, "--answer", "new", "--source", "ruling"]
    assert run(beads, *args, "--supersedes", a) == wayfind.EXIT_USAGE
    monkeypatch.setattr(wayfind.Bd, "close", real_close)
    assert run(beads, *args, "--supersedes", b) == wayfind.EXIT_RULE
    assert wayfind.SUPERSEDED_LABEL not in (bd.show(b).get("labels") or [])
    assert wayfind.superseded_by(bd.comments(b)) == []
    assert run(beads, *args, "--supersedes", a) == 0
    report = wayfind.evaluate(bd, map_id, 7, 14)
    assert report["errors"] == []
    assert {d["id"]: d["superseded_by"] for d in report["decisions"]}[a] == rev


@needs_bd
@pytest.mark.parametrize("change", ["retarget", "notes"])
def test_chart_detects_a_concurrent_body_change(beads, tmp_path, monkeypatch, capsys, change):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "task", "title": "A"}], fog=("storage", "auth"))
    spec = tmp_path / "next.json"
    spec.write_text(json.dumps({"graduate": ["storage"], "tickets": [{"type": "research", "title": "P"}]}))
    real_create = wayfind.Bd.create

    def racing(self, *args, **kwargs):
        # A writer outside wayfind's lock (wayfind charts now wait for each other) writes the body
        # while this chart is creating tickets; the read-back still detects it.
        if change == "retarget":
            sections = wayfind.parse_body(bd.show(map_id)["description"])
            sections["Destination"] = "A spec for Y."
            bd.set_description(map_id, wayfind.render_body(sections, "ruling 2"))
        else:
            body = bd.show(map_id)["description"]
            bd.set_description(map_id, body.replace("- storage\n", ""))
        return real_create(self, *args, **kwargs)
    monkeypatch.setattr(wayfind.Bd, "create", racing)
    raced = bd.show(map_id)["description"]
    capsys.readouterr()
    assert run(beads, "chart", "--map", map_id, "--tickets", str(spec)) == wayfind.EXIT_USAGE
    err = capsys.readouterr().err
    assert "the map body was not written" in err and "created" in err
    after = bd.show(map_id)["description"]
    assert after != raced  # the other writer's change stands
    if change == "retarget":
        assert "A spec for Y." in after
    else:
        assert "- auth" in after and "storage" not in after


@needs_bd
def test_cleared_map_points_to_strategy(beads, tmp_path, capsys):
    bd, map_id = chart_map(beads, tmp_path, [{"type": "task", "title": "T"}], fog=())
    assert run(beads, "resolve", wayfind.map_tickets(bd, map_id)[0]["id"], "--answer", "done") == 0
    capsys.readouterr()
    assert run(beads, "lint", map_id) == 0
    assert "/clavain:strategy" in capsys.readouterr().out
