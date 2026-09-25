"""Tests for scripts/clavain_selector/adapters/ (mk-42j9.7 Task 6).

Only synthetic fixture data (tests/fixtures/selector/claude/*.json) is used;
no real transcript text is read or printed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from selector_helpers import make_candidate, selector_socket_guard  # noqa: F401

from clavain_selector.adapters import (
    BbAdapter,
    ClaudeCodeAdapter,
    CodexAdapter,
    HermesAdapter,
    HostEvent,
    KimiAdapter,
    Outcome,
    PiAdapter,
    PointUnreachable,
    fingerprint_paths,
    gate_mode,
    load_matrix,
)
from clavain_selector.contract import FallbackReason, Point

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "selector" / "claude"

_VALID_STATUSES = {"reachable", "partial", "unreachable", "unverified"}
_VALID_EVIDENCE_LEVELS = {"first_hand", "binary", "clavain_code", "sylveste_code", "docs", "none"}
_ALL_HOSTS = {"claude-code", "codex", "hermes", "kimi", "pi", "bb"}
_ALL_POINTS = {
    Point.LAUNCH_PROFILE,
    Point.PROMPT_SUBMIT,
    Point.PRE_TOOL,
    Point.POST_TOOL_OUTPUT,
    Point.PRE_COMPACT,
    Point.SESSION_START,
    Point.SKILL_LOADING,
}

_FORBIDDEN_SNIPPETS = ('"permissionDecision": "allow"', '"decision": "approve"', "updatedInput")


def _read_fixture(name: str) -> bytes:
    return (_FIXTURE_DIR / name).read_bytes()


def _hash_text(value: str) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------


def test_matrix_complete():
    matrix = load_matrix()
    assert set(matrix.keys()) == _ALL_HOSTS
    for host, points in matrix.items():
        assert set(points.keys()) == _ALL_POINTS, host
        for point, cap in points.items():
            assert cap.status in _VALID_STATUSES, (host, point)
            assert cap.evidence_level in _VALID_EVIDENCE_LEVELS, (host, point)
            assert isinstance(cap.mechanism, str)
            assert isinstance(cap.limits, str)
            assert cap.verified_on
            assert cap.verified_at

    claude = matrix["claude-code"]
    assert claude[Point.PRE_TOOL].status == "partial"
    assert claude[Point.PRE_TOOL].evidence_level == "binary"
    assert "adapters never emit updatedInput or allow" in claude[Point.PRE_TOOL].limits
    assert claude[Point.LAUNCH_PROFILE].evidence_level == "first_hand"

    kimi = matrix["kimi"]
    assert kimi[Point.PROMPT_SUBMIT].evidence_level == "sylveste_code"

    assert matrix["bb"][Point.PRE_TOOL].status == "unreachable"
    assert matrix["bb"][Point.PROMPT_SUBMIT].status == "unreachable"
    assert matrix["bb"][Point.POST_TOOL_OUTPUT].status == "unreachable"
    assert matrix["bb"][Point.LAUNCH_PROFILE].status == "reachable"
    assert matrix["kimi"][Point.POST_TOOL_OUTPUT].status == "unverified"
    assert matrix["hermes"][Point.PRE_COMPACT].status == "unverified"
    assert matrix["hermes"][Point.POST_TOOL_OUTPUT].evidence_level == "first_hand"


@pytest.mark.parametrize(
    "adapter_cls, host_name",
    [
        (CodexAdapter, "codex"),
        (HermesAdapter, "hermes"),
        (KimiAdapter, "kimi"),
        (PiAdapter, "pi"),
        (BbAdapter, "bb"),
    ],
)
def test_stub_capabilities_match_matrix(adapter_cls, host_name):
    matrix = load_matrix()
    adapter = adapter_cls()
    assert adapter.capabilities() == matrix[host_name]


def test_unreachable_raises():
    with pytest.raises(PointUnreachable):
        BbAdapter().parse_event(Point.PRE_TOOL, b"{}")
    with pytest.raises(PointUnreachable):
        KimiAdapter().parse_event(Point.POST_TOOL_OUTPUT, b"{}")


# ---------------------------------------------------------------------------
# Claude Code adapter: render()
# ---------------------------------------------------------------------------


def test_render_never_allows():
    adapter = ClaudeCodeAdapter()
    pre_tool_event = adapter.parse_event(Point.PRE_TOOL, _read_fixture("pre_tool.json"))
    post_tool_event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    candidate = make_candidate(id="cand-a", payload="replacement text")

    outcomes = [
        Outcome(kind="shadow"),
        Outcome(kind="native", fallback_reason=FallbackReason.POINT_UNREACHABLE.value),
        Outcome(kind="native", fallback_reason=FallbackReason.EGRESS_REFUSED.value),
        Outcome(kind="native", fallback_reason=FallbackReason.LOW_CONFIDENCE.value),
        Outcome(kind="native", fallback_reason=FallbackReason.UNAUTHORIZED.value),
        Outcome(kind="emitted", mode="active", candidate=candidate, render_payload="replacement text"),
    ]
    for point, event in (
        (Point.LAUNCH_PROFILE, pre_tool_event),
        (Point.PRE_TOOL, pre_tool_event),
        (Point.POST_TOOL_OUTPUT, post_tool_event),
    ):
        for outcome in outcomes:
            rendered = adapter.render(point, outcome, event).decode("utf-8")
            for snippet in _FORBIDDEN_SNIPPETS:
                assert snippet not in rendered, (point, outcome.kind, snippet)


def test_post_tool_render_shape():
    adapter = ClaudeCodeAdapter()
    event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    assert isinstance(event.tool_response, str)

    candidate = make_candidate(id="cand-shape", payload="replacement text")
    outcome = Outcome(kind="emitted", mode="active", candidate=candidate, render_payload="replacement text")
    rendered = json.loads(adapter.render(Point.POST_TOOL_OUTPUT, outcome, event))
    replacement = rendered["hookSpecificOutput"]["updatedToolOutput"]
    assert isinstance(replacement, type(event.tool_response))
    assert replacement == "replacement text"

    record = {
        "result": {"kind": "selected", "candidate_id": "cand-shape"},
        "candidates": [{"id": "cand-shape", "payload_sha256": _hash_text("replacement text")}],
    }
    original_next_event = HostEvent(
        point=Point.POST_TOOL_OUTPUT, session_id="sess-fake-0001", tool_response=event.tool_response
    )
    selected_next_event = HostEvent(
        point=Point.POST_TOOL_OUTPUT, session_id="sess-fake-0001", tool_response="replacement text"
    )
    assert adapter.acknowledge(record, original_next_event) == "original"
    assert adapter.acknowledge(record, selected_next_event) == "selected"


def test_shadow_render_is_empty():
    adapter = ClaudeCodeAdapter()
    pre_tool_event = adapter.parse_event(Point.PRE_TOOL, _read_fixture("pre_tool.json"))
    post_tool_event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    shadow = Outcome(kind="shadow")
    assert adapter.render(Point.PRE_TOOL, shadow, pre_tool_event) == b""
    assert adapter.render(Point.POST_TOOL_OUTPUT, shadow, post_tool_event) == b""


def test_launch_render_does_not_execute(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("render() must never execute a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)

    adapter = ClaudeCodeAdapter()
    candidate = make_candidate(id="profile-x")
    outcome = Outcome(kind="emitted", mode="active", candidate=candidate)
    event = HostEvent(point=Point.LAUNCH_PROFILE, session_id="sess-fake-0001")
    rendered = json.loads(adapter.render(Point.LAUNCH_PROFILE, outcome, event))
    assert isinstance(rendered["argv"], list)
    assert rendered["argv"][0] == "claude"
    assert "profile-x" in rendered["argv"]


def test_active_requires_first_hand():
    matrix = load_matrix()
    codex_launch = matrix["codex"][Point.LAUNCH_PROFILE]
    assert codex_launch.status == "reachable"
    assert codex_launch.evidence_level == "docs"
    assert gate_mode(codex_launch, "shadow") is None
    assert gate_mode(codex_launch, "active") == FallbackReason.POINT_UNREACHABLE

    claude_launch = matrix["claude-code"][Point.LAUNCH_PROFILE]
    assert claude_launch.evidence_level == "first_hand"
    assert gate_mode(claude_launch, "active") is None

    bb_pre_tool = matrix["bb"][Point.PRE_TOOL]
    assert gate_mode(bb_pre_tool, "shadow") == FallbackReason.POINT_UNREACHABLE


def test_parse_event_fixtures():
    adapter = ClaudeCodeAdapter()
    pre_event = adapter.parse_event(Point.PRE_TOOL, _read_fixture("pre_tool.json"))
    assert pre_event.tool_name == "Bash"
    assert pre_event.session_id == "sess-fake-0001"
    assert pre_event.tool_input["command"] == "echo hello"

    post_event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    assert post_event.tool_name == "Bash"
    assert post_event.session_id == "sess-fake-0001"
    assert post_event.tool_response == "hello\n"


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("alpha")
    f2.write_text("beta")

    fp1 = fingerprint_paths([f1, f2])
    fp2 = fingerprint_paths([f1, f2])
    assert fp1 == fp2

    # Same-size, same-second rewrite with different content: restoring the
    # mtime afterward must not hide the change (content hash differs).
    st_before = f1.stat()
    f1.write_text("ALPHA")
    os.utime(f1, ns=(st_before.st_atime_ns, st_before.st_mtime_ns))
    fp3 = fingerprint_paths([f1, f2])
    assert fp3 != fp1

    # Replace-by-rename changes the inode even if content matches again.
    f1_new = tmp_path / "a_new.txt"
    f1_new.write_text("ALPHA")
    os.replace(f1_new, f1)
    fp4 = fingerprint_paths([f1, f2])
    assert fp4 != fp3

    # A missing file is fingerprinted as missing, not skipped.
    missing = tmp_path / "missing.txt"
    fp_with_missing = fingerprint_paths([f1, f2, missing])
    fp_without = fingerprint_paths([f1, f2])
    assert fp_with_missing != fp_without
