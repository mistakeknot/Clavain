"""Behavioral tests for the orchestrate.py review pipeline (goal 7d610151).

The pipeline is what makes orchestrated delegation trustworthy: the
executor's self-reported VERDICT never gates a task. Machine <verify>
blocks run first, an INDEPENDENT reviewer reads the diff, failures loop
through bounded fix rounds, and two strikes park the task as `escalated`
instead of failing silently. A `VERDICT: QUESTION` parks as `question`.

The real dispatch.sh is replaced by stubs via CLAVAIN_DISPATCH_SH, same
technique as test_orchestrate_observability.py.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def orc(project_root: Path):
    spec = importlib.util.spec_from_file_location(
        "orchestrate", project_root / "scripts" / "orchestrate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["orchestrate"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("orchestrate", None)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

PLAN = """\
# Some Plan

## Task 1: Build the thing

Words about the thing.

<verify>
- run: `true`
  expect: exit 0
- run: `echo hello world`
  expect: contains "hello"
</verify>

## Task 2: Docs only

No verify block here.
"""


class TestParsePlanTasks:
    def test_sections_and_verify_entries(self, orc, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text(PLAN)
        parsed = orc.parse_plan_tasks(str(plan))
        assert set(parsed) == {1, 2}
        assert "Build the thing" in parsed[1].section
        assert parsed[1].verify == [
            {"run": "true", "expect": "exit 0"},
            {"run": "echo hello world", "expect": 'contains "hello"'},
        ]
        assert parsed[2].verify == []
        # Sections must not bleed into each other.
        assert "Docs only" not in parsed[1].section

    def test_missing_plan_is_empty(self, orc):
        assert orc.parse_plan_tasks(None) == {}
        assert orc.parse_plan_tasks("/nonexistent/plan.md") == {}

    def test_task_num_from_manifest_id(self, orc):
        assert orc._task_plan_num("task-3") == 3
        assert orc._task_plan_num("task-12") == 12
        assert orc._task_plan_num("setup") is None


class TestRunVerifyEntries:
    def test_empty_passes(self, orc, tmp_path):
        ok, report = orc.run_verify_entries([], str(tmp_path))
        assert ok
        assert "no verify entries" in report

    def test_exit_and_contains(self, orc, tmp_path):
        ok, report = orc.run_verify_entries(
            [
                {"run": "true", "expect": "exit 0"},
                {"run": "echo weasel", "expect": 'contains "weasel"'},
            ],
            str(tmp_path),
        )
        assert ok
        assert report.count("PASS") == 2

    def test_failure_carries_output_tail(self, orc, tmp_path):
        ok, report = orc.run_verify_entries(
            [{"run": "echo broke && false", "expect": "exit 0"}], str(tmp_path)
        )
        assert not ok
        assert "FAIL" in report
        assert "broke" in report  # the fix agent needs the evidence

    def test_contains_miss_fails(self, orc, tmp_path):
        ok, _ = orc.run_verify_entries(
            [{"run": "echo other", "expect": 'contains "weasel"'}], str(tmp_path)
        )
        assert not ok


class TestExtractQuestion:
    def test_question_line(self, orc, tmp_path):
        out = tmp_path / "output.md"
        out.write_text("did some work\nVERDICT: QUESTION which auth flow?\n")
        assert orc.extract_question(str(out)) == "which auth flow?"

    def test_no_question(self, orc, tmp_path):
        out = tmp_path / "output.md"
        out.write_text("VERDICT: CLEAN\n")
        assert orc.extract_question(str(out)) is None
        assert orc.extract_question(None) is None


class TestReviewEngineRouting:
    def test_tier_routes_engine(self, orc, monkeypatch):
        monkeypatch.delenv("ORC_REVIEW_ENGINE", raising=False)
        assert orc._review_engine_for("fast") == "codex"
        assert orc._review_engine_for("deep") == "claude"

    def test_env_forces_engine(self, orc, monkeypatch):
        monkeypatch.setenv("ORC_REVIEW_ENGINE", "codex")
        assert orc._review_engine_for("deep") == "codex"


class TestReviewPrompt:
    def test_distrust_and_verdict_grammar(self, orc):
        task = orc.Task(id="task-1", title="Build", stage="s", files=["a.py"])
        prompt = orc.build_review_prompt(
            task, "## Task 1: Build\nspec text", None, "diff here", "PASS: `true`", "I did it"
        )
        assert "Do NOT trust" in prompt
        assert "VERDICT: CLEAN" in prompt
        assert "diff here" in prompt
        assert "spec text" in prompt


# ---------------------------------------------------------------------------
# The pipeline end to end, against stub dispatchers
# ---------------------------------------------------------------------------

STUB_PREAMBLE = """#!/bin/bash
# Stub dispatch.sh honoring the real interface (incl. --to for reviews).
ENGINE=codex
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt-file) PROMPT="$2"; shift 2;;
    -C) PROJ="$2"; shift 2;;
    -o) OUT="$2"; shift 2;;
    --tier) TIER="$2"; shift 2;;
    --to) ENGINE="$2"; shift 2;;
    -s) SANDBOX="$2"; shift 2;;
    *) shift;;
  esac
