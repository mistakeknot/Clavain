#!/usr/bin/env python3
"""Count failed review receipts across heads; refuse before another seat starts."""
import argparse
import json
import fcntl
import os
import re
import stat
from pathlib import Path
import sys

from review_round_decision import REVIEW_ROLES, DecisionRefused, claim


HEAD = re.compile(r"[0-9a-f]{40}")
PR_FILE = re.compile(r"([1-9][0-9]*)-([0-9a-f]{40})(?:\.([2-9]|[1-9][0-9]+))?\.json")


def fail_word(raw):
    """FAIL class from lib-verdict.sh; parity tested against its public reader."""
    return isinstance(raw, str) and re.match(r"^(FAIL|BLOCK)($|[\s:;.,(].*)", raw.strip(), re.I) is not None


def bound_head(row):
    return isinstance(row.get("head_sha"), str) and HEAD.fullmatch(row["head_sha"]) is not None


def eligible(row):
    route = row.get("resolved_route")
    profiles = [row.get("policy_profile"), route.get("policy_profile") if isinstance(route, dict) else None]
    return not (row.get("experimental") is True or row.get("gate_review_eligible") is False
                or row.get("experiment_arm") is not None
                or any(isinstance(p, str) and p.startswith("experiment-") for p in profiles))


def downgraded(row, source):
    name = PR_FILE.fullmatch(Path(source).name)
    findings = row.get("findings")
    return (name is not None and type(row.get("pr")) is int
            and int(name.group(1)) == row["pr"] and name.group(2) == row.get("head_sha")
            and row.get("verdict") == "PASS WITH NOTES" and row.get("block_downgraded") is True
            and fail_word(row.get("verdict_raw")) and row.get("findings_source") == "body"
            and type(row.get("findings_total")) is int and row["findings_total"] > 0
            and isinstance(findings, list) and len(findings) == row["findings_total"]
            and row.get("findings_truncated", False) is False
            and all(isinstance(f, dict) and f.get("severity") in ("P2", "P3")
                    and isinstance(f.get("class"), str) and bool(f["class"])
                    and isinstance(f.get("summary"), str) and bool(f["summary"])
                    and "file" in f and (f["file"] is None or isinstance(f["file"], str))
                    and "line" in f and (f["line"] is None or type(f["line"]) is int and f["line"] > 0)
                    for f in findings))


