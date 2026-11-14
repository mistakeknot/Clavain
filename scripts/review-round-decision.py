#!/usr/bin/env python3
"""Authority writer for a single review-round decision; never creates keys."""
import argparse
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import stat
import tempfile
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
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError("unsafe decisions directory")
    # Cooperating writers serialize the existence check and rename. The
    # destination appears only after the complete temporary file is flushed.
    lock_fd = os.open(directory / ".writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = directory / f"{args.bead}.json"
        if os.path.lexists(destination):
            raise FileExistsError("decision already exists")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".decision-",
                                             suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(data, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, destination)
        finally:
            if temporary is not None and os.path.lexists(temporary):
                os.unlink(temporary)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError):
        print("cannot write review round decision; check arguments, destination and authority key", file=sys.stderr)
        sys.exit(26)
