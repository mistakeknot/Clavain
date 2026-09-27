"""Tests for scripts/clavain_selector/preparers.py (mk-42j9.7 Task R6b).

Covers the plan's "Trusted preparers" subsection: the (currently empty,
immutable) `PREPARERS` registry, `prepare`/`from_operator`/`from_case`,
`verify`'s HMAC-tag and payload-binding forgery resistance, the event-field
projection restriction, the vocabulary restriction, and the
`read_set_paths` source-boundary rejection via `egress._source_rule`.

Findings 1-5, 7-9 from the other-frontier review of 13e74b3 (mk-42j9.7):
`verify`/`validated` now raise `NotPrepared` instead of returning a bool
(finding 7); every assertion below that used to check `verify(...) is
True`/`is False` now checks `verify(...) is None` or
`pytest.raises(NotPrepared)`.

Finding 6 (this file's revision): `prepare`/`from_operator`/`from_case` are
registry-driven per plan lines 414-416. `registry` is the same
`Mapping[str, Any]` shape `flags.py` already reads: a `dict` with an
`integrations` mapping from integration name to an entry `dict` whose
`"preparer"` key names an entry in `PREPARERS`. `from_operator`/`from_case`
accept `registry` per the plan's signature but never use it (no vocabulary
check for operator/eval-case sets). `Preparer.vocabulary` is now
`Callable[[Path], frozenset[str]]`, and `Preparer.build` now takes
`(event, project_root)` and returns a `PreparedInput` (task, context,
candidates, read_set_paths, sources, task_revision -- no integration/point).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from selector_helpers import make_candidate, selector_socket_guard  # noqa: F401

import clavain_selector.egress as egress
from clavain_selector import preparers
from clavain_selector.adapters.base import HostEvent
from clavain_selector.contract import Point, Provenance, SessionRef, payload_sha256
from clavain_selector.preparers import (
    NotPrepared,
    PREPARERS,
    Preparer,
    PreparedInput,
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


def _registry_for(integration: str, preparer_name: str) -> dict:
    return {"schema_version": 1, "integrations": {integration: {"preparer": preparer_name}}}


# A registry usable by from_operator/from_case tests: never consulted by
# either factory, so its shape doesn't matter beyond being a Mapping.
UNUSED_REGISTRY: dict = {"schema_version": 1, "integrations": {}}


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
            vocabulary=lambda project_root: frozenset(),
            event_fields=frozenset({"bogus_field"}),
            build=lambda event, project_root: PreparedInput(task="x", candidates=()),
        )


# ---------------------------------------------------------------------------
# prepare(): unknown integration/preparer, point mismatch, build failures,
# vocabulary
# ---------------------------------------------------------------------------


def test_prepare_unknown_integration_raises(tmp_path):
    with pytest.raises(NotPrepared):
        prepare(UNUSED_REGISTRY, "does-not-exist", Point.PRE_TOOL, None, project_root=tmp_path)


def test_prepare_unknown_preparer_name_raises(tmp_path):
    registry = _registry_for("selftest", "does-not-exist")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, None, project_root=tmp_path)


def _install_preparer(monkeypatch, preparer: Preparer) -> None:
    from types import MappingProxyType

    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({preparer.name: preparer}))


def test_prepare_happy_path_produces_verifiable_set(monkeypatch, tmp_path):
    def _build(event: HostEvent | None, project_root) -> PreparedInput:
        return PreparedInput(
            task="do the thing",
            context="",
            candidates=(make_candidate(id="cand-a", prepared_at_revision="rev-1"),),
        )

    fake = Preparer(
        name="test-preparer",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "test-preparer")

    event = HostEvent(point=Point.PRE_TOOL, session_id="sess-real", tool_name="Bash", tool_input={"command": "rm -rf /"})
    result = prepare(registry, "selftest", Point.PRE_TOOL, event, project_root=tmp_path)

    assert result.provenance is Provenance.PREPARER
    assert result.preparer == "test-preparer"
    assert result.integration == "selftest"
    assert result.point is Point.PRE_TOOL
    assert result.task == "do the thing"
    assert [c.id for c in result.candidates] == ["cand-a"]
    # Plan line 1717: bindings equal the candidates' own payload hashes.
    assert result.bindings == tuple((c.id, payload_sha256(c.payload)) for c in result.candidates)
    assert verify(result) is None


def test_prepare_point_mismatch_raises(monkeypatch, tmp_path):
    fake = Preparer(
        name="pre-tool-only",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "pre-tool-only")

    event = HostEvent(point=Point.POST_TOOL_OUTPUT, session_id="sess-real")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.POST_TOOL_OUTPUT, event, project_root=tmp_path)


def test_prepare_point_mismatch_raises_even_with_no_event(monkeypatch, tmp_path):
    """Finding 6: `point in preparer.points` is always required, including
    when `event is None` -- there is no fallback that iterates
    `preparer.points` to pick one."""
    fake = Preparer(
        name="pre-tool-only-no-event",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "pre-tool-only-no-event")

    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.SESSION_START, None, project_root=tmp_path)


def test_prepare_build_missing_required_key_raises(monkeypatch, tmp_path):
    fake = Preparer(
        name="incomplete",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x"),  # missing "candidates"
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "incomplete")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_prepare_build_wrong_return_type_raises(monkeypatch, tmp_path):
    """Finding 6: a preparer that returns a plain `dict` instead of a
    `PreparedInput` is `NotPrepared`, not silently accepted."""
    fake = Preparer(
        name="wrong-shape",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: {"task": "x", "candidates": ()},
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "wrong-shape")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_prepare_build_exception_becomes_not_prepared(monkeypatch, tmp_path):
    def _boom(event: HostEvent | None, project_root):
        raise RuntimeError("boom")

    fake = Preparer(
        name="explodes",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=_boom,
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "explodes")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_prepare_vocabulary_restriction_rejects_outside_ids(monkeypatch, tmp_path):
    fake = Preparer(
        name="scoped",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"allowed-a", "allowed-b"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="not-allowed"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "scoped")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_prepare_vocabulary_restriction_allows_in_scope_ids(monkeypatch, tmp_path):
    fake = Preparer(
        name="scoped-ok",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"allowed-a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="allowed-a"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "scoped-ok")
    result = prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)
    assert [c.id for c in result.candidates] == ["allowed-a"]


def test_prepare_empty_vocabulary_rejects_every_id(monkeypatch, tmp_path):
    """Finding 6: an empty `vocabulary(project_root)` result is an empty
    *closed* set -- every candidate id is rejected, not "no restriction"
    (the opposite of what was previously landed)."""
    fake = Preparer(
        name="closed",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="anything"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "closed")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_prepare_calls_vocabulary_with_project_root_only(tmp_path, monkeypatch):
    """Plan line 1717 ('the vocabulary function is called with
    project_root only (spy)'): finding 9's vocabulary-spy test, un-skipped
    now that `Preparer.vocabulary` is `Callable[[Path], frozenset[str]]`
    (finding 6)."""
    calls: list[tuple] = []

    def _vocabulary(project_root):
        calls.append((project_root,))
        return frozenset({"cand-a"})

    fake = Preparer(
        name="vocab-spy",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=_vocabulary,
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "vocab-spy")

    project_root = tmp_path / "project"
    project_root.mkdir()
    prepare(
        registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"),
        project_root=project_root,
    )

    assert len(calls) == 1
    (args,) = calls
    assert args == (Path(project_root),)


def test_prepare_projects_event_to_declared_fields_only(monkeypatch, tmp_path):
    seen: dict = {}

    def _build(event: HostEvent, project_root) -> PreparedInput:
        seen["session_id"] = event.session_id
        seen["tool_name"] = event.tool_name
        seen["tool_input"] = event.tool_input
        seen["tool_response"] = event.tool_response
        return PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),))

    fake = Preparer(
        name="projected",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset({"tool_name"}),  # only tool_name declared
        build=_build,
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "projected")

    real_event = HostEvent(
        point=Point.PRE_TOOL,
        session_id="real-session-id",
        tool_name="Bash",
        tool_input={"command": "rm -rf /"},
        tool_response="should never be seen",
    )
    prepare(registry, "selftest", Point.PRE_TOOL, real_event, project_root=tmp_path)

    # Only the declared field crosses the boundary; every other field is
    # reset to its projected default regardless of what the real event held.
    assert seen["tool_name"] == "Bash"
    assert seen["session_id"] == ""
    assert seen["tool_input"] is None
    assert seen["tool_response"] is None


def test_prepare_projects_raw_to_empty_dict(monkeypatch, tmp_path):
    """Plan line 1718 (projection spy): the projected event's `raw` is
    always `{}`, regardless of what the real event's `raw` held -- `raw`
    is not one of the fields a preparer can ever declare (it isn't in
    `_EVENT_FIELD_NAMES`)."""
    seen: dict = {}

    def _build(event: HostEvent, project_root) -> PreparedInput:
        seen["raw"] = event.raw
        return PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),))

    fake = Preparer(
        name="raw-spy",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "raw-spy")

    real_event = HostEvent(
        point=Point.PRE_TOOL,
        session_id="real-session-id",
        tool_name="Bash",
        raw={"authorized": True, "anything": "at all"},
    )
    prepare(registry, "selftest", Point.PRE_TOOL, real_event, project_root=tmp_path)

    assert seen["raw"] == {}


def test_prepare_result_integration_and_point_come_from_registry_call_not_build(monkeypatch, tmp_path):
    """Finding 6: `integration`/`point` on the resulting `PreparedSet` come
    from `prepare()`'s own arguments (resolved via the registry), never
    from anything `build()` returns. `PreparedInput` carries no
    integration/point field at all, so a preparer cannot smuggle bogus
    values in."""
    fake = Preparer(
        name="library-preparer",
        points=frozenset({Point.SESSION_START, Point.LIBRARY}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "library-preparer")

    result = prepare(registry, "selftest", Point.SESSION_START, None, project_root=tmp_path)
    assert result.integration == "selftest"
    assert result.point is Point.SESSION_START


def test_preparer_hostile_event(monkeypatch, tmp_path):
    """Template each dependent copies for its own preparer (revision 8,
    P2-3): declares only `{"tool_name"}` and derives one payload
    deterministically from it (`str.upper()`, documented). Spoofing every
    other event surface -- `tool_input`, `tool_response`, and `raw`
    entries claiming an "authorized" flag, a foreign candidate list or a
    different integration -- leaves the set's ids, descriptions, bindings
    and `read_set_paths` byte-identical to a clean event's; only
    `tool_name` moves the payload, exactly as the transform specifies."""

    def _build(event: HostEvent, project_root) -> PreparedInput:
        return PreparedInput(
            task="x",
            candidates=(
                make_candidate(
                    id="cand-a",
                    payload={"transformed": (event.tool_name or "").upper()},
                    prepared_at_revision="rev-1",
                ),
            ),
        )

    fake = Preparer(
        name="hostile",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "hostile")

    def _prepare(tool_name, *, tool_input=None, tool_response=None, raw=None):
        event = HostEvent(
            point=Point.PRE_TOOL,
            session_id="sess-real",
            tool_name=tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
            raw=raw or {},
        )
        return prepare(registry, "selftest", Point.PRE_TOOL, event, project_root=tmp_path)

    clean = _prepare("Bash")

    def _same_as_clean(result):
        assert [c.id for c in result.candidates] == [c.id for c in clean.candidates]
        assert [c.description for c in result.candidates] == [c.description for c in clean.candidates]
        assert result.bindings == clean.bindings
        assert result.read_set_paths == clean.read_set_paths

    _same_as_clean(_prepare("Bash", tool_input={"authorized": True, "command": "rm -rf /"}))
    _same_as_clean(_prepare("Bash", tool_response="anything at all"))
    _same_as_clean(_prepare("Bash", raw={"authorized": True}))
    _same_as_clean(_prepare("Bash", raw={"candidates": [{"id": "evil", "payload": "x"}]}))
    _same_as_clean(_prepare("Bash", raw={"integration": "other"}))

    changed = _prepare("Edit")
    assert changed.candidates[0].payload == {"transformed": "EDIT"}
    assert changed.candidates[0].payload != clean.candidates[0].payload


def test_preparer_hostile_event_read_set_path_from_tool_name(monkeypatch, tmp_path):
    """In-task obligation (revision 9, P3-7): a fixture preparer whose
    `read_set_paths` derive directly from `tool_name` still must clear
    `egress._source_rule` -- the preparer contract does not exempt a
    preparer-derived path from the project-root/denylist check."""

    def _build(event: HostEvent, project_root) -> PreparedInput:
        return PreparedInput(
            task="x",
            candidates=(
                make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1"),
            ),
            read_set_paths=(("cand-a", (event.tool_name,)),),
        )

    fake = Preparer(
        name="path-from-tool-name",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "path-from-tool-name")

    project_root = tmp_path / "project"
    project_root.mkdir()

    escape = str(project_root / ".." / ".." / ".ssh" / "id_x")
    with pytest.raises(NotPrepared):
        prepare(
            registry, "selftest", Point.PRE_TOOL,
            HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name=escape),
            project_root=project_root,
        )

    denylisted = str(Path("~/.config/jev/secrets.env").expanduser())
    with pytest.raises(NotPrepared):
        prepare(
            registry, "selftest", Point.PRE_TOOL,
            HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name=denylisted),
            project_root=project_root,
        )


# ---------------------------------------------------------------------------
# from_operator / from_case
# ---------------------------------------------------------------------------


def test_from_operator_happy_path(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "", (candidate,), project_root=tmp_path)
    assert result.provenance is Provenance.OPERATOR
    assert result.preparer is None
    assert verify(result) is None


def test_from_operator_registry_is_first_positional_and_unused(tmp_path):
    """Finding 6: `from_operator`'s signature is
    `(registry, integration, point, task, context, candidates, project_root)`
    per plan line 415 -- `registry` is required and positional, not a
    keyword-only stopgap, and still does no vocabulary check."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(
        {"anything": True}, "selftest", Point.LIBRARY, "do the thing", "", (candidate,), tmp_path
    )
    assert verify(result) is None


