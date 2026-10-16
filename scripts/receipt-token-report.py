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
    """Uncached input, or None when the inputs needed to derive it are unknown."""
    tin, cached = r.get("tokens_in"), r.get("tokens_cached_in")
    if tin is None:
        return None
    if r.get("usage_basis") == "codex-input-includes-cached":
        return None if cached is None else max(tin - cached, 0)
    return tin


def total(rs, key, fn=None):
    """Sum over rows where the metric is known; return (sum or None, known rows)."""
    vals = [(fn(r) if fn else r.get(key)) for r in rs]
    known = [v for v in vals if v is not None]
    return (sum(known) if known else None), len(known)


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
    groups, excluded, transports = defaultdict(list), defaultdict(int), defaultdict(int)
    for r in rows:
        st = r.get("usage_status")
        if st == "complete":
            groups[r.get(a.by) or "(none)"].append(r)
        else:
            excluded[st or "pre-change"] += 1
            if st == "unavailable":
                transports[r.get("backend") or "(none)"] += 1
    out = []
    for key, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ins = [r["tokens_in"] for r in rs if r.get("tokens_in") is not None]
        wall = []
        for r in rs:
            try:
                s = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                e = datetime.fromisoformat(r["ended_at"].replace("Z", "+00:00"))
                wall.append((e - s).total_seconds())
            except (KeyError, ValueError, AttributeError):
                pass
        g = {a.by: key, "runs": len(rs), "median_in": statistics.median(ins) if ins else None,
             "max_in": max(ins) if ins else None, "median_wall_s": statistics.median(wall) if wall else None}
        for name, fn in (("total_in", lambda r: r.get("tokens_in")), ("cached_in", lambda r: r.get("tokens_cached_in")),
                         ("uncached_in", uncached), ("cache_write_in", lambda r: r.get("tokens_cache_write_in")),
                         ("out", lambda r: r.get("tokens_out")), ("reasoning_out", lambda r: r.get("tokens_reasoning_out"))):
            g[name], g[name + "_known"] = total(rs, None, fn)
        both = [r for r in rs if r.get("tokens_in") and r.get("tokens_cached_in") is not None]
        g["cached_share"] = (sum(r["tokens_cached_in"] for r in both) / sum(r["tokens_in"] for r in both)) if both else None
        g["claude_zero_may_be_unreported"] = any(r.get("usage_basis") == "claude-input-excludes-cache" for r in rs)
        out.append(g)
    result = {"window_days": a.days, "groups": out, "excluded": dict(excluded),
              "unavailable_by_transport": dict(transports)}
    if a.json:
        json.dump(result, sys.stdout, indent=1)
        print()
        return
    print("window %gd; counted rows are usage_status=complete; excluded: %s; unavailable by transport: %s"
          % (a.days, dict(excluded) or "none", dict(transports) or "none"))
    f = lambda v: "?" if v is None else (("%.0f" % v) if not isinstance(v, float) or v > 1 else "%.2f" % v)
    for g in out:
        note = " (claude: 0 may mean not reported)" if g["claude_zero_may_be_unreported"] else ""
        print("%-28s runs=%d med_in=%s max_in=%s uncached=%s cached=%s share=%s cache_write=%s out=%s reason=%s wall_med=%s%s"
              % (g[a.by], g["runs"], f(g["median_in"]), f(g["max_in"]), f(g["uncached_in"]), f(g["cached_in"]),
                 f(g["cached_share"]), f(g["cache_write_in"]), f(g["out"]), f(g["reasoning_out"]),
                 f(g["median_wall_s"]), note))


if __name__ == "__main__":
    main()
