"""Deadline-bounded Jev client (mk-42j9.7 Task 5).

Implements the plan's "Jev client" section and its "Typed client API"
subsection: a stdlib-only HTTP client that sends the canonical wire request
described there, never blocks the caller past its deadline (a daemon worker
thread performs the socket work; the caller ``join``s with the remaining
time), retries at most once under narrow conditions, and returns only typed
values (``JevOk``/``JevFailure``, never a bare ``dict`` or ``str``).

``Breaker`` and ``Budget`` are the file-backed (flocked JSON) helpers the
plan describes for rows 6 and 7 of the fallback table. They are standalone
here: gating a call on budget/breaker state before it is made, and folding a
call's outcome back into that state afterward, is the orchestrator's job
(Task 7). ``JevFailure.reason`` is restricted to ``CLIENT_FAILURE_REASONS``
(the network/response outcomes only) because ``budget_exhausted`` and
``circuit_open`` are never outcomes of an actual Jev call -- they are reasons
a call was never attempted.
"""

from __future__ import annotations

import fcntl
import hashlib
import http.client
import json
import math
import os
import ssl
import threading
import time
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import clavain_selector.contract as contract
import clavain_selector.egress as egress
import clavain_selector.questions as questions
from clavain_selector.contract import FallbackReason
from clavain_selector.credentials import SecretStr
from clavain_selector.egress import AdmittedRequest
from clavain_selector.questions import QuestionBattery

# ---------------------------------------------------------------------------
# Constants (Jev client section)
# ---------------------------------------------------------------------------

PINNED_MODEL = "jev-1.13.0"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
MAX_DEADLINE_MS = 5000
MAX_RESPONSE_BYTES = contract.MAX_RESPONSE_BYTES  # 65,536

CONNECT_TIMEOUT_S = 0.5
RETRY_DELAY_S = 0.1
RETRY_MIN_REMAINING_MS = 600
_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_INFLIGHT_CAP = 2

BREAKER_FAILURE_THRESHOLD = 3
BREAKER_OPEN_SECONDS = 600
CREDENTIAL_BREAKER_SECONDS = 24 * 3600
BUDGET_LIMIT = 8

_TIE_EPSILON = 1e-9
_PROBABILITY_SUM_TOLERANCE = 0.01

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "[::1]", "::1"})


# ---------------------------------------------------------------------------
# Programming-error exceptions (never a network outcome)
# ---------------------------------------------------------------------------


class ClientConfigError(ValueError):
    """`JevClient` constructed with a URL outside TYPESAFE_URL / loopback test URLs."""


class NotAdmitted(TypeError):
    """`call()` given anything but a verified `AdmittedRequest`; raised before any socket."""


class BatteryMismatch(ValueError):
    """A `JevCall`'s battery does not match the one `build_battery` gives for its admitted body."""


# ---------------------------------------------------------------------------
# Deadline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Deadline:
    started_ns: int
    budget_ms: int

    @classmethod
    def start(cls, budget_ms: int) -> "Deadline":
        clamped = max(1, min(MAX_DEADLINE_MS, budget_ms))
        return cls(started_ns=time.monotonic_ns(), budget_ms=clamped)

    def remaining_ms(self) -> int:
        elapsed_ms = (time.monotonic_ns() - self.started_ns) // 1_000_000
        return max(0, self.budget_ms - elapsed_ms)


# ---------------------------------------------------------------------------
# JevCall
# ---------------------------------------------------------------------------


def _views_from_admitted_body(body: bytes) -> list[dict[str, str]]:
    parsed = json.loads(body.decode("utf-8"))
    return parsed["candidates"]


