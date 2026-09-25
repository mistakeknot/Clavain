"""Host adapter interface and capability matrix loader (mk-42j9.7 Task 6).

Implements the plan's "Host adapters" section: the `HostAdapter` Protocol,
the `Capability`/`HostEvent`/`Outcome` shapes it is built from, and
`load_matrix`, which reads `config/selector-host-matrix.json` into
`{host_name: {Point: Capability}}`. `gate_mode` and `fingerprint_paths` are
small shared helpers used by every concrete adapter (not part of the
Protocol's required export list, but needed by more than one adapter module,
so they live here rather than being duplicated).

This module has no I/O beyond reading the matrix file: it never touches the
network, never reads `~/.config/jev/`, and never executes a subprocess.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from clavain_selector.contract import Candidate, FallbackReason, Point

_VALID_STATUS = ("reachable", "partial", "unreachable", "unverified")
_VALID_EVIDENCE = ("first_hand", "binary", "clavain_code", "sylveste_code", "docs", "none")

# "unverified" is treated as unreachable (matrix section, gate_mode below).
_SHADOW_OK_STATUS = frozenset({"reachable", "partial"})

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MATRIX_PATH = _REPO_ROOT / "config" / "selector-host-matrix.json"

ALL_POINTS: tuple[Point, ...] = tuple(Point)
MATRIX_POINTS: tuple[Point, ...] = tuple(p for p in Point if p is not Point.LIBRARY)


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
    host). `render_payload` carries whatever the point's render() needs to
    build an "emitted" effect (e.g. replacement tool-output content for
    point (d)); it is opaque to the adapter interface itself and is never
    itself a permission decision -- `render()` never emits "allow".
    """

    kind: str  # "shadow" | "native" | "emitted"
    mode: str = "shadow"
    candidate: Candidate | None = None
    fallback_reason: str | None = None
    render_payload: Any = None


class HostAdapter(Protocol):
    name: str

    def capabilities(self) -> dict[Point, Capability]: ...

    def detect(self, env: Mapping[str, str]) -> bool: ...

    def parse_event(self, point: Point, raw: bytes) -> HostEvent: ...

    def render(self, point: Point, outcome: Outcome, event: HostEvent) -> bytes: ...

    def authorize(self, candidate: Candidate, event: HostEvent) -> bool: ...

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


def fingerprint_paths(paths: Sequence[Path]) -> str:
    """sha256 over the sorted `(resolved path, st_size, st_mtime_ns, st_ino, content_sha256)` tuples.

    `content_sha256` covers files up to 1 MiB; above that the literal string
    `"large"` stands in. A missing file contributes `(resolved path,
    "missing")` rather than being skipped, so removing a file changes the
    fingerprint. Shared by every adapter -- the Selector contract section
    defines this once, independent of host.
    """
    entries: list[tuple[Any, ...]] = []
    for raw_path in paths:
        p = Path(raw_path)
        try:
            resolved = str(p.resolve())
        except OSError:
            resolved = str(p)
        try:
            st = os.stat(p)
        except OSError:
            entries.append((resolved, "missing"))
            continue
        if st.st_size <= 1024 * 1024:
            try:
                content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                content_hash = "unreadable"
        else:
            content_hash = "large"
        entries.append((resolved, st.st_size, st.st_mtime_ns, st.st_ino, content_hash))
    entries.sort(key=lambda e: e[0])
    canonical = json.dumps(entries, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
