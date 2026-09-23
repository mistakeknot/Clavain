#!/usr/bin/env python3
"""Classify provider error envelopes and retain safe failure evidence."""
import argparse
from functools import lru_cache
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import unquote_plus, urlsplit

QUOTA = {"usage_limit_exceeded", "quota_exhausted", "insufficient_quota"}
DENIAL = {"permission_denied", "policy_denied", "policy_violation", "forbidden", "403"}
CONFIG = {"invalid_request_error", "authentication_error", "unauthorized", "401", "400"}
USAGE_LIMIT_MESSAGE = re.compile(r"^You[’']ve hit your usage limit\.")
STDERR_USAGE_LIMIT = re.compile(
    r"^(?:\x1b\[[0-9;]*m)*(?:ERROR\s*:\s*)?You[’']ve hit your usage limit\."
)
MAPPED_ERROR_FIELDS = {"codex_error_info", "code", "type", "status", "message"}
SAFE_EVENT_FIELDS = {
    "request_id", "requestId", "status", "status_code", "error_code",
    "provider", "model", "will_retry", "willRetry", "retry_after", "retryAfter",
}
BODY_FIELDS = {"message", "result", "content", "text", "output", "input", "prompt", "task"}
MAX_FIELD_BYTES = 256
MAX_UNMAPPED_BYTES = 4096
SENSITIVE_FIELD = re.compile(
    r"token|secret|pass|pwd|(?:^|[-_])pw(?:$|[-_])|api[_-]?key|auth|cookie|session|credential|private",
    re.IGNORECASE,
)
# Context rules run before the allowlist: a credential may be short, low
# entropy, or use an unknown provider/scheme. Values never escape on that basis.
PEM_BLOCK = re.compile(
    r"-----BEGIN [^-\r\n]+-----.*?(?:-----END [^-\r\n]+-----|\Z)",
    re.DOTALL,
)
HEADER = re.compile(r"(?P<prefix>[ \t]*(?:[<>][ \t]*)?)(?P<key>[A-Za-z0-9_-]+)[ \t]*:[ \t]*")
CREDENTIAL_HEADER = re.compile(
    r"(?:proxy-)?authorization|(?:set-)?cookie|(?:[A-Za-z0-9_-]+-)?(?:key|secret|token)",
    re.IGNORECASE,
)
ASSIGNMENT = re.compile(
    r'''(?<![A-Za-z0-9_.%])(?P<key>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|(?:--)?[A-Za-z_%][A-Za-z0-9_.%+-]*)\]?[ \t]*(?P<separator>=>|[:=])\s*'''
)
JSON_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
URL_USERINFO = re.compile(r'''(://)[^\s"'<>]*@''')
BEARER_VALUE = re.compile(r"(?i)(\b(?:Bearer|Basic)\s+)[^\s,;}\]]+")
PASSWORD_VALUE = re.compile(r"(?i)(\bpassword\s+)[^\s,;}]+")
CLI_OPTION = re.compile(r"(?<!\S)(?P<key>--[A-Za-z][A-Za-z0-9_-]*)[ \t]+")
CLI_LOGIN = re.compile(
    r"\b(?:curl\b[^\r\n]*?[ \t](?:-u|--user)|(?:sshpass|mysql)\b[^\r\n]*?[ \t]-p)[ \t]+"
)
# Vendor shapes remain supplemental; unfamiliar tokens are dropped regardless
# of length, apparent randomness, or a provider prefix.
JWT_VALUE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
TOKEN_VALUE = re.compile(
    r"\b(?:sk|tok|gh[pousr]|github_pat|glpat|ntn|xox[beaprs])[-_][A-Za-z0-9._-]{6,}\b"
    r"|\bAIza[A-Za-z0-9_-]{35}\b|\bya29\.[A-Za-z0-9._-]+"
)
AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
HOME_PATH = re.compile(
    r"(?<![A-Za-z0-9_])(?:/(?:home|Users)/[^/\s]+|/root|/(?:private/)?(?:tmp|var/folders))(?=/|\b)"
)
FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
SAFE_HEX = re.compile(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\Z")
SAFE_UUID = re.compile(r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}\Z")
SAFE_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:?[0-9]{2})")
ERROR_CODE = re.compile(r"(?:E[A-Z0-9_]+|[a-z_]+_error)\Z")
NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z")
# Punctuation is structural, never a reason to keep adjoining unknown data.
# The final alternative consumes unknown runs WHOLE (including dotted strings),
# so a random secret cannot be mistaken for a hostname or broken into safe words.
LEXEME = re.compile(
    rf"(?P<timestamp>{SAFE_TIMESTAMP.pattern})(?=$|[\s,;\"'<>\)\]}}])"
    r"|(?P<url>[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"'`]+)"
    r"|(?P<path>~?/[^\s\"'<>`,;()\[\]{}]*)"
    r"|(?P<structure>[ \t\r\n:;=,{}\[\]()<>\"'`!?|&*\\])"
    r"|(?P<atom>[^ \t\r\n:;=,{}\[\]()<>\"'`!?|&*\\]+(?:'[A-Za-z]+)?)"
)


