import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def subject():
    spec = importlib.util.spec_from_file_location("delivery_usage", Path(__file__).parents[1] / "scripts/task-delivery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixtures(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text('{"type":"thread.started","thread_id":"native-child"}\n')
    records = [dict(id=1, rule_matched="measured-delivery-enrollment", context_json=dict(
        enrollment_id="e", cohort_id="c", manifest_sha256="a" * 64,
        enrolled_at="2026-09-12T10:00:00Z", bead_id="b")),
        dict(id=2, rule_matched="measured-delivery-dispatch-request", context_json=dict(
            enrollment_id="e", cohort_id="c", manifest_sha256="a" * 64, dispatch_id="d")),
        dict(id=3, rule_matched="dispatch-profile", context_json=dict(
            dispatch_id="d", attempt_id="a", state="completed", execution={"backend": "codex", "event_log": str(events)},
            task_envelope=dict(enrollment_id="e", cohort_id="c", manifest_sha256="a" * 64)))]
    observation = dict(id="u", captured_at="2026-09-12T10:00:01Z", source="s", kind="account_usage",
        counters=[dict(name="input", value=None)], identity=dict(native_thread_id="native-child"),
        execution_refs={}, payload_sha256="b" * 64, supersedes=None)
    request = dict(id="bound-u", observation_id="u", enrollment_id="e", dispatch_request_id=2,
        execution_id=3, attempt_id="a", evidence_refs=[dict(path=str(events), sha256=hashlib.sha256(events.read_bytes()).hexdigest())])
    seal_collection(tmp_path, records, observation, request)
    return records, observation, request


def seal_collection(tmp_path, records, observation, request, phase="completion"):
    artifact = tmp_path / "observation.json"
    artifact.write_text(json.dumps(observation))
    manifest = tmp_path / "collection.json"
    manifest.write_text(json.dumps(dict(phase=phase, observation_artifacts=[dict(path=artifact.name,
        sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())])))
    ref = dict(path=str(manifest), sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    if phase == "completion":
        records[-1]["context_json"]["execution"]["usage_collection"] = ref
    else:
        records[-1]["context_json"]["execution"].pop("usage_collection", None)
        records[1]["context_json"]["usage_collection"] = ref
    request["evidence_refs"] = request["evidence_refs"][:1] + [ref]


def test_binding_appends_successor_preserving_measurement(tmp_path):
    records, original, request = fixtures(tmp_path)
    original.update(canonical_sha256="c" * 64, inserted_at=1)
    before = copy.deepcopy(original)
    result = subject().bind_usage_record(records, [original], request)
    assert original == before
    assert result["id"] == "bound-u" and result["supersedes"] == "u"
    assert result["counters"] == original["counters"]
    assert result["payload_sha256"] == original["payload_sha256"]
    assert result["captured_at"] == original["captured_at"]
    assert result["execution_refs"]["attempt_id"] == "a"
    assert result["execution_refs"].get("dispatch_id") is None  # wrapper UUID is not a verified kernel primary key
    assert "canonical_sha256" not in result and "inserted_at" not in result


@pytest.mark.parametrize("gap", ["enrollment", "request", "execution", "attempt", "cohort", "identity", "hash", "timestamp", "unknown"])
def test_binding_rejects_missing_conflicting_or_stale_evidence(tmp_path, gap):
    records, original, request = fixtures(tmp_path)
    if gap == "enrollment": records.pop(0)
    if gap == "request": records.pop(1)
    if gap == "execution": records.pop(2)
    if gap == "attempt": request["attempt_id"] = "other"
    if gap == "cohort": records[-1]["context_json"]["task_envelope"]["cohort_id"] = "other"
    if gap == "identity": original["identity"]["native_thread_id"] = "parent"
    if gap == "hash": request["evidence_refs"][0]["sha256"] = "0" * 64
    if gap == "timestamp": original["captured_at"] = "2026-09-11T10:00:01Z"
    if gap == "unknown": request["acceptance"] = True
    with pytest.raises(ValueError):
        subject().bind_usage_record(records, [original], request)


def test_unidentified_boundary_observation_stays_unidentified(tmp_path):
    records, original, request = fixtures(tmp_path)
    original["identity"]["native_thread_id"] = None
    seal_collection(tmp_path, records, original, request, "boundary")
    bound = subject().bind_usage_record(records, [original], request)
    assert bound["identity"]["native_thread_id"] is None
    assert bound["execution_refs"]["execution_id"] is None
    assert bound["execution_refs"]["attempt_id"] is None


@pytest.mark.parametrize("gap", ["unlinked", "observation_changed", "artifact_changed", "wrong_phase"])
def test_account_observation_requires_immutable_collection_provenance(tmp_path, gap):
    records, original, request = fixtures(tmp_path)
    original["identity"]["native_thread_id"] = None
    seal_collection(tmp_path, records, original, request)
    if gap == "unlinked": records[-1]["context_json"]["execution"].pop("usage_collection")
    if gap == "observation_changed": original["counters"][0]["value"] = 99
    if gap == "artifact_changed": (tmp_path / "observation.json").write_text("{}")
    if gap == "wrong_phase":
        seal_collection(tmp_path, records, original, request, "boundary")
        records[-1]["context_json"]["execution"]["usage_collection"] = records[1]["context_json"].pop("usage_collection")
    with pytest.raises(ValueError):
        subject().bind_usage_record(records, [original], request)


@pytest.mark.parametrize("args", [["--rec", "missing"], ["--wat", "missing"], ["--record", "missing", "extra"]])
def test_binding_cli_rejects_unknown_grammar(tmp_path, args):
    result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "scripts/task-delivery.py"),
        "--db", str(tmp_path / "db"), "bind-usage", *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr or "required" in result.stderr


def test_nested_dispatch_drops_parent_collection_controls(monkeypatch):
    monkeypatch.setattr(os, "environ", {"CLAVAIN_USAGE_OUTPUT_DIR": "/parent/private/evidence",
        "CLAVAIN_REVIEW_EVENTS": "/parent/private/events"})
    env = subject().dispatch_environment()
    assert "CLAVAIN_USAGE_OUTPUT_DIR" not in env
    assert "CLAVAIN_REVIEW_EVENTS" not in env
