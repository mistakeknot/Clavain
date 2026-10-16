#!/usr/bin/env python3
"""Hourly burn watch: snapshot Claude and Codex use, and message a steward only on a breach.

Run from a scheduler once an hour. Each run reads the last few complete clock
hours of local transcripts (burn-decompose.py for Claude, codex-burn.py for
Codex), writes a snapshot, and checks the thresholds in a JSON config:

  hourly_burn_max         weighted Claude burn per hour; breached when each of
                          the last `consecutive_hours` complete hours is above it
  main_opus_share_max     Opus share of weighted burn in main sessions
  large_context_share_max share of weighted burn above 100k context
  retired_models          substrings; any Claude or Codex call on a matching model
  audit_command           argv of an audit that exits 0 when clean and 1 with
                          findings on stdout

Share checks read the whole window (`window_hours`) and are skipped when it
burned less than `share_min_weighted`, so a quiet window cannot breach on a
handful of calls. Any threshold left out of the config is off. A breach is
messaged once per `realert_hours`; an hour with no breach sends nothing, so a
quiet watch costs no model tokens.

The message goes to the one unarchived bb thread whose title starts with
`alert.thread_title_prefix`, found when the alert is sent rather than stored,
so a steward handoff needs no config change.

Exit status follows the rig-report convention: 0 when the watch ran (with or
without a breach), 2 when it could not assess or could not deliver an alert.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
KNOWN_KEYS = {
    "window_hours", "hourly_burn_max", "consecutive_hours", "main_opus_share_max",
    "large_context_share_max", "share_min_weighted", "retired_models", "audit_command",
    "realert_hours", "keep_days", "alert",
}
DEFAULTS = {"window_hours": 6, "consecutive_hours": 2, "share_min_weighted": 5_000_000,
            "realert_hours": 6, "keep_days": 30, "retired_models": []}


class CannotAssess(Exception):
    pass


def load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as err:
        raise CannotAssess(f"cannot read config {path}: {err}") from err
    if not isinstance(raw, dict):
        raise CannotAssess(f"config {path} is not a JSON object")
    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        raise CannotAssess(f"config {path} has unknown keys: {', '.join(unknown)}")
    config = {**DEFAULTS, **raw}
    if config["consecutive_hours"] > config["window_hours"]:
        raise CannotAssess("consecutive_hours must not exceed window_hours")
    return config


def stamp(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%MZ")


def evaluate(config: dict, claude: dict, codex: dict | None, until: dt.datetime) -> list[dict]:
    """Return the breaches, each {key, text}."""
    breaches = []
    limit = config.get("hourly_burn_max")
    if limit is not None:
        n = config["consecutive_hours"]
        hours = [(until - dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H:00Z") for i in range(n, 0, -1)]
        burned = [claude["by_hour"].get(h, 0) for h in hours]
        if all(b > limit for b in burned):
            figures = ", ".join(f"{h[11:16]}Z {b / 1e6:.1f}M" for h, b in zip(hours, burned))
            breaches.append({"key": "hourly_burn",
                             "text": f"Weighted Claude burn above {limit / 1e6:.1f}M/h for {n} hours: {figures}."})
    if claude["weighted_total"] >= config["share_min_weighted"]:
        for key, field, label in (("main_opus_share_max", "main_opus_share", "Opus share of main-session burn"),
                                  ("large_context_share_max", "large_context_share", "Share of burn above 100k context")):
            cap = config.get(key)
            if cap is not None and claude[field] > cap:
                breaches.append({"key": field, "text": f"{label} {100 * claude[field]:.0f}% over "
                                 f"{config['window_hours']}h, above {100 * cap:.0f}%."})
    seen = {**{m: ("Claude", c) for m, c in claude["models"].items()},
            **{m: ("Codex", c) for m, c in (codex or {}).get("models", {}).items()}}
    for pattern in config["retired_models"]:
        for model, (source, calls) in sorted(seen.items()):
            if pattern in model:
                breaches.append({"key": f"retired:{model}",
                                 "text": f"{source} ran {calls} call(s) on retired model {model} in the last {config['window_hours']}h."})
    audit = config.get("audit_command")
    if audit:
        try:
            done = subprocess.run(audit, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise CannotAssess(f"audit command failed to run: {err}") from err
        if done.returncode == 1:
            breaches.append({"key": "audit", "text": "Spawn-routing audit findings:\n" + done.stdout.strip()[:2000]})
        elif done.returncode != 0:
            raise CannotAssess(f"audit command exited {done.returncode}: {done.stderr.strip()[:300]}")
    return breaches


def due(breaches: list[dict], state: dict, now: dt.datetime, realert_hours: float) -> list[dict]:
    fresh = []
    for breach in breaches:
        last = state.get(breach["key"])
        if last is None or now - dt.datetime.fromisoformat(last) >= dt.timedelta(hours=realert_hours):
            fresh.append(breach)
    return fresh


def resolve_thread(bb: str, prefix: str) -> str:
    try:
        done = subprocess.run([bb, "thread", "list", "--json"], capture_output=True, text=True, timeout=120)
        threads = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as err:
        raise CannotAssess(f"cannot list bb threads: {err}") from err
    if done.returncode != 0 or not isinstance(threads, list):
        raise CannotAssess(f"bb thread list failed: {done.stderr.strip()[:300]}")
    matches = [t["id"] for t in threads
               if isinstance(t, dict) and not t.get("archivedAt") and (t.get("title") or "").startswith(prefix)]
    if len(matches) != 1:
        raise CannotAssess(f"expected one unarchived thread titled {prefix!r}*, found {len(matches)}")
    return matches[0]


def send(config: dict, message_file: Path) -> str:
    alert = config.get("alert") or {}
    prefix = alert.get("thread_title_prefix")
    if not prefix:
        raise CannotAssess("breach found but config has no alert.thread_title_prefix")
    bb = alert.get("bb") or os.environ.get("BB_CLI") or "bb"
    thread = resolve_thread(bb, prefix)
    try:
        done = subprocess.run([bb, "thread", "tell", thread, "--mode", "auto", "--message-file", str(message_file)],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise CannotAssess(f"bb thread tell failed to run: {err}") from err
    if done.returncode != 0:
        raise CannotAssess(f"bb thread tell exited {done.returncode}: {done.stderr.strip()[:300]}")
    return thread


def message(breaches: list[dict], claude: dict, codex: dict | None, snapshot: Path) -> str:
    lines = [f"Burn watch: {len(breaches)} threshold breach(es), window {claude['since']} to {claude['until']}.", ""]
    lines += [f"- {b['text']}" for b in breaches]
    lines += ["", f"Claude: {claude['weighted_total'] / 1e6:.1f}M weighted, {claude['per_hour'] / 1e6:.1f}M/h; "
              f"Opus share of main {100 * claude['main_opus_share']:.0f}%; above 100k context {100 * claude['large_context_share']:.0f}%."]
    if claude["by_lineage"]:
        lines.append("Top lineages: " + ", ".join(
            f"{g['lineage']} {g['weighted'] / 1e6:.1f}M" for g in claude["by_lineage"][:5]))
    if codex:
        lines.append(f"Codex: {codex['totals']['input_tokens'] / 1e6:.1f}M input ({100 * codex['cached_share']:.0f}% cached) "
                     f"over {codex['sessions']} sessions.")
    lines += ["", f"Snapshot: {snapshot}", "This message is sent once per breach per re-alert period; no reply is needed."]
    return "\n".join(lines) + "\n"


def prune(directory: Path, now: dt.datetime, keep_days: float) -> None:
    cutoff = now - dt.timedelta(days=keep_days)
    for path in directory.glob("*.json"):
        try:
            taken = dt.datetime.strptime(path.stem, "%Y-%m-%dT%H%MZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if taken < cutoff:
            path.unlink(missing_ok=True)


def run(args) -> int:
    now = (args.now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    config = read_config(args.config)
    until = now.replace(minute=0, second=0, microsecond=0)
    since = until - dt.timedelta(hours=config["window_hours"])
    if not args.claude_root.is_dir():
        raise CannotAssess(f"no Claude transcript directory at {args.claude_root}")
    claude = load("burn-decompose").decompose(args.claude_root, since, until, top=10)
    codex = load("codex-burn").report(args.codex_root, since, until, top=10) if args.codex_root.is_dir() else None
    breaches = evaluate(config, claude, codex, until)

    snapshots = args.state_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot = snapshots / f"{until:%Y-%m-%dT%H%MZ}.json"
    state_path = args.state_dir / "alerted.json"
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except ValueError:
        state = {}
    fresh = due(breaches, state, now, config["realert_hours"])
    record = {"taken_at": now.isoformat().replace("+00:00", "Z"), "config": str(args.config),
              "claude": claude, "codex": codex, "breaches": breaches,
              "alerted": [b["key"] for b in fresh], "alert_thread": None, "dry_run": args.dry_run}
    error = None
    if fresh:
        body = message(fresh, claude, codex, snapshot)
        alert_file = args.state_dir / "last-alert.md"
        alert_file.write_text(body)
        if args.dry_run:
            print(body, end="")
        else:
            try:
                record["alert_thread"] = send(config, alert_file)
                state.update({b["key"]: now.isoformat() for b in fresh})
                state_path.write_text(json.dumps(state, indent=2) + "\n")
            except CannotAssess as err:
                error = str(err)
                record["alerted"] = []
                record["alert_error"] = error
    snapshot.write_text(json.dumps(record, indent=2) + "\n")
    prune(snapshots, now, config["keep_days"])
    summary = (f"burn-watch {stamp(since)}..{stamp(until)}: Claude {claude['per_hour'] / 1e6:.1f}M/h, "
               f"{len(breaches)} breach(es), {len(record['alerted'])} alerted")
    print(summary)
    if error:
        print(f"burn-watch: could not deliver alert: {error}", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path(os.path.expanduser("~/.config/burn-watch/config.json")))
    parser.add_argument("--state-dir", type=Path, default=Path(os.path.expanduser("~/.local/state/burn-watch")))
    parser.add_argument("--claude-root", type=Path, default=Path(os.path.expanduser("~/.claude/projects")))
    parser.add_argument("--codex-root", type=Path, default=Path(os.path.expanduser("~/.codex/sessions")))
    parser.add_argument("--now", type=lambda v: dt.datetime.fromisoformat(v.replace("Z", "+00:00")),
                        help="pretend the run happens at this ISO 8601 time (tests)")
    parser.add_argument("--dry-run", action="store_true", help="print any alert instead of sending it")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except CannotAssess as err:
        print(f"burn-watch: could not assess: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
