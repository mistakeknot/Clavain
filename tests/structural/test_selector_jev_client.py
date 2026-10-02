"""Tests for scripts/clavain_selector/jev_client.py (mk-42j9.7 Task 5).

Every secret-like literal used below is assembled at runtime (never written
as a single literal), per the convention in test_selector_egress.py. The
fake Jev server is a real ``http.server`` instance on loopback, run in a
thread; each test scripts its own sequence of responses.
"""

from __future__ import annotations

import copy
import hashlib
import http.server
import json
import socket
import threading
import time
from dataclasses import replace

import dataclasses
import pytest
from selector_helpers import make_candidate, make_request, selector_socket_guard  # noqa: F401

from clavain_selector import contract, credentials, egress, jev_client, questions
from clavain_selector.contract import FallbackReason, Point, SessionRef
from clavain_selector.jev_client import (
    CLIENT_FAILURE_REASONS,
    ClientConfigError,
    Deadline,
    FailureDetail,
    JevCall,
    JevClient,
    JevFailure,
    JevOk,
    JevResponse,
    ChoiceAnswer,
    NoulAnswer,
    Usage,
    NotAdmitted,
    BatteryMismatch,
    Floors,
    Selection,
    Abstention,
    apply_floors,
    Breaker,
    Budget,
    PINNED_MODEL,
)


def _key(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


TEST_KEY = _key("jev-client-test-key")


def _admit(request):
    admitted = egress.admit(request)
    assert isinstance(admitted, egress.AdmittedRequest), f"unexpected refusal: {admitted!r}"
    return admitted


def _views(request):
    return [c.selector_view() for c in request.candidates]


def _battery(request, *, fit_questions=True):
    return questions.build_battery(_views(request), fit_questions=fit_questions)


def _call(request, *, budget_ms=2000, fit_questions=True):
    admitted = _admit(request)
    battery = _battery(request, fit_questions=fit_questions)
    deadline = Deadline.start(budget_ms)
    return JevCall(admitted=admitted, battery=battery, deadline=deadline)


def _default_answers(battery, *, choice=None, confidence=0.9, probabilities=None):
    candidate_ids = [cid for cid, _ in battery.select.criteria]
    if probabilities is None:
        n = len(candidate_ids)
        probabilities = {cid: (0.9 if i == 0 else 0.1 / max(1, n - 1)) for i, cid in enumerate(candidate_ids)}
    if choice is None:
        choice = candidate_ids[0]
    answers = {
        "select": {"choice": choice, "confidence": confidence, "probabilities": probabilities},
    }
    for fit in battery.fits:
        answers[fit.key] = {"noul": 0.8}
    return answers


def _response_json(battery, **kwargs):
    return {
        "model": kwargs.pop("model", PINNED_MODEL),
        "answers": kwargs.pop("answers", None) or _default_answers(battery, **{
            k: v for k, v in kwargs.items() if k in ("choice", "confidence", "probabilities")
        }),
        "usage": kwargs.pop("usage", {"input_tokens": 100, "output_tokens": 20}),
    }


class ScriptedHandler(http.server.BaseHTTPRequestHandler):
    """A fake Jev server: `server.script` is a list of response-callables, consumed in order."""

    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.captured_requests.append({
            "body": body,
            "headers": dict(self.headers.items()),
            "path": self.path,
        })
        if not self.server.script:
            self.send_response(500)
            self.end_headers()
            return
        step = self.server.script.pop(0)
        step(self, body)

    def log_message(self, fmt, *args):  # noqa: D401 - silence default stderr logging
        pass


class FakeServer:
    def __init__(self):
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ScriptedHandler)
        self.httpd.daemon_threads = True
        self.httpd.script = []
        self.httpd.captured_requests = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/"

    @property
    def script(self):
        return self.httpd.script

    @property
    def captured_requests(self):
        return self.httpd.captured_requests

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


@pytest.fixture
def fake_server():
    server = FakeServer()
    yield server
    server.close()


def _json_step(status: int, payload: dict, *, headers: dict | None = None):
    def step(handler: ScriptedHandler, body: bytes):
        data = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            handler.send_header(key, value)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    return step


