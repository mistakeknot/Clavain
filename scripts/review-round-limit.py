#!/usr/bin/env python3
"""Count failed review receipts across heads; refuse before another seat starts."""
import json
import os
from pathlib import Path
import sys

REVIEW_ROLES = {"cross-lab-review", "plan-review", "validation"}


def check(bead, ledger, reviews):
    failures = set()

    def consider(row, source):
        if not isinstance(row, dict) or row.get("schema_version") != 1:
            return
        if row.get("bead_id") != bead or row.get("role") not in REVIEW_ROLES:
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

    if ledger.exists():
        with ledger.open() as stream:
            for n, line in enumerate(stream):
                if line.strip():
                    consider(json.loads(line), f"{ledger}:{n + 1}")
    if reviews.exists():
        for path in sorted(reviews.glob("*/*.json")):
            if path.is_file() and not path.is_symlink():
                consider(json.loads(path.read_text()), str(path))
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
