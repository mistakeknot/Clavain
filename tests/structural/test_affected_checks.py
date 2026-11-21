"""Tests for scripts/affected-checks.py (affected-only PR check selector)."""
import json
import subprocess
import sys
from pathlib import Path

# Built at runtime so this file does not cite them and map itself.
NOVEL = "zz" + "z-uncited"

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


def test_unmapped_path_falls_back_to_full():
    res = pr(f"scripts/{NOVEL}-file.sh")
    assert res["mode"] == "full"
    assert "no test maps" in res["reason"]


def test_one_unmapped_file_widens_a_mapped_pr():
    res = pr("tests/structural/test_agents.py",
             f"scripts/{NOVEL}-file.sh")
    assert res["mode"] == "full"


def test_changed_test_selects_itself():
    res = pr("tests/structural/test_agents.py")
    assert res["mode"] == "affected"
    assert res["pytest"] == ["tests/structural/test_agents.py"]


def test_skill_dir_maps_to_glob_tests():
    res = pr("skills/using-clavain/SKILL.md")
    assert res["mode"] == "affected"
    assert "tests/structural/test_skills.py" in res["pytest"]


def test_docs_only_selects_no_unrelated_tests():
    res = pr(f"docs/{NOVEL}-note.md")
    assert res["mode"] == "affected"
    assert res["pytest"] == [] and res["bats"] == []


def test_instruction_files_are_not_docs():
    res = pr("CLAUDE.md")
    assert res["mode"] == "affected"
    assert "tests/structural/test_check_instruction_contract.py" in res["pytest"]


def test_removed_test_file_is_full():
    assert pr(f"tests/structural/test_gone_{NOVEL}.py")["mode"] == "full"