def check(bead, ledger, reviews, head=None, check_only=False, role=None):
    failures = set()
    malformed = 0
    evidence = {}
    veto = set()
    cancellation_off = False

    def pair(row):
        key = (row.get("dispatch_id"), row.get("attempt_id"))
        return key if all(isinstance(value, str) and value for value in key) else None

    def consider(row, source):
        if row.get("schema_version") != 1:
            return
        for field in ("bead_id", "role", "kind", "dispatch_id", "attempt_id", "verdict_class", "verdict"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError("invalid receipt field")
        role = row.get("role")
        if not isinstance(role, str) or row.get("bead_id") != bead or role not in REVIEW_ROLES:
            return
        if not eligible(row):
            return
        kind = row.get("kind")
        if kind == "dispatch-run-receipt":
            failed = row.get("verdict_class") == "FAIL"
        elif kind == "cross-lab-review-receipt":
            failed = row.get("verdict") in ("BLOCK", "FAIL")
        else:
            return
        if failed:
            # The PR receipt and run receipt describe the same attempt. Copies
            # also count once; older receipts without IDs use their source path.
            key = (row.get("dispatch_id"), row.get("attempt_id"))
            failures.add(key if all(key) else (source,))

    def consume(raw, source):
        nonlocal malformed, cancellation_off
        row = None
        try:
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError("invalid receipt object")
            key = pair(row)
            if key:
                evidence.setdefault(key, []).append((row, source))
            consider(row, source)
        except (ValueError, RecursionError):
            malformed += 1
            if isinstance(row, dict) and pair(row) and isinstance(row.get("bead_id"), str):
                veto.add(pair(row))
            else:
                cancellation_off = True

    if ledger.exists():
        # Cooperate with _append_dispatch_run_receipt's exclusive flock. Hold
        # a shared lock for the whole read so a live append cannot be torn.
        fd = os.open(f"{ledger}.lock", os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            with ledger.open("rb") as stream:
                for n, line in enumerate(stream):
                    if line.strip():
                        consume(line, f"{ledger}:{n + 1}")
    if reviews.exists():
        with os.scandir(reviews) as entries:
            directories = sorted(Path(entry.path) for entry in entries)
        for directory in directories:
            if directory.is_symlink():
                malformed += 1
                cancellation_off = True
                # A readable linked repository may contain the only record
                # of failed reviews. Keep baseline counting through it while
                # cancellation is off; an unreadable target is history error.
                if not directory.is_dir():
                    raise OSError("unreadable linked review directory")
            if not directory.is_dir():
                continue
            # Path.glob may swallow PermissionError and silently hide all
            # failures in a folder. Enumeration errors are history errors.
            with os.scandir(directory) as entries:
                paths = sorted(Path(entry.path) for entry in entries if entry.name.endswith(".json"))
            for path in paths:
                # Never follow a contradictory receipt through a link, or
                # silently omit a directory/FIFO where a receipt should be.
                if not stat.S_ISREG(path.lstat().st_mode):
                    malformed += 1
                    cancellation_off = True
                    continue
                consume(path.read_bytes(), str(path))
    if malformed:
        suffix = "s" if malformed != 1 else ""
        scope = "all attempts" if cancellation_off else "affected attempts"
        print(f"dispatch: skipped {malformed} malformed review history record{suffix}; cancellation is off for {scope}; counted only well-formed receipts", file=sys.stderr)
    if not cancellation_off:
        for key, records in evidence.items():
            if key not in failures or key in veto:
                continue
            rows = [row for row, _ in records]
            first = rows[0]
            if not all(type(row.get("schema_version")) is int and row["schema_version"] == 1
                       and row.get("bead_id") == bead and row.get("role") in REVIEW_ROLES
                       and row.get("role") == first.get("role") and bound_head(row)
                       and row["head_sha"] == first.get("head_sha") and eligible(row)
                       for row in rows):
                continue
            runs = [row for row in rows if row.get("kind") == "dispatch-run-receipt"]
            prs = [(row, source) for row, source in records if row.get("kind") == "cross-lab-review-receipt"]
            if (runs and prs and len(runs) + len(prs) == len(rows)
                    and all(row.get("verdict_class") == "FAIL" for row in runs)
                    and all(downgraded(row, source) for row, source in prs)):
                failures.remove(key)
    if len(failures) < 3:
        return 0
    try:
        decision_id = claim(reviews, bead, head, len(failures), check_only=check_only, role=role)
    except DecisionRefused as error:
        print(f"dispatch: review round decision refused: {error}", file=sys.stderr)
    else:
        if check_only:
            return 0
        print(f"dispatch: accepting one extra review round for {bead} head {head} decision {decision_id}", file=sys.stderr)
        return 0
    directory = reviews / "round-limits"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    summary = directory / f"{bead}.md"
    body = (f"# Review round limit: {bead}\n\n"
            f"{len(failures)} failed review rounds recorded across all heads and review roles.\n"
            "PASS and neutral rounds do not reset this cumulative count.\n"
            "Another review round is refused. Choose one option and record the decision on the bead.\n\n"
            "1. Park the bead.\n"
            "2. Redesign on a frontier seat.\n"
            "3. Accept a stated limit (record the limit and its consequences).\n")
    try:
        # Exclusive create leaves exactly one summary even on concurrent refusal.
        fd = os.open(summary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if summary.is_symlink() or not summary.is_file():
            raise ValueError("invalid summary destination")
    else:
        with os.fdopen(fd, "w") as stream:
            stream.write(body)
    print(f"dispatch: refusing review for {bead}: {len(failures)} failed review rounds; summary: {summary}", file=sys.stderr)
    return 25


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("bead")
        parser.add_argument("ledger", type=Path)
        parser.add_argument("reviews", type=Path)
        parser.add_argument("--head")
        parser.add_argument("--role", choices=sorted(REVIEW_ROLES))
        parser.add_argument("--check-only", action="store_true", help="outer dispatch preflight; resolved child must claim")
        args = parser.parse_args()
        sys.exit(check(args.bead, args.ledger, args.reviews, args.head, args.check_only, args.role))
    except (OSError, ValueError, TypeError, RecursionError):
        # No input bytes or exception text: receipts may contain private data.
        print("dispatch: cannot verify review round history or write summary (exit 26)", file=sys.stderr)
        sys.exit(26)
