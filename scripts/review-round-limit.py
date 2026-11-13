#!/usr/bin/env python3
"""Count failed review receipts across heads; refuse before another seat starts."""
import json
import fcntl
import os
from pathlib import Path
import sys

REVIEW_ROLES = {"cross-lab-review", "plan-review", "validation"}


def check(bead, ledger, reviews):
    failures = set()
    malformed = 0

    def consider(row, source):
        if row.get("schema_version") != 1:
            return
        for field in ("bead_id", "role", "kind", "dispatch_id", "attempt_id", "verdict_class", "verdict"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError("invalid receipt field")
        role = row.get("role")
        if not isinstance(role, str) or row.get("bead_id") != bead or role not in REVIEW_ROLES:
            return
        route = row.get("resolved_route")
        profiles = [row.get("policy_profile"), route.get("policy_profile") if isinstance(route, dict) else None]
        if (row.get("experimental") is True or row.get("gate_review_eligible") is False
                or row.get("experiment_arm") is not None
                or any(isinstance(p, str) and p.startswith("experiment-") for p in profiles)):
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
        nonlocal malformed
        try:
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError("invalid receipt object")
            consider(row, source)
        except (ValueError, RecursionError):
            malformed += 1

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
        for path in sorted(reviews.glob("*/*.json")):
            if path.is_file() and not path.is_symlink():
                consume(path.read_bytes(), str(path))
    if malformed:
        suffix = "s" if malformed != 1 else ""
        print(f"dispatch: skipped {malformed} malformed review history record{suffix}; counted only well-formed receipts", file=sys.stderr)
    if len(failures) < 3:
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
        sys.exit(check(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))
    except (OSError, ValueError, TypeError):
        # No input bytes or exception text: receipts may contain private data.
        print("dispatch: cannot verify review round history or write summary (exit 26)", file=sys.stderr)
        sys.exit(26)
