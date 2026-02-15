#!/usr/bin/env python3
"""Galiana property-based agent evaluation harness.

Runs golden fixtures through agent topologies, checks property assertions,
scores via interbench, and detects regressions.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
from pathlib import Path
from time import time
from typing import Any

from utils import normalize_title, titles_match

CLAVAIN_DIR = Path.home() / ".clavain"
EVAL_RESULTS_FILE = CLAVAIN_DIR / "eval-results.jsonl"
EVAL_RUNS_DIR = CLAVAIN_DIR / "eval-runs"

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def load_fixtures(golden_dir: Path, fixture_filter: str = "*") -> list[dict]:
    """Scan golden_dir for directories containing meta.json + baseline.json + input/.

    Args:
        golden_dir: Directory containing golden fixture subdirectories
        fixture_filter: fnmatch pattern to filter fixtures

    Returns:
        List of dicts: {"name": str, "path": Path, "meta": dict, "baseline": dict}
    """
    fixtures: list[dict] = []

    if not golden_dir.exists():
        return fixtures

    for candidate in sorted(golden_dir.iterdir()):
        if not candidate.is_dir():
            continue

        # Check pattern match
        if not fnmatch.fnmatch(candidate.name, fixture_filter):
            continue

        meta_file = candidate / "meta.json"
        baseline_file = candidate / "baseline.json"
        input_dir = candidate / "input"

        if not meta_file.exists() or not baseline_file.exists() or not input_dir.exists():
            continue

        try:
            meta = json.loads(meta_file.read_text())
            baseline = json.loads(baseline_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: Skipping {candidate.name}: {e}", file=sys.stderr)
            continue

        fixtures.append({
            "name": candidate.name,
            "path": candidate,
            "meta": meta,
            "baseline": baseline
        })

    return fixtures


def load_topologies() -> dict:
    """Read topologies.json from same directory as this script.

    Returns:
        Parsed topology dict
    """
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


def find_interbench() -> Path | None:
    """Look for interbench binary.

    Returns:
        Path to interbench binary or None if not found
    """
    # Try monorepo location first
    script_dir = Path(__file__).parent
    monorepo_path = script_dir.parent.parent.parent / "infra" / "interbench" / "interbench"

    if monorepo_path.exists() and monorepo_path.is_file():
        return monorepo_path

    # Try PATH
    which_result = shutil.which("interbench")
    if which_result:
        return Path(which_result)

    return None


def run_fixture_eval(
    fixture: dict,
    topology_name: str,
    topology_agents: list[str],
    script_dir: Path,
    project_dir: Path
) -> dict:
    """Run fixture evaluation with specified topology.

    Args:
        fixture: Fixture dict from load_fixtures
        topology_name: Name of topology being tested
        topology_agents: List of agent identifiers
        script_dir: Directory containing shadow-review.sh
        project_dir: Project root for running agents

    Returns:
        Dict with findings, agents_completed, duration_seconds
    """
    fixture_name = fixture["name"]
    fixture_path = fixture["path"]

    # Create output directory
    run_dir = EVAL_RUNS_DIR / fixture_name / topology_name
    run_dir.mkdir(parents=True, exist_ok=True)

    shadow_script = script_dir / "shadow-review.sh"
    if not shadow_script.exists():
        print(f"WARN: shadow-review.sh not found at {shadow_script}", file=sys.stderr)
        return {"findings": [], "agents_completed": [], "duration_seconds": 0}

    all_findings: list[dict[str, Any]] = []
    agents_completed: list[str] = []

    # Determine input path
    meta = fixture["meta"]
    input_rel = meta.get("input", "input/")
    if not input_rel.startswith("/"):
        input_path = str(fixture_path / input_rel)
    else:
        input_path = input_rel

    start_time = time()

    for agent in topology_agents:
        # Extract agent name (strip prefix)
        agent_name = agent.split(":")[-1]
        output_file = run_dir / f"{agent_name}.json"

        try:
            result = subprocess.run(
                [str(shadow_script), agent, input_path, str(output_file)],
                cwd=project_dir,
                timeout=300,  # 5 minute timeout per agent
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"WARN: Agent {agent_name} exited {result.returncode}", file=sys.stderr)

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

    duration = time() - start_time

    return {
        "findings": all_findings,
        "agents_completed": agents_completed,
        "duration_seconds": duration
    }


def check_properties(findings: list[dict], expected_properties: list[dict]) -> list[dict]:
    """Check property assertions against findings.

    Args:
        findings: List of finding dicts from agents
        expected_properties: List of property dicts from meta.json

    Returns:
        List of property check results
    """
    results: list[dict] = []

    for prop in expected_properties:
        # Filter findings by agent if specified
        relevant_findings = findings
        if "agent" in prop:
            agent_filter = prop["agent"]
            relevant_findings = []
            for finding in findings:
                # Check agents field (could be list or single agent string)
                finding_agents = finding.get("agents", [])
                if isinstance(finding_agents, str):
                    finding_agents = [finding_agents]

                # Also check agent field
                single_agent = finding.get("agent", "")
                if single_agent:
                    if isinstance(single_agent, str):
                        finding_agents.append(single_agent)

                # Match if agent_filter appears in any agent name (substring match)
                if any(agent_filter in agent for agent in finding_agents):
                    relevant_findings.append(finding)

        passed = False
        actual: int | str = 0
        expected: int | str = ""

        # Check min_findings
        if "min_findings" in prop:
            min_count = prop["min_findings"]
            actual_count = len(relevant_findings)
            passed = actual_count >= min_count
            actual = actual_count
            expected = f">={min_count}"

        # Check must_contain_keyword
        if "must_contain_keyword" in prop:
            keyword = prop["must_contain_keyword"].lower()
            matching_count = sum(
                1 for f in relevant_findings
                if keyword in str(f.get("title", "")).lower()
            )
            if "min_findings" in prop:
                # Already checked count, now verify keyword
                passed = passed and matching_count > 0
            else:
                passed = matching_count > 0
                actual = matching_count
                expected = f">=1 with '{keyword}'"

        # Check severity_at_least with min_count
        if "severity_at_least" in prop and "min_count" in prop:
            severity_threshold = prop["severity_at_least"].upper()
            min_count = prop["min_count"]

            if severity_threshold not in SEVERITY_ORDER:
                print(f"WARN: Unknown severity {severity_threshold}", file=sys.stderr)
                continue

            threshold_level = SEVERITY_ORDER[severity_threshold]

            # Count findings at or above threshold
            count = 0
            for finding in relevant_findings:
                severity = str(finding.get("severity", "")).upper()
                if severity in SEVERITY_ORDER:
                    if SEVERITY_ORDER[severity] <= threshold_level:
                        count += 1

            passed = count >= min_count
            actual = count
            expected = f">={min_count} at {severity_threshold}+"

        # Warn if no recognized assertion type was found
        assertion_found = (
            "min_findings" in prop
            or "must_contain_keyword" in prop
            or ("severity_at_least" in prop and "min_count" in prop)
        )

        if not assertion_found:
            print(f"WARN: Property has no recognized assertion type, skipping: {prop}", file=sys.stderr)
            continue

        results.append({
            "property": prop,
            "passed": passed,
            "actual": actual,
            "expected": expected
        })

    return results


def compute_baseline_metrics(
    findings: list[dict],
    baseline_findings: list[dict]
) -> dict:
    """Compute overlap metrics vs baseline (recall, precision, etc).

    Args:
        findings: Actual findings from evaluation run
        baseline_findings: Expected findings from baseline.json

    Returns:
        Dict with recall, precision, unique_discoveries, etc
    """
    if not baseline_findings:
        return {
            "recall": None,
            "precision": None,
            "unmatched_findings": len(findings),
            "false_positive_rate": None,
            "total_findings": len(findings),
            "p0_findings": sum(1 for f in findings if str(f.get("severity", "")).upper() == "P0"),
            "p1_findings": sum(1 for f in findings if str(f.get("severity", "")).upper() == "P1")
        }

    # Extract P0/P1 baseline findings (high-severity only)
    baseline_p0_p1 = [
        f for f in baseline_findings
        if str(f.get("severity", "")).upper() in {"P0", "P1"}
    ]

    # Match findings to baseline
    matched_baseline = set()
    matched_actual = set()

    for i, actual_f in enumerate(findings):
        actual_title = str(actual_f.get("title", ""))
        for j, baseline_f in enumerate(baseline_p0_p1):
            baseline_title = str(baseline_f.get("title", ""))
            if titles_match(actual_title, baseline_title):
                matched_baseline.add(j)
                matched_actual.add(i)
                break

    # Compute metrics — filter actual findings to P0/P1 for precision (must match baseline severity class)
    findings_p0_p1 = [f for f in findings if str(f.get("severity", "")).upper() in {"P0", "P1"}]
    recall = len(matched_baseline) / len(baseline_p0_p1) if baseline_p0_p1 else None
    precision = len(matched_actual) / len(findings_p0_p1) if findings_p0_p1 else None
    unmatched_findings = len(findings) - len(matched_actual)

    # False positive rate among P0/P1 findings
    false_positive_rate = (len(findings_p0_p1) - len(matched_actual)) / len(findings_p0_p1) if findings_p0_p1 else None

    # Count severity breakdowns
    p0_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "P0")
    p1_count = sum(1 for f in findings if str(f.get("severity", "")).upper() == "P1")

    return {
        "recall": round(recall, 4) if recall is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "unmatched_findings": unmatched_findings,
        "false_positive_rate": round(false_positive_rate, 4) if false_positive_rate is not None else None,
        "total_findings": len(findings),
        "p0_findings": p0_count,
        "p1_findings": p1_count
    }


def score_via_interbench(
    fixture_name: str,
    topology: str,
    metrics: dict,
    property_results: list[dict],
    interbench_bin: Path
) -> str | None:
    """Score run via interbench.

    Args:
        fixture_name: Name of fixture
        topology: Topology name
        metrics: Computed metrics dict
        property_results: Property check results
        interbench_bin: Path to interbench binary

    Returns:
        Run ID string or None on failure
    """
    try:
        # Create run
        result = subprocess.run(
            [
                str(interbench_bin),
                "run",
                "-m", f"fixture={fixture_name}",
                "-m", f"topology={topology}",
                "echo",
                f"eval-{fixture_name}-{topology}"
            ],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            print(f"WARN: interbench run failed: {result.stderr[:200]}", file=sys.stderr)
            return None

        # Parse run ID from last non-empty line
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return None
        run_id = lines[-1]

        # Score metrics
        if metrics.get("recall") is not None:
            subprocess.run(
                [str(interbench_bin), "score", run_id, "recall", str(metrics["recall"])],
                capture_output=True,
                check=False
            )

        if metrics.get("precision") is not None:
            subprocess.run(
                [str(interbench_bin), "score", run_id, "precision", str(metrics["precision"])],
                capture_output=True,
                check=False
            )

        # Property pass rate
        total_props = len(property_results)
        passed_props = sum(1 for p in property_results if p["passed"])
        if total_props > 0:
            pass_rate = passed_props / total_props
            subprocess.run(
                [str(interbench_bin), "score", run_id, "property_pass_rate", str(pass_rate)],
                capture_output=True,
                check=False
            )

        return run_id

    except (OSError, subprocess.SubprocessError) as e:
        print(f"WARN: interbench scoring failed: {e}", file=sys.stderr)
        return None


def detect_regression(
    current_run_id: str,
    previous_run_id: str,
    interbench_bin: Path
) -> list[dict]:
    """Compare two interbench runs and detect regressions.

    Args:
        current_run_id: Current run ID
        previous_run_id: Previous run ID to compare against
        interbench_bin: Path to interbench binary

    Returns:
        List of regression dicts
    """
    try:
        result = subprocess.run(
            [str(interbench_bin), "compare", current_run_id, previous_run_id],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            print(f"WARN: interbench compare failed: {result.stderr[:200]}", file=sys.stderr)
            return []

        # Parse output for regressions (simplified - actual format may vary)
        regressions: list[dict] = []
        for line in result.stdout.splitlines():
            # Look for lines indicating score deltas
            if "worse" in line.lower() or "regression" in line.lower():
                regressions.append({
                    "description": line.strip(),
                    "threshold_exceeded": True
                })

        return regressions

    except (OSError, subprocess.SubprocessError) as e:
        print(f"WARN: regression detection failed: {e}", file=sys.stderr)
        return []


def append_eval_result(
    fixture_name: str,
    topology: str,
    property_results: list[dict],
    metrics: dict,
    duration: float
) -> None:
    """Append evaluation result to JSONL log.

    Args:
        fixture_name: Name of fixture
        topology: Topology name
        property_results: Property check results
        metrics: Computed metrics
        duration: Duration in seconds
    """
    from datetime import datetime, timezone

    total_properties = len(property_results)
    passed_properties = sum(1 for p in property_results if p["passed"])
    property_pass_rate = passed_properties / total_properties if total_properties > 0 else 0.0

    record = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "fixture": fixture_name,
        "topology": topology,
        "total_properties": total_properties,
        "passed_properties": passed_properties,
        "property_pass_rate": round(property_pass_rate, 4),
        "avg_recall": metrics.get("recall"),
        "precision": metrics.get("precision"),
        "false_positive_rate": metrics.get("false_positive_rate"),
        "duration_seconds": int(duration)
    }

    EVAL_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EVAL_RESULTS_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")


def run_eval(
    golden_dir: Path,
    topologies: dict,
    fixture_filter: str,
    dry_run: bool,
    no_interbench: bool,
    project_dir: Path,
    previous_run: str | None
) -> int:
    """Main evaluation orchestrator.

    Args:
        golden_dir: Directory containing golden fixtures
        topologies: Topology definitions
        fixture_filter: fnmatch pattern for fixtures
        dry_run: Print summary without running
        no_interbench: Skip interbench scoring
        project_dir: Project root directory
        previous_run: Previous run ID for regression detection

    Returns:
        Exit code (0=pass, 1=property fail, 2=regression)
    """
    script_dir = Path(__file__).parent

    # Load fixtures
    fixtures = load_fixtures(golden_dir, fixture_filter)

    if not fixtures:
        print(f"No fixtures found in {golden_dir} matching '{fixture_filter}'", file=sys.stderr)
        return 0

    print(f"Loaded {len(fixtures)} fixtures", file=sys.stderr)

    if dry_run:
        print(f"\nDry run: would execute {len(fixtures) * len(topologies)} evaluations", file=sys.stderr)
        print(f"Fixtures: {', '.join(f['name'] for f in fixtures)}", file=sys.stderr)
        print(f"Topologies: {', '.join(topologies.keys())}", file=sys.stderr)
        return 0

    # Find interbench
    interbench_bin = None if no_interbench else find_interbench()
    if not no_interbench and interbench_bin is None:
        print("WARN: interbench not found, skipping benchmark scoring", file=sys.stderr)

    # Track results for summary
    all_results: list[dict] = []
    property_failures = 0
    low_recall_count = 0

    # Run evaluations
    total_runs = len(fixtures) * len(topologies)
    run_count = 0

    for fixture in fixtures:
        fixture_name = fixture["name"]
        meta = fixture["meta"]
        baseline = fixture["baseline"]
        baseline_findings = baseline.get("findings", [])
        expected_properties = meta.get("expected_properties", [])

        for topo_name in topologies:
            run_count += 1
            print(f"\n[{run_count}/{total_runs}] Running {fixture_name} with {topo_name}...", file=sys.stderr)

            topo_config = topologies[topo_name]
            topo_agents = topo_config.get("agents", [])

            # Run evaluation
            eval_result = run_fixture_eval(
                fixture=fixture,
                topology_name=topo_name,
                topology_agents=topo_agents,
                script_dir=script_dir,
                project_dir=project_dir
            )

            findings = eval_result["findings"]
            agents_completed = eval_result["agents_completed"]
            duration = eval_result["duration_seconds"]

            # Check properties
            property_results = check_properties(findings, expected_properties)

            # Compute metrics
            metrics = compute_baseline_metrics(findings, baseline_findings)

            # Score via interbench
            run_id = None
            if interbench_bin:
                run_id = score_via_interbench(
                    fixture_name=fixture_name,
                    topology=topo_name,
                    metrics=metrics,
                    property_results=property_results,
                    interbench_bin=interbench_bin
                )

            # Append to JSONL
            append_eval_result(
                fixture_name=fixture_name,
                topology=topo_name,
                property_results=property_results,
                metrics=metrics,
                duration=duration
            )

            # Track for summary
            passed_props = sum(1 for p in property_results if p["passed"])
            total_props = len(property_results)
            if passed_props < total_props:
                property_failures += 1

            recall = metrics.get("recall")
            if recall is not None and recall < 0.85:
                low_recall_count += 1

            all_results.append({
                "fixture": fixture_name,
                "topology": topo_name,
                "properties": f"{passed_props}/{total_props}",
                "recall": recall,
                "precision": metrics.get("precision"),
                "duration": int(duration)
            })

            print(f"  Completed: {len(agents_completed)}/{len(topo_agents)} agents", file=sys.stderr)
            print(f"  Properties: {passed_props}/{total_props}, Recall: {recall}, Precision: {metrics.get('precision')}", file=sys.stderr)

    # Print summary table
    print("\n" + "="*80)
    print("Eval Results")
    print("="*80)
    print(f"{'Fixture':<24} {'Topo':<6} {'Props':<7} {'Recall':<7} {'Prec':<7} {'Time':<6}")
    print("-"*80)

    for result in all_results:
        recall_str = f"{result['recall']:.2f}" if result['recall'] is not None else "N/A"
        prec_str = f"{result['precision']:.2f}" if result['precision'] is not None else "N/A"

        print(
            f"{result['fixture']:<24} "
            f"{result['topology']:<6} "
            f"{result['properties']:<7} "
            f"{recall_str:<7} "
            f"{prec_str:<7} "
            f"{result['duration']}s"
        )

    print("-"*80)
    print(f"Property Failures: {property_failures}")
    print(f"Recall Below 85%: {low_recall_count} fixtures")

    # Overall stats
    total_props_all = sum(int(r['properties'].split('/')[1]) for r in all_results)
    passed_props_all = sum(int(r['properties'].split('/')[0]) for r in all_results)
    avg_recall = sum(r['recall'] for r in all_results if r['recall'] is not None) / len([r for r in all_results if r['recall'] is not None]) if any(r['recall'] is not None for r in all_results) else 0

    print(f"\nOverall: {passed_props_all}/{total_props_all} properties passed, avg recall {avg_recall:.2f}")
    print(f"\nResults appended to {EVAL_RESULTS_FILE}")

    # Regression detection
    if previous_run and interbench_bin:
        # Note: This is simplified - would need to map fixtures to run IDs
        print("\nRegression detection not fully implemented (needs run ID mapping)", file=sys.stderr)

    # Return appropriate exit code
    if property_failures > 0:
        return 1

    if low_recall_count > 0:
        return 2  # Recall regression

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Property-based agent evaluation harness for Galiana"
    )
    parser.add_argument(
        "--topologies",
        help="Comma-separated topology names (default: T4 only)"
    )
    parser.add_argument(
        "--fixtures",
        default="*",
        help="Fixture filter pattern (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without running agents"
    )
    parser.add_argument(
        "--no-interbench",
        action="store_true",
        help="Skip interbench scoring"
    )
    parser.add_argument(
        "--project",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--previous-run",
        help="Previous run ID for regression detection"
    )

    args = parser.parse_args()

    # Parse topologies
    all_topologies = load_topologies()
    if args.topologies:
        topo_names = [t.strip() for t in args.topologies.split(",") if t.strip()]
        # Validate
        for name in topo_names:
            if name not in all_topologies:
                print(f"ERROR: Unknown topology '{name}'", file=sys.stderr)
                print(f"Available: {', '.join(all_topologies.keys())}", file=sys.stderr)
                sys.exit(1)
        selected_topologies = {name: all_topologies[name] for name in topo_names}
    else:
        # Default to T4 only for speed
        selected_topologies = {"T4": all_topologies["T4"]}

    # Determine paths
    script_dir = Path(__file__).parent
    golden_dir = script_dir / "evals" / "golden"
    project_dir = Path(args.project).expanduser().resolve() if args.project else Path.cwd()

    # Run evaluation
    exit_code = run_eval(
        golden_dir=golden_dir,
        topologies=selected_topologies,
        fixture_filter=args.fixtures,
        dry_run=args.dry_run,
        no_interbench=args.no_interbench,
        project_dir=project_dir,
        previous_run=args.previous_run
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
