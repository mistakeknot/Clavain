"""An empty output file pre-created by the engine is not fresh output (mk-9hqr)."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def orc(project_root: Path):
    spec = importlib.util.spec_from_file_location(
        "orchestrate_fresh", project_root / "scripts" / "orchestrate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["orchestrate_fresh"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("orchestrate_fresh", None)


STUB = """#!/bin/bash
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) OUT="$2"; shift 2;;
    *) shift;;
  esac
done
: > "$OUT"
sleep 5
"""


def _inputs(orc, tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    task = orc.Task(id="task-1", title="empty output", stage="test", files=[])
    manifest = orc.Manifest(
        version=1, mode="dependency-driven", tier="fast", max_parallel=1,
        timeout_per_task=1, stages=[], tasks={task.id: task},
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    stub = tmp_path / "dispatch.sh"
    stub.write_text(STUB)
    stub.chmod(0o755)
    return project, task, manifest, run_dir, stub


def test_an_empty_pre_created_output_file_is_not_fresh(orc, tmp_path, monkeypatch):
    project, task, manifest, run_dir, stub = _inputs(orc, tmp_path)
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    result = orc.dispatch_task(
        task, manifest, str(project), None, {}, str(stub), "testrun", str(run_dir),
    )
    assert result.status == "error"
    assert result.output_path is None
    assert "timed out, no fresh output" in (result.error or "")
    assert (run_dir / task.id / "output.md").exists(), "the stub pre-created the file"
