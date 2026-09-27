"""Tests for scripts/clavain_selector/preparers.py (mk-42j9.7 Task R6b).

Covers the plan's "Trusted preparers" subsection: the (currently empty,
immutable) `PREPARERS` registry, `prepare`/`from_operator`/`from_case`,
`verify`'s HMAC-tag and payload-binding forgery resistance, the event-field
projection restriction, the vocabulary restriction, and the
`read_set_paths` source-boundary rejection via `egress._source_rule`.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from types import MappingProxyType

import pytest
from selector_helpers import make_candidate, selector_socket_guard  # noqa: F401

from clavain_selector import preparers
from clavain_selector.adapters.base import HostEvent
from clavain_selector.contract import Point, Provenance, SessionRef
from clavain_selector.preparers import (
    NotPrepared,
    PREPARERS,
    Preparer,
    PreparedSet,
    from_case,
    from_operator,
    prepare,
    request_from,
    validated,
    verify,
)


# ---------------------------------------------------------------------------
# Registry: empty, immutable
# ---------------------------------------------------------------------------


def test_registry_starts_empty():
    assert dict(PREPARERS) == {}


def test_registry_is_immutable():
    with pytest.raises(TypeError):
        PREPARERS["x"] = object()


def test_preparer_rejects_unknown_event_fields():
    with pytest.raises(NotPrepared):
        Preparer(
            name="bad",
            points=frozenset({Point.PRE_TOOL}),
            vocabulary=frozenset(),
            event_fields=frozenset({"bogus_field"}),
            build=lambda event: {"task": "x", "candidates": ()},
        )


# ---------------------------------------------------------------------------
# prepare(): unknown name, point mismatch, build failures, vocabulary
# ---------------------------------------------------------------------------


def test_prepare_unknown_name_raises():
    with pytest.raises(NotPrepared):
        prepare("does-not-exist", None)


def _install_preparer(monkeypatch, preparer: Preparer) -> None:
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({preparer.name: preparer}))


def test_prepare_happy_path_produces_verifiable_set(monkeypatch):
    def _build(event: HostEvent) -> dict:
        return {
            "integration": "selftest",
            "task": "do the thing",
            "context": "",
            "candidates": (make_candidate(id="cand-a", prepared_at_revision="rev-1"),),
        }

    fake = Preparer(
        name="test-preparer",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)

    event = HostEvent(point=Point.PRE_TOOL, session_id="sess-real", tool_name="Bash", tool_input={"command": "rm -rf /"})
    result = prepare("test-preparer", event)

    assert result.provenance is Provenance.PREPARER
    assert result.preparer == "test-preparer"
    assert result.task == "do the thing"
    assert [c.id for c in result.candidates] == ["cand-a"]
    assert verify(result) is True


def test_prepare_point_mismatch_raises(monkeypatch):
    fake = Preparer(
        name="pre-tool-only",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset(),
        build=lambda event: {"task": "x", "candidates": (make_candidate(id="cand-a"),)},
    )
    _install_preparer(monkeypatch, fake)

    event = HostEvent(point=Point.POST_TOOL_OUTPUT, session_id="sess-real")
    with pytest.raises(NotPrepared):
        prepare("pre-tool-only", event)


def test_prepare_build_missing_required_key_raises(monkeypatch):
    fake = Preparer(
        name="incomplete",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset(),
        build=lambda event: {"task": "x"},  # missing "candidates"
    )
    _install_preparer(monkeypatch, fake)
    with pytest.raises(NotPrepared):
        prepare("incomplete", HostEvent(point=Point.PRE_TOOL, session_id="s"))


def test_prepare_build_exception_becomes_not_prepared(monkeypatch):
    def _boom(event: HostEvent):
        raise RuntimeError("boom")

    fake = Preparer(
        name="explodes",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset(),
        build=_boom,
    )
    _install_preparer(monkeypatch, fake)
    with pytest.raises(NotPrepared):
        prepare("explodes", HostEvent(point=Point.PRE_TOOL, session_id="s"))


def test_prepare_vocabulary_restriction_rejects_outside_ids(monkeypatch):
    fake = Preparer(
        name="scoped",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset({"allowed-a", "allowed-b"}),
        event_fields=frozenset(),
        build=lambda event: {"task": "x", "candidates": (make_candidate(id="not-allowed"),)},
    )
    _install_preparer(monkeypatch, fake)
    with pytest.raises(NotPrepared):
        prepare("scoped", HostEvent(point=Point.PRE_TOOL, session_id="s"))


def test_prepare_vocabulary_restriction_allows_in_scope_ids(monkeypatch):
    fake = Preparer(
        name="scoped-ok",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset({"allowed-a"}),
        event_fields=frozenset(),
        build=lambda event: {"task": "x", "candidates": (make_candidate(id="allowed-a"),)},
    )
    _install_preparer(monkeypatch, fake)
    result = prepare("scoped-ok", HostEvent(point=Point.PRE_TOOL, session_id="s"))
    assert [c.id for c in result.candidates] == ["allowed-a"]


def test_prepare_projects_event_to_declared_fields_only(monkeypatch):
    seen: dict = {}

    def _build(event: HostEvent) -> dict:
        seen["session_id"] = event.session_id
        seen["tool_name"] = event.tool_name
        seen["tool_input"] = event.tool_input
        seen["tool_response"] = event.tool_response
        return {"task": "x", "candidates": (make_candidate(id="cand-a"),)}

    fake = Preparer(
        name="projected",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset({"tool_name"}),  # only tool_name declared
        build=_build,
    )
    _install_preparer(monkeypatch, fake)

    real_event = HostEvent(
        point=Point.PRE_TOOL,
        session_id="real-session-id",
        tool_name="Bash",
        tool_input={"command": "rm -rf /"},
        tool_response="should never be seen",
    )
    prepare("projected", real_event)

    # Only the declared field crosses the boundary; every other field is
    # reset to its projected default regardless of what the real event held.
    assert seen["tool_name"] == "Bash"
    assert seen["session_id"] == ""
    assert seen["tool_input"] is None
    assert seen["tool_response"] is None


def test_prepare_with_no_event_uses_first_declared_point(monkeypatch):
    fake = Preparer(
        name="no-event",
        points=frozenset({Point.SESSION_START}),
        vocabulary=frozenset(),
        event_fields=frozenset(),
        build=lambda event: {"task": "x", "candidates": (make_candidate(id="cand-a"),), "point": event.point},
    )
    _install_preparer(monkeypatch, fake)
    result = prepare("no-event", None)
    assert result.point == Point.SESSION_START


# ---------------------------------------------------------------------------
# from_operator / from_case
# ---------------------------------------------------------------------------


def test_from_operator_happy_path():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
    assert result.provenance is Provenance.OPERATOR
    assert result.preparer is None
    assert verify(result) is True


def test_from_case_happy_path():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    case = {
        "integration": "selftest",
        "point": Point.LIBRARY,
        "task": "do the thing",
        "candidates": (candidate,),
    }
    result = from_case(case)
    assert result.provenance is Provenance.EVAL_CASE
    assert verify(result) is True


def test_from_case_missing_required_key_raises():
    with pytest.raises(NotPrepared):
        from_case({"integration": "selftest", "point": Point.LIBRARY, "task": "x"})


# ---------------------------------------------------------------------------
# verify(): tag forgery resistance and payload-tamper detection
# ---------------------------------------------------------------------------


def test_verify_rejects_hand_built_preparedset():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    forged = PreparedSet(
        integration="selftest",
        point=Point.LIBRARY,
        provenance=Provenance.OPERATOR,
        preparer=None,
        task="do the thing",
        context="",
        candidates=(candidate,),
        sources=(),
        project_root=None,
        task_revision="rev-1",
        bindings=(("cand-a", "0" * 64),),
        read_set_paths=(),
        tag=b"not-a-real-tag",
    )
    assert verify(forged) is False


def test_verify_rejects_tampered_task_after_prepare():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "original task", "", (candidate,))
    tampered = dataclasses.replace(result, task="a different task")
    assert verify(tampered) is False


def test_verify_catches_payload_tampered_after_prepare():
    """The HMAC tag excludes `payload` (per `_json_default`), so a payload
    swap alone must be caught by the recomputed-bindings check, not the tag."""
    candidate = make_candidate(id="cand-a", payload="original", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
    tampered_candidate = dataclasses.replace(candidate, payload="tampered")
    tampered = dataclasses.replace(result, candidates=(tampered_candidate,))
    # The tag itself is untouched (payload isn't tagged) -- only the binding
    # mismatch should cause this to fail.
    assert verify(tampered) is False


def test_verify_rejects_non_preparedset():
    assert verify("not a PreparedSet") is False
    assert verify(None) is False


# ---------------------------------------------------------------------------
# read_set_paths source-boundary rejection
# ---------------------------------------------------------------------------


def test_read_set_paths_inside_project_root_is_accepted(tmp_path):
    inside = tmp_path / "src" / "file.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(
        "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(str(inside),),
    )
    assert result.read_set_paths == (str(inside.resolve()),)


def test_read_set_paths_outside_project_root_raises(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=project_root, read_set_paths=(str(outside),),
        )


def test_read_set_paths_denylisted_home_path_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    ssh_key = str(Path("~/.ssh/id_rsa").expanduser())
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=None, read_set_paths=(ssh_key,),
        )


def test_read_set_paths_with_no_project_root_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=None, read_set_paths=("/tmp/whatever.py",),
        )


# ---------------------------------------------------------------------------
# request_from / validated
# ---------------------------------------------------------------------------


def test_request_from_round_trips_prepared_fields():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "ctx", (candidate,))
    session = SessionRef(host_session_id="sess-real-1")
    request = request_from(result, session=session)
    assert request.integration == "selftest"
    assert request.point == Point.LIBRARY
    assert request.task == "do the thing"
    assert request.context == "ctx"
    assert [c.id for c in request.candidates] == ["cand-a"]
    assert request.session == session


def test_validated_succeeds_for_a_freshly_prepared_set():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
    session = SessionRef(host_session_id="sess-real-1")
    vc = validated(result, session=session)
    assert vc.provenance is Provenance.OPERATOR
    assert vc.bindings == result.bindings
    assert [c.id for c in vc.candidates] == ["cand-a"]


def test_validated_raises_when_verification_fails():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
    tampered = dataclasses.replace(result, task="tampered task")
    with pytest.raises(NotPrepared):
        validated(tampered, session=SessionRef(host_session_id="sess-real-1"))