@dataclass(frozen=True)
class JevCall:
    """One deadline-bound Jev call: an admitted request plus the battery it implies.

    `battery` is always independently recomputed (never trusted as given) in
    `__post_init__`, from `admitted`'s own body -- so a hand-swapped battery
    (`dataclasses.replace(call, battery=other)`) raises `BatteryMismatch`
    before any connection, and a non-admitted `admitted` (a plain dict, a
    tampered `AdmittedRequest`, or one with a forged tag) raises
    `NotAdmitted` before any connection.
    """

    admitted: AdmittedRequest
    battery: QuestionBattery
    deadline: Deadline

    def __post_init__(self) -> None:
        if not egress.verify(self.admitted):
            raise NotAdmitted("JevCall.admitted must be a verified AdmittedRequest")
        views = _views_from_admitted_body(self.admitted.body)
        expected = questions.build_battery(views, fit_questions=self.battery.fit_questions)
        if expected != self.battery:
            raise BatteryMismatch("JevCall.battery does not match its admitted request's candidates")

    @classmethod
    def build(cls, admitted: AdmittedRequest, *, fit_questions: bool, deadline: Deadline) -> "JevCall":
        if not egress.verify(admitted):
            raise NotAdmitted("JevCall.build requires a verified AdmittedRequest")
        views = _views_from_admitted_body(admitted.body)
        battery = questions.build_battery(views, fit_questions=fit_questions)
        return cls(admitted=admitted, battery=battery, deadline=deadline)

    def wire_body(self) -> bytes:
        parsed = json.loads(self.admitted.body.decode("utf-8"))
        body: dict[str, Any] = {
            "model": PINNED_MODEL,
            "state": {
                "schema": "clavain-selection-v1",
                "point": parsed["point"],
                "task": parsed["task"],
                "context": parsed["context"],
                "candidates": parsed["candidates"],
            },
            "questions": self.battery.to_wire(),
        }
        return json.dumps(body, ensure_ascii=True, separators=(",", ":"), sort_keys=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Typed response shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    confidence: float
    probabilities: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class NoulAnswer:
    key: str
    candidate_id: str
    noul: float


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class JevResponse:
    model: str
    select: ChoiceAnswer
    fits: tuple[NoulAnswer, ...]
    usage: Usage


class FailureDetail(str, Enum):
    INFLIGHT_CAP = "inflight_cap"
    DEADLINE = "deadline"
    CONNECT_ERROR = "connect_error"
    STATUS = "status"
    OVERSIZE = "oversize"
    BAD_JSON = "bad_json"
    SCHEMA = "schema"
    QUESTION_SET = "question_set"
    PROBABILITY_KEYS = "probability_keys"
    PROBABILITY_SUM = "probability_sum"
    CHOSEN_NOT_MAX = "chosen_not_max"
    INVALID_FIT = "invalid_fit"
    MODEL = "model"


CLIENT_FAILURE_REASONS = frozenset({
    FallbackReason.TIMEOUT,
    FallbackReason.RATE_LIMITED,
    FallbackReason.CREDENTIAL_REJECTED,
    FallbackReason.HTTP_ERROR,
    FallbackReason.INVALID_RESPONSE,
    FallbackReason.MODEL_MISMATCH,
})

# Mapping from reason to the FailureDetail members it may carry (Jev client
# section, "Mapping from failure to detail").
_REASON_DETAILS: dict[FallbackReason, frozenset[FailureDetail]] = {
    FallbackReason.TIMEOUT: frozenset({FailureDetail.DEADLINE, FailureDetail.INFLIGHT_CAP}),
    FallbackReason.RATE_LIMITED: frozenset({FailureDetail.STATUS}),
    FallbackReason.CREDENTIAL_REJECTED: frozenset({FailureDetail.STATUS}),
    FallbackReason.HTTP_ERROR: frozenset({FailureDetail.STATUS, FailureDetail.CONNECT_ERROR}),
    FallbackReason.INVALID_RESPONSE: frozenset({
        FailureDetail.OVERSIZE, FailureDetail.BAD_JSON, FailureDetail.SCHEMA,
        FailureDetail.QUESTION_SET, FailureDetail.PROBABILITY_KEYS,
        FailureDetail.PROBABILITY_SUM, FailureDetail.CHOSEN_NOT_MAX, FailureDetail.INVALID_FIT,
    }),
    FallbackReason.MODEL_MISMATCH: frozenset({FailureDetail.MODEL}),
}


@dataclass(frozen=True)
class JevOk:
    response: JevResponse
    attempts: int
    http_status: int
    latency_ms: int


@dataclass(frozen=True)
class JevFailure:
    reason: FallbackReason
    detail: FailureDetail
    attempts: int
    http_status: int | None
    latency_ms: int
    model_returned: str | None = None

    def __post_init__(self) -> None:
        if self.reason not in CLIENT_FAILURE_REASONS:
            raise ValueError(f"JevFailure.reason must be a member of CLIENT_FAILURE_REASONS, got {self.reason!r}")
        allowed = _REASON_DETAILS[self.reason]
        if self.detail not in allowed:
            raise ValueError(f"JevFailure(reason={self.reason!r}) cannot carry detail={self.detail!r}")
        if self.model_returned is not None and self.reason != FallbackReason.MODEL_MISMATCH:
            raise ValueError("JevFailure.model_returned is only set for model_mismatch")


JevResult = JevOk | JevFailure


# ---------------------------------------------------------------------------
# Selection floors (row 11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Floors:
    confidence: float
    fit: float


@dataclass(frozen=True)
class Selection:
    candidate_id: str
    jev_choice: str
    confidence: float
    selected_probability: float
    fit: float | None
    tie_size: int


@dataclass(frozen=True)
class Abstention:
    reason: FallbackReason
    jev_choice: str
    confidence: float
    fit: float | None
    tie_size: int


def _tie_set(probabilities: tuple[tuple[str, float], ...]) -> tuple[str, ...]:
    values = [p for _, p in probabilities]
    top = max(values)
    return tuple(key for key, value in probabilities if value >= top - _TIE_EPSILON)


def _canonical_first(tie_ids: tuple[str, ...], candidate_order: tuple[str, ...]) -> str:
    for candidate_id in candidate_order:
        if candidate_id in tie_ids:
            return candidate_id
    raise ValueError("tie set contains no id from the candidate order")


def apply_floors(response: JevResponse, floors: Floors, battery: QuestionBattery) -> Selection | Abstention:
    """Ties, then escalation, then the confidence floor, then the fit floor.

    The winner is the canonically first id in the tie set `T` (probabilities
    within 1e-9 of the max), never Jev's `choice` string, except that
    `choice` must itself be a member of `T` (already required at response
    validation time). `escalate ∈ T` always yields `jev_escalated`, even when
    `choice` names a candidate.
    """
    tie_ids = _tie_set(response.select.probabilities)
    tie_size = len(tie_ids)
    confidence = response.select.confidence
    candidate_order = tuple(candidate_id for candidate_id, _ in battery.select.criteria)

    if questions.ESCALATE_ID in tie_ids:
        return Abstention(
            reason=FallbackReason.JEV_ESCALATED,
            jev_choice=response.select.choice,
            confidence=confidence,
            fit=None,
            tie_size=tie_size,
        )

    winner_id = _canonical_first(tie_ids, candidate_order)
    prob_by_id = dict(response.select.probabilities)
    selected_probability = prob_by_id[winner_id]

    if confidence < floors.confidence:
        return Abstention(
            reason=FallbackReason.LOW_CONFIDENCE,
            jev_choice=response.select.choice,
            confidence=confidence,
            fit=None,
            tie_size=tie_size,
        )

    fit_value: float | None = None
    if battery.fit_questions:
        fit_value = next((f.noul for f in response.fits if f.candidate_id == winner_id), None)
        if fit_value is not None and fit_value < floors.fit:
            return Abstention(
                reason=FallbackReason.LOW_FIT,
                jev_choice=response.select.choice,
                confidence=confidence,
                fit=fit_value,
                tie_size=tie_size,
            )

    return Selection(
        candidate_id=winner_id,
        jev_choice=response.select.choice,
        confidence=confidence,
        selected_probability=selected_probability,
        fit=fit_value,
        tie_size=tie_size,
    )


# ---------------------------------------------------------------------------
# In-flight cap (process-wide; protects long-lived `library` callers)
# ---------------------------------------------------------------------------

_inflight_lock = threading.Lock()
_inflight_count = 0


def _inflight_enter() -> bool:
    global _inflight_count
    with _inflight_lock:
        if _inflight_count >= _INFLIGHT_CAP:
            return False
        _inflight_count += 1
        return True


def _inflight_exit() -> None:
    global _inflight_count
    with _inflight_lock:
        _inflight_count = max(0, _inflight_count - 1)


def _reset_inflight_for_tests() -> None:
    """Test-only escape hatch: force the module-global counter back to zero."""
    global _inflight_count
    with _inflight_lock:
        _inflight_count = 0


# ---------------------------------------------------------------------------
# JevClient
# ---------------------------------------------------------------------------


def _is_allowed_url(url: str) -> bool:
    if url == TYPESAFE_URL:
        return True
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme != "http":
        return False
    hostname = parsed.hostname
    return hostname in ("127.0.0.1", "::1")


class JevClient:
    """Sends one `JevCall` at a time, never blocking past its deadline."""

    def __init__(self, credential: SecretStr, *, url: str = TYPESAFE_URL) -> None:
        if not _is_allowed_url(url):
            raise ClientConfigError(
                f"JevClient url must be {TYPESAFE_URL!r} or a loopback http:// test URL, got {url!r}"
            )
        self._credential = credential
        self._url = url
        parsed = urllib.parse.urlsplit(url)
        self._scheme = parsed.scheme
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or (443 if self._scheme == "https" else 80)
        self._path = parsed.path or "/"

    # -- connection -----------------------------------------------------

    def _open_connection(self, connect_timeout_s: float) -> http.client.HTTPConnection:
        if self._scheme == "https":
            context = ssl.create_default_context()
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                self._host, self._port, timeout=connect_timeout_s, context=context
            )
        else:
            conn = http.client.HTTPConnection(self._host, self._port, timeout=connect_timeout_s)
        conn.connect()
        return conn

    def _perform(self, wire_body: bytes, read_timeout_s: float, box: dict[str, Any]) -> None:
        conn: http.client.HTTPConnection | None = None
        try:
            conn = self._open_connection(CONNECT_TIMEOUT_S)
            if conn.sock is not None:
                conn.sock.settimeout(read_timeout_s)
            conn.request(
                "POST",
                self._path,
                body=wire_body,
                headers={
                    "Authorization": f"Bearer {self._credential.reveal()}",
                    "Content-Type": "application/json",
                },
            )
            resp = conn.getresponse()
            data = resp.read(MAX_RESPONSE_BYTES + 1)
            box["status"] = resp.status
            box["headers"] = {k.lower(): v for k, v in resp.getheaders()}
            box["data"] = data
        except Exception as exc:  # noqa: BLE001 - reported to the caller, never re-raised here
            box["exception"] = exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
            _inflight_exit()

    def _attempt(self, call: JevCall) -> tuple[dict[str, Any], int]:
        """Run one attempt in a daemon thread; return (box, elapsed_ms).

        `box` may be empty (join timed out; the thread is abandoned and will
        decrement the in-flight counter itself, whenever it finishes).
        """
        remaining_ms = call.deadline.remaining_ms()
        box: dict[str, Any] = {}
        wire_body = call.wire_body()
        started = time.monotonic()
        thread = threading.Thread(
            target=self._perform,
            args=(wire_body, max(remaining_ms, 0) / 1000.0, box),
            daemon=True,
        )
        thread.start()
        thread.join(remaining_ms / 1000.0)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        box["_timed_out"] = thread.is_alive()
        return box, elapsed_ms

    def call(self, call: JevCall) -> JevResult:
        if not isinstance(call, JevCall):
            raise NotAdmitted("JevClient.call requires a JevCall built from a verified AdmittedRequest")
        # `JevCall.__post_init__` already verified `call.admitted` (and would
        # have raised NotAdmitted/BatteryMismatch at construction time), so
        # by the time `call` is a JevCall instance it is known-good.

        attempts = 0
        while True:
            if call.deadline.remaining_ms() <= 0:
                return JevFailure(
                    reason=FallbackReason.TIMEOUT, detail=FailureDetail.DEADLINE,
                    attempts=attempts, http_status=None, latency_ms=0,
                )
            if not _inflight_enter():
                return JevFailure(
                    reason=FallbackReason.TIMEOUT, detail=FailureDetail.INFLIGHT_CAP,
                    attempts=0, http_status=None, latency_ms=0,
                )

            attempts += 1
            box, elapsed_ms = self._attempt(call)

            if box.get("_timed_out"):
                return JevFailure(
                    reason=FallbackReason.TIMEOUT, detail=FailureDetail.DEADLINE,
                    attempts=attempts, http_status=None, latency_ms=elapsed_ms,
                )

            result, retry_after_ms = self._interpret(box, call.battery, elapsed_ms, attempts)
            if not isinstance(result, JevFailure):
                return result

            if self._should_retry(result, attempts, call.deadline, retry_after_ms):
                time.sleep(RETRY_DELAY_S)
                continue
            return result

    # -- response interpretation ----------------------------------------

    def _interpret(
        self, box: dict[str, Any], battery: QuestionBattery, elapsed_ms: int, attempts: int
    ) -> tuple[JevResult, int | None]:
        if "exception" in box:
            return (
                JevFailure(
                    reason=FallbackReason.HTTP_ERROR, detail=FailureDetail.CONNECT_ERROR,
                    attempts=attempts, http_status=None, latency_ms=elapsed_ms,
                ),
                None,
            )

        status = box.get("status")
        headers = box.get("headers", {})
        retry_after_ms = _retry_after_ms(headers.get("retry-after"))

        if status in (401, 403):
            return (
                JevFailure(
                    reason=FallbackReason.CREDENTIAL_REJECTED, detail=FailureDetail.STATUS,
                    attempts=attempts, http_status=status, latency_ms=elapsed_ms,
                ),
                retry_after_ms,
            )
        if status == 429:
            return (
                JevFailure(
                    reason=FallbackReason.RATE_LIMITED, detail=FailureDetail.STATUS,
                    attempts=attempts, http_status=status, latency_ms=elapsed_ms,
                ),
                retry_after_ms,
            )
        if status != 200:
            return (
                JevFailure(
                    reason=FallbackReason.HTTP_ERROR, detail=FailureDetail.STATUS,
                    attempts=attempts, http_status=status, latency_ms=elapsed_ms,
                ),
                retry_after_ms,
            )

        data: bytes = box.get("data", b"")
        outcome = _validate_response(data, battery)
        if isinstance(outcome, tuple):
            detail, model_returned = outcome
            if detail == FailureDetail.MODEL:
                return (
                    JevFailure(
                        reason=FallbackReason.MODEL_MISMATCH, detail=detail,
                        attempts=attempts, http_status=status, latency_ms=elapsed_ms,
                        model_returned=model_returned,
                    ),
                    None,
                )
            return (
                JevFailure(
                    reason=FallbackReason.INVALID_RESPONSE, detail=detail,
                    attempts=attempts, http_status=status, latency_ms=elapsed_ms,
                ),
                None,
            )

        return JevOk(response=outcome, attempts=attempts, http_status=status, latency_ms=elapsed_ms), None

    def _should_retry(
        self, failure: JevFailure, attempts: int, deadline: Deadline, retry_after_ms: int | None
    ) -> bool:
        if attempts != 1:
            return False
        retryable = (
            (failure.reason == FallbackReason.HTTP_ERROR and failure.detail == FailureDetail.CONNECT_ERROR)
            or (failure.reason == FallbackReason.HTTP_ERROR and failure.http_status in _RETRY_STATUSES)
            or (failure.reason == FallbackReason.RATE_LIMITED and failure.http_status in _RETRY_STATUSES)
        )
        if not retryable:
            return False
        remaining = deadline.remaining_ms()
        if remaining < RETRY_MIN_REMAINING_MS:
            return False
        if retry_after_ms is not None and retry_after_ms > remaining:
            return False
        return True