def _raw_step(status: int, raw: bytes, *, headers: dict | None = None):
    def step(handler: ScriptedHandler, body: bytes):
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            handler.send_header(key, value)
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    return step


def _sleep_step(seconds: float, then: "callable"):
    def step(handler: ScriptedHandler, body: bytes):
        time.sleep(seconds)
        then(handler, body)

    return step


def _client(fake_server, credential_value=TEST_KEY) -> JevClient:
    return JevClient(credentials.SecretStr(credential_value), url=fake_server.url)


@pytest.fixture(autouse=True)
def _reset_inflight():
    jev_client._reset_inflight_for_tests()
    yield
    jev_client._reset_inflight_for_tests()


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def test_client_construction_rejects_arbitrary_https():
    secret = credentials.SecretStr(TEST_KEY)
    with pytest.raises(ClientConfigError):
        JevClient(secret, url="https://example.com")


def test_client_construction_accepts_typesafe_url():
    secret = credentials.SecretStr(TEST_KEY)
    client = JevClient(secret, url=jev_client.TYPESAFE_URL)
    assert client is not None


def test_client_construction_accepts_loopback(fake_server):
    client = _client(fake_server)
    assert client is not None


# ---------------------------------------------------------------------------
# test_request_body_shape
# ---------------------------------------------------------------------------


