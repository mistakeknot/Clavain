"""Tests for resolve.py — AI conflict resolution via claude -p."""
import json
from unittest.mock import patch, MagicMock
from clavain_sync.resolve import analyze_conflict, ConflictDecision


def _mock_claude_result(decision="accept_upstream", risk="low", rationale="test"):
    return json.dumps({
        "decision": decision,
        "risk": risk,
        "rationale": rationale,
        "blocklist_found": [],
    })


@patch("clavain_sync.resolve.shutil.which", return_value="/usr/bin/claude")
@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_returns_parsed_decision(mock_run, mock_which):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_mock_claude_result("accept_upstream", "low", "Changes are orthogonal"),
    )
    result = analyze_conflict(
        local_path="skills/foo.md",
        local_content="local version",
        upstream_content="upstream version",
        ancestor_content="ancestor version",
        blocklist=["rails_model"],
    )
    assert result.decision == "accept_upstream"
    assert result.risk == "low"


@patch("clavain_sync.resolve.shutil.which", return_value="/usr/bin/claude")
@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_falls_back_on_failure(mock_run, mock_which):
    mock_run.side_effect = Exception("claude not found")
    result = analyze_conflict(
        local_path="skills/foo.md",
        local_content="local",
        upstream_content="upstream",
        ancestor_content="ancestor",
        blocklist=[],
    )
    assert result.decision == "needs_human"
    assert result.risk == "high"


@patch("clavain_sync.resolve.shutil.which", return_value="/usr/bin/claude")
@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_falls_back_on_bad_json(mock_run, mock_which):
    mock_run.return_value = MagicMock(returncode=0, stdout="not json")
    result = analyze_conflict(
        local_path="skills/foo.md",
        local_content="local",
        upstream_content="upstream",
        ancestor_content="ancestor",
        blocklist=[],
    )
    assert result.decision == "needs_human"


@patch("clavain_sync.resolve.shutil.which", return_value="/usr/bin/claude")
@patch("clavain_sync.resolve.subprocess.run")
def test_analyze_passes_blocklist_to_prompt(mock_run, mock_which):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_mock_claude_result(),
    )
    analyze_conflict(
        local_path="skills/foo.md",
        local_content="local",
        upstream_content="upstream",
        ancestor_content="ancestor",
        blocklist=["rails_model", "Every.to"],
    )
    # Verify the prompt sent to claude includes blocklist
    call_args = mock_run.call_args
    stdin_text = call_args.kwargs.get("input", "") or call_args[1].get("input", "")
    assert "rails_model" in stdin_text
    assert "Every.to" in stdin_text


def test_analyze_falls_back_when_claude_missing():
    """When claude binary is not in PATH, return fallback without shelling out."""
    with patch("clavain_sync.resolve.shutil.which", return_value=None):
        result = analyze_conflict(
            local_path="skills/foo.md",
            local_content="local",
            upstream_content="upstream",
            ancestor_content="ancestor",
            blocklist=[],
        )
    assert result.decision == "needs_human"
    assert result.risk == "high"
