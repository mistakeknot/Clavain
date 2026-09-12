#!/usr/bin/env python3
"""Seal and render bounded Codex dispatch reports.

The compact report is presentation only. Full last-message, event, stderr, and
sidecar bytes remain in a private sibling artifact directory. ``replay`` verifies
the sealed manifest before regenerating the same report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_REPORT_BYTES = 4096
SCHEMA = "clavain.dispatch.compact.v1"
MANIFEST_SCHEMA = "clavain.dispatch.artifacts.v1"
RECOVERY = "full artifacts in output parent"
REQUIRED_ARTIFACTS = (
    "last_message",
    "stderr",
    "stdout_events",
    "summary",
    "verdict",
)
ARTIFACT_FILES = {
    "last_message": "last-message.txt",
    "outcome": "outcome.json",
    "receipt": "receipt.json",
    "resolved_route": "resolved-route.json",
    "stderr": "stderr.log",
    "stdout_events": "stdout.events.jsonl",
    "summary": "summary.txt",
    "verdict": "verdict.txt",
    "verdict_pre_error": "verdict.pre-error.txt",
}
DIGEST_SLOTS = tuple(sorted(ARTIFACT_FILES))
THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
DEGRADE_ORDER = ("diagnostics", "counters", "native", "artifacts")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


@dataclass
class ReportModel:
    backend_code: int | None
    dispatcher_code: int
    classification: str
    unusable: bool
    native_coverage: dict[str, Any]
    digests: dict[str, dict[str, Any]]
    manifest_sha256: str | None
    diagnostics: list[str]
    counters: list[dict[str, Any]]
    native: dict[str, Any] | None
    artifacts: list[dict[str, str]]
    recovery: str = RECOVERY


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_status(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    return "available" if stat.S_ISREG(mode) else "nonregular"


def _safe_artifact_dir(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("artifact directory must be an existing real directory")
    path = path.resolve(strict=True)
    os.chmod(path, 0o700)
    return path


def _copy_regular(source: Path, destination: Path) -> str:
    status = _regular_status(source)
    if status != "available":
        return status
    try:
        if source.resolve(strict=True) == destination.resolve(strict=True):
            os.chmod(destination, 0o600)
            return "available"
    except FileNotFoundError:
        pass

    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            return "nonregular"
        with os.fdopen(descriptor, "rb") as reader, temporary.open("xb") as writer:
            os.chmod(temporary, 0o600)
            shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
        return "available"
    except (FileNotFoundError, OSError):
        temporary.unlink(missing_ok=True)
        return "inconsistent"


def _artifact_entry(logical_name: str, path: Path, status: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "logical_name": logical_name,
        "path": ARTIFACT_FILES[logical_name],
        "status": status,
        "size": None,
        "sha256": None,
    }
    if status == "available":
        if _regular_status(path) != "available":
            entry["status"] = "inconsistent"
        else:
            entry["size"] = path.stat().st_size
            entry["sha256"] = _sha256(path)
    return entry


def _parse_events(path: Path, available: bool) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    counter_names = ("turns", "commands", "messages", "input_tokens", "cached_input_tokens", "output_tokens")
    values = {name: 0 for name in counter_names}
    diagnostics: list[str] = []
    thread_ids: list[str] = []
    invalid = 0
    valid_events = 0

    if not available:
        coverage = {"status": "incomplete", "reason": "stdout_events_unavailable", "valid_events": None}
        counters = [{"name": name, "value": None, "status": "unknown"} for name in counter_names]
        return coverage, counters, None, ["stdout_events_unavailable"]

    with path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                invalid += 1
                continue
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                invalid += 1
                continue
            valid_events += 1
            event_type = event["type"]
            if event_type == "thread.started":
                thread_id = event.get("thread_id")
                if not isinstance(thread_id, str) or not THREAD_ID_RE.fullmatch(thread_id):
                    invalid += 1
                else:
                    thread_ids.append(thread_id)
            elif event_type == "turn.started":
                values["turns"] += 1
            elif event_type == "item.completed":
                item = event.get("item")
                item_type = item.get("type") if isinstance(item, dict) else None
                if item_type == "command_execution":
                    values["commands"] += 1
                elif item_type == "agent_message":
                    values["messages"] += 1
            elif event_type == "turn.completed":
                usage = event.get("usage")
                if usage is None:
                    usage = {}
                if not isinstance(usage, dict):
                    invalid += 1
                    continue
                for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
                    value = usage.get(name, 0)
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        invalid += 1
                    else:
                        values[name] += value

    unique_threads = sorted(set(thread_ids))
    if invalid:
        diagnostics.append("malformed_native_events")
    if len(unique_threads) > 1:
        diagnostics.append("contradictory_native_thread_ids")
    if not unique_threads:
        diagnostics.append("native_thread_id_unavailable")

    complete = invalid == 0 and len(unique_threads) == 1
    if complete:
        coverage = {"status": "complete", "reason": None, "valid_events": valid_events}
        counters = [{"name": name, "value": values[name], "status": "observed"} for name in counter_names]
        native = {"thread_id": unique_threads[0]}
    else:
        reason = diagnostics[0] if diagnostics else "native_coverage_incomplete"
        coverage = {"status": "incomplete", "reason": reason, "valid_events": valid_events}
        counters = [{"name": name, "value": None, "status": "unknown"} for name in counter_names]
        native = None
    return coverage, counters, native, diagnostics


def _report_dict(model: ReportModel, omissions: list[str]) -> dict[str, Any]:
    # Insertion order is part of the stable presentation contract.
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "backend_process_code": model.backend_code,
        "dispatcher_code": model.dispatcher_code,
        "classification": model.classification,
        "unusable": model.unusable,
        "native_coverage": model.native_coverage,
        "digests": {name: model.digests[name] for name in DIGEST_SLOTS},
        "manifest_sha256": model.manifest_sha256,
        "recovery": model.recovery,
        "omissions": omissions,
    }
    optional = {
        "diagnostics": model.diagnostics,
        "counters": model.counters,
        "native": model.native,
        "artifacts": model.artifacts,
    }
    for name in DEGRADE_ORDER:
        if name not in omissions and optional[name] not in (None, [], {}):
            report[name] = optional[name]
    return report


def encode_bounded_report(model: ReportModel) -> bytes:
    omissions: list[str] = []
    encoded = _json_bytes(_report_dict(model, omissions))
    for field in DEGRADE_ORDER:
        if len(encoded) <= MAX_REPORT_BYTES:
            return encoded
        omissions.append(field)
        encoded = _json_bytes(_report_dict(model, omissions))
    if len(encoded) <= MAX_REPORT_BYTES:
        return encoded

    # All unbounded optional material is already gone. Normalize the remaining
    # caller-controlled labels rather than truncating text or UTF-8 bytes.
    fallback = ReportModel(
        backend_code=model.backend_code,
        dispatcher_code=model.dispatcher_code or 1,
        classification="presentation_failure",
        unusable=True,
        native_coverage={"status": "incomplete", "reason": "report_core_oversized", "valid_events": None},
        digests=model.digests,
        manifest_sha256=model.manifest_sha256,
        diagnostics=[],
        counters=[],
        native=None,
        artifacts=[],
        recovery=RECOVERY,
    )
    encoded = _json_bytes(_report_dict(fallback, list(DEGRADE_ORDER)))
    if len(encoded) > MAX_REPORT_BYTES:
        raise ValueError("mandatory compact report exceeds byte limit")
    return encoded


def _digest_slots(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name = {entry["logical_name"]: entry for entry in entries}
    return {
        name: {
            "status": by_name.get(name, {}).get("status", "unavailable"),
            "sha256": by_name.get(name, {}).get("sha256"),
        }
        for name in DIGEST_SLOTS
    }


def _write_private(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        os.chmod(temporary, 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def render(args: argparse.Namespace) -> int:
    artifact_dir = _safe_artifact_dir(args.artifacts_dir)
    sources: dict[str, Path] = {}
    for item in args.artifact:
        if "=" not in item:
            raise ValueError("--artifact requires logical_name=path")
        name, raw_path = item.split("=", 1)
        if name not in ARTIFACT_FILES or name == "outcome":
            raise ValueError(f"unsupported artifact logical name: {name}")
        if name in sources:
            raise ValueError(f"duplicate artifact logical name: {name}")
        sources[name] = Path(raw_path)

    entries: list[dict[str, Any]] = []
    for name in sorted(set(ARTIFACT_FILES) - {"outcome"}):
        destination = artifact_dir / ARTIFACT_FILES[name]
        source = sources.get(name)
        if source is None:
            status = "missing" if name in REQUIRED_ARTIFACTS else "unavailable"
        else:
            status = _copy_regular(source, destination)
        entries.append(_artifact_entry(name, destination, status))

    unavailable_required = [entry["logical_name"] for entry in entries if entry["logical_name"] in REQUIRED_ARTIFACTS and entry["status"] != "available"]
    unusable = bool(args.force_unusable or unavailable_required)
    dispatcher_code = args.dispatcher_code
    if unusable and dispatcher_code == 0:
        dispatcher_code = 1
    classification = args.classification
    if unusable and args.backend_code == 0:
        classification = "presentation_failure"

    stdout_entry = next(entry for entry in entries if entry["logical_name"] == "stdout_events")
    coverage, counters, native, native_diagnostics = _parse_events(
        artifact_dir / ARTIFACT_FILES["stdout_events"], stdout_entry["status"] == "available"
    )
    diagnostics = list(dict.fromkeys(args.diagnostic + native_diagnostics))
    diagnostics.extend(f"required_artifact_{name}_unavailable" for name in unavailable_required)

    outcome = {
        "backend_process_code": args.backend_code,
        "dispatcher_code": dispatcher_code,
        "classification": classification,
        "unusable": unusable,
        "diagnostics": diagnostics,
        "recovery": RECOVERY if unusable else str(artifact_dir),
    }
    outcome_path = artifact_dir / ARTIFACT_FILES["outcome"]
    _write_private(outcome_path, _json_bytes(outcome))
    entries.append(_artifact_entry("outcome", outcome_path, "available"))
    entries.sort(key=lambda entry: entry["logical_name"])

    manifest = {"schema": MANIFEST_SCHEMA, "artifacts": entries}
    manifest_path = artifact_dir / "manifest.json"
    manifest_bytes = _json_bytes(manifest)
    _write_private(manifest_path, manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    model = ReportModel(
        backend_code=args.backend_code,
        dispatcher_code=dispatcher_code,
        classification=classification,
        unusable=unusable,
        native_coverage=coverage,
        digests=_digest_slots(entries),
        manifest_sha256=manifest_sha256,
        diagnostics=diagnostics,
        counters=counters,
        native=native,
        artifacts=[{"logical_name": entry["logical_name"], "path": entry["path"]} for entry in entries if entry["status"] == "available"],
        recovery=outcome["recovery"],
    )
    encoded = encode_bounded_report(model)
    rendered = json.loads(encoded)
    if rendered.get("unusable") and not unusable:
        # A recovery path that cannot survive whole-field degradation makes
        # presentation unusable. Reseal outcome + manifest with the bounded,
        # caller-known recovery instruction rather than truncating the path.
        unusable = True
        dispatcher_code = dispatcher_code or 1
        classification = "presentation_failure"
        diagnostics.append("recovery_path_oversized")
        outcome.update(
            dispatcher_code=dispatcher_code,
            classification=classification,
            unusable=True,
            diagnostics=diagnostics,
            recovery=RECOVERY,
        )
        _write_private(outcome_path, _json_bytes(outcome))
        entries = [entry for entry in entries if entry["logical_name"] != "outcome"]
        entries.append(_artifact_entry("outcome", outcome_path, "available"))
        entries.sort(key=lambda entry: entry["logical_name"])
        manifest = {"schema": MANIFEST_SCHEMA, "artifacts": entries}
        manifest_bytes = _json_bytes(manifest)
        _write_private(manifest_path, manifest_bytes)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        model = ReportModel(
            backend_code=args.backend_code,
            dispatcher_code=dispatcher_code,
            classification=classification,
            unusable=True,
            native_coverage=coverage,
            digests=_digest_slots(entries),
            manifest_sha256=manifest_sha256,
            diagnostics=diagnostics,
            counters=counters,
            native=native,
            artifacts=[{"logical_name": entry["logical_name"], "path": entry["path"]} for entry in entries if entry["status"] == "available"],
            recovery=RECOVERY,
        )
        encoded = encode_bounded_report(model)
    sys.stdout.buffer.write(encoded)
    return 2 if unusable else 0


def _load_regular_json(path: Path) -> Any:
    if _regular_status(path) != "available":
        raise ValueError(f"required regular file unavailable: {path.name}")
    return json.loads(path.read_bytes())


def replay(args: argparse.Namespace) -> int:
    artifact_dir = _safe_artifact_dir(args.artifacts_dir)
    manifest_path = artifact_dir / "manifest.json"
    try:
        manifest = _load_regular_json(manifest_path)
        if manifest.get("schema") != MANIFEST_SCHEMA or not isinstance(manifest.get("artifacts"), list):
            raise ValueError("invalid manifest schema")
        entries = manifest["artifacts"]
        names = [entry.get("logical_name") for entry in entries]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("manifest logical names are not unique and sorted")
        diagnostics: list[str] = []
        for entry in entries:
            name = entry.get("logical_name")
            if name not in ARTIFACT_FILES or entry.get("path") != ARTIFACT_FILES[name]:
                raise ValueError("manifest contains an unknown artifact path")
            artifact_path = artifact_dir / entry["path"]
            if entry.get("status") == "available":
                if _regular_status(artifact_path) != "available":
                    diagnostics.append(f"manifest_{name}_nonregular")
                elif artifact_path.stat().st_size != entry.get("size") or _sha256(artifact_path) != entry.get("sha256"):
                    diagnostics.append(f"manifest_{name}_mismatch")
            elif _regular_status(artifact_path) != "missing":
                diagnostics.append(f"manifest_{name}_unexpected")
        expected_files = {"manifest.json"} | {entry["path"] for entry in entries if entry.get("status") == "available"}
        actual_files = {path.name for path in artifact_dir.iterdir()}
        if actual_files != expected_files:
            diagnostics.append("manifest_directory_membership_mismatch")
        outcome = _load_regular_json(artifact_dir / ARTIFACT_FILES["outcome"])
    except (ValueError, OSError, json.JSONDecodeError, AttributeError) as error:
        diagnostics = ["manifest_unverifiable"]
        outcome = {"backend_process_code": None, "dispatcher_code": 1, "classification": "presentation_failure", "unusable": True, "diagnostics": []}
        entries = []

    stdout = next((entry for entry in entries if entry.get("logical_name") == "stdout_events"), None)
    stdout_available = bool(stdout and stdout.get("status") == "available" and not any(item.startswith("manifest_stdout_events_") for item in diagnostics))
    coverage, counters, native, native_diagnostics = _parse_events(
        artifact_dir / ARTIFACT_FILES["stdout_events"], stdout_available
    )
    all_diagnostics = list(dict.fromkeys(list(outcome.get("diagnostics", [])) + native_diagnostics + diagnostics))
    unusable = bool(outcome.get("unusable") or diagnostics)
    dispatcher_code = outcome.get("dispatcher_code", 1)
    classification = outcome.get("classification", "presentation_failure")
    if diagnostics:
        classification = "presentation_failure"
        if dispatcher_code == 0:
            dispatcher_code = 1
    manifest_sha256 = _sha256(manifest_path) if _regular_status(manifest_path) == "available" else None
    model = ReportModel(
        backend_code=outcome.get("backend_process_code"),
        dispatcher_code=dispatcher_code,
        classification=classification,
        unusable=unusable,
        native_coverage=coverage,
        digests=_digest_slots(entries),
        manifest_sha256=manifest_sha256,
        diagnostics=all_diagnostics,
        counters=counters,
        native=native,
        artifacts=[{"logical_name": entry["logical_name"], "path": entry["path"]} for entry in entries if entry.get("status") == "available"],
        recovery=outcome.get("recovery", RECOVERY),
    )
    sys.stdout.buffer.write(encode_bounded_report(model))
    return 2 if unusable else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render", help="copy artifacts, seal a manifest, and render JSON")
    render_parser.add_argument("--artifacts-dir", type=Path, required=True)
    render_parser.add_argument("--backend-code", type=int, required=True)
    render_parser.add_argument("--dispatcher-code", type=int, required=True)
    render_parser.add_argument("--classification", required=True)
    render_parser.add_argument("--artifact", action="append", default=[])
    render_parser.add_argument("--diagnostic", action="append", default=[])
    render_parser.add_argument("--force-unusable", action="store_true")
    render_parser.set_defaults(function=render)
    replay_parser = subparsers.add_parser("replay", help="verify a sealed manifest and reproduce its report")
    replay_parser.add_argument("--artifacts-dir", type=Path, required=True)
    replay_parser.set_defaults(function=replay)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.function(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"dispatch_report: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
