"""Selector contract: candidates, requests, fallback reasons and validation.

This module owns the shapes and pure functions described in the plan's
"Selector contract" section. It has no I/O: flags, egress, records, the Jev
client and adapters each build on these types but this module never touches
the network, the filesystem (beyond dataclasses' normal behavior) or the
environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Any, Sequence

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


@dataclass(frozen=True)
class ValidationContext:
    now_ms: int
    current_revision: str
    current_read_set_fingerprint: str | None
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
    if candidate.read_set_fingerprint is not None and candidate.read_set_fingerprint != ctx.current_read_set_fingerprint:
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
    if candidate.read_set_fingerprint is not None and candidate.read_set_fingerprint != ctx.current_read_set_fingerprint:
        return RejectReason.STALE_READ_SET
    if candidate.expires_at_ms is not None and candidate.expires_at_ms < ctx.now_ms:
        return RejectReason.EXPIRED
    if not preconditions_met:
        return RejectReason.UNMET_PRECONDITION
    if not ctx.authorized:
        return RejectReason.UNAUTHORIZED
    return None
