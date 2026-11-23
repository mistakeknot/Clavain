#!/usr/bin/env python3
"""Extract observed review finding counts from a dispatch output body.

With --detail the JSON also carries "findings": one record per parsed finding
heading (class, severity, summary, file, line). A heading may carry a class tag
after the severity, e.g. "### [P1] [test-gap] summary text (path/file.py:42)"."""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
import urllib.parse
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


def safe_finding_text(text: str) -> str:
    """Lossy audit copy only; verdict validation always reads the original.

    Redact credential-shaped values and private locations before truncation.
    This is deliberately conservative: ambiguous long tokens are not useful
    audit prose. Never copy a finding's free-form body into a receipt.
    """
    text = html.unescape(urllib.parse.unquote(text))
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = "".join(c if not unicodedata.category(c).startswith("C") else " " for c in text)
    text = re.sub(r"(?i)(?:https?://|ssh://)\S+", "[redacted]", text)
    text = re.sub(r"(?i)(?:/(?:home|users|root|private|tmp|var)/|~/|[a-z]:\\Users\\)\S+", "[private-path]", text)
    text = re.sub(
        r"(?i)\b(?:[\w-]*(?:token|secret|password|passwd|api[_-]?key)|authorization)"
        r"\s*[:=]\s*(?:[\"'][^\"']*[\"']|\S+)",
        "[redacted]", text,
    )
    text = re.sub(r"(?i)\b(?:bearer\s+\S+|(?:sk-|gh[pousr]_|github_pat_)[\w-]+)", "[redacted]", text)
    text = re.sub(r"(?<![\w/])[A-Za-z0-9_+=-]{32,}(?![\w/])", "[redacted]", text)
    return re.sub(r"\s+", " ", text).strip()


def zero_declaration(line: str, rest: str) -> bool:
    """Complete empty-count text, allowing balanced bold and one final period.

    Shared with strict validation; title prefixes are never count evidence.
    Reporting also feeds the dispatch sidecar and routing audit.
    """
    if any(line.count(marker) % 2 for marker in ("**", "__")):
        return False
    rest = rest.replace("**", "").replace("__", "")
    return bool(re.fullmatch(r"\s*:\s*(?:0|none(?:\s+found)?|n/?a)\.?\s*", rest, re.I))


def heading_findings(lines: list[str]) -> list[dict[str, str]]:
    """Return one {severity, rest} record per finding heading (same rules as
    the historical heading counter, which is now derived from this list)."""
    found: list[dict[str, str]] = []
    nonempty = [line.strip() for line in lines if line.strip()]
    for index, line in enumerate(nonempty):
        match = FINDING_HEADING.match(line)
        if not match:
            continue
        if zero_declaration(line, line[match.end():]):
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
    summary = safe_finding_text(re.sub(r"(?:\*\*|__)", "", rest))
    file_name: str | None = None
    line_no: int | None = None
    for hit in FILE_LINE.finditer(summary):
        candidate = hit.group(1)
        # Locations in audit records must be repository-relative, never a
        # suffix extracted from an absolute or traversing path.
        if (candidate.startswith(("/", "~")) or ".." in candidate.split("/")
                or len(candidate) > 240):
            continue
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


