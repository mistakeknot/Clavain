#!/usr/bin/env python3
"""Emit once per BB thread/cycle/stage/evidence; storage errors fail open."""
import hashlib
import json
import os
from pathlib import Path
import sys


def first_notice(projection):
    identity = [os.environ['BB_THREAD_ID'], projection['cycle']['id'],
                projection['cycle']['stage'], projection]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    directory = Path(os.environ.get('CLAVAIN_BB_STATE_DIR', '~/.local/state/clavain/bb/notices')).expanduser()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(directory/key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    os.close(fd)
    return True


if __name__ == '__main__':
    try:
        first = first_notice(json.load(sys.stdin))
    except (OSError, ValueError, KeyError, TypeError):
        first = True
    raise SystemExit(0 if first else 1)
