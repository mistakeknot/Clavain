#!/usr/bin/env python3
"""Token usage by role/model/thread from dispatch receipts.

Only receipts with usage_status == complete feed the statistics. Partial,
unavailable and pre-change rows are counted separately, never blended in.
Uncached input is derived per usage_basis and is never negative.
"""
import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

DEFAULT = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                       "clavain", "dispatch-receipts.jsonl")


def uncached(r):
    tin, cached = r.get("tokens_in") or 0, r.get("tokens_cached_in") or 0
    if r.get("usage_basis") == "codex-input-includes-cached":
        return max(tin - cached, 0)
    return tin


def load(path, since):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("kind") != "dispatch-run-receipt":
                continue
            try:
                ended = datetime.fromisoformat(r["ended_at"].replace("Z", "+00:00"))
            except (KeyError, ValueError, AttributeError):
                continue
            if ended >= since:
                rows.append(r)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT)
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--by", choices=("role", "model", "thread_id"), default="role")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    rows = load(a.file, since)
    groups, excluded = defaultdict(list), defaultdict(int)
    for r in rows:
        st = r.get("usage_status")
        if st == "complete":
            groups[r.get(a.by) or "(none)"].append(r)
        else:
            excluded[st or "pre-change"] += 1
    out = []
    for key, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ins = [r.get("tokens_in") or 0 for r in rs]
        wall = []
        for r in rs:
            try:
                s = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                e = datetime.fromisoformat(r["ended_at"].replace("Z", "+00:00"))
                wall.append((e - s).total_seconds())
            except (KeyError, ValueError):
                pass
        tin, cached = sum(ins), sum(r.get("tokens_cached_in") or 0 for r in rs)
        out.append({a.by: key, "runs": len(rs), "median_in": statistics.median(ins),
                    "max_in": max(ins), "total_in": tin, "cached_in": cached,
                    "uncached_in": sum(uncached(r) for r in rs),
                    "cache_write_in": sum(r.get("tokens_cache_write_in") or 0 for r in rs),
                    "out": sum(r.get("tokens_out") or 0 for r in rs),
                    "reasoning_out": sum(r.get("tokens_reasoning_out") or 0 for r in rs),
                    "median_wall_s": statistics.median(wall) if wall else None})
    result = {"window_days": a.days, "groups": out, "excluded": dict(excluded)}
    if a.json:
        json.dump(result, sys.stdout, indent=1)
        print()
        return
    print("window %gd; counted rows are usage_status=complete; excluded: %s"
          % (a.days, dict(excluded) or "none"))
    for g in out:
        print("%-28s runs=%d med_in=%d max_in=%d uncached=%d cached=%d cache_write=%d out=%d reason=%d wall_med=%s"
              % (g[a.by], g["runs"], g["median_in"], g["max_in"], g["uncached_in"], g["cached_in"],
                 g["cache_write_in"], g["out"], g["reasoning_out"], g["median_wall_s"]))


if __name__ == "__main__":
    main()
