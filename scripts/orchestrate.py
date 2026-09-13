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
    python3 orchestrate.py --pattern-f <run.pf.yaml> [--dry-run]

--pattern-f drives the offload loop of pattern-f-contracts.md from a run
file (see the Pattern F section below): gauge, worktree, executor, validation
seat, register rows, merge, with nothing dispatched by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import threading
import sys
import textwrap
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from uuid import uuid4

from verification_runner import (
    VerificationError, parse_verify_blocks, validate_spec, verify as verify_contract,
)

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
    verification: dict | None = None


@dataclass
class TaskResult:
    task_id: str
    status: str  # pass, warn, fail, error, skipped, escalated, question
    output_path: str | None = None
    verdict_path: str | None = None
    error: str | None = None
    duration_s: float = 0.0
    # Review/fix rounds consumed by the pipeline (0 = passed first review).
    rounds: int = 0
    verification_state: str | None = None
    verification_failure: str | None = None
    verification_receipt: str | None = None
    verification_receipt_sha256: str | None = None
    machine_eligible: bool = False


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
        class UniqueLoader(yaml.SafeLoader):
            pass
        def mapping(loader, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in result:
                    raise VerificationError(f"duplicate manifest key: {key}")
                result[key] = loader.construct_object(value_node, deep=deep)
            return result
        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        raw = yaml.load(f, Loader=UniqueLoader)

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
                verification=t.get("verification"),
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

        If a decision you cannot make yourself blocks the work (an ambiguous
        spec, conflicting constraints), do NOT guess: report
        VERDICT: QUESTION <the one-line question>
        and stop. The orchestrator parks the task for the coordinator.
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


# ---------------------------------------------------------------------------
# Review pipeline (goal 7d610151) — implement → machine verify → independent
# review → bounded fix loop.
#
# The executor's self-reported VERDICT is never the gate. That was the gap
# that kept this mode weaker than subagent-driven: a task's own "CLEAN" was
# taken at its word. Here, the plan's <verify> blocks run as machine gates
# first (free, deterministic — no reviewer is paid for a task that fails its
# own commands), then an INDEPENDENT reviewer reads the task-scoped git diff
# — never the executor's report — and rules pass/fail. Failures dispatch a
# fix and re-review, at most ORC_MAX_FIX_ROUNDS times; after two strikes the
# task parks as `escalated` for the controller, matching the capability-
# routing doctrine's escalation rule. A task that cannot proceed without a
# decision reports `VERDICT: QUESTION <q>` and parks as `question` instead
# of guessing.
#
# Reviewer engine is tier-routed (mk's ruling, 2026-08-13): fast-tier tasks
# get a codex reviewer, deep-tier tasks get a claude reviewer (dispatch.sh's
# --to claude engine; deep resolves to opus per the validator doctrine).
# ORC_REVIEW_ENGINE=codex|claude forces one for the whole run.
# ---------------------------------------------------------------------------

MAX_FIX_ROUNDS = int(os.environ.get("ORC_MAX_FIX_ROUNDS", "2"))
REVIEW_DIFF_MAX_LINES = 600

_TASK_HEADING = re.compile(r"^#{2,3}\s+Task\s+(\d+)\s*[:.]", re.MULTILINE)


@dataclass
class PlanTask:
    """One plan task's spec text and machine gates, as the reviewer sees it."""
    section: str
    verify: list[dict[str, str]] = field(default_factory=list)
    verification_error: str | None = None


def parse_plan_tasks(plan_path: str | None) -> dict[int, PlanTask]:
    """Split a plan into per-task sections and their <verify> entries.

    Keyed by task NUMBER (``## Task 3: …`` → 3), which maps to manifest ids
    by trailing digits (``task-3``). Plans without task headings, or a
    missing plan, yield {} — the pipeline then reviews on diff alone.
    """
    if not plan_path or not os.path.exists(plan_path):
        return {}
    with open(plan_path, errors="replace") as f:
        text = f.read()
    matches = list(_TASK_HEADING.finditer(text))
    # A verify block with no task mapping must not silently disappear.
    prefix = text[:matches[0].start()] if matches else text
    if re.search(r"</?verify\b", prefix, re.I):
        raise VerificationError("verify block has no task heading")
    out: dict[int, PlanTask] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[m.start():end]
        try:
            verify = parse_verify_blocks(section)
            error = None
        except VerificationError as exc:
            verify, error = [], str(exc)
        number = int(m.group(1))
        if number in out:
            raise VerificationError(f"duplicate plan task number: {number}")
        out[number] = PlanTask(section=section, verify=verify, verification_error=error)
    return out


def _task_plan_num(task_id: str) -> int | None:
    m = re.search(r"(\d+)$", task_id)
    return int(m.group(1)) if m else None


def _verification_evidence_dir() -> str:
    configured = os.environ.get("CLAVAIN_VERIFICATION_EVIDENCE_DIR")
    if configured:
        return configured
    # A private OS temporary root, never the orchestrator's in-source run_dir.
    return tempfile.mkdtemp(prefix="clavain-verification-", dir=str(Path(tempfile.gettempdir()).resolve()))


def run_verify_entries(
    entries: list[dict[str, str]], project_dir: str, timeout: int = 600,
) -> tuple[bool, str]:
    """Legacy tuple facade. The pipeline consumes structured results below."""
    result = verify_contract({"required": True, "checks": entries, "timeout": timeout},
                             project_dir, _verification_evidence_dir())
    return result.machine_eligible, result.summary


def _task_verification(task: Task, info: PlanTask | None) -> dict:
    if info and info.verification_error:
        raise VerificationError(info.verification_error)
    config = dict(task.verification) if task.verification is not None else {}
    # Manifest checks and plan gates are both required; neither overrides the other.
    checks = config.get("checks", [])
    if not isinstance(checks, list):
        raise VerificationError("verification checks must be a list")
    config["checks"] = list(checks) + (info.verify if info else [])
    validate_spec(config)
    return config


def _git(project_dir: str, *args: str) -> str:
    try:
        p = subprocess.run(
            ["git", "-C", project_dir, *args],
            capture_output=True, text=True, timeout=60,
        )
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _git_head(project_dir: str) -> str | None:
    out = _git(project_dir, "rev-parse", "HEAD").strip()
    return out or None


def task_diff(project_dir: str, head0: str | None) -> str:
    """The reviewer's ground truth: everything that changed since the task
    started — committed and uncommitted — plus the contents of new untracked
    files, which `git diff` alone would silently omit."""
    parts: list[str] = []
    if head0:
        parts.append(_git(project_dir, "diff", "--stat", head0))
        parts.append(_git(project_dir, "diff", head0))
    else:
        parts.append(_git(project_dir, "diff"))
    untracked = _git(
        project_dir, "ls-files", "--others", "--exclude-standard",
    ).strip()
    if untracked:
        parts.append("## Untracked files created by this task:\n" + untracked)
        for f in untracked.splitlines()[:5]:
            fp = os.path.join(project_dir, f)
            try:
                with open(fp, errors="replace") as fh:
                    content = fh.read()
            except OSError:
                continue
            clines = content.splitlines()
            if len(clines) > 200:
                content = "\n".join(clines[:200]) + f"\n... ({len(clines) - 200} more lines)"
            parts.append(f"### {f}\n```\n{content}\n```")
    text = "\n".join(p for p in parts if p and p.strip())
    tlines = text.splitlines()
    if len(tlines) > REVIEW_DIFF_MAX_LINES:
        text = "\n".join(tlines[:REVIEW_DIFF_MAX_LINES]) + (
            f"\n... (truncated at {REVIEW_DIFF_MAX_LINES} lines; run"
            f" `git diff {head0 or ''}` in the repo for the rest)"
        )
    return text or "(no changes detected in the repository)"


def extract_question(output_path: str | None) -> str | None:
    """A parked question, if the executor reported one instead of guessing."""
    if not output_path or not os.path.exists(output_path):
        return None
    with open(output_path, errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("VERDICT: QUESTION"):
                return (
                    s[len("VERDICT: QUESTION"):].strip()
                    or "(question text missing — see the task output)"
                )
    return None


def build_review_prompt(
    task: Task,
    section: str,
    criteria_path: str | None,
    diff_text: str,
    verify_report: str,
    self_report: str,
) -> str:
    """The independent reviewer's brief. The diff is the evidence; the
    executor's self-report is context to be DISTRUSTED, included only so the
    reviewer can flag divergence between claim and diff."""
    parts = [textwrap.dedent(f"""\
        You are an independent spec-compliance reviewer for one task of a
        larger orchestrated plan. You did not write this code. Do NOT trust
        the executor's self-report — judge only what the diff and the
        repository actually show. You may run read-only commands (tests,
        `git log`, linters) to check claims; do not modify any file.

        ## The task under review: {task.title}
        Declared files: {", ".join(task.files) if task.files else "(none declared)"}
    """)]
    if section:
        parts.append("## The plan's specification for this task\n\n" + section)
    if criteria_path and os.path.exists(criteria_path):
        parts.append(
            f"## Sealed acceptance criteria\n\nRead {criteria_path} — where a"
            " criterion touches this task, hold the diff to it."
        )
    parts.append("## Machine verification (already run by the orchestrator)\n\n" + verify_report)
    parts.append("## The diff since this task started (ground truth)\n\n" + diff_text)
    parts.append("## Executor's self-report (untrusted, for divergence-spotting only)\n\n" + self_report)
    parts.append(textwrap.dedent("""\
        ## Your ruling

        Check, in order: (1) everything the spec requires is present in the
        diff; (2) nothing beyond the spec was built; (3) the change is
        correct — probe edge cases the spec implies, not just the happy
        path; (4) the self-report's claims match the diff.

        List concrete findings first (file, line, what is wrong, why it
        matters), each one actionable by a fix agent that has not seen this
        conversation. Then end your reply with EXACTLY one line:

        VERDICT: CLEAN
        (if the task passes review), or
        VERDICT: NEEDS_ATTENTION <one-line summary of the blocking findings>
    """))
    return "\n\n".join(parts)


def build_fix_prompt(
    task: Task, section: str, review_text: str, verify_report: str,
) -> str:
    parts = [textwrap.dedent(f"""\
        You are fixing review findings on a task you (or a prior agent)
        implemented as part of an orchestrated plan. Address EVERY finding
        below — do not re-litigate them, do not expand scope beyond them.
        Commit your fixes when done.

        ## The task: {task.title}
        Declared files: {", ".join(task.files) if task.files else "(none declared)"}
    """)]
    if section:
        parts.append("## The plan's specification for this task\n\n" + section)
    parts.append("## Machine verification results\n\n" + verify_report)
    parts.append("## Review findings to fix\n\n" + review_text)
    parts.append(textwrap.dedent("""\
        When done, report:
        VERDICT: CLEAN | NEEDS_ATTENTION [reason]
        FILES_CHANGED: [list]

        If a finding cannot be fixed without a decision only the coordinator
        can make, report VERDICT: QUESTION <the one-line question> instead
        of guessing.
    """))
    return "\n\n".join(parts)


def _review_engine_for(tier: str) -> str:
    forced = os.environ.get("ORC_REVIEW_ENGINE", "").strip()
    if forced in ("codex", "claude"):
        return forced
    return "claude" if tier == "deep" else "codex"


def _review_dirty_snapshot(project_dir: str, task: Task, manifest: Manifest) -> str:
    """git status --porcelain minus the paths sibling tasks declare. With
    max_parallel > 1 siblings commit into the same tree while a review runs,
    and a snapshot that includes their files invalidates clean reviews on
    every round (mk-b7e0). A declared directory covers everything under it."""
    siblings = {
        f for t in manifest.tasks.values() if t.id != task.id for f in t.files
    }
    dirs = tuple(s.rstrip("/") + "/" for s in siblings)
    kept: list[str] = []
    for line in _git(project_dir, "status", "--porcelain").splitlines():
        path = line[3:].split(" -> ")[-1].strip()
        if path in siblings or path.startswith(dirs):
            continue
        kept.append(line)
    return "\n".join(kept)


def dispatch_review(
    task: Task,
    tier: str,
    section: str,
    criteria_path: str | None,
    project_dir: str,
    head0: str | None,
    verify_report: str,
    impl_result: TaskResult,
    dispatch_sh: str,
    run_dir: str,
    round_num: int,
    manifest: Manifest,
) -> tuple[bool, str]:
    """Dispatch the independent reviewer. Returns (approved, review_text).

    Approved ONLY on an explicit clean verdict (sidecar STATUS pass). A
    malformed or missing verdict is not approval — conservative by design.
    """
    task_dir = os.path.join(run_dir, task.id)
    engine = _review_engine_for(tier)

    self_report = "(no executor output)"
    if impl_result.output_path and os.path.exists(impl_result.output_path):
        with open(impl_result.output_path, errors="replace") as f:
            self_report = "\n".join(f.read().splitlines()[-30:])

    prompt = build_review_prompt(
        task, section, criteria_path,
        task_diff(project_dir, head0), verify_report, self_report,
    )
    prompt_path = os.path.join(task_dir, f"review-{round_num}.prompt.md")
    output_path = os.path.join(task_dir, f"review-{round_num}.md")
    with open(prompt_path, "w") as f:
        f.write(prompt)

    cmd = [
        "bash", dispatch_sh,
        "--prompt-file", prompt_path,
        "-C", project_dir,
        "-o", output_path,
        "--to", engine,
        "--tier", tier,
    ]
    if engine == "codex":
        # The codex reviewer needs workspace-write to RUN tests; the prompt
        # forbids edits and the dirty-tree check below catches violations.
        cmd += ["-s", "workspace-write"]

    dirty_before = _review_dirty_snapshot(project_dir, task, manifest)
    try:
        _rc, timed_out, out, err = run_in_group(cmd, timeout=manifest.timeout_per_task)
        with open(os.path.join(task_dir, f"review-{round_num}.log"), "w") as f:
            f.write(out)
            if err:
                f.write("\n--- stderr ---\n" + err)
        if timed_out:
            return False, (
                f"(reviewer timed out after {manifest.timeout_per_task}s; its process "
                "group was killed — treated as not approved)"
            )
    except Exception as e:  # noqa: BLE001 — any dispatch failure is a non-approval
        return False, f"(reviewer dispatch failed: {type(e).__name__}: {e})"

    review_text = "(reviewer produced no output)"
    if os.path.exists(output_path):
        with open(output_path, errors="replace") as f:
            review_text = f.read()

    approved = _read_verdict_status(f"{output_path}.verdict") == "pass"

    dirty_after = _review_dirty_snapshot(project_dir, task, manifest)
    if dirty_after != dirty_before:
        approved = False
        review_text += (
            "\n\n(orchestrator: the REVIEWER modified the working tree — "
            "review invalidated; treat with suspicion and re-run.)"
        )
    return approved, review_text


def _write_text(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


def run_task_pipeline(
    task: Task,
    manifest: Manifest,
    project_dir: str,
    plan_path: str | None,
    plan_tasks: dict[int, PlanTask],
    criteria_path: str | None,
    dep_outputs: dict[str, TaskResult],
    dispatch_sh: str,
    run_id: str,
    run_dir: str,
    use_tmux: bool = False,
    review_enabled: bool = True,
) -> TaskResult:
    """implement → verify → review → (fix → verify → review)*, bounded.

    Falls back to plain dispatch_task semantics with --no-review.
    """
    task_dir = os.path.join(run_dir, task.id)
    num = _task_plan_num(task.id)
    plan_info = plan_tasks.get(num) if num is not None else None
    try:
        verification = _task_verification(task, plan_info)
    except (TypeError, ValueError) as exc:
        return TaskResult(task_id=task.id, status="error", error=f"UNVERIFIABLE: {exc}",
                          verification_state="UNVERIFIABLE", verification_failure="contract")
    head0 = _git_head(project_dir)

    result = dispatch_task(
        task, manifest, project_dir, plan_path,
        dep_outputs, dispatch_sh, run_id, run_dir, use_tmux,
    )
    q = extract_question(result.output_path)
    if q:
        result.status = "question"
        result.error = f"executor asks: {q}"
        return result
    if result.status == "error" or not review_enabled:
        return result

    num = _task_plan_num(task.id)
    plan_info = plan_tasks.get(num) if num is not None else None
    section = plan_info.section if plan_info else ""
    tier = task.tier or manifest.tier

    rounds = 0
    while True:
        verification_result = verify_contract(
            verification, project_dir, _verification_evidence_dir(),
            run_id=run_id, task_id=task.id, attempt=rounds,
        )
        vreport = verification_result.summary
        result.verification_state = verification_result.step.state.value
        result.verification_failure = verification_result.failure_kind
        result.verification_receipt = verification_result.receipt_path
        result.verification_receipt_sha256 = verification_result.step.extra.get("receipt_sha256")
        result.machine_eligible = verification_result.machine_eligible
        try:
            _write_text(os.path.join(task_dir, f"verify-{rounds}.txt"), vreport)
        except OSError as exc:
            result.status, result.error = "error", f"verification summary unavailable: {exc}"
            result.machine_eligible = False
            return result
        if not verification_result.review_allowed and not verification_result.repairable:
            result.status = "error"
            result.rounds = rounds
            result.error = vreport
            return result

        if verification_result.review_allowed:
            approved, review_text = dispatch_review(
                task, tier, section, criteria_path, project_dir, head0,
                vreport, result, dispatch_sh, run_dir, rounds + 1, manifest,
            )
        else:
            # Machine gates already failed — don't pay a reviewer to say so.
            approved = False
            review_text = (
                "Machine verification failed — the findings to fix are the"
                f" failing gates below.\n\n{vreport}"
            )

        if approved:
            result.rounds = rounds
            if rounds:
                result.error = (
                    (result.error + "; " if result.error else "")
                    + f"review passed after {rounds} fix round(s)"
                )
            print(f"  [review] {task.id}: approved (round {rounds})", flush=True)
            return result

        if rounds >= MAX_FIX_ROUNDS:
            result.status = "escalated"
            result.rounds = rounds
            result.error = (
                f"review/verify still failing after {rounds} fix round(s) — "
                f"two strikes, parked for the controller. Artifacts: {task_dir}"
            )
            return result

        rounds += 1
        print(f"  [review] {task.id}: not approved — fix round {rounds}", flush=True)
        fix_prompt = build_fix_prompt(task, section, review_text, vreport)
        result = dispatch_task(
            task, manifest, project_dir, plan_path,
            dep_outputs, dispatch_sh, run_id, run_dir, use_tmux,
            prompt_text=fix_prompt, phase=f"fix-{rounds}",
        )
        q = extract_question(result.output_path)
        if q:
            result.status = "question"
            result.rounds = rounds
            result.error = f"fix agent asks: {q}"
            return result
        if result.status == "error":
            result.status = "escalated"
            result.rounds = rounds
            result.error = f"fix dispatch {rounds} errored — parked. {result.error or ''}"
            return result


def _dispatch_via_tmux(
    cmd: list[str],
    env: dict[str, str],
    task_dir: str,
    task_id: str,
    stall_timeout: int,
    session: str,
    stem: str = "",
) -> tuple[int, bool]:
    """Run cmd in a dedicated tmux window; timeout on OUTPUT STALL, not wall
    clock — no log growth for stall_timeout seconds kills the task, but a
    slow-and-steady task runs up to a 6x wall-clock backstop (Sylveste-e9y
    stage 2). Returns (returncode, timed_out). ``stem`` keeps pipeline fix
    rounds from clobbering the implement round's artifact names."""
    exit_file = os.path.join(task_dir, f"{stem}exit")
    log_path = os.path.join(task_dir, f"{stem}dispatch.log")
    runner = os.path.join(task_dir, f"{stem}runner.sh")

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

    # Monotonic clock: it pauses during system sleep (macOS and Linux), so a
    # closed lid doesn't read as an output stall and falsely kill the task
    # on wake (goal e453fc6a).
    start = time.monotonic()
    last_size, last_change = -1, start
    while True:
        if os.path.exists(exit_file):
            try:
                with open(exit_file) as f:
                    return int(f.read().strip() or "1"), False
            except ValueError:
                return 1, False
        now = time.monotonic()
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


def _clear_dispatch_artifacts(output_path: str, verdict_path: str) -> None:
    """Remove outputs whose contents belong to an earlier dispatch."""
    for path in (output_path, verdict_path, f"{verdict_path}.pre-error"):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


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
    prompt_text: str | None = None,
    phase: str | None = None,
) -> TaskResult:
    """Dispatch a single task via dispatch.sh and return the result.

    All per-task artifacts (prompt, dispatch log, output, verdict, meta)
    persist under run_dir/<task_id>/ and SURVIVE failure — never written
    to a cleaned-up temp dir (Sylveste-e9y).

    ``prompt_text`` overrides the built prompt (fix rounds); ``phase``
    prefixes the artifact filenames so pipeline rounds don't clobber the
    implement round's legacy names (prompt.md / output.md)."""
    task_dir = os.path.join(run_dir, task.id)
    os.makedirs(task_dir, exist_ok=True)
    stem = f"{phase}." if phase else ""
    prompt_path = os.path.join(task_dir, f"{stem}prompt.md")
    output_path = os.path.join(task_dir, f"{stem}output.md")
    verdict_path = f"{output_path}.verdict"
    log_path = os.path.join(task_dir, f"{stem}dispatch.log")

    _clear_dispatch_artifacts(output_path, verdict_path)

    prompt = prompt_text or build_prompt(task, plan_path, dep_outputs, manifest.tasks)
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
    start_mono = time.monotonic()
    timed_out = False
    returncode: int | None = None
    try:
        if use_tmux:
            returncode, timed_out = _dispatch_via_tmux(
                cmd, env, task_dir, task.id,
                manifest.timeout_per_task,
                _tmux_session_name(project_dir, run_id),
                stem=stem,
            )
        else:
            # Own process group: a timeout kills the group, not just
            # dispatch.sh, so its codex/claude grandchild dies too (mk-kj2m).
            returncode, timed_out, out, err = run_in_group(
                cmd, env=env, timeout=manifest.timeout_per_task,
            )
            with open(log_path, "w") as f:
                f.write(out)
                if timed_out:
                    f.write("\n--- stderr (partial, timeout; process group killed) ---\n" + err)
                elif err:
                    f.write("\n--- stderr ---\n" + err)
    except Exception as e:
        with open(log_path, "a") as f:
            f.write(f"\n--- dispatch exception ---\n{type(e).__name__}: {e}\n")
        return TaskResult(
            task_id=task.id, status="error",
            error=f"{type(e).__name__}: {e} (artifacts: {task_dir})",
            duration_s=time.time() - start,
        )

    duration = time.time() - start
    duration_mono = time.monotonic() - start_mono

    # Verdict resolution: sidecar first, then outcome cross-check. A timeout
    # or missing sidecar is NOT proof of failure — check what actually
    # happened on disk before cascading skips (task-9 false negative).
    note: str | None = None
    # A file that exists but is empty is not output: dispatch.sh pre-creates
    # output.md through tee on the claude and kimi engines, so an existence
    # check reads a silent timeout as output movement (mk-9hqr).
    fresh_output = os.path.exists(output_path) and os.path.getsize(output_path) > 0
    fresh_verdict = (
        os.path.exists(verdict_path)
        and os.path.getmtime(verdict_path) >= start
    )
    verdict_status = _read_verdict_status(verdict_path) if fresh_verdict else None
    if verdict_status:
        status = verdict_status
        if timed_out:
            note = "timed out after verdict was written"
    elif timed_out or (returncode is not None and returncode != 0):
        if timed_out and not fresh_output:
            cause = "timed out, no fresh output"
        else:
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

    # timeout_per_task runs on the monotonic clock, which pauses during
    # system sleep on macOS — surface the divergence so a 2624s wall reading
    # against an 1800s ceiling reads as "lid closed", not "timeout broken"
    # (run 9d5d116d task-2, goal e453fc6a).
    slept = duration - duration_mono
    if slept > 120:
        sleep_note = (
            f"wall-clock exceeded monotonic by {int(slept)}s — system likely "
            "slept mid-dispatch; timeout_per_task counts monotonic time only"
        )
        note = f"{note}; {sleep_note}" if note else sleep_note

    with open(os.path.join(task_dir, f"{stem}meta.json"), "w") as f:
        json.dump({
            "task": task.id, "title": task.title, "tier": tier,
            "phase": phase or "implement",
            "cmd": cmd, "returncode": returncode, "timed_out": timed_out,
            "duration_s": round(duration, 1),
            "duration_monotonic_s": round(duration_mono, 1),
            "status": status, "note": note,
        }, f, indent=2)

    return TaskResult(
        task_id=task.id,
        status=status,
        output_path=output_path if fresh_output else None,
        verdict_path=verdict_path if fresh_verdict else None,
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
    plan_tasks: dict[int, PlanTask] | None = None,
    criteria_path: str | None = None,
    review_enabled: bool = True,
    journal_path: str | None = None,
) -> dict[str, TaskResult]:
    """Dispatch a batch of tasks in parallel, collecting ALL results.

    Prints a flushed per-task completion line as each task finishes so the
    output stream carries live progress (Sylveste-e9y). Each completion is
    journaled immediately (not at batch end) so a kill mid-wave loses only
    in-flight tasks, never finished ones (goal e453fc6a)."""
    results: dict[str, TaskResult] = {}

    def _dispatch_one(tid: str) -> TaskResult:
        task = manifest.tasks[tid]
        # Gather outputs from this task's direct dependencies
        dep_outputs = {
            dep_id: completed[dep_id]
            for dep_id in graph.get(tid, set())
            if dep_id in completed and completed[dep_id].status in ("pass", "warn")
        }
        return run_task_pipeline(
            task, manifest, project_dir, plan_path,
            plan_tasks or {}, criteria_path,
            dep_outputs, dispatch_sh, run_id, run_dir, use_tmux,
            review_enabled=review_enabled,
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
            if journal_path:
                _journal_append(
                    journal_path,
                    _journal_task_entry(run_dir, project_dir, res),
                )

    return results


# ---------------------------------------------------------------------------
# Run journal — kill-safe record of per-task completion (goal e453fc6a)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _journal_append(journal_path: str, entry: dict) -> None:
    """Append one JSONL entry, fsynced — the journal must survive SIGKILL
    arriving the instant after a task completes."""
    with open(journal_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read_journal(run_dir: str) -> list[dict]:
    path = os.path.join(run_dir, "journal.jsonl")
    entries: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # torn write from a kill mid-append
    except OSError:
        pass
    return entries


def _journal_completed(entries: list[dict]) -> dict[str, dict]:
    """Tasks whose LAST journal entry is terminal-complete (pass/warn).

    With the review pipeline on, pass/warn is only reachable through review
    approval, so these are safe to skip on resume. escalated / question /
    error / skipped tasks re-dispatch."""
    last: dict[str, dict] = {}
    for e in entries:
        if e.get("event") == "task" and e.get("task"):
            last[e["task"]] = e
    return {
        tid: e for tid, e in last.items()
        if e.get("status") in ("pass", "warn")
    }


def _journal_task_entry(run_dir: str, project_dir: str, res: TaskResult) -> dict:
    task_dir = Path(run_dir) / res.task_id
    reviews = sorted(task_dir.glob("review-*.md.verdict"))
    return {
        "event": "task",
        "task": res.task_id,
        "status": res.status,
        "rounds": res.rounds,
        "error": res.error,
        "duration_s": round(res.duration_s, 1),
        "output": res.output_path,
        "verdict": res.verdict_path,
        "review_verdict": str(reviews[-1]) if reviews else None,
        "verification_state": res.verification_state,
        "verification_failure": res.verification_failure,
        "verification_receipt": res.verification_receipt,
        "verification_receipt_sha256": res.verification_receipt_sha256,
        "machine_eligible": res.machine_eligible,
        "head": _git_head(project_dir),
        "ts": _now_iso(),
    }


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
        elif (hooks / "pre-push.orc-bak").exists():
            # A stranded guard's backup with no original hook left to sweep —
            # adopt it so this run's teardown restores the user's real hook
            # instead of leaving it as .orc-bak forever.
            backup = hooks / "pre-push.orc-bak"
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


def _pid_alive(pidfile: str) -> bool:
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _sweep_stranded_guards(repos: set[str]) -> None:
    """Remove/restore pre-push guards stranded by a killed orchestrator.

    SIGKILL skips orchestrate()'s finally-teardown, so both scene-pilot kills
    (runs 3155e212, 9d5d116d) left the guard blocking all pushes until a human
    deleted it. A guard is stranded when the run that installed it — located
    via the push-attempts.log path in the hook body — has no live orchestrator
    pid. A live pid means a concurrent run owns the guard: leave it."""
    for repo in sorted(repos):
        hooks = _git_hooks_dir(repo)
        if hooks is None:
            continue
        hook = hooks / "pre-push"
        if not hook.exists():
            continue
        text = hook.read_text(errors="replace")
        if GUARD_MARKER not in text:
            continue
        m = re.search(r">> '?([^'\n]*push-attempts\.log)", text)
        old_run_dir = os.path.dirname(m.group(1)) if m else None
        if old_run_dir and _pid_alive(os.path.join(old_run_dir, "orchestrator.pid")):
            continue
        backup = hooks / "pre-push.orc-bak"
        try:
            hook.unlink()
            if backup.exists():
                shutil.move(str(backup), str(hook))
                print(f"Swept stranded push guard in {repo} (original pre-push restored)")
            else:
                print(f"Swept stranded push guard in {repo}")
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
    review_enabled: bool = True,
    resume_run_id: str | None = None,
) -> dict[str, TaskResult]:
    """Run the full orchestration loop.

    ``resume_run_id`` resumes a prior (killed or partially failed) run: the
    prior run's journal.jsonl identifies terminal-complete tasks, which are
    skipped with their dependency edges treated as satisfied; everything
    else re-dispatches into the SAME run dir (goal e453fc6a)."""
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

    completed: dict[str, TaskResult] = {}
    total_tasks = len(manifest.tasks)

    if resume_run_id:
        run_id = resume_run_id
        run_dir = os.path.join(project_dir, ".clavain", "orchestrate-runs", run_id)
        if not os.path.exists(os.path.join(run_dir, "journal.jsonl")):
            print(
                f"ERROR: cannot resume run {run_id} — no journal at "
                f"{run_dir}/journal.jsonl",
                file=sys.stderr,
            )
            sys.exit(1)
        for tid, e in sorted(_journal_completed(_read_journal(run_dir)).items()):
            if tid not in manifest.tasks:
                continue
            completed[tid] = TaskResult(
                task_id=tid,
                status=e["status"],
                output_path=e.get("output"),
                verdict_path=e.get("verdict"),
                error="resumed: complete in prior run",
                duration_s=0.0,
                rounds=e.get("rounds", 0) or 0,
            )
    else:
        run_id = uuid4().hex[:8]
        run_dir = os.path.join(project_dir, ".clavain", "orchestrate-runs", run_id)

    # Review-pipeline inputs: the plan's per-task sections + <verify> blocks,
    # and the sealed criteria sidecar when one sits next to the plan.
    try:
        plan_tasks = parse_plan_tasks(plan_path)
        for task in manifest.tasks.values():
            number = _task_plan_num(task.id)
            try:
                _task_verification(task, plan_tasks.get(number))
            except (TypeError, ValueError) as exc:
                raise VerificationError(f"{task.id}: {exc}") from exc
    except (TypeError, ValueError) as exc:
        return {tid: TaskResult(task_id=tid, status="error", error=f"UNVERIFIABLE: {exc}",
                                verification_state="UNVERIFIABLE", verification_failure="contract")
                for tid in manifest.tasks}
    criteria_path: str | None = None
    if plan_path and plan_path.endswith(".md"):
        candidate = plan_path[:-3] + ".criteria.md"
        if os.path.exists(candidate):
            criteria_path = candidate

    # Sweep BEFORE writing this run's pidfile: a resume reuses the killed
    # run's run_dir, and writing our own (live) pid first would make the
    # stranded guard look like a concurrent run's and never get swept.
    guards: list[tuple[Path, Path | None]] = []
    repos: set[str] = set()
    if not dry_run and not no_push_guard:
        repos = _find_task_repos(project_dir, manifest.tasks)
        _sweep_stranded_guards(repos)

    # Persistent per-run artifact dir — survives failure by design.
    journal_path: str | None = None
    if not dry_run:
        os.makedirs(run_dir, exist_ok=True)
        # Liveness marker: lets a later invocation distinguish a stranded
        # push guard (dead pid) from a concurrent run's live one.
        with open(os.path.join(run_dir, "orchestrator.pid"), "w") as f:
            f.write(str(os.getpid()))
        journal_path = os.path.join(run_dir, "journal.jsonl")

    if repos:
        guards = _install_push_guards(repos, run_id, run_dir)

    if journal_path:
        _journal_append(journal_path, {
            "event": "resume" if resume_run_id else "run_start",
            "run_id": run_id,
            "pid": os.getpid(),
            "manifest": os.path.abspath(manifest_path),
            "plan": os.path.abspath(plan_path) if plan_path else None,
            "resumed_complete": sorted(completed) if resume_run_id else [],
            "guards": [
                {"hook": str(h), "backup": str(b) if b else None}
                for h, b in guards
            ],
            "ts": _now_iso(),
        })

    tmux_session = _tmux_session_name(project_dir, run_id)
    if use_tmux and not dry_run:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", tmux_session, "-n", "orchestrator",
             f"sh -c 'echo clavain orchestrate run {run_id}; sleep 86400'"],
            check=True, capture_output=True,
        )

    print(f"Orchestrating {total_tasks} tasks (mode: {mode}, max_parallel: {manifest.max_parallel})")
    if resume_run_id:
        print(
            f"Resuming run {run_id}: {len(completed)} task(s) journaled "
            f"complete, skipped: {', '.join(sorted(completed)) or '(none)'}"
        )
    if review_enabled:
        forced = os.environ.get("ORC_REVIEW_ENGINE", "").strip()
        routing = forced if forced else "fast→codex, deep→claude"
        print(
            f"Review pipeline: on (verify blocks: "
            f"{sum(len(t.verify) for t in plan_tasks.values())} across "
            f"{len(plan_tasks)} plan task(s); criteria: "
            f"{criteria_path or 'none'}; reviewer: {routing}; "
            f"max fix rounds: {MAX_FIX_ROUNDS})"
        )
    else:
        print("Review pipeline: OFF (--no-review) — executor self-reports gate task status")
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
                # Drain resumed tasks: journaled complete in a prior run —
                # mark done (edges satisfied) without dispatching.
                for tid in ready:
                    if tid in completed:
                        scheduler.mark_done(tid)
                ready = [tid for tid in ready if tid not in completed]
                if not ready:
                    continue
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
                    plan_tasks, criteria_path, review_enabled, journal_path,
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
                                error=f"Dependency {tid} {result.status}",
                            )
                        if skipped:
                            print(f"  Skipped {len(skipped)} tasks due to {tid} {result.status}: {skipped}")
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
                    plan_tasks, criteria_path, review_enabled, journal_path,
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
        if journal_path:
            _journal_append(journal_path, {
                "event": "run_end",
                "counts": count_verdicts(completed),
                "ts": _now_iso(),
            })
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
      pass      — clean pass (status "pass", including dry-run)
      warn      — needs-attention pass with a caveat (status "warn")
      fail      — hard failure (status "fail" or "error")
      skipped   — dependency-blocked (status "skipped")
      escalated — review/verify failing after the fix-round budget; parked
                  for the controller (two-strikes doctrine, goal 7d610151)
      question  — the executor asked instead of guessing; parked for the
                  coordinator's answer
    """
    counts = {
        "pass": 0, "warn": 0, "fail": 0, "skipped": 0,
        "escalated": 0, "question": 0,
    }
    for result in completed.values():
        status = result.status
        if status == "warn":
            counts["warn"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status in ("escalated", "question"):
            counts[status] += 1
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
            print(f"      verification={result.verification_state or 'not-run'} "
                  f"machine_eligible={str(result.machine_eligible).lower()}")
            if result.verification_receipt:
                print(f"      receipt={result.verification_receipt} sha256={result.verification_receipt_sha256}")

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
    esc_str = _c("35", f"ESCALATED: {counts['escalated']}")  # magenta
    q_str = _c("36", f"QUESTION: {counts['question']}")      # cyan

    print(
        f"\n  Total: {total}  |  {pass_str}  {warn_str}  {fail_str}  "
        f"{skip_str}  {esc_str}  {q_str}"
    )
    if counts["escalated"] or counts["question"]:
        print(
            "\n  Parked tasks need the controller: answer each QUESTION / rule"
            "\n  on each ESCALATED task's findings (see its artifacts dir),"
            "\n  then re-run — completed tasks are skipped by their dependents"
            "\n  only when they failed, so a re-run redispatches parked work."
        )
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Process-group dispatch (mk-kj2m)
#
# subprocess.run(timeout=...) kills only the direct child. dispatch.sh is a
# wrapper, and on uncrancher run 57651f7d its codex grandchild survived the
# kill and committed twelve minutes after its deadline. Every dispatch now
# leads its own session (a fresh process group); a timeout kills the group,
# TERM then KILL, so nothing the dispatch spawned outlives it.
# ---------------------------------------------------------------------------

GROUP_KILL_GRACE_S = float(os.environ.get("ORC_GROUP_KILL_GRACE", "5"))


def _kill_process_group(proc: subprocess.Popen, grace: float = GROUP_KILL_GRACE_S) -> None:
    """TERM the group led by ``proc`` (started with a new session, so the
    pgid is its pid), wait ``grace`` seconds for the leader, then KILL the
    group. Grandchildren stay in the group after the leader is reaped, so
    the KILL reaches them too."""
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if proc.poll() is None:
        proc.kill()


def run_in_group(
    cmd: list[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int | None, bool, str, str]:
    """Run ``cmd`` as the leader of a fresh session and process group. On
    timeout the whole group is killed, so a dispatch.sh child cannot leave
    its codex or claude grandchild running past the deadline (mk-kj2m).
    Returns ``(returncode, timed_out, stdout, stderr)``."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, False, out or "", err or ""
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            out, err = proc.communicate(timeout=GROUP_KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return proc.returncode, True, out or "", err or ""


# ---------------------------------------------------------------------------
# Pattern F mode (goal 60771535): --pattern-f <run.pf.yaml>
#
# The offload loop in skills/executing-plans/references/pattern-f-contracts.md
# was driven by hand on every goal before this one: gauge, dispatch, wait,
# validate, register, merge, each a main-thread turn. This mode drives it
# from a run file. Per item, in order:
#
#   gauge     plan-gauge-lint.py on the plan; a finding writes a gate row and
#             stops the item before any executor exists
#   worktree  a fresh git worktree on its own branch, with `ic init` run in
#             it so dispatch.sh --role can record its routing decision
#   execute   exact -> plan-gauge-lint.py --apply in the worktree, then one
#             commit by the orchestrator (no model is spawned)
#             brief -> dispatch.sh --role <executor role>; the executor commits
#   validate  dispatch.sh --role validation --plan <plan> with the producer
#             identity; the orchestrator writes a receipt nonce to disk AFTER
#             the prompt is fixed and records UNRUN unless the seat echoes it
#   register  pattern-f-verdict.sh with --db explicit: one row per verdict,
#             one independent row per BEYOND THE GAUGE finding; read back
#   merge     a validator PASS merges the branch into the repo and removes
#             the worktree; anything else keeps the worktree for the controller
#
# Every dispatch runs through run_in_group with the run's timeout. The last
# line of stdout is the closing packet, JSON on one line.
# ---------------------------------------------------------------------------

_PF_CONTRACT_LINE = re.compile(r"^\s*\**\s*contract\s*\**\s*:\s*\**\s*(brief|exact)\b", re.I)
_PF_GAUGE_CODE = re.compile(r"\b(?:GAUGE|BRIEF)\d{3}\b")
_PF_MODEL_LINE = re.compile(r"model[:=]\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PF_CMD_MODEL = re.compile(r"(?:^|\s)(?:-m|--model)\s+([A-Za-z0-9][A-Za-z0-9._-]*)")
PF_MAX_INDEPENDENT_ROWS = 12


@dataclass
class PFItem:
    id: str
    plan: str
    executor_role: str = "routine-execution"
    producer: str | None = None
    files: list[str] = field(default_factory=list)  # declared paths; empty = derive from the plan


@dataclass
class PFRun:
    session: str
    register: str
    repo: str
    items: list[PFItem]
    goal: str | None = None
    timeout: int = 2400
    producer: str | None = None
    trailers: list[str] = field(default_factory=list)
    max_parallel: int = 1
    reservation_db: str | None = None  # ic --db; default: ic's own resolution from repo
    reservation_scope: str | None = None  # default: the repo's absolute path, the hook's scope


@dataclass
class PFItemResult:
    id: str
    plan: str
    contract: str | None = None
    status: str = "pending"
    gauge_rc: int | None = None
    worktree: str | None = None
    branch: str | None = None
    executor_model: str | None = None
    executor_commit: str | None = None
    executor_verdict: str | None = None
    executor_criterion: str | None = None
    validator_model: str | None = None
    validator_verdict: str | None = None
    validator_criterion: str | None = None
    receipt_ok: bool | None = None
    independent_findings: int = 0
    merged: bool = False
    merge_commit: str | None = None
    register_rows: int = 0
    register_errors: int = 0
    note: str | None = None
    beyond_gauge: list[str] = field(default_factory=list)
    run: str = ""
    files: list[str] = field(default_factory=list)
    reservations: int = 0
    blocked_by: str | None = None
    wait_s: float = 0.0
    run_s: float = 0.0
    started: str | None = None
    finished: str | None = None
    merge_outcome: str = "not_attempted"  # merged | conflict | failed | not_attempted


@dataclass
class PFExecution:
    commit: str | None
    verdict: str
    criterion: str | None
    model: str | None
    note: str | None = None


@dataclass
class PFValidation:
    verdict: str
    criterion: str | None
    note: str | None
    receipt_ok: bool
    findings: list[str]
    model: str | None


def _pf_tool(env_key: str, name: str) -> str:
    override = os.environ.get(env_key)
    if override:
        return override
    return str(Path(__file__).resolve().parent / name)


def _pf_tools() -> dict[str, str | None]:
    return {
        "dispatch": _find_dispatch_sh(),
        "gauge": _pf_tool("CLAVAIN_GAUGE_LINT", "plan-gauge-lint.py"),
        "verdict": _pf_tool("CLAVAIN_VERDICT_SH", "pattern-f-verdict.sh"),
        "ic": os.environ.get("CLAVAIN_IC_BIN") or shutil.which("ic"),
    }


def pf_contract(plan_path: str) -> str | None:
    with open(plan_path, errors="replace") as f:
        for line in f:
            m = _PF_CONTRACT_LINE.match(line)
            if m:
                return m.group(1).lower()
    return None


def _pf_plan_title(plan_path: str) -> str:
    with open(plan_path, errors="replace") as f:
        for line in f:
            if line.startswith("# "):
                return line[2:].strip()
    return os.path.basename(plan_path)


def load_pf_run(path: str | Path) -> PFRun:
    _require_yaml()
    run_path = Path(path).resolve()
    with open(run_path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("run file must be a mapping")

    def _abs(p: str) -> str:
        return p if os.path.isabs(p) else str((run_path.parent / p).resolve())

    errors: list[str] = []
    session = str(data.get("session") or "").strip()
    register = str(data.get("register") or "").strip()
    repo = str(data.get("repo") or "").strip()
    if not session:
        errors.append("session is required (the register session id shared by every row)")
    if not register:
        errors.append("register is required (--db is always explicit)")
    else:
        register = _abs(register)
        if not os.path.isfile(register):
            errors.append(f"register not found: {register}")
    if not repo:
        errors.append("repo is required")
    else:
        repo = _abs(repo)
        if not os.path.exists(os.path.join(repo, ".git")):
            errors.append(f"repo is not a git checkout: {repo}")
    items: list[PFItem] = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            errors.append(f"item is not a mapping: {raw!r}")
            continue
        iid = str(raw.get("id") or "").strip()
        plan = str(raw.get("plan") or "").strip()
        if not iid or not plan:
            errors.append(f"every item needs id and plan: {raw!r}")
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", iid):
            errors.append(f"item id must be a branch-safe token: {iid!r}")
        plan = _abs(plan)
        if not os.path.isfile(plan):
            errors.append(f"item {iid}: plan not found: {plan}")
        files_raw = raw.get("files") or []
        if not isinstance(files_raw, list) or any(not isinstance(x, str) or not x.strip() for x in files_raw):
            errors.append(f"item {iid}: files must be a list of relative paths")
            files_raw = []
        files = [x.strip() for x in files_raw]
        if any(os.path.isabs(x) or x.startswith("..") for x in files):
            errors.append(f"item {iid}: files must be relative to the repo")
        items.append(PFItem(
            id=iid, plan=plan,
            executor_role=str(raw.get("executor_role") or data.get("executor_role") or "routine-execution"),
            producer=(str(raw["producer"]) if raw.get("producer") else None),
            files=files,
        ))
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        errors.append("item ids must be unique")
    if not items:
        errors.append("items is empty")
    timeout = data.get("timeout", 2400)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        errors.append("timeout must be a positive integer (seconds per dispatch)")
    max_parallel = data.get("max_parallel", 1)
    if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel < 1:
        errors.append("max_parallel must be a positive integer (items dispatched at once)")
        max_parallel = 1
    reservation_db = str(data["reservation_db"]).strip() if data.get("reservation_db") else None
    if reservation_db:
        reservation_db = _abs(reservation_db)
        if not os.path.isfile(reservation_db):
            errors.append(f"reservation_db not found: {reservation_db}")
    if errors:
        raise ValueError("invalid run file:\n  " + "\n  ".join(errors))
    return PFRun(
        session=session, register=register, repo=repo, items=items,
        goal=(str(data["goal"]) if data.get("goal") else None),
        timeout=int(timeout),
        producer=(str(data["producer"]) if data.get("producer") else None),
        trailers=[str(t) for t in (data.get("trailers") or [])],
        max_parallel=int(max_parallel),
        reservation_db=reservation_db,
        reservation_scope=(str(data["reservation_scope"]).strip() if data.get("reservation_scope") else None),
    )


def _pf_named_line(text: str, name: str) -> str | None:
    """`NAME: value`, tolerating a leading bullet or indent (kimi prefixes
    its lines with `• `)."""
    m = re.search(rf"^[ \t•*-]*{name}:[ \t]*(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def _pf_beyond_the_gauge(text: str) -> list[str]:
    """Bullets under BEYOND THE GAUGE:, minus `- none`."""
    m = re.search(r"^BEYOND THE GAUGE:[ \t]*$", text, re.M)
    if not m:
        return []
    findings: list[str] = []
    for line in text[m.end():].splitlines():
        s = line.strip()
        if not s:
            if findings:
                break
            continue
        if s[:2] in ("- ", "* "):
            body = s[2:].strip()
            if body.lower().rstrip(".") != "none":
                findings.append(body)
        elif findings and line[:1] in (" ", "\t"):
            findings[-1] += " " + s
        else:
            break
    return findings


_PF_ENV_FAILURES = (
    ("Tokio executor failed", "the test runner crashed before running the tests"),
    ("panicked", "the test runner crashed before running the tests"),
    ("exit 101", "the test runner crashed before running the tests"),
    ("Operation not permitted", "a path the seat needed was denied by its sandbox"),
    ("No virtual environment found", "no virtual environment in the worktree"),
    ("command not found", "a program the Verification names is missing"),
)


def _pf_environment_failure(report: str) -> str | None:
    """An environment failure named in the seat's own report (its CRITERION or
    BEYOND THE GAUGE lines): the runner never ran the tests, so the verdict is
    UNRUN, never FAIL (mk's ruling on Sylveste-ypvl, 2026-09-07)."""
    low = report.lower()
    for needle, why in _PF_ENV_FAILURES:
        if needle.lower() in low:
            return f"{why} ({needle!r} in the seat's report)"
    return None


def _pf_sidecar_summary(verdict_path: str) -> str | None:
    if not os.path.exists(verdict_path):
        return None
    with open(verdict_path, errors="replace") as f:
        for line in f:
            if line.startswith("SUMMARY:"):
                return line.split(":", 1)[1].strip()
    return None


def _pf_model(stderr: str, fallback: str | None) -> str | None:
    m = _PF_MODEL_LINE.search(stderr or "")
    return m.group(1) if m else fallback


def _pf_dry_run_text(cmd: list[str], cwd: str) -> str:
    """dispatch.sh --dry-run output: the command the role resolves to."""
    try:
        p = subprocess.run(cmd + ["--dry-run"], cwd=cwd, capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return ""
    return (p.stdout or "") + "\n" + (p.stderr or "")


def _pf_resolve_model(cmd: list[str], cwd: str, text: str | None = None) -> str | None:
    """Which model the role resolves to: the dry-run command names it
    (-m for codex, --model for claude)."""
    if text is None:
        text = _pf_dry_run_text(cmd, cwd)
    m = _PF_CMD_MODEL.search(text)
    return m.group(1) if m else None


def _pf_tree_snapshot(wt: str) -> str:
    """What a seat may not change: the status of every path (untracked
    included) and a digest of the diff against HEAD."""
    status = _git(wt, "status", "--porcelain", "--untracked-files=all")
    digest = hashlib.sha256(_git(wt, "diff", "HEAD").encode(errors="replace")).hexdigest()
    return status + "\n" + digest


def _pf_now() -> str:
    """UTC, second precision, Z suffix: what interstat's profile.py parses."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _pf_tail(path: str, n: int = 60) -> str:
    if not os.path.exists(path):
        return "(no output)"
    with open(path, errors="replace") as f:
        lines = f.read().splitlines()
    return "\n".join(lines[-n:]) if lines else "(empty output)"


_PF_PATHSPEC_LINE = re.compile(r"\bPathspec:\s*(.+?)\s*$", re.I | re.M)
PF_MAX_PATTERN_TOKENS = 50  # intercore's glob validator refuses longer patterns


def _pf_reservable(path: str) -> str:
    """The pattern reserved for a declared path. intercore counts one token
    per character and refuses more than 50, so a long path is broadened to
    its nearest short-enough parent directory with `/**`: over-reserving is
    safe, under-reserving is not."""
    pattern = path
    while len(pattern) > PF_MAX_PATTERN_TOKENS:
        parent = os.path.dirname(pattern.rstrip("/").removesuffix("/**").rstrip("/"))
        if not parent:
            return "**"
        pattern = parent + "/**"
    return pattern
_PF_COMMIT_PATHSPEC = re.compile(r"git\s+commit\b[^\n]*?\s--\s+([^\n`]+)")
_PF_PATH_TOKEN = re.compile(r"`((?:[\w.\-]+/)*[\w.\-]+\.[A-Za-z0-9]{1,8})`")
_PF_PATH_OK = re.compile(r"[\w.\-/]+")


def _pf_path_tokens(chunk: str) -> list[str]:
    out: list[str] = []
    for tok in chunk.split():
        tok = tok.strip("`'\" .;,")
        if not tok or tok.startswith(("-", "<", "/")) or not _PF_PATH_OK.fullmatch(tok):
            continue
        if "/" not in tok and "." not in tok:
            continue
        out.append(tok)
    return list(dict.fromkeys(out))


def _pf_declared_files(item: PFItem) -> list[str]:
    """The paths an item reserves before its worktree is cut. `files:` on the
    item wins; else the plan's commit pathspec (a `Pathspec:` line in an exact
    plan, `git commit ... -- <paths>` in a brief's Authority); else every
    backticked relative path in the plan, which over-reserves rather than
    under-reserves; else `**`, the whole tree, so an undeclared item runs
    alone. The dry run prints the derived list so an operator can override
    it with `files:`."""
    if item.files:
        return list(dict.fromkeys(item.files))
    with open(item.plan, errors="replace") as f:
        text = f.read()
    for rx in (_PF_PATHSPEC_LINE, _PF_COMMIT_PATHSPEC):
        m = rx.search(text)
        if m:
            toks = _pf_path_tokens(m.group(1))
            if toks:
                return toks
    toks = [t for t in _PF_PATH_TOKEN.findall(text) if not t.startswith("/")]
    return list(dict.fromkeys(toks)) or ["**"]


def _pf_scope(run: PFRun) -> str:
    """interlock's pre-edit hook reserves under the checkout's absolute path,
    so that is the default scope: the orchestrator and the hooks then contend
    in one key, not two (a directory-name scope never met the hook's rows)."""
    return run.reservation_scope or os.path.abspath(run.repo)


def _pf_owner(run_id: str, item_id: str) -> str:
    return f"pf/{run_id}/{item_id}"


def _pf_jget(obj, *names):
    if not isinstance(obj, dict):
        return None
    low = {str(k).lower(): v for k, v in obj.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def _pf_ic_json(run: PFRun, ic_bin: str, args: list[str]) -> tuple[int, object, str]:
    """ic [--db X] coordination <args> --json, run in the repo so ic resolves
    the same store interlock's hooks use there."""
    cmd = [ic_bin]
    cwd = run.repo
    if run.reservation_db:
        # ic refuses a --db outside its working directory, so run it from the
        # store's root (<root>/.clavain/intercore.db -> <root>).
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(run.reservation_db)))
        cmd += [f"--db={run.reservation_db}"]
    cmd += ["coordination", *args, "--json"]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    data: object = None
    try:
        data = json.loads((p.stdout or "").strip() or "null")
    except json.JSONDecodeError:
        data = None
    return p.returncode, data, ((p.stderr or "") + (p.stdout or "")).strip()[-300:]


def pf_release(run: PFRun, ic_bin: str, owner: str) -> int:
    rc, data, err = _pf_ic_json(run, ic_bin, ["release", f"--owner={owner}", f"--scope={_pf_scope(run)}"])
    if rc != 0:
        print(f"  [pf] {owner}: reservation release failed rc={rc}: {err}", file=sys.stderr, flush=True)
        return -1
    try:
        return int(_pf_jget(data, "released") or 0)
    except (TypeError, ValueError):
        return 0


def pf_reserve(
    run: PFRun, item: PFItem, files: list[str], run_id: str, ic_bin: str, res: PFItemResult,
) -> list[str] | None:
    """Reserve every declared path for the item, exclusively, through ic
    coordination (the store interlock's hooks reserve in). A conflict with any
    other owner releases the partial set and waits; None after the run's
    timeout. Nothing is reserved while the item waits."""
    scope = _pf_scope(run)
    owner = _pf_owner(run_id, item.id)
    ttl = run.timeout * 2 + 600
    poll = float(os.environ.get("ORC_PF_RESERVE_POLL", "2"))
    deadline = time.monotonic() + run.timeout
    last_blocker = None
    while True:
        ids: list[str] = []
        blocker = None
        for path in files:
            pattern = _pf_reservable(path)
            if pattern != path and last_blocker is None and not ids:
                print(f"  [pf] {item.id}: reserving {pattern} for {path} (path longer than {PF_MAX_PATTERN_TOKENS} tokens)", flush=True)
            # intercore's flag parser takes --flag=value, never --flag value.
            rc, data, err = _pf_ic_json(run, ic_bin, [
                "reserve", f"--owner={owner}", f"--scope={scope}", f"--pattern={pattern}",
                f"--ttl={ttl}", f"--reason=pattern-f {run_id} {item.id}", f"--run={run_id}",
            ])
            if rc == 0:
                ids.append(str(_pf_jget(_pf_jget(data, "lock"), "id") or ""))
            elif rc == 1:
                c = _pf_jget(data, "conflict") or {}
                who = _pf_jget(c, "blocker_owner", "blockerowner", "owner") or "unknown"
                what = _pf_jget(c, "blocker_pattern", "blockerpattern", "pattern") or pattern
                blocker = f"{who} on {what}"
                break
            else:
                # A partial set must not outlive the failure.
                pf_release(run, ic_bin, owner)
                raise RuntimeError(f"ic coordination reserve failed rc={rc}: {err}")
        if blocker is None:
            return ids
        pf_release(run, ic_bin, owner)
        res.blocked_by = blocker
        if blocker != last_blocker:
            print(f"  [pf] {item.id}: waiting, {blocker} is reserved", flush=True)
            last_blocker = blocker
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll)


def pf_gauge(plan: str, contract: str, repo: str, gauge_lint: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, gauge_lint, plan, "--contract", contract, "--repo-root", repo],
        capture_output=True, text=True, timeout=300,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def pf_register(
    run: PFRun, verdict_sh: str, res: PFItemResult, *,
    commit: str | None, role: str, kind: str, verdict: str,
    criterion: str | None = None, note: str | None = None,
) -> bool:
    """One register row through pattern-f-verdict.sh, --db explicit. The
    script's nonce read-back is the check; a failed write is retried once,
    then reported loudly. It never stops the run."""
    cmd = [
        "bash", verdict_sh, "--session", run.session, "--plan", res.plan,
        "--commit", commit or "none", "--role", role, "--kind", kind,
        "--verdict", verdict, "--db", run.register,
    ]
    if criterion:
        cmd += ["--criterion", criterion[:100]]
    tag = f"pf {res.run}/{res.id}" if res.run else f"pf {res.id}"
    cmd += ["--note", (f"{tag}: {note}" if note else tag)[:300]]
    if run.goal:
        cmd += ["--goal", run.goal]
    rc, detail = 1, ""
    for _attempt in range(2):
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        rc = p.returncode
        detail = ((p.stdout or "") + (p.stderr or "")).strip()
        if rc == 0:
            break
    if rc == 0:
        res.register_rows += 1
        print(f"  [pf] {res.id}: register {role} {kind} {verdict} commit={commit or 'none'}", flush=True)
        return True
    res.register_errors += 1
    print(
        f"  [pf] {res.id}: REGISTER WRITE FAILED rc={rc} ({role} {kind} {verdict}): {detail[-300:]}",
        file=sys.stderr, flush=True,
    )
    return False


def pf_worktree_add(
    run: PFRun, item: PFItem, run_dir: str, run_id: str, ic_bin: str | None,
) -> tuple[str, str]:
    wt = os.path.join(run_dir, "wt", item.id)
    branch = f"pf/{run_id}/{item.id}"
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    p = subprocess.run(
        ["git", "-C", run.repo, "worktree", "add", "-q", "-b", branch, wt, "HEAD"],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {(p.stderr or p.stdout).strip()[-300:]}")
    if not ic_bin:
        raise RuntimeError(
            "ic not found (set CLAVAIN_IC_BIN or put ic on PATH); dispatch.sh --role "
            "needs an Intercore store in the worktree"
        )
    p = subprocess.run([ic_bin, "init"], cwd=wt, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"ic init failed in {wt}: {(p.stderr or p.stdout).strip()[-300:]}")
    if not os.path.isdir(os.path.join(wt, ".clavain")):
        raise RuntimeError(f"ic init left no .clavain store in {wt}")
    return wt, branch


def pf_executor_prompt(item: PFItem, contract: str, wt: str, branch: str, item_dir: str) -> str:
    return (
        f"PATTERN-F EXECUTOR PLAN: {item.plan}\n"
        f"PATTERN-F EXECUTOR CONTRACT: {contract}\n"
        f"REPO: {wt}\n"
        f"You are the resolved {item.executor_role} executor. Read the {contract} contract at "
        f"{item.plan}. Stay within its scope, constraints, and authority. For a brief, own "
        "reconnaissance, implementation, and the test loop needed to satisfy its acceptance "
        "criteria. For exact, apply its prescribed mechanics verbatim. Never push or deploy "
        f"unless Authority explicitly permits it. Your working copy is {wt}, a dedicated git "
        f"worktree on branch {branch}: commit your finished work there, on that branch (a "
        f"commit message file may be written under {item_dir}); never push, and never touch "
        "any other checkout. Return only a bounded packet: diff or commit, checks run with "
        "outcomes, failures, and unresolved questions. End the packet with one line "
        "`VERDICT: PASS` when every acceptance criterion holds and every check you ran passed, "
        "otherwise `VERDICT: FAIL` followed by `CRITERION: <the criterion or check that failed>`.\n"
    )


def pf_validator_prompt(
    plan: str, contract: str, wt: str, ref: str, packet: str, receipt_path: str,
) -> str:
    return (
        "You are the resolved validation executor, and your resolved model must differ from "
        f"the producer. Read the contract at {plan} and the executor packet below. In {wt} at "
        f"{ref}, run its Verification (a brief) or every `### Verify` fence (an exact plan; its "
        "`## Preconditions` fence describes the tree before the apply and is not replayed) with "
        "the Bash tool, every command, from the repo root, and judge only against its frozen "
        "Acceptance Criteria (a brief) or its `Expected:` lines (an exact plan): output line 1 "
        "`VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: UNRUN` (UNRUN whenever any Verification command could not be executed: a denied tool call, a missing program, an unreadable path, or a runner that crashed or was denied before the test ran, such as a panic, exit 101 or a denied cache path; an environment failure is UNRUN, never FAIL; never guess the outcome of a command you did not run), line 2 `CRITERION: <the "
        "failing criterion, or for UNRUN the command that could not run, or none>`, line 3 "
        "`RECEIPT: <the verbatim output of the receipt command named below, or none>`. Then "
        "output `BEYOND THE GAUGE:` with bullets for real defects or risks the replay did not "
        "check (`- none` allowed). Never restate the contract; never fix anything; never edit a "
        f"file. Contract kind: {contract}. Receipt command: cat {receipt_path}. "
        f"Executor packet:\n{packet}\n"
    )


def _pf_commit(wt: str, message: str, msg_path: str) -> str | None:
    if not _git(wt, "status", "--porcelain").strip():
        return None
    _write_text(msg_path, message)
    subprocess.run(["git", "-C", wt, "add", "-A"], check=True, capture_output=True)
    p = subprocess.run(
        ["git", "-C", wt, "commit", "-q", "-F", msg_path], capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"git commit failed: {(p.stderr or p.stdout).strip()[-300:]}")
    return _git_head(wt)


def pf_execute_exact(
    run: PFRun, item: PFItem, wt: str, item_dir: str, gauge_lint: str,
) -> tuple[str | None, dict | None, str]:
    """Apply an exact plan with the tool and commit the result in the
    worktree. Returns (commit, apply receipt, detail); no model runs."""
    cmd = [
        sys.executable, gauge_lint, "--apply", item.plan, "--repo-root", wt,
        "--json", "--timeout", str(run.timeout),
    ]
    rc, timed_out, out, err = run_in_group(cmd, timeout=run.timeout + 60, cwd=wt)
    _write_text(os.path.join(item_dir, "apply.log"), out + ("\n--- stderr ---\n" + err if err else ""))
    receipt: dict | None = None
    try:
        receipt = json.loads(out) if out.strip() else None
    except json.JSONDecodeError:
        receipt = None
    if timed_out:
        return None, receipt, f"apply timed out after {run.timeout}s; process group killed"
    apply = (receipt or {}).get("apply") or {}
    if rc != 0 or not apply.get("ok"):
        failed = [s for s in apply.get("steps", []) if s.get("status") == "failed"]
        if failed:
            s = failed[0]
            detail = (
                f"apply: {s.get('kind')} {s.get('target') or s.get('heading') or ''} "
                f"(plan line {s.get('line')}): {s.get('detail')}"
            )
        else:
            detail = f"apply exited {rc}: {(err or out).strip()[-200:]}"
        return None, receipt, detail
    message = (
        f"pf({item.id}): {_pf_plan_title(item.plan)}\n\n"
        f"Applied by plan-gauge-lint.py --apply from {os.path.basename(item.plan)}; "
        "verify fences replayed by the tool.\n"
        + ("\n" + "\n".join(run.trailers) + "\n" if run.trailers else "")
    )
    try:
        commit = _pf_commit(wt, message, os.path.join(item_dir, "commit-message.txt"))
    except RuntimeError as e:
        return None, receipt, str(e)
    if commit is None:
        return None, receipt, "apply reported ok but the worktree is unchanged"
    return commit, receipt, "applied"


def pf_execute_brief(
    run: PFRun, item: PFItem, wt: str, branch: str, item_dir: str,
    dispatch_sh: str, meter: list[dict],
) -> PFExecution:
    prompt_path = os.path.join(item_dir, "executor.prompt.md")
    output = os.path.join(item_dir, "executor.md")
    _write_text(prompt_path, pf_executor_prompt(item, "brief", wt, branch, item_dir))
    base = _git_head(wt)
    cmd = [
        "bash", dispatch_sh, "--role", item.executor_role, "-C", wt,
        "--prompt-file", prompt_path, "-o", output, "-s", "workspace-write",
    ]
    resolved = _pf_resolve_model(cmd, wt)
    started = _pf_now()
    rc, timed_out, out, err = run_in_group(cmd, timeout=run.timeout, cwd=wt)
    finished = _pf_now()
    _write_text(
        os.path.join(item_dir, "executor.dispatch.log"),
        out + ("\n--- stderr ---\n" + err if err else ""),
    )
    model = resolved or _pf_model(err, item.producer or run.producer)
    meter.append({
        "item": item.id, "role": item.executor_role, "model": model,
        "started": started, "finished": finished, "rc": rc, "timed_out": timed_out,
        "output": output,
    })
    head = _git_head(wt)
    commit = head if head != base else None
    text = _pf_tail(output, 400)
    verdict_line = _pf_named_line(text, "VERDICT") or ""
    status = _read_verdict_status(output + ".verdict")
    note = None
    dirty = _git(wt, "status", "--porcelain").strip()
    if dirty:
        note = "worktree dirty after the executor: " + " ".join(dirty.split("\n")[:8])
    if timed_out:
        return PFExecution(commit, "FAIL", f"executor timed out after {run.timeout}s; process group killed", model, note)
    if commit is None:
        return PFExecution(None, "FAIL", "executor made no commit in its worktree", model, note)
    if verdict_line.upper().startswith("PASS") or (not verdict_line and status == "pass"):
        return PFExecution(commit, "PASS", None, model, note)
    criterion = _pf_named_line(text, "CRITERION") or f"executor verdict: {verdict_line or status or 'none'}"
    return PFExecution(commit, "FAIL", criterion, model, note)


def pf_validate(
    run: PFRun, item: PFItem, contract: str, wt: str, commit: str, packet: str,
    producer: str, item_dir: str, dispatch_sh: str, meter: list[dict],
) -> PFValidation:
    receipt_path = os.path.join(item_dir, "receipt")
    prompt_path = os.path.join(item_dir, "validator.prompt.md")
    output = os.path.join(item_dir, "validator.md")
    _write_text(prompt_path, pf_validator_prompt(item.plan, contract, wt, commit, packet, receipt_path))
    # The nonce is written only after the prompt is fixed on disk, so the
    # prompt cannot carry it: the seat has to run the receipt command.
    nonce = "receipt-" + secrets.token_hex(5)
    _write_text(receipt_path, nonce + "\n")
    cmd = [
        "bash", dispatch_sh, "--role", "validation", "--producer-identity", producer,
        "--plan", item.plan, "-C", wt, "--prompt-file", prompt_path, "-o", output,
    ]
    dry = _pf_dry_run_text(cmd, wt)
    resolved = _pf_resolve_model(cmd, wt, dry)
    if "codex exec" in dry:
        # A codex seat needs workspace-write to run tests at all; the tree
        # snapshot below turns any write it makes into an UNRUN.
        cmd += ["-s", "workspace-write"]
    snap_before = _pf_tree_snapshot(wt)
    started = _pf_now()
    rc, timed_out, out, err = run_in_group(cmd, timeout=run.timeout, cwd=wt)
    finished = _pf_now()
    snap_after = _pf_tree_snapshot(wt)
    _write_text(
        os.path.join(item_dir, "validator.dispatch.log"),
        out + ("\n--- stderr ---\n" + err if err else ""),
    )
    model = resolved or _pf_model(err, None)
    meter.append({
        "item": item.id, "role": "validation", "model": model,
        "started": started, "finished": finished, "rc": rc, "timed_out": timed_out,
        "output": output,
    })
    text = ""
    if os.path.exists(output):
        with open(output, errors="replace") as f:
            text = f.read()
    verdict_words = (_pf_named_line(text, "VERDICT") or "").split()
    v = verdict_words[0].upper() if verdict_words else ""
    crit = _pf_named_line(text, "CRITERION")
    rec = _pf_named_line(text, "RECEIPT")
    findings = _pf_beyond_the_gauge(text)
    status = _read_verdict_status(output + ".verdict")
    receipt_ok = rec == nonce
    if timed_out:
        return PFValidation("UNRUN", crit, f"validator timed out after {run.timeout}s; process group killed", receipt_ok, [], model)
    if snap_after != snap_before:
        changed = " ".join(l.strip() for l in snap_after.split("\n")[:-1] if l.strip())[:200]
        return PFValidation("UNRUN", crit, f"validator mutated the worktree: {changed or 'diff against HEAD changed'}", receipt_ok, [], model)
    if status == "error":
        return PFValidation("UNRUN", crit, _pf_sidecar_summary(output + ".verdict") or "dispatch reported an error verdict", receipt_ok, [], model)
    if v not in ("PASS", "FAIL", "UNRUN"):
        return PFValidation("UNRUN", crit, f"no VERDICT line from the seat (dispatch rc={rc}, sidecar {status or 'missing'})", receipt_ok, findings, model)
    if v == "FAIL":
        env = _pf_environment_failure(text)
        if env:
            return PFValidation("UNRUN", crit, f"environment failure, not a code failure: {env}", receipt_ok, findings, model)
    if v in ("PASS", "FAIL") and not receipt_ok:
        return PFValidation(
            "UNRUN", crit,
            f"receipt mismatch: wrote {nonce}, seat echoed {rec or 'none'}; nothing shows the block was run",
            False, findings, model,
        )
    return PFValidation(v, crit, (crit if v == "UNRUN" else None), receipt_ok, findings, model)


def pf_merge(run: PFRun, branch: str, wt: str) -> tuple[bool, str | None, str]:
    p = subprocess.run(
        ["git", "-C", run.repo, "merge", "--ff-only", "-q", branch],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        p = subprocess.run(
            ["git", "-C", run.repo, "merge", "--no-ff", "-q",
             "-m", f"Merge {branch} (orchestrate.py --pattern-f)", branch],
            capture_output=True, text=True,
        )
        if p.returncode != 0:
            conflicted = _git(run.repo, "diff", "--name-only", "--diff-filter=U").split()
            subprocess.run(["git", "-C", run.repo, "merge", "--abort"], capture_output=True)
            if conflicted:
                return False, None, "merge conflict: " + " ".join(conflicted)[:280]
            return False, None, f"merge failed: {(p.stderr or p.stdout).strip()[-300:]}"
    head = _git_head(run.repo)
    subprocess.run(["git", "-C", run.repo, "worktree", "remove", "--force", wt], capture_output=True)
    subprocess.run(["git", "-C", run.repo, "branch", "-D", branch], capture_output=True)
    return True, head, "merged"


def pf_run_item(
    run: PFRun, item: PFItem, run_dir: str, run_id: str,
    tools: dict[str, str | None], meter: list[dict],
    merge_lock: "threading.Lock | None" = None,
) -> PFItemResult:
    """One item end to end. Whatever happens inside, the item's reservations
    are released and its wait and run times recorded."""
    res = PFItemResult(id=item.id, plan=item.plan, run=run_id)
    res.started = _pf_now()
    t0 = time.monotonic()
    try:
        _pf_item_steps(run, item, run_dir, run_id, tools, meter, res, merge_lock)
    except Exception as e:  # noqa: BLE001 - the run must outlive one item
        res.status = "error"
        res.note = f"{type(e).__name__}: {e}"[:300]
        print(f"  [pf] {item.id}: {res.note}", file=sys.stderr, flush=True)
    finally:
        # Release by owner whatever happened: a partial set from a failed
        # reserve, or a full set from any later exit, never outlives the item.
        if res.gauge_rc == 0 and tools.get("ic"):
            pf_release(run, tools["ic"] or "", _pf_owner(run_id, item.id))
        res.finished = _pf_now()
        res.run_s = round(max(0.0, time.monotonic() - t0 - res.wait_s), 1)
    return res


def _pf_item_steps(
    run: PFRun, item: PFItem, run_dir: str, run_id: str,
    tools: dict[str, str | None], meter: list[dict], res: PFItemResult,
    merge_lock: "threading.Lock | None",
) -> None:
    item_dir = os.path.join(run_dir, item.id)
    os.makedirs(item_dir, exist_ok=True)
    contract = pf_contract(item.plan)
    res.contract = contract
    print(f"\n[pf] item {item.id}: {os.path.basename(item.plan)} ({contract or 'no contract'})", flush=True)
    if contract is None:
        res.status = "no_contract"
        res.note = "plan has no `Contract: brief|exact` line"
        return
    verdict_sh = tools["verdict"] or ""
    dispatch_sh = tools["dispatch"] or ""
    gauge_lint = tools["gauge"] or ""

    # 1. gauge: a finding is a verdict (gate row) and no executor exists yet.
    rc, report = pf_gauge(item.plan, contract, run.repo, gauge_lint)
    res.gauge_rc = rc
    _write_text(os.path.join(item_dir, "gauge.txt"), report)
    if rc != 0:
        codes = [l.strip() for l in report.splitlines() if _PF_GAUGE_CODE.search(l)]
        note = "; ".join(codes) if codes else report.strip()[-300:]
        pf_register(run, verdict_sh, res, commit=None, role="gate", kind="gate", verdict="FAIL", note=note)
        res.status = "gauge_failed"
        res.note = note[:300]
        print(f"  [pf] {item.id}: gauge rc={rc}; no executor spawned", flush=True)
        return
    print(f"  [pf] {item.id}: gauge clean", flush=True)

    # 2. reserve the declared paths, then a worktree with an Intercore store.
    files = _pf_declared_files(item)
    res.files = files
    if not tools.get("ic"):
        res.status = "worktree_failed"
        res.note = "ic not found (set CLAVAIN_IC_BIN or put ic on PATH); reservations and the worktree store need it"
        return
    w0 = time.monotonic()
    ids = pf_reserve(run, item, files, run_id, tools["ic"] or "", res)
    res.wait_s = round(time.monotonic() - w0, 1)
    if ids is None:
        res.status = "reservation_timeout"
        res.note = f"waited {res.wait_s:g}s for {res.blocked_by}; no worktree cut"
        print(f"  [pf] {item.id}: {res.note}", flush=True)
        return
    res.reservations = len(ids)
    print(f"  [pf] {item.id}: reserved {len(ids)} path(s) in scope {_pf_scope(run)} after {res.wait_s:g}s: {' '.join(files)}", flush=True)
    # The main checkout takes one git operation at a time: a worktree add
    # racing a sibling's merge fights over the same index lock.
    try:
        with (merge_lock or threading.Lock()):
            wt, branch = pf_worktree_add(run, item, run_dir, run_id, tools["ic"])
    except (RuntimeError, subprocess.SubprocessError) as e:
        res.status = "worktree_failed"
        res.note = str(e)[:300]
        print(f"  [pf] {item.id}: {res.note}", flush=True)
        return
    res.worktree, res.branch = wt, branch
    print(f"  [pf] {item.id}: worktree {wt} on {branch}", flush=True)

    # 3. execute: the tool for exact, a role-resolved model for a brief.
    if contract == "exact":
        commit, receipt, detail = pf_execute_exact(run, item, wt, item_dir, gauge_lint)
        res.executor_model = "plan-gauge-lint.py --apply"
        producer = item.producer or run.producer
        verdict = "PASS" if commit else "FAIL"
        criterion = None if commit else detail
        packet = (
            "Applied by: plan-gauge-lint.py --apply (receipt JSON follows)\n"
            + json.dumps(receipt)[:6000]
            + f"\nResult: {detail}\nCommit: {commit or 'none'}"
        )
        exec_note = "applied by plan-gauge-lint.py --apply; fences replayed by the tool"
    else:
        ex = pf_execute_brief(run, item, wt, branch, item_dir, dispatch_sh, meter)
        commit, verdict, criterion, producer = ex.commit, ex.verdict, ex.criterion, ex.model
        res.executor_model = ex.model
        if ex.note:
            res.note = ex.note
        packet = _pf_tail(os.path.join(item_dir, "executor.md"), 60)
        exec_note = None
    res.executor_commit, res.executor_verdict, res.executor_criterion = commit, verdict, criterion
    pf_register(
        run, verdict_sh, res, commit=commit, role="executor", kind="replay",
        verdict=verdict, criterion=criterion, note=exec_note,
    )
    print(
        f"  [pf] {item.id}: executor {verdict} commit={commit or 'none'}"
        + (f" ({criterion})" if criterion else ""), flush=True,
    )
    if verdict != "PASS" or not commit:
        res.status = "executor_failed"
        return

    # 4. validate through the seat, with the receipt nonce.
    if not producer:
        res.status = "no_producer_identity"
        res.note = "cannot dispatch the validation seat without a producer identity (set producer on the item or the run)"
        print(f"  [pf] {item.id}: {res.note}", flush=True)
        return
    val = pf_validate(run, item, contract, wt, commit, packet, producer, item_dir, dispatch_sh, meter)
    res.validator_model = val.model
    res.validator_verdict, res.validator_criterion, res.receipt_ok = val.verdict, val.criterion, val.receipt_ok
    if val.note and val.verdict != "PASS":
        res.note = val.note  # the packet says why a seat did not rule, not only the register
    pf_register(
        run, verdict_sh, res, commit=commit, role="validator", kind="replay",
        verdict=val.verdict, criterion=(val.criterion if val.verdict != "PASS" else None), note=val.note,
    )
    for finding in val.findings[:PF_MAX_INDEPENDENT_ROWS]:
        pf_register(
            run, verdict_sh, res, commit=commit, role="validator", kind="independent",
            verdict="FAIL", note=finding,
        )
    res.independent_findings = len(val.findings)
    res.beyond_gauge = list(val.findings)
    print(
        f"  [pf] {item.id}: validator {val.verdict}" + (f" ({val.note})" if val.note else "")
        + f"; {len(val.findings)} beyond-the-gauge finding(s)", flush=True,
    )
    if val.verdict != "PASS":
        res.status = f"validator_{val.verdict.lower()}"
        return

    # 5. merge back under the run's one lock on the main checkout, in
    # completion order; the worktree is removed only on success and a
    # conflict parks the item.
    with (merge_lock or threading.Lock()):
        ok, head, detail = pf_merge(run, branch, wt)
    res.merged, res.merge_commit = ok, head
    if ok:
        res.status, res.merge_outcome = "merged", "merged"
    elif detail.startswith("merge conflict"):
        res.status, res.merge_outcome = "merge_conflict", "conflict"
        res.note = detail
    else:
        res.status, res.merge_outcome = "merge_failed", "failed"
        res.note = detail
    print(f"  [pf] {item.id}: {detail}" + (f" -> {head}" if head else ""), flush=True)
    return


def _pf_item_packet(r: PFItemResult) -> dict:
    """asdict plus the key names pattern-f-contracts.md § Orchestrator report uses."""
    d = asdict(r)
    d.update({
        "pilot": r.id, "plan_path": r.plan, "lint_rc": r.gauge_rc,
        "executor_strikes": 1 if r.executor_verdict == "FAIL" else 0,
        "validator_strikes": 1 if r.validator_verdict == "FAIL" else 0,
        "register_rc": 0 if r.register_errors == 0 else 4,
        "notes": r.note or "",
    })
    return d


def _pf_readback(run: PFRun, verdict_sh: str) -> int | None:
    p = subprocess.run(
        ["bash", verdict_sh, "--list", "--session", run.session, "--db", run.register],
        capture_output=True, text=True, timeout=120,
    )
    if p.returncode != 0:
        print(
            f"  [pf] register read-back failed rc={p.returncode}: {(p.stderr or p.stdout).strip()[-200:]}",
            file=sys.stderr, flush=True,
        )
        return None
    return len([l for l in (p.stdout or "").splitlines() if l.strip()])


def orchestrate_pattern_f(run_path: str, dry_run: bool = False) -> list[PFItemResult]:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass
    run = load_pf_run(run_path)
    tools = _pf_tools()
    missing = [k for k in ("dispatch", "gauge", "verdict") if not tools[k] or not os.path.exists(tools[k] or "")]
    if dry_run:
        print(
            f"Pattern F dry run: {len(run.items)} item(s), repo {run.repo}, register {run.register}, "
            f"session {run.session}, timeout {run.timeout}s per dispatch, max_parallel {run.max_parallel}, "
            f"reservation scope {_pf_scope(run)}"
        )
        for item in run.items:
            c = pf_contract(item.plan) or "NO CONTRACT"
            how = "plan-gauge-lint.py --apply (no model)" if c == "exact" else f"dispatch.sh --role {item.executor_role}"
            print(
                f"  {item.id}: {c:<5} {os.path.basename(item.plan)} -> gauge, reserve, worktree + ic init, {how}, "
                "dispatch.sh --role validation --plan (receipt nonce), register rows, merge, release"
            )
            print(f"    files={' '.join(_pf_declared_files(item))}")
        print(f"  tools: {json.dumps(tools)}")
        if missing:
            print(f"  MISSING: {', '.join(missing)}")
        return []
    if missing:
        print(f"ERROR: tool(s) not found: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    run_id = uuid4().hex[:8]
    run_dir = os.path.join(run.repo, ".clavain", "orchestrate-runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    shutil.copyfile(run_path, os.path.join(run_dir, "run.yaml"))
    journal = os.path.join(run_dir, "journal.jsonl")
    meter: list[dict] = []
    started = _pf_now()
    print(f"Pattern F run {run_id}: {len(run.items)} item(s), repo {run.repo}, run dir {run_dir}", flush=True)
    _journal_append(journal, {"ts": started, "event": "run_started", "run": run_id, "session": run.session, "goal": run.goal})
    results: list[PFItemResult] = []
    merge_lock = threading.Lock()
    journal_lock = threading.Lock()
    wall0 = time.monotonic()

    def _one(item: PFItem) -> PFItemResult:
        res = pf_run_item(run, item, run_dir, run_id, tools, meter, merge_lock)
        with journal_lock:
            _journal_append(journal, {"ts": _pf_now(), "event": "item", **asdict(res)})
        return res

    order = {item.id: i for i, item in enumerate(run.items)}
    workers = max(1, min(run.max_parallel, len(run.items)))
    print(f"[pf] dispatching {len(run.items)} item(s), up to {workers} at once", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, item) for item in run.items]
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: order.get(r.id, 0))
    finished = _pf_now()
    wall_s = round(time.monotonic() - wall0, 1)
    meter_path = os.path.join(run_dir, "meter.json")
    with open(meter_path, "w") as f:
        json.dump({
            "run": run_id, "session": run.session, "goal": run.goal,
            "started": started, "finished": finished, "wall_s": wall_s,
            "max_parallel": run.max_parallel, "dispatches": meter,
            "items": [{
                "id": r.id, "status": r.status, "wait_s": r.wait_s, "run_s": r.run_s,
                "merge_outcome": r.merge_outcome, "files": r.files, "blocked_by": r.blocked_by,
            } for r in results],
        }, f, indent=2)
    readback = _pf_readback(run, tools["verdict"] or "")
    _journal_append(journal, {"ts": finished, "event": "run_finished", "run": run_id, "register_readback": readback})
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(
        f"\nPattern F run {run_id} finished in {wall_s:g}s (max_parallel {run.max_parallel}): "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        + f"; register rows read back for the session: {readback}", flush=True,
    )
    for r in results:
        print(f"  {r.id}: {r.status}; waited {r.wait_s:g}s, ran {r.run_s:g}s, merge {r.merge_outcome}", flush=True)
    packet = {
        "run": run_id, "goal": run.goal, "session": run.session, "register": run.register,
        "repo": run.repo, "started": started, "finished": finished, "run_dir": run_dir,
        "wall_s": wall_s, "max_parallel": run.max_parallel,
        "meter": meter_path, "register_readback": readback,
        "items": [_pf_item_packet(r) for r in results],
    }
    print(json.dumps(packet, separators=(",", ":")), flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DAG-based Codex agent dispatch orchestrator",
    )
    parser.add_argument("manifest", nargs="?", help="Path to .exec.yaml manifest (omit with --pattern-f)")
    parser.add_argument(
        "--pattern-f", metavar="RUN_YAML",
        help="Drive a Pattern F run from a run file (session, register, repo, items "
             "with plans): gauge, worktree + ic init, exact plans through "
             "plan-gauge-lint.py --apply, briefs through dispatch.sh --role, the "
             "validation seat with a receipt nonce, register rows, merge",
    )
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
    parser.add_argument(
        "--no-review", action="store_true",
        help="Skip the per-task review pipeline (verify blocks + independent "
             "reviewer + fix rounds); executor self-reports gate task status "
             "as before goal 7d610151",
    )
    parser.add_argument(
        "--resume", metavar="RUN_ID",
        help="Resume a prior run: tasks its journal records as complete "
             "(pass/warn) are skipped with dependency edges satisfied; "
             "everything else re-dispatches into the same run dir",
    )

    args = parser.parse_args()

    if args.pattern_f:
        orchestrate_pattern_f(args.pattern_f, dry_run=args.dry_run)
        return
    if not args.manifest:
        parser.error("manifest is required unless --pattern-f is given")

    if args.validate:
        errors = []
        try:
            manifest = load_manifest(args.manifest)
            graph = build_graph(manifest)
            errors = validate_graph(graph, manifest)
            plan_tasks = parse_plan_tasks(args.plan)
            for task in manifest.tasks.values():
                try:
                    _task_verification(task, plan_tasks.get(_task_plan_num(task.id)))
                except (TypeError, ValueError) as exc:
                    errors.append(f"{task.id}: UNVERIFIABLE: {exc}")
        except (TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"UNVERIFIABLE: {exc}")
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
        review_enabled=not args.no_review,
        resume_run_id=args.resume,
    )


if __name__ == "__main__":
    main()
