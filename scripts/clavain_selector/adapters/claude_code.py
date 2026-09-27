"""Claude Code reference host adapter (mk-42j9.7 Task 6).

Implements points (a) `launch_profile`, (c) `pre_tool` and (d)
`post_tool_output` only, per the plan's "Host adapters" section. `render()`
never executes anything (point (a) returns an argv plan, not a subprocess
call) and never emits an "allow"/"approve" decision or `updatedInput` at
point (c) -- Claude Code's own permission pipeline is the only thing that
ever grants a tool call. In shadow mode (and for any native fallback)
`render()` returns empty bytes so the host proceeds exactly as it would
without this layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from clavain_selector import contract
from clavain_selector.contract import AuthorizationPolicy, Candidate, Point, ValidatedCandidates

from .base import (
    Capability,
    HostEvent,
    Outcome,
    PointUnreachable,
    authorize_by_policy,
    fingerprint_paths,
    load_matrix,
)

_IMPLEMENTED_POINTS = frozenset({Point.LAUNCH_PROFILE, Point.PRE_TOOL, Point.POST_TOOL_OUTPUT})
_JSON_SEPARATORS = (",", ":")


def _hash_payload(payload: Any) -> str:
    """`contract.payload_sha256`, kept as a thin local alias for callers already
    importing it from this module. No `except TypeError: repr(...)` fallback --
    a non-JSON-native value raises `ValueError` (from `contract.payload_bytes`)
    rather than silently hashing a `repr()` string instead.
    """
    return contract.payload_sha256(payload)


class ClaudeCodeAdapter:
    name = "claude-code"
    version = "1"

    def capabilities(self) -> dict[Point, Capability]:
        return load_matrix()[self.name]

    def detect(self, env: Mapping[str, str]) -> bool:
        return bool(env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"))

    def parse_event(self, point: Point, raw: bytes) -> HostEvent:
        if point not in _IMPLEMENTED_POINTS:
            raise PointUnreachable(f"claude-code adapter does not implement point {point.value}")
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise PointUnreachable(f"malformed claude-code event payload: {exc}") from exc
        return HostEvent(
            point=point,
            session_id=str(data.get("session_id", "")),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            tool_response=data.get("tool_response"),
            raw=data,
        )

    def render(self, point: Point, outcome: Outcome, event: HostEvent) -> bytes:
        if point == Point.LAUNCH_PROFILE:
            return self._render_launch(outcome)
        if point == Point.PRE_TOOL:
            return self._render_pre_tool(outcome)
        if point == Point.POST_TOOL_OUTPUT:
            return self._render_post_tool(outcome, event)
        raise PointUnreachable(f"claude-code adapter does not implement point {point.value}")

    def _render_launch(self, outcome: Outcome) -> bytes:
        if outcome.kind != "emitted":
            return b""
        # Never executes: this only assembles the argv Claude Code would run,
        # for a dependent bead's own launch orchestration to invoke (or not).
        argv = ["claude", "plugin", "enable", "--scope", "local"]
        if outcome.candidate is not None:
            argv.append(outcome.candidate.id)
        return json.dumps({"argv": argv}, separators=_JSON_SEPARATORS).encode("utf-8")

    def _render_pre_tool(self, outcome: Outcome) -> bytes:
        if outcome.kind in ("shadow", "native"):
            return b""
        # Emitted: the adapter may only ask or deny, expressed as a fixed
        # "ask" decision string -- never "allow"/"approve", and never an
        # updatedInput key (see the matrix's (c) limits entry).
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (outcome.fallback_reason or "")[:200],
            }
        }
        return json.dumps(payload, separators=_JSON_SEPARATORS).encode("utf-8")

    def _render_post_tool(self, outcome: Outcome, event: HostEvent) -> bytes:
        if outcome.kind in ("shadow", "native"):
            return b""
        # `outcome.render_bytes` is the exact, already-hash-checked payload
        # bytes (`__post_init__` on Outcome enforces payload_sha256/
        # binding_sha256 consistency) -- splice it in verbatim rather than
        # re-deriving a replacement shape from the live event.
        updated_tool_output = json.loads(outcome.render_bytes)
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": updated_tool_output,
            }
        }
        return json.dumps(payload, separators=_JSON_SEPARATORS).encode("utf-8")

    def authorize(self, chosen: Candidate, validated: ValidatedCandidates, policy: AuthorizationPolicy) -> bool:
        # Every adapter's authorize must delegate to this one payload-bound
        # rule verbatim -- Claude Code has no additional gate of its own to
        # apply here; its real permission pipeline runs independently and is
        # never influenced by this return value.
        return authorize_by_policy(chosen, validated, policy)

    def fingerprint(self, paths: Sequence[Path]) -> str:
        return fingerprint_paths(paths)

    def acknowledge(self, record: Mapping[str, Any], next_event: HostEvent) -> str:
        try:
            result = record.get("result") or {}
            if result.get("kind") != "selected":
                return "unknown"
            candidate_id = result.get("candidate_id")
            matched = next(
                (c for c in record.get("candidates", []) if c.get("id") == candidate_id),
                None,
            )
            if matched is None:
                return "unknown"
            expected_hash = matched.get("payload_sha256")
            if not expected_hash:
                return "unknown"
            observed_hash = contract.payload_sha256(next_event.tool_response)
            return "selected" if observed_hash == expected_hash else "original"
        except Exception:
            return "unknown"