def test_request_body_shape(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request)
    battery = call.battery
    fake_server.script.append(_json_step(200, _response_json(battery)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)

    assert len(fake_server.captured_requests) == 1
    captured = fake_server.captured_requests[0]
    payload = json.loads(captured["body"].decode("utf-8"))
    assert payload["model"] == "jev-1.13.0"
    assert payload["state"]["schema"] == "clavain-selection-v1"
    assert payload["questions"]["select"]["type"] == "choice"
    criteria_keys = set(payload["questions"]["select"]["criteria"].keys())
    candidate_ids = {c.id for c in request.candidates}
    assert criteria_keys == candidate_ids | {"escalate"}
    for candidate_id in candidate_ids:
        fit_index = [cid for cid, _ in battery.select.criteria].index(candidate_id)
        assert f"fit_{fit_index}" in payload["questions"]

    auth = captured["headers"].get("Authorization")
    assert auth == f"Bearer {TEST_KEY}"


# ---------------------------------------------------------------------------
# test_only_admitted_requests
# ---------------------------------------------------------------------------


def test_only_admitted_requests(fake_server):
    client = _client(fake_server)

    with pytest.raises(NotAdmitted):
        client.call({"not": "a JevCall"})

    request = make_request()
    admitted = _admit(request)
    battery = _battery(request)
    tampered = egress.AdmittedRequest(body=admitted.body + b" ", sha256=admitted.sha256, tag=admitted.tag)
    with pytest.raises(NotAdmitted):
        JevCall(admitted=tampered, battery=battery, deadline=Deadline.start(1000))

    forged = egress.AdmittedRequest(body=admitted.body, sha256=admitted.sha256, tag=b"\x00" * len(admitted.tag))
    with pytest.raises(NotAdmitted):
        JevCall(admitted=forged, battery=battery, deadline=Deadline.start(1000))

    assert fake_server.captured_requests == []


# ---------------------------------------------------------------------------
# test_deadline
# ---------------------------------------------------------------------------


def test_deadline_socket_timeout_before_join_returns_is_timeout(fake_server, monkeypatch):
    """Regression (sylveste-ytpg): a loaded host can wake `join` after the worker's own
    socket read timeout fired; that must still classify as the deadline, not http_error."""
    request = make_request()
    call = _call(request, budget_ms=300)
    battery = call.battery
    fake_server.script.append(_sleep_step(3.0, _json_step(200, _response_json(battery)).__call__))

    real_join = threading.Thread.join

    def late_join(self, timeout=None):
        if timeout is not None:
            time.sleep(timeout + 0.2)  # scheduler delay: worker's read timeout fires first
        return real_join(self, timeout)

    monkeypatch.setattr(threading.Thread, "join", late_join)
    result = _client(fake_server).call(call)

    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.TIMEOUT
    assert result.detail == FailureDetail.DEADLINE


def test_deadline(fake_server):
    request = make_request()
    call = _call(request, budget_ms=300)
    battery = call.battery
    fake_server.script.append(_sleep_step(3.0, _json_step(200, _response_json(battery)).__call__))

    client = _client(fake_server)
    started = time.monotonic()
    result = client.call(call)
    elapsed_ms = (time.monotonic() - started) * 1000

    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.TIMEOUT
    assert elapsed_ms < 450

    daemon_threads = [t for t in threading.enumerate() if t is not threading.main_thread() and t.name.startswith("Thread")]
    # At least one lingering worker thread (the abandoned attempt) must be a daemon.
    lingering = [t for t in threading.enumerate() if t.is_alive() and t.daemon and t is not threading.main_thread()]
    assert any(lingering)


# ---------------------------------------------------------------------------
# test_blocked_resolution_does_not_block_caller
# ---------------------------------------------------------------------------


def test_blocked_resolution_does_not_block_caller(fake_server, monkeypatch):
    request = make_request()
    call = _call(request, budget_ms=300)

    real_getaddrinfo = socket.getaddrinfo

    def _slow_getaddrinfo(*args, **kwargs):
        time.sleep(5.0)
        return real_getaddrinfo(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _slow_getaddrinfo)

    client = _client(fake_server)
    started = time.monotonic()
    result = client.call(call)
    elapsed_ms = (time.monotonic() - started) * 1000

    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.TIMEOUT
    assert elapsed_ms < 450


# ---------------------------------------------------------------------------
# test_inflight_cap
# ---------------------------------------------------------------------------


def test_inflight_cap(fake_server):
    request = make_request()

    call1 = _call(request, budget_ms=5000)
    call2 = _call(request, budget_ms=5000)
    call3 = _call(request, budget_ms=300)

    battery = call1.battery
    ok_response = _response_json(battery)
    fake_server.script.append(_sleep_step(10.0, _json_step(200, ok_response).__call__))
    fake_server.script.append(_sleep_step(10.0, _json_step(200, ok_response).__call__))

    client = _client(fake_server)
    results = {}
    threads = []
    for name, call in (("a", call1), ("b", call2)):
        t = threading.Thread(target=lambda n=name, c=call: results.__setitem__(n, client.call(c)))
        t.start()
        threads.append(t)

    # Give both abandoned calls time to occupy the in-flight slots.
    deadline = time.monotonic() + 2.0
    while jev_client._inflight_count < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert jev_client._inflight_count == 2

    result3 = client.call(call3)
    assert isinstance(result3, JevFailure)
    assert result3.reason == FallbackReason.TIMEOUT
    assert result3.detail == FailureDetail.INFLIGHT_CAP
    assert result3.attempts == 0

    for t in threads:
        t.join(timeout=15)


# ---------------------------------------------------------------------------
# test_retry_policy
# ---------------------------------------------------------------------------


def test_retry_policy_503_then_200(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    fake_server.script.append(_json_step(503, {"error": "unavailable"}))
    fake_server.script.append(_json_step(200, _response_json(battery)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    assert result.attempts == 2


def test_retry_policy_503_insufficient_remaining_no_retry(fake_server):
    request = make_request()
    call = _call(request, budget_ms=500)
    fake_server.script.append(_json_step(503, {"error": "unavailable"}))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.attempts == 1


@pytest.mark.parametrize("status", [400, 401])
def test_retry_policy_no_retry_on_client_errors(fake_server, status):
    request = make_request()
    call = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(status, {"error": "bad"}))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.attempts == 1


def test_retry_policy_no_retry_on_timeout(fake_server):
    request = make_request()
    call = _call(request, budget_ms=300)
    battery = call.battery
    fake_server.script.append(_sleep_step(3.0, _json_step(200, _response_json(battery)).__call__))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.TIMEOUT
    assert result.attempts == 1


def test_retry_policy_429_twice_is_rate_limited(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(429, {"error": "slow down"}))
    fake_server.script.append(_json_step(429, {"error": "slow down"}))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.RATE_LIMITED
    assert result.attempts == 2


# ---------------------------------------------------------------------------
# test_status_mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_status_mapping_credential_rejected(fake_server, status):
    request = make_request()
    call = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(status, {"error": "denied"}))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.CREDENTIAL_REJECTED


def test_status_mapping_http_error(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(500, {"error": "boom"}))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.HTTP_ERROR


# ---------------------------------------------------------------------------
# test_response_validation
# ---------------------------------------------------------------------------


def test_response_validation_oversize(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    raw = b"x" * (jev_client.MAX_RESPONSE_BYTES + 10)
    fake_server.script.append(_raw_step(200, raw))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.OVERSIZE


def test_response_validation_bad_json(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    fake_server.script.append(_raw_step(200, b"{not json"))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.BAD_JSON


def test_response_validation_model_mismatch(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    fake_server.script.append(_json_step(200, _response_json(battery, model="jev-1.14.0")))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.MODEL_MISMATCH
    assert result.model_returned == "jev-1.14.0"


def test_response_validation_missing_probability_key(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request, budget_ms=5000)
    battery = call.battery
    answers = _default_answers(battery)
    del answers["select"]["probabilities"]["escalate"]
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.PROBABILITY_KEYS


def test_response_validation_probability_sum_wrong(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    candidate_ids = [cid for cid, _ in battery.select.criteria]
    probabilities = {cid: 0.0 for cid in candidate_ids}
    probabilities[candidate_ids[0]] = 0.5
    answers = _default_answers(battery, probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.PROBABILITY_SUM


def test_response_validation_chosen_not_max(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request, budget_ms=5000)
    battery = call.battery
    candidate_ids = [cid for cid, _ in battery.select.criteria]
    probabilities = {cid: 0.1 / max(1, len(candidate_ids) - 1) for cid in candidate_ids}
    probabilities[candidate_ids[0]] = 0.9
    answers = _default_answers(battery, choice=candidate_ids[1], probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.CHOSEN_NOT_MAX


def test_response_validation_invalid_fit(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    answers = _default_answers(battery)
    answers["fit_0"]["noul"] = 1.2
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.INVALID_FIT


def test_response_validation_escalate_chosen_is_jev_escalated(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request, budget_ms=5000)
    battery = call.battery
    candidate_ids = [cid for cid, _ in battery.select.criteria]
    probabilities = {cid: 0.0 for cid in candidate_ids}
    probabilities["escalate"] = 1.0
    answers = _default_answers(battery, choice="escalate", probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.5)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Abstention)
    assert outcome.reason == FallbackReason.JEV_ESCALATED


def test_response_validation_low_confidence(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    answers = _default_answers(battery, confidence=0.5)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.5)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Abstention)
    assert outcome.reason == FallbackReason.LOW_CONFIDENCE


def test_response_validation_low_fit(fake_server):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    answers = _default_answers(battery, confidence=0.9)
    answers["fit_0"]["noul"] = 0.7
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.75)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Abstention)
    assert outcome.reason == FallbackReason.LOW_FIT


# ---------------------------------------------------------------------------
# test_key_never_leaks
# ---------------------------------------------------------------------------


def test_key_never_leaks(fake_server, capsys):
    request = make_request()
    call = _call(request, budget_ms=5000)
    battery = call.battery
    fake_server.script.append(_json_step(401, {"error": "denied"}))
    fake_server.script.append(_json_step(500, {"error": "boom"}))
    fake_server.script.append(_json_step(200, _response_json(battery)))

    client = _client(fake_server)
    outcomes = [client.call(call2) for call2 in (
        _call(request, budget_ms=5000),
        _call(request, budget_ms=5000),
        _call(request, budget_ms=5000),
    )]

    for outcome in outcomes:
        text = repr(outcome)
        assert TEST_KEY not in text

    captured_out = capsys.readouterr()
    assert TEST_KEY not in captured_out.out
    assert TEST_KEY not in captured_out.err

    for req in fake_server.captured_requests:
        # The key legitimately appears in the Authorization header sent to
        # the server; it must never appear anywhere else (e.g. the body).
        assert TEST_KEY not in req["body"].decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# test_breaker
# ---------------------------------------------------------------------------


def test_breaker(fake_server, tmp_path, monkeypatch):
    fake_time = {"now": 1_000_000.0}
    monkeypatch.setattr(jev_client.time, "time", lambda: fake_time["now"])

    breaker = Breaker(path=tmp_path / "breaker.json", now_fn=lambda: fake_time["now"])
    request = make_request()
    client = _client(fake_server)

    for _ in range(3):
        assert breaker.check() is None
        call = _call(request, budget_ms=300)
        fake_server.script.append(_sleep_step(3.0, _json_step(200, _response_json(call.battery)).__call__))
        result = client.call(call)
        assert isinstance(result, JevFailure)
        breaker.record(result)

    assert len(fake_server.captured_requests) == 3

    reason = breaker.check()
    assert reason == FallbackReason.CIRCUIT_OPEN
    assert len(fake_server.captured_requests) == 3  # zero additional server hits

    fake_time["now"] += jev_client.BREAKER_OPEN_SECONDS + 1
    assert breaker.check() is None  # one half-open probe allowed
    call = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(200, _response_json(call.battery)))
    result = client.call(call)
    assert isinstance(result, JevOk)
    breaker.record(result)

    assert breaker.check() is None


# ---------------------------------------------------------------------------
# test_budget
# ---------------------------------------------------------------------------


def test_budget(tmp_path):
    budget = Budget("sess-budget-test", "selftest", state_dir=tmp_path)
    for _ in range(8):
        assert budget.consume() is None
    ninth = budget.consume()
    assert ninth == FallbackReason.BUDGET_EXHAUSTED


# ---------------------------------------------------------------------------
# Revision 6 (G1): test_typed_results, test_typed_errors
# ---------------------------------------------------------------------------


def test_typed_results(fake_server):
    request = make_request()
    battery = _battery(request)

    cases = []

    call_ok = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(200, _response_json(battery)))
    cases.append(client_call_pair(fake_server, call_ok))

    call_timeout = _call(request, budget_ms=300)
    fake_server.script.append(_sleep_step(3.0, _json_step(200, _response_json(battery)).__call__))
    cases.append(client_call_pair(fake_server, call_timeout))

    call_credrej = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(401, {"error": "denied"}))
    cases.append(client_call_pair(fake_server, call_credrej))

    call_httperr = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(500, {"error": "boom"}))
    cases.append(client_call_pair(fake_server, call_httperr))

    call_invalid = _call(request, budget_ms=5000)
    fake_server.script.append(_raw_step(200, b"not json"))
    cases.append(client_call_pair(fake_server, call_invalid))

    call_modelmis = _call(request, budget_ms=5000)
    fake_server.script.append(_json_step(200, _response_json(battery, model="jev-9.9.9")))
    cases.append(client_call_pair(fake_server, call_modelmis))

    for result in cases:
        assert isinstance(result, (JevOk, JevFailure))
        if isinstance(result, JevFailure):
            assert result.reason in CLIENT_FAILURE_REASONS

    with pytest.raises(ValueError):
        JevFailure(
            reason=FallbackReason.TIMEOUT,
            detail=FailureDetail.STATUS,  # wrong pairing
            attempts=1,
            http_status=None,
            latency_ms=1,
        )


def client_call_pair(fake_server, call):
    client = _client(fake_server)
    return client.call(call)


def test_typed_errors(fake_server):
    with pytest.raises(ClientConfigError):
        JevClient(credentials.SecretStr(TEST_KEY), url="https://example.com")

    client = _client(fake_server)
    with pytest.raises(NotAdmitted):
        client.call("not a call")

    request = make_request()
    admitted = _admit(request)
    battery = _battery(request)
    other_request = make_request(candidates=(make_candidate(id="zeta"),))
    other_admitted = _admit(other_request)
    other_battery = _battery(other_request)

    call = JevCall(admitted=admitted, battery=battery, deadline=Deadline.start(1000))
    with pytest.raises(BatteryMismatch):
        dataclasses.replace(call, battery=other_battery)
        # dataclasses.replace on a frozen dataclass re-runs __post_init__,
        # so the mismatch is raised at replace() time.

    assert fake_server.captured_requests == []


# ---------------------------------------------------------------------------
# test_response_types
# ---------------------------------------------------------------------------


def test_response_types(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request, budget_ms=5000, fit_questions=True)
    battery = call.battery
    fake_server.script.append(_json_step(200, _response_json(battery)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    response = result.response
    assert isinstance(response, JevResponse)
    assert isinstance(response.select, ChoiceAnswer)
    expected_order = [cid for cid, _ in battery.select.criteria]
    assert [cid for cid, _ in response.select.probabilities] == expected_order
    assert expected_order[-1] == "escalate"
    assert [f.candidate_id for f in response.fits] == [cid for cid, _ in battery.select.criteria[:-1]]
    assert isinstance(response.usage, Usage)
    assert isinstance(response.usage.input_tokens, int)
    assert isinstance(response.usage.output_tokens, int)


def test_response_types_no_fit_questions(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request, budget_ms=5000, fit_questions=False)
    battery = call.battery
    assert "fit_0" not in battery.to_wire()
    fake_server.script.append(_json_step(200, _response_json(battery)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    assert result.response.fits == ()

    payload = json.loads(fake_server.captured_requests[0]["body"].decode("utf-8"))
    assert not any(k.startswith("fit_") for k in payload["questions"].keys())


# ---------------------------------------------------------------------------
# test_wire_body_canonical (G3)
# ---------------------------------------------------------------------------


def test_wire_body_canonical(fake_server):
    ids = ["gamma", "alpha", "beta"]
    permutations = [
        ids,
        list(reversed(ids)),
        [ids[1], ids[2], ids[0]],
        [ids[2], ids[0], ids[1]],
        [ids[0], ids[2], ids[1]],
    ]

    bodies = []
    for order in permutations:
        candidates = tuple(make_candidate(id=cid) for cid in order)
        request = make_request(candidates=candidates)
        call = _call(request, budget_ms=5000)
        bodies.append(call.wire_body())

    assert len(set(bodies)) == 1

    parsed = json.loads(bodies[0].decode("utf-8"))
    assert list(parsed.keys()) == ["model", "state", "questions"]
    assert list(parsed["state"].keys()) == ["schema", "point", "task", "context", "candidates"]
    assert list(parsed["questions"].keys())[0] == "select"
    criteria_ids = list(parsed["questions"]["select"]["criteria"].keys())
    assert criteria_ids[-1] == "escalate"

    request = make_request(candidates=tuple(make_candidate(id=cid) for cid in ids))
    call = _call(request, budget_ms=5000)
    assert json.loads(call.wire_body())["questions"] == call.battery.to_wire()


# ---------------------------------------------------------------------------
# test_tie_break (G3; revision 7 wording)
# ---------------------------------------------------------------------------


def test_tie_break(fake_server):
    candidates = (make_candidate(id="xxx"), make_candidate(id="yyy"))
    request = make_request(candidates=candidates)
    call = _call(request, budget_ms=5000, fit_questions=False)
    battery = call.battery
    canonical_ids = [c.id for c in request.candidates]
    x, y = canonical_ids[0], canonical_ids[1]
    later = y

    probabilities = {x: 0.5, y: 0.5, "escalate": 0.0}
    answers = _default_answers(battery, choice=later, confidence=0.9, probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.5)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Selection)
    assert outcome.candidate_id == canonical_ids[0]
    assert outcome.jev_choice == later
    assert outcome.tie_size == 2


def test_tie_break_gap_not_a_tie(fake_server):
    candidates = (make_candidate(id="xxx"), make_candidate(id="yyy"))
    request = make_request(candidates=candidates)
    call = _call(request, budget_ms=5000, fit_questions=False)
    battery = call.battery
    canonical_ids = [c.id for c in request.candidates]
    x, y = canonical_ids[0], canonical_ids[1]

    probabilities = {x: 0.5, y: 0.5 - 2e-9, "escalate": 2e-9}
    answers = _default_answers(battery, choice=x, confidence=0.9, probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.5)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Selection)
    assert outcome.tie_size == 1


def test_tie_break_with_escalate_is_abstention(fake_server):
    candidates = (make_candidate(id="xxx"), make_candidate(id="yyy"))
    request = make_request(candidates=candidates)
    call = _call(request, budget_ms=5000, fit_questions=False)
    battery = call.battery
    canonical_ids = [c.id for c in request.candidates]
    x = canonical_ids[0]

    probabilities = {x: 0.5, canonical_ids[1]: 0.0, "escalate": 0.5}
    answers = _default_answers(battery, choice=x, confidence=0.9, probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.5)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Abstention)
    assert outcome.reason == FallbackReason.JEV_ESCALATED


def test_tie_break_permutation_invariant(fake_server):
    candidates_a = (make_candidate(id="xxx"), make_candidate(id="yyy"))
    candidates_b = (make_candidate(id="yyy"), make_candidate(id="xxx"))

    outcomes = []
    for candidates in (candidates_a, candidates_b):
        request = make_request(candidates=candidates)
        call = _call(request, budget_ms=5000, fit_questions=False)
        battery = call.battery
        canonical_ids = [c.id for c in request.candidates]
        probabilities = {canonical_ids[0]: 0.5, canonical_ids[1]: 0.5, "escalate": 0.0}
        answers = _default_answers(battery, choice=canonical_ids[1], confidence=0.9, probabilities=probabilities)
        fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))
        client = _client(fake_server)
        result = client.call(call)
        assert isinstance(result, JevOk)
        floors = Floors(confidence=0.6, fit=0.5)
        outcomes.append(apply_floors(result.response, floors, battery))

    assert outcomes[0].candidate_id == outcomes[1].candidate_id


