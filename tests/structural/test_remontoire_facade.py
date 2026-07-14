"""Contracts for the thin Remontoire operator facade."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_facade(
    project_root: Path,
    tmp_path: Path,
    *args: str,
    host: str = "local",
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_executable(
        bin_dir / "remontoire",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "REMONTOIRE_HOST": host,
        "REMONTOIRE_BINARY": str(bin_dir / "remontoire"),
    }
    return subprocess.run(
        ["bash", "scripts/remontoire-operator.sh", *args],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_facade_maps_read_and_cycle_flows(project_root: Path, tmp_path: Path) -> None:
    cases = {
        ("doctor",): ["doctor", "--json"],
        ("status",): ["status", "--json"],
        ("attention",): ["attention", "--json"],
        ("inspect", "cycle-1"): ["status", "cycle-1", "--json"],
        ("shadow",): ["cycle", "--mode=shadow", "--json"],
        ("proposal",): ["cycle", "--mode=proposal", "--json"],
        ("receipt", "show", "cycle-1"): ["receipt", "show", "cycle-1", "--json"],
        ("receipt", "replay", "cycle-1"): ["receipt", "replay", "cycle-1", "--json"],
    }

    for facade_args, expected in cases.items():
        result = _run_facade(project_root, tmp_path, *facade_args)
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == expected


def test_approve_is_forwarded_without_implicit_resume(
    project_root: Path, tmp_path: Path
) -> None:
    result = _run_facade(
        project_root,
        tmp_path,
        "approve",
        "cycle-1",
        "--actor=principal",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "approve",
        "cycle-1",
        "--actor=principal",
        "--json",
    ]
    assert "resume" not in result.stdout


def test_remote_facade_uses_batch_ssh_and_shell_quotes_arguments(
    project_root: Path, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "ssh",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "REMONTOIRE_HOST": "zklw",
        "REMONTOIRE_SSH_BINARY": str(bin_dir / "ssh"),
    }

    result = subprocess.run(
        [
            "bash",
            "scripts/remontoire-operator.sh",
            "decline",
            "cycle-1",
            "--actor=principal",
            "--reason=not enough evidence",
        ],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:5] == [
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "zklw",
    ]
    remote_command = lines[5]
    assert "remontoire" in remote_command
    assert "decline" in remote_command
    assert "not\\ enough\\ evidence" in remote_command
    assert remote_command.endswith("--json")


def test_facade_rejects_unknown_operations(project_root: Path, tmp_path: Path) -> None:
    result = _run_facade(project_root, tmp_path, "push")

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert result.stdout == ""


def test_remontoire_is_registered_and_discoverable(project_root: Path) -> None:
    manifest = (project_root / ".claude-plugin" / "plugin.json").read_text()
    help_text = (project_root / "commands" / "clavain-help.md").read_text()
    doctor_text = (project_root / "commands" / "clavain-doctor.md").read_text()
    status_text = (project_root / "commands" / "clavain-status.md").read_text()

    assert '"./skills/remontoire"' in manifest
    assert '"./commands/remontoire.md"' in manifest
    assert "/clavain:remontoire" in help_text
    assert "remontoire-operator.sh" in doctor_text
    assert "remontoire-operator.sh" in status_text


def test_operator_skill_keeps_principal_boundaries_explicit(project_root: Path) -> None:
    skill = (project_root / "skills" / "remontoire" / "SKILL.md").read_text()

    assert "Approval and execution are separate" in skill
    assert "Never infer approval" in skill
    assert "push, merge, deploy, or publish" in skill
    for operation in (
        "status",
        "shadow",
        "proposal",
        "inspect",
        "approve",
        "decline",
        "resume",
        "receipt",
    ):
        assert operation in skill
