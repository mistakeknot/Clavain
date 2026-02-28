#!/usr/bin/env python3
"""Galiana topology experiment runner.

Finds recent production flux-drive reviews, re-runs with fixed topologies,
compares results.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from typing import Any

from utils import iter_jsonl, normalize_title, titles_match

CLAVAIN_DIR = Path.home() / ".clavain"
RESULTS_FILE = CLAVAIN_DIR / "topology-results.jsonl"


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse ISO string or YYYY-MM-DD to UTC datetime."""
    try:
        if isinstance(raw, (int, float)):
            ts = raw / 1000 if raw > 1_000_000_000_000 else raw
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(raw, str) and raw:
            # Try ISO format first
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None
    return None


def load_topologies() -> dict[str, Any]:
    """Read topologies.json from script directory."""
    script_dir = Path(__file__).parent
    topology_file = script_dir / "topologies.json"

    if not topology_file.exists():
        print(f"ERROR: {topology_file} not found", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(topology_file.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {topology_file}: {e}", file=sys.stderr)
        sys.exit(1)


def find_production_reviews(project_root: Path, target_date: str) -> list[tuple[Path, dict[str, Any]]]:
    """Find findings.json files matching target date.

    Args:
        project_root: Project root directory
        target_date: Date string (YYYY-MM-DD)

    Returns:
        List of (file_path, parsed_document) tuples
    """
    import glob

    flux_drive_pattern = project_root / "**" / "docs" / "research" / "flux-drive" / "**" / "findings.json"
    quality_gates_pattern = project_root / "**" / ".clavain" / "quality-gates" / "findings.json"
    files: set[Path] = set()
    for pattern in [flux_drive_pattern, quality_gates_pattern]:
        files.update(Path(p).resolve() for p in glob.glob(str(pattern), recursive=True))
    findings_files = sorted(files)

    reviews: list[tuple[Path, dict[str, Any]]] = []
    for file_path in findings_files:
        try:
            doc = json.loads(file_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: Skipping {file_path}: {e}", file=sys.stderr)
            continue

        if not isinstance(doc, dict):
            continue

        # Parse reviewed date
        reviewed_raw = doc.get("reviewed")
        reviewed_ts = parse_timestamp(reviewed_raw)

        if reviewed_ts is None:
            continue

        # Compare date portion only
        reviewed_date = reviewed_ts.strftime("%Y-%m-%d")
        if reviewed_date == target_date:
            reviews.append((file_path, doc))

    return reviews


def classify_task_type(review_doc: dict[str, Any]) -> str:
    """Infer task type from input and findings content."""
    input_str = str(review_doc.get("input", "")).lower()

    # Check input field first
    if "plan" in input_str or "prd" in input_str:
        return "planning"
    if input_str.endswith(".md"):
        return "docs"

    # Check findings content
    findings = review_doc.get("findings", [])
    if not isinstance(findings, list):
        return "code_review"

    findings_text = " ".join([
        str(f.get("title", "")).lower() + " " + str(f.get("section", "")).lower()
        for f in findings if isinstance(f, dict)
    ])

    if "refactor" in findings_text:
        return "refactor"
    if any(word in findings_text for word in ["bug", "regression", "fix"]):
        return "bugfix"

    return "code_review"


def select_diverse_tasks(reviews: list[tuple[Path, dict[str, Any]]], max_count: int = 5) -> list[tuple[Path, dict[str, Any]]]:
    """Select diverse tasks, one per task type, preferring richer reviews."""
    if not reviews:
        return []

    # Group by task type
    by_type: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for file_path, doc in reviews:
        task_type = classify_task_type(doc)
        by_type[task_type].append((file_path, doc))

    # Sort each type by finding count (descending)
    for task_type in by_type:
        by_type[task_type].sort(
            key=lambda x: len(x[1].get("findings", [])),
            reverse=True
        )

    # Pick one from each type first
    selected: list[tuple[Path, dict[str, Any]]] = []
    for task_type in sorted(by_type.keys()):
        if len(selected) >= max_count:
            break
        selected.append(by_type[task_type][0])

    # Fill remaining slots from largest groups
    if len(selected) < max_count:
        remaining_types = sorted(by_type.keys(), key=lambda t: len(by_type[t]), reverse=True)
        for task_type in remaining_types:
            # Skip first element (already selected)
            for item in by_type[task_type][1:]:
                if len(selected) >= max_count:
                    break
                selected.append(item)
            if len(selected) >= max_count:
                break

    return selected[:max_count]


def run_shadow_review(
    input_path: str,
    topology_name: str,
    topology_agents: list[str],
    project_dir: Path,
    script_dir: Path
) -> dict[str, Any]:
    """Run shadow review with specified topology.

    Returns:
        Dict with findings list and agents_completed list
    """
    shadow_dir = CLAVAIN_DIR / "shadow-runs" / topology_name
    shadow_dir.mkdir(parents=True, exist_ok=True)

    shadow_script = script_dir / "shadow-review.sh"
    if not shadow_script.exists():
        print(f"WARN: shadow-review.sh not found at {shadow_script}", file=sys.stderr)
        return {"findings": [], "agents_completed": []}

    all_findings: list[dict[str, Any]] = []
    agents_completed: list[str] = []

    for agent in topology_agents:
        # Extract agent name (strip prefix if present)
        agent_name = agent.split(":")[-1]
        output_file = shadow_dir / f"{agent_name}.json"

        try:
            # Call shadow-review.sh
            result = subprocess.run(
                [str(shadow_script), agent, input_path, str(output_file)],
                cwd=project_dir,
                timeout=300,  # 5 minute timeout per agent
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"WARN: Agent {agent_name} exited {result.returncode}: {result.stderr[:200]}", file=sys.stderr)

            # Parse output
            if output_file.exists():
                agent_output = json.loads(output_file.read_text())
                if isinstance(agent_output, dict):
                    findings = agent_output.get("findings", [])
                    if isinstance(findings, list):
                        all_findings.extend(findings)
                        agents_completed.append(agent_name)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            print(f"WARN: Agent {agent_name} failed: {e}", file=sys.stderr)
            continue

    return {"findings": all_findings, "agents_completed": agents_completed}


def compute_overlap_metrics(
    shadow_findings: list[dict[str, Any]],
    production_findings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compute recall, precision, unique discoveries, redundancy ratio."""
    if not production_findings:
        return {
            "recall": None,
            "precision": None,
            "unique_discoveries": len(shadow_findings),
            "total_findings": len(shadow_findings),
            "p0_findings": sum(1 for f in shadow_findings if str(f.get("severity", "")).upper() == "P0"),
            "p1_findings": sum(1 for f in shadow_findings if str(f.get("severity", "")).upper() == "P1"),
            "redundancy_ratio": 0.0
        }

    # Extract P0/P1 production findings
    prod_p0_p1 = [
        f for f in production_findings
        if str(f.get("severity", "")).upper() in {"P0", "P1"}
    ]

    # Match shadow findings to production
    matched_prod = set()
    matched_shadow = set()

    for i, shadow_f in enumerate(shadow_findings):
        shadow_title = str(shadow_f.get("title", ""))
        for j, prod_f in enumerate(prod_p0_p1):
            prod_title = str(prod_f.get("title", ""))
            if titles_match(shadow_title, prod_title):
                matched_prod.add(j)
                matched_shadow.add(i)
                break

    # Compute metrics
    recall = len(matched_prod) / len(prod_p0_p1) if prod_p0_p1 else None
    precision = len(matched_shadow) / len(shadow_findings) if shadow_findings else None
    unique_discoveries = len(shadow_findings) - len(matched_shadow)

    # Count P0/P1 in shadow
    p0_count = sum(1 for f in shadow_findings if str(f.get("severity", "")).upper() == "P0")
    p1_count = sum(1 for f in shadow_findings if str(f.get("severity", "")).upper() == "P1")

    # Compute redundancy ratio (findings with convergence > 1)
    convergent = sum(1 for f in shadow_findings if int(f.get("convergence", 1)) > 1)
    redundancy_ratio = convergent / len(shadow_findings) if shadow_findings else 0.0

    return {
        "recall": round(recall, 4) if recall is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "unique_discoveries": unique_discoveries,
        "total_findings": len(shadow_findings),
        "p0_findings": p0_count,
        "p1_findings": p1_count,
        "redundancy_ratio": round(redundancy_ratio, 4)
    }


def run_experiment(
    project_root: Path,
    target_date: str,
    topology_names: list[str],
    dry_run: bool
) -> None:
    """Run topology experiment for target date."""
    script_dir = Path(__file__).parent

    # Load topologies
    topologies = load_topologies()

    # Validate requested topologies
    for topo_name in topology_names:
        if topo_name not in topologies:
            print(f"ERROR: Unknown topology '{topo_name}'", file=sys.stderr)
            print(f"Available: {', '.join(topologies.keys())}", file=sys.stderr)
            sys.exit(1)

    # Find production reviews
    print(f"Finding production reviews for {target_date}...", file=sys.stderr)
    reviews = find_production_reviews(project_root, target_date)

    if not reviews:
        print(f"No production reviews found for {target_date}", file=sys.stderr)
        print("Make sure findings.json files have 'reviewed' field matching target date", file=sys.stderr)
        return

    print(f"Found {len(reviews)} production reviews", file=sys.stderr)

    # Select diverse tasks
    selected = select_diverse_tasks(reviews)
    print(f"Selected {len(selected)} diverse tasks", file=sys.stderr)

    # Print summary
    for file_path, doc in selected:
        task_type = classify_task_type(doc)
        input_path = doc.get("input", "unknown")
        finding_count = len(doc.get("findings", []))
        print(f"  - {task_type}: {input_path} ({finding_count} findings)", file=sys.stderr)

    if dry_run:
        print(f"\nDry run: would execute {len(selected) * len(topology_names)} shadow reviews", file=sys.stderr)
        print(f"Topologies: {', '.join(topology_names)}", file=sys.stderr)
        return

    # Run experiments
    total_runs = len(selected) * len(topology_names)
    run_count = 0

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    for file_path, doc in selected:
        task_type = classify_task_type(doc)
        input_path = str(doc.get("input", ""))
        task_id = f"flux-drive/{file_path.parent.name}"

        production_findings = doc.get("findings", [])
        if not isinstance(production_findings, list):
            production_findings = []

        # Count production agents (from unique agent names in findings)
        prod_agents = set()
        for f in production_findings:
            if isinstance(f, dict):
                agents_raw = f.get("agents") or f.get("agent", "")
                if isinstance(agents_raw, list):
                    prod_agents.update(agents_raw)
                elif isinstance(agents_raw, str):
                    prod_agents.update([a.strip() for a in agents_raw.split(",") if a.strip()])

        prod_p0_count = sum(1 for f in production_findings if str(f.get("severity", "")).upper() == "P0")
        prod_p1_count = sum(1 for f in production_findings if str(f.get("severity", "")).upper() == "P1")

        for topo_name in topology_names:
            run_count += 1
            print(f"\n[{run_count}/{total_runs}] Running {task_type} with {topo_name}...", file=sys.stderr)

            topo_config = topologies[topo_name]
            topo_agents = topo_config.get("agents", [])

            # Time the shadow review
            start_time = time()
            shadow_result = run_shadow_review(
                input_path=input_path,
                topology_name=topo_name,
                topology_agents=topo_agents,
                project_dir=project_root,
                script_dir=script_dir
            )
            duration = int(time() - start_time)

            # Compute metrics
            shadow_findings = shadow_result["findings"]
            agents_completed = shadow_result["agents_completed"]

            metrics = compute_overlap_metrics(shadow_findings, production_findings)
            metrics["duration_seconds"] = duration

            # Build output record
            record = {
                "date": target_date,
                "task_id": task_id,
                "task_type": task_type,
                "input": input_path,
                "topology": topo_name,
                "agents_dispatched": [a.split(":")[-1] for a in topo_agents],
                "agents_completed": agents_completed,
                "metrics": metrics,
                "production_baseline": {
                    "agents_used": len(prod_agents),
                    "total_findings": len(production_findings),
                    "p0_findings": prod_p0_count,
                    "p1_findings": prod_p1_count
                }
            }

            # Append to JSONL
            with RESULTS_FILE.open("a") as f:
                f.write(json.dumps(record) + "\n")

            print(f"  Completed: {len(agents_completed)}/{len(topo_agents)} agents", file=sys.stderr)
            print(f"  Recall: {metrics['recall']}, Precision: {metrics['precision']}", file=sys.stderr)

    print(f"\nResults appended to {RESULTS_FILE}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run topology experiments on production flux-drive reviews"
    )
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD), default: yesterday"
    )
    parser.add_argument(
        "--topologies",
        help="Comma-separated topology names (default: all from topologies.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without running agents"
    )
    parser.add_argument(
        "--project",
        help="Project root directory (default: current directory)"
    )

    args = parser.parse_args()

    # Parse date
    if args.date:
        try:
            target_date_dt = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
            target_date = target_date_dt.strftime("%Y-%m-%d")
        except ValueError:
            print(f"ERROR: Invalid date '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

    # Parse project path
    project_root = Path(args.project).expanduser().resolve() if args.project else Path.cwd()

    if not project_root.exists():
        print(f"ERROR: Project directory not found: {project_root}", file=sys.stderr)
        sys.exit(1)

    # Parse topologies
    if args.topologies:
        topology_names = [t.strip() for t in args.topologies.split(",") if t.strip()]
    else:
        topologies = load_topologies()
        topology_names = list(topologies.keys())

    # Run experiment
    run_experiment(
        project_root=project_root,
        target_date=target_date,
        topology_names=topology_names,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