done
TID=$(basename "$(dirname "$OUT")")
BASE=$(basename "$OUT")
"""


def _write_stub(path: Path, body: str) -> Path:
    path.write_text(STUB_PREAMBLE + body + "\n")
    path.chmod(0o755)
    return path


def _write_manifest(path: Path, tasks_yaml: str, timeout: int = 60) -> Path:
    path.write_text(
        f"""version: 1
mode: dependency-driven
tier: fast
max_parallel: 2
timeout_per_task: {timeout}

stages:
  - name: "Stage"
    tasks:
{tasks_yaml}"""
    )
    return path


def _git_repo(path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / ".keep").write_text("")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


def test_review_approves_clean_task(orc, tmp_path, monkeypatch):
    """Implement passes verify, reviewer says CLEAN → pass with rounds=0."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        """case "$BASE" in
  review-*) echo "looks right" > "$OUT"; echo "VERDICT: CLEAN" >> "$OUT"
            printf -- "--- VERDICT ---\\nSTATUS: pass\\n---\\n" > "$OUT.verdict";;
  *) touch "$PROJ/made.txt"; echo "VERDICT: CLEAN" > "$OUT"
     printf "STATUS: pass\\n" > "$OUT.verdict";;
esac""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "clean worker"
        files: [made.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert results["task-1"].status == "pass"
    assert results["task-1"].rounds == 0
    # Review artifacts persisted
    run_dirs = list((project / ".clavain" / "orchestrate-runs").iterdir())
    assert (run_dirs[0] / "task-1" / "review-1.prompt.md").exists()


def test_review_failure_fixes_then_passes(orc, tmp_path, monkeypatch):
    """First review NEEDS_ATTENTION → one fix round → second review CLEAN."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        """case "$BASE" in
  review-1.md) echo "missing error handling in made.txt" > "$OUT"
               echo "VERDICT: NEEDS_ATTENTION missing error handling" >> "$OUT"
               printf -- "--- VERDICT ---\\nSTATUS: warn\\n---\\n" > "$OUT.verdict";;
  review-2.md) echo "VERDICT: CLEAN" > "$OUT"
               printf -- "--- VERDICT ---\\nSTATUS: pass\\n---\\n" > "$OUT.verdict";;
  fix-1.output.md) echo fixed >> "$PROJ/made.txt"; echo "VERDICT: CLEAN" > "$OUT"
                   printf "STATUS: pass\\n" > "$OUT.verdict";;
  *) touch "$PROJ/made.txt"; echo "VERDICT: CLEAN" > "$OUT"
     printf "STATUS: pass\\n" > "$OUT.verdict";;
