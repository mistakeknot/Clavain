"""Schema-v1 decision records (mk-42j9.7 Task 4).

Implements the plan's "Decision records (schema v1)" section: `build_record`
assembles the bounded, prompt-free JSON object described there;
`append_record`/`append_outcome` persist it (and its later outcomes) under
`$CLAVAIN_SELECTOR_RECORD_DIR` (or `$CLAVAIN_STATE_DIR/selector/records`) as
flocked, mode-0600 JSONL files in a mode-0700 directory; `read_records` reads
them back, optionally joining outcomes; `effective_applied` derives the four
end states (`native`, `emitted_unconfirmed`, `selected`, `original`) from a
record plus its joined outcomes.

`build_record` never accepts a request's raw task/context text or a
candidate's raw payload -- only a `SelectionRequest` (whose `Candidate.payload`
it hashes, never serializes) and small, already-bounded metadata blocks for
`selector`/`result`/`validation`/`flags`/`policy`. Candidate ids and
descriptions cross into the record only when `egress_verdict == "admitted"`;
otherwise every candidate entry is reduced to `{id_sha256, payload_sha256}`.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from clavain_selector.contract import MAX_CANDIDATES, Candidate, Point, SelectionRequest, SessionRef

SCHEMA = "clavain.selector.decision"
SCHEMA_VERSION = 1

_VALID_APPLIED = ("native", "emitted")
_SUMMARY_MAX_CHARS = 96
_DETAIL_MAX_CHARS = 200

# Keys that must never appear anywhere in a serialized record, at any depth
# (Constraints: "Records never contain prompts, task text, context, candidate
# payloads, raw model output or credentials").
_FORBIDDEN_KEYS = frozenset({"task", "context", "payload", "prompt", "raw", "key", "authorization"})

# Score-like fields that get clamped to [0, 1] with non-finite -> null.
_UNIT_SCORE_FIELDS = ("confidence", "selected_probability", "fit")


class RecordUnwritable(Exception):
    """A decision record (or outcome) could not be persisted."""


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return ""
    return text[:limit]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_payload(payload: Any) -> str:
    try:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        serialized = repr(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _clamp_unit(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(1.0, number))


def _clamp_scores(block: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(block or {})
    for field in _UNIT_SCORE_FIELDS:
        if field in out:
            out[field] = _clamp_unit(out[field])
    return out


def _point_value(point: Point | str) -> str:
    return point.value if isinstance(point, Point) else str(point)


def _session_block(session: SessionRef) -> dict[str, Any]:
    return {"host_session_id": session.host_session_id, "bead_id": session.bead_id}


def _canonical_request_body(request: SelectionRequest) -> bytes:
    """The same canonical, selector-visible envelope egress.admit() scans.

    Reimplemented locally (rather than importing egress's private
    `_build_body`) so records.py stays independent of egress's internals;
    both hash exactly {schema, point, integration, task, context,
    candidates[{id, description}]}, so the resulting `request.sha256` is
    stable across a request whether or not `admit()` has already run for it.
    """
    payload = {
        "schema": "clavain-selection-v1",
        "point": _point_value(request.point),
        "integration": request.integration,
        "task": request.task,
        "context": request.context,
        "candidates": [c.selector_view() for c in request.candidates],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _request_block(request: SelectionRequest, candidate_count: int) -> dict[str, Any]:
    body = _canonical_request_body(request)
    return {
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "task_sha256": _sha256_text(request.task),
        "context_sha256": _sha256_text(request.context),
        "candidate_count": candidate_count,
    }


def _candidate_entries(candidates: Sequence[Candidate], *, admitted: bool) -> list[dict[str, Any]]:
    capped = list(candidates)[:MAX_CANDIDATES]
    entries: list[dict[str, Any]] = []
    for candidate in capped:
        payload_sha256 = _sha256_payload(candidate.payload)
        if admitted:
            entries.append({
                "id": candidate.id,
                "summary": _truncate(candidate.description, _SUMMARY_MAX_CHARS),
                "payload_sha256": payload_sha256,
                "prepared_at_revision": candidate.prepared_at_revision,
                "expires_at_ms": candidate.expires_at_ms,
                "read_set_fingerprint": candidate.read_set_fingerprint,
            })
        else:
            entries.append({
                "id_sha256": _sha256_text(candidate.id),
                "payload_sha256": payload_sha256,
            })
    return entries


def _no_forbidden_keys(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, sub in value.items():
            if key in _FORBIDDEN_KEYS:
                return False
            if not _no_forbidden_keys(sub):
                return False
        return True
    if isinstance(value, (list, tuple)):
        return all(_no_forbidden_keys(item) for item in value)
    return True


# ---------------------------------------------------------------------------
# build_record
# ---------------------------------------------------------------------------


def build_record(
    *,
    request: SelectionRequest,
    host: Mapping[str, Any],
    adapter_version: str,
    mode: str,
    egress_verdict: str,
    applied: str,
    fallback_reason: str | None,
    egress_rule_ids: Sequence[str] = (),
    terms_version: str = "typesafe-2026-09-25",
    fallback_detail: str = "",
    selector: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    validation: Mapping[str, Any] | None = None,
    flags: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    inputs_ref: str | None = None,
    decision_id: str | None = None,
    created_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Assemble one schema-v1 decision record.

    `egress_verdict` is one of `"admitted"`, `"refused"` or `"not_run"` (rows
    2-4 of the fallback table run before egress does). Only `"admitted"`
    lets candidate ids and description-derived summaries into the record;
    every other verdict reduces each candidate to `{id_sha256,
    payload_sha256}`. `applied` must be `"native"` or `"emitted"` -- the
    selector never writes `"selected"` (that is an outcome, joined later by
    `effective_applied`).
    """
    if applied not in _VALID_APPLIED:
        raise ValueError(f"applied must be one of {_VALID_APPLIED}, got {applied!r}")
    if inputs_ref is not None and mode != "eval":
        raise ValueError("inputs_ref is only allowed when mode == 'eval'")

    when = created_at or dt.datetime.now(dt.timezone.utc)
    admitted = egress_verdict == "admitted"
    candidates = _candidate_entries(request.candidates, admitted=admitted)
    candidate_count = len(candidates)

    record: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "decision_id": decision_id or f"sel_{uuid.uuid4().hex}",
        "created_at": when.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "point": _point_value(request.point),
        "integration": request.integration,
        "host": dict(host),
        "adapter_version": adapter_version,
        "mode": mode,
        "session": _session_block(request.session),
        "task_revision": request.task_revision,
        "request": _request_block(request, candidate_count),
        "candidates": candidates,
        "selector": dict({"backend": "jev"}, **(selector or {})),
        "result": _clamp_scores(result) if result else {"kind": "not_called"},
        "validation": dict({"stage": None, "reject_reason": None}, **(validation or {})),
        "fallback": {"reason": fallback_reason, "detail": _truncate(fallback_detail, _DETAIL_MAX_CHARS)},
        "applied": applied,
        "egress": {
            "verdict": egress_verdict,
            "rule_ids": list(egress_rule_ids),
            "terms_version": terms_version,
        },
        "flags": dict(flags or {}),
        "policy": dict({"contract_version": "clavain-selection-v1", "config_sha256": None}, **(policy or {})),
    }
    if mode == "eval" and inputs_ref is not None:
        record["inputs_ref"] = inputs_ref

    assert _no_forbidden_keys(record), "build_record produced a forbidden key"
    return record


