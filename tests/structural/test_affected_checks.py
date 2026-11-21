"""Tests for scripts/affected-checks.py (affected-only PR check selector)."""
import json
import subprocess
import sys
from pathlib import Path

# Built at runtime so this file does not cite them and map itself.
NOVEL = "zz" + "z-uncited"

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "affected-checks.py"


def run(*args):
    out = subprocess.run([sys.executable, "-I", str(SCRIPT), *args],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def pr(*files):
    return run("--event", "pull_request", "--files", *files)


def test_non_pr_events_always_full():
    for ev in ("push", "schedule", "workflow_dispatch"):
        assert run("--event", ev)["mode"] == "full"


def test_pr_without_base_or_files_is_full():
    assert run("--event", "pull_request")["mode"] == "full"


def test_config_and_ci_changes_are_full():
    for f in ("Makefile", ".github/workflows/test.yml", "tests/fixtures/x.json",
              "tests/run-tests.sh", "config/routing.yaml", "tests/uv.lock",
              "hooks/hooks.json"):
        assert pr(f)["mode"] == "full", f


def untracked(tmp_dir, name):
    f = ROOT / tmp_dir / name
    f.write_text("echo hi\n")
    return f


def test_unmapped_path_falls_back_to_full():
    f = untracked("scripts", f"{NOVEL}-file.sh")
    try:
        res = pr(f"scripts/{f.name}")
    finally:
        f.unlink()
    assert res["mode"] == "full"
    assert "no test maps" in res["reason"]


def test_one_unmapped_file_widens_a_mapped_pr():
    f = untracked("scripts", f"{NOVEL}-file.sh")
    try:
        res = pr("tests/structural/test_agents.py", f"scripts/{f.name}")
    finally:
        f.unlink()
    assert res["mode"] == "full"


def test_changed_test_selects_itself():
    res = pr("tests/structural/test_agents.py")
    assert res["mode"] == "affected"
    assert res["pytest"] == ["tests/structural/test_agents.py"]


def test_glob_tested_dirs_are_full():
    for f in ("skills/using-clavain/SKILL.md", "commands/brainstorm.md",
              "cmd/clavain-cli/children.go", "hooks/session-start.sh"):
        assert pr(f)["mode"] == "full", f


def test_deleted_file_is_full():
    res = pr(f"scripts/{NOVEL}-deleted.sh")
    assert res["mode"] == "full" and "deleted" in res["reason"]


def test_transitive_citation_is_followed():
    # dispatch.sh is sourced or called by many scripts; the closure must pull in
    # tests that cite only those callers, so the selection is wider than the
    # tests citing dispatch.sh directly.
    res = pr("scripts/dispatch.sh")
    assert res["mode"] == "affected"
    assert len(res["pytest"]) + len(res["bats"]) > 20


def test_docs_only_selects_no_unrelated_tests():
    f = untracked("docs", f"{NOVEL}-note.md")
    try:
        res = pr(f"docs/{f.name}")
    finally:
        f.unlink()
    assert res["mode"] == "affected"
    assert res["pytest"] == [] and res["bats"] == []


def test_instruction_files_are_not_docs():
    res = pr("CLAUDE.md")
    assert res["mode"] == "affected"
    assert "tests/structural/test_check_instruction_contract.py" in res["pytest"]


def test_removed_test_file_is_full():
    assert pr(f"tests/structural/test_gone_{NOVEL}.py")["mode"] == "full"


def test_runner_widens_when_selector_output_is_unusable(tmp_path):
    """run-tests.sh --affected must not report success on a broken selection."""
    import os, shutil
    root = Path(__file__).resolve().parents[2]
    fake = tmp_path / "r"
    (fake / "tests").mkdir(parents=True)
    (fake / "scripts").mkdir()
    (fake / "tests" / "structural").mkdir()
    shutil.copy(root / "tests" / "run-tests.sh", fake / "tests" / "run-tests.sh")
    (fake / "scripts" / "affected-checks.py").write_text("import sys\nsys.exit(3)\n")
    env = dict(os.environ, PATH="/usr/bin:/bin")
    res = subprocess.run(["bash", str(fake / "tests" / "run-tests.sh"),
                          "--affected", "HEAD"], capture_output=True, text=True,
                         env=env, timeout=60)
    assert "selection unusable" in res.stdout
    assert "Tier 1" in res.stdout  # fell back to the full suite
