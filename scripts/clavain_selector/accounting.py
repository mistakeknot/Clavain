"""One physical-attempt collector; unfinished work always has unknown usage."""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import threading

from clavain_selector.contract import MAX_TOKENS_COUNTER
TOKEN_KEYS = ("input_tokens", "output_tokens")
PHASES = ("not_started", "connect", "request_sent", "response_read")
ERROR_CLASSES = frozenset({"ValueError", "TypeError", "OSError", "RuntimeError", "TimeoutError", "KeyError", "AssertionError", "UnicodeDecodeError", "OverflowError", "_PointMismatch", "_ProvenanceModeError", "_BindingMismatch"})

def safe_class(exc):
    name = type(exc).__name__
    return name if name in ERROR_CLASSES else "other"

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def valid_usage(usage):
    return isinstance(usage, dict) and all(type(usage.get(k)) is int and 0 <= usage[k] <= MAX_TOKENS_COUNTER for k in TOKEN_KEYS)

def response_usage(data):
    try:
        obj = json.loads(data)
        usage = obj.get("usage") if isinstance(obj, dict) else None
        return {k: usage[k] for k in TOKEN_KEYS} if valid_usage(usage) else None
    except (ValueError, UnicodeError, TypeError):
        return None

class AttemptLog:
    def __init__(self):
        self._entries = []
        self._lock = threading.Lock()

    def begin(self, attempt_no, request_sha256=None):
        entry = dict(attempt_no=attempt_no, state="pending", started_at=stamp(), ended_at=None,
                     abandoned_at=None, interrupted_at=None, phase="not_started", http_status=None,
                     error_class=None, usage="unknown", usage_basis="unknown_pending",
                     request_sha256=request_sha256, response_sha256=None, request_id_sha256=None,
                     request_id_len=None, retry_after_ms=None, retry_after_malformed=False)
        with self._lock: self._entries.append(entry)
        return entry

    def progress(self, entry, phase):
        if phase not in PHASES: raise ValueError("invalid transport phase")
        with self._lock:
            if entry["state"] == "pending" and PHASES.index(phase) >= PHASES.index(entry["phase"]):
                entry["phase"] = phase

    def finalize(self, entry, box):
        from clavain_selector.jev_client import MAX_RESPONSE_BYTES, _retry_after_ms
        with self._lock:
            if entry["state"] != "pending": return
            if box.get("_timed_out"):
                entry.update(state="abandoned", abandoned_at=stamp(), usage_basis="unknown_abandoned")
                return
            entry.update(state="finished", ended_at=stamp(), error_class="ok")
            status = box.get("status")
            entry["http_status"] = status if type(status) is int else None
            data = box.get("data", b"")
            if data: entry["response_sha256"] = digest(data)
            headers = box.get("headers", {})
            request_id = headers.get("x-request-id") or headers.get("request-id")
            if isinstance(request_id, str):
                entry.update(request_id_sha256=digest(request_id.encode()), request_id_len=len(request_id))
            retry = headers.get("retry-after")
            entry["retry_after_ms"] = _retry_after_ms(retry)
            entry["retry_after_malformed"] = retry is not None and entry["retry_after_ms"] is None
            if "exception" in box:
                entry["error_class"] = "connect_error"
                if entry["phase"] in ("not_started", "connect"):
                    entry.update(usage={k: 0 for k in TOKEN_KEYS}, usage_basis="not_sent")
                else: entry["usage_basis"] = "unknown_unparseable"
            elif status != 200:
                entry.update(error_class="status", usage_basis="unknown_non200")
            else:
                usage = response_usage(data) if len(data) <= MAX_RESPONSE_BYTES else None
                if usage is not None: entry.update(usage=usage, usage_basis="reported")
                else: entry.update(error_class="schema", usage_basis="unknown_unparseable")

    def finalize_open(self):
        with self._lock:
            for entry in self._entries:
                if entry["state"] == "pending":
                    entry.update(state="interrupted", interrupted_at=stamp(), usage="unknown",
                                 usage_basis="unknown_interrupted", error_class=None)

    @staticmethod
    def _accounting(entries):
        reported = [e for e in entries if e["usage_basis"] == "reported"]
        not_sent = sum(e["usage_basis"] == "not_sent" for e in entries)
        unknown = len(entries) - len(reported) - not_sent
        return dict(basis_version=1, attempts=len(entries), reported_attempts=len(reported),
                    not_sent_attempts=not_sent, unknown_attempts=unknown,
                    known_total={k: sum(e["usage"][k] for e in reported) for k in TOKEN_KEYS}, complete=unknown == 0)

    def to_fields(self):
        with self._lock: entries = copy.deepcopy(self._entries)
        for entry in entries:
            if entry["state"] == "pending":
                entry.update(state="interrupted", interrupted_at=stamp(), usage_basis="unknown_interrupted", error_class=None)
        return dict(attempt_records=entries, jev_usage_accounting=self._accounting(entries), attempts=len(entries))
