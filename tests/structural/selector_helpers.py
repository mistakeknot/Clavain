"""Shared fixtures and builders for scripts/clavain_selector/ tests.

Every selector test module imports `selector_socket_guard` (or simply imports
this module, which is enough for pytest to discover the autouse fixture) so
that a stray call that bypasses `egress.admit()` cannot open a real network
connection during the test suite. Loopback is allowed because the Jev client
tests run a fake server on 127.0.0.1.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from clavain_selector.contract import Candidate, Point, SelectionRequest, SessionRef

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_real_connect = socket.socket.connect


def _guarded_connect(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    if host not in _LOOPBACK_HOSTS:
        raise RuntimeError(
            f"clavain_selector tests must never open a non-loopback connection; "
            f"blocked connect to {address!r}"
        )
    return _real_connect(self, address, *args, **kwargs)


@pytest.fixture(autouse=True)
def selector_socket_guard(monkeypatch):
    """Refuse any socket.connect() that does not target loopback."""
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield


def make_candidate(
    id: str = "brainstorming",
    description: str = "Brainstorm the next step.",
    *,
    payload: Any = None,
    prepared_at_revision: str = "rev-1",
    preconditions: tuple[str, ...] = (),
    read_set_fingerprint: str | None = None,
    expires_at_ms: int | None = None,
) -> Candidate:
    return Candidate(
        id=id,
        description=description,
        payload=payload,
        prepared_at_revision=prepared_at_revision,
        preconditions=preconditions,
        read_set_fingerprint=read_set_fingerprint,
        expires_at_ms=expires_at_ms,
    )


def make_request(
    *,
    integration: str = "selftest",
    point: Point = Point.LIBRARY,
    task: str = "Decide what to do next.",
    context: str = "",
    candidates: tuple[Candidate, ...] | None = None,
    task_revision: str = "rev-1",
    session: SessionRef | None = None,
    sources: tuple[Path, ...] = (),
    project_root: Path | None = None,
) -> SelectionRequest:
    if candidates is None:
        candidates = (make_candidate(),)
    if session is None:
        session = SessionRef(host_session_id="sess-test-0001")
    return SelectionRequest(
        integration=integration,
        point=point,
        task=task,
        context=context,
        candidates=tuple(candidates),
        task_revision=task_revision,
        session=session,
        sources=tuple(sources),
        project_root=project_root,
    )
