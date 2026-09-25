"""Tests for scripts/clavain_selector/contract.py (mk-42j9.7 Task 1)."""

from __future__ import annotations

import json

from selector_helpers import make_candidate, make_request, selector_socket_guard  # noqa: F401

from clavain_selector.contract import (
    FALLBACK_TABLE,
    FallbackReason,
    Point,
    RejectReason,
    SessionRef,
    ValidationContext,
    pre_eligibility,
    revalidate,
    validate_request,
)


def test_candidate_id_pattern():
    assert validate_request(make_request(candidates=(make_candidate(id="a"),))) is None
    assert validate_request(make_request(candidates=(make_candidate(id="x.y-z_1"),))) is None
    assert validate_request(make_request(candidates=(make_candidate(id="a" * 64),))) is None

    assert validate_request(make_request(candidates=(make_candidate(id=""),))) == FallbackReason.INVALID_INPUT
    assert validate_request(make_request(candidates=(make_candidate(id="a" * 65),))) == FallbackReason.INVALID_INPUT
    assert validate_request(make_request(candidates=(make_candidate(id="a b"),))) == FallbackReason.INVALID_INPUT
    assert validate_request(make_request(candidates=(make_candidate(id="escalate"),))) == FallbackReason.INVALID_INPUT
    dup = (make_candidate(id="same"), make_candidate(id="same"))
    assert validate_request(make_request(candidates=dup)) == FallbackReason.INVALID_INPUT


def test_limits():
    long_task = make_request(task="x" * 12_001)
    assert validate_request(long_task) == FallbackReason.INVALID_INPUT

    long_context = make_request(context="x" * 40_001)
    assert validate_request(long_context) == FallbackReason.INVALID_INPUT

    too_many = tuple(make_candidate(id=f"c{i}") for i in range(17))
    assert validate_request(make_request(candidates=too_many)) == FallbackReason.INVALID_INPUT

    long_description = make_request(candidates=(make_candidate(description="x" * 2001),))
    assert validate_request(long_description) == FallbackReason.INVALID_INPUT

    assert validate_request(make_request(candidates=())) == FallbackReason.NO_CANDIDATES


def test_selector_view_omits_payload():
    canary = "CANARY-SECRET-PAYLOAD-VALUE"
    candidate = make_candidate(payload={"secret": canary})
    view = candidate.selector_view()
    assert set(view.keys()) == {"id", "description"}
    assert canary not in json.dumps(view)


def test_fallback_table_complete():
    assert set(FALLBACK_TABLE.keys()) == set(FallbackReason)
    assert len(FallbackReason) == 27
    for reason, row in FALLBACK_TABLE.items():
        assert row.applied == "native"
        assert isinstance(row.counts_toward_breaker, bool)
        assert isinstance(row.writes_record, bool)


def test_pre_eligibility():
    ctx = ValidationContext(now_ms=1_000, current_revision="rev-1", current_read_set_fingerprint=None, authorized=True)
    valid = (make_candidate(id="a"), make_candidate(id="b"))
    assert pre_eligibility(valid, ctx) is None

    expired = (make_candidate(id="a"), make_candidate(id="b", expires_at_ms=500))
    assert pre_eligibility(expired, ctx) == FallbackReason.STALE_BEFORE_SELECT


def test_revalidate_each_reason():
    ctx = ValidationContext(now_ms=1_000, current_revision="rev-1", current_read_set_fingerprint="fp-1", authorized=True)
    candidates = (make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1"),)

    assert revalidate(candidates, "unknown", ctx) == RejectReason.INVALID_ID

    stale_rev = (make_candidate(id="a", prepared_at_revision="rev-0", read_set_fingerprint="fp-1"),)
    assert revalidate(stale_rev, "a", ctx) == RejectReason.STALE_REVISION

    stale_read_set = (make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-0"),)
    assert revalidate(stale_read_set, "a", ctx) == RejectReason.STALE_READ_SET

    expired = (make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1", expires_at_ms=1),)
    assert revalidate(expired, "a", ctx) == RejectReason.EXPIRED

    assert revalidate(candidates, "a", ctx, preconditions_met=False) == RejectReason.UNMET_PRECONDITION

    unauthorized_ctx = ValidationContext(now_ms=1_000, current_revision="rev-1", current_read_set_fingerprint="fp-1", authorized=False)
    assert revalidate(candidates, "a", unauthorized_ctx) == RejectReason.UNAUTHORIZED

    assert revalidate(candidates, "a", ctx) is None


def test_point_and_reject_reason_values_are_stable_strings():
    assert Point.LIBRARY.value == "library"
    assert Point.LAUNCH_PROFILE.value == "launch_profile"
    assert {r.value for r in RejectReason} == {
        "invalid_id", "stale_revision", "stale_read_set", "expired", "unmet_precondition", "unauthorized",
    }


def test_session_ref_is_frozen():
    ref = SessionRef(host_session_id="sess-1")
    assert ref.bead_id is None