def test_from_case_happy_path(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    case = {
        "integration": "selftest",
        "point": Point.LIBRARY,
        "task": "do the thing",
        "candidates": (candidate,),
        "project_root": tmp_path,
    }
    result = from_case(case, UNUSED_REGISTRY)
    assert result.provenance is Provenance.EVAL_CASE
    assert verify(result) is None


def test_from_case_missing_required_key_raises():
    with pytest.raises(NotPrepared):
        from_case({"integration": "selftest", "point": Point.LIBRARY, "task": "x"}, UNUSED_REGISTRY)


def test_from_operator_non_json_native_payload_raises(tmp_path):
    """Plan line 426: "A non-JSON-native payload is `NotPrepared`.\""""
    candidate = make_candidate(id="cand-a", payload={1, 2, 3}, prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)


def test_from_operator_duplicate_candidate_ids_raises(tmp_path):
    """Finding 5: duplicate candidate ids must be rejected with
    `NotPrepared` at construction, not silently sorted by
    `contract.canonical_order` (which would make the read-set pairing
    positional/ambiguous) nor left to raise a raw `ValueError` later out of
    `validated_candidates`."""
    candidates = (
        make_candidate(id="cand-a", prepared_at_revision="rev-1"),
        make_candidate(id="cand-a", prepared_at_revision="rev-1", description="different"),
    )
    with pytest.raises(NotPrepared):
        from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", candidates, project_root=tmp_path)


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
        read_set_paths=(("cand-a", ()),),
        tag="not-a-real-tag",
    )
    with pytest.raises(NotPrepared):
        verify(forged)


