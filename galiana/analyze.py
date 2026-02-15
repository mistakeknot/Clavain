#!/usr/bin/env python3
"""Galiana KPI analyzer.

Reads Clavain telemetry plus optional datasets, computes KPIs, writes:
~/.clavain/galiana-kpis.json
"""

from __future__ import annotations

import argparse
import glob
import json
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


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL records; skip blank and invalid lines."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


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
    pattern = project_root / "docs" / "research" / "flux-drive" / "**" / "findings.json"
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


def compute_cost_per_landed_change(
    tool_events: list[dict[str, Any]] | None,
    shipped_beads: set[str],
    bead_sessions: set[str],
) -> dict[str, Any]:
    """Compute avg tool calls and avg sessions per shipped bead."""
    if tool_events is None:
        return {"avg_tools": None, "avg_sessions": None, "note": "tool-time data not available"}
    if not shipped_beads:
        return {"avg_tools": None, "avg_sessions": None, "note": "no shipped beads in selected period"}

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

    result: dict[str, Any] = {
        "avg_tools": round(tool_count / shipped_count, 4),
        "avg_sessions": round(session_count / shipped_count, 4),
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
