#!/usr/bin/env python3
"""orchestrate.py — DAG-based Codex agent dispatch.

Reads an execution manifest (.exec.yaml) and dispatches tasks via dispatch.sh
with proper dependency ordering. Supports four execution modes:

  all-parallel       — All tasks dispatched simultaneously
  all-sequential     — Tasks run one at a time in topological order
  dependency-driven  — Maximum parallelism respecting declared dependencies
  manual-batching    — Stages run sequentially, tasks within stage respect deps

Usage:
    python3 orchestrate.py <manifest.exec.yaml> [--plan <plan.md>] [--project-dir <dir>]
    python3 orchestrate.py --validate <manifest.exec.yaml>
    python3 orchestrate.py --dry-run <manifest.exec.yaml>
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from uuid import uuid4

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    title: str
    stage: str
    files: list[str] = field(default_factory=list)
    depends: list[str] = field(default_factory=list)
    tier: str | None = None
    prompt_hint: str | None = None


@dataclass
class TaskResult:
    task_id: str
    status: str  # pass, warn, fail, error, skipped
    output_path: str | None = None
    verdict_path: str | None = None
    error: str | None = None
    duration_s: float = 0.0


@dataclass
class Manifest:
    version: int
    mode: str
    tier: str
    max_parallel: int
    timeout_per_task: int
    stages: list[dict]
    tasks: dict[str, Task]  # keyed by task_id


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _require_yaml():
    if yaml is None:
        print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
        sys.exit(1)


def load_manifest(path: str | Path) -> Manifest:
    """Parse a .exec.yaml manifest into a Manifest object."""
    _require_yaml()
    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        print(f"ERROR: Manifest must be a YAML mapping, got {type(raw).__name__}", file=sys.stderr)
        sys.exit(1)

    tasks: dict[str, Task] = {}
    stages = raw.get("stages", [])
    for stage in stages:
        stage_name = stage.get("name", "unnamed")
        for t in stage.get("tasks", []):
            task = Task(
                id=t["id"],
                title=t["title"],
                stage=stage_name,
                files=t.get("files", []),
                depends=t.get("depends", []),
                tier=t.get("tier"),
                prompt_hint=t.get("prompt_hint"),
            )
            if task.id in tasks:
                print(f"ERROR: Duplicate task ID '{task.id}'", file=sys.stderr)
                sys.exit(1)
            tasks[task.id] = task

    return Manifest(
        version=raw.get("version", 1),
        mode=raw.get("mode", "dependency-driven"),
        tier=raw.get("tier", "deep"),
        max_parallel=raw.get("max_parallel", 5),
        timeout_per_task=raw.get("timeout_per_task", 300),
        stages=stages,
        tasks=tasks,
    )


# ---------------------------------------------------------------------------
# Graph building
# ---------------------------------------------------------------------------

def build_graph(manifest: Manifest) -> dict[str, set[str]]:
    """Build dependency graph. Stage barriers are additive: every task depends
    on ALL tasks from prior stages PLUS any explicit depends entries."""
    graph: dict[str, set[str]] = {}
    prior_stage_tasks: set[str] = set()

    for stage in manifest.stages:
        current_stage_ids: list[str] = []
        for t in stage.get("tasks", []):
            tid = t["id"]
            deps: set[str] = set(t.get("depends", []))
            # Additive stage barrier: depend on all prior stage tasks
            deps |= prior_stage_tasks
            graph[tid] = deps
            current_stage_ids.append(tid)
        prior_stage_tasks |= set(current_stage_ids)

    return graph


def validate_graph(graph: dict[str, set[str]], manifest: Manifest) -> list[str]:
    """Validate the dependency graph. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    all_ids = set(graph.keys())

    # Check for references to non-existent tasks
    for tid, deps in graph.items():
        for dep in deps:
            if dep not in all_ids:
                errors.append(f"Task '{tid}' depends on unknown task '{dep}'")
            if dep == tid:
                errors.append(f"Task '{tid}' depends on itself")

    # Check for cycles
    try:
        ts = TopologicalSorter(graph)
        ts.prepare()
    except CycleError as e:
        errors.append(f"Cycle detected: {e}")

    return errors


# ---------------------------------------------------------------------------
# Execution order resolution
# ---------------------------------------------------------------------------

def _resolve_all_parallel(graph: dict[str, set[str]]) -> list[list[str]]:
    """All tasks in one batch, ignoring dependencies."""
    return [list(graph.keys())]


