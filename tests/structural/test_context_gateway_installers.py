"""Installer surfaces that make interactive gateway adoption observable."""

import json
from pathlib import Path


def test_kimi_manifest_tracks_claude_release_version(project_root: Path) -> None:
    claude = json.loads(
        (project_root / ".claude-plugin" / "plugin.json").read_text()
    )
    kimi = json.loads((project_root / "kimi.plugin.json").read_text())

    assert kimi["version"] == claude["version"]


def test_post_bump_keeps_kimi_release_metadata_in_sync(project_root: Path) -> None:
    post_bump = (project_root / "scripts" / "post-bump.sh").read_text()

    assert "kimi.plugin.json" in post_bump
    assert "TARGET_VERSION" in post_bump


def test_kimi_installer_wires_and_diagnoses_context_gateway(project_root: Path) -> None:
    installer = (project_root / "scripts" / "install-kimi.sh").read_text()
    assert "--plugin clavain" in installer
    assert 'git -C "$SOURCE_DIR" archive HEAD' in installer
    assert "managed_plugin_current" in installer
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
