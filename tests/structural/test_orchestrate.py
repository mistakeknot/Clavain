"""Tests for orchestrate.py — DAG-based Codex agent dispatch."""

import os
import tempfile

import pytest

from orchestrate import (
    DependencyDrivenScheduler,
    Manifest,
    Task,
    TaskResult,
    build_graph,
    build_prompt,
    load_manifest,
    summarize_output,
    validate_graph,
    _resolve_all_parallel,
    _resolve_all_sequential,
    _resolve_manual_batching,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_manifest(stages: list[dict], mode: str = "dependency-driven") -> Manifest:
    """Helper to build a Manifest from raw stage dicts."""
    tasks: dict[str, Task] = {}
    for stage in stages:
        for t in stage.get("tasks", []):
            tasks[t["id"]] = Task(
                id=t["id"],
                title=t.get("title", t["id"]),
                stage=stage["name"],
                files=t.get("files", []),
                depends=t.get("depends", []),
                tier=t.get("tier"),
            )
    return Manifest(
        version=1,
        mode=mode,
        tier="deep",
        max_parallel=5,
        timeout_per_task=300,
        stages=stages,
        tasks=tasks,
    )


SIMPLE_LINEAR = [
    {"name": "S1", "tasks": [{"id": "task-1", "title": "A"}]},
    {"name": "S2", "tasks": [{"id": "task-2", "title": "B"}]},
    {"name": "S3", "tasks": [{"id": "task-3", "title": "C"}]},
]

FAN_OUT = [
    {"name": "S1", "tasks": [{"id": "task-1", "title": "root"}]},
    {
        "name": "S2",
        "tasks": [
            {"id": "task-2", "title": "branch-a"},
            {"id": "task-3", "title": "branch-b"},
        ],
    },
]

FAN_IN = [
    {
        "name": "S1",
        "tasks": [
            {"id": "task-1", "title": "A"},
            {"id": "task-2", "title": "B"},
        ],
    },
    {
        "name": "S2",
        "tasks": [
            {"id": "task-3", "title": "join", "depends": ["task-1", "task-2"]},
        ],
    },
]

DIAMOND = [
    {"name": "S1", "tasks": [{"id": "task-1", "title": "root"}]},
    {
        "name": "S2",
        "tasks": [
            {"id": "task-2", "title": "left"},
            {"id": "task-3", "title": "right"},
        ],
    },
    {
        "name": "S3",
        "tasks": [
            {"id": "task-4", "title": "join", "depends": ["task-2", "task-3"]},
        ],
    },
]

INTRA_STAGE_DEPS = [
    {
        "name": "S1",
        "tasks": [
            {"id": "task-1", "title": "setup"},
            {"id": "task-2", "title": "build", "depends": ["task-1"]},
            {"id": "task-3", "title": "test", "depends": ["task-2"]},
        ],
    },
]


# ---------------------------------------------------------------------------
# TestBuildGraph
# ---------------------------------------------------------------------------


class TestBuildGraph:
    def test_simple_linear(self):
        m = _make_manifest(SIMPLE_LINEAR)
        g = build_graph(m)
        assert g["task-1"] == set()
        assert g["task-2"] == {"task-1"}
        assert g["task-3"] == {"task-1", "task-2"}

    def test_fan_out(self):
        m = _make_manifest(FAN_OUT)
        g = build_graph(m)
        assert g["task-1"] == set()
        assert g["task-2"] == {"task-1"}
        assert g["task-3"] == {"task-1"}

    def test_fan_in(self):
        m = _make_manifest(FAN_IN)
        g = build_graph(m)
        # task-3 is in S2, so stage barrier adds task-1 + task-2
        # explicit depends also lists task-1 + task-2 (additive, same result)
        assert g["task-3"] == {"task-1", "task-2"}

    def test_diamond(self):
        m = _make_manifest(DIAMOND)
        g = build_graph(m)
        assert g["task-1"] == set()
        assert g["task-2"] == {"task-1"}
        assert g["task-3"] == {"task-1"}
        # task-4 in S3: stage barrier adds task-1, task-2, task-3
        # explicit deps add task-2, task-3 (already there)
        assert g["task-4"] == {"task-1", "task-2", "task-3"}

    def test_cross_stage_implicit(self):
        """Stage barrier is additive — all prior stage tasks are deps."""
        stages = [
            {"name": "S1", "tasks": [
                {"id": "task-1", "title": "A"},
                {"id": "task-2", "title": "B"},
            ]},
            {"name": "S2", "tasks": [
                {"id": "task-3", "title": "C"},  # no explicit depends
            ]},
        ]
        m = _make_manifest(stages)
        g = build_graph(m)
        # task-3 should depend on BOTH task-1 and task-2 via stage barrier
        assert g["task-3"] == {"task-1", "task-2"}

    def test_intra_stage_deps(self):
        """Explicit intra-stage deps work within the same stage."""
        m = _make_manifest(INTRA_STAGE_DEPS)
        g = build_graph(m)
        assert g["task-1"] == set()
        assert g["task-2"] == {"task-1"}
        assert g["task-3"] == {"task-2"}

    def test_stage_barrier_additive_with_explicit_deps(self):
        """Explicit cross-stage depends do NOT remove stage barrier."""
        stages = [
            {"name": "S1", "tasks": [
                {"id": "task-1", "title": "A"},
                {"id": "task-2", "title": "B"},
            ]},
            {"name": "S2", "tasks": [
                # Explicit dep on task-1 only, but stage barrier should add task-2 too
                {"id": "task-3", "title": "C", "depends": ["task-1"]},
            ]},
        ]
        m = _make_manifest(stages)
        g = build_graph(m)
        assert g["task-3"] == {"task-1", "task-2"}


# ---------------------------------------------------------------------------
# TestValidateGraph
# ---------------------------------------------------------------------------


class TestValidateGraph:
    def test_valid_graph(self):
        m = _make_manifest(DIAMOND)
        g = build_graph(m)
        errors = validate_graph(g, m)
        assert errors == []

    def test_cycle_detected(self):
        # Create a manual cycle: task-1 → task-2 → task-1
        graph = {"task-1": {"task-2"}, "task-2": {"task-1"}}
        m = _make_manifest([{"name": "S1", "tasks": [
            {"id": "task-1", "title": "A"},
            {"id": "task-2", "title": "B"},
        ]}])
        errors = validate_graph(graph, m)
        assert any("ycle" in e for e in errors)

    def test_missing_dependency(self):
        graph = {"task-1": {"task-99"}}
        m = _make_manifest([{"name": "S1", "tasks": [
            {"id": "task-1", "title": "A"},
        ]}])
        errors = validate_graph(graph, m)
        assert any("task-99" in e for e in errors)

    def test_self_dependency(self):
        graph = {"task-1": {"task-1"}}
        m = _make_manifest([{"name": "S1", "tasks": [
            {"id": "task-1", "title": "A"},
        ]}])
        errors = validate_graph(graph, m)
        assert any("itself" in e for e in errors)


# ---------------------------------------------------------------------------
# TestResolveExecutionOrder
# ---------------------------------------------------------------------------


class TestResolveExecutionOrder:
    def test_all_parallel_ignores_deps(self):
        m = _make_manifest(DIAMOND)
        g = build_graph(m)
        batches = _resolve_all_parallel(g)
        assert len(batches) == 1
        assert set(batches[0]) == {"task-1", "task-2", "task-3", "task-4"}

    def test_all_sequential_one_per_batch(self):
        m = _make_manifest(DIAMOND)
        g = build_graph(m)
        batches = _resolve_all_sequential(g)
        assert len(batches) == 4
        # Each batch has exactly one task
        for b in batches:
            assert len(b) == 1
        # task-1 must come before task-2 and task-3
        order = [b[0] for b in batches]
        assert order.index("task-1") < order.index("task-2")
        assert order.index("task-1") < order.index("task-3")
        assert order.index("task-2") < order.index("task-4")
        assert order.index("task-3") < order.index("task-4")

    def test_dependency_driven_max_parallelism(self):
        m = _make_manifest(DIAMOND)
        g = build_graph(m)
        scheduler = DependencyDrivenScheduler(g)
        # Wave 1: only task-1 is ready
        ready1 = scheduler.get_ready()
        assert set(ready1) == {"task-1"}
        scheduler.mark_done("task-1")
        # Wave 2: task-2 and task-3 ready in parallel
        ready2 = scheduler.get_ready()
        assert set(ready2) == {"task-2", "task-3"}
        scheduler.mark_done("task-2")
        scheduler.mark_done("task-3")
        # Wave 3: task-4 ready
        ready3 = scheduler.get_ready()
        assert set(ready3) == {"task-4"}
        scheduler.mark_done("task-4")
        assert not scheduler.is_active

    def test_manual_batching_groups_by_stage(self):
        m = _make_manifest(FAN_OUT, mode="manual-batching")
        g = build_graph(m)
        batches = _resolve_manual_batching(g, m)
        # S1: [task-1], S2: [task-2, task-3]
        assert len(batches) == 2
        assert batches[0] == ["task-1"]
        assert set(batches[1]) == {"task-2", "task-3"}

    def test_manual_batching_respects_intra_stage_deps(self):
        """Intra-stage deps produce sub-waves within a stage."""
        m = _make_manifest(INTRA_STAGE_DEPS, mode="manual-batching")
        g = build_graph(m)
        batches = _resolve_manual_batching(g, m)
        # Should be 3 sub-waves: [task-1], [task-2], [task-3]
        assert len(batches) == 3
        assert batches[0] == ["task-1"]
        assert batches[1] == ["task-2"]
        assert batches[2] == ["task-3"]


# ---------------------------------------------------------------------------
# TestDependencyDrivenScheduler (failure propagation)
# ---------------------------------------------------------------------------


class TestDependencyDrivenScheduler:
    def test_failure_skips_dependents(self):
        m = _make_manifest(SIMPLE_LINEAR)
        g = build_graph(m)
        scheduler = DependencyDrivenScheduler(g)
        ready = scheduler.get_ready()
        assert "task-1" in ready
        # task-1 fails → task-2 and task-3 should be skipped
        skipped = scheduler.mark_failed("task-1")
        assert "task-2" in skipped
        assert "task-3" in skipped

    def test_failure_partial_skip(self):
        """Only dependents of the failed task are skipped."""
        m = _make_manifest(FAN_OUT)
        g = build_graph(m)
        scheduler = DependencyDrivenScheduler(g)
        ready = scheduler.get_ready()
        assert "task-1" in ready
        scheduler.mark_done("task-1")
        ready2 = scheduler.get_ready()
        assert set(ready2) == {"task-2", "task-3"}
        # task-2 fails but task-3 succeeds
        skipped = scheduler.mark_failed("task-2")
        # No further dependents of task-2
        assert skipped == []
        scheduler.mark_done("task-3")
        assert not scheduler.is_active

    def test_diamond_failure_propagation(self):
        m = _make_manifest(DIAMOND)
        g = build_graph(m)
        scheduler = DependencyDrivenScheduler(g)
        scheduler.get_ready()  # [task-1]
        scheduler.mark_done("task-1")
        scheduler.get_ready()  # [task-2, task-3]
        # task-2 fails → task-4 (depends on task-2) should be skipped
        skipped = scheduler.mark_failed("task-2")
        assert "task-4" in skipped
        scheduler.mark_done("task-3")
        # task-4 was skipped, so scheduler should complete
        ready = scheduler.get_ready()
        assert ready == []  # task-4 was already marked done (skipped)


# ---------------------------------------------------------------------------
# TestOutputRouting
# ---------------------------------------------------------------------------


class TestOutputRouting:
    def test_summarize_with_verdict(self, tmp_path):
        verdict = tmp_path / "output.md.verdict"
        verdict.write_text("STATUS: pass\nFILES_CHANGED: a.go, b.go\nSUMMARY: All good\n")
        output = tmp_path / "output.md"
        output.write_text("Full output content here\nLine 2\n")

        result = summarize_output(str(output), str(verdict))
        assert "STATUS: pass" in result
        assert "Full output content" in result

    def test_summarize_without_verdict(self, tmp_path):
        output = tmp_path / "output.md"
        output.write_text("Output only\n")

        result = summarize_output(str(output), "/nonexistent.verdict")
        assert "Output only" in result

    def test_summarize_missing_both(self):
        result = summarize_output("/nonexistent", "/nonexistent.verdict")
        assert result == "(no output)"

    def test_summarize_truncates_long_output(self, tmp_path):
        output = tmp_path / "output.md"
        lines = [f"Line {i}\n" for i in range(100)]
        output.write_text("".join(lines))

        result = summarize_output(str(output), None, max_lines=10)
        assert "truncated" in result

    def test_prompt_enrichment(self):
        task = Task(id="task-3", title="Integration", stage="S2", files=["test.go"])
        dep_results = {
            "task-1": TaskResult(task_id="task-1", status="pass"),
            "task-2": TaskResult(task_id="task-2", status="pass"),
        }
        all_tasks = {
            "task-1": Task(id="task-1", title="API", stage="S1"),
            "task-2": Task(id="task-2", title="CLI", stage="S1"),
            "task-3": task,
        }

        prompt = build_prompt(task, "plan.md", dep_results, all_tasks)
        assert "Context from dependencies" in prompt
        assert "task-1: API" in prompt
        assert "task-2: CLI" in prompt
        assert "Integration" in prompt
        assert "test.go" in prompt
        assert "VERDICT:" in prompt


# ---------------------------------------------------------------------------
# TestLoadManifest (integration with YAML file)
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_load_example_manifest(self):
        example = os.path.join(
            os.path.dirname(__file__), "..", "..", "schemas", "exec-manifest.example.yaml"
        )
        if not os.path.exists(example):
            pytest.skip("Example manifest not found")
        m = load_manifest(example)
        assert m.version == 1
        assert m.mode == "dependency-driven"
        assert len(m.tasks) == 4
        assert "task-1" in m.tasks
        assert "task-4" in m.tasks
        assert m.tasks["task-4"].tier == "fast"

    def test_duplicate_task_id(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(
            "version: 1\nmode: all-parallel\nstages:\n"
            "  - name: S1\n    tasks:\n"
            "      - id: task-1\n        title: A\n"
            "      - id: task-1\n        title: B\n"
        )
        with pytest.raises(SystemExit):
            load_manifest(str(f))
