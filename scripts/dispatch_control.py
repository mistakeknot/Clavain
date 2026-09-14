#!/usr/bin/env python3
"""Fail-closed admission and App Server control for governed Codex operations.

This adapter never starts a turn and never accepts a caller-supplied thread ID.
The only eligible ID is recovered from a seed event artifact whose receipt is
also present in the authoritative Intercore decision log.
"""
from __future__ import annotations

import argparse
import datetime as dt
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
    def __init__(self, reason, *, remote_completion="unknown", failure_class=None, phase="protocol"):
        super().__init__(reason)
        self.reason = reason
        self.remote_completion = remote_completion
        self.failure_class = failure_class or {
            "auth-refresh-request": "operational_auth", "server-request": "operational_permissions",
            "model-rerouted": "terminal_configuration", "config-warning": "terminal_configuration",
            "effective-settings-diff": "terminal_configuration", "timeout": "operational_timeout",
            "transport-closed": "operational_infrastructure", "dispatcher-parent-died": "operational_cancelled",
            "cancelled": "operational_cancelled", "missing-native-usage": "terminal_accounting",
            "malformed-native-usage": "terminal_accounting", "budget-overrun": "terminal_accounting",
        }.get(reason, "terminal_protocol")
        self.phase = phase


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
    if deadline is not None:
        os.set_blocking(descriptor, False)
    view = memoryview(payload)
    while view:
        if deadline is not None and time.monotonic() >= deadline:
            raise ValueError("bounded write deadline exceeded")
        if deadline is not None:
            _fd_ready(descriptor, selectors.EVENT_WRITE, deadline)
        try:
            count = os.write(descriptor, view)
        except BlockingIOError:
            continue
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


def _read_exact(descriptor, count, deadline, cancel_check=None):
    os.set_blocking(descriptor, False)
    chunks = []
    remaining = count
    while remaining:
        if time.monotonic() >= deadline:
            raise ValueError("handoff read deadline exceeded")
        _fd_ready(descriptor, selectors.EVENT_READ, deadline, cancel_check)
        try:
            chunk = os.read(descriptor, remaining)
        except BlockingIOError:
            continue
        if not chunk:
            raise ValueError("truncated or consumed handoff")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _fd_ready(descriptor, event, deadline, cancel_check=None):
    with selectors.DefaultSelector() as selector:
        selector.register(descriptor, event)
        while True:
            if cancel_check: cancel_check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("handoff I/O deadline exceeded")
            if selector.select(min(remaining, .05)):
                return


def read_framed_handoff(descriptor, *, deadline_seconds=HANDSHAKE_TIMEOUT, cancel_check=None):
    deadline = time.monotonic() + deadline_seconds
    header = _read_exact(descriptor, HANDOFF_HEADER.size, deadline, cancel_check)
    magic, size, expected = HANDOFF_HEADER.unpack(header)
    if magic != HANDOFF_MAGIC or size > MAX_FRAME:
        raise ValueError("invalid or oversized handoff")
    payload = _read_exact(descriptor, size, deadline, cancel_check)
    if hashlib.sha256(payload).digest() != expected:
        raise ValueError("handoff digest mismatch")
    _fd_ready(descriptor, selectors.EVENT_READ, deadline, cancel_check)
    if os.read(descriptor, 1):
        raise ValueError("handoff has trailing bytes")
    value = strict_json(payload)
    if not isinstance(value, dict):
        raise ValueError("handoff must be an object")
    return value


def _owned_group_exited_only(text, pgid):
    seen = set()
    members = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 3 or not all(re.fullmatch(r"[0-9]+", x) for x in fields[:2]):
            return False
        pid, group = map(int, fields[:2])
        if pid <= 0 or group < 0 or pid in seen or not re.fullmatch(r"[A-Za-z?][A-Za-z+<>-]*", fields[2]):
            return False
        seen.add(pid)
        if group == pgid:
            members.append((pid, fields[2]))
    return (any(pid == pgid for pid, _ in members)
            and all(state.startswith("Z") for _, state in members))


