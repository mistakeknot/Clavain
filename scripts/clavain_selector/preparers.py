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
class PreparedInput:
    """What `Preparer.build` returns: task, context, candidates, read-set
    paths, sources and task_revision only (finding 6, mk-42j9.7).

    Deliberately carries no `integration`/`point` -- those always come from
    the `prepare()` call's own registry-resolved arguments, never from
    whatever a preparer's `build` happens to return, so a preparer cannot
    smuggle a different integration or point into the resulting
    `PreparedSet`.
    """

    task: str
    candidates: Sequence[Candidate]
    context: str = ""
    read_set_paths: Sequence[tuple[str, Sequence[str]]] = ()
    sources: Sequence[str] = ()
    task_revision: str | None = None


@dataclass(frozen=True)
class Preparer:
    """A trusted, named builder for one or more points.

    `vocabulary(project_root)` is the closed set of candidate ids this
    preparer is allowed to emit for that project root -- it never sees the
    event, and an empty result means an empty closed set (every id is
    rejected), not "no restriction". `event_fields` is a subset of
    `{"session_id", "tool_name", "tool_input", "tool_response"}` -- the only
    fields of the real `HostEvent` the preparer's `build` ever sees.
    """

    name: str
    points: frozenset[Point]
    vocabulary: Callable[[Path], frozenset[str]]
    event_fields: frozenset[str]
    build: Callable[[HostEvent | None, Path | None], PreparedInput]

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", frozenset(self.points))
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
    sources: tuple[Path, ...]
    # Per the plan's landed shape (revision 8/9), `project_root` is `Path`
    # (required) once `prepare()`'s registry-driven rewrite (finding 6,
    # follow-on commit) makes it a mandatory parameter everywhere. Until
    # then this task's entry points still accept `project_root=None` for
    # callers with no read sets at all; `_finish_prepare` fails closed
    # (`NotPrepared`) the moment any candidate carries a non-empty
    # `read_set_paths` entry with no `project_root` to bound it (also
    # enforced transitively by `egress._source_rule`).
    project_root: Path | None
    task_revision: str
    bindings: tuple[tuple[str, str], ...]
    read_set_paths: tuple[tuple[str, tuple[str, ...]], ...]
    tag: str


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
        "read_set_paths": [[cid, list(paths)] for cid, paths in prepared.read_set_paths],
    }


def _compute_tag(fields: Mapping[str, Any]) -> str:
    body_sha256 = hashlib.sha256(_canonical_json_bytes(fields)).digest()
    return hmac.new(_PREPARER_KEY, body_sha256, hashlib.sha256).hexdigest()


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