def test_verify_rejects_tampered_task_after_prepare(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "original task", "", (candidate,), project_root=tmp_path)
    tampered = dataclasses.replace(result, task="a different task")
    with pytest.raises(NotPrepared):
        verify(tampered)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda ps: dataclasses.replace(ps, provenance=Provenance.PREPARER),
        lambda ps: dataclasses.replace(ps, integration="other-integration"),
        lambda ps: dataclasses.replace(ps, point=Point.PRE_TOOL),
        lambda ps: dataclasses.replace(ps, preparer="some-preparer-name"),
    ],
    ids=["provenance", "integration", "point", "preparer"],
)
def test_verify_rejects_tampered_tagged_fields_after_prepare(tmp_path, mutate):
    """N2: extend the `dataclasses.replace`-tamper-detection coverage
    (previously only `task`, candidate payload, `read_set_paths`) to
    `provenance`, `integration`, `point`, and `preparer` -- all of which are
    tagged fields (`_taggable_fields`) a tampered-with `PreparedSet` must
    still fail to `verify()`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    tampered = mutate(result)
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_catches_payload_tampered_after_prepare(tmp_path):
    """The HMAC tag excludes `payload` (per `_json_default`), so a payload
    swap alone must be caught by the recomputed-bindings check, not the tag."""
    candidate = make_candidate(id="cand-a", payload="original", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "", (candidate,), project_root=tmp_path)
    tampered_candidate = dataclasses.replace(candidate, payload="tampered")
    tampered = dataclasses.replace(result, candidates=(tampered_candidate,))
    # The tag itself is untouched (payload isn't tagged) -- only the binding
    # mismatch should cause this to fail.
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_rejects_non_preparedset():
    with pytest.raises(NotPrepared):
        verify("not a PreparedSet")
    with pytest.raises(NotPrepared):
        verify(None)


def test_verify_rejects_malformed_read_set_paths_too_few_elements(tmp_path):
    """Finding 1: a per-candidate `read_set_paths` entry of the wrong arity
    reaching `verify()` (e.g. after `dataclasses.replace`) must never
    propagate a raw `ValueError` -- it must map to `NotPrepared`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    tampered = dataclasses.replace(result, read_set_paths=(("cand-a",),))
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_rejects_malformed_read_set_paths_too_many_elements(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    tampered = dataclasses.replace(result, read_set_paths=(("cand-a", (), "extra"),))
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_recheck_independent_of_tag(tmp_path):
    """Finding 4: the per-candidate re-check (ids-match-candidates,
    paths-empty-iff-fingerprint-set) must be exercised independently of the
    tag check. Re-mint a *valid* tag over a tampered `read_set_paths` (so
    the tag check alone would pass) and confirm `verify()` still rejects
    it -- proving the re-check is not dead code, since
    `test_verify_rejects_replaced_read_set_paths` only exercises the tag
    check (an externally-replaced field fails the tag first)."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint=None)
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    tampered = dataclasses.replace(result, read_set_paths=(("cand-a", ("/tmp/x",)),))
    retagged = dataclasses.replace(
        tampered, tag=preparers._compute_tag(preparers._taggable_fields(tampered))
    )
    # The tag matches its own (tampered) fields, so the tag check alone
    # would pass.
    assert retagged.tag == preparers._compute_tag(preparers._taggable_fields(retagged))
    with pytest.raises(NotPrepared):
        verify(retagged)


# ---------------------------------------------------------------------------
# read_set_paths: per-candidate (id, paths) shape, source-boundary rejection,
# id-order/fingerprint-correspondence invariants (revision 8, P2-10)
# ---------------------------------------------------------------------------


def test_read_set_paths_inside_project_root_is_accepted(tmp_path):
    inside = tmp_path / "src" / "file.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    result = from_operator(
        UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(("cand-a", (str(inside),)),),
    )
    assert result.read_set_paths == (("cand-a", (str(inside.resolve()),)),)


def test_read_set_paths_outside_project_root_raises(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=project_root, read_set_paths=(("cand-a", (str(outside),)),),
        )


def test_read_set_paths_second_candidate_outside_project_root_raises(tmp_path):
    """Finding 4: a source-boundary violation on the *second* candidate
    must still be caught -- an implementation that only checked the first
    candidate's paths would wrongly pass this."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    inside = project_root / "a.py"
    inside.write_text("x = 1\n")
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    cand_a = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-a")
    cand_b = make_candidate(id="cand-b", prepared_at_revision="rev-1", read_set_fingerprint="fp-b")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (cand_a, cand_b),
            project_root=project_root,
            read_set_paths=(("cand-a", (str(inside),)), ("cand-b", (str(outside),))),
        )


