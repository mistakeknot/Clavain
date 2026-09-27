"""Selector contract: candidates, requests, fallback reasons and validation.

This module owns the shapes and pure functions described in the plan's
"Selector contract" section. It has no I/O: flags, egress, records, the Jev
client and adapters each build on these types but this module never touches
the network, the filesystem (beyond dataclasses' normal behavior) or the
environment.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Limits (Selector contract section)
# ---------------------------------------------------------------------------

MAX_TASK_CHARS = 12_000
MAX_CONTEXT_CHARS = 40_000
MAX_CANDIDATE_DESCRIPTION_CHARS = 2_000
MAX_CANDIDATES = 16
MIN_CANDIDATES = 1
MAX_REQUEST_BYTES = 90_000
MAX_RESPONSE_BYTES = 64 * 1024

_CANDIDATE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_RESERVED_CANDIDATE_ID = "escalate"


class Point(str, Enum):
    """Integration points a host event can occur at, plus the in-process ``library`` point."""

    LAUNCH_PROFILE = "launch_profile"
    PROMPT_SUBMIT = "prompt_submit"
    PRE_TOOL = "pre_tool"
    POST_TOOL_OUTPUT = "post_tool_output"
    PRE_COMPACT = "pre_compact"
    SESSION_START = "session_start"
    SKILL_LOADING = "skill_loading"
    LIBRARY = "library"


class RejectReason(str, Enum):
    """Host revalidation outcomes for the candidate Jev chose."""

    INVALID_ID = "invalid_id"
    STALE_REVISION = "stale_revision"
    STALE_READ_SET = "stale_read_set"
    EXPIRED = "expired"
    UNMET_PRECONDITION = "unmet_precondition"
    UNAUTHORIZED = "unauthorized"


class FallbackReason(str, Enum):
    """Every reason ``selector.select`` can fall back to native behavior.

    Ordered as in the plan's "Selection flow and fallback table". The six
    RejectReason values are reused verbatim as fallback reasons for row 12
    (host revalidation of the chosen candidate); a rejected candidate falls
    back to native for the same reason string that describes the rejection.
    """

    # Row 1
    FLAG_OFF = "flag_off"
    # Row 2
    INVALID_INPUT = "invalid_input"
    NO_CANDIDATES = "no_candidates"
    # Row 3
    POINT_UNREACHABLE = "point_unreachable"
    # Row 4
    STALE_BEFORE_SELECT = "stale_before_select"
    # Row 5
    EGRESS_REFUSED = "egress_refused"
    # Row 6
    BUDGET_EXHAUSTED = "budget_exhausted"
    # Row 7
    CIRCUIT_OPEN = "circuit_open"
    # Row 8
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    # Row 9
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CREDENTIAL_REJECTED = "credential_rejected"
    HTTP_ERROR = "http_error"
    # Row 10
    INVALID_RESPONSE = "invalid_response"
    MODEL_MISMATCH = "model_mismatch"
    # Row 11
    JEV_ESCALATED = "jev_escalated"
    LOW_CONFIDENCE = "low_confidence"
    LOW_FIT = "low_fit"
    # Row 12 (RejectReason values, reused)
    INVALID_ID = "invalid_id"
    STALE_REVISION = "stale_revision"
    STALE_READ_SET = "stale_read_set"
    EXPIRED = "expired"
    UNMET_PRECONDITION = "unmet_precondition"
    UNAUTHORIZED = "unauthorized"
    # Row 13
    SHADOW_MODE = "shadow_mode"
    # Row 14
    RECORD_UNWRITABLE = "record_unwritable"
    # any row
    INTERNAL_ERROR = "internal_error"


# Row 12's members must have the exact same string values as RejectReason so
# that a RejectReason returned by `revalidate` can be used directly as the
# `fallback.reason` string in a decision record.
assert {r.value for r in RejectReason} <= {r.value for r in FallbackReason}


@dataclass(frozen=True)
class FallbackRow:
    """One row of the fallback table: what a given reason implies."""

    applied: str
    counts_toward_breaker: bool
    writes_record: bool


# Reasons that count failures toward the circuit breaker (Breaker column "yes").
_BREAKER_REASONS = frozenset({
    FallbackReason.TIMEOUT,
    FallbackReason.RATE_LIMITED,
    FallbackReason.HTTP_ERROR,
    FallbackReason.INVALID_RESPONSE,
})

# Reasons whose row does not write a normal JSONL decision record. `flag_off`
# writes nothing at all (the layer must be byte-for-byte inert);
# `record_unwritable` is, by definition, the case where the record could not
# be written, so it is a best-effort stderr line rather than a written record.
_NO_RECORD_REASONS = frozenset({
    FallbackReason.FLAG_OFF,
    FallbackReason.RECORD_UNWRITABLE,
})

FALLBACK_TABLE: dict[FallbackReason, FallbackRow] = {
    reason: FallbackRow(
        applied="native",
        counts_toward_breaker=reason in _BREAKER_REASONS,
        writes_record=reason not in _NO_RECORD_REASONS,
    )
    for reason in FallbackReason
}


@dataclass(frozen=True)
class Candidate:
    """A host-prepared option offered to the selector.

    ``payload`` is never selector-visible: it never appears in the request
    sent to Jev, nor in a decision record. Only ``selector_view()`` (id and
    description) crosses that boundary.
    """

    id: str
    description: str
    payload: Any
    prepared_at_revision: str
    preconditions: tuple[str, ...] = ()
    read_set_fingerprint: str | None = None
    expires_at_ms: int | None = None

    def selector_view(self) -> dict[str, str]:
        """The only projection of this candidate that may reach Jev or a record's `candidates[].id`."""
        return {"id": self.id, "description": self.description}