def _resolve_all_sequential(graph: dict[str, set[str]]) -> list[list[str]]:
    """Each task in its own batch, topologically sorted.

    Caller must have already validated the graph via validate_graph().
    """
    ts = TopologicalSorter(graph)
    order = list(ts.static_order())
    return [[tid] for tid in order]


def _resolve_manual_batching(
    graph: dict[str, set[str]], manifest: Manifest
) -> list[list[str]]:
    """Group by stage, respecting intra-stage deps with TopologicalSorter."""
    batches: list[list[str]] = []
    for stage in manifest.stages:
        stage_ids = [t["id"] for t in stage.get("tasks", [])]
        if not stage_ids:
            continue
        stage_set = set(stage_ids)
        # Build intra-stage subgraph
        sub_graph = {}
        for tid in stage_ids:
            intra_deps = graph.get(tid, set()) & stage_set
            sub_graph[tid] = intra_deps
        # Use TopologicalSorter for intra-stage ordering
        ts = TopologicalSorter(sub_graph)
        ts.prepare()
        while ts.is_active():
            ready = list(ts.get_ready())
            batches.append(ready)
            for tid in ready:
                ts.done(tid)
    return batches


class DependencyDrivenScheduler:
    """Dynamic scheduler that yields ready tasks as dependencies complete.

    Unlike static batch pre-computation, this responds to actual completion
    order for maximum parallelism.
    """

    def __init__(self, graph: dict[str, set[str]]):
        self._graph = graph
        self._sorter = TopologicalSorter(graph)
        self._sorter.prepare()
        self._failed: set[str] = set()
        self._skip_set: set[str] = set()
        # Pre-compute reverse graph for failure propagation
        self._dependents: dict[str, set[str]] = {}
        for tid, deps in graph.items():
            for dep in deps:
                self._dependents.setdefault(dep, set()).add(tid)

    @property
    def is_active(self) -> bool:
        return self._sorter.is_active()

    def get_ready(self) -> list[str]:
        """Get tasks ready to dispatch (all deps satisfied, not skipped)."""
        ready = list(self._sorter.get_ready())
        # Filter out skipped tasks, marking them done immediately
        actual_ready = []
        for tid in ready:
            if tid in self._skip_set:
                self._sorter.done(tid)
            else:
                actual_ready.append(tid)
        return actual_ready

    def mark_done(self, task_id: str) -> None:
        """Mark a task as successfully completed."""
        self._sorter.done(task_id)

    def mark_failed(self, task_id: str) -> list[str]:
        """Mark a task as failed. Returns list of transitively skipped task IDs."""
        self._failed.add(task_id)
        self._sorter.done(task_id)  # unblock the sorter
        # Propagate failure: skip all transitive dependents
        skipped = []
        queue = list(self._dependents.get(task_id, set()))
        while queue:
            dependent = queue.pop()
            if dependent not in self._skip_set:
                self._skip_set.add(dependent)
                skipped.append(dependent)
                queue.extend(self._dependents.get(dependent, set()))
        return skipped


# ---------------------------------------------------------------------------
# Dispatching
# ---------------------------------------------------------------------------

def _find_dispatch_sh() -> str | None:
    """Locate dispatch.sh: env override first, then relative to this script."""
    env_override = os.environ.get("CLAVAIN_DISPATCH_SH")
    if env_override and os.path.exists(env_override):
        return env_override
    script_dir = Path(__file__).resolve().parent
    candidate = script_dir / "dispatch.sh"
    if candidate.exists():
        return str(candidate)
    # Fallback: search in plugin cache
    cache_dir = Path.home() / ".claude" / "plugins" / "cache"
    if cache_dir.exists():
        for p in sorted(cache_dir.glob("*/clavain/*/scripts/dispatch.sh")):
            return str(p)
    return None


def summarize_output(
    output_path: str | None, verdict_path: str | None, max_lines: int = 50
) -> str:
    """Summarize a completed task's output for dependency context."""
    parts = []

    if verdict_path and os.path.exists(verdict_path):
        with open(verdict_path) as f:
            verdict = f.read().strip()
        parts.append(verdict)

    if output_path and os.path.exists(output_path):
        with open(output_path) as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            parts.append("".join(lines[:max_lines]))
            parts.append(f"\n... ({len(lines) - max_lines} more lines truncated)")
        else:
            parts.append("".join(lines))

    return "\n".join(parts) if parts else "(no output)"


