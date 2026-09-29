"""Task 7 selector orchestration tests.

Real tests exercising the selection flow's fallback table and error handling.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import time
from pathlib import Path
from types import SimpleNamespace
from types import MappingProxyType

import pytest
from selector_helpers import make_candidate, selector_socket_guard  # noqa: F401

import clavain_selector.selector as selector
from clavain_selector import contract, credentials, egress, jev_client, preparers, records
from clavain_selector.adapters import base
from clavain_selector.adapters.base import Capability, HostEvent, Outcome
from clavain_selector.contract import FallbackReason, Point, Provenance, SessionRef


NOW_MS = 1727434800000
SESSION = SessionRef(host_session_id="selector-task7-session")


def _registry(*, active=False, points=("library",)):
    entry = {
        "flag": "CLAVAIN_SELECTOR_SELFTEST",
        "points": list(points),
        "active_allowed": active,
        "floors": {"confidence": 0.6, "fit": 0.5},
        "deadline_ms": {point: 3000 for point in points},
        "authorize": {"allow_ids": ["a", "b"]},
        "owner_bead": "mk-42j9.7",
    }
    return {"schema_version": 1, "integrations": {"selftest": entry}}


def _capability(*, status="reachable", evidence="first_hand"):
    return Capability(
        status=status,
        mechanism="test",
        limits="",
        evidence_level=evidence,
        verified_on="test",
        verified_at="2026-09-27",
    )


class FakeAdapter:
    name = "test-host"
    version = "test"

    def __init__(self):
        self.authorized = True
        self.capability = _capability()
        self.authorize_calls = []

    def capabilities(self):
        return {point: self.capability for point in Point}

    def fingerprint(self, paths, *, phase=None):
        return base.fingerprint_paths(paths, phase=phase)

    def authorize(self, chosen, validated, policy):
        self.authorize_calls.append((chosen, validated, policy))
        return self.authorized and base.authorize_by_policy(chosen, validated, policy)

    def render(self, point, outcome, event):
        return b""

    def parse_event(self, point, raw):
        data = json.loads(raw)
        return HostEvent(point=point, session_id=str(data.get("session_id", "")), raw=data)


class _BudgetOK:
    def __init__(self, *args, **kwargs):
        pass

    def consume(self):
        return None


class _BreakerOK:
    def __init__(self, *args, **kwargs):
        pass

    def check(self):
        return None

    def record(self, result):
        pass


class _ClientOK:
    def __init__(self, credential):
        pass

    def call(self, call):
        cids = tuple(cid for cid, _ in call.battery.select.criteria if cid != "escalate")
        chosen = cids[0] if cids else "a"
        probs = tuple((cid, 0.9 if cid == chosen else 0.1) for cid in cids) if cids else (("a", 0.9),)
        response = jev_client.JevResponse(
            model=jev_client.PINNED_MODEL,
            select=jev_client.ChoiceAnswer(choice=chosen, confidence=0.9, probabilities=probs),
            fits=tuple(
                jev_client.NoulAnswer(key=fit.key, candidate_id=fit.candidate_id, noul=0.9)
                for fit in call.battery.fits
            ),
            usage=jev_client.Usage(input_tokens=10, output_tokens=2),
        )
        return jev_client.JevOk(response=response, attempts=1, http_status=200, latency_ms=4)


@pytest.fixture(autouse=True)
def _setup_deps(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAVAIN_SELECTOR_RECORD_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(selector.egress, "project_owner", lambda root: "mistakeknot")
    monkeypatch.setattr(selector.credentials, "load", lambda: credentials.SecretStr("test"))
    monkeypatch.setattr(selector.jev_client, "Budget", _BudgetOK)
    monkeypatch.setattr(selector.jev_client, "Breaker", _BreakerOK)
    monkeypatch.setattr(selector.jev_client, "JevClient", _ClientOK)


def _operator(tmp_path, *, candidate=None, point=Point.LIBRARY):
    candidate = candidate or make_candidate(id="a", payload={})
    return preparers.from_operator(
        {}, "selftest", point, "choose", "context", (candidate,), tmp_path,
        task_revision="rev-1", read_set_paths=(),
    )


def _active_prepared(monkeypatch, tmp_path, *, payload=None, point=Point.LIBRARY, **candidate_fields):
    definition = preparers.Preparer(
        name="test",
        points=frozenset({point}),
        vocabulary=lambda root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, root: preparers.PreparedInput(
            task="t",
            context="c",
            candidates=(
                make_candidate(id="a", payload={} if payload is None else payload, **candidate_fields),
            ),
            task_revision="rev-1",
        ),
    )
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"test": definition}))
    reg = _registry(active=True, points=(point.value,))
    reg["integrations"]["selftest"]["preparer"] = "test"
    return reg, preparers.prepare(reg, "selftest", point, None, tmp_path)


def _select(prepared, registry, adapter, *, env=None, event=None, mode_override=None, deadline=None):
    # env=None means "caller didn't specify" -> default to shadow-enabled;
    # env={} is a deliberate, distinct choice (flag off) and must not be
    # coerced into the default (an empty dict is falsy, so `env or {...}`
    # would silently discard it -- use an explicit None check instead).
    if env is None:
        env = {"CLAVAIN_SELECTOR_SELFTEST": "shadow"}
    return selector.select(
        prepared,
        session=SESSION,
        adapter=adapter,
        env=env,
        now=NOW_MS,
        registry=registry,
        event=event,
        mode_override=mode_override,
        deadline=deadline,
    )


def test_flag_off_is_inert(monkeypatch, tmp_path):
    """Flag off produces no record."""
    prepared = _operator(tmp_path)
    monkeypatch.setattr(selector.records, "append_record", lambda *a, **k: pytest.fail("flag wrote"))

    result = _select(prepared, _registry(), FakeAdapter(), env={})

    assert result.fallback_reason == FallbackReason.FLAG_OFF
    assert result.record_dict is None


def test_point_mismatch_a1_rejected(tmp_path):
    """A1: event.point != prepared.point is rejected."""
    prepared = _operator(tmp_path, point=Point.LIBRARY)
    event = HostEvent(point=Point.PRE_TOOL, session_id="s")

    result = _select(prepared, _registry(), FakeAdapter(), event=event)

    assert result.fallback_reason == FallbackReason.INTERNAL_ERROR


def test_point_not_in_registry_points_a3_rejected(tmp_path):
    """A3: point not in registry points is rejected."""
    prepared = _operator(tmp_path, point=Point.PRE_TOOL)
    result = _select(prepared, _registry(points=("library",)), FakeAdapter())
    assert result.fallback_reason == FallbackReason.POINT_UNREACHABLE


def test_point_unreachable_via_adapter_matrix(tmp_path):
    """Row 3: adapter matrix says unreachable."""
    adapter = FakeAdapter()
    adapter.capability = _capability(status="unverified")
    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(), adapter)
    assert result.fallback_reason == FallbackReason.POINT_UNREACHABLE


def test_egress_refused_blocks_before_jev(monkeypatch, tmp_path):
    """Row 5: egress blocks before Jev."""
    monkeypatch.setattr(selector.egress, "admit", lambda *a, **k: egress.Refusal(("cred.test",)))
    monkeypatch.setattr(selector.jev_client, "JevClient", lambda *a, **k: pytest.fail("jev called"))

    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(), FakeAdapter())

    assert result.fallback_reason == FallbackReason.EGRESS_REFUSED


def test_external_scope_recheck_blocks_before_fingerprint(monkeypatch, tmp_path):
    """R12-2: egress recheck blocks before fingerprint for EXTERNAL."""
    path = tmp_path / "state.txt"
    path.write_text("content")
    cand = make_candidate(id="a", payload="x", expires_at_ms=2_000_000_000_000, read_set_fingerprint=base.fingerprint_paths((path,)))
    prepared = preparers.from_external(
        _registry(), "selftest", "choose", "context", (cand,), tmp_path,
        task_revision="rev-1", read_set_paths=(("a", (str(path),)),), sources=(),
    )

    calls = [0]
    real_rule = selector.egress._source_rule
    def deny_on_second(p, root):
        calls[0] += 1
        return "src.bad" if calls[0] >= 2 else real_rule(p, root)

    monkeypatch.setattr(selector.egress, "_source_rule", deny_on_second)
    result = _select(prepared, _registry(), FakeAdapter())

    assert result.fallback_reason == FallbackReason.EGRESS_REFUSED


def test_external_preconditions_unmet(tmp_path):
    """Row 4: EXTERNAL with preconditions fails."""
    cand = make_candidate(id="a", payload="x", preconditions=("x",), expires_at_ms=2_000_000_000_000)
    prepared = preparers.from_external(
        _registry(), "selftest", "choose", "context", (cand,), tmp_path,
        task_revision="rev-1", read_set_paths=(), sources=(),
    )
    result = _select(prepared, _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.STALE_BEFORE_SELECT


def test_external_mode_override_rejected(tmp_path):
    """EXTERNAL + mode_override="eval" is rejected even with the flag on."""
    cand = make_candidate(id="a", payload="x", expires_at_ms=2_000_000_000_000)
    prepared = preparers.from_external(
        _registry(), "selftest", "choose", "context", (cand,), tmp_path,
        task_revision="rev-1", read_set_paths=(), sources=(),
    )
    result = _select(prepared, _registry(), FakeAdapter(), mode_override="eval")
    assert result.fallback_reason == FallbackReason.INTERNAL_ERROR


def test_shadow_mode_records_but_native_outcome(tmp_path):
    """Shadow mode: record has mode='shadow' but outcome is native."""
    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(), FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "shadow"})

    assert result.record_dict["mode"] == "shadow"
    assert result.outcome.kind == "shadow"


def test_active_preparer_emits(monkeypatch, tmp_path):
    """Active mode + PREPARER: emits."""
    definition = preparers.Preparer(
        name="test",
        points=frozenset({Point.LIBRARY}),
        vocabulary=lambda root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, root: preparers.PreparedInput(
            task="t", context="c", candidates=(make_candidate(id="a", payload={}),), task_revision="rev-1",
        ),
    )
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"test": definition}))
    reg = _registry(active=True)
    reg["integrations"]["selftest"]["preparer"] = "test"
    prepared = preparers.prepare(reg, "selftest", Point.LIBRARY, None, tmp_path)

    result = _select(prepared, reg, FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "active"})

    assert result.record_dict["applied"] == "emitted"
    assert result.outcome.kind == "emitted"


def test_operator_active_downgrades_to_shadow(tmp_path):
    """OPERATOR + active: downgrades to shadow."""
    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(active=True), FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "active"})
    assert result.record_dict["mode"] == "shadow"


def test_external_emission_guard_r12_1(monkeypatch, tmp_path):
    """R12-1: emission guard blocks EXTERNAL independently."""
    cand = make_candidate(id="a", payload="x", expires_at_ms=2_000_000_000_000)
    prepared = preparers.from_external(
        _registry(), "selftest", "choose", "context", (cand,), tmp_path,
        task_revision="rev-1", read_set_paths=(), sources=(),
    )

    monkeypatch.setattr(selector, "_resolve_mode", lambda *a, **k: "active")
    monkeypatch.setattr(base, "emitted_outcome", lambda *a, **k: pytest.fail("emission reached"))
    adapter = FakeAdapter()
    adapter.render = lambda *a, **k: pytest.fail("render reached")

    result = _select(prepared, _registry(), adapter, env={"CLAVAIN_SELECTOR_SELFTEST": "active"})

    assert result.fallback_reason == FallbackReason.SHADOW_MODE, result.record_dict["fallback"]
    assert result.record_dict["applied"] == "native"
    assert result.outcome.kind == "native"


def test_jev_failure_timeout(monkeypatch, tmp_path):
    """Jev timeout is returned as fallback."""
    class FailedClient:
        def __init__(self, credential):
            pass
        def call(self, call):
            return jev_client.JevFailure(
                reason=FallbackReason.TIMEOUT,
                detail=jev_client.FailureDetail.DEADLINE,
                attempts=1,
                http_status=500,
                latency_ms=0,
            )

    monkeypatch.setattr(selector.jev_client, "JevClient", FailedClient)
    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(), FakeAdapter())

    assert result.fallback_reason == FallbackReason.TIMEOUT


def test_low_confidence_abstention(monkeypatch, tmp_path):
    """Low confidence causes abstention."""
    class LowConfClient(_ClientOK):
        def call(self, call):
            cids = tuple(cid for cid, _ in call.battery.select.criteria)
            return jev_client.JevOk(
                response=jev_client.JevResponse(
                    model=jev_client.PINNED_MODEL,
                    select=jev_client.ChoiceAnswer(choice=cids[0], confidence=0.1, probabilities=((cids[0], 0.1),)),
                    fits=(),
                    usage=jev_client.Usage(1, 1),
                ),
                attempts=1,
                http_status=200,
                latency_ms=1,
            )

    monkeypatch.setattr(selector.jev_client, "JevClient", LowConfClient)
    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(), FakeAdapter())

    assert result.fallback_reason == FallbackReason.LOW_CONFIDENCE


def test_unauthorized_blocks_emission(monkeypatch, tmp_path):
    """Authorization check blocks emission."""
    adapter = FakeAdapter()
    adapter.authorized = False
    monkeypatch.setattr(base, "authorize_by_policy", lambda *a, **k: False)

    definition = preparers.Preparer(
        name="test",
        points=frozenset({Point.LIBRARY}),
        vocabulary=lambda root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, root: preparers.PreparedInput(
            task="t", context="c", candidates=(make_candidate(id="a", payload={}),), task_revision="rev-1",
        ),
    )
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"test": definition}))
    reg = _registry(active=True)
    reg["integrations"]["selftest"]["preparer"] = "test"
    prepared = preparers.prepare(reg, "selftest", Point.LIBRARY, None, tmp_path)

    result = _select(prepared, reg, adapter, env={"CLAVAIN_SELECTOR_SELFTEST": "active"})

    assert result.fallback_reason == FallbackReason.UNAUTHORIZED


def test_internal_error_sanitizes_message(monkeypatch, tmp_path):
    """Internal errors don't leak exception messages."""
    adapter = FakeAdapter()
    adapter.capabilities = lambda: (_ for _ in ()).throw(RuntimeError("secret123"))

    prepared = _operator(tmp_path)
    result = _select(prepared, _registry(), adapter)

    assert result.fallback_reason == FallbackReason.INTERNAL_ERROR
    serialized = json.dumps(result.record_dict)
    assert "secret" not in serialized.lower()
    assert result.record_dict["fallback"]["detail"] == "RuntimeError"


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        ((), FallbackReason.NO_CANDIDATES),
        ((make_candidate(id="bad id", payload={}),), FallbackReason.INVALID_INPUT),
    ],
)
def test_row2_invalid_input_and_no_candidates(tmp_path, candidates, expected):
    prepared = preparers.from_operator(
        {}, "selftest", Point.LIBRARY, "choose", "context", candidates, tmp_path,
        task_revision="rev-1", read_set_paths=(),
    )
    result = _select(prepared, _registry(), FakeAdapter())
    assert result.fallback_reason == expected
    assert result.record_dict["egress"]["verdict"] == "not_run"


