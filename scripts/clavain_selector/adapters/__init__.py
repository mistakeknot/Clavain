"""Host adapters package (mk-42j9.7 Task 6).

`base` holds the `HostAdapter` Protocol, the `Capability`/`HostEvent`/
`Outcome` shapes and `load_matrix`/`gate_mode`/`fingerprint_paths`.
`claude_code` is the one adapter with real behavior (.7 scope: launch
profile, pre-tool, post-tool output). `stubs` holds the five stand-ins for
Codex, Hermes, Kimi, Pi and bb, each reading its capabilities from the
checked-in matrix and deferring real behavior to a dependent bead.
"""

from __future__ import annotations

from .base import (
    FINGERPRINT_MAX_BYTES,
    FINGERPRINT_MAX_PATHS,
    LAUNCH_ARGV_TEMPLATE,
    Capability,
    FingerprintUnavailable,
    HostAdapter,
    HostEvent,
    Outcome,
    PointUnreachable,
    authorize_by_policy,
    emitted_outcome,
    fingerprint_paths,
    gate_mode,
    launch_argv_ok,
    load_matrix,
)
from .claude_code import ClaudeCodeAdapter
from .stubs import BbAdapter, CodexAdapter, HermesAdapter, KimiAdapter, PiAdapter

__all__ = [
    "Capability",
    "FINGERPRINT_MAX_BYTES",
    "FINGERPRINT_MAX_PATHS",
    "FingerprintUnavailable",
    "HostAdapter",
    "HostEvent",
    "LAUNCH_ARGV_TEMPLATE",
    "Outcome",
    "PointUnreachable",
    "authorize_by_policy",
    "emitted_outcome",
    "fingerprint_paths",
    "gate_mode",
    "launch_argv_ok",
    "load_matrix",
    "ClaudeCodeAdapter",
    "BbAdapter",
    "CodexAdapter",
    "HermesAdapter",
    "KimiAdapter",
    "PiAdapter",
]
