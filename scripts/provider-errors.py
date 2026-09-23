#!/usr/bin/env python3
"""Classify provider error envelopes and retain safe failure evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

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
    r"(?:authorization|api[_-]?key|private[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"provider[_-]?token|password|secret|cookie|(?:^|[_-])token(?:$|[_-]))",
    re.IGNORECASE,
)
PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.DOTALL,
)
AUTH_VALUE = re.compile(
    r'''(?i)(["']?Authorization["']?\s*[:=]\s*["']?)(?:(?:Bearer|Basic)\s+)?[^"'\s,;}]+'''
)
BEARER_VALUE = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
COOKIE_VALUE = re.compile(r"(?im)^(\s*(?:set-)?cookie\s*[:=]\s*).*$")
ASSIGNED_SECRET = re.compile(
    r'''(?i)(?<![A-Z0-9_-])(["']?[A-Z0-9_-]{0,64}(?:API[_-]?KEY|PRIVATE[_-]?KEY|'''
    r'''ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|PASSWORD|SECRET|TOKEN)[A-Z0-9_-]{0,64}'''
    r'''["']?\s*[:=]\s*["']?)'''
    r'''[^"'\s,;}]+'''
)
PASSWORD_VALUE = re.compile(r"(?i)(\bpassword\s+)[^\s,;}]+")
JWT_VALUE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
TOKEN_VALUE = re.compile(
    r"\b(?:sk|tok|gh[pousr]|github_pat|glpat|ntn|xox[baprs])[-_][A-Za-z0-9._-]{6,}\b"
)
AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
HOME_PATH = re.compile(
    r"(?<![A-Za-z0-9_])(?:/(?:home|Users)/[^/\s]+|/root|/tmp|/var/folders)(?=/|\b)"
)
FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


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


def redact_text(value):
    """Remove credential, identity, and machine-home material from text."""
    value = PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", str(value))
    value = AUTH_VALUE.sub(r"\1[REDACTED]", value)
    value = BEARER_VALUE.sub(r"\1[REDACTED]", value)
    value = COOKIE_VALUE.sub(r"\1[REDACTED]", value)
    value = ASSIGNED_SECRET.sub(r"\1[REDACTED]", value)
    value = PASSWORD_VALUE.sub(r"\1[REDACTED]", value)
    value = JWT_VALUE.sub("[REDACTED]", value)
    value = TOKEN_VALUE.sub("[REDACTED]", value)
    value = AWS_KEY.sub("[REDACTED]", value)
    value = EMAIL.sub("[REDACTED EMAIL]", value)
    return HOME_PATH.sub("~", value)


def _redact(value, key=""):
    if key and SENSITIVE_FIELD.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
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
