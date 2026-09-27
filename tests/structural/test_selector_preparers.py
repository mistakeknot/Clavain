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
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from selector_helpers import make_candidate, selector_socket_guard  # noqa: F401

import clavain_selector.egress as egress
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
    from types import MappingProxyType

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
    assert verify(result) is None


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


def test_preparer_hostile_event(monkeypatch):
    """Template each dependent copies for its own preparer (revision 8,
    P2-3): declares only `{"tool_name"}` and derives one payload
    deterministically from it (`str.upper()`, documented). Spoofing every
    other event surface -- `tool_input`, `tool_response`, and `raw`
    entries claiming an "authorized" flag, a foreign candidate list or a
    different integration -- leaves the set's ids, descriptions, bindings
    and `read_set_paths` byte-identical to a clean event's; only
    `tool_name` moves the payload, exactly as the transform specifies."""

    def _build(event: HostEvent) -> dict:
        return {
            "task": "x",
            "candidates": (
                make_candidate(
                    id="cand-a",
                    payload={"transformed": (event.tool_name or "").upper()},
                    prepared_at_revision="rev-1",
                ),
            ),
        }

    fake = Preparer(
        name="hostile",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)

    def _prepare(tool_name, *, tool_input=None, tool_response=None, raw=None):
        event = HostEvent(
            point=Point.PRE_TOOL,
            session_id="sess-real",
            tool_name=tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
            raw=raw or {},
        )
        return prepare("hostile", event)

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

    def _build(event: HostEvent) -> dict:
        return {
            "task": "x",
            "candidates": (
                make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1"),
            ),
            "read_set_paths": (("cand-a", (event.tool_name,)),),
        }

    fake = Preparer(
        name="path-from-tool-name",
        points=frozenset({Point.PRE_TOOL}),
        vocabulary=frozenset(),
        event_fields=frozenset({"tool_name"}),
        build=_build,
    )
    _install_preparer(monkeypatch, fake)

    project_root = tmp_path / "project"
    project_root.mkdir()

    escape = str(project_root / ".." / ".." / ".ssh" / "id_x")
    with pytest.raises(NotPrepared):
        prepare(
            "path-from-tool-name",
            HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name=escape),
            project_root=project_root,
        )

    denylisted = str(Path("~/.config/jev/secrets.env").expanduser())
    with pytest.raises(NotPrepared):
        prepare(
            "path-from-tool-name",
            HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name=denylisted),
            project_root=project_root,
        )


# ---------------------------------------------------------------------------
# from_operator / from_case
# ---------------------------------------------------------------------------


def test_from_operator_happy_path():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
    assert result.provenance is Provenance.OPERATOR
    assert result.preparer is None
    assert verify(result) is None


def test_from_operator_accepts_registry_kwarg():
    """Finding 7: `from_operator` needs a `registry` parameter per the
    plan, even though this task does not need it to do anything yet
    (finding 6's registry-driven `prepare()` rewrite is a follow-on
    commit)."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(
        "selftest", Point.LIBRARY, "do the thing", "", (candidate,), registry={"anything": True}
    )
    assert verify(result) is None


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
    assert verify(result) is None


def test_from_case_missing_required_key_raises():
    with pytest.raises(NotPrepared):
        from_case({"integration": "selftest", "point": Point.LIBRARY, "task": "x"})


def test_from_operator_non_json_native_payload_raises():
    """Plan line 426: "A non-JSON-native payload is `NotPrepared`.\""""
    candidate = make_candidate(id="cand-a", payload={1, 2, 3}, prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator("selftest", Point.LIBRARY, "task", "", (candidate,))


def test_from_operator_duplicate_candidate_ids_raises():
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
        from_operator("selftest", Point.LIBRARY, "task", "", candidates)


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


def test_verify_rejects_tampered_task_after_prepare():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "original task", "", (candidate,))
    tampered = dataclasses.replace(result, task="a different task")
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_catches_payload_tampered_after_prepare():
    """The HMAC tag excludes `payload` (per `_json_default`), so a payload
    swap alone must be caught by the recomputed-bindings check, not the tag."""
    candidate = make_candidate(id="cand-a", payload="original", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
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


def test_verify_rejects_malformed_read_set_paths_too_few_elements():
    """Finding 1: a per-candidate `read_set_paths` entry of the wrong arity
    reaching `verify()` (e.g. after `dataclasses.replace`) must never
    propagate a raw `ValueError` -- it must map to `NotPrepared`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "task", "", (candidate,))
    tampered = dataclasses.replace(result, read_set_paths=(("cand-a",),))
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_rejects_malformed_read_set_paths_too_many_elements():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "task", "", (candidate,))
    tampered = dataclasses.replace(result, read_set_paths=(("cand-a", (), "extra"),))
    with pytest.raises(NotPrepared):
        verify(tampered)


def test_verify_recheck_independent_of_tag():
    """Finding 4: the per-candidate re-check (ids-match-candidates,
    paths-empty-iff-fingerprint-set) must be exercised independently of the
    tag check. Re-mint a *valid* tag over a tampered `read_set_paths` (so
    the tag check alone would pass) and confirm `verify()` still rejects
    it -- proving the re-check is not dead code, since
    `test_verify_rejects_replaced_read_set_paths` only exercises the tag
    check (an externally-replaced field fails the tag first)."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint=None)
    result = from_operator("selftest", Point.LIBRARY, "task", "", (candidate,))
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
        "selftest", Point.LIBRARY, "task", "", (candidate,),
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
            "selftest", Point.LIBRARY, "task", "", (candidate,),
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
            "selftest", Point.LIBRARY, "task", "", (cand_a, cand_b),
            project_root=project_root,
            read_set_paths=(("cand-a", (str(inside),)), ("cand-b", (str(outside),))),
        )