# ---------------------------------------------------------------------------
# test_confidence_not_compared (revision 7, P2-5)
# ---------------------------------------------------------------------------


def test_confidence_not_compared(fake_server):
    request = make_request(candidates=(make_candidate(id="alpha"), make_candidate(id="beta")))
    call = _call(request, budget_ms=5000, fit_questions=False)
    battery = call.battery
    candidate_ids = [cid for cid, _ in battery.select.criteria]
    winner = candidate_ids[0]
    probabilities = {winner: 0.64, candidate_ids[1]: 0.36, "escalate": 0.0}
    answers = _default_answers(battery, choice=winner, confidence=0.71, probabilities=probabilities)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevOk)
    floors = Floors(confidence=0.6, fit=0.5)
    outcome = apply_floors(result.response, floors, battery)
    assert isinstance(outcome, Selection)
    assert outcome.confidence == 0.71
    assert outcome.selected_probability == 0.64


@pytest.mark.parametrize("bad_confidence", [1.2, -0.1, float("nan")])
def test_confidence_out_of_range_is_invalid_response(fake_server, bad_confidence):
    request = make_request()
    call = _call(request, budget_ms=5000, fit_questions=False)
    battery = call.battery
    answers = _default_answers(battery, confidence=bad_confidence)
    fake_server.script.append(_json_step(200, _response_json(battery, answers=answers)))

    client = _client(fake_server)
    result = client.call(call)
    assert isinstance(result, JevFailure)
    assert result.reason == FallbackReason.INVALID_RESPONSE
    assert result.detail == FailureDetail.SCHEMA


# ---------------------------------------------------------------------------
# test_deadline_type
# ---------------------------------------------------------------------------


def test_deadline_type():
    deadline = Deadline.start(9000)
    assert deadline.budget_ms == jev_client.MAX_DEADLINE_MS
    assert deadline.remaining_ms() >= 0

    small = Deadline.start(1)
    time.sleep(0.05)
    assert small.remaining_ms() >= 0