def test_row4_stale_revision_stops_before_egress(monkeypatch, tmp_path):
    prepared = _operator(
        tmp_path,
        candidate=make_candidate(id="a", payload={}, prepared_at_revision="old"),
    )
    monkeypatch.setattr(selector.egress, "admit", lambda *a, **k: pytest.fail("egress reached"))
    result = _select(prepared, _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.STALE_BEFORE_SELECT


def test_row6_budget_precedes_breaker_and_credential(monkeypatch, tmp_path):
    class Exhausted:
        def __init__(self, *args, **kwargs):
            pass
        def consume(self):
            return FallbackReason.BUDGET_EXHAUSTED

    monkeypatch.setattr(selector.jev_client, "Budget", Exhausted)
    monkeypatch.setattr(selector.jev_client, "Breaker", lambda: pytest.fail("breaker reached"))
    monkeypatch.setattr(selector.credentials, "load", lambda: pytest.fail("credential reached"))
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.BUDGET_EXHAUSTED


def test_row7_circuit_precedes_credential(monkeypatch, tmp_path):
    class OpenBreaker(_BreakerOK):
        def check(self):
            return FallbackReason.CIRCUIT_OPEN

    monkeypatch.setattr(selector.jev_client, "Breaker", OpenBreaker)
    monkeypatch.setattr(selector.credentials, "load", lambda: pytest.fail("credential reached"))
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.CIRCUIT_OPEN


def test_row8_credential_unavailable_precedes_client(monkeypatch, tmp_path):
    def unavailable():
        raise credentials.CredentialUnavailable("secret path")

    monkeypatch.setattr(selector.credentials, "load", unavailable)
    monkeypatch.setattr(selector.jev_client, "JevClient", lambda *a, **k: pytest.fail("client reached"))
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.CREDENTIAL_UNAVAILABLE
    assert "secret path" not in json.dumps(result.record_dict)


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        (FallbackReason.TIMEOUT, jev_client.FailureDetail.DEADLINE),
        (FallbackReason.RATE_LIMITED, jev_client.FailureDetail.STATUS),
        (FallbackReason.CREDENTIAL_REJECTED, jev_client.FailureDetail.STATUS),
        (FallbackReason.HTTP_ERROR, jev_client.FailureDetail.CONNECT_ERROR),
        (FallbackReason.INVALID_RESPONSE, jev_client.FailureDetail.BAD_JSON),
        (FallbackReason.MODEL_MISMATCH, jev_client.FailureDetail.MODEL),
    ],
)
def test_rows9_and10_client_failures(monkeypatch, tmp_path, reason, detail):
    class FailedClient:
        def __init__(self, credential):
            pass
        def call(self, call):
            return jev_client.JevFailure(
                reason=reason,
                detail=detail,
                attempts=1,
                http_status=500,
                latency_ms=2,
                model_returned="wrong" if reason is FallbackReason.MODEL_MISMATCH else None,
            )

    monkeypatch.setattr(selector.jev_client, "JevClient", FailedClient)
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert result.fallback_reason == reason
    assert result.record_dict["fallback"]["detail"] == detail.value