def build_prompt(
    task: Task,
    plan_path: str | None,
    dep_outputs: dict[str, TaskResult],
    all_tasks: dict[str, Task],
) -> str:
    """Build the prompt for a task, including dependency context."""
    sections = []

    # Dependency context
    if dep_outputs:
        sections.append("## Context from dependencies\n")
        for dep_id, result in dep_outputs.items():
            dep_task = all_tasks.get(dep_id)
            dep_title = dep_task.title if dep_task else dep_id
            sections.append(f"### {dep_id}: {dep_title}")
            sections.append(f"**Status:** {result.status}")
            summary = summarize_output(result.output_path, result.verdict_path)
            sections.append(summary)
            sections.append("")

    # Task description
    sections.append(f"## Task: {task.title}\n")
    if task.files:
        sections.append("**Files:**")
        for f in task.files:
            sections.append(f"- {f}")
        sections.append("")
    if task.prompt_hint:
        sections.append(task.prompt_hint)
        sections.append("")

    # Plan reference
    if plan_path:
        sections.append(f"**Full plan:** {plan_path}")
        sections.append("Read the plan for detailed step-by-step instructions for this task.")
        sections.append("")

    # Verdict suffix
    sections.append(textwrap.dedent("""\
        When done, report:
        VERDICT: CLEAN | NEEDS_ATTENTION [reason]
        FILES_CHANGED: [list]
    """))

    return "\n".join(sections)


def _as_text(x: str | bytes | None) -> str:
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode(errors="replace")
    return x


def _outcome_check(task: Task, project_dir: str, since: float) -> bool:
    """Ground-truth probe: do the task's declared files exist, with at least
    one touched since dispatch started?

    Used when the verdict channel is unreliable (timeout, missing sidecar,
    nonzero exit) so a completed-but-unwitnessed task is not marked ERROR
    and its dependents wrongly skipped (Sylveste-e9y). The mtime clause
    keeps modify-only tasks from passing trivially on pre-existing files.
    """
    if not task.files:
        return False
    paths = [os.path.join(project_dir, f) for f in task.files]
    if not all(os.path.exists(p) for p in paths):
        return False
    return any(os.path.getmtime(p) >= since for p in paths)


def _read_verdict_status(verdict_path: str) -> str | None:
    if not os.path.exists(verdict_path):
        return None
    with open(verdict_path) as f:
        for line in f:
            if line.startswith("STATUS:"):
                return line.split(":", 1)[1].strip()
    return None


def _dispatch_via_tmux(
    cmd: list[str],
    env: dict[str, str],
    task_dir: str,
    task_id: str,
    stall_timeout: int,
    session: str,
) -> tuple[int, bool]:
    """Run cmd in a dedicated tmux window; timeout on OUTPUT STALL, not wall
    clock — no log growth for stall_timeout seconds kills the task, but a
    slow-and-steady task runs up to a 6x wall-clock backstop (Sylveste-e9y
    stage 2). Returns (returncode, timed_out)."""
    exit_file = os.path.join(task_dir, "exit")
    log_path = os.path.join(task_dir, "dispatch.log")
    runner = os.path.join(task_dir, "runner.sh")

    exports = "".join(
        f"export {k}={shlex.quote(env[k])}\n"
        for k in ("PATH", "HOME", "CLAVAIN_DISPATCH_PROFILE",
                  "CLAVAIN_ROUTING_CONFIG", "CLAVAIN_SOURCE_DIR",
                  "CLAVAIN_DISPATCH_SH")
        if k in env
    )
    with open(runner, "w") as f:
        f.write(
            "#!/bin/bash\n" + exports
            + " ".join(shlex.quote(c) for c in cmd)
            + f" 2>&1 | tee {shlex.quote(log_path)}\n"
            + f"echo ${{PIPESTATUS[0]}} > {shlex.quote(exit_file)}\n"
        )
    os.chmod(runner, 0o755)

    subprocess.run(
        ["tmux", "new-window", "-d", "-t", session, "-n", task_id,
         f"bash {shlex.quote(runner)}"],
        check=True, capture_output=True,
    )

    start = time.time()
    last_size, last_change = -1, start
    while True:
        if os.path.exists(exit_file):
            try:
                with open(exit_file) as f:
                    return int(f.read().strip() or "1"), False
            except ValueError:
                return 1, False
        now = time.time()
        size = os.path.getsize(log_path) if os.path.exists(log_path) else -1
        if size != last_size:
            last_size, last_change = size, now
        if now - last_change > stall_timeout or now - start > stall_timeout * 6:
            subprocess.run(
                ["tmux", "kill-window", "-t", f"{session}:{task_id}"],
                capture_output=True,
            )
            return -1, True
        time.sleep(2)