# ---------------------------------------------------------------------------
# Location resolution
# ---------------------------------------------------------------------------


def _state_dir() -> Path:
    return Path(os.environ.get("CLAVAIN_STATE_DIR") or os.path.expanduser("~/.clavain")).expanduser()


def _default_record_dir() -> Path:
    override = os.environ.get("CLAVAIN_SELECTOR_RECORD_DIR")
    if override:
        return Path(override).expanduser()
    return _state_dir() / "selector" / "records"


def _resolve_record_dir(record_dir: str | Path | None) -> Path:
    return Path(record_dir).expanduser() if record_dir is not None else _default_record_dir()


def _outcomes_dir(record_dir: Path) -> Path:
    return record_dir.parent / "outcomes"


def _day_filename(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%d") + ".jsonl"


def _ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError as exc:
        raise RecordUnwritable(f"could not create directory {path}: {exc}") from exc


def _append_line(path: Path, line: str) -> None:
    _ensure_dir(path.parent)
    try:
        fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    except OSError as exc:
        raise RecordUnwritable(f"could not open {path}: {exc}") from exc
    try:
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as exc:
            raise RecordUnwritable(f"could not lock {path}: {exc}") from exc
        try:
            data = (line + "\n").encode("utf-8")
            written = os.write(fd, data)
            if written != len(data):
                raise RecordUnwritable(f"short write to {path}: {written}/{len(data)} bytes")
            os.fsync(fd)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    except OSError as exc:
        raise RecordUnwritable(f"could not write to {path}: {exc}") from exc
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# append_record / append_outcome / read_records / effective_applied
# ---------------------------------------------------------------------------


def append_record(record: Mapping[str, Any], *, record_dir: str | Path | None = None) -> Path:
    """Append one decision record as a JSONL line; returns the file written."""
    resolved_dir = _resolve_record_dir(record_dir)
    created_at = record.get("created_at")
    when = _parse_iso(created_at) if created_at else dt.datetime.now(dt.timezone.utc)
    path = resolved_dir / _day_filename(when)
    _append_line(path, json.dumps(record, sort_keys=True, ensure_ascii=True))
    return path


def append_outcome(
    decision_id: str,
    result: str,
    *,
    host_applied: str = "unknown",
    note: str | None = None,
    source: str = "operator",
    record_dir: str | Path | None = None,
    at: dt.datetime | None = None,
) -> Path:
    """Append one outcome entry to the sibling `outcomes/YYYY-MM-DD.jsonl`."""
    resolved_dir = _resolve_record_dir(record_dir)
    when = at or dt.datetime.now(dt.timezone.utc)
    entry = {
        "decision_id": decision_id,
        "at": when.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "result": result,
        "host_applied": host_applied,
        "source": source,
        "note": _truncate(note, 200) if note else None,
    }
    path = _outcomes_dir(resolved_dir) / _day_filename(when)
    _append_line(path, json.dumps(entry, sort_keys=True, ensure_ascii=True))
    return path


def _parse_iso(value: str) -> dt.datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return dt.datetime.fromisoformat(text)


def _read_jsonl_dir(path: Path) -> list[dict[str, Any]]:
    if not path.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for file_path in sorted(path.glob("*.jsonl")):
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries


def read_records(
    *,
    record_dir: str | Path | None = None,
    join_outcomes: bool = False,
) -> list[dict[str, Any]]:
    """All decision records under `record_dir`, optionally with joined outcomes.

    Joining never rewrites a record's on-disk line: each returned dict is a
    fresh copy with an added `outcomes` list (possibly empty).
    """
    resolved_dir = _resolve_record_dir(record_dir)
    records = _read_jsonl_dir(resolved_dir)
    if not join_outcomes:
        return records

    outcomes_by_decision: dict[str, list[dict[str, Any]]] = {}
    for outcome in _read_jsonl_dir(_outcomes_dir(resolved_dir)):
        outcomes_by_decision.setdefault(outcome.get("decision_id"), []).append(outcome)

    joined: list[dict[str, Any]] = []
    for record in records:
        copy = dict(record)
        copy["outcomes"] = list(outcomes_by_decision.get(record.get("decision_id"), []))
        joined.append(copy)
    return joined


def effective_applied(record: Mapping[str, Any], outcomes: Sequence[Mapping[str, Any]] = ()) -> str:
    """`native`, `emitted_unconfirmed`, `selected` or `original` for one record.

    `outcomes` are this record's joined outcome entries (as attached by
    `read_records(join_outcomes=True)`, or passed explicitly); the last one
    wins when there is more than one.
    """
    applied = record.get("applied")
    if applied == "native":
        return "native"
    if applied != "emitted":
        raise ValueError(f"unknown applied value in record: {applied!r}")

    host_applied = None
    for outcome in outcomes:
        candidate = outcome.get("host_applied")
        if candidate in ("selected", "original"):
            host_applied = candidate
    if host_applied == "selected":
        return "selected"
    if host_applied == "original":
        return "original"
    return "emitted_unconfirmed"
