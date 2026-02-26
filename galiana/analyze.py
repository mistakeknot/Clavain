#!/usr/bin/env python3
"""Galiana KPI analyzer.

Reads Clavain telemetry plus optional datasets, computes KPIs, writes:
~/.clavain/galiana-kpis.json
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CLAVAIN_DIR = Path.home() / ".clavain"
TELEMETRY_FILE = CLAVAIN_DIR / "telemetry.jsonl"
KPI_FILE = CLAVAIN_DIR / "galiana-kpis.json"
TOOL_TIME_EVENTS_FILE = Path.home() / ".claude" / "tool-time" / "events.jsonl"


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse ISO string or unix seconds/milliseconds to UTC datetime."""
    try:
        if isinstance(raw, (int, float)):
            ts = raw / 1000 if raw > 1_000_000_000_000 else raw
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(raw, str) and raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None
    return None


def parse_date_arg(value: str) -> datetime:
    """Parse YYYY-MM-DD as UTC midnight."""
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def extract_session_id(event_id: str) -> str:
    """Extract session id from tool-time event id (uuid-seq)."""
    if "-" not in event_id:
        return event_id
    sid, tail = event_id.rsplit("-", 1)
    return sid if tail.isdigit() else event_id


def safe_rate(numerator: int, denominator: int) -> float | None:
    """Null-safe ratio."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


from utils import iter_jsonl


def load_telemetry_events(
    since: datetime,
    until: datetime,
    bead_filter: str | None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load telemetry events in period; optionally filter to one bead.

    Returns (events, session_to_bead).
    """
    events: list[dict[str, Any]] = []
    session_to_bead: dict[str, str] = {}

    for event in iter_jsonl(TELEMETRY_FILE):
        ts = parse_timestamp(event.get("timestamp"))
        if ts is None or ts < since or ts > until:
            continue

        event["_ts"] = ts
        events.append(event)

        sid = str(event.get("session_id", "")).strip()
        bead = str(event.get("bead", "")).strip()
        if sid and bead:
            session_to_bead[sid] = bead

    if not bead_filter:
        return events, session_to_bead

    filtered: list[dict[str, Any]] = []
    for event in events:
        if event.get("bead") == bead_filter:
            filtered.append(event)
            continue
        sid = str(event.get("session_id", "")).strip()
        if sid and session_to_bead.get(sid) == bead_filter:
            filtered.append(event)

    filtered_sessions = {sid: bead for sid, bead in session_to_bead.items() if bead == bead_filter}
    return filtered, filtered_sessions


def load_tool_time_events(since: datetime, until: datetime) -> list[dict[str, Any]] | None:
    """Load PreToolUse/ToolUse events in period, or None if unavailable."""
    if not TOOL_TIME_EVENTS_FILE.exists():
        return None

    events: list[dict[str, Any]] = []
    for event in iter_jsonl(TOOL_TIME_EVENTS_FILE):
        if event.get("event") not in {"PreToolUse", "ToolUse"}:
            continue
        ts = parse_timestamp(event.get("ts"))
        if ts is None or ts < since or ts > until:
            continue
        event["_ts"] = ts
        event["_session_id"] = extract_session_id(str(event.get("id", "")))
        events.append(event)
    return events


def find_findings_files(project_root: Path) -> list[Path]:
    """Discover docs/research/flux-drive/**/findings.json under project."""
    pattern = project_root / "**" / "docs" / "research" / "flux-drive" / "**" / "findings.json"
    return sorted({Path(p).resolve() for p in glob.glob(str(pattern), recursive=True)})


