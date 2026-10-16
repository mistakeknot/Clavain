"""Burn decomposition, Codex token counts and the hourly burn watch, on synthetic logs."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
DECOMPOSE = ROOT / "scripts/burn-decompose.py"
CODEX = ROOT / "scripts/codex-burn.py"
WATCH = ROOT / "scripts/burn-watch.py"
WORKSPACE = "-home-u--bb-machines-host-data-workspaces-thr-ay39nh2cpv"


def claude_line(msg, ts, model="claude-sonnet-5-5", sidechain=False, ttl_1h=0, **usage):
    if ttl_1h:
        usage["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": ttl_1h}
    return json.dumps(dict(type="assistant", requestId=f"r-{msg}", timestamp=ts, isSidechain=sidechain,
                           message=dict(id=msg, model=model, usage=usage)))


def codex_lines(cwd, model, *calls, originator="codex_exec"):
    lines = [json.dumps(dict(type="session_meta", timestamp=calls[0][0], payload=dict(originator=originator, cwd=cwd))),
             json.dumps(dict(type="turn_context", timestamp=calls[0][0], payload=dict(model=model)))]
    total = 0
    for ts, inp, cached, out in calls:
        total += inp
        lines.append(json.dumps(dict(type="event_msg", timestamp=ts, payload=dict(type="token_count", info=dict(
            total_token_usage=dict(input_tokens=total),
            last_token_usage=dict(input_tokens=inp, cached_input_tokens=cached, output_tokens=out,
                                  reasoning_output_tokens=0))))))
    return lines


def write(root, rel, *lines):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def run_json(script, *args):
    r = subprocess.run([sys.executable, str(script), "--json", *args], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_decompose_classes_roles_and_shares(tmp_path):
    write(tmp_path, f"{WORKSPACE}/main.jsonl",
          claude_line("m1", "2026-10-16T10:00:00Z", model="claude-opus-5-5", cache_creation_input_tokens=1000, ttl_1h=1000),
          claude_line("m2", "2026-10-16T10:01:00Z", model="claude-opus-5-5", cache_creation_input_tokens=100,
                      cache_read_input_tokens=120_000),
          claude_line("m3", "2026-10-16T10:20:00Z", model="claude-opus-5-5", cache_creation_input_tokens=400))
    write(tmp_path, f"{WORKSPACE}/main/subagents/a.jsonl",
          claude_line("m4", "2026-10-16T10:05:00Z", output_tokens=100))
    data = run_json(DECOMPOSE, "--root", str(tmp_path), "--since", "2026-10-16T10:00Z", "--until", "2026-10-16T11:00Z")
    assert data["calls"] == 4
    assert data["by_class"]["session_start_write"] == 1250 + 0  # m1, plus m4 opening its own transcript with no write
    assert data["by_class"]["incremental_write"] == 125
    assert data["by_class"]["cold_rewrite"] == 500
    assert data["by_class"]["read"] == 12_000
    assert data["cache_write_ttl_tokens"] == {"5m": 0, "1h": 1000}
    # Main sessions are all Opus; the subagent's 500 output weight is not main.
    assert data["main_opus_share"] == 1.0
    assert data["by_model_role"]["sonnet-5-5 sub"] == 500
    # Only m2 (120k read + 100 write) sits above 100k context.
    assert data["large_context_share"] == round(12_125 / data["weighted_total"], 4)
    assert data["by_hour"] == {"2026-10-16T10:00Z": data["weighted_total"]}
    assert data["by_lineage"][0]["lineage"] == "thr_ay39nh2cpv" and data["by_lineage"][0]["sessions"] == 2


def test_codex_report_groups_and_window(tmp_path):
    write(tmp_path, "2026/10/16/a.jsonl", *codex_lines(
        "/x/host-data/worktrees/thr_vn99e647a6-1/repo", "gpt-6.1-sol",
        ("2026-10-16T10:00:00Z", 1000, 900, 10), ("2026-10-16T10:30:00Z", 2000, 1800, 20),
        ("2026-10-16T12:00:00Z", 5000, 0, 0), originator="bb"))
    write(tmp_path, "2026/10/16/b.jsonl", *codex_lines(
        "/x/projects/Clavain", "gpt-6-astra", ("2026-10-16T10:10:00Z", 3000, 0, 5)))
    data = run_json(CODEX, "--root", str(tmp_path), "--since", "2026-10-16T10:00Z", "--until", "2026-10-16T11:00Z")
    assert data["sessions"] == 2
    assert data["totals"]["input_tokens"] == 6000 and data["totals"]["cached_input_tokens"] == 2700
    assert data["models"] == {"gpt-6.1-sol": 2, "gpt-6-astra": 1}
    assert {r["lineage"]: r["input_tokens"] for r in data["by_lineage"]} == {"thr_vn99e647a6": 3000, "Clavain": 3000}
    assert {r["originator"]: r["sessions"] for r in data["by_originator"]} == {"bb": 1, "codex_exec": 1}
    assert data["median_session_input"] == 3000


FAKE_BB = """#!/bin/sh
echo "$@" >> "{log}"
if [ "$1 $2" = "thread list" ]; then cat "{threads}"; exit 0; fi
if [ "$1 $2" = "thread tell" ]; then cp "$7" "{log}.msg"; exit {tell_exit}; fi
exit 9
"""


def watch_env(tmp_path, config, threads=None, tell_exit=0):
    claude, codex, state = tmp_path / "claude", tmp_path / "codex", tmp_path / "state"
    claude.mkdir(exist_ok=True)
    codex.mkdir(exist_ok=True)
    log = tmp_path / "bb.log"
    threads_file = tmp_path / "threads.json"
    threads_file.write_text(json.dumps(threads if threads is not None else [
        {"id": "thr_steward001", "title": "#Token-Efficiency | steward", "archivedAt": None},
        {"id": "thr_oldsteward", "title": "#Token-Efficiency", "archivedAt": 1790525542395},
    ]))
    bb = tmp_path / "bb"
    bb.write_text(FAKE_BB.format(log=log, threads=threads_file, tell_exit=tell_exit))
    bb.chmod(0o755)
    config = {"alert": {"thread_title_prefix": "#Token-Efficiency", "bb": str(bb)}, **config}
    (tmp_path / "config.json").write_text(json.dumps(config))
    return claude, codex, state, log


def watch(tmp_path, claude, codex, state, now="2026-10-16T12:05:00Z", *extra):
    return subprocess.run([sys.executable, str(WATCH), "--config", str(tmp_path / "config.json"),
                           "--state-dir", str(state), "--claude-root", str(claude), "--codex-root", str(codex),
                           "--now", now, *extra], capture_output=True, text=True)


def busy_hours(claude):
    # 2M weighted output in each of 10:00 and 11:00.
    write(claude, f"{WORKSPACE}/s.jsonl",
          claude_line("h1", "2026-10-16T10:10:00Z", output_tokens=400_000),
          claude_line("h2", "2026-10-16T11:10:00Z", output_tokens=400_000))


def test_quiet_hour_sends_nothing_and_writes_snapshot(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 5_000_000, "retired_models": ["opus-4-7"]})
    busy_hours(claude)
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0, r.stderr
    assert "0 breach(es)" in r.stdout
    assert not log.exists()
    snap = json.loads((state / "snapshots/2026-10-16T1200Z.json").read_text())
    assert snap["breaches"] == [] and snap["claude"]["weighted_total"] == 4_000_000


def test_breach_messages_the_unarchived_steward_once(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000, "realert_hours": 6})
    busy_hours(claude)
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0, r.stderr
    calls = log.read_text().splitlines()
    assert calls[-1].startswith("thread tell thr_steward001 --mode auto --message-file")
    body = Path(f"{log}.msg").read_text()
    assert "above 1.0M/h for 2 hours: 10:00Z 2.0M, 11:00Z 2.0M" in body
    # The next hour, the same breach is inside the re-alert period: no second message.
    write(claude, f"{WORKSPACE}/t.jsonl", claude_line("h3", "2026-10-16T12:10:00Z", output_tokens=400_000))
    r = watch(tmp_path, claude, codex, state, "2026-10-16T13:05:00Z")
    assert r.returncode == 0 and "0 alerted" in r.stdout
    assert len([c for c in log.read_text().splitlines() if c.startswith("thread tell")]) == 1


def test_one_quiet_hour_in_the_run_is_not_a_breach(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    write(claude, f"{WORKSPACE}/s.jsonl", claude_line("h2", "2026-10-16T11:10:00Z", output_tokens=400_000))
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0 and "0 breach(es)" in r.stdout and not log.exists()


def test_retired_codex_model_and_share_floor(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"retired_models": ["gpt-5.6-sol"], "main_opus_share_max": 0.1,
                                                     "share_min_weighted": 10_000_000})
    write(claude, f"{WORKSPACE}/s.jsonl", claude_line("o1", "2026-10-16T11:00:00Z", model="claude-opus-5-5", output_tokens=10))
    write(codex, "2026/10/16/a.jsonl", *codex_lines("/x/projects/p", "gpt-5.6-sol", ("2026-10-16T11:30:00Z", 10, 0, 1)))
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0, r.stderr
    body = Path(f"{log}.msg").read_text()
    assert "retired model gpt-5.6-sol" in body
    # The Opus share is 100% but the window burned far below the floor, so it is not a breach.
    assert "Opus share" not in body.split("\n\n")[1]


def test_dry_run_prints_and_writes_nothing(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000, "keep_days": 1})
    busy_hours(claude)
    r = watch(tmp_path, claude, codex, state, "2026-10-16T12:05:00Z", "--dry-run")
    assert r.returncode == 0 and "Burn watch: 1 threshold breach" in r.stdout and "1 would alert" in r.stdout
    assert not log.exists() and not state.exists()
    # After a real alert, a dry run in the same hour leaves its evidence alone and prunes nothing.
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0 and "1 alerted" in r.stdout
    old = state / "snapshots/2026-10-01T0000Z.json"
    old.write_text("{}")
    before = {p.name: p.read_bytes() for p in state.rglob("*") if p.is_file()}
    r = watch(tmp_path, claude, codex, state, "2026-10-16T12:30:00Z", "--dry-run")
    assert r.returncode == 0 and "0 would alert" in r.stdout
    assert {p.name: p.read_bytes() for p in state.rglob("*") if p.is_file()} == before


def test_cannot_assess_cases(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000, "hourly_burn_maxx": 1})
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 2 and "unknown keys: hourly_burn_maxx" in r.stderr
    # Two live threads match the prefix: refuse to guess, keep the breach unsent so it retries next hour.
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000}, threads=[
        {"id": "thr_a000000001", "title": "#Token-Efficiency | steward", "archivedAt": None},
        {"id": "thr_b000000002", "title": "#Token-Efficiency | steward 2", "archivedAt": None}])
    busy_hours(claude)
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 2 and "found 2" in r.stderr
    assert not (state / "alerted.json").exists()
    snap = json.loads((state / "snapshots/2026-10-16T1200Z.json").read_text())
    assert snap["alerted"] == [] and "found 2" in snap["alert_error"]
    # A failed send also stays unrecorded, and the next run delivers it.
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000}, tell_exit=1)
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 2 and not (state / "alerted.json").exists()
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    r = watch(tmp_path, claude, codex, state, "2026-10-16T12:20:00Z")
    assert r.returncode == 0 and "1 alerted" in r.stdout
    assert set(json.loads((state / "alerted.json").read_text())) == {"hourly_burn"}


def test_audit_command_findings_and_failure(tmp_path):
    audit = tmp_path / "audit.sh"
    audit.write_text("#!/bin/sh\necho 'thr_x spawned on opus without a receipt'\nexit 1\n")
    audit.chmod(0o755)
    claude, codex, state, log = watch_env(tmp_path, {"audit_command": [str(audit)]})
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0, r.stderr
    assert "thr_x spawned on opus without a receipt" in Path(f"{log}.msg").read_text()
    audit.write_text("#!/bin/sh\nexit 4\n")
    r = watch(tmp_path, claude, codex, tmp_path / "state2")
    assert r.returncode == 2 and "audit command exited 4" in r.stderr


def test_decompose_edges(tmp_path):
    write(tmp_path, f"{WORKSPACE}/main.jsonl",
          # Before the window: not counted, but it is the previous call for the 10:01 write.
          claude_line("p0", "2026-10-16T09:59:00Z", cache_creation_input_tokens=50),
          claude_line("e1", "2026-10-16T10:00:00Z", cache_read_input_tokens=100_000),
          claude_line("e1", "2026-10-16T10:00:00Z", cache_read_input_tokens=100_000, output_tokens=7),
          claude_line("e2", "2026-10-16T10:01:00Z", cache_creation_input_tokens=80),
          claude_line("e3", "2026-10-16T11:00:00Z", output_tokens=1000))
    write(tmp_path, f"{WORKSPACE}/bad.jsonl",
          json.dumps(dict(type="assistant", requestId="r-b", timestamp="2026-10-16T10:30:00Z", message=dict(
              id="b", model="claude-sonnet-5-5", usage=dict(output_tokens="9", cache_creation="bad")))))
    data = run_json(DECOMPOSE, "--root", str(tmp_path), "--since", "2026-10-16T10:00Z", "--until", "2026-10-16T11:00Z")
    # e1 streamed twice counts once at its largest values; e3 at the window end is out; the
    # malformed call counts with zero tokens.
    assert data["calls"] == 3 and data["unreadable"] == []
    assert data["by_class"]["output"] == 35
    assert data["by_class"]["incremental_write"] == 100 and data["by_class"].get("session_start_write", 0) == 0
    # Exactly 100k context counts as large.
    assert data["large_context_share"] == round(10_035 / data["weighted_total"], 4)


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads files whatever their mode")
def test_unreadable_transcript_is_not_a_quiet_hour(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    busy_hours(claude)
    locked = claude / f"{WORKSPACE}/s.jsonl"
    locked.chmod(0)
    try:
        r = watch(tmp_path, claude, codex, state)
        assert r.returncode == 2 and "unreadable" in r.stderr
        r = subprocess.run([sys.executable, str(DECOMPOSE), "--root", str(claude), "--since", "2026-10-16T10:00Z",
                            "--until", "2026-10-16T12:00Z"], capture_output=True, text=True)
        assert r.returncode == 2 and "unreadable transcript" in r.stderr
    finally:
        locked.chmod(0o644)
    assert not log.exists() and not (state / "snapshots").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root lists directories whatever their mode")
def test_unlistable_directory_is_not_a_quiet_hour(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    busy_hours(claude)
    write(codex, "2026/10/16/a.jsonl", *codex_lines("/p", "gpt-6.1-sol", ("2026-10-16T10:30:00Z", 10, 0, 1)))
    hidden = [claude / WORKSPACE, codex / "2026"]
    for directory in hidden:
        directory.chmod(0)
    try:
        r = watch(tmp_path, claude, codex, state)
        assert r.returncode == 2 and "unreadable" in r.stderr, r.stderr
        for script, root, text in ((DECOMPOSE, claude, "unreadable transcript"), (CODEX, codex, "unreadable session log")):
            r = subprocess.run([sys.executable, str(script), "--root", str(root), "--since", "2026-10-16T10:00Z",
                                "--until", "2026-10-16T12:00Z"], capture_output=True, text=True)
            assert r.returncode == 2 and text in r.stderr, r.stderr
    finally:
        for directory in hidden:
            directory.chmod(0o755)
    assert not log.exists() and not (state / "snapshots").exists()


def test_codex_repeated_snapshot_counts_once(tmp_path):
    usage = dict(input_tokens=1000, cached_input_tokens=0, output_tokens=1, reasoning_output_tokens=0)
    event = lambda ts: json.dumps(dict(type="event_msg", timestamp=ts, payload=dict(type="token_count", info=dict(
        total_token_usage=dict(input_tokens=1000), last_token_usage=usage))))
    write(tmp_path, "2026/10/16/a.jsonl",
          json.dumps(dict(type="session_meta", timestamp="2026-10-16T10:00:00Z", payload=dict(originator="x", cwd="/p"))),
          json.dumps(dict(type="turn_context", timestamp="2026-10-16T10:00:00Z", payload=dict(model="gpt-6.1-sol"))),
          event("2026-10-16T10:01:00Z"),
          json.dumps(dict(type="turn_context", timestamp="2026-10-16T10:02:00Z", payload=dict(model="gpt-5.6-sol"))),
          event("2026-10-16T10:02:00Z"))
    data = run_json(CODEX, "--root", str(tmp_path), "--since", "2026-10-16T10:00Z", "--until", "2026-10-16T11:00Z")
    assert data["totals"]["input_tokens"] == 1000 and data["models"] == {"gpt-6.1-sol": 1}


@pytest.mark.parametrize("bad, text", [
    ({"consecutive_hours": "2"}, "consecutive_hours must be a whole number"),
    ({"consecutive_hours": 0}, "consecutive_hours must be a whole number"),
    ({"realert_hours": -1}, "realert_hours must be a positive number"),
    ({"retired_models": "opus"}, "retired_models must be a list"),
    ({"main_opus_share_max": 50}, "main_opus_share_max must be a share"),
    ({"alert": {"thread_title_prefix": "", "bb": "bb"}}, "alert.thread_title_prefix must be"),
    ({"alert": {"thread_title_prefx": "x"}}, "alert has unknown keys: thread_title_prefx"),
    ({"window_hours": None}, "window_hours must be a whole number"),
    ({"retired_models": None}, "retired_models must be a list"),
    ({"share_min_weighted": None}, "share_min_weighted must be a number"),
    ({"realert_hours": None}, "realert_hours must be a positive number"),
    ({"keep_days": None}, "keep_days must be a positive number"),
])
def test_bad_config_values_cannot_assess(tmp_path, bad, text):
    claude, codex, state, log = watch_env(tmp_path, {})
    config = json.loads((tmp_path / "config.json").read_text())
    (tmp_path / "config.json").write_text(json.dumps({**config, **bad}))
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 2 and text in r.stderr, r.stderr


def test_null_threshold_is_off(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": None, "main_opus_share_max": None,
                                                     "audit_command": None, "alert": None})
    busy_hours(claude)
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0 and not log.exists(), r.stderr


@pytest.mark.parametrize("stored", ["not json", "[]", '{"hourly_burn": "2026-10-16T11:00:00"}', '{"hourly_burn": 5}'])
def test_damaged_alert_state_cannot_assess(tmp_path, stored):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    busy_hours(claude)
    state.mkdir()
    (state / "alerted.json").write_text(stored)
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 2 and "alert state" in r.stderr
    assert not log.exists() and (state / "alerted.json").read_text() == stored


def test_future_alert_time_does_not_silence(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    busy_hours(claude)
    state.mkdir()
    (state / "alerted.json").write_text(json.dumps({"hourly_burn": "2099-01-01T00:00:00+00:00"}))
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0 and "1 alerted" in r.stdout
    assert json.loads((state / "alerted.json").read_text())["hourly_burn"].startswith("2026-10-16T12:05")


def test_second_run_refuses_while_the_lock_is_held(tmp_path):
    claude, codex, state, log = watch_env(tmp_path, {"hourly_burn_max": 1_000_000})
    busy_hours(claude)
    state.mkdir()
    with open(state / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 2 and "another burn-watch run" in r.stderr and not log.exists()
    r = watch(tmp_path, claude, codex, state)
    assert r.returncode == 0 and "1 alerted" in r.stdout