esac""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "needs one fix"
        files: [made.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert results["task-1"].status == "pass", results["task-1"].error
    assert results["task-1"].rounds == 1
    assert "review passed after 1 fix round" in (results["task-1"].error or "")


def test_two_strikes_escalates_and_skips_dependents(orc, tmp_path, monkeypatch):
    """Review never approves → MAX_FIX_ROUNDS consumed → escalated; the
    dependent is skipped, and the summary bucket is 'escalated', never a
    silent 'fail'."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        """case "$BASE" in
  review-*) echo "VERDICT: NEEDS_ATTENTION still wrong" > "$OUT"
            printf -- "--- VERDICT ---\\nSTATUS: warn\\n---\\n" > "$OUT.verdict";;
  *) touch "$PROJ/made.txt"; echo "VERDICT: CLEAN" > "$OUT"
     printf "STATUS: pass\\n" > "$OUT.verdict";;
esac""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "unreviewable"
        files: [made.txt]
        depends: []
      - id: task-2
        title: "dependent"
        files: [other.txt]
        depends: [task-1]
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert results["task-1"].status == "escalated"
    assert results["task-1"].rounds == 2
    assert "two strikes" in (results["task-1"].error or "")
    assert results["task-2"].status == "skipped"
    counts = orc.count_verdicts(results)
    assert counts["escalated"] == 1
    assert counts["fail"] == 0


def test_verify_failure_skips_reviewer_and_feeds_fix(orc, tmp_path, monkeypatch):
    """A failing <verify> gate must not pay a reviewer — the failing gate IS
    the finding, dispatched straight to the fix round."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    plan = tmp_path / "plan.md"
    plan.write_text(
        """## Task 1: Make the marker

<verify>
- run: `test -f fixed-marker.txt`
  expect: exit 0
</verify>
"""
    )
    stub = _write_stub(
        tmp_path / "stub.sh",
        """case "$BASE" in
  review-*) echo "VERDICT: CLEAN" > "$OUT"
            printf -- "--- VERDICT ---\\nSTATUS: pass\\n---\\n" > "$OUT.verdict";;
  fix-1.output.md) touch "$PROJ/fixed-marker.txt"; echo "VERDICT: CLEAN" > "$OUT"
                   printf "STATUS: pass\\n" > "$OUT.verdict";;
  *) touch "$PROJ/made.txt"; echo "VERDICT: CLEAN" > "$OUT"
     printf "STATUS: pass\\n" > "$OUT.verdict";;
esac""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "verify-gated"
        files: [made.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(
        str(manifest), plan_path=str(plan), project_dir=str(project)
    )
    assert results["task-1"].status == "pass", results["task-1"].error
    assert results["task-1"].rounds == 1
    run_dir = next((project / ".clavain" / "orchestrate-runs").iterdir())
    # Round 0's verify failed and NO review-1 was dispatched for it — the
    # first review artifact belongs to round 1, after the fix.
    fix_prompt = (run_dir / "task-1" / "fix-1.prompt.md").read_text()
    assert "fixed-marker.txt" in fix_prompt  # failing gate fed to the fix agent


def test_question_parks_task(orc, tmp_path, monkeypatch):
    """VERDICT: QUESTION parks the task instead of guessing or failing."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        """echo "VERDICT: QUESTION should the cache be per-user or global?" > "$OUT"
printf "STATUS: pass\\n" > "$OUT.verdict"
touch "$PROJ/made.txt" """,
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "blocked on a decision"
        files: [made.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert results["task-1"].status == "question"
    assert "per-user or global" in (results["task-1"].error or "")
    assert orc.count_verdicts(results)["question"] == 1


def test_no_review_flag_restores_legacy_semantics(orc, tmp_path, monkeypatch):
    """--no-review: the executor's self-report gates the task, as before."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        """touch "$PROJ/made.txt"; echo "VERDICT: CLEAN" > "$OUT"
printf "STATUS: pass\\n" > "$OUT.verdict" """,
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "self-reported"
        files: [made.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(
        str(manifest), project_dir=str(project), review_enabled=False,
    )
    assert results["task-1"].status == "pass"
    run_dir = next((project / ".clavain" / "orchestrate-runs").iterdir())
    assert not (run_dir / "task-1" / "review-1.prompt.md").exists()
