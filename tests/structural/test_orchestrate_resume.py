"""Kill-safe orchestration: timeout, journal, --resume, guard sweep (goal e453fc6a).

Both scene-pilot kills (runs 3155e212, 9d5d116d) exposed the same three gaps:
no cross-run resume (manual manifest surgery), a stranded push guard (finally
never runs under SIGKILL), and misleading wall-clock timing when the machine
sleeps mid-dispatch. These tests pin the fixes, including the goal's literal
gate: kill a live run mid-wave, resume completes only the remaining tasks,
and the guard is restored.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def orc(project_root: Path):
    import importlib.util

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
# Stub dispatch.sh honoring the real interface.
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
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / ".keep").write_text("")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


def _journal_lines(project: Path) -> list[dict]:
    journals = list((project / ".clavain" / "orchestrate-runs").glob("*/journal.jsonl"))
    assert len(journals) == 1, journals
    return [json.loads(ln) for ln in journals[0].read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Timeout enforcement
# ---------------------------------------------------------------------------

def test_timeout_kills_task_and_marks_meta(orc, tmp_path, monkeypatch):
    """A task exceeding timeout_per_task is killed; meta.json records
    timed_out=true and the new monotonic duration."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        # sleep past the 1s ceiling; the touch after it must never run
        'sleep 3; touch "$PROJ/made.txt"; printf "STATUS: pass\\n" > "$OUT.verdict"',
    )
    manifest_path = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "sleeper"
        files: [made.txt]
        depends: []
