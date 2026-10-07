#!/usr/bin/env python3
"""Deterministic, read-only BB overhead audit (spec #6).

Defaults to --dry-run: prints JSON, writes nothing. --no-dry-run publishes
overhead-turns.json only under --health-dir; --file-beads additionally opts into
bd create. Exit 0 = pass, 1 = detected overhead, 2 = incomplete/invalid evidence
or reporting failure. Active means unarchived and undeleted, including idle.

BB raw envelopes were checked against installed CLI help/source and the local
bb.db events schema: scope={kind:turn,turnId}, millisecond createdAt,
item/completed data.item={id,type:agentMessage,text}, turn/completed.
CLI discovery was sandbox-blocked during implementation; --all is essential
because thread log defaults to the oldest 100 events. Provider-event artifacts
in thread-storage are dispatch transcripts, not authoritative BB thread logs.

Offline: --events FILE accepts the bare array returned by bb thread log --json
--all (multiple threadIds allowed); --thread supplies the id for an empty array.
--now accepts an ISO-8601 UTC time. The window is (now-24h, now].
State is read-only JSON: {"sources":{"rotation":{"fixed_at":"...Z"}}}.
Source names are fixed pattern classes below; no title-based attribution guesses.
Declared-fixed regressions examine all available history after fixed_at.
--source CLASS verifies zero occurrences of that class in the last day, plus
its declared-fixed history. It never marks a source fixed automatically.
"""

import argparse
import json
import math
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PATTERNS = {
    "nothing-new": r"(?:nothing new|no (?:new )?(?:updates?|changes?|news)|no change)(?: (?:to report|yet|since last (?:check|update)))?",
    "rotation": r"(?:(?:rotating|switching|moving)(?: (?:over|now))? to (?:a |the )?(?:new |next )?thread|(?:thread |coordinator )?rotation(?: notice| complete)?|handing off to (?:a |the )?(?:new |next )?thread)",
    "goal-clear": r"(?:(?:the |current )?goal (?:is )?clear(?:ed)?|cleared (?:the |current )?goal)",
    "next-goal": r"(?:please (?:set|provide) (?:the |a )?next goal|(?:waiting|ready) for (?:the |a )?next goal|next goal (?:needed|required))",
    # Bare acknowledgements can answer a substantive question. Restrict this
    # class to explicit status chatter rather than guessing missing context.
    "confirm-only": r"(?:ok(?:ay)?,? noted)",
    "status-only": r"(?:(?:still )?(?:waiting|monitoring|standing by)|(?:status: )?(?:idle|unchanged|no action needed)|(?:work |task )?(?:is )?in progress|(?:continuing|working on it))",
}
PATTERNS = {key: re.compile(value, re.I) for key, value in PATTERNS.items()}
NON_TOOL_ITEMS = {"agentMessage", "reasoning", "userMessage", "contextCompaction"}


def timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValueError("non-finite timestamp")
        return value / 1000  # BB epoch milliseconds, never guessed seconds
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timestamp requires a timezone")
        return dt.timestamp()
    raise ValueError("invalid timestamp")


def classify(text):
    if not text or len(text.split()) >= 60:
        return None
    # Full matches for every sentence: a prefix such as 'Confirmed. I chose...'
    # must not hide a decision or deliverable. No arbitrary wildcard suffixes.
    phrases = [s.strip().strip(".! ") for s in re.split(r"[.!;\n]+", text) if s.strip()]
    sources = []
    for phrase in phrases:
        matched = [key for key, regex in PATTERNS.items() if regex.fullmatch(phrase)]
        if not matched:
            return None
        sources.extend(matched)
    # Preserve every source, deduplicated in phrase order; still one turn.
    return list(dict.fromkeys(sources)) or None


