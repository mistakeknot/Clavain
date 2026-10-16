#!/usr/bin/env python3
"""Extract token-usage categories for a dispatch receipt from provider evidence.

Prints one JSON object. Counts are stored as the backend reports them:
  codex  -> input_tokens INCLUDES cached_input_tokens (usage_basis
            codex-input-includes-cached); absent keys stay null.
  claude -> input excludes cache reads/writes (claude-input-excludes-cache);
            the adapter defaults absent cache fields to 0, so 0 may mean
            "not reported".
usage_status: complete | partial | unavailable. Partial counts are real but are
not a run total and must be kept out of baselines. Any other transport (BB,
Zaka) is reported unavailable rather than guessed.
"""
import argparse
import json
import sys

CODEX_KEYS = {"input_tokens": "tokens_in", "cached_input_tokens": "tokens_cached_in",
              "cache_write_input_tokens": "tokens_cache_write_in",
              "output_tokens": "tokens_out", "reasoning_output_tokens": "tokens_reasoning_out"}


def _read(path):
    """Return (dict records, count of unreadable lines or a failed open)."""
    recs, bad = [], 0
    if not path:
        return recs, 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    bad += 1  # truncated or non-JSON line: capture is damaged
                    continue
                if isinstance(obj, dict):
                    recs.append(obj)
                else:
                    bad += 1
    except OSError:
        bad += 1
    return recs, bad


def _num(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def unavailable(why):
    return {"usage_status": "unavailable", "usage_basis": None, "usage_note": why}


def _finish(res, ok, note_if_not):
    """complete needs usable input and output counts; anything less is partial."""
    if ok and (res.get("tokens_in") is None or res.get("tokens_out") is None):
        ok, note_if_not = False, "usage lacks input or output counts"
    res["usage_status"] = "complete" if ok else "partial"
    if not ok:
        res["usage_note"] = note_if_not
    return res


def codex(events, exit_code):
    started = done = 0
    total, seen = {}, {}
    recs, bad = _read(events)
    for ev in recs:
        kind = ev.get("type")
        if kind == "turn.started":
            started += 1
        elif kind == "turn.completed" and isinstance(ev.get("usage"), dict):
            done += 1
            for src, dst in CODEX_KEYS.items():
                n = _num(ev["usage"].get(src))
                if n is not None:
                    total[dst] = total.get(dst, 0) + n
                    seen[dst] = seen.get(dst, 0) + 1
    if not done:
        return unavailable("no completed turn in provider events")
    res = {"usage_basis": "codex-input-includes-cached"}
    # A total is only a run total when every completed turn reported that count.
    res.update({dst: (total[dst] if seen.get(dst) == done else None)
                for dst in CODEX_KEYS.values() if dst in total})
    res.update({dst: None for dst in CODEX_KEYS.values() if dst not in res})
    ok = exit_code == 0 and started <= done and not bad
    note = "run ended early or capture damaged (%d unreadable line(s))" % bad
    return _finish(res, ok, note)


def _claude_counts(u):
    return {"usage_basis": "claude-input-excludes-cache",
            "tokens_in": _num(u.get("input_tokens")),
            "tokens_out": _num(u.get("output_tokens")),
            "tokens_cached_in": _num(u.get("cache_read_input_tokens")),
            "tokens_cache_write_in": _num(u.get("cache_creation_input_tokens")),
            "tokens_reasoning_out": None}


def claude(events, ledger, exit_code, dispatch_id):
    if ledger:
        recs, bad = _read(ledger)
        # The adapter appends to the destination ledger, so bind to this dispatch.
        mine = [r for r in recs if r.get("type") == "usage.cumulative"
                and dispatch_id and r.get("dispatch_id") == dispatch_id]
        if mine:
            last = mine[-1]
            res = _claude_counts(last)
            return _finish(res, bool(last.get("terminal") and last.get("complete")) and not bad,
                           "claude accounting not terminal or incomplete, or ledger damaged")
        return unavailable("no usage record for this dispatch in the claude ledger")
    recs, bad = _read(events)
    result = None
    for ev in recs:
        if ev.get("type") == "result" and isinstance(ev.get("usage"), dict):
            result = ev["usage"]
    if result is None:
        return unavailable("no claude result usage in provider events")
    return _finish(_claude_counts(result), exit_code == 0 and not bad,
                   "run ended early or capture damaged")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="")
    ap.add_argument("--events", default="")
    ap.add_argument("--ledger", default="")
    ap.add_argument("--exit-code", type=int, default=0)
    ap.add_argument("--dispatch-id", default="")
    a = ap.parse_args(argv)
    if a.backend == "codex":
        res = codex(a.events, a.exit_code)
    elif a.backend == "claude":
        res = claude(a.events, a.ledger, a.exit_code, a.dispatch_id)
    else:
        res = unavailable("transport %r exposes no usage evidence to the receipt" % a.backend)
    json.dump(res, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
