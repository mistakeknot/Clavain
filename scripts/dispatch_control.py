#!/usr/bin/env python3
"""Fail-closed admission and App Server control for governed Codex operations.

This adapter never starts a turn and never accepts a caller-supplied thread ID.
The only eligible ID is recovered from a seed event artifact whose receipt is
also present in the authoritative Intercore decision log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import struct
import subprocess
import sys
import time


MAX_BINDING = 1024 * 1024
MAX_FRAME = 1024 * 1024
MAX_TRANSCRIPT = 16 * 1024 * 1024
HANDSHAKE_TIMEOUT = 10.0
OPERATION_TIMEOUT = 120.0
APPROVED_MANIFEST_SHA256 = "d3368f6ae469d8f0a1018daf701d1a4a1d07d0c075478491ed838a3ab3589997"
APPROVED_MANIFEST_FILES = 426
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
HANDOFF_MAGIC = b"NCF2"
HANDOFF_HEADER = struct.Struct(">4sQ32s")
INT64_MAX = (1 << 63) - 1


class ControlError(ValueError):
    def __init__(self, reason, *, remote_completion="unknown"):
        super().__init__(reason)
        self.reason = reason
        self.remote_completion = remote_completion


class Cancelled(ControlError):
    def __init__(self, signum):
        super().__init__("cancelled", remote_completion="unknown")
        self.signum = signum


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def constant(_):
        raise ValueError("nonfinite JSON number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed JSON") from exc


def read_regular(path, limit=MAX_BINDING, *, reject_hardlinks=False):
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"nonregular or unsafe alias evidence: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit or
                before.st_uid != os.getuid() or reject_hardlinks and before.st_nlink != 1):
            reason = "unsafe hardlink or alias" if reject_hardlinks and before.st_nlink != 1 else "nonregular or oversized evidence"
            raise ValueError(f"{reason}: {path}")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(raw) > limit:
            raise ValueError(f"oversized evidence: {path}")
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError(f"evidence changed while open: {path}")
        return raw
    finally:
        os.close(descriptor)


def _write_all(descriptor, payload, deadline=None):
    view = memoryview(payload)
    while view:
        if deadline is not None and time.monotonic() >= deadline:
            raise ValueError("bounded write deadline exceeded")
        count = os.write(descriptor, view)
        if count <= 0:
            raise ValueError("short write")
        view = view[count:]


def capture_binding_snapshot(path, private_directory):
    """Capture exactly the bytes validated by the fixture supervisor."""
    directory = Path(private_directory)
    info = directory.lstat()
    if directory.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("binding snapshot directory must be a private 0700 directory")
    raw = read_regular(path, MAX_BINDING, reject_hardlinks=True)
    strict_json(raw)
    snapshot = directory / "binding.snapshot.json"
    descriptor = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {"path": str(snapshot.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": raw, "fixture_only": True, "eligible": False}


def write_framed_handoff(descriptor, value, *, deadline_seconds=HANDSHAKE_TIMEOUT):
    payload = canonical(value).encode()
    if len(payload) > MAX_FRAME:
        raise ValueError("oversized handoff")
    frame = HANDOFF_HEADER.pack(HANDOFF_MAGIC, len(payload), hashlib.sha256(payload).digest()) + payload
    try:
        _write_all(descriptor, frame, time.monotonic() + deadline_seconds)
    finally:
        os.close(descriptor)


def _read_exact(descriptor, count, deadline):
    chunks = []
    remaining = count
    while remaining:
        if time.monotonic() >= deadline:
            raise ValueError("handoff read deadline exceeded")
        chunk = os.read(descriptor, remaining)
        if not chunk:
            raise ValueError("truncated or consumed handoff")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_framed_handoff(descriptor, *, deadline_seconds=HANDSHAKE_TIMEOUT):
    deadline = time.monotonic() + deadline_seconds
    header = _read_exact(descriptor, HANDOFF_HEADER.size, deadline)
    magic, size, expected = HANDOFF_HEADER.unpack(header)
    if magic != HANDOFF_MAGIC or size > MAX_FRAME:
        raise ValueError("invalid or oversized handoff")
    payload = _read_exact(descriptor, size, deadline)
    if hashlib.sha256(payload).digest() != expected:
        raise ValueError("handoff digest mismatch")
    if os.read(descriptor, 1):
        raise ValueError("handoff has trailing bytes")
    value = strict_json(payload)
    if not isinstance(value, dict):
        raise ValueError("handoff must be an object")
    return value


def _terminate_group(process, deadline):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        while process.poll() is None and time.monotonic() < min(deadline, time.monotonic() + 1.0):
            time.sleep(0.02)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    remaining = max(0.0, deadline - time.monotonic())
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("owned fixture process group was not reaped") from exc


def run_fixture_handoff(descriptor, result_path):
    """Consume one private packet and supervise one fixture transport group."""
    packet = read_framed_handoff(descriptor)
    fields = {"schema_version", "fixture_only", "eligible", "reservation_decision_id",
              "operation_key", "parent_pid", "fixture_root", "argv", "executable_sha256",
              "timeout_seconds"}
    exact_object(packet, fields, "fixture handoff")
    if packet["schema_version"] != 2 or packet["fixture_only"] is not True or packet["eligible"] is not False:
        raise ValueError("fixture handoff is not permanently ineligible")
    if type(packet["reservation_decision_id"]) is not int or packet["reservation_decision_id"] <= 0:
        raise ValueError("fixture handoff has invalid reservation")
    require_hash(packet["operation_key"], "native operation key")
    if packet["parent_pid"] != os.getppid():
        raise ValueError("fixture handoff parent identity mismatch")
    try:
        os.kill(packet["parent_pid"], 0)
    except PermissionError:
        pass
    except OSError as exc:
        raise ValueError("fixture handoff parent is not live") from exc
    root = Path(packet["fixture_root"]).resolve(strict=True)
    argv = packet["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and "\x00" not in item for item in argv):
        raise ValueError("fixture handoff argv is malformed")
    executable = Path(argv[0]).resolve(strict=True)
    try:
        executable.relative_to(root)
    except ValueError as exc:
        raise ValueError("fixture transport must remain inside its fixture root") from exc
    require_hash(packet["executable_sha256"], "fixture executable")
    if hashlib.sha256(read_regular(executable, 16 * 1024 * 1024)).hexdigest() != packet["executable_sha256"]:
        raise ValueError("fixture executable changed before launch")
    timeout = packet["timeout_seconds"]
    if type(timeout) not in {int, float} or isinstance(timeout, bool) or not 0 < timeout <= OPERATION_TIMEOUT:
        raise ValueError("fixture process timeout is invalid")
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    deadline = time.monotonic() + timeout
    termination_reason = None
    while process.poll() is None:
        if os.getppid() != packet["parent_pid"]:
            termination_reason = "dispatcher-parent-died"
            break
        if time.monotonic() >= deadline:
            termination_reason = "operation-timeout"
            break
        time.sleep(0.02)
    if termination_reason is not None:
        _terminate_group(process, time.monotonic() + 2.0)
    else:
        process.wait()
    result = {"schema_version": 2, "fixture_only": True, "eligible": False,
              "reservation_decision_id": packet["reservation_decision_id"],
              "operation_key": packet["operation_key"],
              "process": {"exit_code": process.returncode, "reaped": process.poll() is not None,
                          "termination_reason": termination_reason}}
    write_private(result_path, result)
    return result


def _toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    raise ValueError("unsupported native configuration value")


def build_native_resume_argv(admitted, output):
    """Build the sole fixture-tested CLI resume grammar; prompt is stdin data."""
    request = admitted.get("configuration", {}).get("request")
    if not isinstance(request, dict):
        raise ValueError("missing admitted resume configuration")
    executable = admitted.get("executable")
    thread_id = admitted.get("native_thread_id")
    if not isinstance(executable, str) or not UUID.fullmatch(str(thread_id)):
        raise ValueError("missing pinned native executable or UUID")
    output = Path(output)
    if not output.is_absolute():
        raise ValueError("native output must be absolute")
    argv = [executable, "exec", "-s", request["sandbox"], "-C", request["cwd"]]
    roots = request.get("runtimeWorkspaceRoots", [])
    if roots:
        argv += ["-c", "sandbox_workspace_write.writable_roots=[" + ",".join(_toml_value(v) for v in roots) + "]"]
    settings = {
        "approval_policy": request["approvalPolicy"],
        "approvals_reviewer": request["approvalsReviewer"],
        "model_provider": request["modelProvider"],
        "model_reasoning_effort": request["config"]["model_reasoning_effort"],
        "service_tier": request["serviceTier"],
    }
    for key, value in settings.items():
        argv += ["-c", f"{key}={_toml_value(value)}"]
    for key, value in sorted(request.get("config", {}).items()):
        if key not in settings:
            argv += ["-c", f"{key}={_toml_value(value)}"]
    argv += ["resume", "--json", "-m", request["model"], "-o", str(output), thread_id.lower(), "-"]
    return argv


def sha256(path, limit=MAX_TRANSCRIPT):
    return hashlib.sha256(read_regular(path, limit)).hexdigest()


def require_hash(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"invalid {label} sha256")


def exact_object(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{label} must contain exactly its declared fields")


def evidence_ref(value, label, limit=MAX_TRANSCRIPT):
    exact_object(value, {"path", "sha256"}, label)
    path = Path(value["path"])
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    require_hash(value["sha256"], label)
    try:
        actual = sha256(path, limit)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} evidence unavailable") from exc
    if actual != value["sha256"]:
        raise ValueError(f"{label} evidence hash mismatch")
    return path


def context(record):
    value = record.get("context_json")
    value = strict_json(value.encode()) if isinstance(value, str) else value
    if not isinstance(value, dict):
        raise ValueError("authoritative decision has malformed context")
    return value


def load_records(database, executable="ic"):
    database = Path(database)
    if not database.is_absolute() or not database.is_file():
        raise ValueError("authoritative database must be an existing absolute file")
    result = subprocess.run(
        [executable, f"--db={database}", "--json", "route", "list", "--limit=1000000"],
        cwd=database.parent, text=True, capture_output=True, check=False, timeout=10,
    )
    if result.returncode:
        raise ValueError(f"authoritative Intercore read failed ({result.returncode})")
    rows = strict_json(result.stdout.encode())
    if not isinstance(rows, list) or len(rows) in {1000, 1_000_000} or len(rows) >= 1_000_000:
        raise ValueError("authoritative decision export malformed or truncated")
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or any(type(ident) is not int for ident in ids) or len(ids) != len(set(ids)):
        raise ValueError("authoritative decision export has malformed or duplicate IDs")
    return rows


def native_operation_key(native_thread_id, operation, provider="codex"):
    """Identify the remote resource; caller-selected provenance is excluded."""
    if provider != "codex" or operation not in {"compact", "resume"}:
        raise ValueError("unsupported native operation key")
    if not isinstance(native_thread_id, str) or not UUID.fullmatch(native_thread_id):
        raise ValueError("invalid native UUID")
    key = {
        "schema": "native-operation-key-v2",
        "provider": provider,
        "native_thread_id": native_thread_id.lower(),
        "operation": operation,
    }
    return hashlib.sha256(canonical(key).encode()).hexdigest()


def _native_record_resource(record):
    """Return a legacy/v2 native resource tuple, conservatively."""
    if not isinstance(record, dict):
        raise ValueError("authoritative decision export contains a non-object row")
    value = context(record)
    execution = value.get("execution")
    if not isinstance(execution, dict):
        return None
    candidates = []
    for field in ("native_admission", "operation_request", "native_send_intent", "native_operation"):
        candidate = execution.get(field)
        if isinstance(candidate, dict):
            candidates.append(candidate)
    resources = set()
    for candidate in candidates:
        operation = candidate.get("operation")
        thread_id = candidate.get("seed_thread_id", candidate.get("native_thread_id"))
        if operation in {"compact", "resume"} and isinstance(thread_id, str) and UUID.fullmatch(thread_id):
            resources.add(("codex", thread_id.lower(), operation))
        elif candidate.get("operation_key") is not None:
            require_hash(candidate.get("operation_key"), "native operation key")
            resources.add(("operation-key", candidate["operation_key"], operation))
    if len(resources) > 1:
        raise ValueError("authoritative native record has ambiguous resource mapping")
    return next(iter(resources), None)


def assert_native_resource_available(records, native_thread_id, operation, binding_sha256=None):
    target = ("codex", native_thread_id.lower(), operation)
    target_key = native_operation_key(native_thread_id, operation)
    for row in records:
        resource = _native_record_resource(row)
        if resource == target or resource == ("operation-key", target_key, operation):
            raise ValueError("native remote resource already admitted or consumed")
        execution = context(row).get("execution", {}) if isinstance(row, dict) else {}
        for field in ("operation_request", "native_operation"):
            legacy = execution.get(field, {}) if isinstance(execution, dict) else {}
            if (isinstance(legacy, dict) and legacy.get("operation") == operation and
                    binding_sha256 is not None and legacy.get("binding_sha256") == binding_sha256):
                raise ValueError("legacy native binding was already admitted or consumed")


def elect_native_reservation(records, operation_key, reservation_decision_id):
    """Elect the lowest committed reservation; locks are never authority."""
    require_hash(operation_key, "native operation key")
    if type(reservation_decision_id) is not int:
        raise ValueError("reservation decision ID must be an integer")
    ids = []
    seen = set()
    for row in records:
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] in seen:
            raise ValueError("authoritative decision export has malformed or duplicate IDs")
        seen.add(row["id"])
        execution = context(row).get("execution", {})
        admission = execution.get("native_admission", {}) if isinstance(execution, dict) else {}
        if isinstance(admission, dict) and admission.get("operation_key") == operation_key:
            if admission.get("fixture_only") is not True or admission.get("eligible") is not False:
                raise ValueError("fixture reservation lacks ineligible provenance")
            ids.append(row["id"])
    if reservation_decision_id not in ids:
        raise ValueError("reservation is absent from authoritative history")
    if reservation_decision_id != min(ids):
        raise ValueError("native reservation lost committed-record election")
    return reservation_decision_id


def evaluate_native_budget(records, scope_id, scope_limit_tokens, reservation_decision_id):
    """Evaluate the durable ordered reservation prefix without refunding unknown spend."""
    if not isinstance(scope_id, str) or not scope_id:
        raise ValueError("native budget scope is missing")
    if type(scope_limit_tokens) is not int or not 0 < scope_limit_tokens <= INT64_MAX:
        raise ValueError("native budget limit must be a positive int64")
    if type(reservation_decision_id) is not int:
        raise ValueError("native budget reservation ID must be an integer")
    admissions = {}
    terminals = {}
    send_intents = set()
    seen = set()
    for row in records:
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] in seen:
            raise ValueError("authoritative decision export has malformed or duplicate IDs")
        seen.add(row["id"])
        execution = context(row).get("execution", {})
        if not isinstance(execution, dict):
            continue
        admission = execution.get("native_admission")
        if isinstance(admission, dict):
            budget = admission.get("native_budget")
            if isinstance(budget, dict) and budget.get("scope_id") == scope_id and row["id"] <= reservation_decision_id:
                allocation = budget.get("allocation_tokens")
                if type(allocation) is not int or not 0 < allocation <= INT64_MAX:
                    raise ValueError("native budget allocation must be a positive int64")
                admissions[row["id"]] = allocation
        intent = execution.get("native_send_intent")
        if isinstance(intent, dict) and type(intent.get("admission_decision_id")) is int:
            send_intents.add(intent["admission_decision_id"])
        terminal = execution.get("native_operation")
        if isinstance(terminal, dict) and type(terminal.get("admission_decision_id")) is int:
            terminals[terminal["admission_decision_id"]] = terminal
    if reservation_decision_id not in admissions:
        raise ValueError("native budget reservation is absent")
    debit = 0
    details = []
    for ident, allocation in sorted(admissions.items()):
        terminal = terminals.get(ident)
        if terminal is None:
            if ident in send_intents:
                raise ValueError("native budget blocked by unknown possible spending")
            charged = allocation
            status = "reserved"
        elif terminal.get("native_launched") is False and terminal.get("remote_completion") == "not-started":
            charged = 0
            status = "not-launched"
        elif terminal.get("accounting_status") == "complete":
            usage = validate_usage(terminal.get("native_usage"))
            charged = usage["last"]["inputTokens"] + usage["last"]["outputTokens"]
            status = "accounted"
        else:
            raise ValueError("native budget blocked by unknown possible spending")
        debit += charged
        if debit > INT64_MAX:
            raise ValueError("native budget debit overflows int64")
        details.append({"admission_decision_id": ident, "debit_tokens": charged, "status": status})
    if debit > scope_limit_tokens:
        raise ValueError("native budget ordered reservation prefix exceeds scope limit")
    return {"scope_id": scope_id, "scope_limit_tokens": scope_limit_tokens,
            "reserved_tokens": debit, "remaining_tokens": scope_limit_tokens - debit,
            "reservations": details}


def decision(records, ident, rule, label):
    if type(ident) is not int:
        raise ValueError(f"{label} authoritative decision ID must be an integer")
    row = next((item for item in records if item.get("id") == ident and item.get("rule_matched") == rule), None)
    if row is None:
        raise ValueError(f"missing authoritative {label} decision")
    return context(row)


def validate_protocol_manifest(path, expected_sha256=APPROVED_MANIFEST_SHA256,
                               expected_file_count=APPROVED_MANIFEST_FILES):
    path = Path(path)
    if sha256(path) != expected_sha256:
        raise ValueError("native schema manifest pin mismatch")
    value = strict_json(read_regular(path, 4 * 1024 * 1024))
    exact_object(value, {"schema_version", "codex_executable", "executable_sha256",
                         "codex_version", "experimental", "files"}, "native schema manifest")
    if value["schema_version"] != 1 or value["experimental"] is not True:
        raise ValueError("native schema manifest metadata mismatch")
    files = value["files"]
    if not isinstance(files, list) or len(files) != expected_file_count:
        raise ValueError("native schema manifest file count mismatch")
    root = path.parent / "native-schema"
    seen = set()
    for item in files:
        exact_object(item, {"path", "sha256"}, "native schema entry")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in seen:
            raise ValueError("native schema manifest has unsafe or duplicate path")
        seen.add(str(relative)); require_hash(item["sha256"], "native schema entry")
        try:
            actual = sha256(root / relative, 4 * 1024 * 1024)
        except (OSError, ValueError) as exc:
            raise ValueError("native schema file unavailable") from exc
        if actual != item["sha256"]:
            raise ValueError("native schema file hash mismatch")
    executable = Path(value["codex_executable"])
    if not executable.is_absolute() or sha256(executable, 256 * 1024 * 1024) != value["executable_sha256"]:
        raise ValueError("native schema executable pin mismatch")
    return value


def seed_thread(events_path):
    threads = set()
    raw = read_regular(events_path, MAX_TRANSCRIPT)
    for line in raw.splitlines():
        if not line.strip():
            continue
        event = strict_json(line)
        if not isinstance(event, dict):
            raise ValueError("malformed seed event")
        if event.get("type") == "thread.started":
            ident = event.get("thread_id")
            if not isinstance(ident, str) or not UUID.fullmatch(ident):
                raise ValueError("seed event has invalid native UUID")
            threads.add(ident)
    if len(threads) != 1:
        raise ValueError("seed events do not establish one native UUID")
    return next(iter(threads))


def _same_envelope(value, enrollment):
    return all(value.get(key) == enrollment[key] for key in ("enrollment_id", "cohort_id", "manifest_sha256"))


def validate_binding(path, operation, *, records=None, ic="ic",
                     expected_manifest_sha256=APPROVED_MANIFEST_SHA256,
                     expected_manifest_file_count=APPROVED_MANIFEST_FILES,
                     expected=None):
    if operation not in {"resume", "compact"}:
        raise ValueError("binding validation supports only resume or compact")
    path = Path(path)
    binding_hash = sha256(path)
    value = strict_json(read_regular(path))
    exact_object(value, {"schema_version", "arm_id", "authority", "enrollment", "seed", "source",
                         "policy", "executable", "native_schema", "configuration",
                         "capability_evidence", "compaction"}, "resume binding")
    if value["schema_version"] != 1 or not isinstance(value["arm_id"], str) or not value["arm_id"]:
        raise ValueError("invalid binding schema or arm")
    authority_fields = {"database", "enrollment_decision_id", "dispatch_request_decision_id",
                        "seed_execution_decision_id", "seed_native_binding_decision_id"}
    if operation == "resume":
        authority_fields |= {"compaction_dispatch_request_decision_id", "compaction_execution_decision_id"}
    exact_object(value["authority"], authority_fields, "binding authority")
    exact_object(value["enrollment"], {"enrollment_id", "cohort_id", "manifest_sha256"}, "binding enrollment")
    for key in ("enrollment_id", "cohort_id"):
        if not isinstance(value["enrollment"][key], str) or not value["enrollment"][key]:
            raise ValueError(f"invalid enrollment {key}")
    require_hash(value["enrollment"]["manifest_sha256"], "enrollment manifest")
    exact_object(value["seed"], {"dispatch_id", "attempt_id", "role", "native_thread_id", "receipt", "events"}, "binding seed")
    if not UUID.fullmatch(str(value["seed"]["native_thread_id"])):
        raise ValueError("seed native UUID is invalid")
    source = evidence_ref(value["source"], "source")
    policy = evidence_ref(value["policy"], "policy")
    executable = evidence_ref(value["executable"], "executable", 256 * 1024 * 1024)
    events = evidence_ref(value["seed"]["events"], "seed events")
    receipt = evidence_ref(value["seed"]["receipt"], "seed receipt")
    capability_path = evidence_ref(value["capability_evidence"], "capability")
    exact_object(value["native_schema"], {"manifest_path", "manifest_sha256"}, "native schema pin")
    require_hash(value["native_schema"]["manifest_sha256"], "native schema manifest")
    manifest_path = Path(value["native_schema"]["manifest_path"])
    if not manifest_path.is_absolute() or sha256(manifest_path, 4 * 1024 * 1024) != value["native_schema"]["manifest_sha256"]:
        raise ValueError("native schema manifest evidence mismatch")
    manifest = validate_protocol_manifest(manifest_path, expected_manifest_sha256, expected_manifest_file_count)
    if str(executable) != manifest["codex_executable"] or value["executable"]["sha256"] != manifest["executable_sha256"]:
        raise ValueError("executable differs from native schema manifest")

    config = value["configuration"]
    exact_object(config, {"request", "effective", "sha256"}, "configuration pin")
    require_hash(config["sha256"], "configuration")
    config_input = {"request": config["request"], "effective": config["effective"]}
    if hashlib.sha256(canonical(config_input).encode()).hexdigest() != config["sha256"]:
        raise ValueError("configuration fingerprint mismatch")
    request_allowed = {"model", "modelProvider", "cwd", "runtimeWorkspaceRoots", "approvalPolicy",
                       "approvalsReviewer", "sandbox", "permissions", "serviceTier", "baseInstructions",
                       "developerInstructions", "config", "excludeTurns"}
    request = config["request"]
    if not isinstance(request, dict) or not set(request) <= request_allowed:
        raise ValueError("configuration has unsupported thread/resume override")
    required_request = request_allowed - {"permissions", "sandbox"}
    if not required_request <= set(request) or request.get("excludeTurns") is not True:
        raise ValueError("configuration leaves required resume override unpinned")
    if request.get("history") is not None or request.get("path") is not None or "initialTurnsPage" in request:
        raise ValueError("history/path/initial turns are prohibited")
    if (request.get("sandbox") is None) == (request.get("permissions") is None):
        raise ValueError("sandbox and named permissions cannot be combined")
    if not isinstance(request.get("baseInstructions"), str) or not request["baseInstructions"] or not isinstance(request.get("developerInstructions"), str) or not request["developerInstructions"]:
        raise ValueError("governed and scoped instructions must be pinned")
    effective_fields = {"model", "modelProvider", "reasoningEffort", "serviceTier", "cwd",
                        "runtimeWorkspaceRoots", "approvalPolicy", "approvalsReviewer", "sandbox",
                        "activePermissionProfile", "instructionSources"}
    exact_object(config["effective"], effective_fields, "effective configuration")
    effective = config["effective"]
    roots = request.get("runtimeWorkspaceRoots")
    if (not isinstance(request.get("cwd"), str) or not Path(request["cwd"]).is_absolute() or
            not isinstance(roots, list) or not all(isinstance(root, str) and Path(root).is_absolute() for root in roots) or
            len(roots) != len(set(roots))):
        raise ValueError("configuration cwd/runtime roots are not exact absolute paths")
    if (effective.get("cwd") != request["cwd"] or effective.get("runtimeWorkspaceRoots") != roots or
            effective.get("approvalPolicy") != request.get("approvalPolicy") or
            effective.get("approvalsReviewer") != request.get("approvalsReviewer") or
            effective.get("modelProvider") != request.get("modelProvider") or
            not isinstance(effective.get("instructionSources"), list)):
        raise ValueError("effective configuration differs from requested authority")
    sandbox_types = {"read-only": "readOnly", "workspace-write": "workspaceWrite",
                     "danger-full-access": "dangerFullAccess"}
    sandbox = effective.get("sandbox")
    if (request.get("sandbox") not in sandbox_types or not isinstance(sandbox, dict) or
            sandbox.get("type") != sandbox_types[request["sandbox"]] or
            effective.get("activePermissionProfile") is not None):
        raise ValueError("effective sandbox differs from requested authority")
    overrides = request.get("config")
    allowed_overrides = {"model_reasoning_effort", "service_tier", "sandbox_workspace_write.network_access",
                         "approvals_reviewer", "model_provider"}
    if not isinstance(overrides, dict) or not set(overrides) <= allowed_overrides or any(
            type(item) not in (str, int, bool) or isinstance(item, str) and ("\n" in item or "\r" in item)
            for item in overrides.values()):
        raise ValueError("configuration has unsupported config override")
    if ("sandbox_workspace_write.network_access" in overrides and
            sandbox.get("networkAccess") != overrides["sandbox_workspace_write.network_access"]):
        raise ValueError("effective sandbox network differs from requested authority")

    records = load_records(value["authority"]["database"], ic) if records is None else records
    enrollment = decision(records, value["authority"]["enrollment_decision_id"],
                          "measured-delivery-enrollment", "enrollment")
    requested = decision(records, value["authority"]["dispatch_request_decision_id"],
                         "measured-delivery-dispatch-request", "dispatch request")
    executed = decision(records, value["authority"]["seed_execution_decision_id"],
                        "dispatch-profile", "seed execution")
    native_binding = decision(records, value["authority"]["seed_native_binding_decision_id"],
                              "measured-delivery-binding", "seed native binding")
    ordered_ids = [
        value["authority"]["enrollment_decision_id"],
        value["authority"]["dispatch_request_decision_id"],
        value["authority"]["seed_execution_decision_id"],
        value["authority"]["seed_native_binding_decision_id"],
    ]
    if ordered_ids != sorted(ordered_ids) or len(set(ordered_ids)) != len(ordered_ids):
        raise ValueError("native evidence is not prospectively ordered")
    if not _same_envelope(enrollment, value["enrollment"]) or not _same_envelope(requested, value["enrollment"]):
        raise ValueError("authoritative enrollment or cohort/manifest differs from binding")
    if enrollment.get("implementation_dispatched") is not False or enrollment.get("arm_id") != value["arm_id"]:
        raise ValueError("authoritative prospective enrollment arm mismatch")
    if requested.get("dispatch_id") != value["seed"]["dispatch_id"] or requested.get("role") != value["seed"]["role"]:
        raise ValueError("authoritative seed dispatch request mismatch")
    if not _same_envelope(executed.get("task_envelope", {}), value["enrollment"]):
        raise ValueError("authoritative seed execution envelope mismatch")
    if not _same_envelope(native_binding, value["enrollment"]):
        raise ValueError("authoritative seed native binding envelope mismatch")
    execution = executed.get("execution", {})
    route = executed.get("resolved_route", {})
    normalized_tier = "default" if execution.get("service_tier") == "standard" else execution.get("service_tier")
    if (request.get("model") != execution.get("model") or request.get("modelProvider") != config["effective"].get("modelProvider") or
            config["effective"].get("model") != execution.get("model") or config["effective"].get("reasoningEffort") != execution.get("reasoning_effort") or
            request.get("serviceTier") != normalized_tier or config["effective"].get("serviceTier") != normalized_tier):
        raise ValueError("configuration identity differs from authoritative execution")
    for key, wanted in (("model_reasoning_effort", execution.get("reasoning_effort")),
                        ("service_tier", normalized_tier), ("model_provider", request.get("modelProvider")),
                        ("approvals_reviewer", request.get("approvalsReviewer"))):
        if key in overrides and overrides[key] != wanted:
            raise ValueError("configuration override contradicts pinned settings")
    if operation == "resume" and request.get("permissions") is not None:
        raise ValueError("CLI resume cannot prove named permissions; sandbox pin required")
    if (executed.get("dispatch_id") != value["seed"]["dispatch_id"] or
            executed.get("attempt_id") != value["seed"]["attempt_id"] or
            executed.get("state") != "completed" or executed.get("result", {}).get("exit_code") != 0 or
            execution.get("backend") != "codex" or execution.get("arm_id") != value["arm_id"]):
        raise ValueError("authoritative seed execution is not an eligible completed attempt")
    if canonical(strict_json(read_regular(receipt))) != canonical(executed):
        raise ValueError("seed receipt differs from authoritative execution")
    if seed_thread(events) != value["seed"]["native_thread_id"] or execution.get("event_log") != str(events):
        raise ValueError("seed receipt/events native UUID mismatch")
    if (native_binding.get("arm_id") != value["arm_id"] or native_binding.get("dispatch_id") != value["seed"]["dispatch_id"] or
            native_binding.get("attempt_id") != value["seed"]["attempt_id"] or native_binding.get("role") != value["seed"]["role"] or
            native_binding.get("provider") != "codex" or native_binding.get("thread_id") != value["seed"]["native_thread_id"] or
            native_binding.get("native_thread_id") != value["seed"]["native_thread_id"] or native_binding.get("evidence_path") != str(events)):
        raise ValueError("authoritative seed native binding identity mismatch")
    comparisons = (
        (native_binding.get("source_path"), str(source), "source"),
        (native_binding.get("source_sha256"), value["source"]["sha256"], "source"),
        (native_binding.get("policy_path"), str(policy), "policy"),
        (native_binding.get("policy_sha256"), value["policy"]["sha256"], "policy"),
        (route.get("policy_source"), str(policy), "policy"),
        (route.get("policy_hash"), value["policy"]["sha256"], "policy"),
        (native_binding.get("executable"), str(executable), "executable"),
        (native_binding.get("executable_sha256"), value["executable"]["sha256"], "executable"),
        (native_binding.get("configuration_sha256"), config["sha256"], "configuration"),
    )
    for actual, pinned, label in comparisons:
        if actual != pinned:
            raise ValueError(f"authoritative {label} pin mismatch")
    if native_binding.get("native_schema_manifest") != {"path": str(manifest_path), "sha256": value["native_schema"]["manifest_sha256"]}:
        raise ValueError("authoritative native schema pin mismatch")
    cap_ref = native_binding.get("native_capability_evidence")
    if cap_ref != {"path": str(capability_path), "sha256": value["capability_evidence"]["sha256"], "status": "verified"}:
        raise ValueError("capability evidence is not bound by authoritative execution")
    capability = strict_json(read_regular(capability_path))
    exact_object(capability, {"schema_version", "status", "native_thread_id", "source_sha256", "policy_sha256",
                              "executable_sha256", "configuration_sha256", "native_schema_manifest_sha256",
                              "verified"}, "capability evidence")
    required_proofs = {"model_provider_effort_tier", "cwd_and_writable_roots",
                       "approval_reviewer_sandbox_network", "instructions_config_and_skills",
                       "exclude_turns_suppresses_history"}
    if (capability["schema_version"] != 1 or capability["status"] != "verified" or
            capability["native_thread_id"] != value["seed"]["native_thread_id"] or
            set(capability["verified"]) != required_proofs or
            any(capability["verified"].get(item) is not True for item in required_proofs)):
        raise ValueError("capability evidence lacks required native canary proof")
    for key, pinned in (("source_sha256", value["source"]["sha256"]),
                        ("policy_sha256", value["policy"]["sha256"]),
                        ("executable_sha256", value["executable"]["sha256"]),
                        ("configuration_sha256", config["sha256"]),
                        ("native_schema_manifest_sha256", value["native_schema"]["manifest_sha256"])):
        if capability.get(key) != pinned:
            raise ValueError("capability evidence pin mismatch")

    assert_native_resource_available(records, value["seed"]["native_thread_id"], operation, binding_hash)

    if operation == "compact":
        if value["compaction"] is not None:
            raise ValueError("compact requires an uncompacted seed")
    else:
        compact = value["compaction"]
        exact_object(compact, {"dispatch_id", "attempt_id", "status", "accounting_status",
                               "configuration_status", "receipt", "operation_result"}, "compaction")
        if (compact["status"], compact["accounting_status"], compact["configuration_status"]) != ("completed", "complete", "verified"):
            raise ValueError("dependent resume requires successful accounted compaction")
        compact_receipt = evidence_ref(compact["receipt"], "compaction receipt")
        compact_result_path = evidence_ref(compact["operation_result"], "compaction result")
        compact_request = decision(records, value["authority"]["compaction_dispatch_request_decision_id"],
                                   "measured-delivery-dispatch-request", "compaction dispatch request")
        compact_execution = decision(records, value["authority"]["compaction_execution_decision_id"],
                                     "dispatch-profile", "compaction execution")
        native = compact_execution.get("execution", {}).get("native_operation", {})
        if (compact_request.get("dispatch_id") != compact["dispatch_id"] or
                compact_execution.get("dispatch_id") != compact["dispatch_id"] or
                compact_execution.get("attempt_id") != compact["attempt_id"] or
                compact_execution.get("result", {}).get("exit_code") != 0 or
                canonical(strict_json(read_regular(compact_receipt))) != canonical(compact_execution) or
                canonical(strict_json(read_regular(compact_result_path))) != canonical(native) or
                native.get("operation") != "compact" or native.get("seed_thread_id") != value["seed"]["native_thread_id"] or
                native.get("status") != "completed" or native.get("accounting_status") != "complete" or
                native.get("configuration_status") != "verified" or not isinstance(native.get("native_usage"), dict)):
            raise ValueError("compaction evidence differs from authoritative accounted execution")

    if expected:
        for key in ("role", "model", "reasoning_effort", "service_tier", "cwd", "sandbox",
                    "enrollment_id", "cohort_id", "manifest_sha256"):
            if key in expected:
                actual = value["seed"]["role"] if key == "role" else (
                    execution.get(key) if key in {"model", "reasoning_effort", "service_tier"} else
                    config["request"].get(key) if key in {"cwd", "sandbox"} else value["enrollment"].get(key))
                if actual != expected[key]:
                    raise ValueError(f"binding {key} differs from resolved operation")
    prompt_prefix = request["baseInstructions"] + "\n\n" + request["developerInstructions"]
    return {"schema_version": 1, "operation": operation, "binding_path": str(path.resolve()),
            "binding_sha256": binding_hash, "native_thread_id": value["seed"]["native_thread_id"],
            "role": value["seed"]["role"], "executable": str(executable), "configuration": config,
            "prompt_prefix": prompt_prefix, "seed_attempt_id": value["seed"]["attempt_id"],
            "authoritative_database": value["authority"]["database"],
            "source": value["source"], "policy": value["policy"], "executable_pin": value["executable"],
            "native_schema": value["native_schema"], "capability_evidence": value["capability_evidence"],
            "fixture_only": True, "eligible": False}


def sanitize_rate_limits(value):
    if not isinstance(value, dict):
        raise ControlError("malformed-rate-limits")
    rows = []
    for name, item in sorted(value.items()):
        if not isinstance(item, dict):
            continue
        clean = {"bucket": name}
        for source, target in (("usedPercent", "used_percent"), ("resetsAt", "resets_at"),
                               ("windowDurationMins", "window_minutes")):
            number = item.get(source)
            if number is not None:
                if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                    raise ControlError("malformed-rate-limits")
                clean[target] = number
        rows.append(clean)
    return rows


def validate_usage(value):
    if (not isinstance(value, dict) or not {"last", "total"} <= set(value) or
            not set(value) <= {"last", "total", "modelContextWindow"}):
        raise ControlError("malformed-native-usage")
    required = {"inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens", "totalTokens"}
    result = {}
    for group in ("last", "total"):
        row = value.get(group)
        if (not isinstance(row, dict) or not required <= set(row) or
                not set(row) <= required | {"cacheWriteInputTokens"}):
            raise ControlError("malformed-native-usage")
        clean = {}
        for key in required | {"cacheWriteInputTokens"}:
            number = row.get(key, 0)
            if type(number) is not int or number < 0 or number > INT64_MAX:
                raise ControlError("malformed-native-usage")
            clean[key] = number
        if (clean["cachedInputTokens"] > clean["inputTokens"] or
                clean["cacheWriteInputTokens"] > clean["inputTokens"] or
                clean["reasoningOutputTokens"] > clean["outputTokens"] or
                clean["totalTokens"] != clean["inputTokens"] + clean["outputTokens"]):
            raise ControlError("malformed-native-usage")
        result[group] = clean
    window = value.get("modelContextWindow")
    if window is not None and (type(window) is not int or window < 0):
        raise ControlError("malformed-native-usage")
    for key in required | {"cacheWriteInputTokens"}:
        if result["last"][key] > result["total"][key]:
            raise ControlError("malformed-native-usage")
    result["modelContextWindow"] = window
    return result


class AppServerControl:
    METHODS = frozenset({"initialize", "initialized", "thread/resume", "thread/compact/start"})
    NOTIFICATIONS = frozenset({"turn/started", "item/started", "item/completed", "turn/completed",
                               "thread/tokenUsage/updated", "account/rateLimits/updated", "model/rerouted",
                               "thread/settings/updated", "configWarning", "thread/status/changed", "thread/compacted"})

    def __init__(self, executable, *, handshake_timeout=HANDSHAKE_TIMEOUT,
                 operation_timeout=OPERATION_TIMEOUT, max_frame=MAX_FRAME,
                 transcript_limit=MAX_TRANSCRIPT, original_parent_pid=None):
        self.executable = executable
        self.handshake_timeout = handshake_timeout
        self.operation_timeout = operation_timeout
        self.max_frame = max_frame
        self.transcript_limit = transcript_limit
        self.process = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        self.buffer = bytearray(); self.transcript = []; self.transcript_bytes = 0
        self.stderr_bytes = 0; self.request_id = 0; self.calls = []
        self.compaction_sent = False; self.cancel_signal = None
        self.configuration_verified = False
        self.original_parent_pid = os.getppid() if original_parent_pid is None else original_parent_pid

    def _parent_alive(self):
        if os.getppid() != self.original_parent_pid:
            return False
        try:
            os.kill(self.original_parent_pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def cancel(self, signum, _frame=None):
        self.cancel_signal = signum
        self._terminate()

    def _send(self, value, method=None):
        if method is not None and method not in self.METHODS:
            raise ControlError("client-method-not-allowlisted")
        raw = (canonical(value) + "\n").encode()
        try:
            self.process.stdin.write(raw); self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ControlError("transport-closed") from exc
        if method:
            self.calls.append(method)

    def _line(self, deadline):
        while True:
            if self.cancel_signal is not None:
                raise Cancelled(self.cancel_signal)
            if not self._parent_alive():
                self._terminate()
                raise ControlError("dispatcher-parent-died")
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self.buffer[:newline]); del self.buffer[:newline + 1]
                if len(raw) > self.max_frame:
                    raise ControlError("oversized-frame")
                return raw
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ControlError("timeout")
            ready = self.selector.select(min(remaining, 0.1))
            if not ready:
                if time.monotonic() >= deadline:
                    raise ControlError("timeout")
                continue
            for key, _ in ready:
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    if key.data == "stdout":
                        if self.cancel_signal is not None:
                            raise Cancelled(self.cancel_signal)
                        raise ControlError("transport-closed")
                    self.selector.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    self.stderr_bytes += len(chunk)
                    if self.stderr_bytes > self.max_frame:
                        raise ControlError("oversized-stderr")
                else:
                    self.buffer.extend(chunk)
                    if len(self.buffer) > self.max_frame and b"\n" not in self.buffer:
                        raise ControlError("oversized-frame")

    def _record(self, value):
        raw = canonical(value).encode()
        self.transcript_bytes += len(raw) + 1
        if self.transcript_bytes > self.transcript_limit:
            raise ControlError("oversized-sanitized-transcript")
        self.transcript.append(value)

    def _receive(self, deadline, outstanding=None):
        raw = self._line(deadline)
        try:
            value = strict_json(raw)
        except ValueError as exc:
            raise ControlError("malformed-frame") from exc
        if not isinstance(value, dict):
            raise ControlError("malformed-frame")
        if "method" in value and "id" in value:
            method = value.get("method")
            # JSON-RPC error responses are not client methods and grant no action.
            self._send({"id": value.get("id"), "error": {"code": -32601, "message": "client refuses all server requests"}})
            reason = "auth-refresh-request" if method == "account/chatgptAuthTokens/refresh" else "server-request"
            self._record({"kind": "server_request_refused", "method": method if isinstance(method, str) else None})
            raise ControlError(reason)
        if "id" in value:
            if outstanding is None or value.get("id") != outstanding or set(value) - {"id", "result", "error"}:
                raise ControlError("unexpected-jsonrpc-response")
            if "error" in value or "result" not in value:
                raise ControlError("jsonrpc-error-response")
            self._record({"kind": "response", "id": outstanding, "status": "ok"})
            return "response", value["result"]
        method = value.get("method")
        if not isinstance(method, str) or set(value) - {"method", "params"} or method not in self.NOTIFICATIONS:
            raise ControlError("unknown-notification")
        params = value.get("params")
        if not isinstance(params, dict):
            raise ControlError("malformed-notification")
        return "notification", (method, params)

    def request(self, method, params, timeout, notification_handler=None):
        if method not in self.METHODS or method == "initialized":
            raise ControlError("client-method-not-allowlisted")
        self.request_id += 1; ident = self.request_id
        self._send({"id": ident, "method": method, "params": params}, method)
        deadline = time.monotonic() + timeout
        while True:
            kind, value = self._receive(deadline, ident)
            if kind == "response":
                return value
            if notification_handler is None:
                raise ControlError("unexpected-notification")
            notification_handler(*value)

    def initialize(self):
        self.request("initialize", {"clientInfo": {"name": "clavain_dispatch_control", "version": "1"}}, self.handshake_timeout)
        self._send({"method": "initialized"}, "initialized")

    @staticmethod
    def _validate_effective(result, thread_id, expected):
        if not isinstance(result, dict) or not isinstance(result.get("thread"), dict):
            raise ControlError("malformed-resume-response")
        thread = result["thread"]
        if thread.get("id") != thread_id:
            raise ControlError("resume-thread-mismatch")
        if thread.get("turns") not in (None, []):
            raise ControlError("hydrated-history")
        for key, pinned in expected.items():
            if result.get(key) != pinned:
                raise ControlError("effective-settings-diff")
        return {key: result.get(key) for key in expected}

    @staticmethod
    def _turn(params, thread_id):
        turn = params.get("turn")
        if params.get("threadId") != thread_id or not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
            raise ControlError("lifecycle-identity")
        return turn

    def _compact_notification(self, method, params, state, thread_id, effective_config):
        if state["done"]:
            raise ControlError("lifecycle-after-terminal")
        if method == "model/rerouted":
            self.configuration_verified = False
            raise ControlError("model-rerouted")
        if method == "configWarning":
            self.configuration_verified = False
            raise ControlError("config-warning")
        if method == "turn/started":
            if state["phase"] != 0:
                raise ControlError("lifecycle-order")
            turn = self._turn(params, thread_id)
            if turn.get("status") != "inProgress":
                raise ControlError("lifecycle-status")
            state["turn_id"] = turn["id"]; state["phase"] = 1
            self._record({"kind": method, "thread_id": thread_id, "turn_id": state["turn_id"]})
        elif method in {"item/started", "item/completed"}:
            expected_phase = 1 if method == "item/started" else 2
            if (state["phase"] != expected_phase or params.get("threadId") != thread_id or
                    params.get("turnId") != state["turn_id"]):
                raise ControlError("lifecycle-order")
            lifecycle_item = params.get("item")
            if (not isinstance(lifecycle_item, dict) or lifecycle_item.get("type") != "contextCompaction" or
                    not isinstance(lifecycle_item.get("id"), str)):
                raise ControlError("lifecycle-item-mismatch")
            if state["item_id"] is None:
                state["item_id"] = lifecycle_item["id"]
            if lifecycle_item["id"] != state["item_id"]:
                raise ControlError("lifecycle-item-mismatch")
            state["phase"] += 1
            self._record({"kind": method, "thread_id": thread_id, "turn_id": state["turn_id"],
                          "item_id": state["item_id"]})
        elif method == "thread/tokenUsage/updated":
            if state["phase"] < 1 or params.get("threadId") != thread_id or params.get("turnId") != state["turn_id"]:
                raise ControlError("native-usage-identity")
            observed = validate_usage(params.get("tokenUsage"))
            if state["usage"] is not None and canonical(state["usage"]) == canonical(observed):
                raise ControlError("duplicate-native-usage")
            state["usage"] = observed
            self._record({"kind": method, "thread_id": thread_id, "turn_id": state["turn_id"], "usage": observed})
        elif method == "account/rateLimits/updated":
            clean = sanitize_rate_limits(params.get("rateLimits"))
            state["observations"].append({"kind": "rate_limits", "attribution": "unattributed", "rate_limits": clean})
            self._record({"kind": method, "status": "sanitized"})
        elif method == "thread/settings/updated":
            if params.get("threadId") != thread_id or not isinstance(params.get("threadSettings"), dict):
                raise ControlError("settings-identity")
            settings = params["threadSettings"]
            mapping = {"model": "model", "modelProvider": "modelProvider", "effort": "reasoningEffort",
                       "serviceTier": "serviceTier", "cwd": "cwd", "approvalPolicy": "approvalPolicy",
                       "approvalsReviewer": "approvalsReviewer", "sandboxPolicy": "sandbox",
                       "activePermissionProfile": "activePermissionProfile"}
            for source, target in mapping.items():
                if source not in settings or settings[source] != effective_config[target]:
                    self.configuration_verified = False
                    raise ControlError("effective-settings-diff")
            self._record({"kind": method, "thread_id": thread_id, "status": "matching"})
        elif method == "thread/status/changed":
            status_value = params.get("status")
            if (params.get("threadId") != thread_id or not isinstance(status_value, dict) or
                    status_value.get("type") not in {"active", "idle"} or
                    (status_value.get("type") == "active" and status_value.get("activeFlags") != [])):
                raise ControlError("status-identity")
            state["statuses"].append(status_value)
            self._record({"kind": method, "thread_id": thread_id, "status": status_value})
        elif method == "thread/compacted":
            if state["phase"] != 3 or params.get("threadId") != thread_id or params.get("turnId") != state["turn_id"]:
                raise ControlError("deprecated-compacted-mismatch")
            state["deprecated"] = True
            self._record({"kind": method, "thread_id": thread_id, "turn_id": state["turn_id"]})
        elif method == "turn/completed":
            if state["phase"] != 3:
                raise ControlError("lifecycle-order")
            turn = self._turn(params, thread_id)
            if turn["id"] != state["turn_id"] or turn.get("status") != "completed":
                raise ControlError("terminal-turn-failed")
            items = turn.get("items")
            if (not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict) or
                    items[0].get("id") != state["item_id"] or items[0].get("type") != "contextCompaction"):
                raise ControlError("terminal-item-mismatch")
            state["phase"] = 4; state["done"] = True
            self._record({"kind": method, "thread_id": thread_id, "turn_id": state["turn_id"]})
        else:
            raise ControlError("unknown-notification")

    def compact(self, thread_id, request_config, effective_config):
        if not UUID.fullmatch(thread_id):
            raise ControlError("invalid-seed-uuid")
        self.initialize()
        params = dict(request_config)
        if set(params) & {"threadId", "history", "path", "initialTurnsPage"}:
            raise ControlError("forbidden-resume-override")
        if params.get("excludeTurns") is not True:
            raise ControlError("exclude-turns-not-pinned")
        params["threadId"] = thread_id
        resumed = self.request("thread/resume", params, self.handshake_timeout)
        actual = self._validate_effective(resumed, thread_id, effective_config)
        self.configuration_verified = True
        state = {"turn_id": None, "item_id": None, "phase": 0, "usage": None,
                 "observations": [], "statuses": [], "deprecated": False, "done": False}
        consume = lambda method, params: self._compact_notification(method, params, state, thread_id, effective_config)
        self.compaction_sent = True
        acknowledgment = self.request("thread/compact/start", {"threadId": thread_id}, self.handshake_timeout,
                                      notification_handler=consume)
        if acknowledgment != {}:
            raise ControlError("malformed-compaction-ack")
        deadline = time.monotonic() + self.operation_timeout
        while not state["done"]:
            kind, item = self._receive(deadline)
            if kind != "notification":
                raise ControlError("unexpected-jsonrpc-response")
            consume(*item)
        if state["usage"] is None:
            raise ControlError("missing-native-usage", remote_completion="completed")
        return {"schema_version": 1, "operation": "compact", "status": "completed",
                "fixture_only": True, "eligible": False,
                "configuration_status": "verified", "accounting_status": "complete",
                "remote_completion": "completed", "seed_thread_id": thread_id,
                "turn_id": state["turn_id"], "item_id": state["item_id"], "effective_configuration": actual,
                "native_usage": state["usage"], "account_observations": state["observations"],
                "thread_statuses": state["statuses"], "deprecated_compacted_observed": state["deprecated"],
                "calls": list(self.calls), "sanitized_transcript": list(self.transcript)}

    def _terminate(self):
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=1)

    def close(self):
        self._terminate()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        self.selector.close()
        return {"process_exit_code": self.process.returncode, "reaped": self.process.poll() is not None,
                "stderr_bytes_discarded": self.stderr_bytes, "calls": list(self.calls)}


def validate_resume_events(binding, events):
    bound = strict_json(read_regular(binding))
    expected = bound.get("seed", {}).get("native_thread_id")
    observed = seed_thread(events)
    if observed != expected:
        raise ValueError("resumed native UUID differs from bound seed")
    return {"native_thread_id": observed, "events_sha256": sha256(events)}


def seal_resume(binding, events, output, artifact_dir, process_code):
    identity = validate_resume_events(binding, events)
    artifact_dir = Path(artifact_dir)
    if not artifact_dir.is_dir() or artifact_dir.is_symlink():
        raise ValueError("resume artifact directory is not a private directory")
    if stat.S_IMODE(artifact_dir.stat().st_mode) != 0o700:
        raise ValueError("resume artifact directory must have mode 0700")
    bound = strict_json(read_regular(binding))
    result = {
        "schema_version": 1,
        "operation": "resume",
        "fixture_only": True,
        "eligible": False,
        "status": "completed" if process_code == 0 else "failed",
        "remote_completion": "completed" if process_code == 0 else "unknown",
        "control_result_is_approval": False,
        "control_result_is_last_message_verdict": False,
        "binding_path": str(Path(binding).resolve()),
        "binding_sha256": sha256(binding),
        "seed_attempt_id": bound["seed"]["attempt_id"],
        "native_thread_id": identity["native_thread_id"],
        "events_sha256": identity["events_sha256"],
        "process": {"process_exit_code": process_code},
    }
    result_path = artifact_dir / "operation-result.json"
    write_private(result_path, result)
    artifacts = []
    for logical_name, path in (("binding", binding), ("events", events), ("last_message", output),
                               ("operation_result", result_path)):
        candidate = Path(path)
        if candidate.is_file() and not candidate.is_symlink():
            artifacts.append({"logical_name": logical_name, "path": str(candidate.resolve()),
                              "size": candidate.stat().st_size, "sha256": sha256(candidate)})
        else:
            artifacts.append({"logical_name": logical_name, "path": str(candidate),
                              "size": None, "sha256": None, "status": "unavailable"})
    manifest = {"schema_version": 1, "operation": "resume", "fixture_only": True,
                "eligible": False, "artifacts": artifacts}
    manifest_path = artifact_dir / "manifest.json"
    write_private(manifest_path, manifest)
    return {"operation_result": str(result_path), "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path)}


def write_private(path, value):
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(payload) > MAX_TRANSCRIPT:
        raise ValueError("sanitized operation result exceeds 16 MiB")
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-binding", allow_abbrev=False)
    validate.add_argument("--binding", required=True); validate.add_argument("--operation", required=True, choices=("resume", "compact"))
    validate.add_argument("--ic", default="ic"); validate.add_argument("--expected", default="{}")
    compact = commands.add_parser("compact", allow_abbrev=False)
    compact.add_argument("--binding", required=True); compact.add_argument("--output", required=True); compact.add_argument("--ic", default="ic")
    compact.add_argument("--handshake-timeout", type=float, default=HANDSHAKE_TIMEOUT)
    compact.add_argument("--operation-timeout", type=float, default=OPERATION_TIMEOUT)
    resume_events = commands.add_parser("validate-resume-events", allow_abbrev=False)
    resume_events.add_argument("--binding", required=True); resume_events.add_argument("--events", required=True)
    seal = commands.add_parser("seal-resume", allow_abbrev=False)
    seal.add_argument("--binding", required=True); seal.add_argument("--events", required=True)
    seal.add_argument("--output", required=True); seal.add_argument("--artifact-dir", required=True)
    seal.add_argument("--process-code", required=True, type=int)
    args = parser.parse_args()
    try:
        if args.command == "compact":
            parser.exit(2, "dispatch-control: native-trusted-launcher-unavailable\n")
        if args.command == "validate-binding":
            result = validate_binding(args.binding, args.operation, ic=args.ic, expected=strict_json(args.expected.encode()))
            print(canonical(result)); return 0
        if args.command == "validate-resume-events":
            print(canonical(validate_resume_events(args.binding, args.events))); return 0
        if args.command == "seal-resume":
            print(canonical(seal_resume(args.binding, args.events, args.output, args.artifact_dir, args.process_code))); return 0
        if not (0 < args.handshake_timeout <= HANDSHAKE_TIMEOUT and 0 < args.operation_timeout <= OPERATION_TIMEOUT):
            raise ValueError("control deadlines exceed approved bounds")
        admitted = validate_binding(args.binding, "compact", ic=args.ic)
        try:
            control = AppServerControl(admitted["executable"], handshake_timeout=args.handshake_timeout,
                                       operation_timeout=args.operation_timeout)
        except OSError:
            write_private(args.output, {
                "schema_version": 1, "operation": "compact", "status": "failed",
                "failure": "transport-start-failed", "remote_completion": "not-started",
                "binding_path": admitted["binding_path"],
                "binding_sha256": admitted["binding_sha256"],
                "seed_attempt_id": admitted["seed_attempt_id"],
                "accounting_status": "missing", "configuration_status": "unknown",
                "control_result_is_approval": False,
                "control_result_is_last_message_verdict": False,
                "process": {"process_exit_code": None, "reaped": True,
                            "stderr_bytes_discarded": 0, "calls": []},
            })
            return 1
        previous = {}
        for item in (signal.SIGINT, signal.SIGTERM):
            previous[item] = signal.signal(item, control.cancel)
        result = None; code = 1
        try:
            result = control.compact(admitted["native_thread_id"], admitted["configuration"]["request"],
                                     admitted["configuration"]["effective"])
            result.update(binding_path=admitted["binding_path"], binding_sha256=admitted["binding_sha256"],
                          seed_attempt_id=admitted["seed_attempt_id"],
                          control_result_is_approval=False,
                          control_result_is_last_message_verdict=False)
            code = 0
        except Cancelled as exc:
            result = {"schema_version": 1, "operation": "compact", "status": "cancelled",
                      "failure": exc.reason, "remote_completion": "unknown",
                      "binding_path": admitted["binding_path"],
                      "binding_sha256": admitted["binding_sha256"],
                      "seed_attempt_id": admitted["seed_attempt_id"],
                      "accounting_status": "missing",
                      "configuration_status": "verified" if control.configuration_verified else "unknown",
                      "control_result_is_approval": False,
                      "control_result_is_last_message_verdict": False}
            code = 128 + exc.signum
        except ControlError as exc:
            result = {"schema_version": 1, "operation": "compact", "status": "failed",
                      "failure": exc.reason, "remote_completion": exc.remote_completion,
                      "binding_path": admitted["binding_path"],
                      "binding_sha256": admitted["binding_sha256"],
                      "seed_attempt_id": admitted["seed_attempt_id"],
                      "accounting_status": "missing",
                      "configuration_status": "verified" if control.configuration_verified else "invalid",
                      "control_result_is_approval": False,
                      "control_result_is_last_message_verdict": False}
        finally:
            process = control.close(); result["process"] = process
            for item, handler in previous.items(): signal.signal(item, handler)
        write_private(args.output, result)
        return code
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"dispatch-control: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
