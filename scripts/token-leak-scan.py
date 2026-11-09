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

An artifact whose full real path differs from its given path (a symlinked
file or a symlinked parent directory) is scanned (the run may have written
through the link) only when the resolved regular file lies under one of the
run's own roots (--root, repeatable). Anything that cannot be resolved to a
regular file, or that resolves outside every root, is never opened or
rewritten: it is recorded as unscanned (by a sanitized name) and fails closed.

The replacement marker never contains a value: the default marker is used only
when the result is verified free of every value; otherwise a fixed-width marker
of characters absent from every value is used; if no marker verifies, the file
or text is left alone and the run fails closed.

Exit status of `scan`: 0 clean or nothing to scan, 3 a hit was found and
redacted, 4 a file could not be scanned or the scanner failed, 5 both.
"""
import sys

FIXED_ERROR = "token-leak-scan: internal error (details withheld)"

# Anything that can fail at import time sits inside this boundary, so no
# traceback can print a path or a value.
try:
    import argparse
    import json
    import os
    import re
    import tempfile
    from datetime import datetime, timezone

    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX
        fcntl = None
except BaseException:
    print(FIXED_ERROR, file=sys.stderr)
    sys.exit(4)

REDACTION = b"[REDACTED:anthropic-token]"
DEFAULT_ENVS = ("ANTHROPIC_AUTH_TOKEN", "CODEX_POOL_AUTH_TOKEN")
HIT_EXIT = 3
ERROR_EXIT = 4
BOTH_EXIT = 5
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


class Unredactable(Exception):
    """No marker could be verified free of every value (fail closed)."""


def marker_candidates(forms):
    """Replacement markers to try, in order, as bytes.

    The default marker first; then a fixed-width marker made of one character
    that occurs in no form (so no form can overlap or span it).
    """
    yield REDACTION
    used = set()
    for form in forms:
        used.update(form)
    for code in list(range(0x21, 0x7F)) + list(range(0x01, 0x21)):
        if code not in used:
            yield bytes([code]) * 8
            return


def redact_bytes(data, forms):
    """Return (count, redacted bytes, marker) with no form left in the result.

    Raises Unredactable when no marker leaves the result free of every form.
    """
    ordered = sorted({f for f in forms if f}, key=len, reverse=True)
    if not ordered:
        return 0, data, REDACTION
    # One pass over the original bytes (longest form first at each position),
    # so text already replaced is never rescanned and cannot grow.
    pattern = re.compile(b"|".join(re.escape(f) for f in ordered))
    total = len(pattern.findall(data))
    if not total:
        return 0, data, REDACTION
    for marker in marker_candidates(ordered):
        out = pattern.sub(lambda _match, _m=marker: _m, data)
        if not any(form in out for form in ordered):
            return total, out, marker
    raise Unredactable()


def report_marker(tokens):
    """The marker that redacts text for these values (verified on a probe)."""
    forms = [f for f in all_forms(tokens) if f]
    for marker in marker_candidates(forms):
        if not any(form in marker for form in forms):
            return marker.decode("ascii")
    raise Unredactable()


def sanitize(text, tokens):
    """Redact every token form from a str (a file name, a path, metadata).

    Fails closed (Unredactable) when a form would still occur afterwards.
    """
    if not isinstance(text, str):
        return text
    forms = [f for f in all_forms(tokens) if f]
    if not forms:
        return text
    data = text.encode("utf-8", "surrogateescape")
    if not any(form in data for form in forms):
        return text
    _count, out, _marker = redact_bytes(data, forms)
    return out.decode("utf-8", "surrogateescape")


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

    def __exit__(self, *_exc_info):
        if self.handle is not None:
            self.handle.close()
        return False


def _under(target, roots):
    for root in roots:
        try:
            if os.path.commonpath([target, root]) == root:
                return True
        except ValueError:
            continue
    return False


def redact_file(path, forms, roots=()):
    """Replace every occurrence in place through the resolved regular file.

    A symlink is followed only when its resolved regular-file target lies under
    one of `roots`; any other symlink is never opened. Returns (count, status)
    where status is "ok", "absent" or "unscannable".
    """
    # The full real path decides, not only the last component: a symlinked
    # parent directory is followed only when the resolved file lies under a
    # root. A path with no symlink anywhere in it is used as given.
    target = os.path.realpath(path)
    if target != os.path.normpath(os.path.abspath(path)) or os.path.islink(path):
        real_roots = [os.path.realpath(r) for r in roots if r]
        if not _under(target, real_roots) or not os.path.isfile(target):
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
        try:
            total, data, _marker = redact_bytes(data, forms)
        except Unredactable:
            return 0, "unscannable"
        if total:
            # Rewrite through the same inode so mode and ownership are kept.
            with open(path, "r+b") as handle:
                handle.seek(0)
                handle.write(data)
                handle.truncate()
    return total, "ok"


def _safe_line(record, forms):
    """Serialized hit record; a fixed value-free one if it would carry a value;
    None (write nothing) if even that would."""
    for candidate in (record, {"file": "<withheld>", "unscanned": True}):
        line = json.dumps(candidate) + "\n"
        data = line.encode("utf-8", "surrogateescape")
        if not any(form in data for form in forms if form):
            return line
    return None


def cmd_scan(args):
    tokens = load_tokens(args.token_env or DEFAULT_ENVS)
    if not tokens:
        return 0
    forms = all_forms(tokens)
    found = False
    failed = False
    with open(args.hits, "a", encoding="utf-8") as hits:
        for path in args.files:
            try:
                safe = sanitize(os.fsdecode(path), tokens)
            except Unredactable:
                safe = "<unprintable name>"
            try:
                count, status = redact_file(path, forms, args.root or ())
            except OSError:
                count, status = 0, "unscannable"
            if status == "unscannable":
                failed = True
                line = _safe_line({"file": safe, "unscanned": True}, forms)
                if line:
                    hits.write(line)
                message = "token-leak-scan: could not scan %s; failing closed" % safe
                if any(f and f in message.encode("utf-8", "surrogateescape") for f in forms):
                    message = "token-leak-scan: could not scan a file; failing closed"
                print(message, file=sys.stderr)
            elif count:
                found = True
                # A record that would carry a value is replaced by a fixed
                # value-free one (the file is still redacted and the run fails).
                line = _safe_line({"file": safe, "count": count}, forms)
                if line:
                    hits.write(line)
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
        "redaction": report_marker(tokens),
    }
    text = json.dumps(report, indent=2) + "\n"
    encoded = text.encode("utf-8", "surrogateescape")
    # The fixed keys and text of the report are not redacted: when a value
    # occurs anywhere in the finished report the report is not written.
    if any(form and form in encoded for form in all_forms(tokens)):
        raise Unredactable()
    directory = os.path.dirname(os.path.abspath(args.report))
    fd, tmp = tempfile.mkstemp(prefix=".token-leak.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
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
        del message
        print("token-leak-scan: invalid arguments", file=sys.stderr)
        raise SystemExit(2)


def build_parser():
    parser = _QuietParser(description=DESCRIPTION)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_QuietParser)
    scan = sub.add_parser("scan")
    scan.add_argument("--hits", required=True)
    scan.add_argument("--token-env", action="append")
    scan.add_argument("--root", action="append")
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
