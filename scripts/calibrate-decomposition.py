#!/usr/bin/env python3
"""Stage 3 calibration: recompute decomposition quality parameters from Interspect evidence.

Reads all decomposition_outcome events from Interspect, computes calibrated
percentiles and thresholds, and writes the `calibrated:` section into
decomposition-calibration.yaml.

Part of rsj.1.9 — decomposition quality calibration pipeline.
Stage 3: auto-calibrate from accumulated evidence.

Usage:
    python3 scripts/calibrate-decomposition.py [--dry-run] [--db PATH] [--config PATH]
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


def percentile(sorted_arr, p):
    """Compute percentile from a sorted array."""
    if not sorted_arr:
        return 0
    idx = int(len(sorted_arr) * p / 100)
    return sorted_arr[min(idx, len(sorted_arr) - 1)]


def load_events(db_path, min_threshold=30):
    """Load decomposition_outcome events from Interspect."""
    conn = sqlite3.connect(db_path)
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    rows = conn.execute(
        """SELECT context FROM evidence
           WHERE event = 'decomposition_outcome'
             AND quarantine_until <= ?""",
        (now_epoch,),
    ).fetchall()
    conn.close()

    events = []
    for (ctx_str,) in rows:
        try:
            ctx = json.loads(ctx_str)
            events.append(ctx)
        except (json.JSONDecodeError, TypeError):
            pass

    if len(events) < min_threshold:
        print(f"Only {len(events)} events (threshold: {min_threshold}). Calibration not ready.")
        sys.exit(1)

    return events


def compute_calibration(events):
    """Compute calibrated parameters from events."""
    child_counts = sorted(e.get("actual_children", 0) for e in events)
    completion_rates = sorted(e.get("completion_rate", 0) for e in events)
    replan_counts = sorted(e.get("replan_count", 0) for e in events)
    n = len(events)

    # Separate retroactive from live events for weighting info
    retroactive = sum(1 for e in events if e.get("retroactive"))
    live = n - retroactive

    calibrated = {
        "child_count": {
            "p25": percentile(child_counts, 25),
            "p50": percentile(child_counts, 50),
            "p75": percentile(child_counts, 75),
            "p90": percentile(child_counts, 90),
            "mean": round(sum(child_counts) / n, 1),
            "range": [min(child_counts), max(child_counts)],
        },
        "thresholds": {
            "under_decomposition": max(2, percentile(child_counts, 5)),
            "over_decomposition": percentile(child_counts, 90),
            "prediction_accuracy_warn": 0.5,
        },
        "completion": {
            "expected_rate": round(sum(completion_rates) / n, 3),
            # p10 can be 1.0 when most decompositions complete fully — use p5 with a floor
            "warn_below": round(min(percentile(completion_rates, 5), 0.75), 2),
        },
        "replanning": {
            # Retroactive events use baseline p50 as prediction stand-in, so replan
            # counts are inflated. Only trust this when live_count > 0.
            "expected_rate": round(sum(replan_counts) / n / max(sum(child_counts) / n, 1), 2) if live > 0 else 0.15,
            "warn_above": 0.40,
        },
        "last_calibrated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_count": n,
        "retroactive_count": retroactive,
        "live_count": live,
    }
    return calibrated


def format_yaml_section(calibrated):
    """Format the calibrated section as YAML."""
    c = calibrated
    cc = c["child_count"]
    th = c["thresholds"]
    co = c["completion"]
    rp = c["replanning"]

    return f"""calibrated:
  child_count:
    p25: {cc['p25']}
    p50: {cc['p50']}
    p75: {cc['p75']}
    p90: {cc['p90']}
    mean: {cc['mean']}
    range: [{cc['range'][0]}, {cc['range'][1]}]

  thresholds:
    under_decomposition: {th['under_decomposition']}
    over_decomposition: {th['over_decomposition']}
    prediction_accuracy_warn: {th['prediction_accuracy_warn']}

  completion:
    expected_rate: {co['expected_rate']}
    warn_below: {co['warn_below']}

  replanning:
    expected_rate: {rp['expected_rate']}
    warn_above: {rp['warn_above']}

  last_calibrated: "{c['last_calibrated']}"
  event_count: {c['event_count']}
  retroactive_count: {c['retroactive_count']}
  live_count: {c['live_count']}
