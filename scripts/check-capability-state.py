#!/usr/bin/env python3
"""Fail if the capability-state block in a doc disagrees with config/capability-state.json.

Usage: check-capability-state.py [--doc PATH] [--source PATH] [--render]
  --render  print the block the doc should contain (between, not including, markers)
Exit 0 on agreement, 1 on drift, 2 on unreadable input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- capability-state:start -->", "<!-- capability-state:end -->"
FOOTER = "Off means unavailable for operational use, even if code or tests exist."
STATES = {"on", "off"}


def render(caps):
    lines = [f"- {c['label']}: {c['state']}." for c in caps]
    return "\n".join(lines + ["", FOOTER])


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--doc", default=str(ROOT / "agents/development.md"))
    p.add_argument("--source", default=str(ROOT / "config/capability-state.json"))
    p.add_argument("--render", action="store_true")
    a = p.parse_args(argv)
    try:
        caps = json.loads(Path(a.source).read_text())["capabilities"]
        bad = [c for c in caps if c.get("state") not in STATES]
        if bad:
            print(f"invalid state in source: {bad}", file=sys.stderr)
            return 2
        if a.render:
            print(render(caps))
            return 0
        text = Path(a.doc).read_text()
    except (OSError, ValueError, KeyError) as e:
        print(f"unreadable input: {e}", file=sys.stderr)
        return 2
    m = re.search(re.escape(START) + r"\n(.*?)\n" + re.escape(END), text, re.S)
    if not m:
        print(f"{a.doc}: capability-state block missing", file=sys.stderr)
        return 1
    if m.group(1).strip() != render(caps).strip():
        print(f"{a.doc}: capability-state block disagrees with {a.source}; "
              "run with --render and update the block", file=sys.stderr)
        return 1
    print("capability-state: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