class NonCanonicalOrder(ValueError):
    """Raised when a candidate/view sequence is not in its canonical order.

    A subclass of ``ValueError`` so existing broad ``except ValueError``
    handling continues to catch it, while callers that specifically need to
    tell "not canonical" apart from other structural problems can still do
    so with ``except NonCanonicalOrder``.
    """


def order_salt(ids: Sequence[str]) -> str:
    """A salt derived from the *set* of candidate ids, not their order or count.

    Ids are deduplicated before hashing so a request that (invalidly)
    contains a duplicate id still has one consistent salt to sort and
    re-verify against, rather than the salt itself depending on how many
    times an id was repeated or where the duplicate landed.
    """
    unique_ids = sorted(set(ids))
    text = "clavain-order-v1\n" + "\n".join(unique_ids)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_json_native(value: Any) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("payload float must be finite")
        return
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for item in value:
            _check_json_native(item)
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            if not isinstance(key, str):
                raise ValueError("payload dict keys must be str")
            _check_json_native(sub)
        return
    raise ValueError(f"payload contains a non-JSON-native value: {type(value)!r}")


def payload_bytes(payload: Any) -> bytes:
    """Canonical JSON bytes for a candidate payload or any other JSON-native value.

    The single source of truth for payload serialization: raises
    ``ValueError`` for anything that is not JSON-native (tuples, sets,
    dict keys that are not ``str``, non-finite floats, or arbitrary
    objects) rather than silently falling back to ``repr()`` or ``str()``.
    """
    _check_json_native(payload)
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False).encode("utf-8")


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(payload_bytes(payload)).hexdigest()


def candidate_sort_key(candidate: "Candidate", *, salt: str) -> tuple[Any, ...]:
    """The full tie-break key for one candidate under a given order salt.

    The salted hash of the id dominates; the remaining fields only matter to
    break a hash collision (astronomically unlikely) or -- more relevantly
    for tests -- to give a deterministic order to two candidates that
    (invalidly) share the same id.
    """
    digest = hashlib.sha256((salt + "\0" + candidate.id).encode("utf-8")).hexdigest()
    return (
        digest,
        candidate.id,
        candidate.description,
        payload_sha256(candidate.payload),
        candidate.prepared_at_revision,
        candidate.read_set_fingerprint or "",
        -1 if candidate.expires_at_ms is None else candidate.expires_at_ms,
        candidate.preconditions,
    )


def canonical_order(candidates: Sequence["Candidate"]) -> tuple["Candidate", ...]:
    """Sort `candidates` into the one order every consumer must agree on.

    Permutation-invariant: any ordering of the same candidate set produces
    the same output, because the sort key is derived from a salt over the
    *set* of ids (`order_salt`), not from input position.
    """
    salt = order_salt([c.id for c in candidates])
    return tuple(sorted(candidates, key=lambda c: candidate_sort_key(c, salt=salt)))


def _view_id(item: Any) -> str:
    return item["id"] if isinstance(item, Mapping) else item.id