_OPEN = "\\[\uff3b\u3010\u300c\u3014\u300e(\uff08"
CANDIDATE = re.compile(
    r"^(?:#{1,6}\s|(?:\*\*|__)|[" + _OPEN + r"]"
    r"|(?:[-+*\u2022]|\d+[.)])\s+(?:\*\*|__)?[" + _OPEN + r"]"
    r"|(?:[-+*\u2022]|\d+[.)])\s+(?:\*\*|__)?(?:finding|issue|severity|blocker)s?\b"
    r"|(?:finding|issue|severity|blocker)s?\b)", re.I,
)
BENIGN_HEADING = re.compile(
    r"^#{1,6}\s*(?:summary|findings?|notes?|overview|verdict|review|scope|conclusion|tests?)\s*:?\s*$", re.I,
)
# Strict downgrade evidence (design choice: fail closed, no position rules).
# The only text the scan exempts is a parsed finding heading's own leading
# P2/P3 label, the FAIL/BLOCK word that opens a VERDICT line, a bare
# "Findings:" heading and a count declaration that matches the headings.
# All other text, heading remainders and verdict explanations included, is
# joined and read under several views: as written, HTML unescaped, tags
# removed, punctuation as a separator, punctuation deleted (so markup inside
# a word cannot split it), camel-case and letter/digit pieces, and the whole
# evidence with every non-alphanumeric character removed (letter spacing,
# words split across lines). A severity or hold token in any view keeps
# BLOCK, whatever its markup or position. Lower-severity words outside the
# exempt label, and any non-ASCII letter or digit, also keep BLOCK. False
# blocks are accepted; they cost only a manual reading of the review.
SEVERITY_TOKENS = frozenset(SEVERITY) | {
    "blocker", "blockers", "blocking", "unknown", "severe", "severely", "serious",
    "major", "important", "urgent", "showstopper", "showstoppers", "highest",
    "higher", "highly", "criticality", "critically", "sev", "severity", "severities",
}
SEVERITY_PATTERN = re.compile(r"(?:p|s|sev)[0-3]s?")
# A label split by a separator or a case change: "P-1", "Sev 1", "Priority 0".
SPLIT_LABEL_FIRST = frozenset({"p", "s", "sev", "severity", "priority", "prio", "pri"})
SPLIT_LABEL_SECOND = frozenset({"0", "1", "2", "3", "zero", "one", "two", "three"})
# Hold vocabulary: any word about merging or blocking (contained stems also
# catch inflections and compounds such as unmerged or unblock), the usual
# forms of hold, land, ship, wait, halt, stop, veto, revert, reject, must and
# until, and any "do not" or "don't". The vocabulary is finite: a hold
# written only in other words is outside this scan.
HOLD_CONTAINS = ("merg", "block")
HOLD_WORD = re.compile(
    r"(?:with|up|on)?hold(?:s|ing|er|ers)?|(?:with)?held|land(?:s|ed|ing|able)?"
    r"|ship(?:s|ped|ping|pable)?|wait(?:s|ed|ing)?|halt(?:s|ed|ing)?|veto(?:es|ed|ing)?"
    r"|stop(?:s|ped|ping|per|pers)?|revert(?:s|ed|ing)?|reject(?:s|ed|ing|ion)?"
    r"|must|mustn|until|dnm|nogo|dont|donot")
HOLD_PAIRS = frozenset({("do", "not"), ("don", "t")})
SQUASHED = re.compile(
    r"critical|blocker|blocking|unknown|severe|severit|showstopper|important|urgent"
    r"|major|high|medium|merge|merging|(?:sev|prio|priority)[0-3]")
VERDICT_LEAD = re.compile(
    r"^(?:\*\*|__)?\s*VERDICT\s*:\s*(?:\*\*|__)?\s*(?:FAIL|BLOCK)(?=$|[\s:;.,(*])", re.I)
# Markup that hides text from a reader (fences, HTML comments) or a NUL byte.
# The receipt writer refuses these already; strict validation refuses alone.
UNREADABLE_MARKUP = ("```", "~~~", "<!--", "-->", "\x00")
TAG = re.compile(r"<[^<>]*>")


def _visible_char(c: str) -> bool:
    return (unicodedata.category(c) != "Cf" and c != "͏"
            and not 0xFE00 <= ord(c) <= 0xFE0F and not 0xE0100 <= ord(c) <= 0xE01EF)


def _clean(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text) if _visible_char(c))


def normalized_line(line: str) -> str:
    return _clean(line).strip()


