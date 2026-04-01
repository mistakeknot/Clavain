#!/usr/bin/env python3
"""Backfill decomposition_outcome events into Interspect from beads JSONL backups.

Scans all beads JSONL files across ~/projects, finds closed parents with >=3
non-event children, computes decomposition metrics, and inserts them as
retroactive evidence into the Interspect database.

Part of rsj.1.9 — decomposition quality calibration pipeline.
Stage 2.5: retroactive data generation from historical beads.

Usage:
    python3 scripts/backfill-decomposition-events.py [--dry-run] [--db PATH]
"""

import argparse
import glob
import json
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone


def find_jsonl_files():
    """Find all beads JSONL files across projects."""
    patterns = [
        os.path.expanduser("~/projects/*/.beads/backup/issues.jsonl"),
        os.path.expanduser("~/projects/*/.beads/issues.jsonl"),
        os.path.expanduser("~/projects/Sylveste/**/.beads/backup/issues.jsonl"),
        os.path.expanduser("~/projects/Sylveste/**/.beads/issues.jsonl"),
        os.path.expanduser("~/projects/Sylveste/research/*/.beads/issues.jsonl"),
        os.path.expanduser("~/projects/.beads/issues.jsonl"),
    ]
    seen = set()
    files = []
    for pat in patterns:
        for f in glob.glob(pat, recursive=True):
            if f in seen or "/worktrees/" in f or "/plugins/cache/" in f:
                continue
            seen.add(f)
            files.append(f)
    return files


def load_all_issues(jsonl_files):
    """Load and deduplicate all issues from JSONL files."""
    all_issues = {}
    for f in jsonl_files:
        proj = f.split("/projects/")[-1].split("/.beads")[0] if "/projects/" in f else "unknown"
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    issue = json.loads(line)
                    iid = issue.get("id", "")
                    if iid:
                        issue["_project"] = proj
                        all_issues[iid] = issue
        except (json.JSONDecodeError, OSError):
            pass
    return all_issues


def get_parent_id(issue_id):
    """Derive parent ID from dotted notation: 'foo-bar.1.2' -> 'foo-bar.1'."""
    if "." in issue_id:
        return issue_id.rsplit(".", 1)[0]
    return None


def is_event_child(issue):
    """Check if an issue is a P4 state-change event (not a real task)."""
    priority = issue.get("priority")
    title = issue.get("title", "")
    if priority == 4 and "State change:" in title:
        return True
    issue_type = issue.get("issue_type", "") or issue.get("work_type", "") or ""
    if issue_type.lower() == "event" and priority == 4:
        return True
    return False


def compute_decomposition_metrics(parent, real_children, baseline_p50=5):
    """Compute decomposition outcome metrics for a parent and its children."""
    actual = len(real_children)
    closed = sum(1 for c in real_children if c.get("status") == "closed")
    completion = round(closed / actual, 3) if actual > 0 else 0.0

    # No real prediction available for retroactive data — use baseline p50
    predicted = baseline_p50
    replan = abs(actual - predicted)

    # Intent survival approximation (fallback from reflect.md line 146)
    if predicted > 0:
        survival = round(min(actual, predicted) / predicted, 3)
    else:
        survival = 1.0

    # Try to get complexity from parent state, default to 3
    complexity = 3

    return {
        "epic_id": parent.get("id", ""),
        "predicted_children": predicted,
        "actual_children": actual,
        "completion_rate": completion,
        "replan_count": replan,
        "intent_survival": survival,
        "complexity": complexity,
        "baseline_typical": baseline_p50,
        "retroactive": True,
        "project": parent.get("_project", "unknown"),
        "parent_title": parent.get("title", "")[:100],
    }


def find_interspect_db(db_path=None):
    """Find the Interspect database path.

    Mirrors lib-interspect.sh _interspect_db_path() priority:
    CLAUDE_PROJECT_DIR > git root > hardcoded fallback.
    """
    if db_path:
        return db_path

    # 1. CLAUDE_PROJECT_DIR
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


def get_existing_event_count(db_path):
    """Count existing decomposition_outcome events."""
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM evidence WHERE event = 'decomposition_outcome'"
    ).fetchone()[0]
    conn.close()
    return count


def get_next_seq(conn, session_id):
    """Get next sequence number for a session."""
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM evidence WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return row[0]