def test_row11_escalated_and_low_fit(monkeypatch, tmp_path):
    class AnswerClient:
        answer = "escalate"
        fit = 0.9

        def __init__(self, credential):
            pass

        def call(self, call):
            candidate_id = call.battery.select.criteria[0][0]
            probabilities = (
                (candidate_id, 0.1 if self.answer == "escalate" else 0.9),
                ("escalate", 0.9 if self.answer == "escalate" else 0.1),
            )
            return jev_client.JevOk(
                response=jev_client.JevResponse(
                    model=jev_client.PINNED_MODEL,
                    select=jev_client.ChoiceAnswer(
                        choice=self.answer if self.answer == "escalate" else candidate_id,
                        confidence=0.9,
                        probabilities=probabilities,
                    ),
                    fits=tuple(
                        jev_client.NoulAnswer(fit.key, fit.candidate_id, self.fit)
                        for fit in call.battery.fits
                    ),
                    usage=jev_client.Usage(1, 1),
                ),
                attempts=1,
                http_status=200,
                latency_ms=1,
            )

    monkeypatch.setattr(selector.jev_client, "JevClient", AnswerClient)
    escalated = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert escalated.fallback_reason == FallbackReason.JEV_ESCALATED

    AnswerClient.answer = "candidate"
    AnswerClient.fit = 0.1
    low_fit = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert low_fit.fallback_reason == FallbackReason.LOW_FIT