def evidence_views(text: str) -> set[str]:
    """Every reading of the evidence that the scan must clear."""
    unescaped = text
    for _ in range(8):
        decoded = _clean(html.unescape(unescaped))
        if decoded == unescaped:
            break
        unescaped = decoded
    else:
        # Still decoding after many rounds: nested escapes are unreadable.
        unescaped = "ÿ"
    views = {text, unescaped, _clean(urllib.parse.unquote(unescaped))}
    views |= {TAG.sub("", view) for view in views}
    # Punctuation deleted, whitespace kept: Hi**gh**, H\igh and Hi_gh join.
    return views | {re.sub(r"[^\w\s]|_", "", view) for view in views}


def _severe_token(token: str) -> bool:
    return (token in SEVERITY_TOKENS or HOLD_WORD.fullmatch(token) is not None
            or SEVERITY_PATTERN.fullmatch(token) is not None
            or any(stem in token for stem in HOLD_CONTAINS))


def _severe_sequence(tokens: list[str]) -> bool:
    return (any(_severe_token(token) for token in tokens)
            or any((a in SPLIT_LABEL_FIRST and b in SPLIT_LABEL_SECOND) or (a, b) in HOLD_PAIRS
                   for a, b in zip(tokens, tokens[1:])))


def severe_evidence(fragments: list[str]) -> bool:
    """True when the evidence, under any view, holds a severity or hold token
    or a non-ASCII letter or digit (lookalike letters are unreadable)."""
    for view in evidence_views("\n".join(fragments)):
        if any(c.isalnum() and not c.isascii() for c in view):
            return True
        runs = re.findall(r"[A-Za-z0-9]+", view)
        pieces = [piece.lower() for run in runs
                  for piece in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", run)]
        if _severe_sequence([run.lower() for run in runs]) or _severe_sequence(pieces):
            return True
        if SQUASHED.search(re.sub(r"[^a-z0-9]", "", view.lower())):
            return True
    return False


def undecorated(line: str) -> str:
    line = re.sub(r"^(?:#{1,6}\s+|[-+*•]\s+|\d+[.)]\s+)", "", line)
    return line.replace("**", "").replace("__", "").strip()


def strict_clean(path: Path) -> bool:
    """Accept only complete lower-severity evidence; errors retain BLOCK.

    A downgrade needs at least one finding, every finding heading carrying a
    parsed P2/P3 label, no unparsed finding-shaped line, count declarations
    that match the headings, and no severity or hold token anywhere outside
    the exempt text (see the comment above)."""
    body = path.read_text()
    if any(marker in body for marker in UNREADABLE_MARKUP):
        return False
    lines = [normalized_line(line) for line in body.splitlines()]
    counts = heading_counts(lines)
    if not counts or counts["P0"] or counts["P1"] or not counts["total"]:
        return False
    evidence: list[str] = []
    for line in lines:
        if not line:
            continue
        plain = undecorated(line)
        # Bare section headings are not declarations; titles containing a
        # declaration marker conservatively retain BLOCK.
        if re.fullmatch(r"findings\s*:", plain, re.I):
            continue
        if re.search(r"\bfindings\s*:", plain, re.I):
            declaration = VERDICT_FINDINGS.fullmatch(plain)
            if not declaration:
                return False
            declared = [int(declaration.group(i) or 0) for i in range(2, 6)]
            if (int(declaration.group(1)) != sum(declared)
                    or declared != [counts[key] for key in ("P0", "P1", "P2", "P3")]):
                return False
            continue
        match = FINDING_HEADING.match(line)
        if match:
            # Structural guard, independent of the lexical scan.
            severity = SEVERITY[next(g for g in match.groups() if g is not None).lower()]
            if severity in ("P0", "P1"):
                return False
            evidence.append(line[match.end():])
            continue
        if CANDIDATE.match(line) and not BENIGN_HEADING.fullmatch(line):
            return False
        verdict = VERDICT_LEAD.match(line)
        evidence.append(line[verdict.end():] if verdict else line)
    return not severe_evidence(evidence)


def main() -> int:
    if "--strict-clean" in sys.argv[1:]:
        if len(sys.argv) != 3 or sys.argv[1] != "--strict-clean":
            return 1
        try:
            return 0 if strict_clean(Path(sys.argv[2])) else 1
        except Exception:
            return 1
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