def insert_events(db_path, metrics_list, dry_run=False):
    """Insert decomposition_outcome events into Interspect."""
    if dry_run:
        print(f"\n[DRY RUN] Would insert {len(metrics_list)} events into {db_path}")
        return 0

    conn = sqlite3.connect(db_path)
    session_id = "backfill-decomposition-" + datetime.now(timezone.utc).strftime("%Y%m%d")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_version = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=os.path.expanduser("~/projects/Sylveste")
        )
        if result.returncode == 0:
            source_version = result.stdout.strip()
    except OSError:
        pass

    inserted = 0
    for i, m in enumerate(metrics_list):
        context = json.dumps({
            "epic_id": m["epic_id"],
            "predicted_children": m["predicted_children"],
            "actual_children": m["actual_children"],
            "completion_rate": m["completion_rate"],
            "replan_count": m["replan_count"],
            "intent_survival": m["intent_survival"],
            "complexity": m["complexity"],
            "baseline_typical": m["baseline_typical"],
            "retroactive": True,
            "source_project": m["project"],
        })
        seq = i + 1
        conn.execute(
            """INSERT INTO evidence
               (ts, session_id, seq, source, source_version, event,
                override_reason, context, project, project_lang, project_type,
                source_event_id, source_table, raw_override_reason, quarantine_until)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, 0)""",
            (
                ts, session_id, seq, "decomposition", source_version,
                "decomposition_outcome", "", context, "Sylveste",
                "interspect-decomposition",
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Backfill decomposition_outcome events")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing")
    parser.add_argument("--db", type=str, help="Path to Interspect database (auto-detected if omitted)")
    parser.add_argument("--min-children", type=int, default=3, help="Minimum non-event children to qualify (default: 3)")
    parser.add_argument("--baseline-p50", type=int, default=5, help="Baseline p50 for prediction stand-in (default: 5)")
    args = parser.parse_args()

    # Find and load all JSONL data
    jsonl_files = find_jsonl_files()
    print(f"Found {len(jsonl_files)} JSONL files")

    all_issues = load_all_issues(jsonl_files)
    print(f"Loaded {len(all_issues)} issues")

    # Build parent-child map
    children_of = defaultdict(list)
    for iid, issue in all_issues.items():
        pid = get_parent_id(iid)
        if pid and pid in all_issues:
            children_of[pid].append(issue)

    # Find qualifying decompositions
    metrics_list = []
    for pid, kids in children_of.items():
        parent = all_issues[pid]
        if parent.get("status") != "closed":
            continue
        real_kids = [k for k in kids if not is_event_child(k)]
        if len(real_kids) < args.min_children:
            continue
        metrics = compute_decomposition_metrics(parent, real_kids, args.baseline_p50)
        metrics_list.append(metrics)

    print(f"Found {len(metrics_list)} qualifying decompositions")

    if not metrics_list:
        print("Nothing to backfill.")
        return

    # Distribution summary
    child_counts = sorted(m["actual_children"] for m in metrics_list)
    n = len(child_counts)
    print(f"\nChild count distribution (N={n}):")
    print(f"  p25={child_counts[n//4]}  p50={child_counts[n//2]}  p75={child_counts[3*n//4]}  p90={child_counts[int(n*0.9)]}")
    print(f"  mean={sum(child_counts)/n:.1f}  range=[{min(child_counts)}, {max(child_counts)}]")

    completion_rates = sorted(m["completion_rate"] for m in metrics_list)
    print(f"  completion: mean={sum(completion_rates)/n:.3f}  min={min(completion_rates):.3f}")

    # Project breakdown
    proj_counts = defaultdict(int)
    for m in metrics_list:
        proj_counts[m["project"]] += 1
    print(f"\nBy project ({len(proj_counts)} projects):")
    for proj, count in sorted(proj_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {proj[:35]:35s} {count:4d}")
    if len(proj_counts) > 10:
        print(f"  ... and {len(proj_counts) - 10} more")

    # Find database
    db_path = find_interspect_db(args.db)
    if not db_path:
        print("\nERROR: Could not find Interspect database. Use --db to specify path.")
        sys.exit(1)
    print(f"\nInterspect DB: {db_path}")

    existing = get_existing_event_count(db_path)
    print(f"Existing decomposition_outcome events: {existing}")

    if existing > 0 and not args.dry_run:
        print(f"WARNING: {existing} events already exist. Backfill is additive.")
        print("  If re-running, consider clearing existing retroactive events first:")
        print(f"  sqlite3 '{db_path}' \"DELETE FROM evidence WHERE event='decomposition_outcome' AND context LIKE '%retroactive%true%';\"")

    # Insert
    inserted = insert_events(db_path, metrics_list, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"\nInserted {inserted} decomposition_outcome events")
        final = get_existing_event_count(db_path)
        print(f"Total decomposition_outcome events: {final}")
        print(f"Calibration threshold: 30 — {'READY' if final >= 30 else f'need {30 - final} more'}")
    else:
        projected = existing + len(metrics_list)
        print(f"\n[DRY RUN] Would bring total to {projected} events")
        print(f"Calibration threshold: 30 — {'READY' if projected >= 30 else f'need {30 - projected} more'}")


if __name__ == "__main__":
    main()
