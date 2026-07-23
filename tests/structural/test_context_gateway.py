"""Behavioral contract tests for the cross-harness tldrs context gateway."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


GATEWAY = Path(__file__).resolve().parents[2] / "scripts" / "context-gateway.py"
PACKET = "# Agent context packet\n## scripts/dispatch.sh\n```bash\nmain() { :; }\n```"


def _write_tldrs_stub(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "tldrs"
    stub.write_text(
        """#!/usr/bin/env python3
import hashlib
import json
import os
import sys

if "--version" in sys.argv:
    print("tldr-swinton 0.8.3")
    raise SystemExit(0)

log_path = os.environ.get("TLDRS_STUB_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\\n")

mode = os.environ.get("TLDRS_STUB_MODE", "inject")
packet = os.environ["TLDRS_STUB_PACKET"]
if mode == "malformed":
    print("{")
    raise SystemExit(0)
if mode == "error":
    raise SystemExit(17)

decision = "fallback" if mode == "fallback" else "inject"
reason = "low_confidence" if mode == "fallback" else "explicit_path"
confidence = 0.2 if mode == "fallback" else 1.0
digest = hashlib.sha256(packet.encode()).hexdigest() if decision == "inject" else None
print(json.dumps({
    "success": True,
    "result": {
        "schema_version": 1,
        "decision": decision,
        "reason": reason,
        "confidence": confidence,
        "packet": packet if decision == "inject" else "",
        "receipt": {
            "schema_version": 1,
            "decision": decision,
            "reason": reason,
            "confidence": confidence,
            "min_confidence": 0.6,
            "harness_profile": "codex",
            "packet_sha256": digest,
            "packet_chars": len(packet) if decision == "inject" else 0,
            "candidate_paths": ["scripts/dispatch.sh"],
        },
    },
}))
"""
    )
    stub.chmod(0o755)
    return bin_dir


@pytest.fixture
def gateway_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    bin_dir = _write_tldrs_stub(tmp_path)
    receipt_dir = tmp_path / "receipts"
    log_path = tmp_path / "tldrs.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "CLAVAIN_CONTEXT_GATEWAY_RECEIPT_DIR": str(receipt_dir),
            "TLDRS_STUB_LOG": str(log_path),
            "TLDRS_STUB_PACKET": PACKET,
        }
    )
    return env, receipt_dir, log_path


def _run(
    args: list[str],
    *,
    prompt: str = "",
    env: dict[str, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATEWAY), *args],
        input=prompt,
        text=True,
        capture_output=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _one_receipt(receipt_dir: Path) -> dict:
    paths = list(receipt_dir.glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_prepare_injects_validated_packet_and_private_receipt(
    tmp_path: Path, gateway_env: tuple[dict[str, str], Path, Path]
) -> None:
    env, receipt_dir, log_path = gateway_env
    project = tmp_path / "project"
    target = project / "scripts" / "dispatch.sh"
    target.parent.mkdir(parents=True)
    target.write_text("\n".join(["main() { :; }"] * 220))
    prompt = "Fix scripts/dispatch.sh so dispatch applies context before Codex."

    result = _run(
        ["prepare", "--project", str(project), "--harness", "codex"],
        prompt=prompt,
        env=env,
        cwd=project,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith(prompt)
    assert PACKET in result.stdout
    assert result.stdout.count("clavain-context-gateway:v1") == 1
    assert "--harness-profile" in log_path.read_text()
    receipt = _one_receipt(receipt_dir)
    assert receipt["decision"] == "inject"
    assert receipt["packet_sha256"] == hashlib.sha256(PACKET.encode()).hexdigest()
    serialized = json.dumps(receipt)
    assert prompt not in serialized
    assert PACKET not in serialized


@pytest.mark.parametrize(
    ("prompt", "reason"),
    [
        ("Summarize the architecture for me.", "non_code_task"),
        ("Improve the prose in README.md.", "docs_or_config"),
        ("<!-- clavain-context-gateway:v1 -->\nFix the bug.", "already_injected"),
    ],
)
def test_prepare_bypasses_ineligible_tasks_without_calling_tldrs(
    tmp_path: Path,
    gateway_env: tuple[dict[str, str], Path, Path],
    prompt: str,
    reason: str,
) -> None:
    env, receipt_dir, log_path = gateway_env

    result = _run(
        ["prepare", "--project", str(tmp_path), "--harness", "generic"],
        prompt=prompt,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == prompt
    assert not log_path.exists()
    receipt = _one_receipt(receipt_dir)
    assert receipt["decision"] == "bypass"
    assert receipt["reason"] == reason


def test_prepare_bypasses_one_known_small_target(
    tmp_path: Path, gateway_env: tuple[dict[str, str], Path, Path]
) -> None:
    env, receipt_dir, log_path = gateway_env
    target = tmp_path / "small.py"
    target.write_text("def answer():\n    return 42\n")
    prompt = "Fix small.py."

    result = _run(
        ["prepare", "--project", str(tmp_path), "--harness", "codex"],
        prompt=prompt,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == prompt
    assert not log_path.exists()
    assert _one_receipt(receipt_dir)["reason"] == "known_small_target"


def test_prepare_bypasses_a_small_explicit_target_set(
    tmp_path: Path, gateway_env: tuple[dict[str, str], Path, Path]
) -> None:
    env, receipt_dir, log_path = gateway_env
    hook = tmp_path / "hooks" / "context-gateway.sh"
    test = tmp_path / "tests" / "context_gateway_hook.bats"
    hook.parent.mkdir()
    test.parent.mkdir()
    hook.write_text("#!/bin/sh\nexec gateway hook\n")
    test.write_text('@test "hook fails open" { run hook; }\n')
    prompt = (
        "Fix hooks/context-gateway.sh and update "
        "tests/context_gateway_hook.bats so failures remain fail-open."
    )

    result = _run(
        ["prepare", "--project", str(tmp_path), "--harness", "kimi"],
        prompt=prompt,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == prompt
    assert not log_path.exists()
    assert _one_receipt(receipt_dir)["reason"] == "known_small_target_set"


@pytest.mark.parametrize("stub_mode", ["error", "malformed", "fallback"])
def test_auto_mode_preserves_prompt_on_tldrs_fallback(
    tmp_path: Path,
    gateway_env: tuple[dict[str, str], Path, Path],
    stub_mode: str,
) -> None:
    env, receipt_dir, _ = gateway_env
    env["TLDRS_STUB_MODE"] = stub_mode
    prompt = "Refactor the authentication implementation and update its tests."

    result = _run(
        ["prepare", "--project", str(tmp_path), "--harness", "claude"],
        prompt=prompt,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == prompt
    assert _one_receipt(receipt_dir)["decision"] == "fallback"


def test_required_mode_fails_when_packet_cannot_be_injected(
    tmp_path: Path, gateway_env: tuple[dict[str, str], Path, Path]
) -> None:
    env, receipt_dir, _ = gateway_env
    env["TLDRS_STUB_MODE"] = "error"
    prompt = "Refactor the authentication implementation and update its tests."

    result = _run(
        [
            "prepare",
            "--project",
            str(tmp_path),
            "--harness",
            "codex",
            "--mode",
            "required",
        ],
        prompt=prompt,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert result.stdout == prompt
    assert _one_receipt(receipt_dir)["decision"] == "fallback"


def test_hook_adapts_additional_context_for_codex_and_plain_text_for_kimi(
    tmp_path: Path, gateway_env: tuple[dict[str, str], Path, Path]
) -> None:
    env, _, _ = gateway_env
    prompt = "Refactor the authentication implementation and update its tests."
    event = json.dumps({"prompt": prompt, "cwd": str(tmp_path)})

    codex = _run(["hook", "--harness", "codex"], prompt=event, env=env, cwd=tmp_path)
    assert codex.returncode == 0, codex.stderr
    output = json.loads(codex.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert output["hookSpecificOutput"]["additionalContext"] == PACKET

    receipt_dir = Path(env["CLAVAIN_CONTEXT_GATEWAY_RECEIPT_DIR"])
    for path in receipt_dir.glob("*.json"):
        path.unlink()
    kimi = _run(["hook", "--harness", "kimi"], prompt=event, env=env, cwd=tmp_path)
    assert kimi.returncode == 0, kimi.stderr
    assert kimi.stdout == PACKET
    assert prompt not in kimi.stdout


def test_doctor_checks_tldrs_schema_and_receipt_directory(
    tmp_path: Path, gateway_env: tuple[dict[str, str], Path, Path]
) -> None:
    env, _, _ = gateway_env

    result = _run(
        ["doctor", "--project", str(tmp_path), "--json"],
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["checks"]["tldrs_executable"]["ok"] is True
    assert report["checks"]["packet_schema"]["ok"] is True
    assert report["checks"]["receipt_directory"]["ok"] is True