""",
        timeout=1,
    )
    manifest = orc.load_manifest(str(manifest_path))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = orc.dispatch_task(
        manifest.tasks["task-1"], manifest, str(project), None,
        {}, str(stub), "testrun", str(run_dir),
    )
    assert result.status == "error", result.error
    meta = json.loads((run_dir / "task-1" / "meta.json").read_text())
    assert meta["timed_out"] is True
    assert "duration_monotonic_s" in meta
    assert not (project / "made.txt").exists()


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def test_journal_records_run_and_tasks(orc, tmp_path, monkeypatch):
    """Every completion journals immediately: run_start, per-task entries
    with status/rounds/review-verdict/head, and run_end with counts."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    stub = _write_stub(
        tmp_path / "stub.sh",
        """case "$BASE" in
  review-*) echo "VERDICT: CLEAN" > "$OUT"
            printf -- "--- VERDICT ---\\nSTATUS: pass\\n---\\n" > "$OUT.verdict";;
  *) touch "$PROJ/$TID.txt"; echo "VERDICT: CLEAN" > "$OUT"
     printf "STATUS: pass\\n" > "$OUT.verdict";;
esac""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "first"
        files: [task-1.txt]
        depends: []
      - id: task-2
        title: "second"
        files: [task-2.txt]
        depends: [task-1]
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(str(manifest), project_dir=str(project))
    assert {r.status for r in results.values()} == {"pass"}

    entries = _journal_lines(project)
    events = [e["event"] for e in entries]
    assert events[0] == "run_start"
    assert events[-1] == "run_end"
    tasks = {e["task"]: e for e in entries if e["event"] == "task"}
    assert set(tasks) == {"task-1", "task-2"}
    for e in tasks.values():
        assert e["status"] == "pass"
        assert e["rounds"] == 0
        assert e["review_verdict"] and e["review_verdict"].endswith(".verdict")
        assert e["head"]  # git HEAD at completion
    assert entries[-1]["counts"]["pass"] == 2


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def test_resume_skips_complete_redispatches_failed(orc, tmp_path, monkeypatch):
    """pass tasks skip on resume with edges satisfied; error tasks (and their
    skipped dependents) re-dispatch."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    calls = tmp_path / "calls.log"
    flag = tmp_path / "fixed.flag"
    stub = _write_stub(
        tmp_path / "stub.sh",
        f"""echo "$TID" >> {calls}
if [[ "$TID" == task-2 && ! -f {flag} ]]; then
  exit 1
fi
touch "$PROJ/$TID.txt"
printf "STATUS: pass\\n" > "$OUT.verdict"
echo done > "$OUT" """,
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "fine"
        files: [task-1.txt]
        depends: []
      - id: task-2
        title: "breaks first time"
        files: [task-2.txt]
        depends: [task-1]
      - id: task-3
        title: "downstream"
        files: [task-3.txt]
        depends: [task-2]
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    first = orc.orchestrate(
        str(manifest), project_dir=str(project), review_enabled=False,
    )
    assert first["task-1"].status == "pass"
    assert first["task-2"].status == "error"
    assert first["task-3"].status == "skipped"
    run_id = next((project / ".clavain" / "orchestrate-runs").iterdir()).name

    flag.write_text("")
    calls.write_text("")
    resumed = orc.orchestrate(
        str(manifest), project_dir=str(project), review_enabled=False,
        resume_run_id=run_id,
    )
    assert resumed["task-1"].status == "pass"
    assert "resumed" in (resumed["task-1"].error or "")
    assert resumed["task-2"].status == "pass"
    assert resumed["task-3"].status == "pass"
    dispatched = set(calls.read_text().split())
    assert dispatched == {"task-2", "task-3"}, "task-1 must not re-dispatch"


def test_resume_without_journal_errors(orc, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "t"
        files: [a.txt]
        depends: []
""",
    )
    with pytest.raises(SystemExit):
        orc.orchestrate(
            str(manifest), project_dir=str(project), resume_run_id="deadbeef",
        )


def test_kill_mid_wave_then_resume_restores_guard(orc, project_root, tmp_path, monkeypatch, capsys):
    """The goal's gate, literally: SIGKILL a live run mid-wave (task-1 done,
    task-2 in flight), verify the guard is stranded, then --resume: the
    stranded guard is swept, only task-2 dispatches, and the guard is gone
    at the end."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    slow_stub = _write_stub(
        tmp_path / "slow.sh",
        """if [[ "$TID" == task-1 ]]; then
  touch "$PROJ/task-1.txt"; printf "STATUS: pass\\n" > "$OUT.verdict"; echo ok > "$OUT"
else
  sleep 20
fi""",
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "instant"
        files: [task-1.txt]
        depends: []
      - id: task-2
        title: "slow"
        files: [task-2.txt]
        depends: []
""",
    )
    env = dict(os.environ, CLAVAIN_DISPATCH_SH=str(slow_stub))
    proc = subprocess.Popen(
        [sys.executable, str(project_root / "scripts" / "orchestrate.py"),
         str(manifest), "--project-dir", str(project), "--no-review"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        journal = None
        while time.time() < deadline:
            found = list(
                (project / ".clavain" / "orchestrate-runs").glob("*/journal.jsonl")
            )
            if found and '"task": "task-1"' in found[0].read_text():
                journal = found[0]
                break
            time.sleep(0.2)
        assert journal is not None, "task-1 never journaled"
        os.kill(proc.pid, signal.SIGKILL)
    finally:
        proc.wait()

    guard = project / ".git" / "hooks" / "pre-push"
    assert guard.exists(), "kill should strand the push guard"
    assert orc.GUARD_MARKER in guard.read_text()
    run_id = journal.parent.name

    calls = tmp_path / "calls.log"
    fast_stub = _write_stub(
        tmp_path / "fast.sh",
        f"""echo "$TID" >> {calls}
touch "$PROJ/$TID.txt"
printf "STATUS: pass\\n" > "$OUT.verdict"
echo ok > "$OUT" """,
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(fast_stub))
    results = orc.orchestrate(
        str(manifest), project_dir=str(project), review_enabled=False,
        resume_run_id=run_id,
    )
    out = capsys.readouterr().out
    assert "Swept stranded push guard" in out
    assert results["task-1"].status == "pass"
    assert "resumed" in (results["task-1"].error or "")
    assert results["task-2"].status == "pass"
    assert calls.read_text().split() == ["task-2"], "only task-2 re-dispatches"
    assert not guard.exists(), "guard must be removed after a clean resume"


def test_stranded_guard_with_backup_restores_original_hook(orc, tmp_path, monkeypatch):
    """A stranded guard whose install backed up a real user hook: the sweep
    restores the original, and the new run's teardown leaves it in place."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    hooks = project / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    original = "#!/bin/sh\n# the user's own pre-push\nexit 0\n"
    (hooks / "pre-push.orc-bak").write_text(original)
    dead_run = tmp_path / "dead-run"
    dead_run.mkdir()
    (dead_run / "orchestrator.pid").write_text("999999")
    (hooks / "pre-push").write_text(
        "#!/bin/sh\n"
        f"# {orc.GUARD_MARKER} run=deadrun1\n"
        f"echo x >> {dead_run}/push-attempts.log\n"
        "exit 1\n"
    )
    (hooks / "pre-push").chmod(0o755)

    stub = _write_stub(
        tmp_path / "stub.sh",
        'touch "$PROJ/$TID.txt"; printf "STATUS: pass\\n" > "$OUT.verdict"; echo ok > "$OUT"',
    )
    manifest = _write_manifest(
        tmp_path / "m.yaml",
        """      - id: task-1
        title: "t"
        files: [task-1.txt]
        depends: []
""",
    )
    monkeypatch.setenv("CLAVAIN_DISPATCH_SH", str(stub))
    results = orc.orchestrate(
        str(manifest), project_dir=str(project), review_enabled=False,
    )
    assert results["task-1"].status == "pass"
    assert (hooks / "pre-push").read_text() == original
    assert not (hooks / "pre-push.orc-bak").exists()


def test_live_guard_of_concurrent_run_left_alone(orc, tmp_path):
    """A guard whose installing run has a LIVE orchestrator pid is not swept."""
    project = tmp_path / "proj"
    project.mkdir()
    _git_repo(project)
    hooks = project / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    live_run = tmp_path / "live-run"
    live_run.mkdir()
    (live_run / "orchestrator.pid").write_text(str(os.getpid()))
    guard_text = (
        "#!/bin/sh\n"
        f"# {orc.GUARD_MARKER} run=liverun1\n"
        f"echo x >> {live_run}/push-attempts.log\n"
        "exit 1\n"
    )
    (hooks / "pre-push").write_text(guard_text)

    orc._sweep_stranded_guards({str(project)})
    assert (hooks / "pre-push").read_text() == guard_text