def _observe_owned_group_exited(process, deadline):
    if sys.platform != "darwin" or process.returncode is not None:
        return False
    query_deadline = min(deadline, time.monotonic() + .5)
    if query_deadline <= time.monotonic():
        return False
    query = None
    try:
        query = subprocess.Popen(
            ["/bin/ps", "-A", "-o", "pid=,pgid=,stat="],
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True,
        )
        outputs = {query.stdout: bytearray(), query.stderr: bytearray()}
        with selectors.DefaultSelector() as selector:
            for stream in outputs:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = query_deadline - time.monotonic()
                if remaining <= 0:
                    return False
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    outputs[key.fileobj].extend(chunk)
                    if sum(map(len, outputs.values())) > 1024 * 1024:
                        return False
        code = query.wait(timeout=max(0, query_deadline - time.monotonic()))
        if code or outputs[query.stderr] or process.returncode is not None:
            return False
        return _owned_group_exited_only(outputs[query.stdout].decode("ascii"), process.pid)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return False
    finally:
        if query is not None:
            if query.poll() is None:
                query.kill()
                try:
                    query.wait(timeout=max(.01, min(.1, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
            query.stdout.close()
            query.stderr.close()


def _terminate_group(process, deadline):
    kill_at = deadline - 1.0
    # Do not reap the leader until the final group signal: its unreaped PID
    # pins the owned group identity even when descendants close every pipe.
    # An observation failure must not prevent the remaining bounded cleanup.
    failure = None
    def send(signum):
        nonlocal failure
        try: os.killpg(process.pid, signum)
        except ProcessLookupError: return False
        except PermissionError as exc:
            if failure is None and _observe_owned_group_exited(process, deadline):
                return False
            failure = failure or exc
        except OSError as exc: failure = failure or exc
        return True
    live = send(signal.SIGTERM)
    while time.monotonic() < kill_at:
        if not live or not send(0): break
        time.sleep(min(.01, max(0, kill_at-time.monotonic())))
    send(signal.SIGKILL)
    remaining = max(0.0, deadline - time.monotonic())
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("owned fixture process group was not reaped") from exc
    if failure is not None: raise failure


def _native_child_signal_mask():
    # This supervisor is single-threaded. The registration mask belongs only
    # to it; an exec child must not inherit blocked INT/TERM.
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT, signal.SIGTERM})




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
    request_fields = {"model", "modelProvider", "cwd", "runtimeWorkspaceRoots", "approvalPolicy", "approvalsReviewer", "sandbox", "serviceTier", "baseInstructions", "developerInstructions", "config", "excludeTurns"}
    exact_object(request, request_fields, "resume configuration")
    allowed = {"model_reasoning_effort", "service_tier", "sandbox_workspace_write.network_access",
               "approvals_reviewer", "model_provider"}
    if not isinstance(request.get("config"), dict) or not set(request["config"]) <= allowed:
        raise ValueError("configuration has unsupported config override")
    if set(request) & {"history", "path", "initialTurnsPage", "threadId", "permissions"}:
        raise ValueError("configuration has unsupported resume override")
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


def read_evidence(value, label, limit=MAX_TRANSCRIPT):
    """Hash and consume the same safely opened sealed artifact bytes."""
    exact_object(value,{"path","sha256"},label)
    if not isinstance(value["path"],str) or not Path(value["path"]).is_absolute():
        raise ValueError(label+" path must be absolute")
    require_hash(value["sha256"],label)
    raw=read_regular(value["path"],limit,reject_hardlinks=True)
    if hashlib.sha256(raw).hexdigest()!=value["sha256"]:
        raise ValueError(label+" evidence hash mismatch")
    return raw


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


def _native_record_resource(record, records=()):
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
        elif candidate is not None:
            raise ValueError("malformed native resource evidence")
    resources = set()
    for candidate in candidates:
        operation = candidate.get("operation")
        thread_id = candidate.get("seed_thread_id", candidate.get("native_thread_id"))
        if candidate.get("provider", "codex") != "codex": raise ValueError("conflicting native provider provenance")
        if operation in {"compact", "resume"} and isinstance(thread_id, str) and UUID.fullmatch(thread_id):
            resources.add(("codex", thread_id.lower(), operation))
        elif candidate.get("schema_version") == 2 and "admission_decision_id" in candidate:
            parent = next((r for r in records if r["id"] == candidate["admission_decision_id"]), None)
            if parent is None or parent["id"] >= record["id"]:
                raise ValueError("native envelope has ambiguous admission mapping")
            resources.add(_native_record_resource(parent, records))
        else:
            # Legacy rows can identify a seed via its authoritative binding. A
            # missing, multiply mapped, or invalid UUID poisons admission.
            matches = {context(r).get("native_thread_id", context(r).get("thread_id")) for r in records
                       if r.get("rule_matched") == "measured-delivery-binding" and
                       context(r).get("dispatch_id") == candidate.get("seed_dispatch_id") and
                       context(r).get("attempt_id") == candidate.get("seed_attempt_id")}
            if len(matches) != 1 or not UUID.fullmatch(str(next(iter(matches), None))) or operation not in {"compact", "resume"}:
                raise ValueError("ambiguous legacy native resource evidence")
            resources.add(("codex", next(iter(matches)).lower(), operation))
        if candidate.get("operation_key") is not None:
            expected = native_operation_key(thread_id, operation, candidate.get("provider", "codex"))
            if candidate["operation_key"] != expected:
                raise ValueError("forged native operation key")
    if len(resources) > 1:
        raise ValueError("authoritative native record has ambiguous resource mapping")
    return next(iter(resources), None)


def assert_native_resource_available(records, native_thread_id, operation, binding_sha256=None):
    target = ("codex", native_thread_id.lower(), operation)
    target_key = native_operation_key(native_thread_id, operation)
    for row in records:
        resource = _native_record_resource(row, records)
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
    provenance = set()
    target = None
    for row in records:
        if row.get("id") == reservation_decision_id:
            target = _native_record_resource(row, records)
    if target is None or native_operation_key(target[1], target[2], target[0]) != operation_key:
        raise ValueError("reservation key differs from authoritative resource")
    seen = set()
    for row in records:
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] in seen:
            raise ValueError("authoritative decision export has malformed or duplicate IDs")
        seen.add(row["id"])
        execution = context(row).get("execution", {})
        resource = _native_record_resource(row, records)
        if resource != target:
            continue
        admission = execution.get("native_admission", {}) if isinstance(execution, dict) else {}
        if isinstance(admission, dict) and admission.get("operation_key") == operation_key:
            if admission.get("fixture_only") is not True or admission.get("eligible") is not False:
                raise ValueError("fixture reservation lacks ineligible provenance")
            ids.append(row["id"])
            provenance.add((admission.get("seed_dispatch_id"), admission.get("seed_attempt_id")))
        elif row["id"] < reservation_decision_id:
            raise ValueError("native resource consumed by earlier legacy evidence")
        elif isinstance(execution.get("native_operation"), dict) and execution["native_operation"].get("admission_decision_id") == reservation_decision_id:
            raise ValueError("native continuation already terminal")
    if len(provenance) > 1:
        raise ValueError("conflicting native seed provenance poisons resource")
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
                maximum = budget.get("max_allocation_tokens", scope_limit_tokens)
                if (type(maximum) is not int or not 0 < maximum <= scope_limit_tokens or
                        type(allocation) is not int or not 0 < allocation <= maximum):
                    raise ValueError("native budget allocation must be a positive int64")
                admissions[row["id"]] = allocation
        intent = execution.get("native_send_intent")
        if isinstance(intent, dict) and type(intent.get("admission_decision_id")) is int:
            send_intents.add(intent["admission_decision_id"])
        terminal = execution.get("native_operation")
        if isinstance(terminal, dict) and type(terminal.get("admission_decision_id")) is int:
            ident = terminal["admission_decision_id"]
            if ident in terminals:
                raise ValueError("conflicting native terminal evidence")
            terminals[ident] = read_operation_envelope(terminal) if terminal.get("schema_version") == 2 else terminal
    if reservation_decision_id not in admissions:
        raise ValueError("native budget reservation is absent")
    debit = 0
    details = []
    for ident, allocation in sorted(admissions.items()):
        terminal = terminals.get(ident)
        if terminal is None:
            if ident in send_intents and ident != reservation_decision_id:
                raise ValueError("native budget blocked by unknown possible spending")
            charged = allocation
            status = "reserved"
        elif terminal.get("native_launched") is False and terminal.get("remote_completion") == "not-started" and ident not in send_intents:
            charged = 0
            status = "not-launched"
        elif terminal.get("accounting_status") == "complete":
            charged = attributable_tokens(terminal)
            if charged > allocation:
                raise ValueError("native budget overrun blocks scope")
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
    binding_raw = read_regular(path, reject_hardlinks=True)
    binding_hash = hashlib.sha256(binding_raw).hexdigest()
    value = strict_json(binding_raw)
    fixture_fields = {"fixture_only", "eligible"} if "fixture_only" in value else set()
    if fixture_fields and (value.get("fixture_only") is not True or value.get("eligible") is not False): raise ValueError("fixture binding is permanently ineligible")
    exact_object(value, {"schema_version", "arm_id", "authority", "enrollment", "seed", "source",
                         "policy", "executable", "native_schema", "configuration",
                         "capability_evidence", "compaction"} | fixture_fields, "resume binding")
    if type(value["schema_version"]) is not int or value["schema_version"] not in {1, 2} or not isinstance(value["arm_id"], str) or not value["arm_id"]:
        raise ValueError("invalid binding schema or arm")
    authority_fields = {"database", "enrollment_decision_id", "dispatch_request_decision_id",
                        "seed_execution_decision_id", "seed_native_binding_decision_id"}
    if value["schema_version"] == 2:
        authority_fields.add("seed_started_decision_id")
    if operation == "resume":
        authority_fields |= {"compaction_dispatch_request_decision_id", "compaction_execution_decision_id"}
        if value["schema_version"] == 2:
            authority_fields |= {"compaction_admission_decision_id", "compaction_send_intent_decision_id", "compaction_result_binding_decision_id"}
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
    for record in records:
        if record.get("rule_matched") == "measured-delivery-binding":
            other = context(record)
            native_id = other.get("native_thread_id", other.get("thread_id"))
            if isinstance(native_id,str) and native_id.lower() == value["seed"]["native_thread_id"].lower() and (
                    other.get("dispatch_id"),other.get("attempt_id")) != (value["seed"]["dispatch_id"],value["seed"]["attempt_id"]):
                raise ValueError("conflicting native seed provenance poisons resource")
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
    if value["schema_version"] == 2:
        start_id = value["authority"]["seed_started_decision_id"]
        started = decision(records, start_id, "dispatch-profile", "prospective seed started")
        ordered_ids.insert(2, start_id)
        if started.get("state") != "started" or started.get("terminal") is True:
            raise ValueError("prospective seed started state mismatch")
        for key in ("dispatch_id", "attempt_id", "resolved_route", "resolved_profile", "task_envelope"):
            if started.get(key) != executed.get(key): raise ValueError("prospective seed started provenance mismatch")
        for key in ("backend", "model", "reasoning_effort", "service_tier", "executable", "executable_sha256",
                    "configuration_sha256", "source_path", "source_sha256", "native_schema_manifest", "arm_id"):
            if started.get("execution", {}).get(key) != executed.get("execution", {}).get(key):
                raise ValueError("prospective seed started execution pin mismatch")
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
        native_result = read_operation_envelope(native)
        if (compact_request.get("dispatch_id") != compact["dispatch_id"] or
                compact_execution.get("dispatch_id") != compact["dispatch_id"] or
                compact_execution.get("attempt_id") != compact["attempt_id"] or
                compact_execution.get("result", {}).get("exit_code") != 0 or
                canonical(strict_json(read_regular(compact_receipt))) != canonical(compact_execution) or
                canonical(strict_json(read_regular(compact_result_path))) != canonical(native_result) or
                native["operation_result"] != compact["operation_result"] or
                native_result.get("operation") != "compact" or native_result.get("seed_thread_id") != value["seed"]["native_thread_id"] or
                native_result.get("status") != "completed" or native_result.get("accounting_status") != "complete" or
                native_result.get("configuration_status") != "verified" or not isinstance(native_result.get("native_usage"), dict)):
            raise ValueError("compaction evidence differs from authoritative accounted execution")
        for field, expected_value in (("seed_dispatch_id", value["seed"]["dispatch_id"]), ("seed_attempt_id", value["seed"]["attempt_id"]),
            ("source_sha256", value["source"]["sha256"]), ("policy_sha256", value["policy"]["sha256"]),
            ("executable_sha256", value["executable"]["sha256"]), ("configuration_sha256", config["sha256"]),
            ("schema_manifest_sha256", value["native_schema"]["manifest_sha256"])):
            if native_result[field] != expected_value: raise ValueError("compaction chain pin mismatch")
        if value["schema_version"] == 2:
            authority = value["authority"]
            admission_id = authority["compaction_admission_decision_id"]
            admitted = decision(records, admission_id, "dispatch-profile", "compaction started").get("execution", {}).get("native_admission")
            sent = decision(records, authority["compaction_send_intent_decision_id"], "dispatch-profile", "compaction send intent").get("execution", {}).get("native_send_intent")
            bound_result = decision(records, authority["compaction_result_binding_decision_id"], "native-fixture-result-binding", "compaction result binding")
            order = ordered_ids + [authority[k] for k in ("compaction_dispatch_request_decision_id", "compaction_admission_decision_id",
                "compaction_send_intent_decision_id", "compaction_execution_decision_id", "compaction_result_binding_decision_id")]
            if order != sorted(set(order)) or native_result["admission_decision_id"] != admission_id:
                raise ValueError("compaction result binding is not prospectively ordered")
            if not isinstance(admitted,dict) or not isinstance(sent,dict) or sent.get("admission_decision_id") != admission_id:
                raise ValueError("compaction admission/send evidence mismatch")
            expected_binding = {"schema_version":2,"fixture_only":True,"eligible":False,"terminal_decision_id":authority["compaction_execution_decision_id"],
                "request_decision_id":authority["compaction_dispatch_request_decision_id"],"native_operation":native}
            if bound_result != expected_binding: raise ValueError("compaction result binding differs from authoritative envelope")
            if compact_execution.get("state") != "completed" or not compact_execution.get("terminal"):
                raise ValueError("compaction terminal state mismatch")
            for field in ("dispatch_id","attempt_id","seed_dispatch_id","seed_attempt_id","seed_thread_id","binding_sha256","resolved_route_sha256","database_identity"):
                if admitted.get(field) != native_result[field]: raise ValueError("compaction admission/result pin mismatch")
            if compact_execution.get("resolved_route") != route or native_result["effective_configuration"] != config["effective"]:
                raise ValueError("compaction route/configuration differs from seed")

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
    for name in ("primary", "secondary"):
        item = value.get(name)
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