def test_authorize_called_once_with_typed_args_and_never_early(monkeypatch, tmp_path):
    adapter = FakeAdapter()
    selected = _select(_operator(tmp_path), _registry(), adapter)
    assert selected.fallback_reason == FallbackReason.SHADOW_MODE
    assert len(adapter.authorize_calls) == 1
    chosen, validated, policy = adapter.authorize_calls[0]
    assert chosen is selected.chosen_candidate
    assert isinstance(validated, contract.ValidatedCandidates)
    assert isinstance(policy, contract.AuthorizationPolicy)

    early = FakeAdapter()
    monkeypatch.setattr(selector.egress, "admit", lambda *a, **k: egress.Refusal(("cred.test",)))
    refused = _select(_operator(tmp_path), _registry(), early)
    assert refused.fallback_reason == FallbackReason.EGRESS_REFUSED
    assert early.authorize_calls == []


def test_row12_refingerprints_only_chosen_candidate(monkeypatch, tmp_path):
    path = tmp_path / "chosen.txt"
    path.write_text("before")
    digest = base.fingerprint_paths((path,))
    candidate = make_candidate(id="a", payload={}, read_set_fingerprint=digest)
    prepared = preparers.from_operator(
        {}, "selftest", Point.LIBRARY, "choose", "context", (candidate,), tmp_path,
        task_revision="rev-1", read_set_paths=(("a", (str(path),)),),
    )

    class MutatingClient(_ClientOK):
        def call(self, call):
            response = super().call(call)
            path.write_text("after")
            return response

    monkeypatch.setattr(selector.jev_client, "JevClient", MutatingClient)
    result = _select(prepared, _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.STALE_READ_SET
    assert result.record_dict["validation"]["reject_reason"] == "stale_read_set"


def test_external_scope_is_checked_before_row4_file_read(monkeypatch, tmp_path):
    path = tmp_path / "external.txt"
    path.write_text("secret bytes")
    digest = base.fingerprint_paths((path,))
    candidate = make_candidate(id="a", payload="x", read_set_fingerprint=digest)
    prepared = preparers.from_external(
        _registry(), "selftest", "choose", "context", (candidate,), tmp_path,
        task_revision="rev-1", read_set_paths=(("a", (str(path),)),), sources=(),
    )
    adapter = FakeAdapter()
    adapter.fingerprint = lambda *a, **k: pytest.fail("file content opened")
    monkeypatch.setattr(selector.egress, "_source_rule", lambda *a, **k: "src.denied")
    result = _select(prepared, _registry(), adapter)
    assert result.fallback_reason == FallbackReason.EGRESS_REFUSED
    assert result.record_dict["egress"]["rule_ids"] == ["src.denied"]


def test_fingerprint_cache_is_per_phase(monkeypatch, tmp_path):
    shared = tmp_path / "shared.txt"
    shared.write_text("shared")
    digest = base.fingerprint_paths((shared,))
    candidates = contract.canonical_order((
        make_candidate(id="a", payload={}, read_set_fingerprint=digest),
        make_candidate(id="b", payload={}, read_set_fingerprint=digest),
    ))
    read_sets = tuple((candidate.id, (str(shared),)) for candidate in candidates)
    prepared = preparers.from_operator(
        {}, "selftest", Point.LIBRARY, "choose", "context", candidates, tmp_path,
        task_revision="rev-1", read_set_paths=read_sets,
    )
    real_entry = base._entry_for_path
    reads = []

    def counted(path, **kwargs):
        reads.append(path.resolve())
        return real_entry(path, **kwargs)

    monkeypatch.setattr(base, "_entry_for_path", counted)
    result = _select(prepared, _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.SHADOW_MODE
    assert reads == [shared.resolve(), shared.resolve()]


def test_row4_fingerprint_aggregate_budget(monkeypatch, tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("1234")
    second.write_text("5678")
    candidates = contract.canonical_order((
        make_candidate(id="a", payload={}, read_set_fingerprint=base.fingerprint_paths((first,))),
        make_candidate(id="b", payload={}, read_set_fingerprint=base.fingerprint_paths((second,))),
    ))
    path_for = {"a": first, "b": second}
    prepared = preparers.from_operator(
        {}, "selftest", Point.LIBRARY, "choose", "context", candidates, tmp_path,
        task_revision="rev-1",
        read_set_paths=tuple((candidate.id, (str(path_for[candidate.id]),)) for candidate in candidates),
    )
    monkeypatch.setattr(base, "FINGERPRINT_MAX_BYTES", 6)
    result = _select(prepared, _registry(), FakeAdapter())
    assert result.fallback_reason == FallbackReason.STALE_BEFORE_SELECT
    assert result.record_dict["fallback"]["detail"] == "fingerprint_unavailable"


def test_eval_override_and_invalid_override(monkeypatch, tmp_path):
    prepared = preparers.from_case({
        "integration": "selftest",
        "point": "library",
        "task": "choose",
        "candidates": (make_candidate(id="a", payload={}),),
        "project_root": tmp_path,
        "task_revision": "rev-1",
    }, _registry())
    result = _select(prepared, _registry(active=True), FakeAdapter(), mode_override="eval")
    assert result.record_dict["mode"] == "eval"
    assert result.record_dict["applied"] == "native"
    assert result.fallback_reason == FallbackReason.SHADOW_MODE

    with pytest.raises(ValueError):
        _select(prepared, _registry(), FakeAdapter(), mode_override="active")

    refused = _select(prepared, _registry(), FakeAdapter())
    assert refused.fallback_reason == FallbackReason.INTERNAL_ERROR


def test_external_active_is_shadow_and_override_is_refused(tmp_path):
    candidate = make_candidate(id="a", payload="x")
    registry = _registry(active=True)
    prepared = preparers.from_external(
        registry, "selftest", "choose", "context", (candidate,), tmp_path,
        task_revision="rev-1", read_set_paths=(), sources=(),
    )
    result = _select(
        prepared,
        registry,
        FakeAdapter(),
        env={"CLAVAIN_SELECTOR_SELFTEST": "active"},
    )
    assert result.record_dict["mode"] == "shadow"
    assert result.record_dict["flags"]["active_denied"] is True
    assert result.record_dict["request"]["provenance"] == "external"
    assert result.record_dict["request"]["preparer"] is None
    assert result.record_dict["applied"] == "native"

    overridden = _select(prepared, registry, FakeAdapter(), mode_override="eval")
    assert overridden.fallback_reason == FallbackReason.INTERNAL_ERROR


def test_existing_exhausted_deadline_never_constructs_client(monkeypatch, tmp_path):
    monkeypatch.setattr(selector.jev_client, "JevClient", lambda *a, **k: pytest.fail("client reached"))
    expired = jev_client.Deadline(
        started_ns=time.monotonic_ns() - 10_000_000,
        budget_ms=1,
    )
    result = _select(_operator(tmp_path), _registry(), FakeAdapter(), deadline=expired)
    assert result.fallback_reason == FallbackReason.TIMEOUT


def test_record_unwritable_prevents_active_emission(monkeypatch, tmp_path, capsys):
    registry, prepared = _active_prepared(monkeypatch, tmp_path)
    monkeypatch.setattr(records, "append_record", lambda *a, **k: (_ for _ in ()).throw(records.RecordUnwritable("secret")))
    result = _select(
        prepared,
        registry,
        FakeAdapter(),
        env={"CLAVAIN_SELECTOR_SELFTEST": "active"},
    )
    assert result.fallback_reason == FallbackReason.RECORD_UNWRITABLE
    assert result.outcome.kind == "native"
    assert result.record_dict["applied"] == "native"
    assert "secret" not in capsys.readouterr().err


def test_emit_rechecks_binding(monkeypatch, tmp_path):
    registry, prepared = _active_prepared(monkeypatch, tmp_path)
    tampered = b"tampered"
    tampered_hash = hashlib.sha256(tampered).hexdigest()
    monkeypatch.setattr(
        base,
        "emitted_outcome",
        lambda *a, **k: Outcome(
            kind="emitted",
            mode="active",
            candidate=prepared.candidates[0],
            render_bytes=tampered,
            payload_sha256=tampered_hash,
            binding_sha256=tampered_hash,
        ),
    )
    result = _select(
        prepared,
        registry,
        FakeAdapter(),
        env={"CLAVAIN_SELECTOR_SELFTEST": "active"},
    )
    assert result.fallback_reason == FallbackReason.INTERNAL_ERROR
    assert result.record_dict["fallback"]["detail"] == "_BindingMismatch"
    assert result.outcome.kind == "native"


def test_launch_payload_must_match_template(tmp_path):
    candidate = make_candidate(id="a", payload=["sh", "-c", "a"])
    prepared = _operator(tmp_path, candidate=candidate, point=Point.LAUNCH_PROFILE)
    result = _select(
        prepared,
        _registry(points=("launch_profile",)),
        FakeAdapter(),
    )
    assert result.fallback_reason == FallbackReason.UNAUTHORIZED


def test_select_rejects_unprepared_request_without_io(monkeypatch, tmp_path):
    prepared = _operator(tmp_path)
    request = preparers.request_from(prepared, session=SESSION)
    monkeypatch.setattr(selector.credentials, "load", lambda: pytest.fail("credential reached"))
    result = selector.select(
        request,
        session=SESSION,
        adapter=FakeAdapter(),
        env={"CLAVAIN_SELECTOR_SELFTEST": "shadow"},
        now=NOW_MS,
        registry=_registry(),
    )
    assert result.fallback_reason == FallbackReason.INTERNAL_ERROR
    assert result.record_dict is None


def test_record_question_hash_matches_call_battery(monkeypatch, tmp_path):
    seen = {}

    class CapturingClient(_ClientOK):
        def call(self, call):
            seen["questions_sha256"] = call.battery.sha256
            return super().call(call)

    monkeypatch.setattr(selector.jev_client, "JevClient", CapturingClient)
    result = _select(_operator(tmp_path), _registry(), FakeAdapter())
    assert result.record_dict["request"]["questions_sha256"] == seen["questions_sha256"]


def test_flag_off_precedes_point_mismatch_and_all_other_logic(monkeypatch, tmp_path):
    """Row 1 runs first: a mismatched event cannot turn an off flag into a record."""
    prepared = _operator(tmp_path, point=Point.LIBRARY)
    event = HostEvent(point=Point.PRE_TOOL, session_id="s")
    monkeypatch.setattr(selector.preparers, "verify", lambda *a, **k: pytest.fail("verify reached"))
    monkeypatch.setattr(selector.records, "build_record", lambda *a, **k: pytest.fail("record built"))
    monkeypatch.setattr(selector.records, "append_record", lambda *a, **k: pytest.fail("record written"))
    monkeypatch.setattr(selector.credentials, "load", lambda: pytest.fail("credential reached"))

    for env in ({}, {"CLAVAIN_SELECTOR": "off", "CLAVAIN_SELECTOR_SELFTEST": "shadow"}):
        result = _select(prepared, _registry(), FakeAdapter(), env=env, event=event)
        assert result.fallback_reason == FallbackReason.FLAG_OFF
        assert result.record_dict is None
        assert result.outcome.kind == "native"


@pytest.mark.parametrize("event_point", [None, Point.LIBRARY], ids=["no_event", "mismatched_event"])
def test_a1_point_identity_required_for_emission(monkeypatch, tmp_path, event_point):
    """A1: no path reaches `emitted` unless the event point equals the prepared point."""
    registry, prepared = _active_prepared(monkeypatch, tmp_path, point=Point.PRE_TOOL)
    event = None if event_point is None else HostEvent(point=event_point, session_id="s")
    monkeypatch.setattr(base, "emitted_outcome", lambda *a, **k: pytest.fail("emission reached"))

    result = _select(prepared, registry, FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "active"}, event=event)

    assert result.fallback_reason == FallbackReason.INTERNAL_ERROR
    assert result.record_dict["fallback"]["detail"] == "_PointMismatch"
    assert result.record_dict["applied"] == "native"
    assert result.outcome.kind == "native"


def test_a1_matching_event_point_emits(monkeypatch, tmp_path):
    """Positive control for the A1 guard: a matching host event is emitted."""
    registry, prepared = _active_prepared(monkeypatch, tmp_path, point=Point.PRE_TOOL)
    event = HostEvent(point=Point.PRE_TOOL, session_id="s")
    result = _select(prepared, registry, FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "active"}, event=event)
    assert result.fallback_reason is None
    assert result.outcome.kind == "emitted"


def test_row12_unverifiable_precondition_never_emits(monkeypatch, tmp_path):
    """Landing review: row 12 must not assert `preconditions_met=True` for a
    trusted-preparer candidate that declares preconditions. This landing has no
    host verifier for them, so an unverifiable precondition is unmet: native
    fallback, nothing emitted."""
    registry, prepared = _active_prepared(
        monkeypatch, tmp_path, expires_at_ms=NOW_MS + 60_000, preconditions=("host-condition-unverified",)
    )
    monkeypatch.setattr(base, "emitted_outcome", lambda *a, **k: pytest.fail("emission reached"))

    result = _select(prepared, registry, FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "active"})

    assert result.fallback_reason == FallbackReason.UNMET_PRECONDITION
    assert result.record_dict["validation"] == {
        "stage": "host_revalidation",
        "reject_reason": "unmet_precondition",
    }
    assert result.record_dict["applied"] == "native"
    assert result.outcome.kind == "native"