def _envelope(event):
    """Return the normalized error envelope consumed by the classifier."""
    if not isinstance(event, dict):
        return None, None, None
    if event.get("type") == "event_msg":
        event = event.get("payload", {})
    if not isinstance(event, dict):
        return None, None, None
    kind = event.get("type")
    error = None
    if kind in ("task_complete", "turn.failed", "error"):
        error = event.get("error")
        if kind == "error" and error is None and isinstance(event.get("message"), str):
            error = event
    elif kind == "result" and event.get("is_error"):
        error = event.get("error", {})
    elif kind == "assistant" and event.get("error"):
        error = event["error"]
    return event, kind, error


def classify(events, stderr=""):
    failures = set()
    transient_errors = set()
    for event in events:
        event, kind, error = _envelope(event)
        if event is None:
            continue
        if kind == 'turn.completed':
            # Codex can recover from stream errors within a turn. Only its
            # generic standalone stream errors are provisional. Coded policy,
            # configuration and quota failures remain sticky across success.
            transient_errors.clear()
            continue
        target = transient_errors if kind == 'error' else failures
        if error is None:
            continue
        codes = {error} if isinstance(error, str) else set()
        if isinstance(error, dict):
            codes = {str(error.get(k, "")) for k in ("codex_error_info", "code", "type", "status")}
        if codes & DENIAL:
            failures.add("terminal_policy")
        elif codes & CONFIG:
            failures.add("terminal_configuration")
        elif codes & QUOTA or (isinstance(error, dict) and USAGE_LIMIT_MESSAGE.match(
                str(error.get('message', '')))):
            failures.add("quota_exhausted")
        else:
            target.add("terminal_error")
    failures.update(transient_errors)
    if any(STDERR_USAGE_LIMIT.match(line.strip()) for line in stderr.splitlines()):
        failures.add("quota_exhausted")
    for failure in ("terminal_policy", "terminal_configuration", "terminal_error", "quota_exhausted"):
        if failure in failures:
            return failure
    return ""


def _redact_headers(text):
    """Blank complete credential header values, including obs-fold lines."""
    lines = []
    header_indent = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        # curl-style '< ' / '> ' prefixes retain the actual header indentation.
        content = re.sub(r"^[ \t]*[<>][ ]?", "", body)
        indent = len(content) - len(content.lstrip(" \t"))
        if body.strip() and header_indent is not None and indent > header_indent:
            prefix_end = len(body) - len(content) + indent
            lines.append(body[:prefix_end] + "<redacted>" + newline)
            continue
        header_indent = None
        match = HEADER.match(body)
        if match and CREDENTIAL_HEADER.fullmatch(match["key"]):
            lines.append(body[:match.end()] + "<redacted>" + newline)
            header_indent = indent
        else:
            lines.append(line)
    return "".join(lines)


def _quoted_end(text, start):
    """Scan a quoted value without depending on its contents or length."""
    quote = text[start]
    position = start + 1
    while position < len(text):
        if text[position] == "\\":
            position += 2
        elif text[position] == quote:
            if quote == "'" and text[position:position + 2] == "''":
                position += 2  # YAML single-quote escaping
            else:
                return position + 1
        else:
            position += 1
    return len(text)  # An unterminated credential consumes the remainder.


