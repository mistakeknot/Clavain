"""Behavioral tests for orchestrate.py observability guarantees (Sylveste-e9y).

Covers the Stage-1 acceptance criteria of the orchestrator-observability goal:
  (a) failed-task artifacts persist under the run dir (never a cleaned temp dir)
  (b) per-task progress lines are emitted as tasks complete, line-buffered
  (c) verdict outcome-check prevents false-negative skip cascades
      (timeout / missing sidecar with work actually done on disk -> WARN,
       dependents still run)
  (d) the dispatch push-guard blocks executor `git push` for the run's
      duration and is removed afterwards

The real dispatch.sh is replaced by stubs via CLAVAIN_DISPATCH_SH.
"""

import importlib.util
import re
import subprocess
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
    # Register before exec: dataclass string-annotation resolution looks the
    # module up in sys.modules (fails on 3.14 otherwise).
    sys.modules["orchestrate"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("orchestrate", None)


STUB_PREAMBLE = """#!/bin/bash
# Stub dispatch.sh honoring the real interface.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt-file) PROMPT="$2"; shift 2;;
    -C) PROJ="$2"; shift 2;;
    -o) OUT="$2"; shift 2;;
    --tier) TIER="$2"; shift 2;;
    -s) SANDBOX="$2"; shift 2;;
    *) shift;;
  esac
done
TID=$(basename "$(dirname "$OUT")")
"""


def _write_stub(path: Path, body: str) -> Path:
    path.write_text(STUB_PREAMBLE + body + "\n")
    path.chmod(0o755)
    return path


def _write_manifest(path: Path, tasks_yaml: str, timeout: int = 30) -> Path:
    path.write_text(
        f"""version: 1
mode: dependency-driven
tier: fast
max_parallel: 2
timeout_per_task: {timeout}

stages:
  - name: "test"
    tasks:
{tasks_yaml}
"""
    )
    return path


def _run_dir(project: Path) -> Path:
    runs = list((project / ".clavain" / "orchestrate-runs").iterdir())
    assert len(runs) == 1, f"expected exactly one run dir, got {runs}"
    return runs[0]


def test_failed_task_artifacts_persist(orc, tmp_path, monkeypatch):
    """(a) A failing dispatch leaves prompt, log, and meta on disk."""
    project = tmp_path / "proj"
    project.mkdir()
    stub = _write_stub(
        tmp_path / "stub.sh",
        'echo "agent partial output"; echo "boom stderr" >&2; exit 2',
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "failing task"
        files: [never-created.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    results = orc.orchestrate(str(manifest), project_dir=str(project))

    assert results["task-1"].status == "error"
    task_dir = _run_dir(project) / "task-1"
    assert (task_dir / "prompt.md").exists()
    assert (task_dir / "meta.json").exists()
    log = (task_dir / "dispatch.log").read_text()
    assert "agent partial output" in log
    assert "boom stderr" in log


def test_progress_lines_emitted_per_task(orc, tmp_path, monkeypatch, capsys):
    """(b) Each task completion prints a flushed progress line."""
    project = tmp_path / "proj"
    project.mkdir()
    stub = _write_stub(
        tmp_path / "stub.sh",
        'echo done > "$OUT"; printf "STATUS: pass\\n" > "$OUT.verdict"; exit 0',
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "quick task"
        files: []
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    orc.orchestrate(str(manifest), project_dir=str(project))

    out = capsys.readouterr().out
    assert re.search(r"\[PASS\] task-1 \(\d+s\)", out)
    # Structural guarantee: stdout is line-buffered even when redirected.
    src = Path(orc.__file__).read_text()
    assert "line_buffering=True" in src


def test_timeout_after_work_is_warn_and_dependents_run(orc, tmp_path, monkeypatch):
    """(c) Timeout with declared files on disk -> WARN, dependent executes."""
    project = tmp_path / "proj"
    project.mkdir()
    stub = _write_stub(
        tmp_path / "stub.sh",
        """if [ "$TID" = "task-1" ]; then
  touch "$PROJ/made.txt"; echo out > "$OUT"; sleep 30
else
  touch "$PROJ/made2.txt"; echo out > "$OUT"
  printf "STATUS: pass\\n" > "$OUT.verdict"
fi""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "slow but productive"
        files: [made.txt]
        depends: []
      - id: task-2
        title: "dependent"
        files: [made2.txt]
        depends: [task-1]
""",
        timeout=3,
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    results = orc.orchestrate(str(manifest), project_dir=str(project))

    assert results["task-1"].status == "warn", results["task-1"].error
    assert results["task-2"].status == "pass"
    assert (project / "made2.txt").exists()


def test_missing_verdict_nonzero_exit_with_work_is_warn(orc, tmp_path, monkeypatch):
    """(c) Missing sidecar + exit!=0 but files touched -> WARN, not ERROR."""
    project = tmp_path / "proj"
    project.mkdir()
    stub = _write_stub(
        tmp_path / "stub.sh",
        'touch "$PROJ/thing.txt"; echo out > "$OUT"; exit 3',
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "verdictless worker"
        files: [thing.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert results["task-1"].status == "warn"


def test_outcome_check_rejects_untouched_preexisting_files(orc, tmp_path):
    """(c) Pre-existing but untouched files do not fake a completed outcome."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "old.txt").write_text("stale")
    task = orc.Task(id="t", title="t", stage="s", files=["old.txt"])
    import time as _time

    assert orc._outcome_check(task, str(project), since=_time.time() + 5) is False


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )


def test_push_guard_blocks_executor_push_then_restores(orc, tmp_path, monkeypatch):
    """(d) `git push` inside a dispatched task fails; pushes work after run."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    project = tmp_path / "proj"
    subprocess.run(["git", "init", "-q", "-b", "main", str(project)], check=True)
    _git(project, "config", "user.email", "t@t")
    _git(project, "config", "user.name", "t")
    (project / "f.txt").write_text("v0")
    _git(project, "add", "f.txt")
    _git(project, "commit", "-q", "-m", "init")
    _git(project, "remote", "add", "origin", str(origin))
    _git(project, "push", "-q", "origin", "main")

    stub = _write_stub(
        tmp_path / "stub.sh",
        """cd "$PROJ"
echo change >> f.txt && git add f.txt && git commit -q -m change
if git push origin main > "$OUT" 2>&1; then
  echo "PUSHED" >> "$OUT"
fi
printf "STATUS: pass\\n" > "$OUT.verdict"
exit 0""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "pushy executor"
        files: [f.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert results["task-1"].status == "pass"

    out_text = (_run_dir(project) / "task-1" / "output.md").read_text()
    assert "PUSHED" not in out_text, "guard failed: executor push succeeded"
    assert (_run_dir(project) / "push-attempts.log").exists()
    # Origin never received the executor's commit.
    origin_head = subprocess.run(
        ["git", "-C", str(origin), "rev-list", "--count", "main"],
        capture_output=True, text=True,
    ).stdout.strip()
    assert origin_head == "1"
    # Guard removed after the run: pushes work again.
    push_after = _git(project, "push", "origin", "main")
    assert push_after.returncode == 0, push_after.stderr