def dispatch_task(
    task: Task,
    manifest: Manifest,
    project_dir: str,
    plan_path: str | None,
    dep_outputs: dict[str, TaskResult],
    dispatch_sh: str,
    run_id: str,
    run_dir: str,
    use_tmux: bool = False,
) -> TaskResult:
    """Dispatch a single task via dispatch.sh and return the result.

    All per-task artifacts (prompt, dispatch log, output, verdict, meta)
    persist under run_dir/<task_id>/ and SURVIVE failure — never written
    to a cleaned-up temp dir (Sylveste-e9y)."""
    task_dir = os.path.join(run_dir, task.id)
    os.makedirs(task_dir, exist_ok=True)
    prompt_path = os.path.join(task_dir, "prompt.md")
    output_path = os.path.join(task_dir, "output.md")
    verdict_path = f"{output_path}.verdict"
    log_path = os.path.join(task_dir, "dispatch.log")

    prompt = build_prompt(task, plan_path, dep_outputs, manifest.tasks)
    with open(prompt_path, "w") as f:
        f.write(prompt)

    tier = task.tier or manifest.tier
    cmd = [
        "bash", dispatch_sh,
        "--prompt-file", prompt_path,
        "-C", project_dir,
        "-o", output_path,
        "--tier", tier,
        "-s", "workspace-write",
    ]

    env = os.environ.copy()
    # Check for interserve mode
    flag_file = os.path.join(project_dir, ".claude", "clodex-toggle.flag")
    if os.path.exists(flag_file):
        env["CLAVAIN_DISPATCH_PROFILE"] = "interserve"

    start = time.time()
    timed_out = False
    returncode: int | None = None
    try:
        if use_tmux:
            returncode, timed_out = _dispatch_via_tmux(
                cmd, env, task_dir, task.id,
                manifest.timeout_per_task,
                _tmux_session_name(project_dir, run_id),
            )
        else:
            result = subprocess.run(
                cmd, env=env, capture_output=True, text=True,
                timeout=manifest.timeout_per_task,
            )
            returncode = result.returncode
            with open(log_path, "w") as f:
                f.write(_as_text(result.stdout))
                if result.stderr:
                    f.write("\n--- stderr ---\n" + _as_text(result.stderr))
    except subprocess.TimeoutExpired as e:
        timed_out = True
        with open(log_path, "w") as f:
            f.write(_as_text(e.stdout))
            f.write("\n--- stderr (partial, timeout) ---\n" + _as_text(e.stderr))
    except Exception as e:
        with open(log_path, "a") as f:
            f.write(f"\n--- dispatch exception ---\n{type(e).__name__}: {e}\n")
        return TaskResult(
            task_id=task.id, status="error",
            error=f"{type(e).__name__}: {e} (artifacts: {task_dir})",
            duration_s=time.time() - start,
        )

    duration = time.time() - start

    # Verdict resolution: sidecar first, then outcome cross-check. A timeout
    # or missing sidecar is NOT proof of failure — check what actually
    # happened on disk before cascading skips (task-9 false negative).
    note: str | None = None
    verdict_status = _read_verdict_status(verdict_path)
    if verdict_status:
        status = verdict_status
        if timed_out:
            note = "timed out after verdict was written"
    elif timed_out or (returncode is not None and returncode != 0):
        cause = "timeout (no output movement)" if timed_out else f"dispatch exit {returncode}"
        if _outcome_check(task, project_dir, since=start):
            status = "warn"
            note = (f"{cause}, but outcome-check passed (declared files present "
                    f"and touched) — completed-unverified; dependents run. Log: {log_path}")
        else:
            status = "error"
            note = f"{cause}; outcome-check failed. Artifacts: {task_dir}"
    else:
        status = "pass"

    with open(os.path.join(task_dir, "meta.json"), "w") as f:
        json.dump({
            "task": task.id, "title": task.title, "tier": tier,
            "cmd": cmd, "returncode": returncode, "timed_out": timed_out,
            "duration_s": round(duration, 1), "status": status, "note": note,
        }, f, indent=2)

    return TaskResult(
        task_id=task.id,
        status=status,
        output_path=output_path if os.path.exists(output_path) else None,
        verdict_path=verdict_path if os.path.exists(verdict_path) else None,
        error=note,
        duration_s=duration,
    )


