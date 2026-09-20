"""Absent `ic` must deselect visibly, never silently, and never vacuously.

Sylveste-psey: tests/structural/test_claude_usage.py has 29 cases; 28 of them
drive scripts/claude_usage.py, whose meter calls `ic --json route identity` and
fails closed when the binary is missing. A hosted runner has no `ic`, so from
75fed68 onward Tier 1 died before Tier 2 bats was ever reached.

The fix moves that coverage to a host that has `ic`; it must not evaporate.
These tests pin the three properties that distinguish moving from losing:
the marked set is exactly the dependent cases, absence is REPORTED rather than
silent, and a present-but-broken `ic` still runs and still fails.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parents[1]
ACCOUNTING = "structural/test_claude_usage.py"
EXPECTED_DEPENDENT = 28
EXPECTED_TOTAL = 29
IC_FREE_CASE = "test_zaka_rejected_before_any_model_call"


def run_pytest(args, path_dir=None, expect_ic=None):
    """Run pytest in a subprocess, optionally under a filtered PATH."""
    # path_dir=None means "the real environment", where ic is present. Setting
    # PATH="" there would deselect everything and make the baseline assertions
    # pass for the wrong reason.
    env = {
        "PATH": str(path_dir) if path_dir is not None else os.environ.get("PATH", ""),
        "HOME": str(TESTS_DIR),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if path_dir is not None and expect_ic is not None:
        # Prove the child really sees what this test intends it to see, rather
        # than trusting the PATH surgery. A filtered-PATH test that silently
        # kept finding ic would pass while testing nothing.
        probe = subprocess.run(
            [sys.executable, "-c", "import shutil;print(shutil.which('ic'))"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        seen = probe.stdout.strip()
        if expect_ic is False:
            assert seen == "None", f"child still resolves ic at {seen}; PATH filter failed"
        else:
            assert seen != "None", "child cannot see the ic stub this test installed"
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=TESTS_DIR, env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.fixture
def clean_bin(tmp_path):
    """A PATH containing the tools a pytest child needs, and no `ic`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("git", "bash", "sh", "uname", "env"):
        real = shutil.which(tool)
        if real:
            (bin_dir / tool).symlink_to(real)
    assert not (bin_dir / "ic").exists()
    return bin_dir


def test_the_accounting_file_still_has_the_expected_cohort():
    """Anti-vacuity. Every assertion below is relative to this cohort, so if the
    file is renamed or its parametrization changes, fail here and say so."""
    proc = run_pytest(["--collect-only", "-q", ACCOUNTING])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ids = [l for l in proc.stdout.splitlines() if l.startswith(ACCOUNTING + "::")]
    assert len(ids) == EXPECTED_TOTAL, f"expected {EXPECTED_TOTAL} cases, collected {len(ids)}"
    assert any(IC_FREE_CASE in i for i in ids), f"{IC_FREE_CASE} is missing"


def test_exactly_the_dependent_cases_carry_the_marker():
    """The marker must cover the 28 that need ic and must not cover the one that
    does not -- marking the module would take the ic-free case down with it."""
    marked = run_pytest(["--collect-only", "-q", "-m", "requires_ic", ACCOUNTING])
    assert marked.returncode == 0, marked.stdout + marked.stderr
    marked_ids = [l for l in marked.stdout.splitlines() if l.startswith(ACCOUNTING + "::")]
    assert len(marked_ids) == EXPECTED_DEPENDENT, (
        f"expected {EXPECTED_DEPENDENT} marked cases, got {len(marked_ids)}"
    )
    assert not any(IC_FREE_CASE in i for i in marked_ids), (
        f"{IC_FREE_CASE} needs no ic and must not be marked"
    )


def test_absent_ic_deselects_only_the_marked_cases_and_says_so(clean_bin):
    """Absence is a reported deselection, not a silent skip and not a failure."""
    proc = run_pytest(["--collect-only", "-q", ACCOUNTING],
                      path_dir=clean_bin, expect_ic=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ids = [l for l in proc.stdout.splitlines() if l.startswith(ACCOUNTING + "::")]
    assert len(ids) == EXPECTED_TOTAL - EXPECTED_DEPENDENT, (
        f"expected only the ic-free case to survive, got {len(ids)}: {ids}"
    )
    assert any(IC_FREE_CASE in i for i in ids), "the ic-free case was wrongly deselected"
    combined = proc.stdout + proc.stderr
    assert re.search(rf"{EXPECTED_DEPENDENT} tests? deselected", combined), (
        "the run does not state how many tests were held back:\n" + combined
    )
    assert "requires_ic" in combined and "ic executable not found on PATH" in combined, (
        "the run does not say WHY coverage was held back:\n" + combined
    )
    assert "zklw" in combined, (
        "the run does not say where the held-back coverage now runs:\n" + combined
    )


def test_require_ic_refuses_rather_than_deselecting(clean_bin):
    """On the designated host the same absence must be an error, so a lane that
    is supposed to carry this coverage cannot quietly report success without it."""
    proc = run_pytest(["--collect-only", "-q", "--require-ic", ACCOUNTING],
                      path_dir=clean_bin, expect_ic=False)
    assert proc.returncode != 0, "--require-ic passed with no ic on PATH:\n" + proc.stdout
    combined = proc.stdout + proc.stderr
    assert "require-ic" in combined or "requires_ic" in combined, combined


def test_a_present_but_broken_ic_is_not_deselected(tmp_path, clean_bin):
    """Deselection keys on presence, not on health. An ic that exits nonzero must
    stay selected and fail loudly -- otherwise a broken binary buys silence."""
    broken = clean_bin / "ic"
    broken.write_text("#!/usr/bin/env bash\nexit 1\n")
    broken.chmod(0o755)
    proc = run_pytest(["--collect-only", "-q", ACCOUNTING],
                      path_dir=clean_bin, expect_ic=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ids = [l for l in proc.stdout.splitlines() if l.startswith(ACCOUNTING + "::")]
    assert len(ids) == EXPECTED_TOTAL, (
        f"a present-but-broken ic changed selection: collected {len(ids)}"
    )
    assert "deselected" not in proc.stdout, "a broken ic must not deselect anything"


def test_unrelated_structural_tests_stay_selected_without_ic(clean_bin):
    """The deselection must be surgical: a mixed run keeps everything else."""
    proc = run_pytest(["--collect-only", "-q", "structural/"],
                      path_dir=clean_bin, expect_ic=False)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    ids = [l for l in proc.stdout.splitlines() if l.startswith("structural/")]
    others = [i for i in ids if not i.startswith(ACCOUNTING + "::")]
    assert len(others) > 500, f"unrelated coverage was lost: only {len(others)} other cases"
    assert not any(i.startswith(ACCOUNTING + "::") and IC_FREE_CASE not in i for i in ids)