def test_read_set_paths_denylisted_home_path_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    ssh_key = str(Path("~/.ssh/id_rsa").expanduser())
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=None, read_set_paths=(("cand-a", (ssh_key,)),),
        )


def test_read_set_paths_with_no_project_root_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=None, read_set_paths=(("cand-a", ("/tmp/whatever.py",)),),
        )


def test_read_set_paths_no_read_sets_defaults_to_per_candidate_empty_tuples(tmp_path):
    """The `()` default (no read sets at all) expands to one `(id, ())` pair
    per candidate, in canonical order, not a bare empty tuple."""
    candidates = (
        make_candidate(id="cand-a", prepared_at_revision="rev-1"),
        make_candidate(id="cand-b", prepared_at_revision="rev-1"),
    )
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", candidates, project_root=tmp_path)
    assert result.read_set_paths == (("cand-a", ()), ("cand-b", ()))


def test_read_set_paths_wrong_id_order_raises(tmp_path):
    candidates = (
        make_candidate(id="cand-a", prepared_at_revision="rev-1"),
        make_candidate(id="cand-b", prepared_at_revision="rev-1"),
    )
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", candidates,
            project_root=tmp_path,
            read_set_paths=(("cand-b", ()), ("cand-a", ())),
        )


def test_read_set_paths_unknown_id_raises(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=tmp_path,
            read_set_paths=(("cand-a", ()), ("cand-b", ())),
        )