def dispatch_batch(
    task_ids: list[str],
    manifest: Manifest,
    graph: dict[str, set[str]],
    project_dir: str,
    plan_path: str | None,
    completed: dict[str, TaskResult],
    dispatch_sh: str,
    run_id: str,
    run_dir: str,
    use_tmux: bool = False,
) -> dict[str, TaskResult]:
    """Dispatch a batch of tasks in parallel, collecting ALL results.

    Prints a flushed per-task completion line as each task finishes so the
    output stream carries live progress (Sylveste-e9y)."""
    results: dict[str, TaskResult] = {}

    def _dispatch_one(tid: str) -> TaskResult:
        task = manifest.tasks[tid]
        # Gather outputs from this task's direct dependencies
        dep_outputs = {
            dep_id: completed[dep_id]
            for dep_id in graph.get(tid, set())
            if dep_id in completed and completed[dep_id].status in ("pass", "warn")
        }
        return dispatch_task(
            task, manifest, project_dir, plan_path,
            dep_outputs, dispatch_sh, run_id, run_dir, use_tmux,
        )

    max_workers = min(manifest.max_parallel, len(task_ids))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_dispatch_one, tid): tid for tid in task_ids}
        for future in as_completed(futures):
            tid = futures[future]
            try:
                results[tid] = future.result()
            except Exception as e:
                results[tid] = TaskResult(
                    task_id=tid, status="error",
                    error=f"{type(e).__name__}: {e}",
                )
            res = results[tid]
            note = f" — {res.error}" if res.error else ""
            print(
                f"  [{res.status.upper()}] {tid} ({res.duration_s:.0f}s){note}",
                flush=True,
            )

    return results


# ---------------------------------------------------------------------------
# Push guard — executors must not push; the orchestrator owns pushes
# ---------------------------------------------------------------------------

GUARD_MARKER = "clavain-orchestrate-push-guard"


def _tmux_session_name(project_dir: str, run_id: str) -> str:
    """Session name in intermux's {terminal}-{project}-{agent}-{N} convention
    so orchestrated Codex runs appear in its agent listing (Sylveste-e9y)."""
    import re as _re
    proj = _re.sub(r"[^a-z0-9]", "", Path(project_dir).name.lower()) or "proj"
    return f"orc-{proj}-codex-{int(run_id[:6], 16) % 100000}"


def _find_task_repos(project_dir: str, tasks: dict[str, Task]) -> set[str]:
    """Find every git repo (project root + nested) that manifest files touch."""
    proj = Path(project_dir).resolve()
    candidates = {proj}
    for task in tasks.values():
        for f in task.files:
            d = (proj / f).parent
            if d == proj or proj in d.parents:
                candidates.add(d)
    repos: set[str] = set()
    for c in candidates:
        cur = c
        while True:
            if (cur / ".git").exists():
                repos.add(str(cur))
                break
            if cur == proj or cur.parent == cur:
                break
            cur = cur.parent
    return repos


def _git_hooks_dir(repo: str) -> Path | None:
    git = Path(repo) / ".git"
    if git.is_dir():
        return git / "hooks"
    if git.is_file():  # worktree / submodule pointer
        for line in git.read_text(errors="replace").splitlines():
            if line.startswith("gitdir:"):
                gd = Path(line.split(":", 1)[1].strip())
                if not gd.is_absolute():
                    gd = (Path(repo) / gd).resolve()
                return gd / "hooks"
    return None


def _install_push_guards(
    repos: set[str], run_id: str, run_dir: str
) -> list[tuple[Path, Path | None]]:
    """Install a pre-push hook in each repo that rejects pushes for the run's
    duration. Existing hooks are backed up and restored on removal.
    ORC_PUSH_GUARD_BYPASS=1 is the human escape hatch."""
    installed: list[tuple[Path, Path | None]] = []
    for repo in sorted(repos):
        hooks = _git_hooks_dir(repo)
        if hooks is None:
            continue
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "pre-push"
        backup: Path | None = None
        if hook.exists() and GUARD_MARKER not in hook.read_text(errors="replace"):
            backup = hooks / "pre-push.orc-bak"
            shutil.move(str(hook), str(backup))
        hook.write_text(
            "#!/bin/sh\n"
            f"# {GUARD_MARKER} run={run_id}\n"
            "# Executor agents must not push; the orchestrator owns pushes (Sylveste-e9y).\n"
            'if [ -n "$ORC_PUSH_GUARD_BYPASS" ]; then exit 0; fi\n'
            f'echo "push-attempt $(date -u +%Y-%m-%dT%H:%M:%SZ) repo=$(pwd)" >> {shlex.quote(os.path.join(run_dir, "push-attempts.log"))}\n'
            f'echo "ERROR: git push blocked by clavain orchestrate run {run_id}'
            ' (ORC_PUSH_GUARD_BYPASS=1 to override)" >&2\n'
            "exit 1\n"
        )
        hook.chmod(0o755)
        installed.append((hook, backup))
    return installed


