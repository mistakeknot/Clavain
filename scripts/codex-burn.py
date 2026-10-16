#!/usr/bin/env python3
"""Codex token use from local session logs, by originator, model and lineage.

Each Codex session log is a JSONL file under ~/.codex/sessions. A token_count
event carries last_token_usage, the tokens of one model call; this sums those
whose timestamp falls in the window. The originator (from session_meta) tells
an exec dispatch from an interactive or bb-hosted session, and the model comes
from the latest turn_context before the call. A bb worktree or workspace path
in the session's cwd names the lineage, as in burn-report.py.

These are raw token counts, not quota: cached input is reported beside total
input rather than weighted, because the providers do not publish how a cached
token counts against a subscription window.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path
import re
import statistics
import sys

FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
THREAD = re.compile(r"/(?:worktrees|workspaces)/(thr_[a-z0-9]{10})(?:-|/|$)")


def parse_time(value: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc)


def lineage(cwd: str) -> str:
    found = THREAD.search(cwd or "")
    if found:
        return found.group(1)
    return Path(cwd).name if cwd else "unknown"


def sessions(root: Path, since: dt.datetime, until: dt.datetime):
    """Yield (originator, lineage, [(model, usage), ...]) for each session with calls in the window."""
    for path in sorted(root.rglob("*.jsonl")):
        try:
            if dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc) < since:
                continue
            handle = path.open(errors="ignore")
        except OSError:
            continue
        origin, cwd, model, calls = "unknown", "", "unknown", []
        with handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                payload = event.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                if event.get("type") == "session_meta":
                    origin = payload.get("originator") or origin
                    cwd = payload.get("cwd") or cwd
                elif event.get("type") == "turn_context":
                    model = payload.get("model") or model
                elif payload.get("type") == "token_count" and isinstance(payload.get("info"), dict):
                    try:
                        moment = parse_time(event["timestamp"])
                    except (KeyError, TypeError, ValueError, AttributeError):
                        continue
                    usage = payload["info"].get("last_token_usage")
                    if since <= moment < until and isinstance(usage, dict):
                        calls.append((model, usage))
        if calls:
            yield origin, lineage(cwd), calls


def report(root: Path, since: dt.datetime, until: dt.datetime, top: int = 15) -> dict:
    totals = collections.Counter()
    groups = {name: collections.defaultdict(collections.Counter) for name in ("originator", "model", "lineage")}
    models = collections.Counter()
    per_session = []
    count = 0
    for origin, line_name, calls in sessions(root, since, until):
        count += 1
        session_input = 0
        for model, usage in calls:
            models[model] += 1
            for field in FIELDS:
                value = usage.get(field) or 0
                totals[field] += value
                for name, key in (("originator", origin), ("model", model), ("lineage", line_name)):
                    groups[name][key][field] += value
            for name, key in (("originator", origin), ("model", model), ("lineage", line_name)):
                groups[name][key]["calls"] += 1
            session_input += usage.get("input_tokens") or 0
        for name, key in (("originator", origin), ("lineage", line_name)):
            groups[name][key]["sessions"] += 1
        per_session.append(session_input)

    def rows(name, limit=None):
        ordered = sorted(groups[name].items(), key=lambda kv: -kv[1]["input_tokens"])
        return [{name: key, **dict(c)} for key, c in ordered[:limit]]

    return {
        "since": since.isoformat().replace("+00:00", "Z"),
        "until": until.isoformat().replace("+00:00", "Z"),
        "sessions": count,
        "totals": {field: totals[field] for field in FIELDS},
        "cached_share": round(totals["cached_input_tokens"] / totals["input_tokens"], 4) if totals["input_tokens"] else 0.0,
        "median_session_input": round(statistics.median(per_session)) if per_session else 0,
        "models": dict(models.most_common()),
        "by_originator": rows("originator"),
        "by_model": rows("model"),
        "by_lineage": rows("lineage", top),
    }


def render(data: dict) -> str:
    M = lambda v: f"{v / 1e6:.1f}M"
    t = data["totals"]
    lines = [
        f"Codex tokens {data['since']} to {data['until']}: {data['sessions']} sessions",
        f"Input {M(t['input_tokens'])} ({100 * data['cached_share']:.0f}% cached), output {M(t['output_tokens'])} "
        f"(reasoning {M(t['reasoning_output_tokens'])}); median input per session {data['median_session_input'] / 1000:.0f}K",
    ]
    for name in ("originator", "model", "lineage"):
        lines += ["", f"By {name}: input, cached, output, calls"]
        lines += [f"  {M(r['input_tokens']):>7} {100 * r['cached_input_tokens'] / max(r['input_tokens'], 1):>4.0f}% "
                  f"{M(r['output_tokens']):>6} {r['calls']:>5}  {r[name]}" for r in data[f"by_{name}"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", help="window start, ISO 8601 (default: until minus 5h)")
    parser.add_argument("--until", help="window end, ISO 8601 (default: now)")
    parser.add_argument("--root", type=Path, default=Path(os.path.expanduser("~/.codex/sessions")))
    parser.add_argument("--top", type=int, default=15, help="lineages to list")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        until = parse_time(args.until) if args.until else dt.datetime.now(dt.timezone.utc)
        since = parse_time(args.since) if args.since else until - dt.timedelta(hours=5)
    except ValueError as err:
        parser.error(str(err))
    if since >= until:
        parser.error("--since must be before --until")
    if not args.root.is_dir():
        parser.error(f"no Codex session directory at {args.root}")
    data = report(args.root, since, until, args.top)
    print(json.dumps(data, indent=2) if args.json else render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