class NativeSchemas:
    """Complete consumed 0.154.0 schemas, then local privacy/state constraints.

    These inputs are generated locally by the pinned CLI; no server connection.
    Reject unknown object fields, even where the wire schema permits extensions.
    """
    NAMES = {"initialize":"InitializeResponse", "request:initialize":"InitializeParams", "request:thread/resume":"ThreadResumeParams", "request:thread/compact/start":"ThreadCompactStartParams",
             "thread/resume": "ThreadResumeResponse", "thread/compact/start": "ThreadCompactStartResponse",
             "turn/started": "TurnStartedNotification", "turn/completed": "TurnCompletedNotification",
             "item/started": "ItemStartedNotification", "item/completed": "ItemCompletedNotification",
             "thread/tokenUsage/updated": "ThreadTokenUsageUpdatedNotification", "account/rateLimits/updated": "AccountRateLimitsUpdatedNotification",
             "thread/settings/updated": "ThreadSettingsUpdatedNotification", "thread/status/changed": "ThreadStatusChangedNotification",
             "thread/compacted": "ContextCompactedNotification", "model/rerouted": "ModelReroutedNotification",
             "configWarning": "ConfigWarningNotification", "error": "ErrorNotification"}

    def __init__(self, root):
        import jsonschema
        self.validators = {}
        formats = jsonschema.FormatChecker()
        for name, lower, upper in (("int64",-INT64_MAX-1,INT64_MAX),("uint64",0,INT64_MAX),("int32",-(1<<31),(1<<31)-1),("uint16",0,65535)):
            formats.checks(name)(lambda value,lo=lower,hi=upper: value is None or type(value) is int and lo <= value <= hi)
        def close(value):
            if isinstance(value, dict):
                if "properties" in value:
                    value["additionalProperties"] = False
                for item in value.values(): close(item)
            elif isinstance(value, list):
                for item in value: close(item)
        for method, name in self.NAMES.items():
            path = self.path(root, name)
            value = strict_json(read_regular(path, 4*1024*1024)); close(value)
            self.validators[method] = jsonschema.Draft7Validator(value,format_checker=formats)

    @staticmethod
    def path(root, name):
        return Path(root) / ("v1" if name.startswith("Initialize") else "v2") / (name+".json")

    def validate(self, method, value):
        if method not in self.validators: return
        if not self.validators[method].is_valid(value):
            raise ControlError("native-schema-invalid")


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
    if window is not None and (type(window) is not int or not 0 <= window <= INT64_MAX):
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
                               "thread/settings/updated", "configWarning", "thread/status/changed", "thread/compacted", "error"})

    def __init__(self, executable, *, handshake_timeout=HANDSHAKE_TIMEOUT,
                 operation_timeout=OPERATION_TIMEOUT, max_frame=MAX_FRAME,
                 transcript_limit=MAX_TRANSCRIPT, original_parent_pid=None, schema_root=None,
                 cancellation=None, send_intent_monotonic=None, allocation_tokens=None):
        if schema_root is None:
            raise ValueError("complete pinned native schema input required")
        self.schemas = NativeSchemas(schema_root)
        self.executable = executable
        self.handshake_timeout = handshake_timeout
        self.operation_timeout = operation_timeout
        self.max_frame = max_frame
        self.transcript_limit = transcript_limit
        self.process = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            preexec_fn=_native_child_signal_mask)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr): os.set_blocking(stream.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        self.buffer = bytearray(); self.transcript = []; self.transcript_bytes = 0
        self.stderr_bytes = 0; self.request_id = 0; self.calls = []
        self.compaction_sent = False; self.cancel_signal = None
        self.configuration_verified = False
        self.original_parent_pid = os.getppid() if original_parent_pid is None else original_parent_pid
        self.cancellation = cancellation
        self.started_monotonic = time.monotonic()
        self.send_intent_monotonic = send_intent_monotonic
        self.deadline = send_intent_monotonic + operation_timeout if send_intent_monotonic is not None else None
        self.cancel_deadline = None
        self.state = {"turn_id": None, "item_id": None, "phase": 0, "usage": None,
                      "observations": [], "statuses": [], "deprecated": False, "done": False}
        self.phase = "initialize"
        self.actual = None
        self.allocation_tokens = allocation_tokens

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
        if self.cancel_signal is None:
            self.cancel_signal = signum
            self.cancel_deadline = time.monotonic()+2

    def _check_cancel(self):
        if self.cancellation is not None and self.cancellation.signum is not None:
            self.cancel_signal = self.cancellation.signum
            self.cancel_deadline = self.cancellation.deadline
        if self.cancel_signal is not None:
            raise Cancelled(self.cancel_signal)
        if not self._parent_alive():
            if self.cancel_deadline is None: self.cancel_deadline = time.monotonic()+2
            raise ControlError("dispatcher-parent-died", phase=self.phase)

    def _send(self, value, method=None):
        if method is not None and method not in self.METHODS:
            raise ControlError("client-method-not-allowlisted")
        raw = (canonical(value) + "\n").encode()
        deadline = min(time.monotonic()+self.handshake_timeout, self.deadline or float("inf"))
        view = memoryview(raw)
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while view:
                self._check_cancel()
                if time.monotonic() >= deadline: raise ControlError("timeout", phase=self.phase)
                if not selector.select(min(.02, deadline-time.monotonic())): continue
                try: count = os.write(self.process.stdin.fileno(), view)
                except BlockingIOError: continue
                except OSError as exc: raise ControlError("transport-closed", phase=self.phase) from exc
                view = view[count:]
        if method:
            self.calls.append(method)

    def _line(self, deadline):
        while True:
            self._check_cancel()
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
        value = dict(value, sequence=len(self.transcript), elapsed_ms=int((time.monotonic()-self.started_monotonic)*1000))
        raw = canonical(value).encode()
        self.transcript_bytes += len(raw) + 1
        if self.transcript_bytes > self.transcript_limit or len(self.transcript) >= 10000:
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
        if "id" in value and type(value["id"]) not in {int,str}:
            raise ControlError("malformed-jsonrpc-id")
        if "method" in value and "id" in value:
            method = value.get("method")
            # JSON-RPC error responses are not client methods and grant no action.
            self._send({"id": value.get("id"), "error": {"code": -32601, "message": "client refuses all server requests"}})
            reason = "auth-refresh-request" if method == "account/chatgptAuthTokens/refresh" else "server-request"
            safe = method if method in {"account/chatgptAuthTokens/refresh", "item/commandExecution/requestApproval", "item/fileChange/requestApproval"} else "unknown"
            self._record({"kind": "server_request_refused", "method": safe})
            raise ControlError(reason)
        if "id" in value:
            if outstanding is None or type(value["id"]) is not int or value.get("id") != outstanding or set(value) - {"id", "result", "error"}:
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
        self.schemas.validate(method, params)
        if method == "error":
            info = params["error"].get("codexErrorInfo")
            classes = {"unauthorized": ("operational_auth", "native-unauthorized"),
                "sandboxError": ("operational_permissions", "native-sandbox-denial"),
                "cyberPolicy": ("terminal_policy", "native-cyber-policy"),
                "misalignmentPolicyViolation": ("terminal_policy", "native-policy-denial"),
                "usageLimitExceeded": ("operational_quota", "native-usage-limit"),
                "rateLimitExceeded": ("operational_rate", "native-rate-limit"),
                "sessionBudgetExceeded": ("operational_budget", "native-session-budget"),
                "serverOverloaded": ("operational_infrastructure", "native-server-overloaded")}
            category, reason = classes.get(info, ("terminal_protocol", "native-error")) if isinstance(info,str) else ("terminal_protocol", "native-error")
            if isinstance(info,dict) and any(isinstance(v,dict) and v.get("httpStatusCode")==401 for v in info.values()):
                category, reason = "operational_auth", "native-unauthorized"
            raise ControlError(reason,failure_class=category,phase=self.phase)
        return "notification", (method, params)

    def request(self, method, params, timeout, notification_handler=None):
        if method not in self.METHODS or method == "initialized":
            raise ControlError("client-method-not-allowlisted")
        self.request_id += 1; ident = self.request_id
        self.schemas.validate("request:"+method, params)
        self._send({"id": ident, "method": method, "params": params}, method)
        deadline = min(time.monotonic() + timeout, self.deadline or float("inf"))
        while True:
            kind, value = self._receive(deadline, ident)
            if kind == "response":
                self.schemas.validate(method, value)
                return value
            if notification_handler is None:
                raise ControlError("unexpected-notification")
            notification_handler(*value)

    def initialize(self):
        def observe(method, params):
            if method == "account/rateLimits/updated":
                self.state["observations"].append({"kind":"rate_limits","attribution":"unattributed","rate_limits":sanitize_rate_limits(params["rateLimits"])})
                self._record({"kind":method,"status":"sanitized"})
            elif method == "configWarning": raise ControlError("config-warning",phase="initialize")
            else: raise ControlError("unexpected-initialize-notification",phase="initialize")
        self.request("initialize", {"clientInfo": {"name": "clavain_dispatch_control", "version": "2"},
                     "capabilities": {"experimentalApi": True}}, self.handshake_timeout,notification_handler=observe)
        self._send({"method": "initialized"}, "initialized")

    @staticmethod
    def _validate_effective(result, thread_id, expected):
        if not isinstance(result, dict) or not isinstance(result.get("thread"), dict):
            raise ControlError("malformed-resume-response")
        thread = result["thread"]
        if thread.get("id") != thread_id:
            raise ControlError("resume-thread-mismatch")
        if thread.get("turns") != [] or result.get("initialTurnsPage") is not None:
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
        if state["done"] and method not in {"thread/tokenUsage/updated", "account/rateLimits/updated", "thread/status/changed", "thread/settings/updated", "configWarning", "model/rerouted"}:
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
            if turn.get("items") != [] or turn.get("error") is not None or turn.get("itemsView") not in (None, "full"):
                raise ControlError("lifecycle-item-mismatch")
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
                          "item_id": state["item_id"], "native_at_ms":params.get("startedAtMs" if method == "item/started" else "completedAtMs")})
        elif method == "thread/tokenUsage/updated":
            if state["phase"] < 1 or params.get("threadId") != thread_id or params.get("turnId") != state["turn_id"]:
                raise ControlError("native-usage-identity")
            observed = validate_usage(params.get("tokenUsage"))
            if state["usage"] is not None and canonical(state["usage"]) == canonical(observed):
                raise ControlError("duplicate-native-usage")
            state["usage"] = observed
            self._record({"kind": method, "thread_id": thread_id, "turn_id": state["turn_id"], "usage": observed})
            if self.allocation_tokens is not None and observed["last"]["inputTokens"]+observed["last"]["outputTokens"]>self.allocation_tokens:
                raise ControlError("budget-overrun",phase=self.phase)
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
                raise ControlError("terminal-turn-failed", remote_completion=turn.get("status") if turn.get("status") in {"failed", "interrupted"} else "unknown")
            if turn.get("error") is not None or turn.get("itemsView") not in (None, "full"):
                raise ControlError("terminal-item-mismatch")
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
        self.phase = "resume"
        state = self.state
        consume = lambda method, params: self._compact_notification(method, params, state, thread_id, effective_config)
        def resume_notification(method, params):
            if method not in {"account/rateLimits/updated", "thread/settings/updated", "thread/status/changed", "configWarning", "model/rerouted"}:
                raise ControlError("unexpected-resume-notification")
            consume(method, params)
        resumed = self.request("thread/resume", params, self.handshake_timeout, notification_handler=resume_notification)
        actual = self._validate_effective(resumed, thread_id, effective_config)
        self.actual = actual
        self.configuration_verified = True
        self.phase = "compact-send-intent"
        if self.send_intent_monotonic is None: self.send_intent_monotonic = time.monotonic()
        self.deadline = self.send_intent_monotonic + self.operation_timeout
        self.compaction_sent = True
        acknowledgment = self.request("thread/compact/start", {"threadId": thread_id}, self.handshake_timeout,
                                      notification_handler=consume)
        if acknowledgment != {}:
            raise ControlError("malformed-compaction-ack")
        deadline = self.deadline
        self.phase = "active-compaction"
        while not state["done"] or state["usage"] is None:
            if state["done"]: self.phase = "terminal-awaiting-accounting"
            try: kind, item = self._receive(deadline)
            except ControlError as exc:
                if state["done"] and state["usage"] is None and exc.reason in {"timeout", "transport-closed"}:
                    raise ControlError("missing-native-usage", remote_completion="completed", phase=self.phase) from exc
                raise
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
        if self.cancel_deadline is None: self.cancel_deadline = time.monotonic()+2
        try: self.process.stdin.close()
        except OSError: pass
        _terminate_group(self.process, self.cancel_deadline)

    def close(self):
        cleanup_confirmed = True
        try:
            self._terminate()
        except (OSError, ValueError):
            # Failure to observe/signal the owned group is not successful
            # cleanup. Preserve already observed protocol evidence for Bash.
            cleanup_confirmed = False
            try: self.process.wait(timeout=max(.001,(self.cancel_deadline or time.monotonic())-time.monotonic()))
            except subprocess.TimeoutExpired: pass
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        self.selector.close()
        self.cleanup_confirmed = cleanup_confirmed
        return {"process_exit_code": self.process.returncode, "reaped": cleanup_confirmed and self.process.poll() is not None,
                "stderr_bytes_discarded": self.stderr_bytes, "calls": list(self.calls)}


