"""Tests for flux-drive diff slicing configuration and integration."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def diff_routing_path(project_root: Path) -> Path:
    return project_root / "config" / "flux-drive" / "diff-routing.md"


@pytest.fixture(scope="session")
def flux_drive_skill(project_root: Path) -> str:
    return (project_root / "skills" / "flux-drive" / "SKILL.md").read_text()


@pytest.fixture(scope="session")
def launch_phase(project_root: Path) -> str:
    return (project_root / "skills" / "flux-drive" / "phases" / "launch.md").read_text()


@pytest.fixture(scope="session")
def shared_contracts(project_root: Path) -> str:
    return (project_root / "skills" / "flux-drive" / "phases" / "shared-contracts.md").read_text()


@pytest.fixture(scope="session")
def synthesize_phase(project_root: Path) -> str:
    return (project_root / "skills" / "flux-drive" / "phases" / "synthesize.md").read_text()


def test_diff_routing_exists(diff_routing_path: Path):
    """diff-routing.md exists in config/flux-drive/."""
    assert diff_routing_path.exists(), "config/flux-drive/diff-routing.md is missing"


def test_diff_routing_covers_all_agents(diff_routing_path: Path):
    """diff-routing.md mentions all 6 fd-* agents."""
    content = diff_routing_path.read_text()
    agents = [
        "fd-architecture",
        "fd-safety",
        "fd-correctness",
        "fd-performance",
        "fd-user-product",
        "fd-quality",
    ]
    for agent in agents:
        assert agent in content, (
            f"diff-routing.md does not mention {agent}"
        )


def test_diff_routing_has_cross_cutting_section(diff_routing_path: Path):
    """diff-routing.md defines cross-cutting agents."""
    content = diff_routing_path.read_text()
    assert "Cross-Cutting Agents" in content


def test_diff_routing_has_domain_specific_sections(diff_routing_path: Path):
    """diff-routing.md has sections for domain-specific agents."""
    content = diff_routing_path.read_text()
    assert "Domain-Specific Agents" in content
    for agent in ["fd-safety", "fd-correctness", "fd-performance", "fd-user-product"]:
        assert f"### {agent}" in content, (
            f"diff-routing.md missing section for {agent}"
        )


def test_diff_routing_has_priority_patterns(diff_routing_path: Path):
    """Each domain agent section has priority file patterns and keywords."""
    content = diff_routing_path.read_text()
    assert "Priority file patterns" in content
    assert "Priority hunk keywords" in content


def test_skill_mentions_input_type_diff(flux_drive_skill: str):
    """SKILL.md defines INPUT_TYPE = diff."""
    assert "INPUT_TYPE = diff" in flux_drive_skill


def test_skill_has_diff_profile(flux_drive_skill: str):
    """SKILL.md contains a Diff Profile section."""
    assert "Diff Profile" in flux_drive_skill
    assert "slicing_eligible" in flux_drive_skill


def test_skill_detects_diff_content(flux_drive_skill: str):
    """SKILL.md detects diff inputs by content signature."""
    assert "diff --git" in flux_drive_skill
    assert "--- a/" in flux_drive_skill


def test_launch_mentions_diff_slicing(launch_phase: str):
    """launch.md references diff slicing."""
    assert "diff slicing" in launch_phase.lower() or "Diff Slicing" in launch_phase
    assert "Step 2.1b" in launch_phase


def test_launch_has_diff_to_review_section(launch_phase: str):
    """launch.md has a Diff to Review prompt template section."""
    assert "## Diff to Review" in launch_phase


def test_launch_has_priority_context_slicing(launch_phase: str):
    """launch.md has priority/context slicing for both diff and document inputs."""
    assert "priority hunks" in launch_phase or "priority sections" in launch_phase
    assert "context" in launch_phase.lower()


def test_shared_contracts_has_slicing_contract(shared_contracts: str):
    """shared-contracts.md has a Diff Slicing Contract section."""
    assert "## Diff Slicing Contract" in shared_contracts


def test_shared_contracts_defines_agent_access(shared_contracts: str):
    """shared-contracts.md defines which agents get full vs sliced content."""
    assert "Agent Content Access" in shared_contracts
    assert "slicing_map" in shared_contracts


def test_shared_contracts_synthesis_implications(shared_contracts: str):
    """shared-contracts.md documents synthesis implications of slicing."""
    assert "Convergence adjustment" in shared_contracts
    assert "discovered beyond sliced scope" in shared_contracts
    assert "No penalty for silence" in shared_contracts


def test_synthesize_has_slicing_awareness(synthesize_phase: str):
    """synthesize.md has diff slicing awareness in dedup rules."""
    assert "Diff slicing awareness" in synthesize_phase
    assert "slicing_map" in synthesize_phase


def test_synthesize_has_slicing_report(synthesize_phase: str):
    """synthesize.md has a Diff Slicing Report section in the report template."""
    assert "### Diff Slicing Report" in synthesize_phase
    assert "Routing improvements" in synthesize_phase
