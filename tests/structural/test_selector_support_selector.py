"""Selector collector integration through the real client with fake transport."""
import json
import threading
import pytest
from clavain_selector import selector, jev_client as j, burn
from support_helpers import isolation, require_netns  # noqa: F401
from test_selector_orchestrator import _operator, _registry, _select, FakeAdapter

pytestmark = pytest.mark.usefixtures("isolation", "require_netns")

def setup_client(monkeypatch, *, statuses=(200,), model=j.PINNED_MODEL):
    real = j.JevClient
    replies = iter(statuses)
    def transport(body, timeout, progress):
        request = json.loads(body)
        criteria = request["questions"]["select"]["criteria"]
        answers = {"select": {"choice": "a", "confidence": .9, "probabilities": {k: .9 if k == "a" else .1 for k in criteria}}}
        for key in request["questions"]:
            if key != "select": answers[key] = {"noul": .9}
        progress("response_read")
        return j.RawReply(next(replies), {}, json.dumps({"model": model, "answers": answers, "usage": {"input_tokens": 4, "output_tokens": 2}}).encode())
    monkeypatch.setattr(selector.egress, "project_owner", lambda root: "mistakeknot")
    monkeypatch.setattr(j, "JevClient", lambda credential: real(credential, transport=transport, sleep=lambda delay: None))

@pytest.mark.parametrize("failure", [None, "breaker", "interpret", "build"])
def test_collector_survives(monkeypatch, tmp_path, capsys, failure):
    setup_client(monkeypatch)
    def fail(*args, **kwargs): raise OSError("dummy-private-message")
    if failure == "breaker": monkeypatch.setattr(j.Breaker, "record", fail)
    if failure == "interpret": monkeypatch.setattr(j, "apply_floors", fail)
    if failure == "build": monkeypatch.setattr(selector.records, "build_record", fail)
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    record = result.record_dict
    if failure == "build": record = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    block = record["selector"]
    assert block["attempts"] == len(block["attempt_records"]) == block["jev_usage_accounting"]["attempts"] == 1
    assert block["attempt_records"][0]["usage_basis"] == "reported"
    assert block["jev_usage_accounting"]["complete"] is True
    if failure: assert result.fallback_reason.value == "internal_error"
    else:
        assert burn.accounting_from_record(record) == burn.accounting_from_record(block)
        assert burn.accounting_from_record(record)["complete"] is True

def test_429_breaker_failure(monkeypatch, tmp_path):
    setup_client(monkeypatch, statuses=(429, 200))
    monkeypatch.setattr(j.Breaker, "record", lambda *a: (_ for _ in ()).throw(OSError("dummy")))
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    block = result.record_dict["selector"]
    assert block["attempts"] == 2
    assert block["jev_usage_accounting"]["complete"] is False

def test_interrupted_selector_writes(monkeypatch, tmp_path, capsys):
    setup_client(monkeypatch)
    monkeypatch.setattr(j, "_join", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): _select(_operator(tmp_path), _registry(), FakeAdapter())
    record = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert record["selector"]["attempts"] == 1
    assert record["selector"]["jev_usage_accounting"]["complete"] is False

def test_deadline_zero_breaker_failure(monkeypatch,tmp_path):
    setup_client(monkeypatch)
    monkeypatch.setattr(j.Breaker,"record",lambda *a: (_ for _ in ()).throw(OSError("dummy")))
    class Expired:
        def remaining_ms(self): return 0
    result=_select(_operator(tmp_path),_registry(),FakeAdapter(),deadline=Expired())
    assert result.fallback_reason.value == "internal_error"
    assert result.record_dict["selector"]["attempts"] == 0
    assert result.record_dict["selector"]["jev_usage_accounting"]["complete"] is True

def test_selector_model_echo_hash(monkeypatch,tmp_path):
    import hashlib
    model="dummy-provider-private-echo"
    setup_client(monkeypatch,model=model)
    result=_select(_operator(tmp_path),_registry(),FakeAdapter())
    assert result.fallback_reason.value == "model_mismatch"
    assert model not in json.dumps(result.record_dict)
    assert result.record_dict["selector"]["model_returned_matches"] is False
    assert result.record_dict["selector"]["model_returned_sha256"] == hashlib.sha256(model.encode()).hexdigest()
