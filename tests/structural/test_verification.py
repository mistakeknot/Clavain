"""Unit tests for scripts/_verification.py (vendored from interflux).

Mirrors interflux/scripts/tests/test_verification.py — keep in sync when the
upstream primitive changes. Adds an extra test for the Bash-callable `emit`
subcommand that lib-routing.sh depends on.

Run from the Clavain repo root:
    cd os/Clavain/tests && uv run pytest structural/test_verification.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Tier 1 pyproject sets pythonpath = ["structural", "../scripts"] so the
# vendored primitive imports cleanly without manipulating sys.path here.
import _verification as v  # noqa: E402

SCRIPT = str(
    Path(__file__).resolve().parent.parent.parent / "scripts" / "_verification.py"
)


# --- factory constructors --------------------------------------------------


def test_verified_factory() -> None:
    s = v.VerificationStep.verified("test", "ok")
    assert s.state == v.VerificationState.VERIFIED
    assert s.is_success() is True


def test_failed_factory() -> None:
    s = v.VerificationStep.failed("test", "did not hold")
    assert s.state == v.VerificationState.FAILED_VERIFICATION
    assert s.is_success() is False


def test_unverifiable_factory() -> None:
    s = v.VerificationStep.unverifiable("test", "no data")
    assert s.state == v.VerificationState.UNVERIFIABLE
    assert s.is_success() is False  # critical invariant: UNVERIFIABLE != success


def test_unverifiable_is_not_success() -> None:
    """UNVERIFIABLE must NOT be treated as success — this is the core invariant."""
    s = v.VerificationStep.unverifiable("X", "Y")
    assert s.is_success() is False


# --- field validation ------------------------------------------------------


def test_state_must_be_enum() -> None:
    with pytest.raises(TypeError, match="state must be VerificationState"):
        v.VerificationStep(name="x", state="VERIFIED", evidence="y")  # type: ignore[arg-type]


def test_name_required_non_empty() -> None:
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        v.VerificationStep.verified("", "evidence")


def test_evidence_must_be_string() -> None:
    with pytest.raises(ValueError, match="evidence must be a string"):
        v.VerificationStep.verified("name", 42)  # type: ignore[arg-type]


def test_frozen_dataclass() -> None:
    """Steps are immutable — accidentally mutating evidence post-emit is a bug."""
    s = v.VerificationStep.verified("name", "ev")
    with pytest.raises(Exception):  # FrozenInstanceError
        s.evidence = "changed"  # type: ignore[misc]


# --- decision_type + extras ------------------------------------------------


def test_decision_type_recorded() -> None:
    s = v.VerificationStep.verified(
        "microrouter-passthrough",
        "matched B3 calibration",
        decision_type="passthrough",
    )
    d = s.to_dict()
    assert d["decision_type"] == "passthrough"


def test_extras_preserved_in_dict() -> None:
    s = v.VerificationStep.verified("name", "ev", slug="fd-x", tier="sonnet")
    d = s.to_dict()
    assert d["extra"] == {"slug": "fd-x", "tier": "sonnet"}


# --- run_uuid auto-population from env ------------------------------------


def test_run_uuid_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLUX_RUN_UUID", "run-abc-123")
    s = v.VerificationStep.verified("name", "ev")
    assert s.run_uuid == "run-abc-123"


def test_run_uuid_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLUX_RUN_UUID", "env-uuid")
    s = v.VerificationStep.verified("name", "ev", run_uuid="explicit-uuid")
    assert s.run_uuid == "explicit-uuid"


def test_run_uuid_none_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLUX_RUN_UUID", raising=False)
    s = v.VerificationStep.verified("name", "ev")
    assert s.run_uuid is None


# --- auto-populated fields ------------------------------------------------


def test_step_id_unique() -> None:
    a = v.VerificationStep.verified("x", "y")
    b = v.VerificationStep.verified("x", "y")
    assert a.step_id != b.step_id


def test_timestamp_populated() -> None:
    before = int(time.time() * 1000)
    s = v.VerificationStep.verified("x", "y")
    after = int(time.time() * 1000)
    assert before <= s.timestamp_ms <= after


# --- serialization --------------------------------------------------------


def test_to_dict_drops_none() -> None:
    """Compactness: don't bloat the JSONL with None fields."""
    s = v.VerificationStep.verified("x", "y")  # decision_type / run_uuid are None
    d = s.to_dict()
    assert "decision_type" not in d
    assert "run_uuid" not in d


def test_to_dict_drops_empty_extra() -> None:
    s = v.VerificationStep.verified("x", "y")
    d = s.to_dict()
    assert "extra" not in d


def test_to_dict_state_is_string() -> None:
    """Enum should render as its bare string value, not 'VerificationState.VERIFIED'."""
    s = v.VerificationStep.verified("x", "y")
    d = s.to_dict()
    assert d["state"] == "VERIFIED"


