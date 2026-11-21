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
    required = os.environ.get("PROBE_RUN_REQUIRE_SCOPE") == "1"
    if not HAS_SCOPE:
        if required:
            pytest.fail("scope required but systemd-run is missing")
        pytest.skip("needs systemd-run")
    r = run("--", "true")
    if r.returncode == 125:
        if required:
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
    # Unbounded forking is refused by the cap, observed from inside the probe.
    prog = (
        "import subprocess,sys\n"
        "kids=[]; refused=0\n"
        "for _ in range(100):\n"
        "    try: kids.append(subprocess.Popen(['sleep','20']))\n"
        "    except OSError: refused+=1; break\n"
        "for k in kids: k.kill()\n"
        "print('REFUSED' if refused else 'UNBOUNDED', len(kids))\n"
    )
    r = run("--tasks", "16", "--timeout", "60", "--", "python3", "-c", prog)
    assert r.returncode == 0 and r.stdout.startswith("REFUSED"), r.stdout + r.stderr
    assert int(r.stdout.split()[1]) < 16


def test_independent_137_is_not_a_timeout():
    scope_or_skip()
    r = run("--timeout", "30", "--", "bash", "-c", "sleep 2; exit 137")
    assert r.returncode == 137 and "timed out" not in r.stderr


def test_timeout_wins_even_if_probe_exits_zero_and_descendants_die():
    scope_or_skip()
    code = "trap 'exit 0' TERM; (trap '' TERM; sleep 30) & wait"
    r = run("--timeout", "1", "--", "bash", "-c", code)
    assert r.returncode == 124
    leftover = subprocess.run(["pgrep", "-fx", "sleep 30"], capture_output=True, text=True)
    assert leftover.stdout.strip() == ""


def test_missing_command_is_a_probe_failure_not_scope_failure():
    scope_or_skip()
    assert run("--", "/nonexistent/probe-cmd").returncode == 127