def _remove_push_guards(installed: list[tuple[Path, Path | None]]) -> None:
    for hook, backup in installed:
        try:
            if hook.exists() and GUARD_MARKER in hook.read_text(errors="replace"):
                hook.unlink()
            if backup and backup.exists():
                shutil.move(str(backup), str(hook))
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------

def orchestrate(
    manifest_path: str,
    plan_path: str | None = None,
    project_dir: str | None = None,
    mode_override: str | None = None,
    dry_run: bool = False,
    use_tmux: bool = False,
    keep_tmux: bool = False,
    no_push_guard: bool = False,
) -> dict[str, TaskResult]:
    """Run the full orchestration loop."""
    # Live progress even when stdout is a redirected file (Sylveste-e9y).
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass
    manifest = load_manifest(manifest_path)
    mode = mode_override or manifest.mode
    graph = build_graph(manifest)

    # Validate
    errors = validate_graph(graph, manifest)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if project_dir is None:
        project_dir = os.getcwd()

    dispatch_sh = _find_dispatch_sh()
    if not dispatch_sh and not dry_run:
        print("ERROR: dispatch.sh not found", file=sys.stderr)
        sys.exit(1)
    # Narrow type for dispatch calls (guarded by sys.exit above)
    assert dispatch_sh is not None or dry_run

    run_id = uuid4().hex[:8]
    completed: dict[str, TaskResult] = {}
    total_tasks = len(manifest.tasks)

    # Persistent per-run artifact dir — survives failure by design.
    run_dir = os.path.join(project_dir, ".clavain", "orchestrate-runs", run_id)
    if not dry_run:
        os.makedirs(run_dir, exist_ok=True)

    guards: list[tuple[Path, Path | None]] = []
    if not dry_run and not no_push_guard:
        guards = _install_push_guards(
            _find_task_repos(project_dir, manifest.tasks), run_id, run_dir,
        )

    tmux_session = _tmux_session_name(project_dir, run_id)
    if use_tmux and not dry_run:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", tmux_session, "-n", "orchestrator",
             f"sh -c 'echo clavain orchestrate run {run_id}; sleep 86400'"],
            check=True, capture_output=True,
        )

    print(f"Orchestrating {total_tasks} tasks (mode: {mode}, max_parallel: {manifest.max_parallel})")
    if not dry_run:
        print(f"Run artifacts: {run_dir}")
        if guards:
            print(f"Push guard: active in {len(guards)} repo(s) for run duration")
        if use_tmux:
            print(f"tmux mode: attach with `tmux attach -t {tmux_session}`")
    if dry_run:
        # Pre-compute all waves for summary header
        dry_waves = _compute_waves(graph, mode, manifest)
        max_par = max(len(w) for w in dry_waves) if dry_waves else 0
        print(f"Dry run: {len(dry_waves)} wave(s), max parallelism: {max_par}")
    print()

    try:
        if mode == "dependency-driven":
            scheduler = DependencyDrivenScheduler(graph)
            wave = 0
            while scheduler.is_active:
                ready = scheduler.get_ready()
                if not ready:
                    break
                wave += 1
                _print_wave(wave, ready, manifest.tasks, dry_run)
                if dry_run:
                    for tid in ready:
                        scheduler.mark_done(tid)
                        completed[tid] = TaskResult(task_id=tid, status="pass (dry-run)")
                    continue

                batch_results = dispatch_batch(
                    ready, manifest, graph, project_dir, plan_path,
                    completed, dispatch_sh, run_id, run_dir, use_tmux,  # type: ignore[arg-type]
                )
                for tid, result in batch_results.items():
                    completed[tid] = result
                    if result.status in ("pass", "warn"):
                        scheduler.mark_done(tid)
                    else:
                        skipped = scheduler.mark_failed(tid)
                        for skip_id in skipped:
                            completed[skip_id] = TaskResult(
                                task_id=skip_id, status="skipped",
                                error=f"Dependency {tid} failed",
                            )
                        if skipped:
                            print(f"  Skipped {len(skipped)} tasks due to {tid} failure: {skipped}")
        else:
            # Static batch modes
            if mode == "all-parallel":
                batches = _resolve_all_parallel(graph)
            elif mode == "all-sequential":
                batches = _resolve_all_sequential(graph)
            elif mode == "manual-batching":
                batches = _resolve_manual_batching(graph, manifest)
            else:
                print(f"ERROR: Unknown mode '{mode}'", file=sys.stderr)
                sys.exit(1)

            for wave, batch in enumerate(batches, 1):
                # Filter out tasks skipped by earlier failures
                active = [tid for tid in batch if tid not in completed]
                if not active:
                    continue
                _print_wave(wave, active, manifest.tasks, dry_run)
                if dry_run:
                    for tid in active:
                        completed[tid] = TaskResult(task_id=tid, status="pass (dry-run)")
                    continue

                batch_results = dispatch_batch(
                    active, manifest, graph, project_dir, plan_path,
                    completed, dispatch_sh, run_id, run_dir, use_tmux,  # type: ignore[arg-type]
                )
                for tid, result in batch_results.items():
                    completed[tid] = result
                    if result.status not in ("pass", "warn"):
                        # Propagate failure for static modes too
                        _propagate_failure(tid, graph, completed)
    finally:
        # Artifacts in run_dir persist deliberately (Sylveste-e9y) — only the
        # push guards and (on clean runs) the tmux session are torn down.
        _remove_push_guards(guards)
        if use_tmux and not dry_run and not keep_tmux:
            all_ok = all(
                r.status in ("pass", "warn") or r.status.startswith("pass")
                for r in completed.values()
            )
            if all_ok and completed:
                subprocess.run(
                    ["tmux", "kill-session", "-t", tmux_session],
                    capture_output=True,
                )
            else:
                print(f"tmux session kept for inspection: tmux attach -t {tmux_session}")

    # Summary
    _print_summary(completed, manifest.tasks)
    return completed


