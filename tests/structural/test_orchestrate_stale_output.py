"""Regression tests for stale artifacts reused across dispatches (mk-meti)."""

import importlib.util
import os
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


STUB_PREAMBLE = """#!/bin/bash
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
"""


def _write_stub(path: Path, body: str) -> Path:
    path.write_text(STUB_PREAMBLE + body + "\n")
    path.chmod(0o755)
    return path


def _dispatch_inputs(orc, tmp_path: Path, timeout: int = 1):
    project = tmp_path / "project"
    project.mkdir()
    task = orc.Task(id="task-1", title="stale output", stage="test", files=[],
                    verification={"required": False, "checks": []})
    manifest = orc.Manifest(
        version=1,
        mode="dependency-driven",
        tier="fast",
        max_parallel=1,
        timeout_per_task=timeout,
        stages=[],
        tasks={task.id: task},
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return project, task, manifest, run_dir


@pytest.mark.parametrize("phase", [None, "fix-1"])
def test_dispatch_removes_stale_artifacts_before_stub_runs(
    orc, tmp_path, monkeypatch, phase
):
    project, task, manifest, run_dir = _dispatch_inputs(orc, tmp_path)
    task_dir = run_dir / task.id
    task_dir.mkdir()
    stem = f"{phase}." if phase else ""
    output = task_dir / f"{stem}output.md"
    output.write_text("VERDICT: QUESTION stale?\n")
    output.with_suffix(output.suffix + ".verdict").write_text("STATUS: question\n")
    Path(f"{output}.verdict.pre-error").write_text("STATUS: error\n")

    stub = _write_stub(
        tmp_path / "dispatch.sh",
        """if [[ -e "$OUT" || -e "$OUT.verdict" || -e "$OUT.verdict.pre-error" ]]; then
  exit 41
fi
echo fresh > "$OUT"
printf "STATUS: pass\\n" > "$OUT.verdict"
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    result = orc.dispatch_task(
        task,
        manifest,
        str(project),
        None,
        {},
        os.environ["CLAVAIN_DISPATCH_SH"],
        "testrun",
        str(run_dir),
        phase=phase,
    )

    assert result.status == "pass", result.error
    assert output.read_text() == "fresh\n"


def test_timeout_without_fresh_output_reports_exactly_that(
    orc, tmp_path, monkeypatch
):
    project, task, manifest, run_dir = _dispatch_inputs(orc, tmp_path)
    stub = _write_stub(tmp_path / "dispatch.sh", "sleep 5")
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    result = orc.dispatch_task(
        task,
        manifest,
        str(project),
        None,
        {},
        os.environ["CLAVAIN_DISPATCH_SH"],
        "testrun",
        str(run_dir),
    )

    assert result.status == "error"
    assert result.output_path is None
    assert "timed out, no fresh output" in (result.error or "")


def test_fresh_question_output_is_parked_after_timeout(
    orc, tmp_path, monkeypatch
):
    project, task, manifest, run_dir = _dispatch_inputs(orc, tmp_path)
    task_dir = run_dir / task.id
    task_dir.mkdir()
    (task_dir / "output.md").write_text("VERDICT: QUESTION stale question?\n")
    stub = _write_stub(
        tmp_path / "dispatch.sh",
        'echo "VERDICT: QUESTION which colour?" > "$OUT"; sleep 5',
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    result = orc.run_task_pipeline(
        task,
        manifest,
        str(project),
        None,
        {},
        None,
        {},
        os.environ["CLAVAIN_DISPATCH_SH"],
        "testrun",
        str(run_dir),
    )

    assert result.status == "question"
    assert result.error == "executor asks: which colour?"


def test_backdated_verdict_sidecar_is_treated_as_absent(
    orc, tmp_path, monkeypatch
):
    project, task, manifest, run_dir = _dispatch_inputs(orc, tmp_path)
    stub = _write_stub(
        tmp_path / "dispatch.sh",
        'printf "STATUS: warn\\n" > "$OUT.verdict"; touch -t 200001010000 "$OUT.verdict"',
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))

    result = orc.dispatch_task(
        task,
        manifest,
        str(project),
        None,
        {},
        os.environ["CLAVAIN_DISPATCH_SH"],
        "testrun",
        str(run_dir),
    )

    assert result.status == "pass"
    assert result.verdict_path is None