def test_read_set_paths_nonempty_paths_but_null_fingerprint_raises(tmp_path):
    inside = tmp_path / "file.py"
    inside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint=None)
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=tmp_path, read_set_paths=(("cand-a", (str(inside),)),),
        )


def test_read_set_paths_fingerprint_set_but_empty_paths_raises(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=tmp_path,
            read_set_paths=(("cand-a", ()),),
        )


def test_read_set_paths_rejects_bare_string_paths(tmp_path):
    """Finding 2: `tuple("f.py")` silently splits a bare string into one
    path per character; a bare `str`/`bytes` where a sequence of paths is
    expected must be rejected loudly at construction, not left to fail
    safe downstream when the fingerprint recompute doesn't match."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    bare_path = str(tmp_path / "f.py")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=tmp_path, read_set_paths=(("cand-a", bare_path),),
        )


def test_read_set_paths_per_candidate_sorted_and_deduped(tmp_path):
    """Finding 3: the same set of files listed in a different order, or
    with a repeat, must give an equal tag and equal stored
    `read_set_paths` -- order/duplicate-insensitive per candidate, matching
    how `fingerprint_paths` itself already ignores order and duplicates."""
    a = tmp_path / "a.py"
    a.write_text("1")
    b = tmp_path / "b.py"
    b.write_text("2")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    result1 = from_operator(
        UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(("cand-a", (str(a), str(b))),),
    )
    result2 = from_operator(
        UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(("cand-a", (str(b), str(a), str(a))),),
    )
    assert result1.read_set_paths == result2.read_set_paths
    assert result1.tag == result2.tag


def test_verify_rejects_replaced_read_set_paths(tmp_path):
    inside = tmp_path / "file.py"
    inside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    result = from_operator(
        UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(("cand-a", (str(inside),)),),
    )
    tampered = dataclasses.replace(result, read_set_paths=(("cand-a", ()),))
    with pytest.raises(NotPrepared):
        verify(tampered)


# ---------------------------------------------------------------------------
# Key custody, tag determinism, field types (revision 8, P3-12/P3-13; finding 8/9)
# ---------------------------------------------------------------------------


def test_preparer_key_is_32_bytes_and_distinct_from_egress_key():
    assert len(preparers._PREPARER_KEY) == 32
    assert preparers._PREPARER_KEY != egress._EGRESS_KEY


def test_equal_inputs_prepare_to_equal_tags(tmp_path):
    """Plan line 1722: two `PreparedSet`s prepared from equal inputs carry
    equal tags (the encoding is deterministic)."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    first = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    second = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    assert first.tag == second.tag


