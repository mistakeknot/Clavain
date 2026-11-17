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
from clavain_selector.contract import Point, Provenance, SessionRef
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
        fit_questions=True,
        host={"name": "claude-code", "version": "2.1.282"},
        adapter_version="1",
        mode="shadow",
        egress_verdict="admitted",
        applied="native",
        fallback_reason="shadow_mode",
        provenance=Provenance.OPERATOR,
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
    # The 16 kept are the canonically first 16 (request.candidates is already
    # canonicalized at construction time; capping just takes a prefix).
    expected_first_16 = [c.id for c in request_many.candidates[:16]]
    assert [entry["id"] for entry in record_many["candidates"]] == expected_first_16
    # The request itself is structurally invalid (>16 candidates), so no
    # question battery was ever built for it: questions_sha256 stays null
    # even though egress_verdict == "admitted".
    assert record_many["request"]["question_set_version"] is not None
    assert record_many["request"]["questions_sha256"] is None

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
    from clavain_selector.contract import Provenance as _Provenance  # noqa: PLC0415
    from clavain_selector.records import build_record as _build_record  # noqa: PLC0415
    from selector_helpers import make_request  # noqa: PLC0415

    for _ in range(n):
        rec = _build_record(
            request=make_request(),
            fit_questions=True,
            host={"name": "claude-code", "version": "2.1.282"},
            adapter_version="1",
            mode="shadow",
            egress_verdict="admitted",
            applied="native",
            fallback_reason="shadow_mode",
            provenance=_Provenance.OPERATOR,
        )
        _records.append_record(rec, record_dir=record_dir)


def test_concurrent_append(tmp_path):
    record_dir = tmp_path / "selector" / "records"
    # Pin "spawn": Python 3.14 defaults to "forkserver", which connects to its
    # server over a Unix socket that the loopback-only socket guard rightly
    # refuses. Spawn hands the child its state over a pipe, needs no socket, and
    # behaves the same on every platform (mk-47vtm.1).
    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(target=_append_worker, args=(str(record_dir), 50))
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


def test_build_record_requires_fit_questions_keyword():
    kwargs = _base_kwargs()
    del kwargs["fit_questions"]
    with pytest.raises(TypeError):
        build_record(**kwargs)


def test_record_question_identity():
    import clavain_selector.questions as questions

    request = make_request(
        candidates=(make_candidate(id="cand-a"), make_candidate(id="cand-b")),
    )

    admitted_true = build_record(**_base_kwargs(request=request, egress_verdict="admitted", fit_questions=True))
    admitted_false = build_record(**_base_kwargs(request=request, egress_verdict="admitted", fit_questions=False))
    assert admitted_true["request"]["question_set_version"] == questions.QUESTION_SET_VERSION
    assert admitted_false["request"]["question_set_version"] == questions.QUESTION_SET_VERSION
    assert admitted_true["request"]["questions_sha256"] is not None
    assert admitted_false["request"]["questions_sha256"] is not None
    assert admitted_true["request"]["questions_sha256"] != admitted_false["request"]["questions_sha256"]

    views = [c.selector_view() for c in request.candidates]
    battery = questions.build_battery(views, fit_questions=True)
    assert admitted_true["request"]["questions_sha256"] == battery.sha256

    for verdict in ("refused", "not_run"):
        record = build_record(**_base_kwargs(request=request, egress_verdict=verdict))
        assert record["request"]["question_set_version"] == questions.QUESTION_SET_VERSION
        assert record["request"]["questions_sha256"] is None

    # An invalid request (empty candidates -> NO_CANDIDATES) never raises
    # from build_record, and reports questions_sha256 as null even if the
    # caller (incorrectly) claims egress_verdict="admitted".
    invalid_request = make_request(candidates=())
    invalid_record = build_record(
        **_base_kwargs(request=invalid_request, egress_verdict="admitted", fallback_reason="no_candidates")
    )
    assert invalid_record["request"]["questions_sha256"] is None