def test_row12_revalidation_rereads_clock(monkeypatch, tmp_path):
    """Row 12 uses the time at revalidation, not the time `select()` started."""
    registry, prepared = _active_prepared(monkeypatch, tmp_path, expires_at_ms=NOW_MS + 5_000)
    real_monotonic_ns = time.monotonic_ns
    offset_ns = [0]
    monkeypatch.setattr(time, "monotonic_ns", lambda: real_monotonic_ns() + offset_ns[0])

    class SlowClient(_ClientOK):
        def call(self, call):
            response = super().call(call)
            offset_ns[0] += 10_000 * 1_000_000
            return response

    monkeypatch.setattr(selector.jev_client, "JevClient", SlowClient)
    monkeypatch.setattr(base, "emitted_outcome", lambda *a, **k: pytest.fail("emission reached"))

    result = _select(prepared, registry, FakeAdapter(), env={"CLAVAIN_SELECTOR_SELFTEST": "active"})

    assert result.fallback_reason == FallbackReason.EXPIRED
    assert result.record_dict["validation"] == {"stage": "host_revalidation", "reject_reason": "expired"}
    assert result.record_dict["applied"] == "native"
    assert result.outcome.kind == "native"


def test_fingerprint_phase_counts_bytes_actually_read(monkeypatch, tmp_path):
    """P3-6: the phase budget counts bytes read, not the size seen at lstat."""
    path = tmp_path / "grows.txt"
    path.write_bytes(b"1234")
    real_lstat = base._lstat
    grown = []

    def growing_lstat(raw_path):
        result = real_lstat(raw_path)
        if not grown:
            grown.append(True)
            with open(path, "ab") as handle:
                handle.write(b"567890")
        return result

    monkeypatch.setattr(base, "_lstat", growing_lstat)
    phase = base.FingerprintPhase()
    base.fingerprint_paths((path,), phase=phase)
    assert grown == [True]
    assert phase.bytes_read == 10