def _normalize_read_set_paths(
    read_set_paths: Sequence[tuple[str, Sequence[str]]],
    ordered: Sequence[Candidate],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Fill in the per-candidate `(id, paths)` shape the plan requires.

    An empty `read_set_paths` (the default for callers with no read sets at
    all) is shorthand for "every candidate has an empty read set" -- it
    expands to `(id, ())` for every candidate in canonical order. A
    non-empty `read_set_paths` must already carry exactly the candidates'
    ids, in canonical order; any other shape is `NotPrepared` (revision 8,
    P2-10).
    """
    expected_ids = tuple(c.id for c in ordered)
    if not read_set_paths:
        return tuple((cid, ()) for cid in expected_ids)

    normalized: list[tuple[str, tuple[str, ...]]] = []
    for entry in read_set_paths:
        try:
            cid, paths = entry
        except (TypeError, ValueError) as exc:
            raise NotPrepared(f"read_set_paths entry is not an (id, paths) pair: {entry!r}") from exc
        if isinstance(paths, (str, bytes)):
            # `tuple("f.py")` silently splits a bare string into one path
            # per character; reject the shape outright instead of letting
            # that happen (revision 8, P2-10 finding 2).
            raise NotPrepared(
                f"read_set_paths for {cid!r} must be a sequence of paths, not a bare "
                f"{type(paths).__name__}: {paths!r}"
            )
        try:
            path_tuple = tuple(paths)
        except TypeError as exc:
            raise NotPrepared(f"read_set_paths for {cid!r} is not iterable: {paths!r}") from exc
        normalized.append((cid, path_tuple))

    got_ids = tuple(cid for cid, _ in normalized)
    if got_ids != expected_ids:
        raise NotPrepared(
            f"read_set_paths ids {list(got_ids)!r} do not match candidates "
            f"{list(expected_ids)!r} in canonical order"
        )
    return tuple(normalized)


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
    read_set_paths: Sequence[tuple[str, Sequence[str]]],
) -> PreparedSet:
    candidates = tuple(candidates)
    ids = [c.id for c in candidates]
    if len(ids) != len(set(ids)):
        # `contract.canonical_order` sorts duplicates rather than rejecting
        # them, which would make the read-set pairing positional/ambiguous
        # and let a raw `ValueError` from `validated_candidates` reach a
        # caller downstream instead of `NotPrepared` (revision 8, finding
        # 5). Reject here, before any candidate ever reaches
        # `canonical_order`.
        dupes = sorted({cid for cid in ids if ids.count(cid) > 1})
        raise NotPrepared(f"duplicate candidate ids: {dupes}")

    try:
        ordered = contract.canonical_order(candidates)
    except contract.NonCanonicalOrder as exc:
        raise NotPrepared(f"candidates could not be canonicalized: {exc}") from exc
    except ValueError as exc:
        # `canonical_order`'s sort key hashes each candidate's payload
        # (`payload_sha256`), so a non-JSON-native payload surfaces here as
        # a raw `ValueError` before `_finish_prepare` ever reaches its own
        # `payload_sha256` call below (revision 8, finding 1/8: no raw
        # exception should ever reach a caller of a trusted entry point).
        raise NotPrepared(f"could not canonicalize candidates: {exc}") from exc

    if task_revision is None:
        revisions = {c.prepared_at_revision for c in ordered}
        if len(revisions) != 1:
            raise NotPrepared("task_revision was not supplied and candidates do not agree on one")
        task_revision = next(iter(revisions))

    root = Path(project_root).resolve() if project_root is not None else None

    normalized_read_set = _normalize_read_set_paths(read_set_paths, ordered)

    if root is None and any(paths for _, paths in normalized_read_set):
        # Fails closed explicitly rather than relying only on
        # `egress._source_rule` always returning `src.outside_project` for
        # a `None` root (revision 8, finding 8): a missing project root
        # with any non-empty read-set paths is `NotPrepared`, never a
        # silently permissive or silently all-rejecting state.
        raise NotPrepared("read_set_paths requires a project_root")

    resolved_pairs: list[tuple[str, tuple[str, ...]]] = []
    for candidate, (cid, paths) in zip(ordered, normalized_read_set):
        has_fingerprint = candidate.read_set_fingerprint is not None
        if bool(paths) != has_fingerprint:
            raise NotPrepared(
                f"candidate {cid!r} read_set_paths emptiness ({bool(paths)}) does not match "
                f"read_set_fingerprint being set ({has_fingerprint})"
            )
        resolved_paths: list[str] = []
        for raw_path in paths:
            real = os.path.realpath(str(raw_path))
            rule = egress._source_rule(Path(real), root)
            if rule is not None:
                raise NotPrepared(f"read_set_paths rejected ({rule}): {raw_path!r}")
            resolved_paths.append(real)
        # Order/duplicate-insensitive per candidate, matching how
        # `fingerprint_paths` itself already ignores order and duplicates
        # (revision 8, finding 3): two sets prepared from equal inputs,
        # differently ordered or with a repeat, carry equal tags.
        resolved_pairs.append((cid, tuple(sorted(set(resolved_paths)))))

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
        sources=tuple(Path(s) for s in sources),
        project_root=root,
        task_revision=task_revision,
        bindings=bindings,
        read_set_paths=tuple(resolved_pairs),
        tag="",
    )
    tag = _compute_tag(_taggable_fields(prelim))
    return dataclasses.replace(prelim, tag=tag)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def prepare(
    registry: Mapping[str, Any],
    integration: str,
    point: "Point | str",
    event: HostEvent | None,
    project_root: str | Path | None = None,
) -> PreparedSet:
    """Build a `PreparedSet` via the registry-resolved, registered `Preparer`.

    `registry` is the loaded integration registry (the same
    `Mapping[str, Any]` shape `flags.py` already reads: a `dict` with an
    `integrations` mapping from integration name to an entry `dict` whose
    `"preparer"` key names an entry in `PREPARERS`). Looks up
    `registry["integrations"][integration]["preparer"]` in `PREPARERS`
    (an unknown integration or preparer name is `NotPrepared`) and requires
    `point in preparer.points` -- this check is always required, including
    when `event is None`; there is no fallback that picks a point from
    `preparer.points`. Projects `event` down to only the fields
    `preparer.event_fields` declares (every other field is `None`, `raw` is
    `{}`) and calls `preparer.build(projected, project_root)`. Every
    produced candidate id must be in `preparer.vocabulary(project_root)`;
    an empty result from that call is an empty closed set -- every
    candidate id is rejected, not "no restriction". `integration`/`point`
    on the resulting `PreparedSet` always come from this call's own
    arguments, never from anything `build()` returns (`PreparedInput`
    carries no such fields). Also raises `NotPrepared` when
    `read_set_paths` (a per-candidate `(id, paths)` sequence in canonical
    order, or `()` when no candidate has a read set) does not correspond to
    the candidates or disagrees with a candidate's `read_set_fingerprint`,
    or when any candidate's path resolves outside `project_root` or onto
    the source denylist.
    """
    point_value = point if isinstance(point, Point) else Point(point)

    integrations = registry.get("integrations", {}) if isinstance(registry, Mapping) else {}
    entry = integrations.get(integration)
    if not isinstance(entry, Mapping):
        raise NotPrepared(f"unknown integration: {integration!r}")

    preparer_name = entry.get("preparer")
    if not isinstance(preparer_name, str):
        raise NotPrepared(f"integration {integration!r} has no registered preparer")

    preparer_def = PREPARERS.get(preparer_name)
    if preparer_def is None:
        raise NotPrepared(f"unknown preparer: {preparer_name!r}")

    if point_value not in preparer_def.points:
        raise NotPrepared(f"preparer {preparer_name!r} does not serve point {point_value!r}")

    root_arg = Path(project_root) if project_root is not None else None
    projected = _project_event(point_value, event, preparer_def.event_fields)

    try:
        built = preparer_def.build(projected, root_arg)
    except NotPrepared:
        raise
    except Exception as exc:  # noqa: BLE001 - any preparer failure means NotPrepared
        raise NotPrepared(f"preparer {preparer_name!r} build failed: {exc}") from exc

    if not isinstance(built, PreparedInput):
        raise NotPrepared(f"preparer {preparer_name!r} build did not return a PreparedInput")

    try:
        vocabulary = frozenset(preparer_def.vocabulary(root_arg))
    except NotPrepared:
        raise
    except Exception as exc:  # noqa: BLE001 - any preparer failure means NotPrepared
        raise NotPrepared(f"preparer {preparer_name!r} vocabulary failed: {exc}") from exc

    candidates = tuple(built.candidates)
    outside = [c.id for c in candidates if c.id not in vocabulary]
    if outside:
        raise NotPrepared(f"preparer {preparer_name!r} emitted candidates outside its vocabulary: {outside}")

    return _finish_prepare(
        integration=integration,
        point=point_value,
        provenance=Provenance.PREPARER,
        preparer=preparer_name,
        task=built.task,
        context=built.context,
        candidates=candidates,
        sources=built.sources,
        project_root=project_root,
        task_revision=built.task_revision,
        read_set_paths=built.read_set_paths,
    )


def from_operator(
    registry: Mapping[str, Any],
    integration: str,
    point: Point,
    task: str,
    context: str,
    candidates: Sequence[Candidate],
    project_root: str | Path | None = None,
    *,
    sources: Sequence[str] = (),
    read_set_paths: Sequence[tuple[str, Sequence[str]]] = (),
    task_revision: str | None = None,
) -> PreparedSet:
    """Build a `PreparedSet` on behalf of a human operator (no preparer, no event).

    `read_set_paths` is a per-candidate `(id, paths)` sequence, in the same
    canonical order as `candidates`; `()` means no candidate has a read set.

    `registry` is accepted, as the plan's signature requires (line 415),
    but unused -- there is no vocabulary check for operator-provided sets
    (plan line 430).
    """
    del registry
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


def from_case(case: Mapping[str, Any], registry: Mapping[str, Any]) -> PreparedSet:
    """Build a `PreparedSet` from one eval-harness case mapping (Task 9).

    `registry` is accepted, per the plan's signature (line 416), but
    unused -- no vocabulary check applies to eval-case sets either. `case`
    must supply `integration`,
    `point`, `task`, `candidates`, with `context`/`sources`/`read_set_paths`/
    `project_root`/`task_revision`/`preparer` optional. `read_set_paths`, if
    given, is a per-candidate `(id, paths)` sequence in canonical order.
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


def verify(prepared: PreparedSet) -> None:
    """Recompute the tag and independently recompute the payload bindings.

    Raises `NotPrepared` unless every check passes; returns `None` on
    success (plan line 421). Never propagates a raw exception -- every
    exception the tag-computation or re-check path can raise from
    malformed input (at minimum `TypeError` and `ValueError`, e.g. a
    per-candidate `read_set_paths` entry of the wrong arity) is caught and
    mapped to `NotPrepared` (revision 8, P2-10, finding 1).

    The tag alone would not catch a `payload` mutated in place after
    preparation (a `Candidate`'s dict-encoding for tagging excludes
    `payload`), so this also rebuilds `bindings` from the live candidates
    and requires an exact match. `read_set_paths` is itself part of the
    tagged fields (so a replaced entry already fails the tag check), but
    this also re-checks, independently of the tag, that its ids still
    correspond to `candidates` in canonical order and that each candidate's
    paths are empty exactly when its `read_set_fingerprint` is `None`
    (revision 8, P2-10).
    """
    if not isinstance(prepared, PreparedSet):
        raise NotPrepared(f"not a PreparedSet: {prepared!r}")
    try:
        expected_tag = _compute_tag(_taggable_fields(prepared))
    except (TypeError, ValueError) as exc:
        raise NotPrepared(f"could not compute tag for PreparedSet: {exc}") from exc
    if not isinstance(prepared.tag, str) or not hmac.compare_digest(expected_tag, prepared.tag):
        raise NotPrepared("PreparedSet tag does not verify")
    try:
        recomputed = tuple((c.id, payload_sha256(c.payload)) for c in prepared.candidates)
    except ValueError as exc:
        raise NotPrepared(f"could not recompute payload bindings: {exc}") from exc
    if recomputed != prepared.bindings:
        raise NotPrepared("PreparedSet bindings do not match recomputed payload hashes")
    try:
        expected_ids = tuple(c.id for c in prepared.candidates)
        got_ids = tuple(cid for cid, _ in prepared.read_set_paths)
    except (TypeError, ValueError) as exc:
        raise NotPrepared(f"malformed read_set_paths: {exc}") from exc
    if got_ids != expected_ids:
        raise NotPrepared("read_set_paths ids do not match candidates in canonical order")
    for candidate, (_, paths) in zip(prepared.candidates, prepared.read_set_paths):
        if bool(paths) != (candidate.read_set_fingerprint is not None):
            raise NotPrepared(
                f"candidate {candidate.id!r} read_set_paths emptiness does not match "
                "read_set_fingerprint being set"
            )


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


def validated(prepared: PreparedSet, request: SelectionRequest) -> ValidatedCandidates:
    """`verify()` then bind: the only path from a `PreparedSet` to `ValidatedCandidates`.

    `request` is the already-built `SelectionRequest` (built by the caller
    via `request_from(prepared, session=...)`); `validated` no longer
    builds it internally (plan lines 422-424).
    """
    verify(prepared)
    return contract.validated_candidates(request, bindings=prepared.bindings, provenance=prepared.provenance)