def test_to_jsonl_line_parseable() -> None:
    s = v.VerificationStep.verified("x", "y", decision_type="passthrough", slug="fd-a")
    line = s.to_jsonl_line()
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed["state"] == "VERIFIED"
    assert parsed["decision_type"] == "passthrough"
    assert parsed["extra"] == {"slug": "fd-a"}


def test_jsonl_compact_separator() -> None:
    """Compact separator: no spaces in (',', ':')."""
    s = v.VerificationStep.verified("x", "y")
    line = s.to_jsonl_line()
    assert ", " not in line
    assert ": " not in line


# --- append_to_log -------------------------------------------------------


def test_append_to_log_creates_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "decisions.jsonl"
    v.append_to_log(v.VerificationStep.verified("a", "1"), str(log))
    v.append_to_log(v.VerificationStep.failed("b", "2"), str(log))
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "a"
    assert json.loads(lines[1])["state"] == "FAILED_VERIFICATION"


def test_append_to_log_appends_existing(tmp_path: Path) -> None:
    log = tmp_path / "decisions.jsonl"
    log.write_text('{"name":"prior"}\n')
    v.append_to_log(v.VerificationStep.verified("new", "ev"), str(log))
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "prior"
    assert json.loads(lines[1])["name"] == "new"


# --- canonical use case: microrouter no-op short-circuit (Sylveste-a5u) ---


def test_microrouter_passthrough_audit() -> None:
    """The exact pattern that closes Sylveste-a5u — record the short-circuit."""
    s = v.VerificationStep.verified(
        "microrouter-passthrough",
        evidence="matched B3 calibration:sonnet for fd-architecture",
        decision_type="passthrough",
    )
    d = s.to_dict()
    assert d["decision_type"] == "passthrough"
    assert "matched B3 calibration" in d["evidence"]
    assert d["state"] == "VERIFIED"


def test_microrouter_endpoint_unreachable_audit() -> None:
    """Endpoint failure: record as UNVERIFIABLE (must trigger fail-closed downstream)."""
    s = v.VerificationStep.unverifiable(
        "microrouter-shadow-log",
        evidence="interspect endpoint unreachable: connection refused",
        decision_type="endpoint-unreachable",
    )
    assert s.is_success() is False  # critical: fail-closed for privacy
    d = s.to_dict()
    assert d["state"] == "UNVERIFIABLE"


# --- CLI ------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_demo_emits_three_lines() -> None:
    result = _run_cli("--demo")
    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 3
    states = {json.loads(line)["state"] for line in lines}
    assert states == {"VERIFIED", "FAILED_VERIFICATION", "UNVERIFIABLE"}


def test_cli_no_args_prints_help() -> None:
    result = _run_cli()
    assert result.returncode == 0
    assert "VerificationStep" in result.stderr


# --- emit subcommand (Bash-callable bridge) -------------------------------


def test_cli_emit_to_stdout() -> None:
    """Bash bridge: omit --log-path, get the JSONL line on stdout."""
    result = _run_cli(
        "emit",
        "--name", "calibration-passthrough",
        "--state", "VERIFIED",
        "--evidence", "matched B3 calibration:sonnet for fd-architecture",
        "--decision-type", "passthrough",
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert parsed["name"] == "calibration-passthrough"
    assert parsed["state"] == "VERIFIED"
    assert parsed["decision_type"] == "passthrough"


def test_cli_emit_to_log_path(tmp_path: Path) -> None:
    """Bash bridge: with --log-path, append to file and write nothing to stdout."""
    log = tmp_path / "subdir" / "shadow.jsonl"  # parent dir doesn't exist yet
    result = _run_cli(
        "emit",
        "--name", "x",
        "--state", "VERIFIED",
        "--evidence", "ev",
        "--log-path", str(log),
    )
    assert result.returncode == 0
    assert result.stdout == ""  # silent on success
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["name"] == "x"


def test_cli_emit_appends(tmp_path: Path) -> None:
    log = tmp_path / "shadow.jsonl"
    log.write_text('{"name":"prior"}\n')
    result = _run_cli(
        "emit",
        "--name", "new",
        "--state", "VERIFIED",
        "--evidence", "ev",
        "--log-path", str(log),
    )
    assert result.returncode == 0
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "prior"
    assert json.loads(lines[1])["name"] == "new"


def test_cli_emit_rejects_invalid_state() -> None:
    result = _run_cli(
        "emit",
        "--name", "x",
        "--state", "MAYBE",
        "--evidence", "ev",
    )
    assert result.returncode != 0


def test_cli_emit_picks_up_run_uuid_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLUX_RUN_UUID", "env-pickup-456")
    log = tmp_path / "shadow.jsonl"
    result = _run_cli(
        "emit",
        "--name", "x",
        "--state", "VERIFIED",
        "--evidence", "ev",
        "--log-path", str(log),
    )
    assert result.returncode == 0
    parsed = json.loads(log.read_text().strip())
    assert parsed["run_uuid"] == "env-pickup-456"
