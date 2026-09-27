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
        if isinstance(self.points, (str, bytes)):
            # N4-2 (same bug class as finding 2): `frozenset("library")`
            # silently splits a bare string into one `Point`-shaped
            # character per element instead of the single intended point.
            raise NotPrepared(
                f"preparer {self.name!r} points must be a collection of Point values, "
                f"not a bare {type(self.points).__name__}: {self.points!r}"
            )
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
    # Per the plan's landed shape (plan lines 405/414-415), `project_root` is
    # a mandatory `Path` -- this is the fix (Commit C, finding 8) that makes
    # it so: every entry point (`prepare`, `from_operator`, `from_case`)
    # requires a real project root and `_finish_prepare` raises
    # `NotPrepared` for a missing or unresolvable one, before any candidate
    # is even considered.
    project_root: Path
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

    try:
        entries = list(read_set_paths)
    except TypeError as exc:
        # Commit D (N3 residual): a non-iterable `read_set_paths` (e.g. a
        # bare `5`) must not raise a raw `TypeError` from the `for` loop
        # below -- `not read_set_paths` above only screens out falsy
        # values, not truthy non-iterables.
        raise NotPrepared(f"read_set_paths is not iterable: {read_set_paths!r}") from exc

    normalized: list[tuple[str, tuple[str, ...]]] = []
    for entry in entries:
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
    if project_root is None or (isinstance(project_root, str) and project_root == ""):
        # Finding 8 / Commit D Minor 2: `project_root` is mandatory
        # everywhere -- a missing one (`None` or an empty string, which
        # `Path("")` would otherwise silently resolve to the current
        # working directory) is `NotPrepared`, never a silent default that
        # later code has to remember to special-case.
        raise NotPrepared(f"project_root is required and must be non-empty: {project_root!r}")

    try:
        candidates = tuple(candidates)
    except TypeError as exc:
        raise NotPrepared(f"candidates is not iterable: {candidates!r}") from exc

    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            # N3: a `build()` (or operator/eval-case caller) that hands back
            # a non-`Candidate` (including `None`) must not reach `.id`
            # below and raise a raw `AttributeError`.
            raise NotPrepared(f"candidate is not a Candidate: {candidate!r}")

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

    try:
        root = Path(project_root).resolve()
    except TypeError as exc:
        raise NotPrepared(f"project_root is not a valid path: {project_root!r}") from exc

    normalized_read_set = _normalize_read_set_paths(read_set_paths, ordered)

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

    try:
        source_paths = tuple(Path(s) for s in sources)
    except TypeError as exc:
        # N3: a `build()`/operator/eval-case `sources` entry that isn't
        # path-like (e.g. an int) must not raise a raw `TypeError` here.
        raise NotPrepared(f"sources contains a non-path-like entry: {sources!r}") from exc

    prelim = PreparedSet(
        integration=integration,
        point=point,
        provenance=provenance,
        preparer=preparer,
        task=task,
        context=context,
        candidates=ordered,
        sources=source_paths,
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
    project_root: str | Path,
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
    carries no such fields). `PreparedSet.preparer` is always
    `preparer_def.name` (finding N4-1), which may differ from the registry
    key `preparer_def` was looked up under if a preparer is registered
    under an alias. Also raises `NotPrepared` when `read_set_paths` (a
    per-candidate `(id, paths)` sequence in canonical order, or `()` when
    no candidate has a read set) does not correspond to the candidates or
    disagrees with a candidate's `read_set_fingerprint`, or when any
    candidate's path resolves outside `project_root` or onto the source
    denylist. `project_root` is mandatory (finding 8): `None` is
    `NotPrepared`, never a silently permissive default.
    """
    if project_root is None or (isinstance(project_root, str) and project_root == ""):
        # Commit D Minor 2: an empty string would otherwise resolve
        # silently to the current working directory via `Path("")`.
        raise NotPrepared(f"project_root is required and must be non-empty: {project_root!r}")

    try:
        point_value = point if isinstance(point, Point) else Point(point)
    except ValueError as exc:
        raise NotPrepared(f"not a valid point: {point!r}") from exc

    integrations = registry.get("integrations", {}) if isinstance(registry, Mapping) else {}
    if not isinstance(integrations, Mapping):
        raise NotPrepared(f"registry integrations is not a mapping: {integrations!r}")
    try:
        entry = integrations.get(integration)
    except TypeError as exc:
        # Commit D Minor 3: an unhashable `integration` (e.g. a list) must
        # not raise a raw `TypeError` from the dict lookup.
        raise NotPrepared(f"integration is not a valid key: {integration!r}") from exc
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

    try:
        root_arg = Path(project_root)
    except TypeError as exc:
        raise NotPrepared(f"project_root is not a valid path: {project_root!r}") from exc
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
        raw_vocabulary = preparer_def.vocabulary(root_arg)
    except NotPrepared:
        raise
    except Exception as exc:  # noqa: BLE001 - any preparer failure means NotPrepared
        raise NotPrepared(f"preparer {preparer_name!r} vocabulary failed: {exc}") from exc

    if isinstance(raw_vocabulary, (str, bytes)):
        # N4-3: `frozenset("a")` and `frozenset({"a"})` coincide for a
        # single character but diverge for anything longer -- reject a bare
        # str/bytes return outright rather than silently treating it as a
        # set of characters.
        raise NotPrepared(
            f"preparer {preparer_name!r} vocabulary() returned a bare "
            f"{type(raw_vocabulary).__name__}, not a set of ids: {raw_vocabulary!r}"
        )
    try:
        vocabulary = frozenset(raw_vocabulary)
    except TypeError as exc:
        raise NotPrepared(f"preparer {preparer_name!r} vocabulary() did not return an iterable: {exc}") from exc

    try:
        candidates = tuple(built.candidates)
    except TypeError as exc:
        # Commit D (N3 residual): a `build()` returning a non-iterable
        # `candidates` (e.g. `None` or `5`) must not raise a raw
        # `TypeError` here, before `_finish_prepare`'s own guard is ever
        # reached.
        raise NotPrepared(
            f"preparer {preparer_name!r} build returned non-iterable candidates: {built.candidates!r}"
        ) from exc
    for c in candidates:
        if not isinstance(c, Candidate):
            # N3: a non-`Candidate` entry (including `None`) has no `.id` to
            # report -- `_finish_prepare` below raises `NotPrepared` for
            # this same shape too, but that check must never be reached via
            # a raw `AttributeError` from `c.id` here first.
            raise NotPrepared(f"preparer {preparer_name!r} emitted a non-Candidate entry: {c!r}")
    outside = [c.id for c in candidates if c.id not in vocabulary]
    if outside:
        raise NotPrepared(f"preparer {preparer_name!r} emitted candidates outside its vocabulary: {outside}")

    return _finish_prepare(
        integration=integration,
        point=point_value,
        provenance=Provenance.PREPARER,
        preparer=preparer_def.name,
        task=built.task,
        context=built.context,
        candidates=candidates,
        sources=built.sources,
        project_root=root_arg,
        task_revision=built.task_revision,
        read_set_paths=built.read_set_paths,
    )


def from_operator(
    registry: Mapping[str, Any],
    integration: str,
    point: "Point | str",
    task: str,
    context: str,
    candidates: Sequence[Candidate],
    project_root: str | Path,
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
    (plan line 430). `project_root` is mandatory (finding 8): `None` is
    `NotPrepared`. `point` is coerced to a real `Point`; anything that
    isn't a valid `Point` value is `NotPrepared` (N3), not a raw
    `ValueError` from a downstream comparison.
    """
    del registry
    try:
        point_value = point if isinstance(point, Point) else Point(point)
    except ValueError as exc:
        raise NotPrepared(f"not a valid point: {point!r}") from exc
    return _finish_prepare(
        integration=integration,
        point=point_value,
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
    must supply `integration`, `point`, `task`, `candidates`, `project_root`
    (mandatory per finding 8 -- a case with no `project_root` key is
    `NotPrepared`, same as a missing `integration`/`point`/`task`/
    `candidates`), with `context`/`sources`/`read_set_paths`/`task_revision`/
    `preparer` optional. `read_set_paths`, if given, is a per-candidate
    `(id, paths)` sequence in canonical order. A non-`Mapping` `case`
    (including `None`) is `NotPrepared`, not a raw `TypeError` (N3). `point`
    is coerced to a real `Point`; anything that isn't a valid `Point` value
    is `NotPrepared`.
    """
    del registry
    if not isinstance(case, Mapping):
        raise NotPrepared(f"eval case is not a mapping: {case!r}")
    try:
        integration = case["integration"]
        point = case["point"]
        task = case["task"]
        candidates = case["candidates"]
        project_root = case["project_root"]
    except KeyError as exc:
        raise NotPrepared(f"eval case is missing required key {exc.args[0]!r}") from exc

    try:
        point_value = point if isinstance(point, Point) else Point(point)
    except ValueError as exc:
        raise NotPrepared(f"not a valid point: {point!r}") from exc

    return _finish_prepare(
        integration=integration,
        point=point_value,
        provenance=Provenance.EVAL_CASE,
        preparer=case.get("preparer"),
        task=task,
        context=case.get("context", ""),
        candidates=candidates,
        sources=case.get("sources", ()),
        project_root=project_root,
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


def _check_request_matches_prepared(prepared: PreparedSet, request: SelectionRequest) -> None:
    """N1 (mk-42j9.7 Commit C, sealed criterion at plan line 2264).

    `contract.validated_candidates` only checks that `request` is
    structurally valid and that `bindings` matches `request.candidates`'
    own payload hashes -- it never checks that `request` actually
    describes the same selection `prepared` was built for. Without this
    check, a caller could hand `validated()` a verified `prepared` set
    together with an unrelated `request` (a different integration, point,
    task, context, sources, project_root, task_revision, or even
    substituted `Candidate` objects that happen to share ids and payload
    hashes with `prepared`'s own candidates) and still get back a
    `ValidatedCandidates` -- breaking the identity chain `authorize()`
    relies on. Every field both dataclasses carry must match exactly
    (`sources` order-sensitively, matching how `request_from` copies it
    with no reordering); candidates are compared by full field equality
    (not just id/payload hash), in the same canonical order, so a
    substituted `Candidate` with a different `description` or
    `prepared_at_revision` (but the same id and payload hash) is caught
    too.
    """
    if not isinstance(request, SelectionRequest):
        # Commit D Minor 1: a non-`SelectionRequest` (e.g. `None`) must not
        # raise a raw `AttributeError` from `request.integration` below.
        raise NotPrepared(f"not a SelectionRequest: {request!r}")
    mismatches: list[str] = []
    if request.integration != prepared.integration:
        mismatches.append("integration")
    if request.point != prepared.point:
        mismatches.append("point")
    if request.task != prepared.task:
        mismatches.append("task")
    if request.context != prepared.context:
        mismatches.append("context")
    if request.task_revision != prepared.task_revision:
        mismatches.append("task_revision")
    if tuple(request.sources) != tuple(prepared.sources):
        mismatches.append("sources")
    if request.project_root != prepared.project_root:
        mismatches.append("project_root")
    if tuple(request.candidates) != tuple(prepared.candidates):
        mismatches.append("candidates")
    if mismatches:
        raise NotPrepared(f"request does not match the prepared set on: {mismatches}")


def validated(prepared: PreparedSet, request: SelectionRequest) -> ValidatedCandidates:
    """`verify()` then bind: the only path from a `PreparedSet` to `ValidatedCandidates`.

    `request` is the already-built `SelectionRequest` (built by the caller
    via `request_from(prepared, session=...)`); `validated` no longer
    builds it internally (plan lines 422-424).

    After `verify(prepared)` succeeds, `request` is checked field-by-field
    against `prepared` (see `_check_request_matches_prepared`) -- a
    mismatch on any shared field is `NotPrepared`. Once they are known
    equal, the `ValidatedCandidates` returned is built from a request
    reconstructed from `prepared`'s own fields (only `session` comes from
    the caller's `request`, since `PreparedSet` carries no session): its
    identity always comes from the verified `prepared` set, never from the
    caller-supplied `request`.
    """
    verify(prepared)
    _check_request_matches_prepared(prepared, request)
    trusted_request = SelectionRequest(
        integration=prepared.integration,
        point=prepared.point,
        task=prepared.task,
        context=prepared.context,
        candidates=prepared.candidates,
        task_revision=prepared.task_revision,
        session=request.session,
        sources=prepared.sources,
        project_root=prepared.project_root,
    )
    return contract.validated_candidates(
        trusted_request, bindings=prepared.bindings, provenance=prepared.provenance
    )
