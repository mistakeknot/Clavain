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
    assert run("--", "/nonexistent/probe-cmd").returncode != 0


def test_runtime_limit_stops_whole_scope():
    scope_or_skip()
    marker = f"probe-run-marker-{os.getpid()}"
    code = f"(exec -a {marker} sleep 60) & wait"
    r = run("--timeout", "2", "--", "bash", "-c", code)
    assert r.returncode != 0
    left = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
    assert left.stdout.strip() == ""


def test_cap_applies_to_descendants():
    scope_or_skip()
    code = "cg=$(cut -d: -f3 /proc/self/cgroup); (cat /sys/fs/cgroup$cg/pids.max)"
    r = run("--tasks", "64", "--", "bash", "-c", code)
    assert r.returncode == 0 and r.stdout.strip() == "64", r.stderr
    prog = (
        "import subprocess\n"
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
