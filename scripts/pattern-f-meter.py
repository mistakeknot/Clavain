#!/usr/bin/env python3
"""pattern-f-meter.py — what a Pattern F run cost the main thread.

An orchestrate.py --pattern-f run writes <run dir>/meter.json: the register
session id, the run window, and one entry per dispatch (item, role, model,
window). This script prices the run through interstat's profile.py in three
explicit slices of that window: the orchestrating session (--session <id>),
the claude seats (transcripts whose project path carries the run's worktree,
orchestrate-runs-<run>), and the codex seats (session files that name the
run's worktree, orchestrate-runs/<run>). Seats are never derived by
subtraction: other sessions run on this machine at the same time, so the
window total is printed only as context. It also prints the orchestrating
session's turn count inside the window (distinct assistant message ids in
its transcript, and how many of those carried tool calls).

Shares are reported beside the dollars, never alone: the doctrine gates on
absolutes (commands/model-routing.md).

Usage:
  pattern-f-meter.py <run dir | meter.json> [--interstat DIR] [--json]
      [--seat-path-fragment F ...] [--seat-content-fragment F ...]

The fragment options override the run-id defaults, so a hand-driven goal can
be metered the same way from a synthetic meter.json (for example
--seat-path-fragment Sylveste-os-Clavain --seat-content-fragment
Sylveste/os/Clavain). profile.py is taken from --interstat, then
$INTERSTAT_DIR, then the newest interstat in the plugin cache, then
~/projects/Sylveste/interverse/interstat.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _version_key(path: str) -> list:
    return [int(x) if x.isdigit() else x for x in Path(path).parts[-3].split(".")]


def find_profile(explicit: str | None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(os.path.join(explicit, "scripts", "profile.py"))
    env = os.environ.get("INTERSTAT_DIR")
    if env:
        candidates.append(os.path.join(env, "scripts", "profile.py"))
    cache = glob.glob(os.path.expanduser("~/.claude/plugins/cache/*/interstat/*/scripts/profile.py"))
    candidates.extend(sorted(cache, key=_version_key, reverse=True))
    candidates.append(os.path.expanduser("~/projects/Sylveste/interverse/interstat/scripts/profile.py"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def profile(profile_py: str, since: str, until: str, session: str | None) -> dict:
    cmd = [sys.executable, profile_py, "--since", since, "--until", until, "--json"]
    if session:
        cmd += ["--session", session]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise SystemExit(f"pattern-f-meter: profile.py failed rc={p.returncode}: {(p.stderr or p.stdout).strip()[-400:]}")
    return json.loads(p.stdout)


def lane_costs(report: dict) -> tuple[dict[str, float], int]:
    out: dict[str, float] = {}
    unpriced = 0
    for row in report.get("rows", []):
        if row.get("cost") is None:
            unpriced += int(row.get("msgs", 0) or 0)
            continue
        out[row["lane"]] = out.get(row["lane"], 0.0) + float(row["cost"])
    return out, unpriced


def parse_ts(value: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def turns(session: str, since: dt.datetime, until: dt.datetime) -> dict:
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session}.jsonl"))
    ids: set[str] = set()
    tool_ids: set[str] = set()
    for path in paths:
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                t = parse_ts(rec.get("timestamp") or "")
                if t is None or t < since or t > until:
                    continue
                msg = rec.get("message") or {}
                mid = msg.get("id") or rec.get("uuid")
                if not mid:
                    continue
                ids.add(mid)
                content = msg.get("content")
                if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_use" for b in content
                ):
                    tool_ids.add(mid)
    return {"transcripts": paths, "turns": len(ids), "tool_turns": len(tool_ids)}


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def codex_sessions_mentioning(fragments: list[str], since: dt.datetime) -> list[str]:
    """Codex session ids whose rollout file (modified at or after the window
    start) names one of the fragments: the run's worktree path shows up in
    the session_meta record at the top of the file."""
    root = os.path.expanduser("~/.codex/sessions")
    found: list[str] = []
    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        try:
            if dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc) < since:
                continue
            with open(path, errors="replace") as f:
                head = f.read(200_000)
        except OSError:
            continue
        if any(frag in head for frag in fragments):
            m = _UUID.search(os.path.basename(path))
            found.append(m.group(0) if m else os.path.basename(path)[:-6])
    return sorted(set(found))


def claude_seat_sessions(fragments: list[str], since: dt.datetime) -> list[str]:
    """Session ids of claude transcripts whose project directory (the seat's
    cwd, slugified) carries a fragment and that were written at or after the
    window start. profile.py --session matches the file name, so the seat
    must be named by its id, not by its directory."""
    root = os.path.expanduser("~/.claude/projects")
    ids: list[str] = []
    for d in glob.glob(os.path.join(root, "*")):
        if not any(frag in os.path.basename(d) for frag in fragments):
            continue
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            try:
                if dt.datetime.fromtimestamp(os.path.getmtime(f), dt.timezone.utc) < since:
                    continue
            except OSError:
                continue
            ids.append(os.path.basename(f)[:-6])
    return sorted(set(ids))


def total_cost(report: dict) -> float:
    return sum(float(r["cost"]) for r in report.get("rows", []) if r.get("cost") is not None)


def main() -> int:
    ap = argparse.ArgumentParser(description="main-thread dollars, seat dollars, share and turns for a Pattern F run")
    ap.add_argument("target", help="run dir or meter.json")
    ap.add_argument("--interstat", help="interstat checkout (scripts/profile.py under it)")
    ap.add_argument("--seat-path-fragment", action="append", default=[],
                    help="claude seats: fragment of the transcript's project directory (default orchestrate-runs-<run>)")
    ap.add_argument("--seat-content-fragment", action="append", default=[],
                    help="codex seat sessions: content fragment (default orchestrate-runs/<run>)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    meter_path = args.target if args.target.endswith(".json") else os.path.join(args.target, "meter.json")
    with open(meter_path) as f:
        meter = json.load(f)
    profile_py = find_profile(args.interstat)
    if not profile_py:
        print("pattern-f-meter: interstat profile.py not found", file=sys.stderr)
        return 2
    since, until, session = meter["started"], meter["finished"], meter["session"]
    run_id = str(meter.get("run") or "")
    path_frags = args.seat_path_fragment or [f"orchestrate-runs-{run_id}"]
    content_frags = args.seat_content_fragment or [f"orchestrate-runs/{run_id}"]

    everything = profile(profile_py, since, until, None)
    main_only = profile(profile_py, since, until, session)
    claude_ids = claude_seat_sessions(path_frags, parse_ts(since))
    claude_seats = {sid: total_cost(profile(profile_py, since, until, sid)) for sid in claude_ids}
    codex_ids = codex_sessions_mentioning(content_frags, parse_ts(since))
    codex_seats = {sid: total_cost(profile(profile_py, since, until, sid)) for sid in codex_ids}

    main_cost = total_cost(main_only)
    seats = sum(claude_seats.values()) + sum(codex_seats.values())
    run_total = main_cost + seats
    share = (main_cost / run_total) if run_total else None
    machine_total = total_cost(everything)
    _lanes, all_unpriced = lane_costs(everything)
    _lanes_main, main_unpriced = lane_costs(main_only)
    t = turns(session, parse_ts(since), parse_ts(until))
    result = {
        "run": run_id, "goal": meter.get("goal"), "session": session,
        "window": {"since": since, "until": until},
        "profile_py": profile_py,
        "main_thread_usd": round(main_cost, 2),
        "seats_usd": round(seats, 2),
        "claude_seats_usd": {k: round(v, 2) for k, v in claude_seats.items()},
        "codex_seats_usd": {k: round(v, 2) for k, v in codex_seats.items()},
        "run_total_usd": round(run_total, 2),
        "main_thread_share_of_run": (round(share, 3) if share is not None else None),
        "machine_window_usd": round(machine_total, 2),
        "main_thread_share_of_machine_window": (round(main_cost / machine_total, 3) if machine_total else None),
        "unpriced_msgs": {"window": all_unpriced, "main": main_unpriced},
        "files_scanned": (everything.get("summary") or {}).get("files_scanned"),
        "orchestrator_turns": t["turns"],
        "orchestrator_tool_turns": t["tool_turns"],
        "transcripts": t["transcripts"],
        "dispatches": meter.get("dispatches", []),
    }
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"# Pattern F meter: run {run_id} (goal {result['goal']}), session {session}")
    print(f"window: {since} .. {until}")
    print(
        f"main thread ${result['main_thread_usd']} | seats ${result['seats_usd']} "
        f"(claude {result['claude_seats_usd']}, codex {result['codex_seats_usd']}) | "
        f"run total ${result['run_total_usd']} | main-thread share of the run {result['main_thread_share_of_run']}"
    )
    print(f"orchestrating session turns in the window: {t['turns']} (with tool calls: {t['tool_turns']})")
    for d in result["dispatches"]:
        print(
            f"  dispatch {d.get('item')} {d.get('role')} model={d.get('model')} "
            f"{d.get('started')} .. {d.get('finished')} rc={d.get('rc')} timed_out={d.get('timed_out')}"
        )
    print(
        f"context: everything on this machine in the window ${result['machine_window_usd']} "
        f"(main thread {result['main_thread_share_of_machine_window']} of it; files scanned "
        f"{result['files_scanned']}; unpriced messages {all_unpriced})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
