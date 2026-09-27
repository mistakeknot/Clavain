"""Host adapter interface and capability matrix loader (mk-42j9.7 Task 6, R6b).

Implements the plan's "Host adapters" section: the `HostAdapter` Protocol,
the `Capability`/`HostEvent`/`Outcome` shapes it is built from, and
`load_matrix`, which reads `config/selector-host-matrix.json` into
`{host_name: {Point: Capability}}`. `gate_mode` and `fingerprint_paths` are
small shared helpers used by every concrete adapter (not part of the
Protocol's required export list, but needed by more than one adapter module,
so they live here rather than being duplicated).

R6b adds: `authorize_by_policy` (the one payload-bound authorization rule
every adapter's `authorize` must delegate to verbatim), `emitted_outcome`
(the only normal-use constructor for an `"emitted"` `Outcome`, now bound to
`render_bytes`/`payload_sha256`/`binding_sha256` instead of a single opaque
render field), `LAUNCH_ARGV_TEMPLATE`/`launch_argv_ok`, and a fail-safe
rewrite of `fingerprint_paths` that raises `FingerprintUnavailable` rather
than ever returning a marker value in place of a real fingerprint.

This module has no I/O beyond reading the matrix file and the paths handed
to `fingerprint_paths`: it never touches the network, never reads
`~/.config/jev/`, and never executes a subprocess.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat as stat_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import clavain_selector.contract as contract
from clavain_selector.contract import AuthorizationPolicy, Candidate, FallbackReason, Point, ValidatedCandidates

_VALID_STATUS = ("reachable", "partial", "unreachable", "unverified")
_VALID_EVIDENCE = ("first_hand", "binary", "clavain_code", "sylveste_code", "docs", "none")

# "unverified" is treated as unreachable (matrix section, gate_mode below).
_SHADOW_OK_STATUS = frozenset({"reachable", "partial"})

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MATRIX_PATH = _REPO_ROOT / "config" / "selector-host-matrix.json"

ALL_POINTS: tuple[Point, ...] = tuple(Point)
MATRIX_POINTS: tuple[Point, ...] = tuple(p for p in Point if p is not Point.LIBRARY)

# The one argv shape `render()` may ever produce at `launch_profile`: the
# fixed prefix plus the chosen candidate's id as the last element.
LAUNCH_ARGV_TEMPLATE: tuple[str, ...] = ("claude", "plugin", "enable", "--scope", "local")


class PointUnreachable(Exception):
    """Raised when an adapter is asked to act at a point it cannot reach.

    Covers both matrix-driven refusals (status `unreachable`/`unverified`)
    and points the concrete adapter simply does not implement yet.
    """


@dataclass(frozen=True)
class Capability:
    """One cell of the host capability matrix."""

    status: str
    mechanism: str
    limits: str
    evidence_level: str
    verified_on: str
    verified_at: str

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUS:
            raise ValueError(f"invalid capability status: {self.status!r}")
        if self.evidence_level not in _VALID_EVIDENCE:
            raise ValueError(f"invalid capability evidence_level: {self.evidence_level!r}")


@dataclass(frozen=True)
class HostEvent:
    """A parsed host hook/event, independent of the host's own wire shape."""

    point: Point
    session_id: str
    tool_name: str | None = None
    tool_input: Any = None
    tool_response: Any = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    """What the selector decided to render at a point.

    `kind` is `"shadow"` (Jev's pick is recorded but the host proceeds
    natively and render() must return empty output), `"native"` (any
    fallback reason -- the host also proceeds natively) or `"emitted"`
    (active mode reached and the selector hands a rendered effect to the
    host). For `kind == "emitted"`, `render_bytes` is the exact bytes
    `render()` splices into its output; `payload_sha256` must equal
    `sha256(render_bytes)` and `binding_sha256` must equal the chosen
    candidate's entry in `ValidatedCandidates.bindings` -- `__post_init__`
    enforces both as a backstop against a hand-built, inconsistent
    `Outcome` ever reaching a host render.
    """

    kind: str  # "shadow" | "native" | "emitted"
    mode: str = "shadow"
    candidate: Candidate | None = None
    fallback_reason: str | None = None
    render_bytes: bytes | None = None
    payload_sha256: str | None = None
    binding_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.kind != "emitted":
            return
        if self.render_bytes is None or self.payload_sha256 is None or self.binding_sha256 is None:
            raise ValueError("an 'emitted' Outcome requires render_bytes, payload_sha256 and binding_sha256")
        if not isinstance(self.render_bytes, (bytes, bytearray)):
            raise ValueError("render_bytes must be bytes")
        if hashlib.sha256(bytes(self.render_bytes)).hexdigest() != self.payload_sha256:
            raise ValueError("payload_sha256 does not match sha256(render_bytes)")
        if self.payload_sha256 != self.binding_sha256:
            raise ValueError("payload_sha256 does not match binding_sha256")


