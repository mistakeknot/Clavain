#!/usr/bin/env python3
"""Post-run bearer-token leak scan for dispatch (bead mk-ouz83).

Token values are read from the environment of this process (the variables
named by --token-env, repeatable; default ANTHROPIC_AUTH_TOKEN and
CODEX_POOL_AUTH_TOKEN), never from argv, so they are not visible in `ps`.
Matching is fixed-string over raw bytes. Any nonempty value is scanned. A value
is never printed, logged or written to a report: file names and metadata are
redacted too, and every failure prints one fixed message.

  scan    FILE...   redact every occurrence in place; record hits
  report            write the leak report JSON from the recorded hits

A symlinked artifact is resolved and its regular-file target is scanned (the
run may have written through the link). A symlink that cannot be resolved to a
regular file cannot be scanned: it is recorded as unscanned and fails closed.

Exit status of `scan`: 0 clean or nothing to scan, 3 a hit was found and
redacted, 4 a file could not be scanned or the scanner failed, 5 both.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

REDACTION = b"[REDACTED:anthropic-token]"
DEFAULT_ENVS = ("ANTHROPIC_AUTH_TOKEN", "CODEX_POOL_AUTH_TOKEN")
HIT_EXIT = 3
ERROR_EXIT = 4
BOTH_EXIT = 5
FIXED_ERROR = "token-leak-scan: internal error (details withheld)"
DESCRIPTION = "Post-run bearer-token leak scan for dispatch"


def load_tokens(envs):
    """Distinct nonempty values of the named variables, in order."""
    values = []
    for name in envs:
        value = os.environ.get(name, "")
        if value and value not in values:
            values.append(value)
    return values


def needles(token):
    """The raw value plus its JSON-escaped form (stream-json event files)."""
    forms = [token.encode("utf-8", "surrogateescape")]
    escaped = json.dumps(token)[1:-1].encode("utf-8")
    if escaped not in forms:
        forms.append(escaped)
    return forms


def all_forms(tokens):
    forms = []
    for token in tokens:
        for form in needles(token):
            if form not in forms:
                forms.append(form)
    # longest first so a short value inside a longer one cannot split it
    return sorted(forms, key=len, reverse=True)


def sanitize(text, tokens):
    """Redact every token form from a str (a file name, a path, metadata)."""
    if not isinstance(text, str):
        return text
    marker = REDACTION.decode()
    forms = sorted(
        {f.decode("utf-8", "surrogateescape") for f in all_forms(tokens)},
        key=len,
        reverse=True,
    )
    for form in forms:
        if form:
            text = text.replace(form, marker)
    return text


class _Lock:
    """Hold the append lock (`<file>.lock`) of a shared log while rewriting it."""

    def __init__(self, path):
        self.path = path + ".lock"
        self.handle = None

    def __enter__(self):
        if fcntl is not None and os.path.isfile(self.path):
            try:
                self.handle = open(self.path, "a")
                fcntl.flock(self.handle, fcntl.LOCK_EX)
            except OSError:
                self.handle = None
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            self.handle.close()
        return False


def redact_file(path, forms):
    """Replace every occurrence in place through the resolved regular file.

    Returns (count, status) where status is "ok", "absent" or "unscannable".
    """
    if os.path.islink(path):
        target = os.path.realpath(path)
        if not os.path.isfile(target):
            return 0, "unscannable"
        path = target
    elif not os.path.lexists(path):
        return 0, "absent"
    elif not os.path.isfile(path):
        # a directory, device or pipe is not artifact storage (/dev/null)
        return 0, "absent"
    with _Lock(path):
        with open(path, "rb") as handle:
            data = handle.read()
        total = 0
        for form in forms:
            count = data.count(form)
            if count:
                total += count
                data = data.replace(form, REDACTION)
        if total:
            # Rewrite through the same inode so mode and ownership are kept.
            with open(path, "r+b") as handle:
                handle.seek(0)
                handle.write(data)
                handle.truncate()
    return total, "ok"


def cmd_scan(args):
    tokens = load_tokens(args.token_env or DEFAULT_ENVS)
    if not tokens:
        return 0
    forms = all_forms(tokens)
    found = False
    failed = False
    with open(args.hits, "a", encoding="utf-8") as hits:
        for path in args.files:
            safe = sanitize(os.fsdecode(path), tokens)
            try:
                count, status = redact_file(path, forms)
            except OSError:
                count, status = 0, "unscannable"
            if status == "unscannable":
                failed = True
                hits.write(json.dumps({"file": safe, "unscanned": True}) + "\n")
                print(
                    "token-leak-scan: could not scan %s; failing closed" % safe,
                    file=sys.stderr,
                )
            elif count:
                found = True
                hits.write(json.dumps({"file": safe, "count": count}) + "\n")
    if found and failed:
        return BOTH_EXIT
    if failed:
        return ERROR_EXIT
    return HIT_EXIT if found else 0


def cmd_report(args):
    tokens = load_tokens(args.token_env or DEFAULT_ENVS)
    merged = {}
    unscanned = set()
    if os.path.exists(args.hits):
        with open(args.hits, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                name = sanitize(record["file"], tokens)
                if record.get("unscanned"):
                    unscanned.add(name)
                else:
                    merged[name] = merged.get(name, 0) + int(record["count"])

    def meta(value):
        return sanitize(value, tokens) or None

    report = {
        "schema_version": 1,
        "kind": "anthropic-token-leak",
        "bead": meta(args.bead),
        "role": meta(args.role),
        "run_id": meta(args.run_id),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": [{"path": p, "count": c} for p, c in sorted(merged.items())],
        "total_count": sum(merged.values()),
        "unscanned": sorted(unscanned),
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


class _QuietParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse echoes argument values; print a fixed text instead.
        print("token-leak-scan: invalid arguments", file=sys.stderr)
        raise SystemExit(2)


def build_parser():
    parser = _QuietParser(description=DESCRIPTION)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_QuietParser)
    scan = sub.add_parser("scan")
    scan.add_argument("--hits", required=True)
    scan.add_argument("--token-env", action="append")
    scan.add_argument("files", nargs="*")
    scan.set_defaults(func=cmd_scan)
    report = sub.add_parser("report")
    report.add_argument("--hits", required=True)
    report.add_argument("--report", required=True)
    report.add_argument("--token-env", action="append")
    report.add_argument("--bead", default="")
    report.add_argument("--role", default="")
    report.add_argument("--run-id", default="")
    report.set_defaults(func=cmd_report)
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except SystemExit:
        raise
    except BaseException:
        # Exception text can carry a file name, which can carry a value.
        print(FIXED_ERROR, file=sys.stderr)
        return ERROR_EXIT


if __name__ == "__main__":
    sys.exit(main())