def test_record_permutation_invariant():
    ids = ["zeta", "alpha", "mu", "beta"]
    forward = make_request(candidates=tuple(make_candidate(id=i) for i in ids))
    reversed_request = make_request(candidates=tuple(make_candidate(id=i) for i in reversed(ids)))

    record_forward = build_record(**_base_kwargs(request=forward, egress_verdict="admitted"))
    record_reversed = build_record(**_base_kwargs(request=reversed_request, egress_verdict="admitted"))

    assert record_forward["request"]["sha256"] == record_reversed["request"]["sha256"]
    assert record_forward["request"]["questions_sha256"] == record_reversed["request"]["questions_sha256"]
    assert [c["id"] for c in record_forward["candidates"]] == [c["id"] for c in record_reversed["candidates"]]


def test_record_duplicate_id_request_does_not_raise():
    dup_request = make_request(candidates=(make_candidate(id="same"), make_candidate(id="same")))
    record = build_record(
        **_base_kwargs(request=dup_request, egress_verdict="not_run", fallback_reason="invalid_input")
    )
    assert record["request"]["questions_sha256"] is None


def test_record_provenance_and_preparer_round_trip():
    record_operator = build_record(**_base_kwargs(provenance=Provenance.OPERATOR, preparer=None))
    assert record_operator["request"]["provenance"] == Provenance.OPERATOR.value
    assert record_operator["request"]["preparer"] is None

    record_preparer = build_record(**_base_kwargs(provenance=Provenance.PREPARER, preparer="claude-code-bash"))
    assert record_preparer["request"]["provenance"] == Provenance.PREPARER.value
    assert record_preparer["request"]["preparer"] == "claude-code-bash"

    record_eval = build_record(**_base_kwargs(provenance=Provenance.EVAL_CASE))
    assert record_eval["request"]["provenance"] == Provenance.EVAL_CASE.value
    assert record_eval["request"]["preparer"] is None

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    request_schema = schema["properties"]["request"]
    assert "provenance" in request_schema["required"]
    assert "preparer" in request_schema["required"]
    assert set(request_schema["properties"]["provenance"]["enum"]) == {p.value for p in Provenance}


def test_build_record_requires_provenance_keyword():
    kwargs = _base_kwargs()
    del kwargs["provenance"]
    with pytest.raises(TypeError):
        build_record(**kwargs)


def test_record_external_provenance():
    """build_record accepts a request with provenance == Provenance.EXTERNAL
    and preparer is None; the record's request block reflects these values."""
    request = make_request()
    record = build_record(
        **_base_kwargs(
            request=request,
            provenance=Provenance.EXTERNAL,
            preparer=None,
        )
    )
    # Verify the record was built successfully
    assert record["request"]["provenance"] == "external"
    assert record["request"]["preparer"] is None

    # Round-trip through JSON to ensure serialization is valid
    serialized = json.dumps(record)
    deserialized = json.loads(serialized)
    assert deserialized["request"]["provenance"] == "external"
    assert deserialized["request"]["preparer"] is None


def test_unwritable_raises(tmp_path):
    record_dir = tmp_path / "readonly" / "records"
    record_dir.parent.mkdir(parents=True)
    os.chmod(record_dir.parent, 0o500)
    try:
        with pytest.raises(RecordUnwritable):
            append_record(build_record(**_base_kwargs()), record_dir=record_dir)
    finally:
        os.chmod(record_dir.parent, 0o700)

@pytest.mark.parametrize('component', ['.clavain', 'outcomes', 'dayfile'])
def test_outcome_refuses_symlinks(tmp_path, component):
    import datetime as dt
    root = tmp_path / 'project'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir(mode=0o755)
    parent = root / '.clavain'
    if component == '.clavain':
        parent.symlink_to(outside, target_is_directory=True)
    else:
        parent.mkdir()
        if component == 'outcomes':
            (parent / 'outcomes').symlink_to(outside, target_is_directory=True)
        else:
            (parent / 'outcomes').mkdir()
            (parent / 'outcomes' / (dt.datetime.now(dt.timezone.utc).date().isoformat() + '.jsonl')).symlink_to(outside / 'data')
    with pytest.raises(RecordUnwritable):
        append_outcome('synthetic-id', 'verified', record_dir=parent / 'decisions')
    assert list(outside.iterdir()) == []
    assert stat.S_IMODE(outside.stat().st_mode) == 0o755