def launch_argv_ok(chosen: Candidate, validated: ValidatedCandidates) -> bool:
    """True everywhere except `launch_profile`, where the payload must be
    exactly `[*LAUNCH_ARGV_TEMPLATE, chosen.id]` -- a `list` of six `str`."""
    if validated.point != Point.LAUNCH_PROFILE:
        return True
    expected = [*LAUNCH_ARGV_TEMPLATE, chosen.id]
    payload = chosen.payload
    return isinstance(payload, list) and payload == expected and all(isinstance(item, str) for item in payload)


def authorize_by_policy(chosen: Candidate, validated: ValidatedCandidates, policy: AuthorizationPolicy) -> bool:
    """The one authorization rule every adapter's `authorize` must delegate to.

    True only when: (1) `chosen` is one of `validated.candidates` by object
    identity; (2) `policy` names the same `(integration, point)` as
    `validated`; (3) `chosen.id` is not in `policy.deny_ids` and is allowed
    by `allow_all`, `allow_ids` or `allow_id_prefixes`; (4) `chosen.payload`'s
    hash matches `chosen.id`'s entry in `validated.bindings`. Reads nothing
    else -- no event, no environment, no filesystem, no adapter state.
    """
    if not any(candidate is chosen for candidate in validated.candidates):
        return False
    if policy.integration != validated.integration or policy.point != validated.point:
        return False
    if chosen.id in policy.deny_ids:
        return False
    allowed = policy.allow_all or chosen.id in policy.allow_ids or any(
        chosen.id.startswith(prefix) for prefix in policy.allow_id_prefixes
    )
    if not allowed:
        return False
    bindings = dict(validated.bindings)
    if chosen.id not in bindings:
        return False
    return contract.payload_sha256(chosen.payload) == bindings[chosen.id]


def emitted_outcome(chosen: Candidate, validated: ValidatedCandidates, *, mode: str) -> Outcome:
    """The only normal-use constructor for an `"emitted"` `Outcome`.

    Raises `ValueError` (never emits) when `chosen` is not launch-argv-safe
    for a `launch_profile` point, or when `chosen.id` is not bound in
    `validated.bindings`.
    """
    if not launch_argv_ok(chosen, validated):
        raise ValueError("candidate payload does not match LAUNCH_ARGV_TEMPLATE for launch_profile")
    bindings = dict(validated.bindings)
    if chosen.id not in bindings:
        raise ValueError(f"candidate {chosen.id!r} is not bound in validated.bindings")
    render_bytes = contract.payload_bytes(chosen.payload)
    payload_hash = hashlib.sha256(render_bytes).hexdigest()
    return Outcome(
        kind="emitted",
        mode=mode,
        candidate=chosen,
        render_bytes=render_bytes,
        payload_sha256=payload_hash,
        binding_sha256=bindings[chosen.id],
    )


class HostAdapter(Protocol):
    name: str

    def capabilities(self) -> dict[Point, Capability]: ...

    def detect(self, env: Mapping[str, str]) -> bool: ...

    def parse_event(self, point: Point, raw: bytes) -> HostEvent: ...

    def render(self, point: Point, outcome: Outcome, event: HostEvent) -> bytes: ...

    def authorize(self, chosen: Candidate, validated: ValidatedCandidates, policy: AuthorizationPolicy) -> bool: ...

    def fingerprint(self, paths: Sequence[Path]) -> str: ...

    def acknowledge(self, record: Mapping[str, Any], next_event: HostEvent) -> str: ...


