"""Tests for hooks/hooks.json configuration."""

import re


VALID_EVENT_TYPES = {
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "UserPromptSubmit",
}

# Exact event types Clavain should register
EXPECTED_EVENT_TYPES = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SessionEnd",
    "UserPromptSubmit",
}


def test_hooks_json_valid(hooks_json):
    """hooks.json is a valid dict with a 'hooks' key."""
    assert isinstance(hooks_json, dict)
    assert "hooks" in hooks_json


def test_hooks_json_event_types(hooks_json):
    """All hook event types are valid Claude Code hook events."""
    for event_type in hooks_json["hooks"]:
        assert event_type in VALID_EVENT_TYPES, (
            f"Unknown event type: {event_type!r}. "
            f"Valid types: {VALID_EVENT_TYPES}"
        )


def test_hooks_json_expected_event_types(hooks_json):
    """hooks.json registers exactly the expected event types."""
    actual = set(hooks_json["hooks"].keys())
    assert actual == EXPECTED_EVENT_TYPES, (
        f"Expected event types {EXPECTED_EVENT_TYPES}, got {actual}"
    )


def test_hooks_json_commands_exist(hooks_json, project_root):
    """Every .sh path in hooks.json resolves to a real file."""
    for event_type, hook_groups in hooks_json["hooks"].items():
        for group in hook_groups:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                # Extract the .sh path from the command string
                # Commands may be: bash "${CLAUDE_PLUGIN_ROOT}/hooks/foo.sh"
                # or: ${CLAUDE_PLUGIN_ROOT}/hooks/foo.sh
                # Strip bash prefix and quotes
                path_str = command
                path_str = path_str.replace('bash ', '').strip()
                path_str = path_str.strip('"').strip("'")
                path_str = path_str.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                resolved = project_root / path_str
                assert resolved.exists(), (
                    f"Hook command references non-existent file: {command} "
                    f"(resolved to {resolved})"
                )


def test_hooks_json_timeouts_reasonable(hooks_json):
    """All timeout values are <= 30 seconds."""
    for event_type, hook_groups in hooks_json["hooks"].items():
        for group in hook_groups:
            for hook in group.get("hooks", []):
                timeout = hook.get("timeout")
                if timeout is not None:
                    assert timeout <= 30, (
                        f"Timeout {timeout} for {event_type} exceeds 30s"
                    )


def test_hooks_json_matchers_valid(hooks_json):
    """All matcher values compile as valid regex."""
    for event_type, hook_groups in hooks_json["hooks"].items():
        for group in hook_groups:
            matcher = group.get("matcher")
            if matcher is not None:
                try:
                    re.compile(matcher)
                except re.error as e:
                    raise AssertionError(
                        f"Invalid regex matcher {matcher!r} in {event_type}: {e}"
                    )


def test_user_prompt_submit_has_one_bounded_context_gateway(hooks_json):
    hooks = [
        hook
        for group in hooks_json["hooks"]["UserPromptSubmit"]
        for hook in group.get("hooks", [])
        if "context-gateway.sh" in hook.get("command", "")
    ]
    assert len(hooks) == 1
    assert hooks[0]["type"] == "command"
    assert 0 < hooks[0]["timeout"] <= 30


def test_session_start_interserve_injection(project_root):
    """session-start.sh contains the interserve behavioral contract injection."""
    session_start = project_root / "hooks" / "session-start.sh"
    content = session_start.read_text()
    assert "INTERSERVE MODE" in content, (
        "session-start.sh should contain 'INTERSERVE MODE' for behavioral contract injection"
    )


def test_session_end_calibration_hook_closes_core_loops(project_root):
    """SessionEnd calibration refreshes gate tiers and phase-cost estimates."""
    hook = project_root / "hooks" / "gate-calibration-session-end.sh"
    content = hook.read_text()
    assert "calibrate-gate-tiers --auto" in content
    assert "calibrate-phase-costs" in content
    assert "timeout" in content


def test_session_end_calibration_hook_records_evidence_receipts(project_root):
    """SessionEnd advances A:L3 proof only through evidence receipts."""
    hook = project_root / "hooks" / "gate-calibration-session-end.sh"
    content = hook.read_text()
    assert "calibration-streak record-receipt" in content
    assert "calibration-streak record-session-end" not in content
    assert "calibration-streak status --json" in content


def test_reflect_command_leaves_receipted_calibration_to_session_end(project_root):
    """Normal reflect cannot mutate artifacts outside the receipt boundary."""
    reflect = project_root / "commands" / "reflect.md"
    content = reflect.read_text()
    assert "calibration-streak record-manual" not in content
    assert "calibrate-phase-costs" not in content
    assert "_interspect_write_routing_calibration" not in content


def test_status_command_reports_calibration_streak(project_root):
    """Unified status includes the A:L3 no-touch streak surface."""
    status = project_root / "commands" / "clavain-status.md"
    content = status.read_text()
    assert "clavain-cli calibration-streak status" in content
