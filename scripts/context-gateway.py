#!/usr/bin/env python3
"""Validated, auditable tldrs context injection for Clavain harnesses."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


SCHEMA_VERSION = 1
MARKER = "clavain-context-gateway:v1"
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_TIMEOUT_SECONDS = 15.0
SOURCE_SUFFIXES = {
    ".bash",
    ".bats",
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lua",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zsh",
}
DOC_CONFIG_NAMES = {
    "agents.md",
    "changelog.md",
    "claude.md",
    "contributing.md",
    "license",
    "license.md",
    "readme",
    "readme.md",
}
DOC_CONFIG_SUFFIXES = {
    ".ini",
    ".json",
    ".md",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
CODE_ACTION_RE = re.compile(
    r"\b(add|build|change|code|debug|delete|fix|implement|migrate|modify|"
    r"optimi[sz]e|patch|refactor|remove|rename|repair|replace|test|update|"
    r"upgrade|validate|verify|write)\b",
    re.IGNORECASE,
)
CODE_NOUN_RE = re.compile(
    r"\b(api|bug|class|cli|code|command|database|endpoint|function|hook|"
    r"implementation|method|middleware|module|package|parser|plugin|runtime|"
    r"schema|script|server|test|tool)\b",
    re.IGNORECASE,
)
PATH_RE = re.compile(
    r"(?<![\w.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\."
    r"(?:bash|bats|c|cc|cpp|cs|go|h|hpp|ini|java|js|json|jsx|kt|lua|md|php|"
    r"py|rb|rs|rst|sh|swift|toml|ts|tsx|txt|yaml|yml|zsh)\b",
    re.IGNORECASE,
)


class GatewayError(RuntimeError):
    """Expected tldrs execution or validation failure."""


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str
    confidence: float = 0.0
    packet: str = ""
    packet_sha256: str | None = None
    packet_chars: int = 0
    candidate_paths: tuple[str, ...] = ()
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    tldrs_version: str | None = None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _explicit_paths(prompt: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in PATH_RE.finditer(prompt):
        value = match.group(0).rstrip(".,:;)")
        if value not in seen:
            seen.add(value)
            paths.append(value)
    return paths


def _resolve_inside_project(project: Path, relative: str) -> Path | None:
    candidate = (project / relative).resolve()
    try:
        candidate.relative_to(project.resolve())
    except ValueError:
        return None
    return candidate


def _known_small_target_count(project: Path, paths: list[str]) -> int:
    source_paths = [path for path in paths if Path(path).suffix.lower() in SOURCE_SUFFIXES]
    if not source_paths or len(source_paths) > 3:
        return 0
    total_bytes = 0
    total_lines = 0
    line_limit = 200 if len(source_paths) == 1 else 400
    for source_path in source_paths:
        candidate = _resolve_inside_project(project, source_path)
        if candidate is None or not candidate.is_file():
            return 0
        try:
            total_bytes += candidate.stat().st_size
            if total_bytes > 8_000:
                return 0
            with candidate.open("rb") as handle:
                total_lines += sum(1 for _ in handle)
            if total_lines >= line_limit:
                return 0
        except OSError:
            return 0
    return len(source_paths)


def assess_eligibility(prompt: str, project: Path, mode: str) -> Decision | None:
    """Return a bypass decision, or None when tldrs should assess the task."""
    if mode == "off":
        return Decision("bypass", "gateway_disabled")
    if MARKER in prompt:
        return Decision("bypass", "already_injected")

    paths = _explicit_paths(prompt)
    if paths:
        doc_config_only = all(
            Path(path).name.lower() in DOC_CONFIG_NAMES
            or Path(path).suffix.lower() in DOC_CONFIG_SUFFIXES
            for path in paths
        )
        if doc_config_only and not any(
            Path(path).suffix.lower() in SOURCE_SUFFIXES for path in paths
        ):
            return Decision("bypass", "docs_or_config")
        small_target_count = _known_small_target_count(project, paths)
        if small_target_count == 1:
            return Decision("bypass", "known_small_target")
        if small_target_count > 1:
            return Decision("bypass", "known_small_target_set")

    has_source_path = any(
        Path(path).suffix.lower() in SOURCE_SUFFIXES for path in paths
    )
    if not has_source_path and not (
        CODE_ACTION_RE.search(prompt) and CODE_NOUN_RE.search(prompt)
    ):
        return Decision("bypass", "non_code_task")
    return None


def _tldrs_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _parse_tldrs_result(
    stdout: str, harness: str, min_confidence: float, tldrs_version: str | None
) -> Decision:
    try:
        envelope = json.loads(stdout)
        result = envelope["result"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GatewayError("malformed_tldrs_output") from exc

    if envelope.get("success") is not True or result.get("schema_version") != 1:
        raise GatewayError("unsupported_tldrs_schema")

    decision = result.get("decision")
    reason = str(result.get("reason") or "unspecified")
    confidence = float(result.get("confidence", 0.0))
    receipt = result.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise GatewayError("missing_tldrs_receipt")
    if decision != "inject":
        return Decision(
            "fallback",
            reason,
            confidence=confidence,
            min_confidence=min_confidence,
            candidate_paths=tuple(receipt.get("candidate_paths") or ()),
            tldrs_version=tldrs_version,
        )

    packet = result.get("packet")
    if not isinstance(packet, str) or not packet:
        raise GatewayError("empty_tldrs_packet")
    digest = _sha256(packet)
    if receipt.get("packet_sha256") != digest:
        raise GatewayError("packet_hash_mismatch")
    if receipt.get("packet_chars") != len(packet):
        raise GatewayError("packet_length_mismatch")
    if confidence < min_confidence:
        return Decision(
            "fallback",
            "below_gateway_confidence",
            confidence=confidence,
            min_confidence=min_confidence,
            candidate_paths=tuple(receipt.get("candidate_paths") or ()),
            tldrs_version=tldrs_version,
        )
    return Decision(
        "inject",
        reason,
        confidence=confidence,
        packet=packet,
        packet_sha256=digest,
        packet_chars=len(packet),
        candidate_paths=tuple(receipt.get("candidate_paths") or ()),
        min_confidence=min_confidence,
        tldrs_version=tldrs_version,
    )


def invoke_tldrs(
    prompt: str,
    project: Path,
    harness: str,
    min_confidence: float,
    test_command: str | None,
) -> Decision:
    executable = shutil.which(os.environ.get("CLAVAIN_TLDRS_BIN", "tldrs"))
    if executable is None:
        raise GatewayError("tldrs_not_found")
    command = [
        executable,
        "--machine",
        "packet",
        prompt,
        "--project",
        str(project),
        "--harness-profile",
        harness,
        "--min-confidence",
        str(min_confidence),
    ]
    if test_command:
        command.extend(["--test-command", test_command])
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=float(
                os.environ.get(
                    "CLAVAIN_CONTEXT_GATEWAY_TIMEOUT", DEFAULT_TIMEOUT_SECONDS
                )
            ),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GatewayError("tldrs_timeout") from exc
    except OSError as exc:
        raise GatewayError("tldrs_execution_error") from exc
    if completed.returncode != 0:
        raise GatewayError(f"tldrs_exit_{completed.returncode}")
    return _parse_tldrs_result(
        completed.stdout, harness, min_confidence, _tldrs_version(executable)
    )


def _receipt_dir() -> Path:
    override = os.environ.get("CLAVAIN_CONTEXT_GATEWAY_RECEIPT_DIR")
    if override:
        return Path(override).expanduser()
    state_root = Path(
        os.environ.get("CLAVAIN_STATE_DIR", "~/.clavain")
    ).expanduser()
    return state_root / "context-gateway"


def _writable_receipt_dir() -> Path:
    preferred = _receipt_dir()
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        if os.environ.get("CLAVAIN_CONTEXT_GATEWAY_RECEIPT_DIR"):
            raise
    fallback = _fallback_receipt_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _fallback_receipt_dir() -> Path:
    return Path(tempfile.gettempdir()) / f"clavain-context-gateway-{os.getuid()}"


def _write_receipt(directory: Path, filename: str, payload: dict[str, Any]) -> Path:
    descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        destination = directory / filename
        os.replace(temporary, destination)
        return destination
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def persist_receipt(
    decision: Decision,
    *,
    prompt: str,
    project: Path,
    harness: str,
    mode: str,
    duration_ms: int,
) -> Path:
    directory = _writable_receipt_dir()
    timestamp = datetime.now(timezone.utc)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp.isoformat(),
        "decision": decision.decision,
        "reason": decision.reason,
        "confidence": decision.confidence,
        "min_confidence": decision.min_confidence,
        "mode": mode,
        "harness_profile": harness,
        "project": str(project),
        "task_sha256": _sha256(prompt),
        "packet_sha256": decision.packet_sha256,
        "packet_chars": decision.packet_chars,
        "candidate_paths": list(decision.candidate_paths),
        "tldrs_version": decision.tldrs_version,
        "duration_ms": duration_ms,
    }
    filename = (
        f"{timestamp.strftime('%Y%m%dT%H%M%S.%fZ')}-{os.getpid()}-"
        f"{payload['task_sha256'][:10]}.json"
    )
    try:
        return _write_receipt(directory, filename, payload)
    except OSError:
        if os.environ.get("CLAVAIN_CONTEXT_GATEWAY_RECEIPT_DIR"):
            raise
        fallback = _fallback_receipt_dir()
        if directory == fallback:
            raise
        fallback.mkdir(parents=True, exist_ok=True)
        return _write_receipt(fallback, filename, payload)


def decide(
    prompt: str,
    *,
    project: Path,
    harness: str,
    mode: str,
    min_confidence: float,
    test_command: str | None,
) -> tuple[Decision, int]:
    started = time.monotonic()
    decision = assess_eligibility(prompt, project, mode)
    if decision is None:
        try:
            decision = invoke_tldrs(
                prompt, project, harness, min_confidence, test_command
            )
        except GatewayError as exc:
            decision = Decision(
                "fallback",
                str(exc),
                min_confidence=min_confidence,
            )
    duration_ms = round((time.monotonic() - started) * 1000)
    persist_receipt(
        decision,
        prompt=prompt,
        project=project,
        harness=harness,
        mode=mode,
        duration_ms=duration_ms,
    )
    return decision, duration_ms


def _injected_prompt(prompt: str, decision: Decision) -> str:
    assert decision.packet_sha256 is not None
    return (
        f"<!-- {MARKER} sha256={decision.packet_sha256} -->\n"
        "<tldrs-context>\n"
        f"{decision.packet}\n"
        "</tldrs-context>\n\n"
        f"{prompt}"
    )


def command_prepare(args: argparse.Namespace) -> int:
    prompt = sys.stdin.read()
    project = Path(args.project).expanduser().resolve()
    decision, _ = decide(
        prompt,
        project=project,
        harness=args.harness,
        mode=args.mode,
        min_confidence=args.min_confidence,
        test_command=args.test_command,
    )
    output = _injected_prompt(prompt, decision) if decision.decision == "inject" else prompt
    sys.stdout.write(output)
    if args.mode == "required" and decision.decision == "fallback":
        return 3
    return 0


def _hook_event() -> dict[str, Any]:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GatewayError("malformed_hook_input") from exc
    if not isinstance(event, dict):
        raise GatewayError("malformed_hook_input")
    return event


def command_hook(args: argparse.Namespace) -> int:
    try:
        event = _hook_event()
    except GatewayError:
        return 0
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return 0
    project_value = event.get("cwd") or os.getcwd()
    project = Path(str(project_value)).expanduser().resolve()
    decision, _ = decide(
        prompt,
        project=project,
        harness=args.harness,
        mode=args.mode,
        min_confidence=args.min_confidence,
        test_command=args.test_command,
    )
    if decision.decision != "inject":
        return 0
    if args.harness == "kimi":
        sys.stdout.write(decision.packet)
    else:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": decision.packet,
                }
            },
            sys.stdout,
            separators=(",", ":"),
        )
    return 0


def _doctor_receipt_directory() -> dict[str, Any]:
    try:
        directory = _writable_receipt_dir()
        descriptor, temporary = tempfile.mkstemp(prefix=".doctor-", dir=directory)
        os.close(descriptor)
        os.unlink(temporary)
    except OSError as exc:
        return {"ok": False, "detail": str(exc)}
    return {"ok": True, "detail": str(directory)}


def command_doctor(args: argparse.Namespace) -> int:
    executable = shutil.which(os.environ.get("CLAVAIN_TLDRS_BIN", "tldrs"))
    executable_check: dict[str, Any] = {
        "ok": executable is not None,
        "detail": executable or "tldrs not found",
    }
    schema_check: dict[str, Any]
    if executable is None:
        schema_check = {"ok": False, "detail": "not checked"}
    else:
        try:
            result = invoke_tldrs(
                "Refactor scripts/context-gateway.py and update its tests.",
                Path(args.project).expanduser().resolve(),
                "codex",
                DEFAULT_MIN_CONFIDENCE,
                None,
            )
            schema_check = {
                "ok": result.decision in {"inject", "fallback"},
                "detail": f"schema={SCHEMA_VERSION} decision={result.decision}",
            }
        except GatewayError as exc:
            schema_check = {"ok": False, "detail": str(exc)}
    checks = {
        "tldrs_executable": executable_check,
        "packet_schema": schema_check,
        "receipt_directory": _doctor_receipt_directory(),
    }
    report = {"ok": all(check["ok"] for check in checks.values()), "checks": checks}
    if args.json:
        json.dump(report, sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
    else:
        for name, check in checks.items():
            status = "OK" if check["ok"] else "FAIL"
            print(f"{status} {name}: {check['detail']}")
    return 0 if report["ok"] else 1


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--harness", choices=("generic", "codex", "claude", "kimi"), default="generic"
    )
    parser.add_argument(
        "--mode",
        choices=("off", "auto", "required"),
        default=os.environ.get("CLAVAIN_CONTEXT_GATEWAY_MODE", "auto"),
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=float(
            os.environ.get(
                "CLAVAIN_CONTEXT_GATEWAY_MIN_CONFIDENCE",
                DEFAULT_MIN_CONFIDENCE,
            )
        ),
    )
    parser.add_argument("--test-command")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="%(prog)s 1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="enrich a prompt read from stdin")
    prepare.add_argument("--project", required=True)
    _common_arguments(prepare)
    prepare.set_defaults(function=command_prepare)

    hook = subparsers.add_parser("hook", help="adapt a UserPromptSubmit hook event")
    _common_arguments(hook)
    hook.set_defaults(function=command_hook)

    doctor = subparsers.add_parser("doctor", help="verify gateway dependencies")
    doctor.add_argument("--project", default=os.getcwd())
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(function=command_doctor)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
