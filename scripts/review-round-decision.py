#!/usr/bin/env python3
"""Authority writer for a single review-round decision; never creates keys."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

from review_round_decision import key_bytes, mac, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-dir", type=Path, required=True)
    parser.add_argument("--bead", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--accepted-failures", type=int, required=True)
    parser.add_argument("--ruling", required=True)
    args = parser.parse_args()
    data = dict(schema_version=1, decision_id=str(uuid.uuid4()), bead=args.bead,
                head=args.head, accepted_failures=args.accepted_failures, authority="vizier",
                ruling=args.ruling, decided_at=datetime.now(timezone.utc).isoformat(), mac="0" * 64)
    validate(data)
    data["mac"] = mac(data, key_bytes())
    directory = args.reviews_dir / "round-limits/decisions"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Never overwrite an earlier decision or follow an existing symlink.
    fd = os.open(directory / f"{args.bead}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError):
        print("cannot write review round decision; check arguments, destination and authority key", file=sys.stderr)
        sys.exit(26)
