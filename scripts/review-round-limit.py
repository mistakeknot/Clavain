#!/usr/bin/env python3
"""Count failed review receipts across heads; refuse before another seat starts."""
import argparse
import json
import fcntl
import os
from pathlib import Path
import sys

from review_round_decision import DecisionRefused, claim
import review_policy

REVIEW_ROLES = {"cross-lab-review", "plan-review", "validation"}


def routine_allowance(policy, rounds):
    """Total code-review rounds allowed for this bead under the trial, or None for the full cap.

    The full 3-fix-round + 1-confirm cap (counted on failed rounds) applies unless
    the review-by-risk trial is active, there is at least one cross-lab round on
    record, and every one of those rounds has a complete path list that classifies
    as routine. Then the allowance is 1 round in total (pass or fail), or 2 once a
    round found a high-severity issue. A round whose findings are not on record
    counts as high; a round with no paths, truncated paths or any ambiguity keeps
    the full cap.
    """
    if not review_policy.trial_active(policy):
        return None
    code = [seen for seen in rounds.values() if seen["code"]]
    if not code or any(seen["failed"] and not seen["code"] for seen in rounds.values()):
        return None  # a failed plan-review or validation round keeps the full cap
    paths = []
    for seen in code:
        if not seen["paths"] or seen["truncated"]:
            return None
        paths.extend(seen["paths"])
    if review_policy.decide(paths, policy)["action"] != "one-round":
        return None
    high = any(seen["high"] or not seen["findings"] for seen in code if seen["failed"])
    return 2 if high else 1


def check(bead, ledger, reviews, head=None, check_only=False):
    failures = set()
    rounds = {}  # round key -> evidence for every review round, pass or fail; feeds the review-by-risk trial
    malformed = 0
    policy = None
    try:
        policy = review_policy.load_policy()
    except Exception:  # an unreadable policy means the full 3-round cap
        policy = None

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
        # The PR receipt and run receipt describe the same attempt. Copies
        # also count once; older receipts without IDs use their source path.
        key = (row.get("dispatch_id"), row.get("attempt_id"))
        key = key if all(key) else (source,)
        seen = rounds.setdefault(key, {"paths": set(), "high": False, "findings": False, "truncated": False,
                                       "failed": False, "code": False})
        seen["failed"] = seen["failed"] or failed
        seen["code"] = seen["code"] or role == "cross-lab-review"
        if failed:
            failures.add(key)
        paths = row.get("changed_paths")
        if isinstance(paths, list):
            seen["paths"].update(p for p in paths if isinstance(p, str))
        if row.get("changed_paths_truncated"):
            seen["truncated"] = True
        found = row.get("findings")
        # findings: [] with findings_source "unknown" means the verdict was not parsed into findings.
        if isinstance(found, list) and found and row.get("findings_source") != "unknown":
            seen["findings"] = True
            for item in found:
                sev = item.get("severity") if isinstance(item, dict) else None
                seen["high"] = seen["high"] or review_policy.is_high(sev, policy or {})

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
    allowance = routine_allowance(policy, rounds)
    if allowance is not None:
        if sum(1 for seen in rounds.values() if seen["code"]) < allowance:
            return 0
        limit = allowance
    else:
        limit = 3
        if len(failures) < limit:
            return 0
    if limit >= 3:
        try:
            decision_id = claim(reviews, bead, head, len(failures), check_only=check_only)
        except DecisionRefused as error:
            print(f"dispatch: review round decision refused: {error}", file=sys.stderr)
        else:
            if check_only:
                return 0
            print(f"dispatch: accepting one extra review round for {bead} head {head} decision {decision_id}", file=sys.stderr)
            return 0
    else:
        print("dispatch: review-by-risk trial limit reached; export CLAVAIN_REVIEW_POLICY=off to run the full cap for this change", file=sys.stderr)
    directory = reviews / "round-limits"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    summary = directory / f"{bead}.md"
    body = (f"# Review round limit: {bead}\n\n"
            f"{len(failures)} failed review rounds recorded across all heads and review roles.\n"
            "PASS and neutral rounds do not reset this cumulative count.\n"
            + (f"Review-by-risk trial, routine change: {limit} review round(s) in total are allowed.\n" if limit < 3
               else f"The limit for this change is {limit} failed rounds.\n") +
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
        parser.add_argument("--check-only", action="store_true", help="outer dispatch preflight; resolved child must claim")
        args = parser.parse_args()
        sys.exit(check(args.bead, args.ledger, args.reviews, args.head, args.check_only))
    except (OSError, ValueError, TypeError, RecursionError):
        # No input bytes or exception text: receipts may contain private data.
        print("dispatch: cannot verify review round history or write summary (exit 26)", file=sys.stderr)
        sys.exit(26)
