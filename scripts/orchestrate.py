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
import shutil
import subprocess
import sys
import tempfile
import textwrap
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
    """Locate dispatch.sh relative to this script."""
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


def dispatch_task(
    task: Task,
    manifest: Manifest,
    project_dir: str,
    plan_path: str | None,
    dep_outputs: dict[str, TaskResult],
    dispatch_sh: str,
    run_id: str,
    tmp_dir: str | None = None,
) -> TaskResult:
    """Dispatch a single task via dispatch.sh and return the result."""
    # Write prompt to run-scoped temp dir (cleaned up by orchestrate())
    base = tmp_dir or tempfile.gettempdir()
    prompt_path = os.path.join(base, f"orchestrate-{run_id}-{task.id}-prompt.md")
    output_path = os.path.join(base, f"orchestrate-{run_id}-{task.id}.md")
    verdict_path = f"{output_path}.verdict"

    prompt = build_prompt(task, plan_path, dep_outputs, manifest.tasks)
    with open(prompt_path, "w") as f:
        f.write(prompt)

    # Build dispatch.sh command
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

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=manifest.timeout_per_task,
        )
    except subprocess.TimeoutExpired as e:
        partial = (e.stderr or b"").decode(errors="replace")[-500:]
        return TaskResult(
            task_id=task.id, status="error",
            error=f"Timeout expired. Last stderr: {partial}",
        )
    except Exception as e:
        return TaskResult(
            task_id=task.id, status="error",
            error=f"{type(e).__name__}: {e}",
        )

    # Read status from verdict sidecar (not exit code)
    status = "error"
    if os.path.exists(verdict_path):
        with open(verdict_path) as f:
            for line in f:
                if line.startswith("STATUS:"):
                    status = line.split(":", 1)[1].strip()
                    break
    elif result.returncode == 0:
        status = "pass"

    return TaskResult(
        task_id=task.id,
        status=status,
        output_path=output_path if os.path.exists(output_path) else None,
        verdict_path=verdict_path if os.path.exists(verdict_path) else None,
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
    tmp_dir: str | None = None,
) -> dict[str, TaskResult]:
    """Dispatch a batch of tasks in parallel, collecting ALL results."""
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
            dep_outputs, dispatch_sh, run_id, tmp_dir,
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

    return results


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------

def orchestrate(
    manifest_path: str,
    plan_path: str | None = None,
    project_dir: str | None = None,
    mode_override: str | None = None,
    dry_run: bool = False,
) -> dict[str, TaskResult]:
    """Run the full orchestration loop."""
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
    tmp_dir = tempfile.mkdtemp(prefix=f"orchestrate-{run_id}-")

    print(f"Orchestrating {total_tasks} tasks (mode: {mode}, max_parallel: {manifest.max_parallel})")
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
                    completed, dispatch_sh, run_id, tmp_dir,  # type: ignore[arg-type]
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
                    completed, dispatch_sh, run_id, tmp_dir,  # type: ignore[arg-type]
                )
                for tid, result in batch_results.items():
                    completed[tid] = result
                    if result.status not in ("pass", "warn"):
                        # Propagate failure for static modes too
                        _propagate_failure(tid, graph, completed)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Summary
    _print_summary(completed, manifest.tasks)
    return completed


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
    print(f"{prefix}Wave {wave}: {len(task_ids)} task(s)")
    for tid in task_ids:
        task = tasks.get(tid)
        title = task.title if task else tid
        files = ", ".join(task.files) if task and task.files else "(no files)"
        tier = task.tier if task and task.tier else "default"
        deps = task.depends if task else []
        dep_str = f" ← [{', '.join(deps)}]" if deps else ""
        print(f"  {tid}: {title} ({files}) [tier: {tier}]{dep_str}")
    print()


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
    passed = sum(
        len(v) for k, v in by_status.items()
        if k in ("pass", "warn", "pass (dry-run)")
    )
    failed = total - passed
    print(f"\n  Total: {total}, Passed: {passed}, Failed/Skipped: {failed}")
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
    )


if __name__ == "__main__":
    main()
