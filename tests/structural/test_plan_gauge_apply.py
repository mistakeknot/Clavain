"""Acceptance for ``plan-gauge-lint.py --apply``: an exact contract applied and
replayed by the tool, so an exact plan needs no executor model.

Frozen before the executor was dispatched (replay-channel goal, 2026-09-06).
Every test builds a small git repo, writes a plan in the exact-contract
grammar from skills/executing-plans/references/pattern-f-contracts.md, and
runs the script as a subprocess, the way the gate and the orchestrator do.

Exit codes under --apply: 0 applied and every verify matched; 1 the gauge
found defects (nothing applied); 2 usage; 3 refused before any edit (brief
contract, dirty targets, failed preconditions); 4 an edit did not anchor
(old_string not found exactly once, or Create over an existing file); 5 a
verify fence did not meet its Expected line. On 4 and 5 the tree may be
partially edited and the output says how to revert.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan-gauge-lint.py"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=repo, capture_output=True, text=True, check=True)


APP = 'def greet():\n    return "hi"\n'
OTHER = "X = 2\n"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(APP)
    (tmp_path / "src" / "other.py").write_text(OTHER)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


HEAD = "# Plan: apply demo\n\nContract: exact\n\n"
PRE_OK = "## Preconditions\n\n```bash\ntest -f src/app.py\n```\n\n"
PRE_BAD = "## Preconditions\n\n```bash\ntest -f src/missing.py\n```\n\n"
TASK1 = (
    "## Task 1\n\nIn `src/app.py`:\n\n"
    'old_string:\n```python\ndef greet():\n    return "hi"\n```\n\n'
    'new_string:\n```python\ndef greet():\n    return "hello"\n```\n\n'
    "Create `src/new_module.py` with:\n\n```python\nVALUE = 42\n```\n\n"
)
VERIFY1_OK = (
    "### Verify Task 1\n\n```bash\n"
    "grep -n 'return \"hello\"' src/app.py\n"
    "python3 -c 'import sys; sys.path.insert(0, \"src\"); import new_module; print(new_module.VALUE)'\n"
    "```\n\nExpected: exit 0\n\n"
)
VERIFY1_BAD = (
    "### Verify Task 1\n\n```bash\ngrep -n 'return \"nope\"' src/app.py\n```\n\n"
    "Expected: exit 0\n\n"
)
TASK2_MISMATCH = (
    "## Task 2\n\nIn `src/other.py`:\n\n"
    "old_string:\n```python\nX = 1\n```\n\n"
    "new_string:\n```python\nX = 3\n```\n\n"
    '### Verify Task 2\n\n```bash\ngrep -n "X = 3" src/other.py\n```\n\nExpected: exit 0\n\n'
)
COMMIT = "## Commit\n\nMessage file: `/dev/null`. Pathspec: `src/app.py src/new_module.py`.\n"
GOOD = HEAD + PRE_OK + TASK1 + VERIFY1_OK + COMMIT
BRIEF = (
    "# Brief\n\nContract: brief\n\n## Objective\nx\n\n## Scope\nx\n\n## Constraints\nx\n\n"
    "## Authority\nx\n\n## Acceptance Criteria\nx\n\n## Verification\n\n```bash\ntrue\n```\n\n"
    "## Deliverables\ndiff or commit, checks run, failures, unresolved questions\n"
)


def write(repo: Path, text: str) -> Path:
    p = repo / "plan.md"
    p.write_text(text)
    return p


def unchanged(repo: Path) -> bool:
    return (repo / "src" / "app.py").read_text() == APP and not (repo / "src" / "new_module.py").exists()


def test_apply_requires_repo_root(repo: Path):
    r = run("--apply", str(write(repo, GOOD)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert unchanged(repo)


def test_apply_refuses_a_brief_contract(repo: Path):
    r = run("--apply", "--repo-root", str(repo), str(write(repo, BRIEF)))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "brief" in (r.stdout + r.stderr).lower()


def test_plain_lint_never_touches_the_tree(repo: Path):
    r = run("--repo-root", str(repo), str(write(repo, GOOD)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert unchanged(repo)


def test_apply_applies_edits_creates_files_and_replays_verify(repo: Path):
    r = run("--apply", "--repo-root", str(repo), "--json", str(write(repo, GOOD)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo / "src" / "app.py").read_text() == APP.replace('"hi"', '"hello"')
    assert (repo / "src" / "new_module.py").read_text() == "VALUE = 42\n"
    doc = json.loads(r.stdout)
    assert doc["contract"] == "exact"
    assert doc["findings"] == []
    assert doc["apply"]["ok"] is True
    steps = doc["apply"]["steps"]
    assert [s["kind"] for s in steps] == ["precondition", "edit", "create", "verify"]
    assert all(s["status"] == "ok" for s in steps), steps
    assert steps[1]["target"] == "src/app.py"
    assert steps[2]["target"] == "src/new_module.py"
    assert steps[3]["rc"] == 0


def test_apply_stops_at_the_first_old_string_mismatch(repo: Path):
    plan = HEAD + PRE_OK + TASK1 + VERIFY1_OK + TASK2_MISMATCH + COMMIT
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 4, r.stdout + r.stderr
    # Task 1 landed; Task 2's edit did not anchor and nothing after it ran.
    assert (repo / "src" / "app.py").read_text() == APP.replace('"hi"', '"hello"')
    assert (repo / "src" / "other.py").read_text() == OTHER
    text = r.stdout + r.stderr
    assert "src/other.py" in text
    assert "old_string" in text
    assert "git checkout" in text


def test_apply_refuses_to_create_over_an_existing_file(repo: Path):
    plan = (
        HEAD + "## Task 1\n\nCreate `src/app.py` with:\n\n```python\nVALUE = 1\n```\n\n"
        "### Verify Task 1\n\n```bash\ntest -f src/app.py\n```\n\nExpected: exit 0\n\n" + COMMIT
    )
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 4, r.stdout + r.stderr
    assert (repo / "src" / "app.py").read_text() == APP
    assert "src/app.py" in r.stdout + r.stderr


def test_apply_verify_failure_exits_nonzero_and_names_the_block(repo: Path):
    plan = HEAD + PRE_OK + TASK1 + VERIFY1_BAD + COMMIT
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 5, r.stdout + r.stderr
    text = r.stdout + r.stderr
    assert "Verify Task 1" in text
    assert "rc" in text
    assert "git checkout" in text
    # The edits before the failing verify were applied; the tool stops there.
    assert (repo / "src" / "app.py").read_text() == APP.replace('"hi"', '"hello"')


def test_apply_runs_preconditions_before_any_edit(repo: Path):
    plan = HEAD + PRE_BAD + TASK1 + VERIFY1_OK + COMMIT
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 3, r.stdout + r.stderr
    assert unchanged(repo)
    assert "recondition" in r.stdout + r.stderr


def test_apply_refuses_dirty_targets(repo: Path):
    (repo / "src" / "app.py").write_text(APP + "# local change\n")
    r = run("--apply", "--repo-root", str(repo), str(write(repo, GOOD)))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "src/app.py" in r.stdout + r.stderr
    assert (repo / "src" / "app.py").read_text() == APP + "# local change\n"
    assert not (repo / "src" / "new_module.py").exists()


def test_apply_runs_the_gauge_first_and_refuses_defects(repo: Path):
    plan = (
        HEAD + "## Task 1\n\nIn `src/app.py`:\n\n"
        'old_string:\n```python\ndef greet():\n    return "hi"\n```\n\n'
        'new_string:\n```python\ndef greet():\n    return "hi"  # TODO tidy\n```\n\n'
        "### Verify Task 1\n\n```bash\ngrep -n TODO src/app.py\n```\n\nExpected: prints NOTHING\n\n" + COMMIT
    )
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "GAUGE001" in r.stdout + r.stderr
    assert unchanged(repo)


def test_apply_honours_prints_nothing_and_exit_1_expectations(repo: Path):
    plan = (
        HEAD + PRE_OK + TASK1
        + "### Verify Task 1\n\n```bash\ngrep -n 'absent-token' src/app.py\n```\n\nExpected: prints NOTHING\n\n"
        + "### Verify Task 1 again\n\n```bash\ngrep -q 'absent-token' src/app.py\n```\n\nExpected: exit 1\n\n"
        + COMMIT
    )
    r = run("--apply", "--repo-root", str(repo), "--json", str(write(repo, plan)))
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(r.stdout)
    verifies = [s for s in doc["apply"]["steps"] if s["kind"] == "verify"]
    assert len(verifies) == 2
    assert [s["status"] for s in verifies] == ["ok", "ok"]


def test_apply_prints_nothing_fails_when_output_appears(repo: Path):
    plan = (
        HEAD + PRE_OK + TASK1
        + "### Verify Task 1\n\n```bash\ngrep -n 'VALUE' src/new_module.py\n```\n\nExpected: exit 0 and prints the VALUE line\n\n"
        + "### Verify Task 1 again\n\n```bash\ngrep -n 'greet' src/app.py\n```\n\nExpected: prints NOTHING\n\n"
        + COMMIT
    )
    # The gauge itself flags the second block (the plan writes `greet`), so
    # --apply must refuse before any edit rather than discover it at replay.
    r = run("--apply", "--repo-root", str(repo), str(write(repo, plan)))
    assert r.returncode == 1, r.stdout + r.stderr
    assert unchanged(repo)