def test_project_log_cap_spans_day_files(tmp_path):
    directory = tmp_path / '.clavain/decisions'
    first = {'created_at': '2026-01-01T00:00:00Z', 'value': 'synthetic'}
    second = dict(first, created_at='2026-01-02T00:00:00Z')
    size = len((json.dumps(first, sort_keys=True, ensure_ascii=True) + '\n').encode())
    append_record(first, record_dir=directory, project_root=tmp_path, max_bytes=size)
    with pytest.raises(RecordUnwritable):
        append_record(second, record_dir=directory, project_root=tmp_path, max_bytes=size)
    assert read_records(record_dir=directory) == [first]
    assert sum(p.stat().st_size for p in directory.glob('*.jsonl')) == size


def test_outcome_allows_symlink_above_trusted_project(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    path = append_outcome('synthetic', 'verified', record_dir=alias / '.clavain/decisions')
    assert path.exists()
    assert json.loads(path.read_text())['decision_id'] == 'synthetic'


def test_cap_requires_project_root(tmp_path):
    with pytest.raises(ValueError):
        append_record({}, record_dir=tmp_path, max_bytes=1)


def test_project_gitignore_without_repository_ignore(tmp_path):
    import subprocess
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    directory = tmp_path / '.clavain/decisions'
    path = append_record({}, record_dir=directory, project_root=tmp_path)
    ignore = directory / '.gitignore'
    assert ignore.read_text() == '*\n!.gitignore\n'
    before = ignore.stat()
    append_record({}, record_dir=directory, project_root=tmp_path)
    assert ignore.stat().st_mtime_ns == before.st_mtime_ns
    assert not (tmp_path / '.gitignore').exists()
    result = subprocess.run(['git', '-C', str(tmp_path), 'check-ignore', str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0
    result = subprocess.run(['git', '-C', str(tmp_path), 'check-ignore', str(ignore)],
                            capture_output=True, text=True)
    assert result.returncode == 1


@pytest.mark.parametrize('existing', ['different', 'symlink', 'dangling', 'directory'])
def test_project_gitignore_preserves_existing(tmp_path, existing):
    directory = tmp_path / '.clavain/decisions'
    directory.mkdir(parents=True)
    ignore = directory / '.gitignore'
    outside = tmp_path / 'outside'
    if existing == 'different':
        ignore.write_text('custom\n')
    elif existing == 'directory':
        ignore.mkdir()
    else:
        if existing == 'symlink':
            outside.write_text('untouched\n')
        ignore.symlink_to(outside)
    before = ignore.lstat()
    append_record({}, record_dir=directory, project_root=tmp_path)
    assert ignore.lstat() == before
    if existing == 'different':
        assert ignore.read_text() == 'custom\n'
    elif existing == 'symlink':
        assert outside.read_text() == 'untouched\n'
    elif existing == 'dangling':
        assert not outside.exists()


def test_failed_ignore_publication_can_retry(tmp_path, monkeypatch):
    from clavain_selector import records
    original = records.os.fsync
    def fail(fd):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(records.os, 'fsync', fail)
    directory = tmp_path / '.clavain/decisions'
    with pytest.raises(RecordUnwritable):
        append_record({}, record_dir=directory, project_root=tmp_path)
    assert not (directory / '.gitignore').exists()
    monkeypatch.setattr(records.os, 'fsync', original)
    append_record({}, record_dir=directory, project_root=tmp_path)
    assert (directory / '.gitignore').read_text() == '*\n!.gitignore\n'


def test_admission_creates_ignore(tmp_path):
    from clavain_selector import records
    with records.admit_project_record(tmp_path, max_bytes=1000, reserve_bytes=100) as write:
        write({})
    assert (tmp_path / '.clavain/decisions/.gitignore').read_text() == '*\n!.gitignore\n'