def assistant_turns(events, thread):
    if not isinstance(events, list):
        raise ValueError("event stream must be a bare array")
    turns = {}
    seen = {}
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        for key in ("id", "type", "threadId"):
            if not isinstance(event.get(key), str) or not event[key]:
                raise ValueError("event missing " + key)
        if event["threadId"] != thread:
            raise ValueError("event threadId mismatch")
        if not isinstance(event.get("seq"), int) or isinstance(event["seq"], bool):
            raise ValueError("event missing seq")
        when = timestamp(event.get("createdAt"))
        scope, data = event.get("scope"), event.get("data")
        if not isinstance(scope, dict) or not isinstance(data, dict):
            raise ValueError("event missing scope/data")
        if not isinstance(scope.get("kind"), str) or not scope["kind"]:
            raise ValueError("event scope missing kind")
        if event["id"] in seen:
            if seen[event["id"]] != event:
                raise ValueError("conflicting duplicate event: " + event["id"])
            continue
        seen[event["id"]] = event
        if scope.get("kind") != "turn":
            continue
        turn_id = scope.get("turnId")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("turn scope missing turnId")
        turn = turns.setdefault(turn_id, {"id": turn_id, "messages": {}, "tool": False,
                                          "completed_at": None})
        kind = event["type"]
        if kind in ("item/started", "item/completed"):
            item = data.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not item.get("id"):
                raise ValueError("item event missing item id/type")
            if item["type"] not in NON_TOOL_ITEMS:
                # Unknown item types are conservatively disqualifying too.
                turn["tool"] = True
            if kind == "item/completed" and item["type"] == "agentMessage":
                if not isinstance(item.get("text"), str):
                    raise ValueError("agentMessage missing text")
                turn["messages"][item["id"]] = (event["seq"], item["text"])
        elif kind == "turn/completed":
            if data.get("status") == "completed":
                turn["completed_at"] = when
    results = []
    for turn in turns.values():
        if turn["tool"] or turn["completed_at"] is None:
            continue
        text = "\n".join(text for _, text in sorted(turn["messages"].values()))
        sources = classify(text)
        if sources:
            results.append({"turn_id": turn["id"], "sources": sources, "at": turn["completed_at"]})
    return sorted(results, key=lambda row: (row["at"], row["turn_id"]))


THREAD_ID = re.compile(r"thr_[A-Za-z0-9]+")


def read_json_command(args):
    proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if proc.returncode:
        raise ValueError(f"{shlex.join(args)} failed: {proc.stderr.strip()}")
    value = json.loads(proc.stdout)
    if not isinstance(value, list):
        raise ValueError(f"{shlex.join(args)} did not return a bare array")
    return value


def live_streams(bb):
    threads = read_json_command([bb, "thread", "list", "--json", "--include-hidden"])
    streams = {}
    for thread in threads:
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str) or "archivedAt" not in thread:
            raise ValueError("invalid thread list entry")
        if not THREAD_ID.fullmatch(thread["id"]):
            raise ValueError("invalid thread id: " + repr(thread["id"]))
        if thread["archivedAt"] is None and thread.get("deletedAt") is None:
            streams[thread["id"]] = read_json_command([bb, "thread", "log", "--json", "--all", "--", thread["id"]])
    return streams


def fixed_sources(path, explicit):
    if not path.exists() and not explicit:
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("sources"), dict):
        raise ValueError("state requires a sources object")
    result = {}
    for source, record in value["sources"].items():
        if source not in PATTERNS or not isinstance(record, dict) or "fixed_at" not in record:
            raise ValueError("invalid fixed source: " + source)
        result[source] = timestamp(record["fixed_at"])
    return result


def audit(streams, now, limit, fixed, source):
    findings, counts = [], {}
    for thread, events in streams.items():
        turns = [turn for turn in assistant_turns(events, thread)
                 if turn["at"] <= now and (source is None or source in turn["sources"])]
        recent = [turn for turn in turns if now - 86400 < turn["at"] <= now]
        counts[thread] = len(recent)
        selected = {}
        for turn in turns:
            for name in turn["sources"]:
                if (source is None or name == source) and name in fixed and turn["at"] > fixed[name]:
                    selected.setdefault((name, "declared-fixed-regression"), []).append(turn["turn_id"])
        if len(recent) > limit or (source is not None and recent):
            reason = "source-verification" if source else "daily-limit"
            for turn in recent:
                for name in turn["sources"]:
                    if source is None or name == source:
                        selected.setdefault((name, reason), []).append(turn["turn_id"])
        for (name, reason), ids in selected.items():
            findings.append({"thread": thread, "source": name, "reason": reason,
                             "overhead_turns_24h": len(recent), "example_turn_ids": ids[:10]})
    return findings, counts


