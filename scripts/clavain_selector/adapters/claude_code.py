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

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from clavain_selector.contract import Candidate, Point

from .base import Capability, HostEvent, Outcome, PointUnreachable, fingerprint_paths, load_matrix

_IMPLEMENTED_POINTS = frozenset({Point.LAUNCH_PROFILE, Point.PRE_TOOL, Point.POST_TOOL_OUTPUT})
_JSON_SEPARATORS = (",", ":")


def _hash_payload(payload: Any) -> str:
    """Same hashing convention as records._sha256_payload, reimplemented locally.

    acknowledge() needs to compare a live tool_response against a decision
    record's `candidates[].payload_sha256`, which records.py computed with
    this exact json.dumps(..., sort_keys=True, ensure_ascii=True,
    default=str) shape; duplicated here rather than imported so this adapter
    module stays independent of records.py's internals.
    """
    try:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        serialized = repr(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _shape_like(original: Any, payload: Any) -> Any:
    """Coerce `payload` into the same JSON shape `original` had (str vs. structured)."""
    if isinstance(original, str) and not isinstance(payload, str):
        return str(payload)
    return payload


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
        replacement = _shape_like(event.tool_response, outcome.render_payload)
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": replacement,
            }
        }
        return json.dumps(payload, separators=_JSON_SEPARATORS).encode("utf-8")

    def authorize(self, candidate: Candidate, event: HostEvent) -> bool:
        # Defers to Claude Code's own permission gate; this adapter never
        # grants anything on its own. `raw["authorized"]` is populated (if at
        # all) by whatever already ran the host's real gate before this call.
        return bool(event.raw.get("authorized", False))

    def fingerprint(self, paths: Sequence[Path]) -> str:
        return fingerprint_paths(paths)

    def acknowledge(self, record: Mapping[str, Any], next_event: HostEvent) -> str:
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
        observed_hash = _hash_payload(next_event.tool_response)
        return "selected" if observed_hash == expected_hash else "original"