"""


def find_config_path(config_path=None):
    """Find the decomposition-calibration.yaml config."""
    if config_path:
        return config_path
    candidates = [
        os.path.expanduser("~/projects/Sylveste/os/Clavain/config/decomposition-calibration.yaml"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def find_interspect_db(db_path=None):
    """Find the Interspect database path.

    Mirrors lib-interspect.sh _interspect_db_path() priority:
    CLAUDE_PROJECT_DIR > git root > hardcoded fallback.
    """
    if db_path:
        return db_path

    # 1. CLAUDE_PROJECT_DIR (set by Claude Code for the active project)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if project_dir:
        candidate = os.path.join(project_dir, ".clavain/interspect/interspect.db")
        if os.path.isfile(candidate):
            return candidate

    # 2. Git root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            candidate = os.path.join(result.stdout.strip(), ".clavain/interspect/interspect.db")
            if os.path.isfile(candidate):
                return candidate
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 3. Hardcoded fallback
    candidate = os.path.expanduser("~/projects/Sylveste/.clavain/interspect/interspect.db")
    if os.path.isfile(candidate):
        return candidate

    return None


def main():
    parser = argparse.ArgumentParser(description="Calibrate decomposition quality parameters")
    parser.add_argument("--dry-run", action="store_true", help="Print calibrated values without writing")
    parser.add_argument("--db", type=str, help="Path to Interspect database")
    parser.add_argument("--config", type=str, help="Path to decomposition-calibration.yaml")
    parser.add_argument("--min-events", type=int, default=30, help="Minimum events for calibration (default: 30)")
    args = parser.parse_args()

    db_path = find_interspect_db(args.db)
    if not db_path:
        print("ERROR: Could not find Interspect database.")
        sys.exit(1)

    config_path = find_config_path(args.config)
    if not config_path:
        print("ERROR: Could not find decomposition-calibration.yaml.")
        sys.exit(1)

    print(f"Interspect DB: {db_path}")
    print(f"Config: {config_path}")

    # Load events
    events = load_events(db_path, args.min_events)
    print(f"Loaded {len(events)} decomposition_outcome events")

    # Compute calibration
    calibrated = compute_calibration(events)
    yaml_section = format_yaml_section(calibrated)

    print(f"\nCalibrated values:")
    print(yaml_section)

    if args.dry_run:
        print("[DRY RUN] Would write to config. Exiting.")
        return

    # Read existing config and replace/append calibrated section
    with open(config_path) as f:
        content = f.read()

    # Remove existing calibrated section (commented or uncommented)
    lines = content.split("\n")
    new_lines = []
    in_calibrated = False
    for line in lines:
        if line.startswith("calibrated:") or line.startswith("# calibrated:"):
            in_calibrated = True
            continue
        if in_calibrated:
            # Stay in calibrated section until we hit a non-indented, non-comment line
            stripped = line.lstrip("# ")
            if line == "" or line.startswith("  ") or line.startswith("#  "):
                continue
            else:
                in_calibrated = False
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Ensure trailing newline, then append calibrated section
    result = "\n".join(new_lines).rstrip() + "\n\n" + yaml_section

    with open(config_path, "w") as f:
        f.write(result)

    print(f"Written calibrated section to {config_path}")

    # Comparison with defaults
    print("\n--- Defaults vs Calibrated ---")
    print(f"  child p50:    5 → {calibrated['child_count']['p50']}")
    print(f"  child p90:   16 → {calibrated['child_count']['p90']}")
    print(f"  child mean: 7.5 → {calibrated['child_count']['mean']}")
    print(f"  completion: 0.99 → {calibrated['completion']['expected_rate']}")
    print(f"  over_decomp: 15 → {calibrated['thresholds']['over_decomposition']}")


if __name__ == "__main__":
    main()