def write_health(directory, report, now, source):
    """Match rig-health-write.py schema and protect scheduled fields on one-shots."""
    path = directory / "overhead-turns.json"
    stored = None
    if path.exists():
        try:
            stored = json.loads(path.read_text())
        except ValueError:
            pass
    kind = "manual" if source else (
        os.environ.get("RIG_RUN_KIND") or ("scheduled" if os.environ.get("INVOCATION_ID") else
        "session" if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_SESSION_ID") else
        "remote" if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT") else "manual"))
    if kind == "dry":
        return
    first_failed = None
    if report["status"] != "pass":
        first_failed = (stored.get("first_failed_at_epoch") or stored.get("ran_at_epoch")) if isinstance(stored, dict) and stored.get("status") != "pass" else None
        first_failed = first_failed or int(now)
    summary = f"{len(report['findings'])} overhead findings across {len(report['counts'])} threads"
    if not report["evaluated"]:
        summary = "NOT EVALUATED: " + "; ".join(report["errors"])
    record = {"check": "overhead-turns", "status": report["status"], "summary": summary,
              "detail": json.dumps({"findings": report["findings"], "errors": report["errors"]}),
              "host": socket.gethostname().split(".")[0],
              "ran_at": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "ran_at_epoch": int(now), "interval_seconds": 86400,
              "first_failed_at_epoch": first_failed, "run_kind": kind,
              "evaluated": report["evaluated"]}
    if kind != "scheduled" and isinstance(stored, dict):
        stored["last_nonauthoritative"] = record
        record = stored
    directory.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as handle:
            temp = Path(handle.name)
            json.dump(record, handle, indent=2)
            handle.write("\n")
        temp.replace(path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--events", type=Path, help="offline bb thread log --json --all array")
    parser.add_argument("--thread", help="offline thread id (also identifies an empty stream)")
    parser.add_argument("--bb", default="bb")
    parser.add_argument("--now", help="ISO-8601 time, default current UTC")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--source", choices=PATTERNS)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--health-dir", type=Path, default=Path.home() / ".claude/health")
    parser.add_argument("--file-beads", action="store_true", help="opt in to bd create (dry-run prints only)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_true")
    group.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)
    args = parser.parse_args(argv)
    if args.limit < 0 or (args.thread and not args.events):
        parser.error("--limit must be nonnegative; --thread requires --events")
    report = {"status": "fail", "evaluated": False, "dry_run": args.dry_run,
              "findings": [], "counts": {}, "errors": [], "bead_commands": []}
    now = datetime.now(timezone.utc).timestamp()
    code = 2
    try:
        if args.now:
            now = timestamp(args.now)
        state = args.state_file or args.health_dir / "state/overhead-turns.json"
        fixed = fixed_sources(state, args.state_file is not None)
        if args.events:
            events = json.loads(args.events.read_text())
            if not isinstance(events, list):
                raise ValueError("event stream must be a bare array")
            streams = {args.thread: []} if args.thread else {}
            for event in events:
                if not isinstance(event, dict) or not isinstance(event.get("threadId"), str):
                    raise ValueError("event missing threadId")
                if args.thread and event["threadId"] != args.thread:
                    raise ValueError("event threadId mismatch")
                streams.setdefault(event["threadId"], []).append(event)
        else:
            streams = live_streams(args.bb)
        report["findings"], report["counts"] = audit(streams, now, args.limit, fixed, args.source)
        report["evaluated"] = True
        report["status"] = "fail" if report["findings"] else "pass"
        code = 1 if report["findings"] else 0
        if args.file_beads:
            for finding in report["findings"]:
                command = ["bd", "--actor", "clavain-coord", "create", "--type", "bug",
                           "--title", f"Overhead turns: {finding['thread']} / {finding['source']}",
                           "--description", json.dumps(finding)]
                report["bead_commands"].append(shlex.join(command))
                if not args.dry_run:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    if result.returncode:
                        raise ValueError("bead filing failed: " + result.stderr.strip())
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        report["errors"].append(str(exc))
        report["status"] = "fail"
        code = 2
    if not args.dry_run:
        try:
            write_health(args.health_dir, report, now, args.source)
        except (OSError, ValueError, OverflowError) as exc:
            report["errors"].append("health write failed: " + str(exc))
            report["status"] = "fail"
            code = 2
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