def load_matrix(path: str | Path | None = None) -> dict[str, dict[Point, Capability]]:
    """Load `config/selector-host-matrix.json` into `{host: {Point: Capability}}`."""
    matrix_path = Path(path) if path is not None else DEFAULT_MATRIX_PATH
    with open(matrix_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    hosts: dict[str, dict[Point, Capability]] = {}
    for host_name, points in data.get("hosts", {}).items():
        hosts[host_name] = {
            Point(point_name): Capability(**entry) for point_name, entry in points.items()
        }
    return hosts


def gate_mode(capability: Capability, mode: str) -> FallbackReason | None:
    """`None` when `mode` can be honored for `capability`; else the `FallbackReason`.

    Shadow mode needs `status` `reachable` or `partial` (`unverified` is
    treated as `unreachable`, per the matrix section). Active mode
    additionally needs `evidence_level == "first_hand"` (B9): a flag alone
    cannot turn on an effect whose host mechanism has not actually been
    observed to behave as documented.
    """
    if capability.status not in _SHADOW_OK_STATUS:
        return FallbackReason.POINT_UNREACHABLE
    if mode == "active" and capability.evidence_level != "first_hand":
        return FallbackReason.POINT_UNREACHABLE
    return None


# ---------------------------------------------------------------------------
# Fail-safe fingerprinting
# ---------------------------------------------------------------------------

FINGERPRINT_MAX_BYTES = 64 * 1024 * 1024
FINGERPRINT_MAX_PATHS = 4096

# A seam so tests can force lstat failures/races without touching the real
# filesystem; looked up at call time (never bound at import time) so a
# `monkeypatch.setattr(base, "_lstat", ...)` reaches every call.
_lstat = os.lstat


class FingerprintUnavailable(Exception):
    """`fingerprint_paths` could not produce a stable fingerprint for a path.

    Raised (never a marker value standing in for a real fingerprint) when
    there are too many paths, a regular file exceeds
    `FINGERPRINT_MAX_BYTES`, a regular file cannot be read, or a path's
    identity (`dev`, `ino`) is not stable between `lstat` and `open` even
    after one retry. Two unavailable results must never compare equal --
    a caller that wants "unavailable" and "identical" to differ must catch
    this exception itself rather than compare fingerprint strings.
    """


def _entry_for_path(raw_path: Path | str) -> list[Any]:
    p = Path(raw_path)
    try:
        resolved = str(p.resolve())
    except OSError:
        resolved = str(p)

    last_exc: OSError | None = None
    for _attempt in range(2):
        try:
            st1 = _lstat(p)
        except FileNotFoundError:
            return [resolved, "missing"]
        except OSError as exc:
            raise FingerprintUnavailable(f"lstat failed for {resolved}: {exc}") from exc

        if not stat_module.S_ISREG(st1.st_mode):
            return [resolved, "not_regular", st1.st_mode, st1.st_dev, st1.st_ino, st1.st_size, st1.st_mtime_ns]

        if st1.st_size > FINGERPRINT_MAX_BYTES:
            raise FingerprintUnavailable(f"{resolved} exceeds fingerprint max bytes ({FINGERPRINT_MAX_BYTES})")

        try:
            with open(p, "rb") as handle:
                st2 = os.fstat(handle.fileno())
                if (st2.st_dev, st2.st_ino) != (st1.st_dev, st1.st_ino):
                    # Identity changed between lstat and open (a swap): retry
                    # once, then raise rather than fingerprint a moving target.
                    last_exc = None
                    continue
                data = handle.read(FINGERPRINT_MAX_BYTES + 1)
        except OSError as exc:
            raise FingerprintUnavailable(f"could not read {resolved}: {exc}") from exc

        if len(data) > FINGERPRINT_MAX_BYTES:
            raise FingerprintUnavailable(f"{resolved} exceeds fingerprint max bytes ({FINGERPRINT_MAX_BYTES})")

        content_sha256 = hashlib.sha256(data).hexdigest()
        return [resolved, st1.st_dev, st1.st_ino, st1.st_size, st1.st_mtime_ns, content_sha256]

    raise FingerprintUnavailable(f"unstable identity for {resolved}: dev/ino swapped between lstat and open")


def fingerprint_paths(paths: Sequence[Path]) -> str:
    """sha256 over the sorted per-path entries described above.

    Raises `FingerprintUnavailable` (never returns a marker value) when any
    path cannot be fingerprinted safely. Shared by every adapter -- the
    Selector contract section defines this once, independent of host.
    """
    path_list = list(paths)
    if len(path_list) > FINGERPRINT_MAX_PATHS:
        raise FingerprintUnavailable(f"too many paths for fingerprint_paths: {len(path_list)} > {FINGERPRINT_MAX_PATHS}")
    entries = [_entry_for_path(p) for p in path_list]
    entries.sort(key=lambda e: e[0])
    canonical = json.dumps(sorted(entries), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