def require_canonical(candidates: Sequence[Any]) -> None:
    """Raise `NonCanonicalOrder` unless `candidates` is already in canonical order.

    Accepts either `Candidate` objects or `{id, description}` selector-view
    mappings. Deliberately never calls `canonical_order` itself (so a test
    or a caller that only patches `canonical_order` cannot silently disable
    this guard) -- it recomputes the salt and per-item hash independently.
    For two adjacent items that tie on `(hash, id)`, a full-key tie-break is
    only possible when both items are `Candidate` objects (a selector view
    lacks the fields a full tie-break needs), so a tie involving any view
    raises unconditionally.
    """
    items = list(candidates)
    ids = [_view_id(item) for item in items]
    salt = order_salt(ids)
    for previous, current in zip(items, items[1:]):
        prev_id = _view_id(previous)
        curr_id = _view_id(current)
        prev_key = (hashlib.sha256((salt + "\0" + prev_id).encode("utf-8")).hexdigest(), prev_id)
        curr_key = (hashlib.sha256((salt + "\0" + curr_id).encode("utf-8")).hexdigest(), curr_id)
        if prev_key < curr_key:
            continue
        if prev_key > curr_key:
            raise NonCanonicalOrder(f"candidates not in canonical order at id {prev_id!r} -> {curr_id!r}")
        if isinstance(previous, Mapping) or isinstance(current, Mapping):
            raise NonCanonicalOrder(f"duplicate id {prev_id!r} in a selector-view sequence has no canonical tie-break")
        if candidate_sort_key(previous, salt=salt) > candidate_sort_key(current, salt=salt):
            raise NonCanonicalOrder(f"duplicate-id candidates out of order at id {prev_id!r}")


@dataclass(frozen=True)
class SessionRef:
    """Host session identity carried through a selection for logging and budgets."""

    host_session_id: str
    bead_id: str | None = None


@dataclass(frozen=True)
class SelectionRequest:
    integration: str
    point: Point
    task: str
    context: str
    candidates: tuple[Candidate, ...]
    task_revision: str
    session: SessionRef
    sources: tuple[Path, ...] = ()
    project_root: Path | None = None

    def __post_init__(self) -> None:
        # A frozen dataclass: reorder at construction time via
        # object.__setattr__ so every consumer of `request.candidates`
        # downstream sees the one canonical order, without each consumer
        # having to remember to sort it itself.
        object.__setattr__(self, "candidates", canonical_order(self.candidates))