def test_fingerprint_paths_default_is_r6b(monkeypatch, tmp_path):
    """Without a phase, no dedup and no resolution happens before `_entry_for_path`."""
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one")
    second.write_text("two")
    link = tmp_path / "link.txt"
    link.symlink_to(second)
    paths = [link, first, first]

    expected_entries = [base._entry_for_path(p) for p in paths]
    expected_entries.sort(key=lambda e: e[0])
    expected = hashlib.sha256(
        json.dumps(sorted(expected_entries), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    real_entry = base._entry_for_path
    seen = []

    def spy(raw_path, **kwargs):
        seen.append((raw_path, kwargs))
        return real_entry(raw_path, **kwargs)

    monkeypatch.setattr(base, "_entry_for_path", spy)
    assert base.fingerprint_paths(paths) == expected
    assert seen == [(link, {}), (first, {}), (first, {})]


def _gate_order_case(monkeypatch, tmp_path, row):
    """Arrange the failure for `row` and for every later row of the table."""

    def failing(r):
        return r >= row

    def unwritable(*args, **kwargs):
        raise records.RecordUnwritable("gate-order")

    if row == 14:
        # Row 13 (shadow) and row 14 (active) are mutually exclusive modes, so
        # row 14 is arranged alone on an otherwise emitting PREPARER set.
        registry, prepared = _active_prepared(monkeypatch, tmp_path)
        monkeypatch.setattr(records, "append_record", unwritable)
        return prepared, registry, FakeAdapter(), {"CLAVAIN_SELECTOR_SELFTEST": "active"}, None

    candidate = make_candidate(
        id="bad id" if failing(2) else "a",
        payload={},
        prepared_at_revision="old" if failing(4) else "rev-1",
    )
    prepared = _operator(tmp_path, candidate=candidate)
    registry = _registry(points=("pre_tool",) if failing(3) else ("library",))
    if failing(11):
        registry["integrations"]["selftest"]["floors"]["confidence"] = 0.99
    if failing(5):
        monkeypatch.setattr(selector.egress, "admit", lambda *a, **k: egress.Refusal(("cred.test",)))
    if failing(6):
        class Exhausted(_BudgetOK):
            def consume(self):
                return FallbackReason.BUDGET_EXHAUSTED

        monkeypatch.setattr(selector.jev_client, "Budget", Exhausted)
    if failing(7):
        class OpenBreaker(_BreakerOK):
            def check(self):
                return FallbackReason.CIRCUIT_OPEN

        monkeypatch.setattr(selector.jev_client, "Breaker", OpenBreaker)
    if failing(8):
        def unavailable():
            raise credentials.CredentialUnavailable("gate-order")

        monkeypatch.setattr(selector.credentials, "load", unavailable)
    deadline = None
    if failing(9):
        deadline = jev_client.Deadline(started_ns=time.monotonic_ns() - 10_000_000, budget_ms=1)
    if failing(10):
        class InvalidClient:
            def __init__(self, credential):
                pass

            def call(self, call):
                return jev_client.JevFailure(
                    reason=FallbackReason.INVALID_RESPONSE,
                    detail=jev_client.FailureDetail.BAD_JSON,
                    attempts=1,
                    http_status=200,
                    latency_ms=1,
                )

        monkeypatch.setattr(selector.jev_client, "JevClient", InvalidClient)
    adapter = FakeAdapter()
    adapter.authorized = not failing(12)
    # Row 13 (shadow) is the default below row 14; row 1 replaces it with off.
    env = {} if failing(1) else {"CLAVAIN_SELECTOR_SELFTEST": "shadow"}
    # Row 14's failure is arranged under shadow mode, where it cannot win.
    monkeypatch.setattr(records, "append_record", unwritable)
    return prepared, registry, adapter, env, deadline


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (1, FallbackReason.FLAG_OFF),
        (2, FallbackReason.INVALID_INPUT),
        (3, FallbackReason.POINT_UNREACHABLE),
        (4, FallbackReason.STALE_BEFORE_SELECT),
        (5, FallbackReason.EGRESS_REFUSED),
        (6, FallbackReason.BUDGET_EXHAUSTED),
        (7, FallbackReason.CIRCUIT_OPEN),
        (8, FallbackReason.CREDENTIAL_UNAVAILABLE),
        (9, FallbackReason.TIMEOUT),
        (10, FallbackReason.INVALID_RESPONSE),
        (11, FallbackReason.LOW_CONFIDENCE),
        (12, FallbackReason.UNAUTHORIZED),
        (13, FallbackReason.SHADOW_MODE),
        (14, FallbackReason.RECORD_UNWRITABLE),
    ],
)
def test_gate_order(monkeypatch, tmp_path, capsys, row, expected):
    """Each row wins over every later row's simultaneously arranged failure."""
    prepared, registry, adapter, env, deadline = _gate_order_case(monkeypatch, tmp_path, row)
    result = _select(prepared, registry, adapter, env=env, deadline=deadline)
    assert result.fallback_reason == expected
    if row == 1:
        assert result.record_dict is None
    else:
        assert result.record_dict["fallback"]["reason"] == expected.value
    assert result.outcome.kind != "emitted"


