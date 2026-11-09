#!/usr/bin/env python3
"""Post-run bearer-token leak scan for dispatch (bead mk-ouz83).

Token values are read from the environment of this process (ANTHROPIC_AUTH_TOKEN and
CODEX_POOL_AUTH_TOKEN always, plus the variables named by --token-env,
repeatable; a named variable adds to the defaults), never from argv, so they are not visible in `ps`.
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

Every message this scanner prints (stdout or stderr, including usage and
errors) is queued in memory per stream and written once, at exit, through one
checked output point: the whole buffer is encoded exactly as the stream will
write it (its own encoding and error handler) and checked, message boundaries
and terminators included, against the raw and JSON-escaped forms of every
value. If none occurs, those bytes are written in one write. If one occurs, a
fixed line replaces them, and only when that line contains no value; else
nothing is written. The exit status is the same either way. Trade-off:
diagnostics appear at exit, not as they occur. Not covered: output the
interpreter writes before this script installs its handlers.

Exit status of `scan`: 0 clean or nothing to scan, 3 a hit was found and
redacted, 4 a file could not be scanned or the scanner failed, 5 both.
"""
import sys

# Interrupt handling comes first: an interrupt ends the process by the signal
# itself (shell status 130), so Python never builds a KeyboardInterrupt
# traceback. SIGPIPE keeps Python's own disposition (ignored): a broken pipe
# surfaces as a write error, which the checked output point absorbs silently.
try:
    import signal as _signal

    _signal.signal(_signal.SIGINT, _signal.SIG_DFL)
except BaseException:
    pass

FIXED_ERROR = "token-leak-scan: internal error (details withheld)"
FIXED_SUPPRESSED = "token-leak-scan: diagnostics suppressed"

# One in-memory buffer per stream. Nothing is written while the scanner runs;
# _flush_output() writes each buffer once, at exit (trade-off: diagnostics
# appear when the scanner ends, not as they occur).
_BUFFER = {"stdout": [], "stderr": []}


def _emit(message, stream=None):
    """Queue message (plus newline) for the checked output point."""
    try:
        name = "stdout" if stream is not None and stream is sys.stdout else "stderr"
        _BUFFER[name].append(message + "\n")
    except BaseException:
        return


def _token_values():
    """Values of the default variables plus every --token-env named in argv
    (any prefix of --token-env of three or more characters, either form).
    Returns None when they cannot be determined."""
    try:
        import os as _os

        names = ["ANTHROPIC_AUTH_TOKEN", "CODEX_POOL_AUTH_TOKEN"]
        argv = sys.argv[1:]
        for i, arg in enumerate(argv):
            if arg == "--":
                break
            head, eq, rest = arg.partition("=")
            if len(head) >= 3 and "--token-env".startswith(head):
                if eq:
                    names.append(rest)
                elif i + 1 < len(argv):
                    names.append(argv[i + 1])
        return [v for v in (_os.environ.get(n, "") for n in names) if v]
    except BaseException:
        return None


def _contains_token(data, values, encoding, errors):
    """True/False whether any value (raw or JSON-escaped; encoded as the
    stream encodes, and also as UTF-8 with surrogateescape) occurs in the
    complete byte string data. None when that cannot be decided."""
    try:
        try:
            import json as _json
        except BaseException:
            _json = None
        for value in values:
            texts = [value]
            if _json is not None:
                texts.append(_json.dumps(value)[1:-1])
            elif not all(0x20 <= ord(c) < 0x7F and c not in '"\\' for c in value):
                return None
            for text in texts:
                forms = [text.encode("utf-8", "surrogateescape")]
                try:
                    forms.append(text.encode(encoding, errors))
                except BaseException:
                    pass
                if any(form in data for form in forms):
                    return True
        return False
    except BaseException:
        return None


def _flush_output():
    """The one output point: write each stream's buffer, checked as the exact
    bytes that will be written, in one write; then keep shutdown quiet."""
    try:
        values = _token_values()
        for name in ("stdout", "stderr"):
            chunks = _BUFFER[name]
            _BUFFER[name] = []
            if not chunks:
                continue
            stream = getattr(sys, name, None)
            data = None
            try:
                encoding = getattr(stream, "encoding", None) or "utf-8"
                errors = getattr(stream, "errors", None) or "strict"
                raw = "".join(chunks)
                if values is not None:
                    data = raw.encode(encoding, errors)
                    verdict = _contains_token(data, values, encoding, errors)
                    if verdict is None:
                        data = None
                    elif verdict:
                        data = (FIXED_SUPPRESSED + "\n").encode(encoding, errors)
                        if _contains_token(data, values, encoding, errors) is not False:
                            data = None
            except BaseException:
                data = None
            if not data:
                continue
            try:
                binary = stream.buffer
                binary.write(data)
                binary.flush()
            except BaseException:
                _silence(stream)
    except BaseException:
        pass
    _final_flush()


