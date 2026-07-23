"""Installer surfaces that make interactive gateway adoption observable."""

from pathlib import Path


def test_kimi_installer_wires_and_diagnoses_context_gateway(project_root: Path) -> None:
    installer = (project_root / "scripts" / "install-kimi.sh").read_text()
    assert 'event = "UserPromptSubmit"' in installer
    assert "CLAVAIN_CONTEXT_GATEWAY_HARNESS=kimi" in installer
    assert "context-gateway.sh" in installer
    assert "context_gateway_hook_present" in installer
    assert "context_gateway_packet_schema" in installer


def test_codex_installer_wires_and_diagnoses_context_gateway(project_root: Path) -> None:
    installer = (project_root / "scripts" / "install-codex.sh").read_text()
    assert "UserPromptSubmit" in installer
    assert "context-gateway.sh" in installer
    assert "context_gateway_user_prompt_hook_present" in installer
    assert "context_gateway_packet_schema" in installer