@pytest.mark.parametrize("provenance", ["operator", "external", "eval_case"])
def test_provenance_limits_mode_survives_forced_active(monkeypatch, tmp_path, provenance):
    """R12-1: with the provenance cap bypassed, only PREPARER may still emit."""
    registry = _registry(active=True)
    mode_override = None
    if provenance == "operator":
        prepared = _operator(tmp_path)
    elif provenance == "external":
        prepared = preparers.from_external(
            registry, "selftest", "choose", "context", (make_candidate(id="a", payload="x"),), tmp_path,
            task_revision="rev-1", read_set_paths=(), sources=(),
        )
    else:
        prepared = preparers.from_case({
            "integration": "selftest",
            "point": "library",
            "task": "choose",
            "candidates": (make_candidate(id="a", payload={}),),
            "project_root": tmp_path,
            "task_revision": "rev-1",
        }, registry)
        mode_override = "eval"
    assert prepared.provenance is Provenance(provenance)

    monkeypatch.setattr(selector, "_resolve_mode", lambda *a, **k: selector._ModeDecision("active", {}))
    monkeypatch.setattr(base, "emitted_outcome", lambda *a, **k: pytest.fail("emission reached"))
    adapter = FakeAdapter()
    adapter.render = lambda *a, **k: pytest.fail("render reached")

    result = _select(
        prepared,
        registry,
        adapter,
        env={"CLAVAIN_SELECTOR_SELFTEST": "active"},
        mode_override=mode_override,
    )

    assert result.fallback_reason == FallbackReason.SHADOW_MODE
    assert result.record_dict["mode"] == "active"
    assert result.record_dict["applied"] == "native"
    assert result.outcome.kind == "native"
    # A successful authorization cannot lift the cap.
    assert len(adapter.authorize_calls) == 1
    assert base.authorize_by_policy(*adapter.authorize_calls[0]) is True


def _external_state_set(tmp_path):
    state = tmp_path / "state.txt"
    state.write_text("content")
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=not-for-jev")
    candidate = make_candidate(id="a", payload="x", read_set_fingerprint=base.fingerprint_paths((state,)))
    prepared = preparers.from_external(
        _registry(), "selftest", "choose", "context", (candidate,), tmp_path,
        task_revision="rev-1", read_set_paths=(("a", (str(state),)),), sources=(),
    )
    return state, secret, prepared


def test_external_scope_recheck_before_fingerprint(monkeypatch, tmp_path):
    """R12-2, row 4: a path that now resolves to a denylisted target is refused unread."""
    state, secret, prepared = _external_state_set(tmp_path)
    state.unlink()
    state.symlink_to(secret)
    adapter = FakeAdapter()
    adapter.fingerprint = lambda *a, **k: pytest.fail("fingerprint reached")
    monkeypatch.setattr(base, "_entry_for_path", lambda *a, **k: pytest.fail("file content opened"))

    result = _select(prepared, _registry(), adapter)

    assert result.fallback_reason == FallbackReason.EGRESS_REFUSED
    assert result.record_dict["egress"]["rule_ids"] == ["src.denylisted_path"]


