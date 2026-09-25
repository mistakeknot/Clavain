"""Tests for scripts/clavain_selector/records.py (mk-42j9.7 Task 4).

No real transcript text is printed; every canary below is a synthetic marker
string, never real project material.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import stat
from pathlib import Path

import pytest
from selector_helpers import make_candidate, make_request, selector_socket_guard  # noqa: F401

from clavain_selector import records
from clavain_selector.contract import Point, SessionRef
from clavain_selector.records import (
    RecordUnwritable,
    append_outcome,
    append_record,
    build_record,
    effective_applied,
    read_records,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "selector-decision-record.v1.schema.json"

_TOP_LEVEL_KEYS = {
    "schema", "schema_version", "decision_id", "created_at", "point", "integration",
    "host", "adapter_version", "mode", "session", "task_revision", "request",
    "candidates", "selector", "result", "validation", "fallback", "applied",
    "egress", "flags", "policy",
}


def _base_kwargs(**overrides):
    kwargs = dict(
        request=make_request(),
        host={"name": "claude-code", "version": "2.1.282"},
        adapter_version="1",
        mode="shadow",
        egress_verdict="admitted",
        applied="native",
        fallback_reason="shadow_mode",
    )
    kwargs.update(overrides)
    return kwargs


def test_record_shape():
    record = build_record(**_base_kwargs())
    assert set(record.keys()) == _TOP_LEVEL_KEYS

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(schema["required"]) == _TOP_LEVEL_KEYS


def test_no_forbidden_content():
    canary = "CANARY-TASK-CONTEXT-PAYLOAD-9f3c"
    request = make_request(
        task=f"do the thing {canary}",
        context=f"background {canary}",
        candidates=(
            make_candidate(
                id="brainstorming",
                description=f"desc with {canary}",
                payload={"secret": canary, "raw": canary},
            ),
        ),
    )
    record = build_record(**_base_kwargs(request=request, egress_verdict="admitted"))
    serialized = json.dumps(record)
    assert canary not in serialized.replace(f"desc with {canary}"[:96], "")
    # The description prefix (<=96 chars) is allowed as a summary when admitted.
    assert record["candidates"][0]["summary"].startswith("desc with")
    # But the raw payload / task / context text never appears.
    assert "do the thing" not in serialized
    assert "background" not in serialized
    assert '"raw"' not in serialized


def test_refused_record_has_no_summaries():
    canary_id_shape = "escalate-like-id-9f3c"
    canary_desc = "REFUSED-CANARY-DESCRIPTION-TEXT"
    request = make_request(
        candidates=(make_candidate(id="cand-a", description=canary_desc),),
    )
    for verdict in ("refused", "not_run"):
        record = build_record(**_base_kwargs(request=request, egress_verdict=verdict, applied="native"))
        serialized = json.dumps(record)
        assert canary_desc not in serialized
        assert canary_id_shape not in serialized
        assert "cand-a" not in serialized
        for entry in record["candidates"]:
            assert set(entry.keys()) == {"id_sha256", "payload_sha256"}


def test_applied_values():
    build_record(**_base_kwargs(applied="native"))
    build_record(**_base_kwargs(applied="emitted", mode="active"))
    with pytest.raises(ValueError):
        build_record(**_base_kwargs(applied="selected"))

    record = build_record(**_base_kwargs(applied="emitted", mode="active"))
    assert effective_applied(record, []) == "emitted_unconfirmed"
    assert effective_applied(record, [{"decision_id": record["decision_id"], "host_applied": "selected"}]) == "selected"
    assert effective_applied(record, [{"decision_id": record["decision_id"], "host_applied": "original"}]) == "original"

    native_record = build_record(**_base_kwargs(applied="native"))
    assert effective_applied(native_record, []) == "native"

    def _walk(value):
        if isinstance(value, dict):
            for key, sub in value.items():
                assert key not in {"task", "context", "payload", "prompt", "raw", "key", "authorization"}
                _walk(sub)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    _walk(record)


def test_bounds():
    long_description = "y" * 300
    request = make_request(candidates=(make_candidate(id="cand-long", description=long_description),))
    record = build_record(**_base_kwargs(request=request, egress_verdict="admitted"))
    assert len(record["candidates"][0]["summary"]) == 96

    many_candidates = tuple(make_candidate(id=f"c{i}") for i in range(20))
    request_many = make_request(candidates=many_candidates)
    record_many = build_record(**_base_kwargs(request=request_many, egress_verdict="admitted"))
    assert len(record_many["candidates"]) == 16
    assert record_many["request"]["candidate_count"] == 16

    record_scores = build_record(
        **_base_kwargs(result={"kind": "selected", "candidate_id": "c0", "confidence": 1.7, "fit": float("nan")})
    )
    assert record_scores["result"]["confidence"] == 1.0
    assert record_scores["result"]["fit"] is None

    record_detail = build_record(**_base_kwargs(fallback_detail="z" * 250))
    assert len(record_detail["fallback"]["detail"]) == 200


def test_permissions(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAVAIN_STATE_DIR", raising=False)
    record_dir = tmp_path / "selector" / "records"
    monkeypatch.setenv("CLAVAIN_SELECTOR_RECORD_DIR", str(record_dir))
    record = build_record(**_base_kwargs())
    path = append_record(record)
    assert stat.S_IMODE(record_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def _append_worker(record_dir: str, n: int) -> None:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    os.environ["CLAVAIN_SELECTOR_RECORD_DIR"] = record_dir
    from clavain_selector import records as _records  # noqa: PLC0415
    from clavain_selector.records import build_record as _build_record  # noqa: PLC0415
    from selector_helpers import make_request  # noqa: PLC0415

    for _ in range(n):
        rec = _build_record(
            request=make_request(),
            host={"name": "claude-code", "version": "2.1.282"},
            adapter_version="1",
            mode="shadow",
            egress_verdict="admitted",
            applied="native",
            fallback_reason="shadow_mode",
        )
        _records.append_record(rec, record_dir=record_dir)


def test_concurrent_append(tmp_path):
    record_dir = tmp_path / "selector" / "records"
    procs = [
        multiprocessing.Process(target=_append_worker, args=(str(record_dir), 50))
        for _ in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
        assert p.exitcode == 0

    all_records = read_records(record_dir=record_dir)
    assert len(all_records) == 200
    for rec in all_records:
        assert rec["schema"] == "clavain.selector.decision"


def test_outcome_join(tmp_path):
    record_dir = tmp_path / "selector" / "records"
    record = build_record(**_base_kwargs(applied="emitted", mode="active"))
    append_record(record, record_dir=record_dir)
    path = append_outcome(
        record["decision_id"], "verified", host_applied="selected", record_dir=record_dir,
    )
    assert path.exists()
    raw_line_before = path.read_text(encoding="utf-8")

    joined = read_records(record_dir=record_dir, join_outcomes=True)
    assert len(joined) == 1
    assert joined[0]["outcomes"][0]["host_applied"] == "selected"
    assert effective_applied(joined[0], joined[0]["outcomes"]) == "selected"

    # The outcome file itself is untouched by the read.
    assert path.read_text(encoding="utf-8") == raw_line_before

    plain = read_records(record_dir=record_dir, join_outcomes=False)
    assert "outcomes" not in plain[0]


def test_unwritable_raises(tmp_path):
    record_dir = tmp_path / "readonly" / "records"
    record_dir.parent.mkdir(parents=True)
    os.chmod(record_dir.parent, 0o500)
    try:
        with pytest.raises(RecordUnwritable):
            append_record(build_record(**_base_kwargs()), record_dir=record_dir)
    finally:
        os.chmod(record_dir.parent, 0o700)
