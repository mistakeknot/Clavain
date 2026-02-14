"""Tests for work discovery feature (M1 F1+F2)."""

from pathlib import Path


def test_lib_discovery_exists(project_root):
    """hooks/lib-discovery.sh exists."""
    lib = project_root / "hooks" / "lib-discovery.sh"
    assert lib.exists(), "hooks/lib-discovery.sh is missing"


def test_lib_discovery_has_required_functions(project_root):
    """lib-discovery.sh defines the required scanner functions."""
    lib = project_root / "hooks" / "lib-discovery.sh"
    text = lib.read_text(encoding="utf-8")
    for func in ("discovery_scan_beads", "infer_bead_action", "discovery_log_selection"):
        assert f"{func}()" in text, (
            f"lib-discovery.sh is missing function: {func}"
        )


def test_lib_discovery_has_sentinels(project_root):
    """lib-discovery.sh (or delegated interphase) defines DISCOVERY_UNAVAILABLE sentinel."""
    lib = project_root / "hooks" / "lib-discovery.sh"
    text = lib.read_text(encoding="utf-8")
    # The shim provides DISCOVERY_UNAVAILABLE as a no-op stub.
    # DISCOVERY_ERROR is only emitted by the full implementation in interphase.
    assert "DISCOVERY_UNAVAILABLE" in text, "Missing DISCOVERY_UNAVAILABLE sentinel"


def test_sprint_has_discovery_section(project_root):
    """commands/sprint.md has the Before Starting discovery section."""
    sprint = project_root / "commands" / "sprint.md"
    text = sprint.read_text(encoding="utf-8")
    assert "Before Starting" in text, "sprint.md missing 'Before Starting' discovery section"
    assert "discovery_scan_beads" in text, "sprint.md missing discovery_scan_beads invocation"
    assert "DISCOVERY_UNAVAILABLE" in text, "sprint.md missing DISCOVERY_UNAVAILABLE handling"
