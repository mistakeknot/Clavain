#!/usr/bin/env python3
"""Post-run bearer-token leak scan for Claude-backed dispatch (bead mk-ouz83).

The token value is read from the environment of this process (default
ANTHROPIC_AUTH_TOKEN), never from argv, so it is not visible in `ps`. Matching
is fixed-string over raw bytes. The value is never printed, logged or written
to a report.

  scan    FILE...   redact every occurrence in place; record hits
  report            write the leak report JSON from the recorded hits

Exit status of `scan`: 0 clean or skipped, 3 a hit was found and redacted.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

MIN_TOKEN_LEN = 16
REDACTION = b"[REDACTED:anthropic-token]"
HIT_EXIT = 3


def load_token(var):
    value = os.environ.get(var, "")
    if len(value) < MIN_TOKEN_LEN:
        return None
    return value


def needles(token):
    """The raw value plus its JSON-escaped form (stream-json event files)."""
    forms = [token.encode("utf-8", "surrogateescape")]
    escaped = json.dumps(token)[1:-1].encode("utf-8")
    if escaped not in forms:
        forms.append(escaped)
    return forms


def redact_file(path, forms):
    """Replace every occurrence in place. Returns the occurrence count."""
    if os.path.islink(path) or not os.path.isfile(path):
        return 0
    with open(path, "rb") as handle:
        data = handle.read()
    total = 0
    for form in forms:
        count = data.count(form)
        if count:
            total += count
            data = data.replace(form, REDACTION)
    if total:
        # Rewrite through the same inode so mode and ownership are preserved.
        with open(path, "r+b") as handle:
            handle.seek(0)
            handle.write(data)
            handle.truncate()
    return total


def cmd_scan(args):
    token = load_token(args.token_env)
    if token is None:
        print(
            "token-leak-scan: skipped (%s unset or shorter than %d characters)"
            % (args.token_env, MIN_TOKEN_LEN),
            file=sys.stderr,
        )
        return 0
    forms = needles(token)
    found = False
    with open(args.hits, "a", encoding="utf-8") as hits:
        for path in args.files:
            count = redact_file(path, forms)
            if count:
                found = True
                hits.write(json.dumps({"file": path, "count": count}) + "\n")
    return HIT_EXIT if found else 0


def cmd_report(args):
    merged = {}
    if os.path.exists(args.hits):
        with open(args.hits, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                merged[record["file"]] = merged.get(record["file"], 0) + int(record["count"])
    report = {
        "schema_version": 1,
        "kind": "anthropic-token-leak",
        "bead": args.bead or None,
        "role": args.role or None,
        "run_id": args.run_id or None,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"path": p, "count": c} for p, c in sorted(merged.items())],
        "total_count": sum(merged.values()),
        "redaction": REDACTION.decode(),
    }
    directory = os.path.dirname(os.path.abspath(args.report))
    fd, tmp = tempfile.mkstemp(prefix=".token-leak.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, args.report)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--hits", required=True)
    scan.add_argument("--token-env", default="ANTHROPIC_AUTH_TOKEN")
    scan.add_argument("files", nargs="*")
    scan.set_defaults(func=cmd_scan)
    report = sub.add_parser("report")
    report.add_argument("--hits", required=True)
    report.add_argument("--report", required=True)
    report.add_argument("--bead", default="")
    report.add_argument("--role", default="")
    report.add_argument("--run-id", default="")
    report.set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