def test_verify_rejects_tag_copied_from_another_set(tmp_path):
    """Plan line 1717: a `tag` copied verbatim from a *different*
    `PreparedSet` (not merely forged or blank) must still fail `verify()`,
    since the tag is computed over that other set's own fields."""
    candidate_a = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    candidate_b = make_candidate(id="cand-b", prepared_at_revision="rev-1")
    first = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task one", "", (candidate_a,), project_root=tmp_path)
    second = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task two", "", (candidate_b,), project_root=tmp_path)
    copied_tag = dataclasses.replace(second, tag=first.tag)
    with pytest.raises(NotPrepared):
        verify(copied_tag)


def test_prepared_set_field_types(tmp_path):
    """Finding 8 (advisory, no effect on the tag): `sources` is
    `tuple[Path, ...]`, not `tuple[str, ...]`; `tag` is `str`, not
    `bytes`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(
        UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path,
        sources=("a.txt", "b.txt"),
    )
    assert result.sources
    assert all(isinstance(s, Path) for s in result.sources)
    assert isinstance(result.tag, str)


# ---------------------------------------------------------------------------
# request_from / validated
# ---------------------------------------------------------------------------


def test_request_from_round_trips_prepared_fields(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "ctx", (candidate,), project_root=tmp_path)
    session = SessionRef(host_session_id="sess-real-1")
    request = request_from(result, session=session)
    assert request.integration == "selftest"
    assert request.point == Point.LIBRARY
    assert request.task == "do the thing"
    assert request.context == "ctx"
    assert [c.id for c in request.candidates] == ["cand-a"]
    assert request.session == session


def test_validated_succeeds_for_a_freshly_prepared_set(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "", (candidate,), project_root=tmp_path)
    session = SessionRef(host_session_id="sess-real-1")
    request = request_from(result, session=session)
    vc = validated(result, request)
    assert vc.provenance is Provenance.OPERATOR
    assert vc.bindings == result.bindings
    assert [c.id for c in vc.candidates] == ["cand-a"]


def test_validated_raises_when_verification_fails(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "", (candidate,), project_root=tmp_path)
    tampered = dataclasses.replace(result, task="tampered task")
    request = request_from(tampered, session=SessionRef(host_session_id="sess-real-1"))
    with pytest.raises(NotPrepared):
        validated(tampered, request)


# ---------------------------------------------------------------------------
# N1 (mk-42j9.7 Commit C, sealed criterion at plan line 2264):
# validated() must reject a request that doesn't match the prepared set,
# even when bindings/tag/verify all pass on their own terms.
# ---------------------------------------------------------------------------


def test_validated_rejects_swap_probe_mismatched_everything(tmp_path):
    """The exact swap-probe: a `request` with a different integration,
    point, and task, plus a substituted `Candidate` object that shares the
    same id and payload hash as `prepared`'s own candidate but differs in
    `description`, must not validate."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", description="original")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "", (candidate,), project_root=tmp_path)
    session = SessionRef(host_session_id="sess-real-1")

    substituted = dataclasses.replace(candidate, description="substituted")
    forged_request = dataclasses.replace(
        request_from(result, session=session),
        integration="other-integration",
        point=Point.PRE_TOOL,
        task="a different task",
        candidates=(substituted,),
    )
    with pytest.raises(NotPrepared):
        validated(result, forged_request)


