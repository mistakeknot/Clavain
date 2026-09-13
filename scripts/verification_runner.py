#!/usr/bin/env python3
"""Fresh, bounded machine evidence. Receipts do not grant task acceptance.

CLI: verification_runner.py --spec spec.json --project-dir REPO --evidence-dir DIR
Only declared inputs and executable inventory are covered; shell commands are
trusted reviewed code, not sandboxed. No installation, repair or result caching.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET

from _verification import VerificationStep

TIMEOUT = 600
OUTPUT_LIMIT = 64 * 1024 * 1024
SUMMARY_LIMIT = 6000
VERSION_ARGS = (("--version",), ("-V",), ("version",))


class VerificationError(ValueError):
    def __init__(self, message, kind="contract"):
        super().__init__(message)
        self.kind = kind


@dataclass
class VerificationResult:
    step: VerificationStep
    summary: str
    receipt_path: str | None = None
    failure_kind: str | None = None
    machine_eligible: bool = False
    review_allowed: bool = False
    repairable: bool = False


def _json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _object(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise VerificationError(f"invalid fields; expected {sorted(allowed)}, required {sorted(required)}")


def _string(value):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise VerificationError("expected nonempty string without NUL")
    return value


def _list(value):
    if not isinstance(value, list):
        raise VerificationError("expected a list")
    return value


def _limit(value, integer=False, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= minimum:
        raise VerificationError("invalid positive finite limit")
    if integer and not isinstance(value, int):
        raise VerificationError("expected integer limit")


def expectation(text):
    _string(text)
    m = re.fullmatch(r"exit (0|[1-9][0-9]{0,2})", text)
    if m and int(m[1]) <= 255:
        return "exit", int(m[1])
    m = re.fullmatch(r'contains ("(?:[^"\\]|\\.)*")', text)
    if m:
        try:
            value = json.loads(m[1])
        except ValueError as exc:
            raise VerificationError("malformed contains string") from exc
        if value:
            return "contains", value.encode()
    raise VerificationError(f"unsupported expectation: {text}")


def parse_verify_blocks(text):
    """Consume every byte of every legacy block; never salvage partial entries."""
    blocks = list(re.finditer(r"<verify>\s*\n(.*?)</verify>", text, re.S))
    remainder = re.sub(r"<verify>\s*\n(.*?)</verify>", "", text, flags=re.S)
    if re.search(r"</?verify\b", remainder, re.I):
        raise VerificationError("malformed or unclosed verify block")
    entries = []
    pattern = re.compile(r'\s*- run: `([^`\n]+)`[ \t]*\n[ \t]+expect: ([^\n]+)\n?')
    for block in blocks:
        body, pos, count = block[1], 0, 0
        while body[pos:].strip():
            m = pattern.match(body, pos)
            if not m:
                raise VerificationError("partially parsed verify entry or unknown field")
            expectation(m[2].strip())
            entries.append({"run": m[1], "expect": m[2].strip()})
            pos, count = m.end(), count + 1
        if not count:
            raise VerificationError("empty verify block")
    return entries


def validate_spec(raw):
    _object(raw, {"required", "checks", "prerequisites", "inputs", "timeout", "output_limit"}, {"checks"})
    spec = json.loads(_json(raw))  # independent immutable-in-practice copy
    if not isinstance(spec.get("required", True), bool):
        raise VerificationError("required must be boolean")
    for key, default in (("timeout", TIMEOUT), ("output_limit", OUTPUT_LIMIT)):
        _limit(spec.get(key, default), integer=key == "output_limit")
    checks = _list(spec["checks"])
    if not checks and spec.get("required", True):
        raise VerificationError("required verification has no checks")
    identifiers, reports = set(), set()
    for i, check in enumerate(checks):
        _object(check, {"id", "run", "expect", "timeout", "output_limit", "test_count"}, {"run", "expect"})
        check.setdefault("id", f"check-{i+1}")
        identifier = _string(check["id"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", identifier) or identifier in identifiers:
            raise VerificationError("invalid or duplicate check identifier")
        identifiers.add(identifier)
        _string(check["run"])
        expectation(check["expect"])
        for key, default in (("timeout", TIMEOUT), ("output_limit", OUTPUT_LIMIT)):
            _limit(check.get(key, spec.get(key, default)), integer=key == "output_limit")
        if "test_count" in check:
            count = check["test_count"]
            _object(count, {"parser", "report", "min_executed", "max_skipped"}, {"parser", "report"})
            if count["parser"] != "pytest-junit":
                raise VerificationError("unsupported test-count parser")
            report = _string(count["report"])
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.xml", report):
                raise VerificationError("report must be a simple XML filename")
            if report in reports:
                raise VerificationError("duplicate test-count report filename")
            reports.add(report)
            _limit(count.get("min_executed", 1), integer=True)
            _limit(count.get("max_skipped", 0), integer=True, minimum=-1)
    for path in _list(spec.get("inputs", [])):
        _string(path)
    pre = spec.get("prerequisites", {})
    _object(pre, {"paths", "repositories", "executables"})
    for path in _list(pre.get("paths", [])):
        _string(path)
    for repo in _list(pre.get("repositories", [])):
        _object(repo, {"path", "revision", "inputs"}, {"path", "revision"})
        _string(repo["path"])
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", _string(repo["revision"])):
            raise VerificationError("dependency revision must be an exact commit hash")
        for path in _list(repo.get("inputs", [])):
            _string(path)
    names = set()
    for exe in _list(pre.get("executables", [])):
        _object(exe, {"name", "path", "sha256", "version_args", "version_contains"}, {"name"})
        name = _string(exe["name"])
        if name in names:
            raise VerificationError("duplicate executable identifier")
        names.add(name)
        if "path" in exe:
            _string(exe["path"])
        if "sha256" in exe and not re.fullmatch(r"[0-9a-f]{64}", _string(exe["sha256"])):
            raise VerificationError("invalid executable digest")
        if tuple(_list(exe.get("version_args", ["--version"]))) not in VERSION_ARGS:
            raise VerificationError("unsupported fixed version argument vector")
        if "version_contains" in exe:
            _string(exe["version_contains"])
    return spec


def _git(root, *args):
    try:
        p = subprocess.run(["git", "-C", str(root), *args], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=30, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError(f"git probe unavailable: {exc}", "prerequisite") from exc
    if p.returncode:
        raise VerificationError(f"git probe failed: {' '.join(args)}", "prerequisite")
    return p.stdout


def _file_record(path):
    try:
        before = path.lstat()
    except FileNotFoundError:
        return {"missing": True}
    record = {"mode": stat.S_IMODE(before.st_mode)}
    if stat.S_ISLNK(before.st_mode):
        record["target"] = os.readlink(path)
    elif stat.S_ISREG(before.st_mode):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise VerificationError("file replaced during fingerprint", "source-changed")
            digest = hashlib.sha256()
            while chunk := os.read(fd, 1024 * 1024):
                digest.update(chunk)
            after = os.fstat(fd)
            if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise VerificationError("file changed during fingerprint", "source-changed")
            record["sha256"] = digest.hexdigest()
        finally:
            os.close(fd)
    elif stat.S_ISDIR(before.st_mode):
        record["directory"] = True
    else:
        raise VerificationError(f"unsupported input type: {path}", "prerequisite")
    return record


def _input_path(root, value):
    path = Path(os.path.abspath(root / value))
    if not path.is_relative_to(root) or not path.parent.resolve().is_relative_to(root):
        raise VerificationError(f"input escapes repository: {value}", "prerequisite")
    return path


def fingerprint(root, inputs):
    """Endpoints bind stable dirty trees; this is not a filesystem event monitor."""
    root = root.resolve(strict=True)
    top = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if root != top:
        raise VerificationError("project/dependency must be a repository root", "prerequisite")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    staged = _git(root, "ls-files", "--stage", "-z")
    index_path = Path(os.fsdecode(_git(root, "rev-parse", "--git-path", "index")).strip())
    if not index_path.is_absolute():
        index_path = root / index_path
    paths = {os.fsdecode(p) for p in _git(root, "ls-files", "-z").split(b"\0") if p}
    for value in inputs:
        path = _input_path(root, value)
        if not path.exists() and not path.is_symlink():
            raise VerificationError(f"declared input missing: {value}", "prerequisite")
        paths.add(str(path.relative_to(root)))
        if path.is_dir() and not path.is_symlink():
            for base, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [d for d in dirs if d != ".git"]
                for name in dirs + files:
                    paths.add(str((Path(base) / name).relative_to(root)))
    records = {p: _file_record(_input_path(root, p)) for p in sorted(paths)}
    result = {"root": str(root), "head": head, "index": _file_record(index_path),
              "staged_sha256": _sha(staged), "files": records,
              "dirty": bool(_git(root, "status", "--porcelain", "--untracked-files=no"))}
    result["sha256"] = _sha(_json(result))
    return result


class Evidence:
    """Anchored openat writes; no symlink traversal, exclusive private run dirs."""
    def __init__(self, destination, roots):
        path = Path(os.path.abspath(destination))
        resolved = path.resolve()
        if any(resolved.is_relative_to(root) or root.is_relative_to(resolved) for root in roots):
            raise VerificationError("evidence must be separate from source/dependency trees", "containment")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in path.parts[1:]:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                try:
                    child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except OSError as exc:
                    raise VerificationError(f"cannot safely open evidence component {component}: {exc}", "containment") from exc
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise VerificationError("evidence base must be owned and private (0700)", "containment")
            name = "verify-" + uuid.uuid4().hex
            os.mkdir(name, mode=0o700, dir_fd=fd)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.fsync(fd)
            self.path, self.fd = path / name, child
            self.artifacts = []
        finally:
            os.close(fd)

    def check_location(self):
        current = os.stat(self.path, follow_symlinks=False)
        held = os.fstat(self.fd)
        if self.path.resolve() != self.path or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise VerificationError("evidence directory moved or replaced", "containment")

    def create(self, name):
        return os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)

    def record(self, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise VerificationError("artifact is not a private regular file", "containment")
            digest, size = hashlib.sha256(), 0
            while chunk := os.read(fd, 1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            artifact = {"path": name, "sha256": digest.hexdigest(), "bytes": size}
            self.artifacts.append(artifact)
            return artifact
        finally:
            os.close(fd)

    def write(self, name, data):
        fd = self.create(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return self.record(name)

    def receipt(self, data):
        self.check_location()
        for artifact in list(self.artifacts):
            observed = self.record(artifact["path"])
            self.artifacts.pop()
            if observed != artifact:
                raise VerificationError("artifact changed before receipt", "persistence")
        raw = _json(data) + b"\n"
        self.write("receipt.pending", raw)
        os.rename("receipt.pending", "receipt.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)
        self.check_location()
        return str(self.path / "receipt.json"), _sha(raw)

    def close(self):
        os.close(self.fd)


def _kill_group(proc):
    killed = False
    try:
        os.killpg(proc.pid, signal.SIGKILL)
        killed = True
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        raise VerificationError("process group cleanup permission denied", "containment") from exc
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired as exc:
        raise VerificationError("process group cleanup incomplete", "containment") from exc
    return killed


def _run(argv, cwd, env, evidence, name, timeout, output_limit, cancel):
    """Drain one merged pipe without communicate()'s unbounded memory/wait."""
    start, started = time.monotonic(), time.time_ns()
    result = {"argv": argv, "started_ns": started, "exit_status": None,
              "output_bytes": 0, "failure_kind": None, "log": name,
              "drained_after_leader_exit": False}
    proc = None
    cleaned = False
    tail = b""
    fd = evidence.create(name)
    try:
        with os.fdopen(fd, "wb") as log, selectors.DefaultSelector() as selector:
            # Compare report freshness within this filesystem's clock domain.
            # Kernel inode timestamps can lag time.time_ns() on a fresh write.
            result["filesystem_started_ns"] = os.fstat(log.fileno()).st_mtime_ns
            try:
                proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as exc:
                raise VerificationError(f"launch failed: {exc}", "launch") from exc
            os.set_blocking(proc.stdout.fileno(), False)
            selector.register(proc.stdout, selectors.EVENT_READ)
            exited_at = None
            while True:
                now = time.monotonic()
                if cancel.is_set():
                    result["failure_kind"] = "cancelled"
                    break
                if now - start >= timeout:
                    result["failure_kind"] = "timeout"
                    break
                status = proc.poll()
                if status is not None:
                    exited_at = exited_at or now
                    if not selector.get_map():
                        break
                    result["drained_after_leader_exit"] = True
                    if now - exited_at > .3:
                        result["failure_kind"] = "incomplete-output"
                        break
                for key, _ in selector.select(.02):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = output_limit - result["output_bytes"]
                    retained = chunk[:available]
                    log.write(retained)
                    result["output_bytes"] += len(retained)
                    tail = (tail + retained)[-3000:]
                    if len(chunk) > available:
                        result["failure_kind"] = "output-limit"
                        break
                if result["failure_kind"]:
                    break
            # After bounded output drain, kill any group members still running.
            # Short-lived descendants may have finished during the drain window.
            if _kill_group(proc) and result["failure_kind"] is None:
                result["failure_kind"] = "incomplete-processes"
            cleaned = True
            result["exit_status"] = proc.returncode
            log.flush()
            os.fsync(log.fileno())
    finally:
        if proc is not None:
            try:
                if not cleaned:
                    _kill_group(proc)
            finally:
                proc.stdout.close()
    evidence.record(name)
    result.update(ended_ns=time.time_ns(), duration_s=time.monotonic()-start,
                  excerpt=tail.decode("utf-8", errors="replace"))
    return result