def _value_end(text, start, *, assignment=False):
    """Consume a whole scalar or balanced collection in JSON/YAML/env text."""
    if start == len(text):
        return start
    if assignment and text[start] not in "[{":
        # Env and query values can contain commas/braces, and shell quoting may
        # concatenate adjacent pieces. JSON collection separators do not apply.
        position = start
        while position < len(text) and text[position] not in " \t\r\n&;#":
            if text[position] in "\"'":
                position = _quoted_end(text, position)
            elif text[position] == "\\":
                position += 2
            else:
                position += 1
        return min(position, len(text))
    if text[start] in "\"'":
        return _quoted_end(text, start)
    if text[start] in "[{":
        stack = []
        position = start
        while position < len(text):
            char = text[position]
            if char in "\"'":
                position = _quoted_end(text, position)
                continue
            if char in "[{":
                stack.append("]" if char == "[" else "}")
            elif char in "]}":
                if not stack or char != stack.pop():
                    return len(text)  # Malformed credential collection.
                if not stack:
                    return position + 1
            position += 1
        return len(text)
    position = start
    while position < len(text) and text[position] not in "\r\n,;&}]":
        position += 1
    return position


def _yaml_block_end(text, match):
    """Include indented children of a sensitive YAML key/block scalar."""
    line_start = text.rfind("\n", 0, match.start()) + 1
    prefix = text[line_start:match.start()]
    if prefix.strip() not in ("", "-"):
        return match.end()
    line_end = text.find("\n", match.end())
    if line_end == -1:
        return len(text)
    position = line_end + 1
    while position < len(text):
        end = text.find("\n", position)
        end = len(text) if end == -1 else end + 1
        line = text[position:end]
        indent = len(line) - len(line.lstrip(" \t"))
        if (line.strip() and indent <= len(prefix)
                and not (indent == len(prefix) and line.lstrip().startswith("- "))):
            break
        position = end
    return position


def _credential_key(raw):
    if raw.startswith('"'):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = raw.strip('"')
    else:
        raw = raw.strip("'")
    raw = unquote_plus(raw)
    return bool(SENSITIVE_FIELD.search(raw) or CREDENTIAL_HEADER.fullmatch(raw))


def _redact_assignments(text):
    parts = []
    copied = 0
    position = 0
    while match := ASSIGNMENT.search(text, position):
        position = match.end()
        if not _credential_key(match["key"]):
            continue
        end = _value_end(text, position, assignment=match["separator"] != ":")
        if match["separator"] == ":":
            # YAML block and multiline values are credential values too.
            end = max(end, _yaml_block_end(text, match))
        replacement = '"<redacted>"' if match["key"].startswith('"') else "<redacted>"
        if text[position:end].endswith("\n"):
            replacement += "\n"
        parts.extend((text[copied:position], replacement))
        copied = position = end
    return "".join(parts) + text[copied:]


def _safe_shape(value):
    return bool(SAFE_HEX.fullmatch(value) or SAFE_UUID.fullmatch(value)
                or SAFE_TIMESTAMP.fullmatch(value))


def _redact_cli(text):
    def suppress(match):
        start = match.end()
        end = _value_end(text, start, assignment=True)
        return start, end

    spans = [suppress(m) for m in CLI_OPTION.finditer(text) if _credential_key(m["key"])]
    spans.extend(suppress(m) for m in CLI_LOGIN.finditer(text))
    for start, end in sorted(set(spans), reverse=True):
        text = text[:start] + "<redacted>" + text[end:]
    return text


def _redact_contexts(value, *, _depth=0):
    """Suppress whole credential values even when they have an allowed shape."""
    def escaped_string(match):
        literal = match.group()
        if "\\" not in literal:
            return literal
        # Serialized logs may embed serialized headers/JSON. Decode one layer
        # and use exactly the same context rules; do not regex-match through
        # quote escapes. Stop pathological nesting by dropping the whole value.
        if _depth >= 8:
            return '"<redacted>"'
        try:
            decoded = json.loads(literal)
        except ValueError:
            return '"<redacted>"'
        return json.dumps(_redact_contexts(decoded, _depth=_depth + 1), ensure_ascii=False)

    value = PEM_BLOCK.sub("<redacted>", str(value))
    value = JSON_STRING.sub(escaped_string, value)
    value = _redact_headers(value)
    value = URL_USERINFO.sub(r"\1", value)
    value = _redact_assignments(value)
    value = _redact_cli(value)
    value = BEARER_VALUE.sub(r"\1<redacted>", value)
    value = PASSWORD_VALUE.sub(r"\1<redacted>", value)
    value = JWT_VALUE.sub("<redacted>", value)
    value = TOKEN_VALUE.sub("<redacted>", value)
    value = AWS_KEY.sub("<redacted>", value)
    return EMAIL.sub("<redacted>", value)