def canonical_request_body(request: "SelectionRequest") -> bytes:
    """The single source of truth for the bytes sent to Jev for a request.

    `egress._build_body` and `records._request_block` both delegate here
    rather than each serializing the request themselves.
    """
    require_canonical(request.candidates)
    point_value = request.point.value if isinstance(request.point, Point) else request.point
    payload = {
        "schema": "clavain-selection-v1",
        "point": point_value,
        "integration": request.integration,
        "task": request.task,
        "context": request.context,
        "candidates": [c.selector_view() for c in request.candidates],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def request_sha256(request: "SelectionRequest") -> str:
    return hashlib.sha256(canonical_request_body(request)).hexdigest()


class Provenance(str, Enum):
    """Where a `ValidatedCandidates`/`PreparedSet` came from (revision 7, S1)."""

    PREPARER = "preparer"
    OPERATOR = "operator"
    EVAL_CASE = "eval_case"
    EXTERNAL = "external"


@dataclass(frozen=True)
class AuthorizationPolicy:
    """A per-integration, per-point authorization policy parsed from the registry."""

    integration: str
    point: Point
    allow_all: bool = False
    allow_ids: frozenset[str] = frozenset()
    allow_id_prefixes: tuple[str, ...] = ()
    deny_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ValidatedCandidates:
    """A canonically-ordered, structurally-checked candidate set bound to payload hashes.

    Only built by `validated_candidates` in normal use; `__post_init__` still
    re-validates a hand-built instance so a bad set cannot reach `authorize()`.
    """

    integration: str
    point: Point
    candidates: tuple[Candidate, ...]
    request_sha256: str
    bindings: tuple[tuple[str, str], ...]
    provenance: "Provenance"

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        object.__setattr__(self, "candidates", candidates)
        n = len(candidates)
        if n < MIN_CANDIDATES or n > MAX_CANDIDATES:
            raise ValueError(f"ValidatedCandidates must have {MIN_CANDIDATES}..{MAX_CANDIDATES} candidates, got {n}")
        ids = [c.id for c in candidates]
        if len(set(ids)) != n:
            raise ValueError("ValidatedCandidates ids must be unique")
        for cid in ids:
            if not _CANDIDATE_ID_PATTERN.match(cid):
                raise ValueError(f"invalid candidate id: {cid!r}")
            if cid == _RESERVED_CANDIDATE_ID:
                raise ValueError(f"reserved candidate id: {cid!r}")
        require_canonical(candidates)
        binding_ids = tuple(b[0] for b in self.bindings)
        if binding_ids != tuple(ids):
            raise ValueError("bindings ids do not match candidates ids")


def validated_candidates(
    request: "SelectionRequest",
    *,
    bindings: tuple[tuple[str, str], ...],
    provenance: "Provenance",
) -> "ValidatedCandidates":
    """The only normal-use constructor for `ValidatedCandidates`.

    Raises `ValueError` unless `validate_request(request) is None` and
    `bindings` equals `tuple((c.id, payload_sha256(c.payload)) for c in
    request.candidates)`.
    """
    if validate_request(request) is not None:
        raise ValueError("request is not structurally valid")
    expected_bindings = tuple((c.id, payload_sha256(c.payload)) for c in request.candidates)
    if tuple(bindings) != expected_bindings:
        raise ValueError("bindings do not match request payload hashes")
    return ValidatedCandidates(
        integration=request.integration,
        point=request.point,
        candidates=request.candidates,
        request_sha256=request_sha256(request),
        bindings=tuple(bindings),
        provenance=provenance,
    )


@dataclass(frozen=True)
class ValidationContext:
    now_ms: int
    current_revision: str
    current_read_set_fingerprints: Mapping[str, str]
    authorized: bool


def validate_request(request: SelectionRequest) -> FallbackReason | None:
    """Row 2 of the fallback table: limits, id pattern, duplicates, candidate count.

    Returns the FallbackReason to fall back with, or None when the request is
    structurally valid. Zero candidates is reported separately (`no_candidates`)
    from every other structural problem (`invalid_input`).
    """
    if len(request.candidates) < MIN_CANDIDATES:
        return FallbackReason.NO_CANDIDATES
    if len(request.candidates) > MAX_CANDIDATES:
        return FallbackReason.INVALID_INPUT
    if len(request.task) > MAX_TASK_CHARS:
        return FallbackReason.INVALID_INPUT
    if len(request.context) > MAX_CONTEXT_CHARS:
        return FallbackReason.INVALID_INPUT
    seen_ids: set[str] = set()
    for candidate in request.candidates:
        if not _CANDIDATE_ID_PATTERN.match(candidate.id):
            return FallbackReason.INVALID_INPUT
        if candidate.id == _RESERVED_CANDIDATE_ID:
            return FallbackReason.INVALID_INPUT
        if candidate.id in seen_ids:
            return FallbackReason.INVALID_INPUT
        seen_ids.add(candidate.id)
        if len(candidate.description) > MAX_CANDIDATE_DESCRIPTION_CHARS:
            return FallbackReason.INVALID_INPUT
    return None


def _is_stale(candidate: Candidate, ctx: ValidationContext) -> bool:
    if candidate.prepared_at_revision != ctx.current_revision:
        return True
    if candidate.read_set_fingerprint is not None:
        current = ctx.current_read_set_fingerprints.get(candidate.id)
        if current != candidate.read_set_fingerprint:
            return True
    if candidate.expires_at_ms is not None and candidate.expires_at_ms < ctx.now_ms:
        return True
    return False


def pre_eligibility(candidates: Sequence[Candidate], ctx: ValidationContext) -> FallbackReason | None:
    """Row 4: if any candidate is already stale, the whole step is skipped.

    Asking Jev to choose among partly stale options wastes a call and invites
    a stale pick (keel behavior), so this checks every candidate up front.
    """
    for candidate in candidates:
        if _is_stale(candidate, ctx):
            return FallbackReason.STALE_BEFORE_SELECT
    return None


def revalidate(
    candidates: Sequence[Candidate],
    chosen_id: str,
    ctx: ValidationContext,
    *,
    preconditions_met: bool = True,
) -> RejectReason | None:
    """Row 12: host revalidation of the specific candidate Jev chose."""
    candidate = next((c for c in candidates if c.id == chosen_id), None)
    if candidate is None:
        return RejectReason.INVALID_ID
    if candidate.prepared_at_revision != ctx.current_revision:
        return RejectReason.STALE_REVISION
    if candidate.read_set_fingerprint is not None:
        current = ctx.current_read_set_fingerprints.get(candidate.id)
        if current != candidate.read_set_fingerprint:
            return RejectReason.STALE_READ_SET
    if candidate.expires_at_ms is not None and candidate.expires_at_ms < ctx.now_ms:
        return RejectReason.EXPIRED
    if not preconditions_met:
        return RejectReason.UNMET_PRECONDITION
    if not ctx.authorized:
        return RejectReason.UNAUTHORIZED
    return None
