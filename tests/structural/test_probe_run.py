"""probe-run.sh: argument handling and exit semantics (no scope needed)."""
import os
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


@pytest.mark.parametrize("flag", ["--tasks", "--timeout"])
def test_missing_option_value(flag):
    assert run(flag).returncode == 2


def test_unknown_option():
    assert run("--bogus", "--", "true").returncode == 2


def scope_or_skip():
    """Skip when no user scope is available, unless PROBE_RUN_REQUIRE_SCOPE=1."""
    if not HAS_SCOPE:
        pytest.skip("needs systemd-run")
    r = run("--", "true")
    if r.returncode == 125:
        if os.environ.get("PROBE_RUN_REQUIRE_SCOPE") == "1":
            pytest.fail("scope required but unavailable: " + r.stderr)
        pytest.skip("user scope unavailable")


def test_exit_codes_pass_through():
    scope_or_skip()
    assert run("--", "true").returncode == 0
    assert run("--", "bash", "-c", "exit 7").returncode == 7
    r = run("--timeout", "1", "--", "sleep", "10")
    assert r.returncode == 124 and "timed out" in r.stderr
    # A probe that ignores SIGTERM is force-killed but still reports 124.
    r = run("--timeout", "1", "--", "bash", "-c", "trap '' TERM; sleep 30")
    assert r.returncode == 124


def test_cap_applies_to_descendants():
    scope_or_skip()
    code = (
        "cg=$(cut -d: -f3 /proc/self/cgroup); "
        "(cat /sys/fs/cgroup$cg/pids.max)"
    )
    r = run("--tasks", "64", "--", "bash", "-c", code)
    assert r.returncode == 0 and r.stdout.strip() == "64", r.stderr
    # Unbounded forking is stopped by the cap.
    r = run("--tasks", "16", "--timeout", "20", "--", "bash", "-c",
            "for i in $(seq 60); do sleep 20 & done; wait")
    assert r.returncode != 0