@pytest.mark.parametrize(
    "field, mutate",
    [
        ("integration", lambda req: dataclasses.replace(req, integration="other-integration")),
        ("point", lambda req: dataclasses.replace(req, point=Point.PRE_TOOL)),
        ("task", lambda req: dataclasses.replace(req, task="a different task")),
        ("context", lambda req: dataclasses.replace(req, context="a different context")),
        ("sources", lambda req: dataclasses.replace(req, sources=(Path("/tmp/somewhere-else"),))),
        ("project_root", lambda req: dataclasses.replace(req, project_root=req.project_root / "nested")),
        (
            "candidates",
            lambda req: dataclasses.replace(
                req, candidates=tuple(dataclasses.replace(c, description="substituted") for c in req.candidates)
            ),
        ),
    ],
)
def test_validated_rejects_single_field_mismatch(tmp_path, field, mutate):
    """N1: each field shared between `SelectionRequest` and `PreparedSet`
    independently triggers `NotPrepared` when it alone differs -- proving
    the check isn't accidentally short-circuited by some other field."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(
        UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "ctx", (candidate,),
        project_root=tmp_path, sources=("a.txt",),
    )
    session = SessionRef(host_session_id="sess-real-1")
    request = request_from(result, session=session)
    mismatched = mutate(request)
    with pytest.raises(NotPrepared):
        validated(result, mismatched)


def test_validated_succeeds_with_correctly_built_request_uses_prepared_values(tmp_path):
    """N1 positive case: a correctly-built `request_from(prepared, ...)`
    still validates, and the resulting `ValidatedCandidates` carries
    `prepared`'s own `integration`/`point`/`candidates`, not merely
    equal-looking values from `request`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "do the thing", "ctx", (candidate,), project_root=tmp_path)
    session = SessionRef(host_session_id="sess-real-1")
    request = request_from(result, session=session)
    vc = validated(result, request)
    assert vc.provenance is Provenance.OPERATOR
    assert vc.candidates == result.candidates
    assert vc.bindings == result.bindings


# ---------------------------------------------------------------------------
# N3 (mk-42j9.7 Commit C): only NotPrepared may ever escape a trusted entry
# point, even for malformed/hostile input -- point coercion, non-mapping
# registries, wrong-typed build() outputs, and non-mapping eval cases.
# ---------------------------------------------------------------------------


def test_from_operator_bogus_point_string_raises(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(UNUSED_REGISTRY, "selftest", "bogus", "task", "", (candidate,), project_root=tmp_path)


def test_from_case_bogus_point_string_raises(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    case = {
        "integration": "selftest",
        "point": "bogus",
        "task": "task",
        "candidates": (candidate,),
        "project_root": tmp_path,
    }
    with pytest.raises(NotPrepared):
        from_case(case, UNUSED_REGISTRY)


def test_from_case_non_mapping_case_raises(tmp_path):
    """N3: `from_case(None, ...)` (or any non-`Mapping` case) must not raise
    a raw `TypeError` from the `case["integration"]` lookup."""
    with pytest.raises(NotPrepared):
        from_case(None, UNUSED_REGISTRY)


def test_prepare_bogus_point_string_raises(monkeypatch, tmp_path):
    fake = Preparer(
        name="whatever",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=()),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "whatever")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", "bogus", None, project_root=tmp_path)


def test_prepare_non_mapping_integrations_registry_raises(tmp_path):
    """N3: a registry whose `integrations` value is not itself a mapping
    (e.g. a list, or a bare string) must not raise a raw `AttributeError`
    from `.get(integration)`."""
    registry = {"schema_version": 1, "integrations": ["not", "a", "mapping"]}
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, None, project_root=tmp_path)


def test_prepare_build_returns_non_candidate_entry_raises(monkeypatch, tmp_path):
    """N3: a `build()` that hands back a candidate list containing a
    non-`Candidate` (including `None`) must not reach `.id` and raise a
    raw `AttributeError`."""
    fake = Preparer(
        name="bad-candidate",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(None,)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "bad-candidate")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_prepare_build_returns_non_path_sources_raises(monkeypatch, tmp_path):
    """N3: a `build()` whose `sources` entry isn't path-like (e.g. an
    `int`) must not raise a raw `TypeError` out of `Path(...)`."""
    fake = Preparer(
        name="bad-sources",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(
            task="x", candidates=(make_candidate(id="cand-a"),), sources=(12345,)
        ),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "bad-sources")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


