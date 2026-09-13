"""Follow-up to the frozen --apply acceptance: three defects the validation
seat found in c03442c (register, goal 5bdf10a5), each red before the fix.

1. A fence timeout was recorded as a match under `Expected: prints NOTHING`
   and `Expected: exit 124`; only the bare exit-0 default treated it as failure.
2. A shell fence under a `### Verify` heading was skipped silently when the
   old classification heuristic did not call it a verify (no hint word within
   four prose lines and a first command outside the fixed list).
3. The revert hint listed created files under `git checkout --`, which exits 1
   with a pathspec error and reverts nothing, including the edited file.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from test_plan_gauge_apply import (  # noqa: F401  (fixture re-export)
    APP, COMMIT, HEAD, PRE_OK, TASK1, TASK2_MISMATCH, VERIFY1_OK, repo, run, write,
)


def test_timeout_is_a_mismatch_under_every_expectation(repo: Path):
    for expected in ("prints NOTHING", "exit 124", "exit 0"):
        plan = (
            HEAD + PRE_OK + TASK1
            + "### Verify Task 1\n\n```bash\nsleep 3\n```\n\nExpected: " + expected + "\n\n"
            + COMMIT
        )
        subprocess.run(["git", "checkout", "--", "."], cwd=repo, check=True)
        (repo / "src" / "new_module.py").unlink(missing_ok=True)
        r = run("--apply", "--repo-root", str(repo), "--timeout", "1", str(write(repo, plan)))
        assert r.returncode == 5, (expected, r.stdout + r.stderr)
        assert "timed out" in r.stdout + r.stderr


def test_verify_fence_far_below_its_heading_still_runs(repo: Path):
    plan = (
        HEAD + PRE_OK + TASK1
        + "### Verify Task 1\n\nThis fence starts with an interpreter the old\n"
        "heuristic does not list, and it sits below five lines of prose,\n"
        "none of which carries a hint word.\nLine four.\nLine five.\n\n"
        "```bash\npython3 -c 'import sys; sys.exit(7)'\n```\n\nExpected: exit 0\n\n"
        + COMMIT
    )
    r = run("--apply", "--repo-root", str(repo), "--json", str(write(repo, plan)))
    assert r.returncode == 5, r.stdout + r.stderr
    assert "Verify Task 1" in r.stdout + r.stderr
    assert "rc=7" in r.stdout + r.stderr


def test_revert_hint_separates_edited_and_created_files(repo: Path):
    plan = HEAD + PRE_OK + TASK1 + VERIFY1_OK + TASK2_MISMATCH + COMMIT
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 4, r.stdout + r.stderr
    text = r.stdout + r.stderr
    checkout = re.search(r"git checkout -- ([^\n]*)", text)
    assert checkout, text
    assert "src/app.py" in checkout.group(1)
    assert "src/new_module.py" not in checkout.group(1)
    assert re.search(r"rm -f [^\n]*src/new_module\.py", text), text
    # and the hint actually works
    subprocess.run(["bash", "-c", checkout.group(0)], cwd=repo, check=True)
    assert (repo / "src" / "app.py").read_text() == APP