def _silence(stream):
    """After a failed write or flush, point the stream at /dev/null so that
    nothing buffered can fail (and print a diagnostic) at interpreter exit."""
    try:
        import os as _os

        null = _os.open(_os.devnull, _os.O_WRONLY)
        try:
            _os.dup2(null, stream.fileno())
        finally:
            _os.close(null)
    except BaseException:
        pass
    try:
        stream.flush()
    except BaseException:
        try:
            import io as _io

            name = "stdout" if stream is sys.stdout else "stderr"
            setattr(sys, name, _io.StringIO())
        except BaseException:
            pass


def _final_flush():
    """Flush both streams inside the checked path; a failure ends silently."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except BaseException:
            _silence(stream)


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
    _emit(FIXED_ERROR)
    _flush_output()
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


def _all_envs(args):
    """The default variables plus every --token-env: an explicit name adds to
    the defaults, never replaces them (as _token_values already treats them)."""
    return tuple(DEFAULT_ENVS) + tuple(args.token_env or ())


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


def _std_stream_for(path):
    """"stdout" or "stderr" when path is the same open file as that stream
    (a terminal, file or pipe; /dev/stdout and /dev/stderr included), else
    None."""
    try:
        target = os.stat(path)
        for name in ("stdout", "stderr"):
            st = os.fstat(getattr(sys, name).fileno())
            if (st.st_dev, st.st_ino) == (target.st_dev, target.st_ino):
                return name
    except BaseException:
        pass
    return None


def _existing_tail(path, size):
    """The last size bytes already in a regular file (b"" otherwise)."""
    try:
        if size <= 0 or not os.path.isfile(path):
            return b""
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - size))
            return handle.read()
    except BaseException:
        return b""


def _write_hits(hits, lines, forms):
    """The one output of hit records, checked as the whole destination.
    The joined records of this scan are checked against every form together
    with what they will be joined to: for a regular file opened for append,
    the last (longest form - 1) bytes already in it; for a path that is the
    same open file as stdout or stderr, the records go into that stream's
    buffer, so the checked output point checks them together with the
    diagnostics as one document. If the joined bytes would carry a value the
    records are replaced by the fixed value-free record, or nothing if even
    that would. Memory: one short line per scanned file."""
    if not lines:
        return
    std = _std_stream_for(hits.name)
    tail = b"" if std else _existing_tail(
        hits.name, max((len(f) for f in forms if f), default=1) - 1)

    def carries(text):
        data = tail + text.encode("utf-8", "surrogateescape")
        return any(form in data for form in forms if form)

    document = "".join(lines)
    if carries(document):
        document = _safe_line({"file": "<withheld>", "unscanned": True}, forms)
        if not document or carries(document):
            return
    if std:
        _BUFFER[std].append(document)
    else:
        hits.write(document)


def cmd_scan(args):
    tokens = load_tokens(_all_envs(args))
    if not tokens:
        return 0
    forms = all_forms(tokens)
    found = False
    failed = False
    lines = []
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
                    lines.append(line)
                message = "token-leak-scan: could not scan %s; failing closed" % safe
                if any(f and f in message.encode("utf-8", "surrogateescape") for f in forms):
                    message = "token-leak-scan: could not scan a file; failing closed"
                _emit(message)
            elif count:
                found = True
                # A record that would carry a value is replaced by a fixed
                # value-free one (the file is still redacted and the run fails).
                line = _safe_line({"file": safe, "count": count}, forms)
                if line:
                    lines.append(line)
        _write_hits(hits, lines, forms)
    if found and failed:
        return BOTH_EXIT
    if failed:
        return ERROR_EXIT
    return HIT_EXIT if found else 0


def cmd_report(args):
    tokens = load_tokens(_all_envs(args))
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
    def _print_message(self, message, file=None):
        # usage and --help text go through the checked printer too
        if message:
            _emit(message.rstrip("\n"), file or sys.stdout)

    def error(self, message):
        # argparse echoes argument values; print a fixed text instead.
        del message
        _emit("token-leak-scan: invalid arguments")
        raise SystemExit(2)


def build_parser():
    parser = _QuietParser(description=DESCRIPTION, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_QuietParser)
    scan = sub.add_parser("scan", allow_abbrev=False)
    scan.add_argument("--hits", required=True)
    scan.add_argument("--token-env", action="append")
    scan.add_argument("--root", action="append")
    scan.add_argument("files", nargs="*")
    scan.set_defaults(func=cmd_scan)
    report = sub.add_parser("report", allow_abbrev=False)
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
        _emit(FIXED_ERROR)
        return ERROR_EXIT


if __name__ == "__main__":
    try:
        _code = main()
    except SystemExit as _exc:
        _code = _exc.code
    except BaseException:
        _emit(FIXED_ERROR)
        _code = ERROR_EXIT
    if _code is not None and not isinstance(_code, int):
        _code = ERROR_EXIT
    _flush_output()
    sys.exit(_code)
