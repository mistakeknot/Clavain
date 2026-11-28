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






def test_changed_test_selects_itself():
    res = pr("tests/structural/test_agents.py")
    assert res["mode"] == "affected"
    assert "tests/structural/test_agents.py" in res["pytest"]




def test_code_paths_select_full():
    for f in ("scripts/dispatch.sh", "scripts/script-lint.sh",
              "skills/using-clavain/SKILL.md", "commands/brainstorm.md",
              "cmd/clavain-cli/children.go", "hooks/session-start.sh",
              "interlab.sh"):
        assert pr(f)["mode"] == "full", f


def test_docs_are_full():
    for f in ("CLAUDE.md", "docs/guide-goal-shape.md", "README.md"):
        assert pr(f)["mode"] == "full", f


def test_test_change_mixed_with_code_is_full():
    assert pr("tests/structural/test_agents.py", "scripts/dispatch.sh")["mode"] == "full"


def test_changed_bats_runs_all_structural_tests():
    res = pr("tests/shell/goal_shape_guide.bats")
    assert res["mode"] == "affected"
    assert "tests/shell/goal_shape_guide.bats" in res["bats"]
    assert "tests/structural/test_shell_suite_safety.py" in res["pytest"]


def test_discovery_skips_untracked_dependency_tests():
    res = pr("tests/structural/test_agents.py")
    assert not any("/.venv/" in t or "site-packages" in t for t in res["pytest"])


def test_changed_test_pulls_in_its_importers():
    res = pr("tests/structural/test_review_round_limit.py")
    assert res["mode"] == "affected"
    assert "tests/structural/test_review_round_decision.py" in res["pytest"]


def test_missing_path_is_full():
    res = pr(f"tests/structural/test_{NOVEL}_gone.py")
    assert res["mode"] == "full" and "deleted" in res["reason"]


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
