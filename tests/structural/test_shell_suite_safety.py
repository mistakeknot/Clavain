"""The shell suite must not touch shared host state.

Sylveste-psey: a scheduled run of tests/shell/ on a host where sessions live
deleted /tmp/intercore/locks/sprint-claim 84 times per run -- the production
mutual-exclusion namespace used by hooks/lib-sprint.sh, cmd/clavain-cli/claim.go,
hooks/lib-intercore.sh and Intercore's internal/lock/lock.go (DefaultBaseDir,
with no environment override anywhere in that package).

These checks are STATIC. They read source and never reproduce the deletion,
because demonstrating the old behaviour on a live host is the harm itself.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHELL_DIR = ROOT / "tests" / "shell"

# A literal /tmp path: /tmp/ not reached through a shell variable.
LITERAL_TMP = re.compile(r"(?<![\w$}])/tmp/")

# Writes to a literal /tmp path that are test-owned, distinctive and
# PID-scoped. Listed rather than silently tolerated so a new one is visible.
WRITE_ALLOWLIST = {
    ("dispatch_parser.bats", "STATE_FILE"): "PID-scoped, test-specific name, never executed",
    ("dispatch_parser.bats", "SUMMARY_FILE"): "PID-scoped, test-specific name, never executed",
}


def shell_files():
    files = sorted(SHELL_DIR.rglob("*.bats")) + sorted(SHELL_DIR.rglob("*.bash"))
    assert files, f"no shell suite files under {SHELL_DIR} — this test would pass vacuously"
    return files


def numbered(path):
    return list(enumerate(path.read_text().splitlines(), start=1))


def test_shell_dir_is_present_and_populated():
    """Anti-vacuity: every other check here scans files, so prove they exist."""
    files = shell_files()
    assert len(files) >= 40, f"expected the full shell suite, found {len(files)} files"


def test_no_removal_of_a_literal_tmp_path():
    """Class A. rm against a shared /tmp path can delete another session's state."""
    offenders = []
    for path in shell_files():
        for lineno, line in numbered(path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not re.search(r"\brm(dir)?\b", stripped):
                continue
            if LITERAL_TMP.search(stripped):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")
    assert not offenders, (
        "shell tests remove literal /tmp paths, which is shared host state:\n  "
        + "\n  ".join(offenders)
    )


def test_no_literal_tmp_path_is_executed_or_placed_on_path():
    """Class B. An ambient executable at a predictable /tmp path is attacker-writable,
    and a /tmp entry on PATH shadows the binaries the harness deliberately selected.

    The hazard usually arrives through a variable, not a literal, so this taints any
    name assigned a literal /tmp path and then flags its use in an execution context.
    A rule that only matched literals missed test_seam_integration.bats entirely.
    """
    danger = re.compile(r"\bPATH=|\bgo build\b|\bchmod \+x\b|\binstall -m\b")
    offenders = []
    for path in shell_files():
        tainted = set()
        for lineno, line in numbered(path):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assign = re.match(r"(?:local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)=\"?/tmp/", stripped)
            if assign:
                tainted.add(assign.group(1))
            hit = LITERAL_TMP.search(stripped) or any(
                re.search(r"\$\{?" + re.escape(name) + r"\b", stripped) for name in tainted
            )
            if hit and danger.search(stripped):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")
    assert not offenders, (
        "shell tests build, execute, or PATH-prepend a /tmp path:\n  "
        + "\n  ".join(offenders)
    )


def test_no_implicit_default_to_a_literal_tmp_binary():
    """Class C. ${VAR:-/tmp/...} silently executes whatever is at that path when
    VAR is unset, so selection must be explicit opt-in."""
    pattern = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-\s*/tmp/")
    offenders = []
    for path in shell_files():
        for lineno, line in numbered(path):
            if line.strip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "shell tests fall back to a literal /tmp path when a variable is unset:\n  "
        + "\n  ".join(offenders)
    )


def test_literal_tmp_writes_are_allowlisted():
    """Class D. Any remaining literal-/tmp write must be named here with a reason,
    so a new one is a test failure rather than an invisible addition."""
    offenders = []
    for path in shell_files():
        for lineno, line in numbered(path):
            stripped = line.strip()
            if stripped.startswith("#") or not LITERAL_TMP.search(stripped):
                continue
            assign = re.match(r"(?:local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)=\"?/tmp/", stripped)
            if not assign:
                continue
            key = (path.name, assign.group(1))
            if key not in WRITE_ALLOWLIST:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {stripped}")
    assert not offenders, (
        "shell tests assign a literal /tmp path without an allowlist entry:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("name", ["test_lib_sprint.bats", "test_b3_calibration.bats", "test_seam_integration.bats"])
def test_named_regressions_stay_fixed(name):
    """Pin the three specific sites Sylveste-we1q was filed for, by content, so a
    revert is caught even if the generic rules above are later relaxed.

    Comments are stripped first. A comment cannot delete a directory, and the
    fixes deliberately leave a note naming the path they no longer touch -- the
    record of why is worth more than a blunter pin.
    """
    text = "\n".join(
        line for line in (SHELL_DIR / name).read_text().splitlines()
        if not line.strip().startswith("#")
    )
    assert "/tmp/intercore/locks" not in text, f"{name} touches the production lock namespace"
    assert "/tmp/sprint-lock-" not in text, f"{name} removes retired global sprint lock globs"
    assert "/tmp/clavain-discovery-brief-" not in text, f"{name} removes retired global discovery caches"
    assert "/tmp/adaptive-routing-" not in text, f"{name} defaults to an ambient dated candidate path"
    assert "/tmp/ic-seam-" not in text, f"{name} builds an ambient binary under /tmp"
