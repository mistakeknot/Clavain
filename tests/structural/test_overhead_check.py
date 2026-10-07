"""Offline fixtures mirror BB's raw event envelope and item/turn lifecycle."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/overhead-check.py"
NOW = "2026-10-02T12:00:00Z"
EPOCH_MS = 1790942400000


def turn(number, text="Nothing new.", age_hours=1, tool=None, complete=True):
    scope = {"kind": "turn", "turnId": f"turn-{number}"}
    def event(kind, data, offset):
        return {"id": f"evt-{number}-{offset}", "seq": number * 10 + offset,
                "threadId": "thr_fixture", "scope": scope, "type": kind,
                "createdAt": EPOCH_MS - age_hours * 3600000 + offset, "data": data}
    events = [event("turn/started", {}, 0)]
    if tool:
        events.append(event("item/started", {"item": {"id": f"tool-{number}", "type": tool}}, 1))
    events.append(event("item/completed", {"item": {"id": f"msg-{number}", "type": "agentMessage", "text": text}}, 2))
    if complete:
        events.append(event("turn/completed", {"status": "completed"}, 3))
    return events


def run_check(tmp_path, events, *args):
    path = tmp_path / "events.json"
    path.write_text(json.dumps(events))
    result = subprocess.run([sys.executable, str(SCRIPT), "--events", str(path),
                             "--thread", "thr_fixture", "--now", NOW,
                             "--health-dir", str(tmp_path / "health"), *args],
                            capture_output=True, text=True, timeout=10)
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)


def test_excess_overhead_really_fails(tmp_path):
    code, report = run_check(tmp_path, sum((turn(n) for n in range(4)), []))
    assert code == 1
    assert report["status"] == "fail"
    assert report["findings"][0]["thread"] == "thr_fixture"
    assert report["findings"][0]["source"] == "nothing-new"
    assert report["findings"][0]["example_turn_ids"] == [f"turn-{n}" for n in range(4)]
    assert not (tmp_path / "health").exists()
    assert report["bead_commands"] == []


@pytest.mark.parametrize("count", [0, 1, 3])
def test_empty_pass_and_boundary(tmp_path, count):
    code, report = run_check(tmp_path, sum((turn(n) for n in range(count)), []))
    assert code == 0
    assert report["status"] == "pass"


def test_configurable_limit(tmp_path):
    code, _ = run_check(tmp_path, turn(1) + turn(2), "--limit", "1")
    assert code == 1


def test_window_excludes_old_and_future_turns(tmp_path):
    events = turn(1, age_hours=25) + turn(2, age_hours=-1)
    events += sum((turn(n) for n in range(3, 6)), [])
    assert run_check(tmp_path, events)[0] == 0


def test_fixed_regression_includes_older_than_one_day(tmp_path):
    state = tmp_path / "fixed.json"
    state.write_text(json.dumps({"sources": {"nothing-new": {"fixed_at": "2026-09-30T00:00:00Z"}}}))
    code, report = run_check(tmp_path, turn(1, age_hours=25), "--state-file", str(state))
    assert code == 1
    assert report["findings"][0]["reason"] == "declared-fixed-regression"
    assert state.read_text() == json.dumps({"sources": {"nothing-new": {"fixed_at": "2026-09-30T00:00:00Z"}}})


def test_source_one_shot_rejects_any_recent_overhead(tmp_path):
    assert run_check(tmp_path, turn(1), "--source", "nothing-new")[0] == 1
    assert run_check(tmp_path, turn(1), "--source", "rotation")[0] == 0


@pytest.mark.parametrize("events", [[{"type": "item/completed"}], [None],
                                    turn(1) + [{"invalid": True}]])
def test_malformed_event_is_not_a_clean_pass(tmp_path, events):
    code, report = run_check(tmp_path, events)
    assert code == 2
    assert report["status"] == "fail"
    assert report["evaluated"] is False
    assert report["errors"]


@pytest.mark.parametrize("tool", ["toolCall", "commandExecution", "fileRead", "webSearch", "delegation", "backgroundTask"])
def test_tool_anywhere_in_turn_disqualifies(tmp_path, tool):
    events = sum((turn(n, tool=tool) for n in range(4)), [])
    assert run_check(tmp_path, events)[0] == 0


@pytest.mark.parametrize("text", ["Nothing new. I chose SQLite for persistence.",
                                 "Confirmed. Tests: 12 passed.",
                                 "Status: delivered scripts/check.py.",
                                 "Nothing new. " + "word " * 60])
def test_decisions_deliverables_and_long_turns_are_not_overhead(tmp_path, text):
    assert run_check(tmp_path, sum((turn(n, text) for n in range(4)), []))[0] == 0


@pytest.mark.parametrize("text,source", [("Still waiting.", "status-only"),
    ("Rotating to a new thread.", "rotation"), ("Goal cleared.", "goal-clear"),
    ("Please set the next goal.", "next-goal"), ("Ok, noted.", "confirm-only")])
def test_fixed_pattern_sources(tmp_path, text, source):
    code, report = run_check(tmp_path, turn(1, text), "--source", source)
    assert code == 1
    assert report["findings"][0]["source"] == source


def test_incomplete_turn_is_not_classified(tmp_path):
    assert run_check(tmp_path, turn(1, complete=False), "--source", "nothing-new")[0] == 0


def test_threshold_counts_across_sources_and_deduplicates_items(tmp_path):
    events = turn(1) + turn(2, "Ok, noted.") + turn(3, "Goal cleared.") + turn(4, "Still waiting.")
    assert run_check(tmp_path, events)[0] == 1
    events = turn(1) * 4
    assert run_check(tmp_path, events)[0] == 0


def test_health_record_and_manual_run_preserves_scheduled_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "fixture")
    code, _ = run_check(tmp_path, sum((turn(n) for n in range(4)), []), "--no-dry-run")
    assert code == 1
    path = tmp_path / "health/overhead-turns.json"
    stored = json.loads(path.read_text())
    assert stored["check"] == "overhead-turns"
    assert stored["status"] == "fail"
    assert stored["evaluated"] is True
    assert stored["interval_seconds"] == 86400
    assert stored["first_failed_at_epoch"] == EPOCH_MS // 1000
    assert stored["run_kind"] == "scheduled"
    monkeypatch.delenv("INVOCATION_ID")
    run_check(tmp_path, [], "--source", "nothing-new", "--no-dry-run")
    updated = json.loads(path.read_text())
    assert {k: updated[k] for k in stored} == stored
    assert updated["last_nonauthoritative"]["status"] == "pass"


def test_dry_run_bead_command_is_printed_not_executed(tmp_path, monkeypatch):
    # Neither bb nor bd can resolve to the live executables in this CLI test.
    monkeypatch.setenv("PATH", str(tmp_path / "no-executables"))
    code, report = run_check(tmp_path, sum((turn(n) for n in range(4)), []), "--file-beads")
    assert code == 1
    assert report["bead_commands"]
    assert "--actor clavain-coord" in report["bead_commands"][0]
    assert "thr_fixture" in report["bead_commands"][0]
    assert not (tmp_path / "health").exists()


def test_live_reader_requests_all_events_only_for_active_threads(monkeypatch):
    spec = importlib.util.spec_from_file_location("overhead_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        if args[1:3] == ["thread", "list"]:
            value = [{"id": "thr_fixture", "archivedAt": None, "status": "idle"},
                     {"id": "thr_archive", "archivedAt": 123, "status": "idle"}]
        else:
            value = turn(1)
        return subprocess.CompletedProcess(args, 0, json.dumps(value), "")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.live_streams("bb")["thr_fixture"] == turn(1)
    assert calls == [["bb", "thread", "list", "--json", "--include-hidden"],
                     ["bb", "thread", "log", "--json", "--all", "--", "thr_fixture"]]


def test_live_reader_rejects_flag_like_thread_id(monkeypatch):
    spec = importlib.util.spec_from_file_location("overhead_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps([{"id": "--output=/tmp/x", "archivedAt": None}]), "")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        module.live_streams("bb")
    assert len(calls) == 1


@pytest.mark.parametrize("text", ["Yes.", "Okay.", "Confirmed.", "Understood.", "Will do.", "Got it."])
def test_short_answers_to_questions_are_not_overhead(tmp_path, text):
    events = []
    for number in range(4):
        answered = turn(number, text)
        answered.insert(1, {**answered[1], "id": f"question-{number}", "seq": number * 10 + 1,
                            "data": {"item": {"id": f"user-{number}", "type": "userMessage",
                                               "text": "Should we use SQLite?"}}})
        events.extend(answered)
    code, report = run_check(tmp_path, events)
    assert code == 0
    assert report["counts"]["thr_fixture"] == 0


@pytest.mark.parametrize("text", ["Ok, noted.", "Okay, noted."])
def test_unambiguous_confirmation_chatter_is_overhead(tmp_path, text):
    code, report = run_check(tmp_path, turn(1, text), "--source", "confirm-only")
    assert code == 1
    assert report["counts"]["thr_fixture"] == 1


def test_mixed_sources_count_turn_once_and_report_every_source(tmp_path):
    code, report = run_check(tmp_path, turn(1, "Nothing new. Goal cleared. Nothing new."),
                             "--limit", "0")
    assert code == 1
    assert report["counts"]["thr_fixture"] == 1
    assert {finding["source"] for finding in report["findings"]} == {"nothing-new", "goal-clear"}
    assert all(finding["example_turn_ids"] == ["turn-1"] for finding in report["findings"])


def test_mixed_sources_detect_declared_fixed_secondary_source(tmp_path):
    state = tmp_path / "fixed.json"
    state.write_text(json.dumps({"sources": {"goal-clear": {"fixed_at": "2026-09-30T00:00:00Z"}}}))
    code, report = run_check(tmp_path, turn(1, "Nothing new. Goal cleared.", age_hours=25),
                             "--state-file", str(state))
    assert code == 1
    assert report["findings"][0]["source"] == "goal-clear"
    assert report["findings"][0]["reason"] == "declared-fixed-regression"


@pytest.mark.parametrize("source", ["nothing-new", "goal-clear"])
def test_mixed_sources_verify_each_source_independently(tmp_path, source):
    code, report = run_check(tmp_path, turn(1, "Nothing new. Goal cleared."), "--source", source)
    assert code == 1
    assert report["counts"]["thr_fixture"] == 1
    assert [finding["source"] for finding in report["findings"]] == [source]


def test_live_reader_includes_hidden_active_children(monkeypatch):
    spec = importlib.util.spec_from_file_location("overhead_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def fake_run(args, **kwargs):
        if args[1:3] == ["thread", "list"]:
            value = [{"id": "thr_fixture", "archivedAt": None, "visibility": "visible"}]
            if "--include-hidden" in args:
                value.extend([{"id": "thr_child", "parentThreadId": "thr_fixture",
                               "archivedAt": None, "visibility": "hidden"},
                              {"id": "thr_archive", "archivedAt": 123, "visibility": "hidden"},
                              {"id": "thr_deleted", "archivedAt": None, "deletedAt": 123,
                               "visibility": "hidden"}])
        else:
            value = [{**event, "threadId": args[-1]} for event in turn(1)]
        return subprocess.CompletedProcess(args, 0, json.dumps(value), "")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    streams = module.live_streams("bb")
    assert set(streams) == {"thr_fixture", "thr_child"}
    findings, counts = module.audit(streams, EPOCH_MS / 1000, 0, {}, None)
    assert counts == {"thr_fixture": 1, "thr_child": 1}
    assert {finding["thread"] for finding in findings} == set(streams)


def test_window_and_fixed_timestamp_boundaries(tmp_path):
    events = turn(1, age_hours=24)
    for event in events:
        event["createdAt"] -= 3  # completion exactly at window start
    assert run_check(tmp_path, events, "--limit", "0")[0] == 0
    events[-1]["createdAt"] += 1
    assert run_check(tmp_path, events, "--limit", "0")[0] == 1
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"sources": {"nothing-new": {"fixed_at": events[-1]["createdAt"]}}}))
    assert run_check(tmp_path, events, "--state-file", str(state))[0] == 0
    events[-1]["createdAt"] += 1
    assert run_check(tmp_path, events, "--state-file", str(state))[0] == 1


@pytest.mark.parametrize("state", [{}, {"sources": []},
    {"sources": {"nothing-new": {"fixed_at": "invalid"}}}])
def test_bad_declaration_cannot_verify_clean(tmp_path, state):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    code, report = run_check(tmp_path, [], "--state-file", str(path))
    assert code == 2
    assert report["evaluated"] is False


def test_conflicting_duplicate_event_is_malformed(tmp_path):
    events = turn(1)
    events.append({**events[1], "data": {"item": {"type": "agentMessage", "id": "msg-1", "text": "Changed."}}})
    assert run_check(tmp_path, events)[0] == 2


def test_missing_scope_kind_is_malformed(tmp_path):
    events = turn(1)
    events[1]["scope"] = {}
    assert run_check(tmp_path, events)[0] == 2


def test_tool_after_message_still_disqualifies(tmp_path):
    events = turn(1)
    events.insert(-1, {**events[1], "id": "late-tool", "seq": 12,
                       "type": "item/started", "data": {"item": {"id": "tool", "type": "toolCall"}}})
    assert run_check(tmp_path, events, "--source", "nothing-new")[0] == 0


def test_dry_run_never_overwrites_existing_health(tmp_path):
    health = tmp_path / "health"
    health.mkdir()
    path = health / "overhead-turns.json"
    path.write_text("existing health bytes")
    run_check(tmp_path, [], "--dry-run")
    assert path.read_text() == "existing health bytes"


def test_invalid_stream_writes_unevaluated_health_only_in_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "fixture")
    code, _ = run_check(tmp_path, [None], "--no-dry-run")
    assert code == 2
    health = json.loads((tmp_path / "health/overhead-turns.json").read_text())
    assert health["status"] == "fail"
    assert health["evaluated"] is False
    assert health["summary"].startswith("NOT EVALUATED:")