def validate_resume_events(binding, events):
    bound = strict_json(read_regular(binding))
    expected = bound.get("seed", {}).get("native_thread_id")
    observed = seed_thread(events)
    if observed != expected:
        raise ValueError("resumed native UUID differs from bound seed")
    return {"native_thread_id": observed, "events_sha256": sha256(events)}


def seal_resume(*args, **kwargs):
    raise ValueError("native-trusted-launcher-unavailable")


def write_private(path, value):
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(payload) > MAX_TRANSCRIPT:
        raise ValueError("sanitized operation result exceeds 16 MiB")
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


RESULT_FIELDS = set("schema_version fixture_only eligible operation operation_key admission_decision_id dispatch_id attempt_id seed_dispatch_id seed_attempt_id seed_thread_id binding_sha256 resolved_route_sha256 database_identity source_sha256 policy_sha256 executable_sha256 schema_manifest_sha256 configuration_sha256 actual_identity effective_configuration status failure remote_completion configuration_status accounting_status native_usage budget turn_id item_id times process sanitized_events account_observations control_result_is_approval control_result_is_last_message_verdict".split())
FAILURE_CLASSES = {"operational_auth", "operational_permissions", "terminal_policy", "operational_quota",
                   "operational_rate", "operational_budget", "terminal_configuration", "operational_timeout",
                   "operational_infrastructure", "terminal_accounting", "terminal_protocol", "terminal_evidence",
                   "terminal_recording", "operational_cancelled"}


def integer(value, label, minimum=0):
    if type(value) is not int or not minimum <= value <= INT64_MAX:
        raise ValueError("invalid int64 " + label)
    return value


def database_identity(path):
    path = Path(path)
    if not path.is_absolute() or str(path.resolve(strict=True)) != str(path):
        raise ValueError("database must be canonical without aliases")
    info = path.stat()
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino}


def attributable_tokens(value):
    usage = value["native_usage"]
    if value.get("operation", "compact") == "compact":
        row = validate_usage(usage)["last"]
        return integer(row["inputTokens"] + row["outputTokens"], "usage debit")
    exact_object(usage, {"input_tokens", "cached_input_tokens", "output_tokens"}, "CLI invocation usage")
    for key, number in usage.items(): integer(number, key)
    if usage["cached_input_tokens"] > usage["input_tokens"]:
        raise ValueError("invalid CLI cached input subset")
    return integer(usage["input_tokens"] + usage["output_tokens"], "CLI debit")


