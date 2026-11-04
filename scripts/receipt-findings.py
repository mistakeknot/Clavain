#!/usr/bin/env python3
"""Extract observed review finding counts from a dispatch output body.

With --detail the JSON also carries "findings": one record per parsed finding
heading (class, severity, summary, file, line). A heading may carry a class tag
after the severity, e.g. "### [P1] [test-gap] summary text (path/file.py:42)"."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


UNKNOWN = {
    "source": "unknown",
    "P0": None,
    "P1": None,
    "P2": None,
    "P3": None,
    "total": None,
}
ZERO = {"source": "body", "P0": 0, "P1": 0, "P2": 0, "P3": 0, "total": 0}

VERDICT_FINDINGS = re.compile(
    r"^\s*FINDINGS:\s*(\d+)\s*\(\s*"
    r"P0:\s*(\d+)\s*,\s*P1:\s*(\d+)\s*,\s*P2:\s*(\d+)"
    r"(?:\s*,\s*P3:\s*(\d+))?\s*\)\s*$",
    re.IGNORECASE,
)
FINDING_HEADING = re.compile(
    r"^(?:#{1,6}\s+|[-+*]\s+|\d+[.)]\s+)"
    r"(?:"
    r"(?:\*\*|__)?\[?(P[0-3])(?=\]|\s|:|—|–)\]?"
    r"|(?:\*\*|__)?\[(Critical|High|Medium|Low)\]"
    r"|(?:\*\*|__)(Critical|High|Medium|Low)(?=\s+[—–]|:)"
    r")",
    re.IGNORECASE,
)
SEVERITY = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
    "p0": "P0",
    "p1": "P1",
    "p2": "P2",
    "p3": "P3",
}


def visible_lines(body: str) -> list[str]:
    """Return non-fenced lines; fenced examples are not reviewer findings."""
    visible: list[str] = []
    fenced = False
    for line in body.splitlines():
        if re.match(r"^\s*```", line):
            fenced = not fenced
            continue
        if not fenced:
            visible.append(line)
    return visible


def verdict_counts(lines: list[str]) -> dict[str, int | str] | None:
    active = False
    matches: list[re.Match[str]] = []
    for line in lines:
        if line.strip() == "--- VERDICT ---":
            active = True
            continue
        if active and line.strip() == "---":
            active = False
            continue
        if active and (match := VERDICT_FINDINGS.match(line)):
            matches.append(match)
    if not matches:
        return None
    match = matches[-1]
    counts = {
        "source": "verdict",
        "P0": int(match.group(2)),
        "P1": int(match.group(3)),
        "P2": int(match.group(4)),
        "P3": int(match.group(5) or 0),
    }
    # Severity counts are the evidence; repair inconsistent stated totals using
    # their sum. P3 remains optional and defaults to zero by the receipt contract.
    counts["total"] = sum(counts[key] for key in ("P0", "P1", "P2", "P3"))
    return counts


CLASSES = (
    "logic-correctness",
    "concurrency-ordering",
    "security-trust-boundary",
    "data-integrity-migration",
    "error-handling",
    "test-gap",
    "spec-or-doc-mismatch",
    "performance",
    "style-naming",
    "process-gate",
    "other",
)
CLASS_TAG = re.compile(r"^(?:\*\*|__)?\[([A-Za-z][A-Za-z _-]*)\](?:\*\*|__)?\s*")
FILE_LINE = re.compile(r"`?([A-Za-z0-9_./@+-]+\.[A-Za-z0-9]+|[A-Za-z0-9_./@+-]*/[A-Za-z0-9_.@+-]+)(?::(\d+))?`?(?=[\s,;:)\]]|$)")
SUMMARY_MAX = 200


def heading_findings(lines: list[str]) -> list[dict[str, str]]:
    """Return one {severity, rest} record per finding heading (same rules as
    the historical heading counter, which is now derived from this list)."""
    found: list[dict[str, str]] = []
    nonempty = [line.strip() for line in lines if line.strip()]
    for index, line in enumerate(nonempty):
        match = FINDING_HEADING.match(line)
        if not match:
            continue
        if re.match(r"^(?:\*\*|__)?\s*:\s*(?:0|none|n/?a)\b", line[match.end():], re.IGNORECASE):
            continue
        # A severity section immediately introducing tagged children is not an
        # additional finding — but only when the heading carries no text of
        # its own beyond the tag (e.g. "### P1 findings"). A heading that IS
        # itself a distinct finding (e.g. "### [P1] leak" followed by another
        # finding line) must still be counted; otherwise it silently
        # disappears. Headings otherwise remain the unit of counting.
        trailing = re.sub(r"^[:\-–—\]]+\s*", "", line[match.end():].strip())
        is_bare_heading = trailing == "" or re.match(
            r"(?i)^(?:findings?|items?|issues?)\s*\(?\d*\)?[:.]?$", trailing
        )
        if (
            line.startswith("#")
            and is_bare_heading
            and index + 1 < len(nonempty)
            and FINDING_HEADING.match(nonempty[index + 1])
        ):
            continue
        severity = next(group for group in match.groups() if group is not None)
        found.append({"severity": SEVERITY[severity.lower()], "rest": line[match.end():]})
    return found


def parse_finding(record: dict[str, str]) -> dict[str, str | int | None]:
    """Class, summary, file and line for one finding heading. A missing or
    unlisted class is stored as "other"; nothing is guessed."""
    rest = re.sub(r"^(?:\*\*|__)?[\]:\-–—\s]*", "", record["rest"])
    cls = "other"
    tag = CLASS_TAG.match(rest)
    if tag:
        name = re.sub(r"[\s_]+", "-", tag.group(1).strip().lower())
        if name in CLASSES:
            cls = name
        rest = rest[tag.end():]
    rest = re.sub(r"^[\]:\-–—\s]+", "", rest)
    summary = re.sub(r"\s+", " ", re.sub(r"(?:\*\*|__)", "", rest)).strip()
    file_name: str | None = None
    line_no: int | None = None
    for hit in FILE_LINE.finditer(summary):
        candidate = hit.group(1)
        if hit.group(2) or "/" in candidate or re.search(r"\.(?:sh|py|go|rs|md|ya?ml|json|toml|bats|ts|js)$", candidate):
            file_name = candidate
            line_no = int(hit.group(2)) if hit.group(2) else None
            break
    if len(summary) > SUMMARY_MAX:
        summary = summary[: SUMMARY_MAX - 1].rstrip() + "…"
    return {
        "class": cls,
        "severity": record["severity"],
        "summary": summary,
        "file": file_name,
        "line": line_no,
    }


def heading_counts(lines: list[str]) -> dict[str, int | str] | None:
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    records = heading_findings(lines)
    if not records:
        return None
    for record in records:
        counts[record["severity"]] += 1
    return {"source": "body", **counts, "total": len(records)}


def clean_verdict(lines: list[str]) -> bool:
    joined = "\n".join(lines)
    # This repo's own reviewer vocabulary (skills/interserve-engine/templates/
    # review-agent.md, commands/clavain-review.md) uses "needs-changes" and
    # "risky" as verdict values, and both hyphen/underscore/space separators
    # show up across templates ("PASS WITH CHANGES", "CHANGES_REQUESTED").
    if re.search(
        r"\b(?:REVISE|FAIL|REJECT|UNRUN|NEEDS[-_ ]?ATTENTION|NEEDS[-_ ]?CHANGES"
        r"|CHANGES[-_ ]?REQUESTED|RISKY|WITH[-_ ]?CHANGES)\b",
        joined,
        re.IGNORECASE,
    ):
        return False
    if re.search(r"^\s*STATUS:\s*(?:pass|safe)\s*$", joined, re.IGNORECASE | re.MULTILINE):
        return True
    if re.search(r"^\s*VERDICT:\s*(?:CLEAN|PASS|SAFE)\s*$", joined, re.IGNORECASE | re.MULTILINE):
        return True
    final_line = next((line for line in reversed(lines) if line.strip()), "")
    return bool(
        re.search(
            r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:APPROVE|pass)(?:\*\*)?[.!]?\s*$",
            final_line,
            re.IGNORECASE,
        )
    )


def extract(path: Path) -> dict[str, int | str | None]:
    result = extract_detail(path, resolve_conflict=False)
    result.pop("findings", None)
    return result


def extract_detail(path: Path, resolve_conflict: bool = True) -> dict:
    """Counts plus the per-finding list, from one pass over the review body.

    "findings" holds the parsed headings; it is empty when nothing parsed. The
    count fields are exactly those of extract(). When the counts come from a
    verdict block or a clean verdict but no headings parsed, "findings" is
    empty and callers must read "source"/"total" for what was observed.

    When a verdict count block and parsed headings both exist but disagree on
    the total, the headings are the evidence: "source" becomes "conflict",
    "total" and the severity counts come from the headings, and the block's
    stated total is kept in the additive "block_total" field."""
    try:
        body = path.read_text()
    except (OSError, UnicodeError):
        return {**UNKNOWN, "findings": []}
    lines = visible_lines(body)
    counts = verdict_counts(lines) or heading_counts(lines) or (ZERO.copy() if clean_verdict(lines) else UNKNOWN.copy())
    findings = [parse_finding(r) for r in heading_findings(lines)]
    if resolve_conflict and counts["source"] == "verdict" and findings and counts["total"] != len(findings):
        observed = heading_counts(lines)
        if observed is not None:
            counts = {**observed, "source": "conflict", "block_total": counts["total"]}
    return {**counts, "findings": findings}


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--detail"]
    detail = len(args) != len(sys.argv) - 1
    result: dict = {**UNKNOWN, "findings": []} if detail else UNKNOWN.copy()
    if len(args) == 1:
        try:
            result = extract_detail(Path(args[0])) if detail else extract(Path(args[0]))
        except Exception:
            result = {**UNKNOWN, "findings": []} if detail else UNKNOWN.copy()
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