@lru_cache(maxsize=1)
def _vocabulary():
    # Fail closed for evidence, but never prevent the independent classifier
    # from reporting quota/policy/etc. if this evidence-only resource is absent.
    return frozenset(
        word.casefold()
        for line in Path(__file__).with_name("provider-error-vocabulary.txt").read_text(
            encoding="utf-8").splitlines()
        for word in line.partition("#")[0].split()
    )


def _allowed_atom(value):
    if NUMBER.fullmatch(value):
        # A long decimal is not a git SHA just because it has 40/64 digits.
        return sum(c.isdigit() for c in value) <= 10
    return (value.casefold() in _vocabulary() or _safe_shape(value)
            or ERROR_CODE.fullmatch(value))


def _keep_atom(value):
    # Keep sentence punctuation / CLI flag prefixes apart from the word, without
    # exempting a whole assignment because just its value is a SHA or timestamp.
    prefix = value[:len(value) - len(value.lstrip("-"))]
    suffix = value[len(value.rstrip(".")):]
    atom = value[len(prefix):len(value) - len(suffix) if suffix else len(value)]
    if not atom:
        return prefix + suffix if prefix or suffix else "<word>"
    if _allowed_atom(atom):
        kept = atom
    elif NUMBER.fullmatch(atom):
        kept = "<num>"
    elif atom.isalpha():
        kept = "<word>"
    else:
        kept = "<id>"
    return prefix + kept + suffix


def _keep_path(value):
    value = HOME_PATH.sub("~", value)
    if not value.startswith("~/"):
        return "<path>"
    for component in value[2:].rstrip("/").split("/"):
        if _safe_shape(component) and not NUMBER.fullmatch(component):
            continue
        # Dotfiles, package names, and extensions can compose known words, but
        # arbitrary alphanumeric components (e.g. customer names) cannot pass.
        words = [part for part in re.split(r"[._-]", component) if part]
        if not words or not all(_allowed_atom(word) for word in words):
            return "<path>"
    return value


def _keep_url(value):
    # A URL is summarized, never replayed. Neither query/fragment nor path nor
    # userinfo is retained. Only here can a dotted string be a hostname; a bare
    # dotted token may be an unfamiliar credential and receives no exemption.
    suffix = value[len(value.rstrip(".,;)")):]
    try:
        parsed = urlsplit(value.rstrip(".,;)"))
        host = parsed.hostname or ""
        port = parsed.port
        if ":" in host:
            ipaddress.IPv6Address(host)
            host = f"[{host}]"
        elif not (0 < len(host) <= 253 and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split(".")
        )):
            return "<url-host:unknown>" + suffix
        return f"<url-host:{host}{':' + str(port) if port is not None else ''}>" + suffix
    except ValueError:
        return "<url-host:unknown>" + suffix


def redact_text(value):
    """Keep only reviewed diagnostic words and explicit non-secret token classes.

    This lossy evidence is not a raw log or an arbitrary-secret detector: the
    allowlisted words, short numbers, error codes, SHAs, UUIDs, timestamps and
    URL hosts are intentional disclosures. Credential contexts override those
    exemptions. No vocabulary is learned from the text being sanitized.
    """
    value = _redact_contexts(value)
    value = re.sub(r"\x1b\[[0-9;]*m", "", value)
    parts = []
    for match in LEXEME.finditer(value):
        token = match.group()
        if match.lastgroup in {"timestamp", "structure"}:
            parts.append(token)
        elif match.lastgroup == "url":
            parts.append(_keep_url(token))
        elif match.lastgroup == "path":
            parts.append(_keep_path(token))
        else:
            parts.append(_keep_atom(token))
    return "".join(parts)


def _redact(value, key=""):
    if key and SENSITIVE_FIELD.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # A JSON scalar must not bypass the textual numeric bound.
        return value if _allowed_atom(str(value).lstrip("-")) else "<num>"
    return value


def _bounded_scalar(value, key):
    if isinstance(value, (dict, list)) or value is None:
        return None
    if not isinstance(value, (str, int, float, bool)):
        return None
    value = _redact(value, key)
    if isinstance(value, str):
        value = value.encode("utf-8")[:MAX_FIELD_BYTES].decode("utf-8", errors="ignore")
    return value


