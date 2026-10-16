#!/usr/bin/env python3
"""Decompose weighted Claude burn: model by main session or subagent, cache-write class, TTL and context.

burn-report.py answers how much was burned and by which lineage. This answers
why: whether the weight sits in cache reads, in prefix writes at the start of a
session, in rewrites after the cache expired, or in output; how much of it ran
on Opus in main sessions; and how much ran above 100k context. It uses
burn-report.py's weights, lineage rule and dedup rule (one count per message
id and request id, each field at its largest streamed value).

A write is classed by the gap since the previous call in the same transcript:
the first call writes the session prefix, a call more than 5 minutes after the
previous one is a cold rewrite, and any other write is incremental. The 5-minute
gap matches the short cache TTL; a session writing 1-hour entries keeps its
cache across longer gaps, so read cold rewrites together with the TTL split.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys

_SPEC = importlib.util.spec_from_file_location("_burn_report", Path(__file__).resolve().parent / "burn-report.py")
br = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(br)

WEIGHTS = br.WEIGHTS
COLD_GAP = dt.timedelta(minutes=5)
LARGE_CONTEXT = 100_000


def responses(root: Path, since: dt.datetime, until: dt.datetime) -> list[dict]:
    """One row per API response in the window, oldest first."""
    seen: dict[tuple, dict] = {}
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
                    moment = br.parse_time(event["timestamp"])
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                message = event.get("message")
                if not isinstance(message, dict) or not (since <= moment < until):
                    continue
                usage, model = message.get("usage"), message.get("model")
                if not isinstance(usage, dict) or model == "<synthetic>":
                    continue
                key = (message.get("id"), event.get("requestId"))
                row = seen.get(key)
                if row is None:
                    row = seen[key] = {
                        "path": path, "time": moment, "model": model or "unknown",
                        "sub": "subagents" in path.relative_to(root).parts,
                        "usage": dict.fromkeys(WEIGHTS, 0), "ttl_5m": 0, "ttl_1h": 0,
                    }
                row["sub"] = row["sub"] or bool(event.get("isSidechain"))
                for field in WEIGHTS:
                    row["usage"][field] = max(row["usage"][field], usage.get(field) or 0)
                ttl = usage.get("cache_creation") or {}
                row["ttl_5m"] = max(row["ttl_5m"], ttl.get("ephemeral_5m_input_tokens") or 0)
                row["ttl_1h"] = max(row["ttl_1h"], ttl.get("ephemeral_1h_input_tokens") or 0)
    return sorted(seen.values(), key=lambda r: r["time"])


def weighted(usage: dict) -> float:
    return sum((usage.get(field) or 0) * weight for field, weight in WEIGHTS.items())


def context_size(usage: dict) -> int:
    return sum(usage.get(field) or 0 for field in WEIGHTS if field != "output_tokens")


def short_model(model: str) -> str:
    return model.removeprefix("claude-")


def decompose(root: Path, since: dt.datetime, until: dt.datetime, top: int = 20) -> dict:
    rows = responses(root, since, until)
    total = 0.0
    by_role = collections.Counter()
    classes = collections.Counter()
    context = collections.Counter()
    models = collections.Counter()
    ttl = collections.Counter()
    by_hour = collections.Counter()
    lineages = collections.defaultdict(collections.Counter)
    sessions = collections.defaultdict(set)
    last_call: dict[Path, dt.datetime] = {}
    main = main_opus = large = 0.0
    for row in rows:
        usage, w = row["usage"], weighted(row["usage"])
        total += w
        role = "sub" if row["sub"] else "main"
        by_role[f"{short_model(row['model'])} {role}"] += w
        models[row["model"]] += 1
        by_hour[row["time"].strftime("%Y-%m-%dT%H:00Z")] += w
        if role == "main":
            main += w
            if "opus" in row["model"]:
                main_opus += w
        write = usage["cache_creation_input_tokens"] * WEIGHTS["cache_creation_input_tokens"]
        previous = last_call.get(row["path"])
        last_call[row["path"]] = row["time"]
        if previous is None:
            classes["session_start_write"] += write
        elif row["time"] - previous > COLD_GAP:
            classes["cold_rewrite"] += write
        else:
            classes["incremental_write"] += write
        classes["read"] += usage["cache_read_input_tokens"] * WEIGHTS["cache_read_input_tokens"]
        classes["output"] += usage["output_tokens"] * WEIGHTS["output_tokens"]
        classes["uncached_input"] += usage["input_tokens"] * WEIGHTS["input_tokens"]
        ttl["5m"] += row["ttl_5m"]
        ttl["1h"] += row["ttl_1h"]
        size = context_size(usage)
        context[br.context_bucket(usage)] += w
        if size >= LARGE_CONTEXT:
            large += w
        group = lineages[br.lineage(row["path"], root)]
        group["weighted"] += w
        group["calls"] += 1
        group["opus"] += w if "opus" in row["model"] else 0
        group["sub"] += w if row["sub"] else 0
        group["large"] += w if size >= LARGE_CONTEXT else 0
        group["context"] += size
        sessions[br.lineage(row["path"], root)].add(row["path"])
    hours = max((until - since).total_seconds() / 3600, 1e-9)
    share = lambda part, whole: round(part / whole, 4) if whole else 0.0
    return {
        "since": since.isoformat().replace("+00:00", "Z"),
        "until": until.isoformat().replace("+00:00", "Z"),
        "weights": WEIGHTS,
        "calls": len(rows),
        "weighted_total": round(total),
        "per_hour": round(total / hours),
        "main_opus_share": share(main_opus, main),
        "large_context_share": share(large, total),
        "by_model_role": {k: round(v) for k, v in by_role.most_common()},
        "by_class": {k: round(v) for k, v in classes.most_common()},
        "cache_write_ttl_tokens": {"5m": ttl["5m"], "1h": ttl["1h"]},
        "by_context": {k: round(v) for k, v in context.most_common()},
        "models": dict(models.most_common()),
        "by_hour": {k: round(v) for k, v in sorted(by_hour.items())},
        "by_lineage": [
            {
                "lineage": name,
                "weighted": round(g["weighted"]),
                "calls": g["calls"],
                "opus_share": share(g["opus"], g["weighted"]),
                "subagent_share": share(g["sub"], g["weighted"]),
                "large_context_share": share(g["large"], g["weighted"]),
                "avg_context": round(g["context"] / g["calls"]),
                "sessions": len(sessions[name]),
            }
            for name, g in sorted(lineages.items(), key=lambda kv: -kv[1]["weighted"])[:top]
        ],
    }


def render(data: dict) -> str:
    total = data["weighted_total"]
    M, P = br.millions, lambda v: br.share(v, total)
    lines = [
        f"Weighted burn {data['since']} to {data['until']}: {M(total)} over {data['calls']} calls, {M(data['per_hour'])}/h",
        f"Opus share of main sessions {100 * data['main_opus_share']:.0f}%; above 100k context {100 * data['large_context_share']:.0f}%",
        f"Cache-write TTL tokens: 5m {M(data['cache_write_ttl_tokens']['5m'])}, 1h {M(data['cache_write_ttl_tokens']['1h'])}",
        "", "By model and role:", *(f"  {M(v):>7} {P(v):>4}  {k}" for k, v in data["by_model_role"].items()),
        "", "By class:", *(f"  {M(v):>7} {P(v):>4}  {k}" for k, v in data["by_class"].items()),
        "", "By context size:", *(f"  {M(v):>7} {P(v):>4}  {k}" for k, v in data["by_context"].items()),
        "", "By lineage: weighted, calls, Opus, subagent, above 100k, average context, sessions",
        *(f"  {M(g['weighted']):>7} {g['calls']:>5} {100 * g['opus_share']:>4.0f}% {100 * g['subagent_share']:>4.0f}% "
          f"{100 * g['large_context_share']:>4.0f}% {g['avg_context'] / 1000:>5.0f}k {g['sessions']:>4}  {g['lineage']}"
          for g in data["by_lineage"]),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", help="window start, ISO 8601 (default: until minus 5h)")
    parser.add_argument("--until", help="window end, ISO 8601 (default: now)")
    parser.add_argument("--root", type=Path, default=Path(os.path.expanduser("~/.claude/projects")))
    parser.add_argument("--top", type=int, default=20, help="lineages to list")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        until = br.parse_time(args.until) if args.until else dt.datetime.now(dt.timezone.utc)
        since = br.parse_time(args.since) if args.since else until - dt.timedelta(hours=br.PACE_HOURS)
    except ValueError as err:
        parser.error(str(err))
    if since >= until:
        parser.error("--since must be before --until")
    if not args.root.is_dir():
        parser.error(f"no transcript directory at {args.root}")
    data = decompose(args.root, since, until, args.top)
    print(json.dumps(data, indent=2) if args.json else render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
