"""Trusted preparers (mk-42j9.7 Task R6b).

Implements the plan's "Trusted preparers" subsection: a `Preparer` is a named,
point-scoped, vocabulary-bounded builder that turns a projected `HostEvent`
into candidates; `prepare()` looks it up in the (currently empty) `PREPARERS`
registry, projects the event down to only the fields the preparer declared,
and calls its `build`. `from_operator`/`from_case` are the two other trusted
entry points (a human operator, and the eval harness) that skip the
event-projection step but go through the same finishing logic. Every entry
point returns a `PreparedSet` carrying an HMAC `tag` (under a module-private,
per-process key distinct from `egress._EGRESS_KEY`) so a hand-built
`PreparedSet` cannot reach `validated()`/`authorize()` without going back
through `verify()`.

`from_external` (the revision-11 `select-json` external-stdin provenance) is
explicitly out of this task's scope -- only the `Provenance.EXTERNAL` member
exists so far; no factory produces it here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import clavain_selector.contract as contract
import clavain_selector.egress as egress
from clavain_selector.adapters.base import HostEvent
from clavain_selector.contract import (
    Candidate,
    Point,
    Provenance,
    SelectionRequest,
    SessionRef,
    ValidatedCandidates,
    payload_sha256,
)

# ---------------------------------------------------------------------------
# Key custody (revision 8, P3-12): generated once per process, at import
# time, independent of `egress._EGRESS_KEY` -- two module-private
# `secrets.token_bytes(32)` calls at import time of two different modules.
# ---------------------------------------------------------------------------

_PREPARER_KEY = secrets.token_bytes(32)

_EVENT_FIELD_NAMES = frozenset({"session_id", "tool_name", "tool_input", "tool_response"})


class NotPrepared(ValueError):
    """A `Preparer` could not build, or a `PreparedSet` failed to verify."""


@dataclass(frozen=True)
class Preparer:
    """A trusted, named builder for one or more points.

    `vocabulary`, when non-empty, is the closed set of candidate ids this
    preparer is allowed to emit; `event_fields` is a subset of
    `{"session_id", "tool_name", "tool_input", "tool_response"}` -- the only
    fields of the real `HostEvent` the preparer's `build` ever sees.
    """

    name: str
    points: frozenset[Point]
    vocabulary: frozenset[str]
    event_fields: frozenset[str]
    build: Callable[[HostEvent], Mapping[str, Any]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", frozenset(self.points))
        object.__setattr__(self, "vocabulary", frozenset(self.vocabulary))
        object.__setattr__(self, "event_fields", frozenset(self.event_fields))
        bad = self.event_fields - _EVENT_FIELD_NAMES
        if bad:
            raise NotPrepared(f"preparer {self.name!r} declares unknown event fields: {sorted(bad)}")


@dataclass(frozen=True)
class PreparedSet:
    """The trusted output of `prepare`/`from_operator`/`from_case`.

    Never constructed directly by callers other than this module; a
    hand-built instance still fails `verify()` because its `tag` cannot be
    forged without `_PREPARER_KEY`.
    """

    integration: str
    point: Point
    provenance: Provenance
    preparer: str | None
    task: str
    context: str
    candidates: tuple[Candidate, ...]
    sources: tuple[str, ...]
    project_root: Path | None
    task_revision: str
    bindings: tuple[tuple[str, str], ...]
    read_set_paths: tuple[str, ...]
    tag: bytes


class _FrozenPreparers(dict):
    """A `dict` subclass whose mutators always raise `TypeError`.

    Used only as the backing store for `PREPARERS` -- `MappingProxyType`
    would already refuse `PREPARERS["x"] = ...`, but wrapping the (currently
    empty) literal here keeps the type importable and the immutability
    explicit at the definition site.
    """

    def __setitem__(self, key, value):  # noqa: D105
        raise TypeError("PREPARERS is immutable")


PREPARERS: Mapping[str, Preparer] = MappingProxyType(_FrozenPreparers())


# ---------------------------------------------------------------------------
# Canonical JSON + HMAC tag (revision 8, P3-13)
# ---------------------------------------------------------------------------


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if isinstance(obj, Candidate):
        return {k: v for k, v in dataclasses.asdict(obj).items() if k != "payload"}
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"object of type {type(obj).__name__!r} is not canonical-JSON-able")


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def _taggable_fields(prepared: PreparedSet) -> dict[str, Any]:
    """Every `PreparedSet` field except `payload`s (dropped by `_json_default`
    on each `Candidate`) and `tag` itself."""
    return {
        "integration": prepared.integration,
        "point": prepared.point,
        "provenance": prepared.provenance,
        "preparer": prepared.preparer,
        "task": prepared.task,
        "context": prepared.context,
        "candidates": list(prepared.candidates),
        "sources": list(prepared.sources),
        "project_root": prepared.project_root,
        "task_revision": prepared.task_revision,
        "bindings": [list(b) for b in prepared.bindings],
        "read_set_paths": list(prepared.read_set_paths),
    }


def _compute_tag(fields: Mapping[str, Any]) -> bytes:
    body_sha256 = hashlib.sha256(_canonical_json_bytes(fields)).digest()
    return hmac.new(_PREPARER_KEY, body_sha256, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Event projection
# ---------------------------------------------------------------------------


def _project_event(point: Point, event: HostEvent | None, fields: frozenset[str]) -> HostEvent:
    values: dict[str, Any] = {
        "point": point,
        "session_id": "",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "raw": {},
    }
    if event is not None:
        for name in fields:
            values[name] = getattr(event, name)
    return HostEvent(**values)


# ---------------------------------------------------------------------------
# Shared finishing logic
# ---------------------------------------------------------------------------


def _finish_prepare(
    *,
    integration: str,
    point: Point,
    provenance: Provenance,
    preparer: str | None,
    task: str,
    context: str,
    candidates: Sequence[Candidate],
    sources: Sequence[str],
    project_root: str | Path | None,
    task_revision: str | None,
    read_set_paths: Sequence[str],
) -> PreparedSet:
    try:
        ordered = contract.canonical_order(tuple(candidates))
    except contract.NonCanonicalOrder as exc:
        raise NotPrepared(f"candidates could not be canonicalized: {exc}") from exc

    if task_revision is None:
        revisions = {c.prepared_at_revision for c in ordered}
        if len(revisions) != 1:
            raise NotPrepared("task_revision was not supplied and candidates do not agree on one")
        task_revision = next(iter(revisions))

    root = Path(project_root).resolve() if project_root is not None else None

    resolved_read_set: list[str] = []
    for raw_path in read_set_paths:
        real = os.path.realpath(str(raw_path))
        rule = egress._source_rule(Path(real), root)
        if rule is not None:
            raise NotPrepared(f"read_set_paths rejected ({rule}): {raw_path!r}")
        resolved_read_set.append(real)

    try:
        bindings = tuple((c.id, payload_sha256(c.payload)) for c in ordered)
    except ValueError as exc:
        raise NotPrepared(f"could not bind candidate payloads: {exc}") from exc

    prelim = PreparedSet(
        integration=integration,
        point=point,
        provenance=provenance,
        preparer=preparer,
        task=task,
        context=context,
        candidates=ordered,
        sources=tuple(sources),
        project_root=root,
        task_revision=task_revision,
        bindings=bindings,
        read_set_paths=tuple(resolved_read_set),
        tag=b"",
    )
    tag = _compute_tag(_taggable_fields(prelim))
    return dataclasses.replace(prelim, tag=tag)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def prepare(name: str, event: HostEvent | None, *, project_root: str | Path | None = None) -> PreparedSet:
    """Build a `PreparedSet` via the named, registered `Preparer`.

    Raises `NotPrepared` when `name` is not in `PREPARERS`, when `event`'s
    point is not one the preparer serves, when the preparer's `build` omits
    a required key or raises, when a produced candidate id is outside a
    non-empty `vocabulary`, or when any `read_set_paths` entry resolves
    outside `project_root` or onto the source denylist.
    """
    preparer_def = PREPARERS.get(name)
    if preparer_def is None:
        raise NotPrepared(f"unknown preparer: {name!r}")
    if event is not None and event.point not in preparer_def.points:
        raise NotPrepared(f"preparer {name!r} does not serve point {event.point!r}")

    point = event.point if event is not None else next(iter(preparer_def.points), Point.LIBRARY)
    projected = _project_event(point, event, preparer_def.event_fields)

    try:
        built = dict(preparer_def.build(projected))
    except NotPrepared:
        raise
    except Exception as exc:  # noqa: BLE001 - any preparer failure means NotPrepared
        raise NotPrepared(f"preparer {name!r} build failed: {exc}") from exc

    try:
        candidates = tuple(built["candidates"])
        task = built["task"]
    except KeyError as exc:
        raise NotPrepared(f"preparer {name!r} build did not return {exc.args[0]!r}") from exc

    if preparer_def.vocabulary:
        outside = [c.id for c in candidates if c.id not in preparer_def.vocabulary]
        if outside:
            raise NotPrepared(f"preparer {name!r} emitted candidates outside its vocabulary: {outside}")

    return _finish_prepare(
        integration=built.get("integration", ""),
        point=built.get("point", point),
        provenance=Provenance.PREPARER,
        preparer=name,
        task=task,
        context=built.get("context", ""),
        candidates=candidates,
        sources=built.get("sources", ()),
        project_root=project_root if project_root is not None else built.get("project_root"),
        task_revision=built.get("task_revision"),
        read_set_paths=built.get("read_set_paths", ()),
    )


def from_operator(
    integration: str,
    point: Point,
    task: str,
    context: str,
    candidates: Sequence[Candidate],
    project_root: str | Path | None = None,
    *,
    sources: Sequence[str] = (),
    read_set_paths: Sequence[str] = (),
    task_revision: str | None = None,
) -> PreparedSet:
    """Build a `PreparedSet` on behalf of a human operator (no preparer, no event)."""
    return _finish_prepare(
        integration=integration,
        point=point,
        provenance=Provenance.OPERATOR,
        preparer=None,
        task=task,
        context=context,
        candidates=candidates,
        sources=sources,
        project_root=project_root,
        task_revision=task_revision,
        read_set_paths=read_set_paths,
    )


def from_case(case: Mapping[str, Any], registry: Mapping[str, Any] | None = None) -> PreparedSet:
    """Build a `PreparedSet` from one eval-harness case mapping (Task 9).

    `registry` is accepted but currently unused -- reserved for a future
    per-integration validation pass; `case` must supply `integration`,
    `point`, `task`, `candidates`, with `context`/`sources`/`read_set_paths`/
    `project_root`/`task_revision`/`preparer` optional.
    """
    del registry
    try:
        integration = case["integration"]
        point = case["point"]
        task = case["task"]
        candidates = case["candidates"]
    except KeyError as exc:
        raise NotPrepared(f"eval case is missing required key {exc.args[0]!r}") from exc

    return _finish_prepare(
        integration=integration,
        point=point,
        provenance=Provenance.EVAL_CASE,
        preparer=case.get("preparer"),
        task=task,
        context=case.get("context", ""),
        candidates=candidates,
        sources=case.get("sources", ()),
        project_root=case.get("project_root"),
        task_revision=case.get("task_revision"),
        read_set_paths=case.get("read_set_paths", ()),
    )


def verify(prepared: PreparedSet) -> bool:
    """Recompute the tag and independently recompute the payload bindings.

    The tag alone would not catch a `payload` mutated in place after
    preparation (a `Candidate`'s dict-encoding for tagging excludes
    `payload`), so this also rebuilds `bindings` from the live candidates
    and requires an exact match.
    """
    if not isinstance(prepared, PreparedSet):
        return False
    try:
        expected_tag = _compute_tag(_taggable_fields(prepared))
    except TypeError:
        return False
    if not isinstance(prepared.tag, (bytes, bytearray)) or not hmac.compare_digest(expected_tag, bytes(prepared.tag)):
        return False
    try:
        recomputed = tuple((c.id, payload_sha256(c.payload)) for c in prepared.candidates)
    except ValueError:
        return False
    return recomputed == prepared.bindings


def request_from(prepared: PreparedSet, *, session: SessionRef) -> SelectionRequest:
    """The `SelectionRequest` a `PreparedSet` describes, for one host session."""
    return SelectionRequest(
        integration=prepared.integration,
        point=prepared.point,
        task=prepared.task,
        context=prepared.context,
        candidates=prepared.candidates,
        task_revision=prepared.task_revision,
        session=session,
        sources=tuple(Path(s) for s in prepared.sources),
        project_root=prepared.project_root,
    )


def validated(prepared: PreparedSet, *, session: SessionRef) -> ValidatedCandidates:
    """`verify()` then bind: the only path from a `PreparedSet` to `ValidatedCandidates`."""
    if not verify(prepared):
        raise NotPrepared("PreparedSet failed verification")
    request = request_from(prepared, session=session)
    return contract.validated_candidates(request, bindings=prepared.bindings, provenance=prepared.provenance)