def _compute_waves(
    graph: dict[str, set[str]],
    mode: str,
    manifest: Manifest,
) -> list[list[str]]:
    """Pre-compute wave groupings for dry-run summary without dispatching."""
    if mode == "all-parallel":
        return _resolve_all_parallel(graph)
    elif mode == "all-sequential":
        return _resolve_all_sequential(graph)
    elif mode == "manual-batching":
        return _resolve_manual_batching(graph, manifest)
    else:  # dependency-driven
        waves: list[list[str]] = []
        ts = TopologicalSorter(dict(graph))
        ts.prepare()
        while ts.is_active():
            ready = list(ts.get_ready())
            if not ready:
                break
            waves.append(ready)
            for tid in ready:
                ts.done(tid)
        return waves


def _propagate_failure(
    failed_id: str,
    graph: dict[str, set[str]],
    completed: dict[str, TaskResult],
) -> None:
    """For static batch modes, mark transitive dependents as skipped.

    NOTE: mirrors DependencyDrivenScheduler.mark_failed — keep in sync.
    """
    reverse: dict[str, set[str]] = {}
    for tid, deps in graph.items():
        for dep in deps:
            reverse.setdefault(dep, set()).add(tid)

    queue = list(reverse.get(failed_id, set()))
    while queue:
        dependent = queue.pop()
        if dependent not in completed:
            completed[dependent] = TaskResult(
                task_id=dependent, status="skipped",
                error=f"Dependency {failed_id} failed",
            )
            queue.extend(reverse.get(dependent, set()))


def _print_wave(
    wave: int,
    task_ids: list[str],
    tasks: dict[str, Task],
    dry_run: bool,
) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    parallelism = len(task_ids)
    par_label = f"parallel: {parallelism}" if parallelism > 1 else "sequential"
    # Group by stage for multi-stage visibility
    stages_in_wave: dict[str, list[str]] = {}
    for tid in task_ids:
        task = tasks.get(tid)
        stage = task.stage if task else "unnamed"
        stages_in_wave.setdefault(stage, []).append(tid)
    stage_str = ", ".join(stages_in_wave.keys())
    print(f"{prefix}Wave {wave}: {parallelism} task(s) ({par_label}) [{stage_str}]")
    for tid in task_ids:
        task = tasks.get(tid)
        title = task.title if task else tid
        files = ", ".join(task.files) if task and task.files else "(no files)"
        tier = task.tier if task and task.tier else "default"
        deps = task.depends if task else []
        dep_str = f" \u2190 [{', '.join(deps)}]" if deps else ""
        print(f"  {tid}: {title}")
        print(f"       files: {files}  tier: {tier}{dep_str}")
    print()