def validate_operation_result(value):
    exact_object(value, RESULT_FIELDS, "native result v2")
    if type(value["schema_version"]) is not int or value["schema_version"] != 2 or value["fixture_only"] is not True or value["eligible"] is not False:
        raise ValueError("native source artifacts are fixture-only and ineligible")
    if value["operation_key"] != native_operation_key(value["seed_thread_id"], value["operation"]):
        raise ValueError("result resource key mismatch")
    integer(value["admission_decision_id"], "admission", 1)
    for field in ("dispatch_id", "attempt_id", "seed_dispatch_id", "seed_attempt_id"):
        if not isinstance(value[field], str) or not value[field]: raise ValueError("missing result identity")
    for field in RESULT_FIELDS:
        if field.endswith("sha256"): require_hash(value[field], field)
    exact_object(value["database_identity"], {"path", "device", "inode"}, "database identity")
    for key in ("device", "inode"): integer(value["database_identity"][key], key)
    if not Path(value["database_identity"]["path"]).is_absolute(): raise ValueError("database path")
    for key, choices in {
        "status": {"completed", "failed", "cancelled"},
        "remote_completion": {"not-started", "unknown", "completed", "failed", "interrupted"},
        "configuration_status": {"unknown", "verified", "invalid"},
        "accounting_status": {"missing", "partial", "complete", "invalid"},
    }.items():
        if value[key] not in choices: raise ValueError("invalid result " + key)
    failure = value["failure"]
    if value["status"] == "completed" and failure is not None: raise ValueError("completed result carries a failure")
    if failure is not None:
        exact_object(failure, {"class", "reason", "phase"}, "typed native failure")
        if failure["class"] not in FAILURE_CLASSES: raise ValueError("invalid failure class")
        if not all(isinstance(failure[k], str) and re.fullmatch(r"[a-z][a-z0-9-]{0,95}", failure[k]) for k in ("reason", "phase")):
            raise ValueError("invalid safe failure enum")
    elif value["status"] != "completed": raise ValueError("non-success result lacks failure")
    identity = value["actual_identity"]
    exact_object(identity, {"backend", "model", "provider", "reasoning_effort", "service_tier", "evidence_refs", "coverage"}, "actual identity")
    if identity["coverage"] not in {"complete", "partial", "unknown"}: raise ValueError("identity coverage")
    for field in ("backend", "model", "provider", "reasoning_effort", "service_tier"):
        if identity[field] is not None and not isinstance(identity[field], str): raise ValueError("identity type")
    if not isinstance(identity["evidence_refs"], list): raise ValueError("identity references")
    for ref in identity["evidence_refs"]:
        exact_object(ref, {"kind", "decision_id"}, "identity reference")
        if ref["kind"] != "authoritative-decision": raise ValueError("identity reference kind")
        integer(ref["decision_id"], "identity decision", 1)
    effective = value["effective_configuration"]
    if effective is not None:
        exact_object(effective, {"model", "modelProvider", "reasoningEffort", "serviceTier", "cwd", "runtimeWorkspaceRoots", "approvalPolicy", "approvalsReviewer", "sandbox", "activePermissionProfile", "instructionSources"}, "effective configuration")
        # The complete native schema is checked before these observations are
        # retained. Recheck their bounded local value shapes on the reader.
        for key in ("runtimeWorkspaceRoots", "instructionSources"):
            if not isinstance(effective[key], list) or not all(isinstance(p, str) for p in effective[key]): raise ValueError("configuration paths")
        if not isinstance(effective["sandbox"], dict): raise ValueError("configuration sandbox")
        for key in ("model", "modelProvider", "cwd"):
            if not isinstance(effective[key],str) or not effective[key]: raise ValueError("configuration scalar")
        for key in ("reasoningEffort", "serviceTier"):
            if effective[key] is not None and not isinstance(effective[key],str): raise ValueError("configuration nullable scalar")
        if effective['approvalPolicy'] not in {'never','untrusted','on-failure','on-request'} or effective['approvalsReviewer'] not in {'user','guardian_subagent'}:
            raise ValueError('configuration authority enum')
        if effective['activePermissionProfile'] is not None: raise ValueError('unproved named permission profile')
        sandbox=effective['sandbox']; kind=sandbox.get('type')
        allowed={'workspaceWrite':{'type','networkAccess','writableRoots','excludeSlashTmp','excludeTmpdirEnvVar'},
                 'readOnly':{'type','networkAccess'},'dangerFullAccess':{'type'},'externalSandbox':{'type','networkAccess'}}
        if kind not in allowed or not set(sandbox)<=allowed[kind]: raise ValueError('sandbox fields')
        for key in ('networkAccess','excludeSlashTmp','excludeTmpdirEnvVar'):
            if key in sandbox and kind!='externalSandbox' and type(sandbox[key]) is not bool: raise ValueError('sandbox boolean')
        if kind=='externalSandbox' and sandbox.get('networkAccess','restricted') not in {'restricted','enabled'}: raise ValueError('sandbox network enum')
        for paths in (effective['runtimeWorkspaceRoots'],effective['instructionSources'],sandbox.get('writableRoots',[])):
            if not isinstance(paths,list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in paths) or len(paths)!=len(set(paths)):
                raise ValueError('configuration absolute paths')
    budget = value["budget"]
    exact_object(budget, set("scope_id manifest_sha256 allocation_tokens scope_limit_tokens reservation_decision_id attributable_input_tokens attributable_output_tokens debit_tokens status".split()), "native budget result")
    for key in ("allocation_tokens", "scope_limit_tokens", "reservation_decision_id"): integer(budget[key], key, 1)
    require_hash(budget["manifest_sha256"], "budget manifest")
    if not isinstance(budget['scope_id'],str) or not budget['scope_id']:raise ValueError('budget scope type')
    if budget["reservation_decision_id"] != value["admission_decision_id"] or budget["status"] not in {"reserved", "accounted", "unresolved", "overrun"}: raise ValueError("budget identity/status")
    if budget["allocation_tokens"] > budget["scope_limit_tokens"]: raise ValueError("budget allocation exceeds scope")
    for key in ("attributable_input_tokens", "attributable_output_tokens", "debit_tokens"):
        if budget[key] is not None: integer(budget[key], key)
    if value["native_usage"] is not None:
        debit = attributable_tokens(value)
        usage=value["native_usage"]
        counters=(usage["last"]["inputTokens"],usage["last"]["outputTokens"]) if value["operation"] == "compact" else (usage["input_tokens"],usage["output_tokens"])
        if (budget["attributable_input_tokens"],budget["attributable_output_tokens"]) != counters:
            raise ValueError("budget attributable counters differ from native usage")
        if budget["debit_tokens"] != debit: raise ValueError("result debit differs from usage")
        if debit > budget["allocation_tokens"] and budget["status"] != "overrun": raise ValueError("unreported budget overrun")
        if debit <= budget["allocation_tokens"] and budget["status"] != ("accounted" if value["accounting_status"] == "complete" else "unresolved"):
            raise ValueError("usage result has inconsistent budget status")
    elif value["accounting_status"] == "complete": raise ValueError("complete accounting without usage")
    elif any(budget[k] is not None for k in ("debit_tokens","attributable_input_tokens","attributable_output_tokens")):
        raise ValueError("unknown usage has fabricated debit counters")
    exact_object(value["times"], {"started_at", "send_intent_at", "completed_at", "elapsed_ms"}, "result times")
    integer(value["times"]["elapsed_ms"], "elapsed")
    for key in ("started_at", "send_intent_at", "completed_at"):
        timestamp = value["times"][key]
        if timestamp is not None and (not isinstance(timestamp, str) or not timestamp.endswith("Z") or dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).utcoffset() != dt.timedelta(0)): raise ValueError("UTC timestamp required")
    times=[dt.datetime.fromisoformat(value['times'][k].replace('Z','+00:00')) for k in ('started_at','send_intent_at','completed_at') if value['times'][k] is not None]
    if not times or times!=sorted(times):raise ValueError('result time ordering')
    exact_object(value["process"], {"exit_code", "reaped", "termination_reason"}, "process result")
    if type(value["process"]["reaped"]) is not bool or (value["process"]["exit_code"] is not None and type(value["process"]["exit_code"]) is not int): raise ValueError("invalid process evidence")
    termination=value['process']['termination_reason']
    if termination is not None and (not isinstance(termination,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,95}',termination)):raise ValueError('invalid process termination enum')
    for key in ("turn_id", "item_id"):
        if value[key] is not None and not isinstance(value[key], str): raise ValueError("invalid lifecycle ID")
    for key in ("control_result_is_approval", "control_result_is_last_message_verdict"):
        if value[key] is not False: raise ValueError("control results confer no approval")
    if value["status"] == "completed" and (value["process"]["exit_code"] != 0 or not value["process"]["reaped"] or value["accounting_status"] != "complete"):
        raise ValueError("completed result lacks successful accounted process")
    if not isinstance(value["sanitized_events"], list) or len(value["sanitized_events"]) > 10000: raise ValueError("event bound")
    variants={'response':{'id','status'},'server_request_refused':{'method'},'turn/started':{'thread_id','turn_id'},
              'turn/completed':{'thread_id','turn_id'},'item/started':{'thread_id','turn_id','item_id','native_at_ms'},'item/completed':{'thread_id','turn_id','item_id','native_at_ms'},
              'thread/tokenUsage/updated':{'thread_id','turn_id','usage'},'account/rateLimits/updated':{'status'},
              'thread/settings/updated':{'thread_id','status'},'thread/status/changed':{'thread_id','status'},'thread/compacted':{'thread_id','turn_id'}}
    for index, event in enumerate(value["sanitized_events"]):
        if not isinstance(event,dict) or event.get('kind') not in variants:raise ValueError('sanitized event kind')
        if set(event)!=variants[event['kind']]|{'kind','sequence','elapsed_ms'} or type(event.get('sequence')) is not int or event['sequence']!=index:raise ValueError('sanitized event shape/order')
        integer(event.get("elapsed_ms"), "event time")
        if event.get("native_at_ms") is not None: integer(event["native_at_ms"],"native event timestamp")
        if "usage" in event: validate_usage(event["usage"])
        if 'id' in event:integer(event['id'],'response ID',1)
        for key in ('thread_id','turn_id','item_id'):
            if key in event and (not isinstance(event[key],str) or not event[key] or len(event[key])>256):raise ValueError('sanitized identity')
        if event['kind']=='server_request_refused' and event['method'] not in {'unknown','account/chatgptAuthTokens/refresh','item/commandExecution/requestApproval','item/fileChange/requestApproval'}:raise ValueError('unsafe method enum')
        if event['kind']=='response' and event['status']!='ok':raise ValueError('response status')
        if event['kind']=='account/rateLimits/updated' and event['status']!='sanitized':raise ValueError('account event status')
        if event['kind']=='thread/settings/updated' and event['status']!='matching':raise ValueError('settings event status')
        if event['kind']=='thread/status/changed':
            status=event['status']
            if status not in ({'type':'idle'},{'type':'active','activeFlags':[]}):raise ValueError('thread status event')
    if not isinstance(value["account_observations"], list): raise ValueError("account observations")
    for observation in value["account_observations"]:
        exact_object(observation, {"kind", "attribution", "rate_limits"}, "account observation")
        if observation["kind"] != "rate_limits" or observation["attribution"] != "unattributed": raise ValueError("account attribution")
        for row in observation["rate_limits"]:
            if not isinstance(row, dict) or not set(row) <= {"bucket", "used_percent", "resets_at", "window_minutes"} or row.get("bucket") not in {"primary", "secondary"}: raise ValueError("rate limit shape")
            for key,number in row.items():
                if key!='bucket' and (type(number) not in {int,float} or not math.isfinite(number) or number<0):raise ValueError('rate limit number')
    return value


def seal_operation_result(directory, value):
    directory = Path(directory)
    validate_operation_result(value)
    result_path = directory / "operation-result.json"
    write_private(result_path, value)
    artifacts = []
    paths = {"binding": directory/"binding.snapshot.json", "operation_result": result_path}
    if value["operation"] == "resume": paths.update(events=directory/"resume.events.jsonl", last_message=directory/"last-message")
    for name, path in sorted(paths.items()):
        if not path.exists() and value["status"] != "completed":
            artifacts.append({"logical_name":name,"path":str(path),"size":None,"sha256":None,"status":"unavailable"})
            continue
        raw=read_regular(path,MAX_TRANSCRIPT,reject_hardlinks=True)
        artifacts.append({"logical_name": name, "path": str(path), "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "status": "sealed"})
    manifest_path = directory / "manifest.json"
    write_private(manifest_path, {"schema_version": 2, "fixture_only": True, "eligible": False, "artifacts": artifacts})
    return {"schema_version": 2, "admission_decision_id": value["admission_decision_id"],
            "operation_result": {"path": str(result_path), "sha256": sha256(result_path)},
            "artifact_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path)}}


def read_operation_envelope(envelope):
    exact_object(envelope, {"schema_version", "admission_decision_id", "operation_result", "artifact_manifest"}, "native envelope")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 2: raise ValueError("legacy native result is ineligible")
    integer(envelope["admission_decision_id"],"envelope admission",1)
    result = validate_operation_result(strict_json(read_evidence(envelope["operation_result"], "operation result")))
    manifest = strict_json(read_evidence(envelope["artifact_manifest"], "artifact manifest"))
    exact_object(manifest, {"schema_version", "fixture_only", "eligible", "artifacts"}, "artifact manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 2 or manifest["fixture_only"] is not True or manifest["eligible"] is not False: raise ValueError("manifest eligibility")
    names = []
    for entry in manifest["artifacts"]:
        exact_object(entry, {"logical_name", "path", "size", "sha256", "status"}, "manifest entry")
        names.append(entry["logical_name"])
        if entry["status"] == "unavailable" and result["status"] != "completed" and entry["logical_name"] in {"events","last_message"}:
            if entry["size"] is not None or entry["sha256"] is not None: raise ValueError("unavailable artifact has fabricated metadata")
            continue
        if entry["status"] != "sealed": raise ValueError("incomplete manifest")
        raw=read_evidence({"path": entry["path"], "sha256": entry["sha256"]}, "manifest artifact")
        if len(raw) != integer(entry["size"],"manifest size"): raise ValueError("manifest size mismatch")
        if entry["logical_name"] == "operation_result" and {"path": entry["path"], "sha256": entry["sha256"]} != envelope["operation_result"]: raise ValueError("manifest result mismatch")
        if entry["logical_name"] == "binding" and entry["sha256"] != result["binding_sha256"]: raise ValueError("manifest binding mismatch")
    expected_names={"binding","operation_result"}|({"events","last_message"} if result["operation"]=="resume" else set())
    if names != sorted(set(names)) or set(names) != expected_names: raise ValueError("manifest inventory mismatch")
    if result["admission_decision_id"] != envelope["admission_decision_id"]: raise ValueError("envelope admission mismatch")
    return result


def prepare_fixture_operation(spec_path, parent_pid):
    spec = strict_json(read_regular(spec_path))
    exact_object(spec, {"binding", "request_id", "attempt_id", "directory", "ic", "schema_root", "prompt"}, "fixture operation specification")
    spec["ic"] = str(Path(spec["ic"]).resolve(strict=True))
    directory = Path(spec["directory"])
    directory.mkdir(mode=0o700)  # exclusive attempt ownership
    snapshot = capture_binding_snapshot(spec["binding"], directory)
    value = strict_json(snapshot.pop("bytes"))
    if value.get("schema_version") != 2 or "seed_started_decision_id" not in value.get("authority",{}):
        raise ValueError("composed fixture requires prospective seed started evidence")
    database = value["authority"]["database"]
    identity = database_identity(database)
    records = load_records(database, spec["ic"])
    requested = decision(records, spec["request_id"], "measured-delivery-dispatch-request", "operation request")
    operation = requested.get("operation")
    if operation not in {"compact", "resume"}: raise ValueError("operation request missing native operation")
    # Old binding validators are fixture predicates only. They cannot grant
    # production admission; the public native commands are unconditionally shut.
    manifest_path = value["native_schema"]["manifest_path"]
    manifest = strict_json(read_regular(manifest_path))
    admitted = validate_binding(snapshot["path"], operation, records=records,
        expected_manifest_sha256=value["native_schema"]["manifest_sha256"], expected_manifest_file_count=len(manifest["files"]))
    if requested.get("seed_dispatch_id") != value["seed"]["dispatch_id"] or requested.get("seed_attempt_id") != value["seed"]["attempt_id"]:
        raise ValueError("operation request seed provenance mismatch")
    if not _same_envelope(requested, value["enrollment"]): raise ValueError("operation enrollment mismatch")
    if spec["request_id"] <= max(v for k,v in value["authority"].items() if k.endswith("decision_id")):
        raise ValueError("operation request must follow bound evidence")
    enrolled = decision(records, value["authority"]["enrollment_decision_id"], "measured-delivery-enrollment", "enrollment")
    budget_ref = enrolled.get("native_budget_manifest")
    budget_manifest = strict_json(read_regular(evidence_ref(budget_ref, "budget manifest")))
    exact_object(budget_manifest, {"scope_id", "units", "scope_limit_tokens", "max_allocation_tokens"}, "prospective budget manifest")
    if budget_manifest["units"] != "native_input_plus_output_tokens": raise ValueError("native budget units")
    exact_object(budget_manifest["max_allocation_tokens"], {"compact", "resume"}, "operation maxima")
    allocation = requested.get("allocation_tokens")
    limit = integer(budget_manifest["scope_limit_tokens"], "scope limit", 1)
    maximum = integer(budget_manifest["max_allocation_tokens"][operation], "maximum allocation", 1)
    integer(allocation, "allocation", 1)
    if allocation > maximum or maximum > limit: raise ValueError("native allocation exceeds approved maximum")
    seed = decision(records, value["authority"]["seed_execution_decision_id"], "dispatch-profile", "seed execution")
    route = seed["resolved_route"]
    if requested.get("resolved_route") != route: raise ValueError("operation route mismatch")
    root = Path(database).parent.resolve()
    executable = Path(admitted["executable"]).resolve()
    executable.relative_to(root)  # only an actual fake transport in this fixture
    directory.resolve().relative_to(root)
    if not isinstance(spec["prompt"], str) or len(spec["prompt"].encode()) > MAX_BINDING: raise ValueError("fixture prompt bound")
    prompt_digest = hashlib.sha256(spec["prompt"].encode()).hexdigest()
    if requested.get("prompt_sha256") != prompt_digest: raise ValueError("fixture prompt differs from prospective request")
    # Schema tree is pinned byte-for-byte into the admission, rechecked by child.
    schema_root = Path(spec["schema_root"]).resolve(strict=True)
    if schema_root != Path(manifest_path).parent / "native-schema" or len(manifest["files"]) != APPROVED_MANIFEST_FILES:
        raise ValueError("composed fixture requires its complete pinned schema tree")
    schema_files = {name: sha256(NativeSchemas.path(schema_root,name)) for name in NativeSchemas.NAMES.values()}
    admission = {"schema_version": 2, "fixture_only": True, "eligible": False,
        "provider": "codex", "operation": operation, "operation_key": native_operation_key(value["seed"]["native_thread_id"], operation),
        "seed_thread_id": value["seed"]["native_thread_id"], "seed_dispatch_id": value["seed"]["dispatch_id"], "seed_attempt_id": value["seed"]["attempt_id"],
        "dispatch_id": requested["dispatch_id"], "attempt_id": spec["attempt_id"], "request_decision_id": spec["request_id"],
        "binding_sha256": snapshot["sha256"], "prompt_sha256":prompt_digest,
        "request_sha256": hashlib.sha256(canonical(requested).encode()).hexdigest(),
        "ic_sha256":sha256(spec["ic"],256*1024*1024), "resolved_route_sha256": hashlib.sha256(canonical(route).encode()).hexdigest(),
        "database_identity": identity, "parent_pid": int(parent_pid),
        "native_budget": {"scope_id": budget_manifest["scope_id"], "manifest_sha256": budget_ref["sha256"], "allocation_tokens": allocation,
            "max_allocation_tokens": maximum, "scope_limit_tokens": limit},
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")}
    return {"admission": admission, "snapshot": snapshot, "directory": str(directory.resolve()), "ic": spec["ic"],
        "route": route, "profile": seed["resolved_profile"], "configuration": admitted["configuration"],
        "workdir": admitted["configuration"]["request"]["cwd"], "executable": admitted["executable"],
        "schema_root": str(schema_root), "schema_files": schema_files, "prompt": spec["prompt"], "binding": value}


def continue_fixture_operation(prepared, reservation_id):
    prepared = strict_json(prepared)
    admission = prepared["admission"]; ident = int(reservation_id)
    rows = load_records(admission["database_identity"]["path"], prepared["ic"])
    actual = decision(rows, ident, "dispatch-profile", "reservation")
    if actual.get("execution", {}).get("native_admission") != admission: raise ValueError("reservation readback mismatch")
    elect_native_reservation(rows, admission["operation_key"], ident)
    budget = admission["native_budget"]
    evaluate_native_budget(rows, budget["scope_id"], budget["scope_limit_tokens"], ident)
    intent = {"schema_version": 2, "fixture_only": True, "eligible": False,
        "admission_decision_id": ident, "operation": admission["operation"], "operation_key": admission["operation_key"],
        "seed_thread_id": admission["seed_thread_id"], "send_intent_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "send_intent_monotonic": time.monotonic()}
    return {"schema_version": 2, "fixture_only": True, "eligible": False, "parent_pid": admission["parent_pid"],
            "prepared": prepared, "reservation_decision_id": ident, "send_intent": intent}


def export_fixture_receipt(records, terminal_id, destination):
    rows = strict_json(records)
    value = decision(rows, int(terminal_id), "dispatch-profile", "terminal")
    if value.get("fixture_only") is not True or value.get("eligible") is not False or value.get("terminal") is not True:
        raise ValueError("terminal is not fixture-only evidence")
    read_operation_envelope(value["execution"]["native_operation"])
    write_private(destination, value)
    return {"path": destination, "sha256": sha256(destination), "fixture_only": True, "eligible": False}


def seal_fixture_admission_failure(prepared, reservation_id, phase):
    prepared = strict_json(prepared)
    if phase not in {"admission", "send-intent-recording"}: raise ValueError("unknown admission failure phase")
    outcome = {"status":"failed", "remote_completion":"not-started", "accounting_status":"missing", "configuration_status":"unknown",
        "failure":{"class":"terminal_recording" if phase == "send-intent-recording" else "terminal_evidence",
                   "reason":"admission-rejected" if phase == "admission" else "send-intent-recording-failed", "phase":phase}}
    result = fixture_result(prepared,int(reservation_id),{"send_intent_at":None},outcome,
        {"exit_code":1,"reaped":True,"termination_reason":outcome["failure"]["reason"]},time.monotonic())
    # No refund: an admission remains reserved, and any committed send intent
    # still blocks the budget even when its append response was lost.
    envelope = seal_operation_result(prepared["directory"],result)
    write_private(Path(prepared["directory"])/"envelope.json",envelope)
    return envelope


def bind_fixture_compaction(binding_path, database, terminal_id, request_id, receipt_path, output, ic="ic"):
    """Real fixture writer -> authoritative terminal -> dependent binding reader.

    The measured task-delivery consumers reject this binding and all its rows.
    """
    bound = strict_json(read_regular(binding_path, reject_hardlinks=True))
    rows = load_records(database, ic)
    terminal = decision(rows, int(terminal_id), "dispatch-profile", "compaction terminal")
    if terminal != strict_json(read_regular(receipt_path)) or terminal.get("fixture_only") is not True or not terminal.get("terminal"):
        raise ValueError("fixture compaction receipt differs from authoritative terminal")
    envelope = terminal["execution"]["native_operation"]; result = read_operation_envelope(envelope)
    if result["operation"] != "compact" or result["status"] != "completed" or result["accounting_status"] != "complete" or result["configuration_status"] != "verified":
        raise ValueError("dependent fixture requires completed accounted compaction")
    if result["binding_sha256"] != sha256(binding_path) or result["seed_thread_id"] != bound["seed"]["native_thread_id"]:
        raise ValueError("fixture compaction source binding mismatch")
    request = decision(rows, int(request_id), "measured-delivery-dispatch-request", "compaction request")
    if request.get("dispatch_id") != result["dispatch_id"] or not int(request_id) < result["admission_decision_id"] < int(terminal_id):
        raise ValueError("compaction fixture request ordering mismatch")
    sends = [r for r in rows if context(r).get("execution",{}).get("native_send_intent",{}).get("admission_decision_id") == result["admission_decision_id"]]
    if len(sends) != 1 or not result["admission_decision_id"] < sends[0]["id"] < int(terminal_id):
        raise ValueError("compaction fixture send-intent ordering mismatch")
    result_binding = {"schema_version":2,"fixture_only":True,"eligible":False,"terminal_decision_id":int(terminal_id),
        "request_decision_id":int(request_id),"native_operation":envelope}
    # This is an actual append and readback, never a caller-created receipt
    # substituted for the authoritative binding row. Lost replies do not retry.
    response = subprocess.run([ic, f"--db={database}", "--json", "route", "record", "--agent=native-fixture-binder", "--model=fixture",
        "--rule=native-fixture-result-binding", "--context="+canonical(result_binding)], cwd=Path(database).parent,
        capture_output=True,text=True,timeout=10)
    if response.returncode: raise ValueError("fixture result binding append failed")
    binding_id = integer(strict_json(response.stdout)["id"],"result binding",1)
    rows = load_records(database, ic)
    if decision(rows,binding_id,"native-fixture-result-binding","compaction result binding") != result_binding:
        raise ValueError("fixture result binding readback failed")
    bound["authority"].update(compaction_dispatch_request_decision_id=int(request_id), compaction_execution_decision_id=int(terminal_id),
        compaction_admission_decision_id=result["admission_decision_id"], compaction_send_intent_decision_id=sends[0]["id"],
        compaction_result_binding_decision_id=binding_id)
    bound["compaction"] = {"dispatch_id": result["dispatch_id"], "attempt_id": result["attempt_id"], "status": result["status"],
        "accounting_status": result["accounting_status"], "configuration_status": result["configuration_status"],
        "receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path)}, "operation_result": envelope["operation_result"]}
    bound.update(fixture_only=True, eligible=False)
    write_private(output, bound)
    pin = bound["native_schema"]
    return validate_binding(output, "resume", records=rows, expected_manifest_sha256=pin["manifest_sha256"], expected_manifest_file_count=APPROVED_MANIFEST_FILES)


class FixtureCancellation:
    def __init__(self, parent):
        self.parent = parent; self.signum = None; self.deadline = None
        self.previous = {sig: signal.signal(sig, self.signal) for sig in (signal.SIGINT, signal.SIGTERM)}

    def signal(self, signum, _frame=None):
        if self.signum is None:
            self.signum = signum; self.deadline = time.monotonic()+2

    def check(self):
        if os.getppid() != self.parent:
            self.signal(signal.SIGTERM)
        if self.signum is not None: raise Cancelled(self.signum)

    def restore(self):
        for sig, handler in self.previous.items(): signal.signal(sig, handler)


def fixture_result(prepared, ident, intent, outcome, process, started):
    a = prepared["admission"]; bound = prepared["binding"]; budget = a["native_budget"]
    result = {key: a[key] for key in ("operation", "operation_key", "dispatch_id", "attempt_id", "seed_dispatch_id", "seed_attempt_id", "seed_thread_id", "binding_sha256", "resolved_route_sha256", "database_identity")}
    result.update(schema_version=2, fixture_only=True, eligible=False, admission_decision_id=ident,
        source_sha256=bound["source"]["sha256"], policy_sha256=bound["policy"]["sha256"], executable_sha256=bound["executable"]["sha256"],
        schema_manifest_sha256=bound["native_schema"]["manifest_sha256"], configuration_sha256=bound["configuration"]["sha256"],
        actual_identity={"backend": None, "model": None, "provider": None, "reasoning_effort": None, "service_tier": None, "evidence_refs": [], "coverage": "unknown"},
        effective_configuration=outcome.get("effective_configuration"), status=outcome.get("status", "failed"), failure=outcome.get("failure"),
        remote_completion=outcome.get("remote_completion", "unknown"), configuration_status=outcome.get("configuration_status", "unknown"),
        accounting_status=outcome.get("accounting_status", "missing"), native_usage=outcome.get("native_usage"),
        turn_id=outcome.get("turn_id"), item_id=outcome.get("item_id"), process=process,
        times={"started_at": a["started_at"], "send_intent_at": intent["send_intent_at"], "completed_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"), "elapsed_ms": int((time.monotonic()-started)*1000)},
        sanitized_events=outcome.get("sanitized_transcript", []), account_observations=outcome.get("account_observations", []),
        control_result_is_approval=False, control_result_is_last_message_verdict=False)
    native_budget = {key: budget[key] for key in ("scope_id", "manifest_sha256", "allocation_tokens", "scope_limit_tokens")}
    native_budget.update(reservation_decision_id=ident, attributable_input_tokens=None, attributable_output_tokens=None, debit_tokens=None, status="unresolved")
    result["budget"] = native_budget
    if result["native_usage"] is not None:
        usage = result["native_usage"]; compact = a["operation"] == "compact"
        row = usage["last"] if compact else usage
        native_budget.update(attributable_input_tokens=row["inputTokens" if compact else "input_tokens"],
            attributable_output_tokens=row["outputTokens" if compact else "output_tokens"], debit_tokens=attributable_tokens(result),
            status="accounted" if result["accounting_status"] == "complete" else "unresolved")
        if native_budget["debit_tokens"] > budget["allocation_tokens"]:
            native_budget["status"] = "overrun"; result["status"] = "failed"; result["accounting_status"] = "invalid"
            result["failure"] = {"class": "terminal_accounting", "reason": "budget-overrun", "phase": "terminal-accounting"}
    effective = result["effective_configuration"]
    if effective is not None:
        result["actual_identity"] = {"backend": "codex", "model": effective["model"], "provider": effective["modelProvider"], "reasoning_effort": effective["reasoningEffort"], "service_tier": effective["serviceTier"], "evidence_refs": [], "coverage": "partial"}
    return result


def verify_fixture_packet(packet):
    exact_object(packet, {"schema_version", "fixture_only", "eligible", "parent_pid", "prepared",
        "reservation_decision_id", "send_intent", "send_intent_decision_id"}, "private fixture packet")
    if packet["fixture_only"] is not True or packet["eligible"] is not False or packet["parent_pid"] != os.getppid():
        raise ValueError("private fixture parent/eligibility mismatch")
    p = packet["prepared"]; a = p["admission"]; ident = packet["reservation_decision_id"]
    exact_object(p, {"admission","snapshot","directory","ic","route","profile","configuration","workdir","executable","schema_root","schema_files","prompt","binding"},"private prepared state")
    if hashlib.sha256(p["prompt"].encode()).hexdigest() != a["prompt_sha256"] or sha256(p["ic"],256*1024*1024) != a["ic_sha256"]:
        raise ValueError("private prompt or Intercore executable changed")
    database = a["database_identity"]["path"]
    if database_identity(database) != a["database_identity"]: raise ValueError("authoritative database replaced")
    private = Path(p["directory"])
    private.resolve(strict=True).relative_to(Path(database).parent.resolve())
    if private.is_symlink() or stat.S_IMODE(private.stat().st_mode) != 0o700 or private.stat().st_uid != os.getuid():
        raise ValueError("private artifact directory changed")
    if Path(p["snapshot"]["path"]) != private/"binding.snapshot.json": raise ValueError("private snapshot path changed")
    rows = load_records(database, p["ic"])
    if decision(rows, ident, "dispatch-profile", "reservation").get("execution", {}).get("native_admission") != a:
        raise ValueError("private child reservation mismatch")
    elect_native_reservation(rows, a["operation_key"], ident)
    b = a["native_budget"]
    evaluate_native_budget(rows, b["scope_id"], b["scope_limit_tokens"], ident)
    if decision(rows, packet["send_intent_decision_id"], "dispatch-profile", "send intent").get("execution", {}).get("native_send_intent") != packet["send_intent"] or packet["send_intent_decision_id"] <= ident:
        raise ValueError("private child send-intent mismatch")
    raw = read_regular(p["snapshot"]["path"], reject_hardlinks=True)
    if hashlib.sha256(raw).hexdigest() != a["binding_sha256"] or strict_json(raw) != p["binding"]:
        raise ValueError("private snapshot changed")
    if p["configuration"] != p["binding"]["configuration"] or p["executable"] != p["binding"]["executable"]["path"]:
        raise ValueError("private configuration differs from snapshot")
    for field in ("source", "policy", "executable"): evidence_ref(p["binding"][field], field, 256*1024*1024)
    pin = p["binding"]["native_schema"]
    validate_protocol_manifest(pin["manifest_path"], pin["manifest_sha256"], APPROVED_MANIFEST_FILES)
    if hashlib.sha256(canonical(p["route"]).encode()).hexdigest() != a["resolved_route_sha256"]:
        raise ValueError("private route changed")
    request = decision(rows, a["request_decision_id"], "measured-delivery-dispatch-request", "request")
    if hashlib.sha256(canonical(request).encode()).hexdigest() != a["request_sha256"] or request.get("resolved_route") != p["route"] or request.get("dispatch_id") != a["dispatch_id"]:
        raise ValueError("private request changed")
    # Election above has checked *all* rows, including conflicting provenance
    # and competing reservations. Recheck seed predicates without rerunning the
    # public-entry availability test against this already elected resource.
    target = ("codex",a["seed_thread_id"].lower(),a["operation"])
    validation_rows = [r for r in rows if _native_record_resource(r,rows) != target]
    validate_binding(p["snapshot"]["path"],a["operation"],records=validation_rows,
        expected_manifest_sha256=pin["manifest_sha256"], expected_manifest_file_count=APPROVED_MANIFEST_FILES)
    if set(p["schema_files"]) != set(NativeSchemas.NAMES.values()): raise ValueError("native schema inventory changed")
    for name, expected in p["schema_files"].items():
        if sha256(NativeSchemas.path(p["schema_root"],name)) != expected: raise ValueError("native schema changed")
    Path(p["executable"]).resolve(strict=True).relative_to(Path(database).parent.resolve())
    return p


def run_fixture_resume(process, prepared, cancellation, deadline, observed):
    for stream in (process.stdin, process.stdout, process.stderr): os.set_blocking(stream.fileno(), False)
    req = prepared["configuration"]["request"]
    payload = memoryview((req["baseInstructions"]+"\n\n"+req["developerInstructions"]+"\n\n"+prepared["prompt"]).encode())
    buffer = bytearray(); usage = None; thread_seen = False; terminal = False; discarded = 0; count = 0
    events_descriptor=os.open(Path(prepared["directory"])/"resume.events.jsonl",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    event_bytes=0
    with os.fdopen(events_descriptor,"wb",buffering=0) as events_file, selectors.DefaultSelector() as selector:
        selector.register(process.stdin, selectors.EVENT_WRITE, "input")
        selector.register(process.stdout, selectors.EVENT_READ, "output")
        selector.register(process.stderr, selectors.EVENT_READ, "error")
        while selector.get_map():
            cancellation.check()
            if time.monotonic() >= deadline: raise ControlError("timeout", phase="cli-resume")
            for key, _ in selector.select(.02):
                if key.data == "input":
                    if payload:
                        try: n = os.write(key.fd, payload)
                        except BlockingIOError: continue
                        except BrokenPipeError as exc: raise ControlError("transport-closed") from exc
                        payload = payload[n:]
                    if not payload:
                        selector.unregister(key.fileobj); key.fileobj.close()
                    continue
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj); continue
                if key.data == "error":
                    discarded += len(chunk)
                    if discarded > MAX_FRAME: raise ControlError("oversized-stderr")
                    continue
                event_bytes+=len(chunk)
                if event_bytes>MAX_TRANSCRIPT: raise ControlError("oversized-frame")
                _write_all(events_file.fileno(),chunk)
                buffer.extend(chunk)
                if len(buffer)>MAX_TRANSCRIPT: raise ControlError("oversized-frame")
                while b"\n" in buffer:
                    raw, _, rest = buffer.partition(b"\n"); buffer = bytearray(rest); count += 1
                    if len(raw)>MAX_FRAME or count>10000: raise ControlError("oversized-frame")
                    event = strict_json(raw); kind = event.get("type")
                    if kind == "thread.started":
                        if thread_seen or event.get("thread_id") != prepared["admission"]["seed_thread_id"]: raise ControlError("resume-thread-mismatch")
                        thread_seen = True
                    elif kind == "turn.completed":
                        if terminal or not thread_seen: raise ControlError("lifecycle-order")
                        usage = event.get("usage"); attributable_tokens({"operation":"resume", "native_usage":usage}); terminal = True
                        observed.update(remote_completion="completed",native_usage=usage,accounting_status="complete")
                    elif kind in {"turn.started", "item.started", "item.updated", "item.completed"}:
                        if not thread_seen or terminal: raise ControlError("lifecycle-order")
                    elif kind in {"turn.failed", "error"}:
                        observed["remote_completion"]="failed"
                        raise ControlError("cli-turn-failed",remote_completion="failed",phase="cli-resume")
                    else: raise ControlError("unknown-notification")
        os.fsync(events_file.fileno())
    if buffer or not terminal or usage is None: raise ControlError("missing-native-usage")
    # Observe exit without reaping so cleanup retains the original group ID
    # through its last signal, even if the leader left descendants behind.
    while (exited := os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)) is None:
        cancellation.check()
        if time.monotonic() >= deadline: raise ControlError("timeout",phase="cli-resume")
        time.sleep(.01)
    if exited.si_code != os.CLD_EXITED or exited.si_status:
        raise ControlError("cli-process-failed", failure_class="operational_infrastructure")
    return {"status":"completed", "remote_completion":"completed", "accounting_status":"complete",
            "configuration_status":"unknown", "native_usage":usage}


def run_fixture_handoff(descriptor, result_path):
    cancellation = FixtureCancellation(os.getppid())
    control = None; process = None; prepared = None; outcome = None; code = 1; cleanup_confirmed = True
    resume_observed = {}
    started = time.monotonic()
    try:
        packet = read_framed_handoff(descriptor, cancel_check=cancellation.check); os.close(descriptor)
        prepared = packet.get("prepared")
        admission = prepared["admission"]; intent = packet["send_intent"]; ident = packet["reservation_decision_id"]
        verify_fixture_packet(packet)
        write_private(Path(prepared["directory"])/"handoff-consumed.json", {"fixture_only":True,"eligible":False,"admission_decision_id":ident})
        cancellation.check()
        admission = prepared["admission"]; intent = packet["send_intent"]; ident = packet["reservation_decision_id"]
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            if admission["operation"] == "compact":
                control = AppServerControl(prepared["executable"], schema_root=prepared["schema_root"], cancellation=cancellation,
                    original_parent_pid=packet["parent_pid"], send_intent_monotonic=intent["send_intent_monotonic"],
                    allocation_tokens=admission["native_budget"]["allocation_tokens"])
                process = control.process
            else:
                argv = build_native_resume_argv({"executable":prepared["executable"], "native_thread_id":admission["seed_thread_id"],
                    "configuration":prepared["configuration"]}, Path(prepared["directory"])/"last-message")
                process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                    close_fds=True,preexec_fn=_native_child_signal_mask)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        cancellation.check()
        if control:
            outcome = control.compact(admission["seed_thread_id"], prepared["configuration"]["request"], prepared["configuration"]["effective"])
        else:
            outcome = run_fixture_resume(process, prepared, cancellation, intent["send_intent_monotonic"]+OPERATION_TIMEOUT,resume_observed)
        code = 0
    except (ControlError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        if prepared is None: raise
        code = 128+exc.signum if isinstance(exc, Cancelled) else 1
        failure = {"class": exc.failure_class if isinstance(exc, ControlError) else "terminal_evidence",
                   "reason": exc.reason if isinstance(exc, ControlError) else "private-handoff-rejected",
                   "phase": control.phase if control else "private-handoff"}
        state = control.state if control else {}
        outcome = {"status":"cancelled" if isinstance(exc, Cancelled) else "failed", "failure":failure,
            "remote_completion":"completed" if state.get("done") else "not-started" if control and not control.compaction_sent else getattr(exc,"remote_completion","unknown" if process else "not-started"),
            "configuration_status":"verified" if control and control.configuration_verified else "invalid" if failure["class"] == "terminal_configuration" else "unknown",
            "accounting_status":"partial" if state.get("usage") else "missing", "native_usage":state.get("usage"),
            "turn_id":state.get("turn_id"), "item_id":state.get("item_id"), "effective_configuration":control.actual if control else None,
            "sanitized_transcript":list(control.transcript) if control else [], "account_observations":state.get("observations",[])}
        if not control: outcome.update(resume_observed)
    finally:
        if control:
            control.cancel_deadline = cancellation.deadline or control.cancel_deadline; control.close()
        elif process:
            for stream in (process.stdin, process.stdout, process.stderr): stream.close()
            try: _terminate_group(process, cancellation.deadline or time.monotonic()+2)
            except (OSError, ValueError): cleanup_confirmed = False
        cancellation.restore()
    reaped = cleanup_confirmed and (process is None or process.poll() is not None) and (control is None or control.cleanup_confirmed)
    if not reaped:
        if not outcome.get("failure"): outcome["failure"] = {"class":"operational_infrastructure","reason":"cleanup-unconfirmed","phase":"cleanup"}
        if outcome["status"] != "cancelled": outcome["status"] = "failed"
        code = code or 1
    result = fixture_result(prepared, ident, intent, outcome,
        {"exit_code":code, "reaped":reaped,
         "termination_reason":outcome.get("failure",{}).get("reason") if outcome.get("failure") else None}, started)
    if result["status"] != "completed" and code == 0: result["process"]["exit_code"] = 1
    envelope = seal_operation_result(prepared["directory"], result)
    write_private(result_path, envelope)
    return result


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
        if args.command in {"compact", "seal-resume", "validate-binding"}:
            parser.exit(2, "dispatch-control: native-trusted-launcher-unavailable\n")
        if args.command == "validate-binding":
            result = validate_binding(args.binding, args.operation, ic=args.ic, expected=strict_json(args.expected.encode()))
            print(canonical(result)); return 0
        if args.command == "validate-resume-events":
            print(canonical(validate_resume_events(args.binding, args.events))); return 0
        if args.command == "seal-resume":
            print(canonical(seal_resume(args.binding, args.events, args.output, args.artifact_dir, args.process_code))); return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"dispatch-control: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