def _serialized_size(value):
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _unmapped_provider_fields(events):
    rows = []
    for original in events:
        event, kind, error = _envelope(original)
        if event is None or error is None:
            continue
        fields = {}

        def retain(key, value, *, nested=False):
            if (not isinstance(key, str) or not FIELD_NAME.fullmatch(key)
                    or any(body in key.lower() for body in BODY_FIELDS)):
                return True
            value = _bounded_scalar(value, key)
            if value is None:
                return True
            safe_key = redact_text(key)
            if safe_key != key:
                # Unknown field names can themselves contain secrets. Preserve
                # multiple unknown fields without overwriting a placeholder key.
                occupied = fields.get("error", {}) if nested else fields
                key = f"{safe_key}:{len(occupied)}"
            trial = dict(fields)
            if nested:
                nested_fields = dict(trial.get("error", {}))
                nested_fields[key] = value
                trial["error"] = nested_fields
            else:
                trial[key] = value
            candidate = rows + [{"event_type": kind, "fields": trial}]
            if _serialized_size(candidate) > MAX_UNMAPPED_BYTES:
                return False
            fields.clear()
            fields.update(trial)
            return True

        for key in sorted(SAFE_EVENT_FIELDS):
            if key in event and not retain(key, event[key]):
                return rows
        if isinstance(error, dict) and error is not event:
            for key, value in sorted(error.items()):
                retain_field = key not in MAPPED_ERROR_FIELDS
                if key in {"codex_error_info", "code", "type", "status"}:
                    retain_field = str(value) not in QUOTA | DENIAL | CONFIG
                if retain_field and not retain(key, value, nested=True):
                    return rows
        if fields:
            rows.append({"event_type": kind, "fields": fields})
    return rows


def _tail_bytes(value, limit=4096):
    raw = value.encode("utf-8")
    if len(raw) <= limit:
        return value
    return raw[-limit:].decode("utf-8", errors="ignore")


def _ensure_self_ignored(directory):
    ignore = directory / ".gitignore"
    raw = b"*\n"
    if ignore.exists() and ignore.read_bytes() == raw:
        os.chmod(ignore, 0o600)
        return
    temporary = ignore.with_name(f".{ignore.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, ignore)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_evidence(path, events, stderr, *, failure_class, dispatch_id,
                   attempt_id, receipt_path):
    """Atomically write a private, redacted failure artifact and its reference."""
    path = Path(path)
    events = list(events)
    evidence = {
        "schema_version": 1,
        "dispatch_id": dispatch_id,
        "attempt_id": attempt_id,
        "failure_class": failure_class,
        "stderr_tail": _tail_bytes(redact_text(stderr)),
        "unmapped_provider_fields": _unmapped_provider_fields(events),
    }
    raw = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _ensure_self_ignored(path.parent)
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError(f"failure evidence already exists with different content: {path}")
        return {"path": receipt_path, "sha256": hashlib.sha256(raw).hexdigest()}
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return {"path": receipt_path, "sha256": hashlib.sha256(raw).hexdigest()}


def read_events(path):
    try:
        with open(path) as stream:
            for line in stream:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("events")
    parser.add_argument("--stderr")
    parser.add_argument("--write-evidence")
    parser.add_argument("--receipt-path")
    parser.add_argument("--failure-class")
    parser.add_argument("--dispatch-id")
    parser.add_argument("--attempt-id")
    args = parser.parse_args(argv)
    events = list(read_events(args.events))
    stderr = ""
    if args.stderr:
        try:
            stderr = Path(args.stderr).read_text(errors="replace")
        except OSError:
            pass
    if args.write_evidence:
        required = {
            "receipt path": args.receipt_path,
            "failure class": args.failure_class,
            "dispatch id": args.dispatch_id,
            "attempt id": args.attempt_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error("missing evidence metadata: " + ", ".join(missing))
        print(json.dumps(write_evidence(
            args.write_evidence,
            events,
            stderr,
            failure_class=args.failure_class,
            dispatch_id=args.dispatch_id,
            attempt_id=args.attempt_id,
            receipt_path=args.receipt_path,
        ), separators=(",", ":")))
    else:
        print(classify(events, stderr))


if __name__ == "__main__":
    main()