def count_verdicts(completed: dict[str, TaskResult]) -> dict[str, int]:
    """Bucket completed results into PASS / WARN / FAIL / SKIPPED counts.

    WARN (needs_attention) is deliberately kept separate from PASS so the
    summary does not roll caveated results into the clean-pass total — that
    masking nearly caused a premature phase advance (sylveste-nfqo).

    Buckets:
      pass    — clean pass (status "pass", including dry-run)
      warn    — needs-attention pass with a caveat (status "warn")
      fail    — hard failure (status "fail" or "error")
      skipped — dependency-blocked (status "skipped")
    """
    counts = {"pass": 0, "warn": 0, "fail": 0, "skipped": 0}
    for result in completed.values():
        status = result.status
        if status == "warn":
            counts["warn"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status in ("fail", "error"):
            counts["fail"] += 1
        elif status == "pass" or status.startswith("pass"):
            # "pass" and "pass (dry-run)" both count as clean passes
            counts["pass"] += 1
        else:
            # Unknown status — treat conservatively as a failure so it is
            # never silently rolled into the pass total.
            counts["fail"] += 1
    return counts


def _print_summary(
    completed: dict[str, TaskResult], tasks: dict[str, Task]
) -> None:
    print()
    print("=" * 60)
    print("Orchestration Summary")
    print("=" * 60)

    by_status: dict[str, list[str]] = {}
    for tid, result in completed.items():
        by_status.setdefault(result.status, []).append(tid)

    for status, tids in sorted(by_status.items()):
        print(f"\n  {status.upper()}: {len(tids)}")
        for tid in tids:
            task = tasks.get(tid)
            title = task.title if task else tid
            result = completed[tid]
            extra = f" — {result.error}" if result.error else ""
            print(f"    {tid}: {title}{extra}")

    total = len(completed)
    counts = count_verdicts(completed)

    # Color-code the four counters when stdout is an interactive TTY.
    tty = sys.stdout.isatty()

    def _c(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if tty else text

    pass_str = _c("32", f"PASS: {counts['pass']}")        # green
    warn_str = _c("33", f"WARN: {counts['warn']}")        # yellow
    fail_str = _c("31", f"FAIL: {counts['fail']}")        # red
    skip_str = _c("90", f"SKIPPED: {counts['skipped']}")  # grey

    print(
        f"\n  Total: {total}  |  {pass_str}  {warn_str}  {fail_str}  {skip_str}"
    )
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DAG-based Codex agent dispatch orchestrator",
    )
    parser.add_argument("manifest", help="Path to .exec.yaml manifest")
    parser.add_argument("--plan", help="Path to companion markdown plan")
    parser.add_argument("--project-dir", help="Project directory (default: cwd)")
    parser.add_argument("--validate", action="store_true", help="Validate manifest and exit")
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without dispatching")
    parser.add_argument(
        "--mode",
        choices=["all-parallel", "all-sequential", "dependency-driven", "manual-batching"],
        help="Override manifest execution mode",
    )
    parser.add_argument(
        "--tmux", action="store_true",
        help="Dispatch each task in a named tmux window (live-watchable; "
             "stall-based timeout instead of wall-clock)",
    )
    parser.add_argument(
        "--keep-tmux", action="store_true",
        help="Keep the tmux session alive after a clean run",
    )
    parser.add_argument(
        "--no-push-guard", action="store_true",
        help="Skip installing the executor pre-push guard (guard is ON by default)",
    )

    args = parser.parse_args()

    if args.validate:
        manifest = load_manifest(args.manifest)
        graph = build_graph(manifest)
        errors = validate_graph(graph, manifest)
        if errors:
            print(f"Manifest INVALID: {len(errors)} error(s)")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print(f"Manifest valid: {len(manifest.tasks)} tasks, 0 cycles, mode: {manifest.mode}")
            sys.exit(0)

    orchestrate(
        manifest_path=args.manifest,
        plan_path=args.plan,
        project_dir=args.project_dir,
        mode_override=args.mode,
        dry_run=args.dry_run,
        use_tmux=args.tmux,
        keep_tmux=args.keep_tmux,
        no_push_guard=args.no_push_guard,
    )


if __name__ == "__main__":
    main()
