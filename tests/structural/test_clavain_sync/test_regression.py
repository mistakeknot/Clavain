"""Regression test: verify Python sync produces same classifications as bash.

This test runs both versions in dry-run mode against the real upstreams
and compares their classification output. Requires upstreams to be cloned.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _has_upstreams():
    """Check if upstream clones exist."""
    for d in [PROJECT_ROOT / ".upstream-work", Path("/root/projects/upstreams")]:
        if d.is_dir():
            return True
    return False


@pytest.mark.skipif(not _has_upstreams(), reason="Upstream clones not available")
def test_python_matches_bash_classifications():
    """Run both bash and Python in dry-run, compare classification counts."""
    # Run bash version
    bash_result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "sync-upstreams.sh"), "--dry-run"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        env={**os.environ, "NO_COLOR": "1"},
    )

    # Run Python version
    python_result = subprocess.run(
        ["python3", "-m", "clavain_sync", "sync", "--dry-run"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "scripts"), "NO_COLOR": "1"},
    )

    # Extract classification lines from both
    cls_pattern = re.compile(r"(COPY|AUTO|KEEP|SKIP|CONFLICT|REVIEW)\s+(\S+)")

    bash_cls = set(cls_pattern.findall(bash_result.stdout))
    python_cls = set(cls_pattern.findall(python_result.stdout))

    # They should produce the same classifications
    missing_in_python = bash_cls - python_cls
    extra_in_python = python_cls - bash_cls

    assert not missing_in_python, f"Bash had these but Python didn't: {missing_in_python}"
    assert not extra_in_python, f"Python had these but bash didn't: {extra_in_python}"
