#!/usr/bin/env python3
"""Extract observed review finding counts from a dispatch output body."""

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


def heading_counts(lines: list[str]) -> dict[str, int | str] | None:
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    total = 0
    nonempty = [line.strip() for line in lines if line.strip()]
    for index, line in enumerate(nonempty):
        match = FINDING_HEADING.match(line)
        if not match:
            continue
        if re.match(r"^(?:\*\*|__)?\s*:\s*(?:0|none|n/?a)\b", line[match.end():], re.IGNORECASE):
            continue
        # A severity section immediately introducing tagged children is not an
        # additional finding. Headings otherwise remain the unit of counting.
        if line.startswith("#") and index + 1 < len(nonempty) and FINDING_HEADING.match(nonempty[index + 1]):
            continue
        severity = next(group for group in match.groups() if group is not None)
        counts[SEVERITY[severity.lower()]] += 1
        total += 1
    if total == 0:
        return None
    return {"source": "body", **counts, "total": total}


def clean_verdict(lines: list[str]) -> bool:
    joined = "\n".join(lines)
    if re.search(r"\b(?:REVISE|FAIL|REJECT|UNRUN|NEEDS_ATTENTION|WITH-CHANGES)\b", joined, re.IGNORECASE):
        return False
    if re.search(r"^\s*STATUS:\s*pass\s*$", joined, re.IGNORECASE | re.MULTILINE):
        return True
    if re.search(r"^\s*VERDICT:\s*(?:CLEAN|PASS)\s*$", joined, re.IGNORECASE | re.MULTILINE):
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
    try:
        body = path.read_text()
    except (OSError, UnicodeError):
        return UNKNOWN.copy()
    lines = visible_lines(body)
    return verdict_counts(lines) or heading_counts(lines) or (ZERO.copy() if clean_verdict(lines) else UNKNOWN.copy())


def main() -> int:
    result = UNKNOWN.copy()
    if len(sys.argv) == 2:
        try:
            result = extract(Path(sys.argv[1]))
        except Exception:
            result = UNKNOWN.copy()
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
