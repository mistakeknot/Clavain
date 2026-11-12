"""Socket-free physical-attempt accounting acceptance tests."""
import json
from pathlib import Path
import threading
import time
from dataclasses import replace
import pytest
from clavain_selector import jev_client as j
from support_helpers import isolation, require_netns, request_packet  # noqa: F401

pytestmark = pytest.mark.usefixtures("isolation", "require_netns")

def test_pending_is_unknown():
    assert hasattr(j, "AttemptLog")
    log = j.AttemptLog()
    log.begin(1)
    fields = log.to_fields()
    assert fields["attempts"] == 1
    assert fields["attempt_records"][0]["usage_basis"] == "unknown_interrupted"
    assert fields["jev_usage_accounting"]["complete"] is False

@pytest.mark.parametrize("counter", [True, -1, 1.0, 2**40 + 1, None])
def test_strict_usage(counter):
    assert hasattr(j, "valid_usage")
    assert not j.valid_usage({"input_tokens": counter, "output_tokens": 1})

def test_max_counter():
    assert hasattr(j, "valid_usage")
    assert j.valid_usage({"input_tokens": 2**40, "output_tokens": 0})

@pytest.mark.parametrize("header", ["-1", "abc"])
def test_retry_header(header):
    assert j._retry_after_ms(header) is None

def test_retry_header_cap():
    assert j._retry_after_ms("1e300") == j.MAX_DEADLINE_MS

def call_fixture(packet, transport, **kwargs):
    from clavain_selector import egress, credentials, support
    call = support.SupportCall.build(egress.admit_support(packet), deadline=j.Deadline.start(5000))
    log = j.AttemptLog()
    client = j.JevClient(credentials.SecretStr("dummy-qualification-value"), transport=transport, sleep=lambda delay: None, **kwargs)
    return call, log, client

@pytest.mark.parametrize("header", ["inf", "nan"])
def test_nonfinite_retry_after_vetoes_retry(request_packet, header):
    sent = []
    def transport(body, timeout, progress):
        sent.append(1)
        progress("response_read")
        return j.RawReply(429, {"retry-after": header}, b"{}")
    call, log, client = call_fixture(request_packet, transport)
    client.call(call, log=log)
    assert j._retry_after_ms(header) == j.MAX_DEADLINE_MS
    assert len(sent) == log.to_fields()["attempts"] == 1

@pytest.mark.parametrize("phase", ["connect", "request_sent", "response_read"])
def test_exception_phase(request_packet, phase):
    count = []
    def transport(body, timeout, progress):
        count.append(1)
        progress(phase)
        raise OSError("dummy-private-message")
    call, log, client = call_fixture(request_packet, transport)
    client.call(call, log=log)
    fields = log.to_fields()
    assert fields["attempts"] == (2 if phase == "connect" else 1)
    assert fields["attempt_records"][0]["usage_basis"] == ("not_sent" if phase == "connect" else "unknown_unparseable")
    assert "dummy-private-message" not in json.dumps(fields)

def test_429_then_success(request_packet):
    from test_selector_support import answer
    replies = iter([j.RawReply(429, {}, b'{"usage":{"input_tokens":999,"output_tokens":999}}'), j.RawReply(200, {}, json.dumps(answer()).encode())])
    def transport(body, timeout, progress):
        progress("response_read")
        return next(replies)
    call, log, client = call_fixture(request_packet, transport)
    client.call(call, log=log)
    f = log.to_fields()
    assert f["attempts"] == 2
    assert [a["usage_basis"] for a in f["attempt_records"]] == ["unknown_non200", "reported"]
    assert f["jev_usage_accounting"]["complete"] is False
    assert f["jev_usage_accounting"]["known_total"] == {"input_tokens": 2, "output_tokens": 1}
    golden=Path(__file__).resolve().parents[1]/"fixtures/selector/support-retry-accounting.json"
    assert f["jev_usage_accounting"] == json.loads(golden.read_text())

@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_start_after_launch_is_unknown(monkeypatch, request_packet, failure):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    exits = []
    real_exit = j._inflight_exit
    def exit_spy():
        exits.append(threading.current_thread())
        real_exit()
        finished.set()
    monkeypatch.setattr(j, "_inflight_exit", exit_spy)
    class Thread(threading.Thread):
        def start(self):
            super().start()
            assert entered.wait(2)
            raise failure("dummy")
    def transport(body, timeout, progress):
        progress("request_sent")
        entered.set()
        release.wait(3)
        raise OSError("dummy")
    call, log, client = call_fixture(request_packet, transport)
    before = j._inflight_count
    monkeypatch.setattr(j.threading, "Thread", Thread)
    try:
        with pytest.raises(failure): client.call(call, log=log)
        assert exits == []
        f = log.to_fields()
        assert f["attempt_records"][0]["usage_basis"] == "unknown_interrupted"
        assert f["jev_usage_accounting"]["complete"] is False
    finally:
        release.set()
        assert finished.wait(2)
    assert j._inflight_count == before
    assert len(exits) == 1 and exits[0] is not threading.current_thread()
    assert log.to_fields() == f

