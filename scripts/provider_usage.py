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


def _lines(path):
    if not path:
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue  # truncated or non-JSON line
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def _num(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def unavailable(why):
    return {"usage_status": "unavailable", "usage_basis": None, "usage_note": why}


def codex(events, exit_code):
    started = done = 0
    total = {}
    for ev in _lines(events):
        kind = ev.get("type")
        if kind == "turn.started":
            started += 1
        elif kind == "turn.completed" and isinstance(ev.get("usage"), dict):
            done += 1
            for src, dst in CODEX_KEYS.items():
                n = _num(ev["usage"].get(src))
                if n is not None:
                    total[dst] = total.get(dst, 0) + n
    if not done:
        return unavailable("no completed turn in provider events")
    ok = exit_code == 0 and started <= done
    out = {"usage_status": "complete" if ok else "partial",
           "usage_basis": "codex-input-includes-cached"}
    out.update({dst: total.get(dst) for dst in CODEX_KEYS.values()})
    return out


def claude(events, ledger, exit_code):
    last = None
    for rec in _lines(ledger):
        if rec.get("type") == "usage.cumulative":
            last = rec
    if last is not None:
        ok = bool(last.get("terminal") and last.get("complete"))
        return {"usage_status": "complete" if ok else "partial",
                "usage_basis": "claude-input-excludes-cache",
                "tokens_in": _num(last.get("input_tokens")),
                "tokens_out": _num(last.get("output_tokens")),
                "tokens_cached_in": _num(last.get("cache_read_input_tokens")),
                "tokens_cache_write_in": _num(last.get("cache_creation_input_tokens")),
                "tokens_reasoning_out": None}
    result = None
    for ev in _lines(events):
        if ev.get("type") == "result" and isinstance(ev.get("usage"), dict):
            result = ev["usage"]
    if result is None:
        return unavailable("no claude result usage in provider events")
    return {"usage_status": "complete" if exit_code == 0 else "partial",
            "usage_basis": "claude-input-excludes-cache",
            "tokens_in": _num(result.get("input_tokens")),
            "tokens_out": _num(result.get("output_tokens")),
            "tokens_cached_in": _num(result.get("cache_read_input_tokens")),
            "tokens_cache_write_in": _num(result.get("cache_creation_input_tokens")),
            "tokens_reasoning_out": None}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="")
    ap.add_argument("--events", default="")
    ap.add_argument("--ledger", default="")
    ap.add_argument("--exit-code", type=int, default=0)
    a = ap.parse_args(argv)
    if a.backend == "codex":
        res = codex(a.events, a.exit_code)
    elif a.backend == "claude":
        res = claude(a.events, a.ledger, a.exit_code)
    else:
        res = unavailable("transport %r exposes no usage evidence to the receipt" % a.backend)
    json.dump(res, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
