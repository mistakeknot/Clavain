#!/usr/bin/env python3
"""Weighted Claude burn from local transcripts, grouped by thread lineage.

Reads every Claude Code transcript under the projects root, subagent
transcripts included, and counts each API response once: streaming writes the
same (message id, request id) on several lines. Weights approximate relative
cost: cache write 1.25, cache read 0.1, input 1, output 5. This is an estimate
of burn, not the provider's quota accounting.

A bb thread's workspace directory survives handoffs, so the transcript
directory names the lineage root: thr_ay39nh2cpv and its successors share one
group. Transcripts outside a bb workspace group by their project directory.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

WEIGHTS = {
    "input_tokens": 1.0,
    "cache_creation_input_tokens": 1.25,
    "cache_read_input_tokens": 0.1,
    "output_tokens": 5.0,
}
CONTEXT_BUCKETS = ((50_000, "<50k"), (100_000, "50-100k"), (150_000, "100-150k"))
THREAD_SLUG = re.compile(r"-thr-([a-z0-9]{10})(?=-|$)")
PACE_HOURS = 5


def parse_time(value: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc)


def lineage(path: Path, root: Path) -> str:
    slug = path.relative_to(root).parts[0]
    threads = THREAD_SLUG.findall(slug)
    if threads:
        return f"thr_{threads[-1]}"
    return re.sub(r"^-home-[^-]+-+", "", slug) or slug


def context_bucket(usage: dict) -> str:
    size = usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
    for limit, name in CONTEXT_BUCKETS:
        if size < limit:
            return name
    return ">150k"


def responses(root: Path, since: dt.datetime, until: dt.datetime):
    """Yield (path, timestamp, model, usage) once per API response in the window."""
    seen = set()
    for path in sorted(root.rglob("*.jsonl")):
        try:
            if dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc) < since:
                continue
            handle = path.open(errors="ignore")
        except OSError:
            continue
        with handle:
            for line in handle:
                if '"usage"' not in line:
                    continue
                try:
                    event = json.loads(line)
                    moment = parse_time(event["timestamp"])
                except (ValueError, KeyError, TypeError):
                    continue
                message = event.get("message")
                if not isinstance(message, dict) or not (since <= moment < until):
                    continue
                usage, model = message.get("usage"), message.get("model")
                if not isinstance(usage, dict) or model == "<synthetic>":
                    continue
                key = (message.get("id"), event.get("requestId"))
                if key in seen:
                    continue
                seen.add(key)
                yield path, moment, model, usage


def report(root: Path, since: dt.datetime, until: dt.datetime) -> dict:
    by_type = collections.Counter()
    groups = collections.defaultdict(collections.Counter)
    tallies = {name: collections.Counter() for name in ("lineage", "model", "hour", "context")}
    pace_start = until - dt.timedelta(hours=PACE_HOURS)
    pace = calls = 0
    for path, moment, model, usage in responses(root, since, until):
        weighted = 0.0
        for field, weight in WEIGHTS.items():
            value = usage.get(field) or 0
            by_type[field] += value * weight
            weighted += value * weight
        group = lineage(path, root)
        groups[group]["calls"] += 1
        tallies["lineage"][group] += weighted
        tallies["model"][model or "unknown"] += weighted
        tallies["hour"][moment.strftime("%Y-%m-%dT%H:00Z")] += weighted
        tallies["context"][context_bucket(usage)] += weighted
        if moment >= pace_start:
            pace += weighted
        calls += 1
    total = sum(by_type.values())
    return {
        "since": since.isoformat().replace("+00:00", "Z"),
        "until": until.isoformat().replace("+00:00", "Z"),
        "weights": WEIGHTS,
        "calls": calls,
        "weighted_total": round(total),
        "by_token_type": {k: round(v) for k, v in by_type.items()},
        "by_lineage": [
            {"lineage": k, "weighted": round(v), "calls": groups[k]["calls"]}
            for k, v in tallies["lineage"].most_common()
        ],
        "by_model": {k: round(v) for k, v in tallies["model"].most_common()},
        "by_hour": {k: round(v) for k, v in sorted(tallies["hour"].items())},
        "by_context": {k: round(v) for k, v in tallies["context"].most_common()},
        "pace": {
            "hours": PACE_HOURS,
            "weighted": round(pace),
            "per_hour": round(pace / min(PACE_HOURS, max((until - since).total_seconds() / 3600, 1e-9))),
        },
    }


def millions(value: float) -> str:
    return f"{value / 1e6:.1f}M"


def share(value: float, total: float) -> str:
    return f"{100 * value / total:.0f}%" if total else "0%"


def render(data: dict, top: int) -> str:
    total = data["weighted_total"]
    lines = [
        f"Weighted burn {data['since']} to {data['until']}: {millions(total)} over {data['calls']} calls",
        "By token type: " + ", ".join(f"{k.removesuffix('_tokens')} {share(v, total)}" for k, v in data["by_token_type"].items()),
        "By context size: " + ", ".join(f"{k} {share(v, total)}" for k, v in data["by_context"].items()),
        f"Last {data['pace']['hours']}h: {millions(data['pace']['weighted'])}, {millions(data['pace']['per_hour'])}/h",
        "",
        "By hour (UTC):",
        *(f"  {k}  {millions(v)}" for k, v in data["by_hour"].items()),
        "",
        "By model:",
        *(f"  {millions(v):>7}  {k}" for k, v in data["by_model"].items()),
        "",
        f"By lineage (top {top}):",
        *(f"  {millions(g['weighted']):>7}  {share(g['weighted'], total):>4}  {g['calls']:>5} calls  {g['lineage']}" for g in data["by_lineage"][:top]),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", help="window start, ISO 8601 (default: until minus 5h)")
    parser.add_argument("--until", help="window end, ISO 8601 (default: now)")
    parser.add_argument("--root", type=Path, default=Path(os.path.expanduser("~/.claude/projects")))
    parser.add_argument("--top", type=int, default=10, help="lineages to list (text output)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        until = parse_time(args.until) if args.until else dt.datetime.now(dt.timezone.utc)
        since = parse_time(args.since) if args.since else until - dt.timedelta(hours=PACE_HOURS)
    except ValueError as err:
        parser.error(str(err))
    if since >= until:
        parser.error("--since must be before --until")
    if not args.root.is_dir():
        parser.error(f"no transcript directory at {args.root}")
    data = report(args.root, since, until)
    print(json.dumps(data, indent=2) if args.json else render(data, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