def test_launch_failure_leaks_conservatively(monkeypatch, request_packet):
    call, log, client = call_fixture(request_packet, lambda *a: pytest.fail("not launched"))
    before = j._inflight_count
    monkeypatch.setattr(j.threading, "_start_new_thread", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dummy")))
    try:
        with pytest.raises(RuntimeError): client.call(call, log=log)
        f = log.to_fields()
        assert f["attempt_records"][0]["usage_basis"] == "unknown_interrupted"
        assert f["attempt_records"][0]["error_class"] is None
        assert f["jev_usage_accounting"]["complete"] is False
        assert j._inflight_count == before + 1
    finally:
        j._inflight_count = before

def test_pre_started_false_is_not_proof(monkeypatch, request_packet):
    os_entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    before = j._inflight_count
    real_start = threading._start_new_thread
    exits = []
    real_exit = j._inflight_exit
    def exit_spy():
        exits.append(threading.current_thread())
        real_exit()
        finished.set()
    monkeypatch.setattr(j, "_inflight_exit", exit_spy)
    class Thread(threading.Thread):
        def start(self):
            def raw_worker():
                os_entered.set()
                release.wait(3)
                self._target(*self._args, **self._kwargs)
            real_start(raw_worker, ())
            assert os_entered.wait(2)
            assert self.is_alive() is False
            raise RuntimeError("dummy startup exception")
    def transport(body, timeout, progress):
        progress("request_sent")
        raise OSError("dummy")
    call, log, client = call_fixture(request_packet, transport)
    monkeypatch.setattr(j.threading, "Thread", Thread)
    try:
        with pytest.raises(RuntimeError): client.call(call, log=log)
        f = log.to_fields()
        assert f["attempt_records"][0]["usage_basis"] == "unknown_interrupted"
        assert f["jev_usage_accounting"]["complete"] is False
        assert exits == []
    finally:
        release.set()
        assert finished.wait(2)
    assert j._inflight_count == before
    assert len(exits) == 1
    assert log.to_fields() == f

@pytest.mark.parametrize("status", [429,500,301,201])
def test_non200_body_unparsed(monkeypatch, request_packet, status):
    from clavain_selector import accounting
    monkeypatch.setattr(accounting, "response_usage", lambda *args: pytest.fail("non200 body parsed"))
    def transport(body, timeout, progress):
        progress("response_read")
        return j.RawReply(status, {}, b'{"usage":{"input_tokens":10,"output_tokens":1}}')
    call, log, client = call_fixture(request_packet, transport)
    client.call(call, log=log)
    assert all(a["usage_basis"] == "unknown_non200" for a in log.to_fields()["attempt_records"])

def test_interruption_during_retry(monkeypatch, request_packet):
    second_entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    real_exit = j._inflight_exit
    monkeypatch.setattr(j, "_inflight_exit", lambda: (real_exit(), finished.set() if len(calls) == 2 else None))
    def transport(body, timeout, progress):
        calls.append(1)
        progress("request_sent")
        if len(calls) == 1: return j.RawReply(429, {}, b'')
        second_entered.set()
        release.wait(3)
        return j.RawReply(200, {}, b'{}')
    joins = []
    def join(thread, timeout):
        joins.append(1)
        if len(joins) == 1: thread.join(timeout)
        else:
            assert second_entered.wait(2)
            raise KeyboardInterrupt()
    call, log, client = call_fixture(request_packet, transport)
    monkeypatch.setattr(j, "_join", join)
    try:
        with pytest.raises(KeyboardInterrupt): client.call(call, log=log)
        f = log.to_fields()
        assert [a["usage_basis"] for a in f["attempt_records"]] == ["unknown_non200", "unknown_interrupted"]
        assert f["jev_usage_accounting"]["unknown_attempts"] == 2
    finally:
        release.set()
        assert finished.wait(2)
    assert log.to_fields() == f

def test_abandoned_and_late_result(monkeypatch, request_packet):
    entered,release,finished = threading.Event(),threading.Event(),threading.Event()
    real_exit = j._inflight_exit
    monkeypatch.setattr(j,"_inflight_exit",lambda: (real_exit(),finished.set()))
    def transport(body,timeout,progress):
        progress("request_sent")
        entered.set()
        release.wait(3)
        return j.RawReply(200,{},b'{}')
    call,log,client = call_fixture(request_packet,transport)
    monkeypatch.setattr(j,"_join",lambda *args: entered.wait(2))
    try:
        result = client.call(call,log=log)
        f = log.to_fields()
        assert result.reason.value == "timeout"
        assert f["attempt_records"][0]["usage_basis"] == "unknown_abandoned"
        assert f["attempt_records"][0]["abandoned_at"]
    finally:
        release.set()
        assert finished.wait(2)
    assert log.to_fields() == f

def test_inflight_on_retry_keeps_first(monkeypatch,request_packet):
    enters = []
    real_enter = j._inflight_enter
    def enter():
        enters.append(1)
        return real_enter() if len(enters)==1 else False
    monkeypatch.setattr(j,"_inflight_enter",enter)
    def transport(body,timeout,progress):
        progress("response_read")
        return j.RawReply(429,{},b'')
    call,log,client = call_fixture(request_packet,transport)
    result=client.call(call,log=log)
    assert result.attempts == log.to_fields()["attempts"] == 1

def test_sleep_and_retry_after_veto(request_packet):
    sleeps=[]
    def transport(body,timeout,progress):
        progress("response_read")
        return j.RawReply(429,{},b'')
    call,log,client=call_fixture(request_packet,transport)
    client._sleep = sleeps.append
    client.call(call,log=log)
    assert sleeps == [.1]
    def veto(body,timeout,progress):
        progress("response_read")
        return j.RawReply(429,{"retry-after":"1e300"},b'')
    call,log,client=call_fixture(request_packet,veto)
    call=replace(call,deadline=j.Deadline(time.monotonic_ns()-100_000_000,5000))
    client._sleep=sleeps.append
    client.call(call,log=log)
    assert log.to_fields()["attempts"] == 1
