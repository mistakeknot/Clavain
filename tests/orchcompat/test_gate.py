"""The strict gate (--orchcompat-require-ic) refuses to run without its tools.

A run that is meant to gate a change must not be able to pass by skipping the
fleet-reader tests (no yq) or the dispatch tests (no jq). Each case runs a
child pytest collection with a PATH that lacks one tool.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchlib as o  # noqa: E402


def _collect(tmp_path, tools, *flags):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for t in tools:
        src = shutil.which(t) if t != "ic" else o.real_ic()
        if src is None:
            pytest.skip(f"{t} not installed here")
        (bindir / t).symlink_to(src)
    env = o.hermetic_env(tmp_path / "home", bindir)
    env["PATH"] = str(bindir)  # only the listed tools
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)  # find pytest in the child
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only",
         str(o.HERE / "test_gate_probe.py"), *flags],
        env=env, cwd=o.ROOT, capture_output=True, text=True, timeout=90)


@pytest.mark.parametrize("missing,present", [("yq", ["ic", "jq"]), ("jq", ["ic", "yq"])])
def test_strict_gate_errors_when_a_tool_is_missing(tmp_path, missing, present):
    r = _collect(tmp_path, present, "--orchcompat-require-ic")
    assert r.returncode != 0
    assert f"required tool(s) not on PATH: {missing}" in (r.stdout + r.stderr)


def test_without_the_flag_a_missing_tool_is_announced_in_the_header(tmp_path):
    r = _collect(tmp_path, ["ic", "jq"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "MISSING yq" in r.stdout