def _contains(evidence, name, needle):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=evidence.fd)
    overlap = b""
    try:
        while chunk := os.read(fd, max(65536, len(needle))):
            chunk = overlap + chunk
            if needle in chunk:
                return True
            overlap = chunk[-(len(needle)-1):] if len(needle) > 1 else b""
        return False
    finally:
        os.close(fd)


def _junit(evidence, name, config, filesystem_started_ns):
    """Strict pytest xunit2 shape: one suite, counts agree with testcase outcomes."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=evidence.fd)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mtime_ns < filesystem_started_ns:
                raise ValueError("stale or non-regular report")
            data = stream.read(OUTPUT_LIMIT + 1)
            if len(data) > OUTPUT_LIMIT or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                raise ValueError("oversized or unsupported XML report")
        root = ET.fromstring(data)
        if root.tag != "testsuites" or len(root) != 1 or root[0].tag != "testsuite":
            raise ValueError("expected one pytest testsuite")
        suite = root[0]
        allowed = {
            "testsuites": {"testsuite"},
            "testsuite": {"testcase", "properties", "system-out", "system-err"},
            "testcase": {"failure", "error", "skipped", "properties", "system-out", "system-err"},
            "properties": {"property"},
        }
        for parent in root.iter():
            if any(child.tag not in allowed.get(parent.tag, set()) for child in parent):
                raise ValueError("unsupported nested suite or report element")
        cases = suite.findall("testcase")
        counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
        actual = {"tests": len(cases), "failures": sum(len(c.findall("failure")) for c in cases),
                  "errors": sum(len(c.findall("error")) for c in cases),
                  "skipped": sum(len(c.findall("skipped")) for c in cases)}
        if counts != actual or any(v < 0 for v in counts.values()):
            raise ValueError("inconsistent test counts")
        if any(sum(len(c.findall(t)) for t in ("failure", "error", "skipped")) > 1 for c in cases):
            raise ValueError("inconsistent testcase outcomes")
        executed = counts["tests"] - counts["skipped"]
        if executed <= 0:
            raise ValueError("zero executed tests")
        # Persist an immutable copy; assertions and digest use these exact bytes.
        artifact = evidence.write(name + ".retained", data)
        return {**counts, "executed": executed, "artifact": artifact,
                "passed": executed >= config.get("min_executed", 1)
                and counts["skipped"] <= config.get("max_skipped", 0)
                and counts["failures"] == 0 and counts["errors"] == 0}
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        raise VerificationError(f"invalid pytest report: {exc}", "test-report") from exc


def _executable(name, root):
    return shutil.which(str(root / name) if "/" in name else name)


def verify(raw, project_dir, evidence_dir, *, run_id=None, task_id="verification", attempt=0, cancel=None):
    """Return structured evidence. Operational failures are never repairable."""
    cancel = cancel or threading.Event()
    run_id = run_id or str(uuid.uuid4())
    started = time.time_ns()
    evidence, spec, before, after, inventory, checks = None, None, [], [], [], []
    failure, detail, receipt_path, receipt_hash = None, "", None, None
    optional_empty = False
    manifest_hash = None
    try:
        spec = validate_spec(raw)
        manifest_hash = _sha(_json(raw))
        _string(run_id)
        _string(task_id)
        _limit(attempt, integer=True, minimum=-1)
        root = Path(project_dir).resolve(strict=True)
        pre = spec.get("prerequisites", {})
        repositories = [(root, spec.get("inputs", []))]
        for dep in pre.get("repositories", []):
            path = (root / dep["path"]).resolve(strict=True)
            actual = _git(path, "rev-parse", "HEAD").decode().strip()
            if actual != dep["revision"]:
                raise VerificationError(f"wrong dependency revision: {path}", "prerequisite")
            repositories.append((path, dep.get("inputs", [])))
        for path in pre.get("paths", []):
            if not (root / path).exists():
                raise VerificationError(f"missing prerequisite: {path}", "prerequisite")
        before = [fingerprint(path, inputs) for path, inputs in repositories]
        evidence = Evidence(evidence_dir, [path for path, _ in repositories])
        env = {k: v for k, v in os.environ.items()
               if k not in {"BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "CDPATH", "LD_PRELOAD",
                            "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH"}
               and not k.startswith("BASH_FUNC_")}
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env["VERIFY_EVIDENCE_DIR"] = str(evidence.path)
        for i, exe in enumerate(pre.get("executables", [])):
            found = _executable(exe["name"], root)
            if not found:
                raise VerificationError(f"missing executable: {exe['name']}", "prerequisite")
            path = Path(found).resolve(strict=True)
            identity = _file_record(path)
            if "path" in exe and path != (root / exe["path"]).resolve(strict=True):
                raise VerificationError(f"wrong executable path: {exe['name']}", "prerequisite")
            if "sha256" in exe and identity.get("sha256") != exe["sha256"]:
                raise VerificationError(f"wrong executable hash: {exe['name']}", "prerequisite")
            probe = _run([str(path), *exe.get("version_args", ["--version"])], root, env, evidence,
                         f"executable.{i}.log", 10, 1024*1024, cancel)
            if probe["failure_kind"] or probe["exit_status"] != 0:
                raise VerificationError(f"version probe unavailable: {exe['name']}", probe["failure_kind"] or "prerequisite")
            if "version_contains" in exe and not _contains(evidence, probe["log"], exe["version_contains"].encode()):
                raise VerificationError(f"wrong executable version: {exe['name']}", "prerequisite")
            inventory.append({"name": exe["name"], "resolved_path": str(path), **identity, "version": probe})
        for check in spec["checks"]:
            count_config = check.get("test_count")
            report_name = count_config["report"] if count_config else None
            if report_name and os.path.lexists(evidence.path / report_name):
                raise VerificationError("report already exists before check", "test-report")
            execution = _run(["/bin/bash", "-e", "-o", "pipefail", "-c", check["run"]], root, env, evidence,
                             check["id"] + ".log", check.get("timeout", spec.get("timeout", TIMEOUT)),
                             check.get("output_limit", spec.get("output_limit", OUTPUT_LIMIT)), cancel)
            execution.update(id=check["id"], command=check["run"], expectation=check["expect"])
            checks.append(execution)
            if execution["failure_kind"]:
                raise VerificationError("check did not complete: " + check["id"], execution["failure_kind"])
            kind, value = expectation(check["expect"])
            execution["passed"] = (execution["exit_status"] == value if kind == "exit" else
                                   execution["exit_status"] == 0 and _contains(evidence, execution["log"], value))
            if count_config:
                execution["test_count"] = _junit(evidence, report_name, count_config, execution["filesystem_started_ns"])
                execution["passed"] &= execution["test_count"]["passed"]
        optional_empty = not spec["checks"] and not spec.get("required", True)
        if any(not c["passed"] for c in checks):
            failure, detail = "assertion", "completed assertion failed"
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        failure, detail = getattr(exc, "kind", "prerequisite"), str(exc)
    except KeyboardInterrupt:
        failure, detail = "cancelled", "verification cancelled"
    # Snapshot even failed runs; source or executable drift outranks assertions.
    if evidence:
        try:
            after = [fingerprint(path, inputs) for path, inputs in repositories]
            if before != after:
                raise VerificationError("source or index changed during verification", "source-changed")
            for exe in inventory:
                found = _executable(exe["name"], root)
                if not found or str(Path(found).resolve()) != exe["resolved_path"] or _file_record(Path(found).resolve()).get("sha256") != exe["sha256"]:
                    raise VerificationError("declared executable changed", "source-changed")
        except (OSError, ValueError) as exc:
            failure, detail = getattr(exc, "kind", "source-changed"), str(exc)
    if cancel.is_set():
        failure, detail = "cancelled", "verification cancelled"
    state = ("UNVERIFIABLE" if optional_empty or failure not in (None, "assertion", "timeout") else
             "FAILED_VERIFICATION" if failure else "VERIFIED")
    eligible = state == "VERIFIED" and bool(checks)
    lines = [state + (f" ({failure})" if failure else ""), detail]
    if optional_empty:
        lines.append("Explicitly optional: no verify entries; no machine acceptance or vetting signal.")
    for check in sorted(checks, key=lambda check: bool(check.get("passed"))):
        lines.append(f"{'PASS' if check.get('passed') else 'FAIL'}: {check['id']} (expect {check['expectation']}) log={check['log']}")
        if not check.get("passed"):
            lines.append(check["excerpt"][-1200:])
    summary = "\n".join(lines)[:4800]
    if evidence:
        try:
            receipt_path, receipt_hash = evidence.receipt({
                "schema": 1, "run_id": run_id, "task_id": task_id, "attempt": attempt,
                "manifest_sha256": manifest_hash, "spec": spec, "started_ns": started,
                "ended_ns": time.time_ns(), "state": state, "failure_kind": failure,
                "machine_eligible": eligible, "detail": detail, "before": before, "after": after,
                "executable_inventory": inventory, "checks": checks, "artifacts": list(evidence.artifacts),
                "coverage": "tracked source, index, declared inputs/dependencies/executables; endpoint snapshots; no shell executable census",
                "usage": {"subscription_allowance": None, "api_cost": None, "verification_model_turns": 0},
                "summary": summary})
            reference = f"\nReceipt: {receipt_path}\nSHA256: {receipt_hash}"
            summary = summary[:SUMMARY_LIMIT - len(reference)] + reference
        except (OSError, ValueError) as exc:
            failure, state, eligible = getattr(exc, "kind", "persistence"), "UNVERIFIABLE", False
            receipt_path = None
            summary = f"UNVERIFIABLE ({failure}): receipt persistence failed: {exc}"
        finally:
            evidence.close()
    summary = summary[:SUMMARY_LIMIT]
    constructor = {"VERIFIED": VerificationStep.verified, "FAILED_VERIFICATION": VerificationStep.failed,
                   "UNVERIFIABLE": VerificationStep.unverifiable}[state]
    step = constructor("task-verification", summary, run_uuid=run_id,
                       decision_type=failure or ("skipped" if optional_empty else "checked"),
                       task_id=task_id, attempt=attempt, receipt_path=receipt_path,
                       receipt_sha256=receipt_hash, machine_eligible=eligible)
    return VerificationResult(step, summary, receipt_path, failure, eligible,
                              bool(receipt_path) and (eligible or optional_empty and failure is None),
                              bool(receipt_path) and failure == "assertion")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--task-id", default="verification")
    parser.add_argument("--attempt", type=int, default=0)
    args = parser.parse_args(argv)
    cancel = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: cancel.set())
    try:
        raw = json.loads(Path(args.spec).read_text(), object_pairs_hook=_unique_pairs)
    except (OSError, ValueError) as exc:
        print(VerificationStep.unverifiable("task-verification", f"invalid specification: {exc}").to_jsonl_line())
        return 2
    result = verify(raw, args.project_dir, args.evidence_dir, run_id=args.run_id,
                    task_id=args.task_id, attempt=args.attempt, cancel=cancel)
    print(result.step.to_jsonl_line())
    return 0 if result.machine_eligible else 1 if result.failure_kind in ("assertion", "timeout") else 2


if __name__ == "__main__":
    raise SystemExit(main())