def test_read_set_paths_denylisted_home_path_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    ssh_key = str(Path("~/.ssh/id_rsa").expanduser())
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=None, read_set_paths=(("cand-a", (ssh_key,)),),
        )


def test_read_set_paths_with_no_project_root_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=None, read_set_paths=(("cand-a", ("/tmp/whatever.py",)),),
        )


def test_read_set_paths_no_read_sets_defaults_to_per_candidate_empty_tuples():
    """The `()` default (no read sets at all) expands to one `(id, ())` pair
    per candidate, in canonical order, not a bare empty tuple."""
    candidates = (
        make_candidate(id="cand-a", prepared_at_revision="rev-1"),
        make_candidate(id="cand-b", prepared_at_revision="rev-1"),
    )
    result = from_operator("selftest", Point.LIBRARY, "task", "", candidates)
    assert result.read_set_paths == (("cand-a", ()), ("cand-b", ()))


def test_read_set_paths_wrong_id_order_raises():
    candidates = (
        make_candidate(id="cand-a", prepared_at_revision="rev-1"),
        make_candidate(id="cand-b", prepared_at_revision="rev-1"),
    )
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", candidates,
            read_set_paths=(("cand-b", ()), ("cand-a", ())),
        )


def test_read_set_paths_unknown_id_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            read_set_paths=(("cand-a", ()), ("cand-b", ())),
        )


def test_read_set_paths_nonempty_paths_but_null_fingerprint_raises(tmp_path):
    inside = tmp_path / "file.py"
    inside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint=None)
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
            project_root=tmp_path, read_set_paths=(("cand-a", (str(inside),)),),
        )


def test_read_set_paths_fingerprint_set_but_empty_paths_raises():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    with pytest.raises(NotPrepared):
        from_operator(
            "selftest", Point.LIBRARY, "task", "", (candidate,),
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
            "selftest", Point.LIBRARY, "task", "", (candidate,),
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
        "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(("cand-a", (str(a), str(b))),),
    )
    result2 = from_operator(
        "selftest", Point.LIBRARY, "task", "", (candidate,),
        project_root=tmp_path, read_set_paths=(("cand-a", (str(b), str(a), str(a))),),
    )
    assert result1.read_set_paths == result2.read_set_paths
    assert result1.tag == result2.tag


def test_verify_rejects_replaced_read_set_paths(tmp_path):
    inside = tmp_path / "file.py"
    inside.write_text("x = 1\n")
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1")
    result = from_operator(
        "selftest", Point.LIBRARY, "task", "", (candidate,),
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


def test_equal_inputs_prepare_to_equal_tags():
    """Plan line 1722: two `PreparedSet`s prepared from equal inputs carry
    equal tags (the encoding is deterministic)."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    first = from_operator("selftest", Point.LIBRARY, "task", "", (candidate,))
    second = from_operator("selftest", Point.LIBRARY, "task", "", (candidate,))
    assert first.tag == second.tag


def test_prepared_set_field_types():
    """Finding 8 (advisory, no effect on the tag): `sources` is
    `tuple[Path, ...]`, not `tuple[str, ...]`; `tag` is `str`, not
    `bytes`."""
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator(
        "selftest", Point.LIBRARY, "task", "", (candidate,),
        sources=("a.txt", "b.txt"),
    )
    assert result.sources
    assert all(isinstance(s, Path) for s in result.sources)
    assert isinstance(result.tag, str)


@pytest.mark.skip(
    reason=(
        "Plan line 1717 ('the vocabulary function is called with "
        "project_root only (spy)') requires Preparer.vocabulary to be a "
        "Callable[[Path], frozenset[str]] (plan line 391). That shape "
        "lands with finding 6's registry-driven prepare() rewrite "
        "(a separate, follow-on commit) -- .7's Preparer.vocabulary is "
        "still a plain frozenset here. Un-skip and rewrite this test to "
        "call the callable vocabulary with project_root once that lands."
    )
)
def test_prepare_calls_vocabulary_with_project_root_only():
    pass


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
    request = request_from(result, session=session)
    vc = validated(result, request)
    assert vc.provenance is Provenance.OPERATOR
    assert vc.bindings == result.bindings
    assert [c.id for c in vc.candidates] == ["cand-a"]


def test_validated_raises_when_verification_fails():
    candidate = make_candidate(id="cand-a", prepared_at_revision="rev-1")
    result = from_operator("selftest", Point.LIBRARY, "do the thing", "", (candidate,))
    tampered = dataclasses.replace(result, task="tampered task")
    request = request_from(tampered, session=SessionRef(host_session_id="sess-real-1"))
    with pytest.raises(NotPrepared):
        validated(tampered, request)