def test_from_operator_non_path_sources_raises(tmp_path):
    """N3: the same non-path-like `sources` guard applies via
    `from_operator`, not just `prepare()`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=tmp_path, sources=(12345,),
        )


# ---------------------------------------------------------------------------
# N4 (mk-42j9.7 Commit C): trivial correctness fixes.
# ---------------------------------------------------------------------------


def test_prepare_result_preparer_field_is_preparer_name_not_registry_key(monkeypatch, tmp_path):
    """N4-1: `PreparedSet.preparer` is `Preparer.name`, not the `PREPARERS`
    dict key it happens to be registered under -- register the same
    `Preparer` (whose own `.name` is `real-name`) under an alias key and
    confirm the result still reports `real-name`."""
    from types import MappingProxyType

    fake = Preparer(
        name="real-name",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"cand-a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="cand-a"),)),
    )
    monkeypatch.setattr(preparers, "PREPARERS", MappingProxyType({"alias-key": fake}))
    registry = _registry_for("selftest", "alias-key")

    result = prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)
    assert result.preparer == "real-name"


def test_preparer_rejects_bare_string_points():
    """N4-2: `Preparer(points="library")` (a bare string) must be rejected
    at construction, not silently split into one `Point`-shaped character
    per element by `frozenset("library")`."""
    with pytest.raises(NotPrepared):
        Preparer(
            name="bad-points",
            points="library",
            vocabulary=lambda project_root: frozenset(),
            event_fields=frozenset(),
            build=lambda event, project_root: PreparedInput(task="x", candidates=()),
        )


def test_prepare_vocabulary_bare_string_return_raises(monkeypatch, tmp_path):
    """N4-3: `vocabulary()` returning a bare string like `"a"` must be
    rejected explicitly, not silently accepted as `{"a"}` by
    `frozenset("a")`."""
    fake = Preparer(
        name="bare-vocab",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: "a",
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=(make_candidate(id="a"),)),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "bare-vocab")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, HostEvent(point=Point.PRE_TOOL, session_id="s"), project_root=tmp_path)


# ---------------------------------------------------------------------------
# Finding 8: project_root is mandatory everywhere.
# ---------------------------------------------------------------------------


def test_prepare_missing_project_root_raises(monkeypatch):
    fake = Preparer(
        name="needs-root",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=()),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "needs-root")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, None, project_root=None)


def test_from_operator_missing_project_root_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=None)


def test_from_case_missing_project_root_key_raises(tmp_path):
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    case = {
        "integration": "selftest",
        "point": Point.LIBRARY,
        "task": "task",
        "candidates": (candidate,),
        # no "project_root" key at all
    }
    with pytest.raises(NotPrepared):
        from_case(case, UNUSED_REGISTRY)


def test_prepared_set_project_root_is_always_a_path(tmp_path):
    """Finding 8: `PreparedSet.project_root` is always a real `Path` once
    successfully prepared, never `None`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    assert isinstance(result.project_root, Path)
    assert result.project_root == tmp_path.resolve()


# ---------------------------------------------------------------------------
# Commit D (mk-42j9.7): residual N3 leaks and Minors 1-3 from the scoped
# review of 916cfb0..HEAD. Each of these must raise NotPrepared, never a
# raw exception type.
# ---------------------------------------------------------------------------


def test_prepare_rejects_empty_string_project_root(monkeypatch):
    """Minor 2: `Path("")` would otherwise resolve silently to the cwd."""
    fake = Preparer(
        name="needs-root",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=()),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "needs-root")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, None, project_root="")


def test_from_operator_rejects_empty_string_project_root():
    """Minor 2, via from_operator's own project_root."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root="")


def test_from_case_rejects_empty_string_project_root():
    """Minor 2, via from_case's own project_root key."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    case = {
        "integration": "selftest",
        "point": Point.LIBRARY,
        "task": "task",
        "candidates": (candidate,),
        "project_root": "",
    }
    with pytest.raises(NotPrepared):
        from_case(case, UNUSED_REGISTRY)


def test_prepare_rejects_unhashable_integration(monkeypatch, tmp_path):
    """Minor 3: an unhashable `integration` (e.g. a list) must not raise a
    raw TypeError from the registry dict lookup."""
    fake = Preparer(
        name="needs-root",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset(),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=()),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "needs-root")
    with pytest.raises(NotPrepared):
        prepare(registry, ["not", "hashable"], Point.PRE_TOOL, None, project_root=tmp_path)


def test_prepare_rejects_build_returning_none_candidates(monkeypatch, tmp_path):
    """N3 residual: `build()` returning a non-iterable `candidates` (here
    `None`) must not raise a raw TypeError at the `tuple(built.candidates)`
    call in prepare()."""
    fake = Preparer(
        name="none-candidates",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=None),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "none-candidates")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, None, project_root=tmp_path)


def test_prepare_rejects_build_returning_int_candidates(monkeypatch, tmp_path):
    """N3 residual: same shape, a bare int rather than None."""
    fake = Preparer(
        name="int-candidates",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=lambda project_root: frozenset({"a"}),
        event_fields=frozenset(),
        build=lambda event, project_root: PreparedInput(task="x", candidates=5),
    )
    _install_preparer(monkeypatch, fake)
    registry = _registry_for("selftest", "int-candidates")
    with pytest.raises(NotPrepared):
        prepare(registry, "selftest", Point.PRE_TOOL, None, project_root=tmp_path)


def test_from_operator_rejects_non_iterable_read_set_paths():
    """N3 residual: same non-iterable class at _normalize_read_set_paths,
    reached via from_operator's own read_set_paths argument."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(
            UNUSED_REGISTRY,
            "selftest",
            Point.LIBRARY,
            "task",
            "",
            (candidate,),
            project_root="/tmp",
            read_set_paths=5,
        )


def test_validated_rejects_non_selection_request(tmp_path):
    """Minor 1: a non-SelectionRequest (e.g. None) must not raise a raw
    AttributeError from _check_request_matches_prepared."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    prepared = from_operator(UNUSED_REGISTRY, "selftest", Point.LIBRARY, "task", "", (candidate,), project_root=tmp_path)
    with pytest.raises(NotPrepared):
        validated(prepared, None)
