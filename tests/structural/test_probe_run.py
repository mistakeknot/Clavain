"""probe-run.sh: argument handling and exit semantics (no scope needed)."""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "probe-run.sh"
HAS_SCOPE = shutil.which("systemd-run") is not None


def run(*args):
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, timeout=60)


def test_requires_command():
    assert run().returncode == 2
    assert run("--").returncode == 2


@pytest.mark.parametrize("flag", ["--tasks", "--timeout"])
def test_rejects_bad_numbers(flag):
    assert run(flag, "abc", "--", "true").returncode == 2
    assert run(flag, "0", "--", "true").returncode == 2


def test_unknown_option():
    assert run("--bogus", "--", "true").returncode == 2


@pytest.mark.skipif(not HAS_SCOPE, reason="needs systemd-run")
def test_exit_codes_pass_through():
    try:
        ok = run("--", "true")
    except subprocess.TimeoutExpired:
        pytest.skip("scope unavailable")
    if ok.returncode == 125 or "Failed to" in ok.stderr:
        pytest.skip("user scope unavailable")
    assert ok.returncode == 0
    assert run("--", "bash", "-c", "exit 7").returncode == 7
    r = run("--timeout", "1", "--", "sleep", "10")
    assert r.returncode == 124 and "timed out" in r.stderr