def _retry_after_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value) * 1000)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Response validation ("validate in keel's order")
# ---------------------------------------------------------------------------


def _validate_response(
    data: bytes, battery: QuestionBattery
) -> JevResponse | tuple[FailureDetail, str | None]:
    if len(data) > MAX_RESPONSE_BYTES:
        return FailureDetail.OVERSIZE, None

    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return FailureDetail.BAD_JSON, None

    if not isinstance(parsed, dict):
        return FailureDetail.SCHEMA, None

    model = parsed.get("model")
    answers = parsed.get("answers")
    usage = parsed.get("usage")
    if not isinstance(model, str) or not isinstance(answers, dict) or not isinstance(usage, dict):
        return FailureDetail.SCHEMA, None

    select_wire = answers.get("select")
    if not isinstance(select_wire, dict):
        return FailureDetail.SCHEMA, None
    choice = select_wire.get("choice")
    confidence = select_wire.get("confidence")
    probabilities_wire = select_wire.get("probabilities")
    if not isinstance(choice, str) or not isinstance(probabilities_wire, dict):
        return FailureDetail.SCHEMA, None
    if not _is_finite_number(confidence):
        return FailureDetail.SCHEMA, None

    if model != PINNED_MODEL:
        return FailureDetail.MODEL, model

    expected_fit_keys = {fit.key for fit in battery.fits}
    answer_keys = set(answers.keys())
    if answer_keys != ({"select"} | expected_fit_keys):
        return FailureDetail.QUESTION_SET, None

    candidate_ids = {candidate_id for candidate_id, _ in battery.select.criteria}
    if set(probabilities_wire.keys()) != candidate_ids:
        return FailureDetail.PROBABILITY_KEYS, None

    probabilities: list[tuple[str, float]] = []
    total = 0.0
    for candidate_id, _ in battery.select.criteria:
        value = probabilities_wire.get(candidate_id)
        if not _is_finite_number(value):
            return FailureDetail.PROBABILITY_SUM, None
        probabilities.append((candidate_id, float(value)))
        total += float(value)
    if abs(total - 1.0) > _PROBABILITY_SUM_TOLERANCE:
        return FailureDetail.PROBABILITY_SUM, None

    prob_by_id = dict(probabilities)
    if choice not in prob_by_id:
        return FailureDetail.CHOSEN_NOT_MAX, None
    max_prob = max(prob_by_id.values())
    if prob_by_id[choice] < max_prob - _TIE_EPSILON:
        return FailureDetail.CHOSEN_NOT_MAX, None

    fits: list[NoulAnswer] = []
    for fit in battery.fits:
        fit_wire = answers.get(fit.key)
        if not isinstance(fit_wire, dict):
            return FailureDetail.INVALID_FIT, None
        noul = fit_wire.get("noul")
        if not _is_finite_number(noul) or not (0.0 <= float(noul) <= 1.0):
            return FailureDetail.INVALID_FIT, None
        fits.append(NoulAnswer(key=fit.key, candidate_id=fit.candidate_id, noul=float(noul)))

    if not (0.0 <= float(confidence) <= 1.0):
        return FailureDetail.SCHEMA, None

    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return FailureDetail.SCHEMA, None

    return JevResponse(
        model=model,
        select=ChoiceAnswer(choice=choice, confidence=float(confidence), probabilities=tuple(probabilities)),
        fits=tuple(fits),
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


# ---------------------------------------------------------------------------
# Breaker and Budget (flocked JSON files under $CLAVAIN_STATE_DIR/selector/)
# ---------------------------------------------------------------------------


def _state_dir() -> Path:
    return Path(os.environ.get("CLAVAIN_STATE_DIR") or os.path.expanduser("~/.clavain")).expanduser()


def _selector_dir() -> Path:
    return _state_dir() / "selector"


def _read_locked_json(path: Path) -> tuple[int, dict[str, Any]]:
    """Open (creating if absent), flock exclusively, and return `(fd, data)`.

    The caller must close `fd` (which also releases the lock) once done,
    normally via `_write_locked_json`.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        size = os.fstat(fd).st_size
        if size == 0:
            return fd, {}
        raw = os.read(fd, size)
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            data = {}
        return fd, data if isinstance(data, dict) else {}
    except Exception:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        raise


def _write_locked_json(fd: int, data: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(data).encode("utf-8")
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class Breaker:
    """The circuit breaker for row 7 (`circuit_open`) plus the separate 24h credential breaker.

    Persisted at `$CLAVAIN_STATE_DIR/selector/breaker.json`. `now_fn`
    defaults to `time.time` and exists so tests can monkeypatch the clock
    without touching the real one.
    """

    def __init__(self, *, path: Path | None = None, now_fn=time.time) -> None:
        self._path = path or (_selector_dir() / "breaker.json")
        self._now_fn = now_fn

    def check(self) -> FallbackReason | None:
        fd, state = _read_locked_json(self._path)
        try:
            now = self._now_fn()
            opened_until = state.get("opened_until")
            probe_pending = bool(state.get("probe_pending", False))
            if opened_until is not None:
                if now < opened_until:
                    return FallbackReason.CIRCUIT_OPEN
                if probe_pending:
                    # A probe is already outstanding; refuse until it resolves.
                    return FallbackReason.CIRCUIT_OPEN
                # Cooldown elapsed: allow exactly one half-open probe.
                state["probe_pending"] = True
                _write_locked_json(fd, state)
                fd = -1
                return None
            return None
        finally:
            if fd >= 0:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def record(self, result: "JevResult") -> None:
        fd, state = _read_locked_json(self._path)
        try:
            now = self._now_fn()
            probe_pending = bool(state.get("probe_pending", False))
            if isinstance(result, JevOk):
                state["consecutive_failures"] = 0
                state["opened_until"] = None
                state["probe_pending"] = False
            else:
                if result.reason == FallbackReason.CREDENTIAL_REJECTED:
                    state["credential_breaker_until"] = now + CREDENTIAL_BREAKER_SECONDS
                elif result.reason in contract._BREAKER_REASONS:
                    if probe_pending:
                        state["opened_until"] = now + BREAKER_OPEN_SECONDS
                        state["consecutive_failures"] = 0
                        state["probe_pending"] = False
                    else:
                        failures = int(state.get("consecutive_failures", 0)) + 1
                        if failures >= BREAKER_FAILURE_THRESHOLD:
                            state["opened_until"] = now + BREAKER_OPEN_SECONDS
                            failures = 0
                        state["consecutive_failures"] = failures
            _write_locked_json(fd, state)
        except Exception:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            raise


class Budget:
    """The per-session, per-integration call budget for row 6 (`budget_exhausted`).

    Persisted at `$CLAVAIN_STATE_DIR/selector/budget/<sha256(session)>.json`,
    keyed inside that file by integration name.
    """

    def __init__(
        self,
        session_id: str,
        integration: str,
        *,
        limit: int = BUDGET_LIMIT,
        state_dir: Path | None = None,
    ) -> None:
        self._integration = integration
        self._limit = limit
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        base = state_dir or _selector_dir()
        self._path = base / "budget" / f"{digest}.json"

    def consume(self) -> FallbackReason | None:
        fd, state = _read_locked_json(self._path)
        try:
            used = int(state.get(self._integration, 0))
            if used >= self._limit:
                return FallbackReason.BUDGET_EXHAUSTED
            state[self._integration] = used + 1
            _write_locked_json(fd, state)
            fd = -1
            return None
        finally:
            if fd >= 0:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)


# ---------------------------------------------------------------------------
# Record-field bridging (best-effort helper for the orchestrator, Task 7)
# ---------------------------------------------------------------------------


def to_record_fields(
    outcome: "Selection | Abstention | JevFailure",
    result: "JevOk | JevFailure",
) -> dict[str, Any]:
    """The `selector`/`result` blocks for `records.build_record`.

    `result` is the raw `JevClient.call()` outcome (carries `attempts`,
    `http_status`, `latency_ms` and, on success, `usage`); `outcome` is what
    `apply_floors` derived from it (`Selection`, `Abstention`) or, when the
    call itself failed, the same `JevFailure` passed as `result`. This is the
    only producer of these two blocks so the record schema and these types
    cannot drift apart.
    """
    selector_block: dict[str, Any] = {
        "backend": "jev",
        "model_requested": PINNED_MODEL,
        "attempts": result.attempts,
        "http_status": result.http_status,
        "latency_ms": result.latency_ms,
    }
    if isinstance(result, JevOk):
        selector_block["model_returned"] = result.response.model
        selector_block["jev_usage"] = {
            "input_tokens": result.response.usage.input_tokens,
            "output_tokens": result.response.usage.output_tokens,
        }
    else:
        selector_block["model_returned"] = result.model_returned

    if isinstance(outcome, Selection):
        result_block = {
            "kind": "selected",
            "candidate_id": outcome.candidate_id,
            "jev_choice": outcome.jev_choice,
            "tie_size": outcome.tie_size,
            "confidence": outcome.confidence,
            "selected_probability": outcome.selected_probability,
            "fit": outcome.fit,
        }
    elif isinstance(outcome, Abstention):
        result_block = {
            "kind": "abstained",
            "jev_choice": outcome.jev_choice,
            "tie_size": outcome.tie_size,
            "confidence": outcome.confidence,
            "fit": outcome.fit,
        }
    else:
        result_block = {"kind": "not_called"}

    return {"selector": selector_block, "result": result_block}
