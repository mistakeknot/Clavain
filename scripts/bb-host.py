#!/usr/bin/env python3
"""Shared, fail-closed BB host enrollment check (no credential output)."""
import json
import os
from pathlib import Path
import subprocess


def bb_host():
    if not os.environ.get("BB_THREAD_ID") or not os.environ.get("BB_SERVER_URL"):
        return None
    try:
        config = json.loads((Path(__file__).resolve().parents[1] / "config/bb-integration.json").read_text())
        result = subprocess.run([os.environ.get("BB_CLI") or "bb", "status", "--json"],
                                capture_output=True, text=True, timeout=10, check=True)
        thread = json.loads(result.stdout)["thread"]
        host = thread["environment"]["hostId"]
        if thread["id"] == os.environ["BB_THREAD_ID"] and host in config["allowed_host_ids"]:
            return host
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        pass
    return None


if __name__ == "__main__":
    host = bb_host()
    if host:
        print(host)
    raise SystemExit(0 if host else 1)