def test_external_scope_recheck_before_row12_fingerprint(monkeypatch, tmp_path):
    """R12-2, row 12: the chosen read set is rechecked before it is re-read."""
    state, secret, prepared = _external_state_set(tmp_path)
    swapped = []

    class SwappingClient(_ClientOK):
        def call(self, call):
            response = super().call(call)
            state.unlink()
            state.symlink_to(secret)
            swapped.append(True)
            return response

    real_entry = base._entry_for_path

    def guarded_entry(raw_path, **kwargs):
        if swapped:
            pytest.fail("file content opened after the swap")
        return real_entry(raw_path, **kwargs)

    fingerprint_calls = []
    adapter = FakeAdapter()
    real_fingerprint = adapter.fingerprint

    def spy_fingerprint(paths, *, phase=None):
        fingerprint_calls.append(tuple(paths))
        return real_fingerprint(paths, phase=phase)

    adapter.fingerprint = spy_fingerprint
    monkeypatch.setattr(selector.jev_client, "JevClient", SwappingClient)
    monkeypatch.setattr(base, "_entry_for_path", guarded_entry)

    result = _select(prepared, _registry(), adapter)

    assert swapped == [True]
    assert len(fingerprint_calls) == 1
    assert result.fallback_reason == FallbackReason.EGRESS_REFUSED
    assert result.record_dict["egress"]["rule_ids"] == ["src.denylisted_path"]


def _load_cli_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "clavain-select.py"
    spec = importlib.util.spec_from_file_location("clavain_select_task7_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_subcommand_uses_registry_preparer_and_environment(monkeypatch, tmp_path):
    cli = _load_cli_module()
    registry = _registry()
    registry["integrations"]["selftest"].update({
        "preparer": "hook-test",
        "hooks": [{"host": "claude-code", "point": "pre_tool"}],
        "points": ["pre_tool"],
        "deadline_ms": {"pre_tool": 3000},
    })
    definition = preparers.Preparer(
        name="hook-test",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, root: preparers.PreparedInput(
            task="trusted task",
            candidates=(make_candidate(id="a", payload={"trusted": True}),),
            task_revision="rev-1",
        ),
    )
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"hook-test": definition}))
    monkeypatch.setattr(cli, "_load_registry", lambda: registry)
    monkeypatch.setattr(cli, "_get_host_adapter", lambda host: FakeAdapter())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAVAIN_SELECTOR_SELFTEST", "shadow")
    raw = {
        "session_id": "hook-session",
        "integration": "other",
        "candidates": [{"id": "evil", "payload": "evil-payload"}],
        "project_root": "/tmp/evil",
        "CLAUDE_PROJECT_DIR": "/tmp/evil-2",
    }
    monkeypatch.setattr(cli.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(raw).encode())))
    seen = {}
    real_select = selector.select

    def capture(prepared, **kwargs):
        seen["prepared"] = prepared
        return real_select(prepared, **kwargs)

    monkeypatch.setattr(cli.selector, "select", capture)
    result = cli.main_hook(SimpleNamespace(point="pre_tool", host="claude-code"))
    assert result == 0
    assert seen["prepared"].integration == "selftest"
    assert [candidate.id for candidate in seen["prepared"].candidates] == ["a"]
    assert seen["prepared"].project_root == tmp_path.resolve()
    assert "evil" not in json.dumps(seen["prepared"].bindings)


def test_hook_subcommand_has_no_integration_option(monkeypatch):
    cli = _load_cli_module()
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["clavain-select.py", "hook", "--point", "pre_tool", "--host", "claude-code", "--integration", "x"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def _hook_registry(*, active=False):
    registry = _registry(active=active)
    registry["integrations"]["selftest"].update({
        "preparer": "hook-test",
        "hooks": [{"host": "claude-code", "point": "pre_tool"}],
        "points": ["pre_tool"],
        "deadline_ms": {"pre_tool": 3000},
    })
    definition = preparers.Preparer(
        name="hook-test",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, root: preparers.PreparedInput(
            task="trusted task",
            candidates=(make_candidate(id="a", payload={"trusted": True}),),
            task_revision="rev-1",
        ),
    )
    return registry, definition


class _NoStdin:
    @property
    def buffer(self):
        pytest.fail("stdin read")


@pytest.mark.parametrize(
    "env",
    [
        {"CLAVAIN_SELECTOR": "off", "CLAVAIN_SELECTOR_SELFTEST": "shadow"},
        {"CLAVAIN_SELECTOR_SELFTEST": "off"},
    ],
    ids=["global_kill_switch", "integration_off"],
)
def test_hook_flag_off_precedes_stdin_and_preparer(monkeypatch, tmp_path, env):
    cli = _load_cli_module()
    registry, definition = _hook_registry()
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"hook-test": definition}))
    monkeypatch.setattr(cli, "_load_registry", lambda: registry)
    monkeypatch.setattr(cli, "_get_host_adapter", lambda host: FakeAdapter())
    monkeypatch.setattr(cli.preparers, "prepare", lambda *a, **k: pytest.fail("preparer reached"))
    monkeypatch.setattr(cli.selector, "select", lambda *a, **k: pytest.fail("select reached"))
    monkeypatch.setattr(cli.sys, "stdin", _NoStdin())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAVAIN_SELECTOR", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert cli.main_hook(SimpleNamespace(point="pre_tool", host="claude-code")) == 0


@pytest.mark.parametrize(
    ("event_point", "rendered"),
    [(Point.PRE_TOOL, True), (Point.POST_TOOL_OUTPUT, False)],
    ids=["matching_event", "mismatched_event"],
)
def test_hook_renders_only_matching_event_point(monkeypatch, tmp_path, event_point, rendered):
    cli = _load_cli_module()
    registry, definition = _hook_registry(active=True)
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"hook-test": definition}))
    monkeypatch.setattr(cli, "_load_registry", lambda: registry)

    class WrongPointAdapter(FakeAdapter):
        def parse_event(self, point, raw):
            return HostEvent(point=event_point, session_id="hook-session")

        def render(self, point, outcome, event):
            assert outcome.kind == "emitted"
            return b"EMITTED"

    monkeypatch.setattr(cli, "_get_host_adapter", lambda host: WrongPointAdapter())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAVAIN_SELECTOR", raising=False)
    monkeypatch.setenv("CLAVAIN_SELECTOR_SELFTEST", "active")
    monkeypatch.setattr(cli.sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    stdout = SimpleNamespace(buffer=io.BytesIO())
    monkeypatch.setattr(cli.sys, "stdout", stdout)

    assert cli.main_hook(SimpleNamespace(point="pre_tool", host="claude-code")) == 0
    assert stdout.buffer.getvalue() == (b"EMITTED" if rendered else b"")