def parse_reviewed_date(value: Any) -> datetime | None:
    """Parse findings reviewed date (YYYY-MM-DD or ISO timestamp)."""
    if not isinstance(value, str) or not value:
        return None
    ts = parse_timestamp(value)
    if ts is not None:
        return ts
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_findings_docs(files: list[Path], since: datetime, until: datetime) -> list[dict[str, Any]]:
    """Load findings.json docs filtered by reviewed date when present."""
    docs: list[dict[str, Any]] = []
    for file_path in files:
        try:
            doc = json.loads(file_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue

        reviewed = parse_reviewed_date(doc.get("reviewed"))
        if reviewed is not None and (reviewed < since or reviewed > until):
            continue

        doc["_file"] = str(file_path)
        docs.append(doc)
    return docs


def compute_defect_escape_rate(events: list[dict[str, Any]]) -> tuple[dict[str, Any], set[str], int]:
    """Defect escape rate = defect reports / unique beads that reached done."""
    defects = sum(1 for e in events if e.get("event") == "defect_report")
    shipped = {
        str(e.get("bead", "")).strip()
        for e in events
        if e.get("event") == "phase_transition"
        and e.get("phase") == "done"
        and str(e.get("bead", "")).strip()
    }
    return ({"value": safe_rate(defects, len(shipped)), "numerator": defects, "denominator": len(shipped)}, shipped, defects)


def compute_human_override_rate(events: list[dict[str, Any]]) -> tuple[dict[str, Any], int, int]:
    """Override rate = gate_enforce(decision=skip) / gate_enforce(total)."""
    gate_events = [e for e in events if e.get("event") == "gate_enforce"]
    total = len(gate_events)
    skipped = sum(1 for e in gate_events if str(e.get("decision", "")).lower() == "skip")

    tier_totals: Counter[str] = Counter()
    tier_skips: Counter[str] = Counter()
    for event in gate_events:
        tier = str(event.get("tier") or "unknown")
        tier_totals[tier] += 1
        if str(event.get("decision", "")).lower() == "skip":
            tier_skips[tier] += 1

    by_type: dict[str, dict[str, Any]] = {}
    for tier in sorted(tier_totals):
        num = tier_skips[tier]
        denom = tier_totals[tier]
        by_type[tier] = {"value": safe_rate(num, denom), "numerator": num, "denominator": denom}

    return ({"value": safe_rate(skipped, total), "numerator": skipped, "denominator": total, "by_type": by_type}, skipped, total)


def _find_cost_query_script() -> str | None:
    """Locate interstat cost-query.sh in standard paths."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "interverse" / "interstat" / "scripts" / "cost-query.sh",
        Path.home() / ".claude" / "plugins" / "cache" / "interagency-marketplace" / "interstat",
    ]
    def _parse_semver(name: str) -> tuple[int, ...]:
        """Parse '0.2.6' into (0, 2, 6) for proper numeric sorting."""
        try:
            return tuple(int(p) for p in name.split("."))
        except (ValueError, AttributeError):
            return (0,)

    for c in candidates:
        if c.is_dir():
            # Plugin cache: find latest version dir (semver sort, not lexicographic)
            version_dirs = [e for e in c.iterdir() if e.is_dir()]
            version_dirs.sort(key=lambda e: _parse_semver(e.name), reverse=True)
            for entry in version_dirs:
                script = entry / "scripts" / "cost-query.sh"
                if script.exists():
                    return str(script)
        elif c.exists():
            return str(c)
    return None


def _query_interstat_tokens(shipped_bead_ids: set[str]) -> dict[str, Any] | None:
    """Query real token data from interstat via cost-query.sh."""
    script = _find_cost_query_script()
    if not script:
        return None

    try:
        result = subprocess.run(
            ["bash", script, "by-bead"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        rows = json.loads(result.stdout.strip() or "[]")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None

    if not rows:
        return None

    # Correlate with shipped beads
    correlated = [r for r in rows if r.get("bead_id") in shipped_bead_ids]
    if not correlated:
        return None

    token_values = sorted(r.get("tokens", 0) for r in correlated)
    n = len(token_values)
    total = sum(token_values)
    input_total = sum(r.get("input_tokens", 0) for r in correlated)
    output_total = sum(r.get("output_tokens", 0) for r in correlated)

    return {
        "avg_tokens_per_landed_change": round(total / n),
        "median_tokens_per_landed_change": token_values[min(n // 2, n - 1)],
        "p90_tokens_per_landed_change": token_values[min(n * 90 // 100, n - 1)],
        "total_tokens": total,
        "input_tokens": input_total,
        "output_tokens": output_total,
        "beads_with_token_data": n,
        "token_data_coverage_pct": round(n / len(shipped_bead_ids) * 100, 1) if shipped_bead_ids else 0,
    }


def compute_cost_per_landed_change(
    tool_events: list[dict[str, Any]] | None,
    shipped_beads: set[str],
    bead_sessions: set[str],
) -> dict[str, Any]:
    """Compute cost per shipped bead using real token data (preferred) or tool-time proxy."""
    if not shipped_beads:
        return {"avg_tools": None, "avg_sessions": None, "note": "no shipped beads in selected period"}

    # Try real token data from interstat first
    token_data = _query_interstat_tokens(shipped_beads)
    if token_data is not None:
        result: dict[str, Any] = {**token_data, "source": "interstat"}
        # Also include tool-time proxy for comparison if available
        if tool_events is not None:
            result["avg_tools"] = round(len(tool_events) / len(shipped_beads), 4)
        return result

    # Fall back to tool-time proxy
    if tool_events is None:
        return {"avg_tools": None, "avg_sessions": None, "note": "tool-time data not available", "source": "none"}

    scoped = tool_events
    note: str | None = None
    if bead_sessions:
        matched = [e for e in tool_events if e.get("_session_id") in bead_sessions]
        if matched:
            scoped = matched
        else:
            note = "no telemetry session links to tool-time events; used full period"

    tool_count = len(scoped)
    session_count = len({str(e.get("_session_id", "")).strip() for e in scoped if str(e.get("_session_id", "")).strip()})
    shipped_count = len(shipped_beads)

    result = {
        "avg_tools": round(tool_count / shipped_count, 4),
        "avg_sessions": round(session_count / shipped_count, 4),
        "source": "tool-time",
    }
    if note:
        result["note"] = note
    return result


def compute_time_to_first_signal() -> dict[str, Any]:
    """Current schema placeholder until signal events include bead ids."""
    return {
        "avg_seconds": None,
        "p50": None,
        "p90": None,
        "note": "signal events don't link to beads yet",
    }


def extract_finding_agents(finding: dict[str, Any]) -> list[str]:
    """Normalize agents from either `agent` or `agents` fields."""
    agents: list[str] = []

    raw_agents = finding.get("agents")
    if isinstance(raw_agents, list):
        agents.extend([a.strip() for a in raw_agents if isinstance(a, str) and a.strip()])
    elif isinstance(raw_agents, str):
        agents.extend([a.strip() for a in raw_agents.split(",") if a.strip()])

    raw_agent = finding.get("agent")
    if isinstance(raw_agent, str):
        agents.extend([a.strip() for a in raw_agent.split(",") if a.strip()])

    deduped: list[str] = []
    seen = set()
    for agent in agents:
        if agent not in seen:
            seen.add(agent)
            deduped.append(agent)
    return deduped


def compute_findings_metrics(findings_docs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """Compute redundant work ratio and agent scorecard."""
    total = 0
    convergent = 0
    scorecard: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"findings": 0, "p0_findings": 0, "p1_findings": 0})

    for doc in findings_docs:
        findings = doc.get("findings")
        if not isinstance(findings, list):
            continue

        for finding in findings:
            if not isinstance(finding, dict):
                continue
            total += 1

            try:
                convergence = int(finding.get("convergence", 1))
            except (TypeError, ValueError):
                convergence = 1
            if convergence > 1:
                convergent += 1

            severity = str(finding.get("severity", "")).upper()
            for agent in extract_finding_agents(finding):
                scorecard[agent]["findings"] += 1
                if severity == "P0":
                    scorecard[agent]["p0_findings"] += 1
                if severity == "P1":
                    scorecard[agent]["p1_findings"] += 1

    ratio = {"value": safe_rate(convergent, total), "convergent": convergent, "total": total}
    return ratio, dict(sorted(scorecard.items()))


TOPOLOGY_RESULTS_FILE = CLAVAIN_DIR / "topology-results.jsonl"
EVAL_RESULTS_FILE = CLAVAIN_DIR / "eval-results.jsonl"


def load_topology_results(since: datetime, until: datetime) -> list[dict[str, Any]]:
    """Load topology experiment results from topology-results.jsonl."""
    if not TOPOLOGY_RESULTS_FILE.exists():
        return []
    results = []
    for record in iter_jsonl(TOPOLOGY_RESULTS_FILE):
        date_str = record.get("date", "")
        ts = parse_timestamp(date_str)
        if ts is None:
            continue
        if ts < since or ts > until:
            continue
        results.append(record)
    return results


def compute_topology_efficiency(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-topology recall statistics."""
    if not results:
        return {"available": False, "note": "No topology experiment data yet. Run /clavain:galiana experiment."}

    by_topology: dict[str, list[float]] = defaultdict(list)
    by_task_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for r in results:
        topology = r.get("topology", "unknown")
        recall = r.get("metrics", {}).get("recall")
        task_type = r.get("task_type", "unknown")
        if recall is not None:
            by_topology[topology].append(recall)
            by_task_type[task_type][topology].append(recall)

    summary = {}
    for topo in sorted(by_topology):
        values = by_topology[topo]
        summary[topo] = {
            "avg_recall": round(sum(values) / len(values), 4),
            "samples": len(values),
        }

    breakdown = {}
    for task_type in sorted(by_task_type):
        breakdown[task_type] = {}
        for topo in sorted(by_task_type[task_type]):
            values = by_task_type[task_type][topo]
            breakdown[task_type][topo] = {
                "avg_recall": round(sum(values) / len(values), 4),
                "samples": len(values),
            }

    return {
        "available": True,
        "summary": summary,
        "by_task_type": breakdown,
        "total_experiments": len(results),
    }


def load_eval_results(since: datetime, until: datetime) -> list[dict[str, Any]]:
    """Load eval harness results from eval-results.jsonl."""
    if not EVAL_RESULTS_FILE.exists():
        return []
    results = []
    for record in iter_jsonl(EVAL_RESULTS_FILE):
        date_str = record.get("date", "")
        ts = parse_timestamp(date_str)
        if ts is None:
            continue
        if ts < since or ts > until:
            continue
        results.append(record)
    return results


def compute_eval_health(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute eval harness health — property pass rates and recall trends."""
    if not results:
        return {"available": False, "note": "No eval results yet. Run /clavain:galiana eval."}

    total_properties = sum(r.get("total_properties", 0) for r in results)
    passed_properties = sum(r.get("passed_properties", 0) for r in results)
    overall_pass_rate = safe_rate(passed_properties, total_properties)

    recalls = [r.get("avg_recall") for r in results if r.get("avg_recall") is not None]
    avg_recall = round(sum(recalls) / len(recalls), 4) if recalls else None

    by_fixture: dict[str, dict[str, Any]] = defaultdict(lambda: {"runs": 0, "passed": 0, "total": 0, "recalls": []})
    for r in results:
        fixture = r.get("fixture", "unknown")
        by_fixture[fixture]["runs"] += 1
        by_fixture[fixture]["passed"] += r.get("passed_properties", 0)
        by_fixture[fixture]["total"] += r.get("total_properties", 0)
        recall = r.get("avg_recall")
        if recall is not None:
            by_fixture[fixture]["recalls"].append(recall)

    fixture_summary = {}
    for fixture in sorted(by_fixture):
        data = by_fixture[fixture]
        fixture_recalls = data["recalls"]
        fixture_summary[fixture] = {
            "pass_rate": safe_rate(data["passed"], data["total"]),
            "avg_recall": round(sum(fixture_recalls) / len(fixture_recalls), 4) if fixture_recalls else None,
            "runs": data["runs"],
        }

    return {
        "available": True,
        "overall_pass_rate": overall_pass_rate,
        "avg_recall": avg_recall,
        "total_runs": len(results),
        "by_fixture": fixture_summary,
    }


def run_analysis(since: datetime, project: Path, bead_filter: str | None = None) -> dict[str, Any]:
    """Compute full KPI payload."""
    until = datetime.now(timezone.utc)

    telemetry_events, _session_to_bead = load_telemetry_events(since, until, bead_filter)
    defect_escape_rate, shipped_beads, defect_count = compute_defect_escape_rate(telemetry_events)
    human_override_rate, gate_skip_count, gate_total = compute_human_override_rate(telemetry_events)

    bead_sessions = {
        str(e.get("session_id", "")).strip()
        for e in telemetry_events
        if e.get("event") in {"workflow_start", "workflow_end"} and str(e.get("session_id", "")).strip()
    }

    tool_events = load_tool_time_events(since, until)
    cost_per_landed_change = compute_cost_per_landed_change(tool_events, shipped_beads, bead_sessions)

    findings_files = find_findings_files(project)
    findings_docs = load_findings_docs(findings_files, since, until)
    redundant_work_ratio, agent_scorecard = compute_findings_metrics(findings_docs)

    topology_results = load_topology_results(since, until)
    topology_efficiency = compute_topology_efficiency(topology_results)

    eval_results = load_eval_results(since, until)
    eval_health = compute_eval_health(eval_results)

    advisories: list[dict[str, str]] = [{
        "level": "info",
        "message": "Time-to-first-signal KPI unavailable: signal events don't include bead IDs. Will be enabled in v0.2.",
    }]

    if defect_count == 0:
        advisories.append({
            "level": "info",
            "message": "No defect reports found. Use /clavain:galiana report-defect to log escaped issues.",
        })
    if gate_skip_count == 0:
        advisories.append({"level": "info", "message": "No gate overrides detected."})
    if tool_events is None:
        advisories.append({"level": "info", "message": "Install tool-time for cost metrics."})
    if not findings_files:
        advisories.append({"level": "info", "message": "No flux-drive findings for redundancy analysis."})
    if not topology_results:
        advisories.append({
            "level": "info",
            "message": "No topology experiment data. Run /clavain:galiana experiment to start collecting.",
        })
    if not eval_results:
        advisories.append({
            "level": "info",
            "message": "No eval harness results. Run /clavain:galiana eval to test golden fixtures.",
        })

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": {"start": since.strftime("%Y-%m-%d"), "end": until.strftime("%Y-%m-%d")},
        "summary": {
            "total_beads_shipped": len(shipped_beads),
            "total_events": len(telemetry_events),
            "total_defects_reported": defect_count,
            "total_gate_enforcements": gate_total,
        },
        "kpis": {
            "defect_escape_rate": defect_escape_rate,
            "human_override_rate": human_override_rate,
            "cost_per_landed_change": cost_per_landed_change,
            "time_to_first_signal": compute_time_to_first_signal(),
            "redundant_work_ratio": redundant_work_ratio,
            "topology_efficiency": topology_efficiency,
            "eval_health": eval_health,
        },
        "agent_scorecard": agent_scorecard,
        "advisories": advisories,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Galiana KPI metrics from telemetry")
    parser.add_argument("--since", type=parse_date_arg, help="Start date (YYYY-MM-DD), default: 30 days ago")
    parser.add_argument("--project", help="Project path for findings discovery (default: current directory)")
    parser.add_argument("--bead", help="Filter telemetry to a specific bead ID")
    args = parser.parse_args()

    since = args.since or (datetime.now(timezone.utc) - timedelta(days=30))
    project = Path(args.project).expanduser().resolve() if args.project else Path.cwd()

    result = run_analysis(since=since, project=project, bead_filter=args.bead)
    KPI_FILE.parent.mkdir(parents=True, exist_ok=True)
    KPI_FILE.write_text(json.dumps(result, indent=2) + "\n")
    print(str(KPI_FILE))


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
