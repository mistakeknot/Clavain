"""Stub host adapters (mk-42j9.7 Task 6).

Codex, Hermes, Kimi, Pi and bb each get a stub here: `capabilities()` comes
straight from the checked-in matrix (so `test_stub_capabilities_match_matrix`
holds by construction), and every other method either raises
`PointUnreachable` for a point the matrix marks `unreachable`/`unverified`,
or `NotImplementedError("adapter owned by dependent bead")` for a point the
matrix marks `reachable`/`partial` but whose adapter code has not been
written yet -- writing that adapter is out of scope for mk-42j9.7 Task 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from clavain_selector.contract import Candidate, Point

from .base import Capability, HostEvent, Outcome, PointUnreachable, fingerprint_paths, load_matrix

_UNREACHABLE_STATUSES = ("unreachable", "unverified")


class _StubAdapter:
    name = "stub"
    version = "0"

    def capabilities(self) -> dict[Point, Capability]:
        return load_matrix()[self.name]

    def detect(self, env: Mapping[str, str]) -> bool:
        return False

    def _require_reachable(self, point: Point) -> Capability:
        cap = self.capabilities().get(point)
        if cap is None:
            raise PointUnreachable(f"{self.name} adapter: {point.value} is not in the host matrix")
        if cap.status in _UNREACHABLE_STATUSES:
            raise PointUnreachable(
                f"{self.name} adapter: {point.value} is {cap.status} per the host matrix"
            )
        return cap

    def parse_event(self, point: Point, raw: bytes) -> HostEvent:
        self._require_reachable(point)
        raise NotImplementedError("adapter owned by dependent bead")

    def render(self, point: Point, outcome: Outcome, event: HostEvent) -> bytes:
        self._require_reachable(point)
        raise NotImplementedError("adapter owned by dependent bead")

    def authorize(self, candidate: Candidate, event: HostEvent) -> bool:
        raise NotImplementedError("adapter owned by dependent bead")

    def fingerprint(self, paths: Sequence[Path]) -> str:
        # Shared, host-independent, and safe to expose even before the rest
        # of the adapter exists.
        return fingerprint_paths(paths)

    def acknowledge(self, record: Mapping[str, Any], next_event: HostEvent) -> str:
        return "unknown"


class CodexAdapter(_StubAdapter):
    name = "codex"
    version = "0"


class HermesAdapter(_StubAdapter):
    name = "hermes"
    version = "0"


class KimiAdapter(_StubAdapter):
    name = "kimi"
    version = "0"


class PiAdapter(_StubAdapter):
    name = "pi"
    version = "0"


class BbAdapter(_StubAdapter):
    name = "bb"
    version = "0"
