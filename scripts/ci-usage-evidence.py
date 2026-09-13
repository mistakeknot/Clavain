#!/usr/bin/env python3
"""Fail-closed exact identity/count checks for the bounded usage CI evidence."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import xml.etree.ElementTree as ET


LIMIT = 64 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")
LEGACY_ARCHIVE_LIMIT = 32 * 1024 * 1024


class EvidenceError(ValueError):
    """The evidence cannot be safely or completely interpreted."""


class EvidenceFailure(EvidenceError):
    """The evidence is valid but does not satisfy the frozen test contract."""


def _read_regular(path: Path) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise EvidenceError(f"cannot safely open report {path.name}: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise EvidenceError(f"report is not a single-link regular file: {path.name}")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise EvidenceError(f"report changed while opening: {path.name}")
        data = bytearray()
        while chunk := os.read(fd, min(1024 * 1024, LIMIT + 1 - len(data))):
            data.extend(chunk)
            if len(data) > LIMIT:
                raise EvidenceError(f"report exceeds {LIMIT} bytes: {path.name}")
        after = os.fstat(fd)
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ):
            raise EvidenceError(f"report changed while reading: {path.name}")
        return bytes(data)
    finally:
        os.close(fd)


def _identity_digest(names: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()


def _require_expected(names: list[str], count: int, digest: str, label: str) -> None:
    if count <= 0 or not SHA256.fullmatch(digest):
        raise EvidenceError(f"invalid frozen {label} contract")
    if len(names) != count:
        raise EvidenceFailure(f"{label} count changed: expected {count}, observed {len(names)}")
    if len(set(names)) != len(names):
        raise EvidenceFailure(f"{label} identities contain duplicates")
    observed = _identity_digest(names)
    if observed != digest:
        raise EvidenceFailure(f"{label} identity set changed: {observed}")


def _parse_junit(path: Path, expected_count: int, expected_digest: str, *, label: str = "pytest") -> dict:
    data = _read_regular(path)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise EvidenceError("unsupported XML declaration")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise EvidenceError(f"invalid JUnit XML: {exc}") from exc
    if root.tag != "testsuites" or len(root) != 1 or root[0].tag != "testsuite":
        raise EvidenceError("expected one pytest xunit2 testsuite")
    suite = root[0]
    allowed = {
        "testsuites": {"testsuite"},
        "testsuite": {"testcase", "properties", "system-out", "system-err"},
        "testcase": {"failure", "error", "skipped", "properties", "system-out", "system-err"},
        "properties": {"property"},
    }
    for parent in root.iter():
        if any(child.tag not in allowed.get(parent.tag, set()) for child in parent):
            raise EvidenceError("unsupported JUnit element")
    cases = suite.findall("testcase")
    try:
        declared = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
    except (KeyError, ValueError) as exc:
        raise EvidenceError("missing or invalid JUnit counters") from exc
    actual = {
        "tests": len(cases),
        "failures": sum(len(case.findall("failure")) for case in cases),
        "errors": sum(len(case.findall("error")) for case in cases),
        "skipped": sum(len(case.findall("skipped")) for case in cases),
    }
    if declared != actual or any(value < 0 for value in declared.values()):
        raise EvidenceError("inconsistent JUnit counters")
    if any(sum(len(case.findall(tag)) for tag in ("failure", "error", "skipped")) > 1 for case in cases):
        raise EvidenceError("inconsistent JUnit testcase outcomes")
    names = []
    for case in cases:
        classname, name = case.attrib.get("classname"), case.attrib.get("name")
        if not classname or not name or "\0" in classname or "\0" in name:
            raise EvidenceError("JUnit testcase identity is incomplete")
        names.append(f"{classname}::{name}")
    _require_expected(names, expected_count, expected_digest, label)
    if declared["failures"] or declared["errors"] or declared["skipped"]:
        raise EvidenceFailure(
            "pytest outcomes are not all passing: "
            f"failures={declared['failures']} errors={declared['errors']} skipped={declared['skipped']}"
        )
    return {
        "tests": declared["tests"], "executed": declared["tests"],
        "failures": 0, "errors": 0, "skipped": 0,
        "identities": sorted(names), "identities_sha256": _identity_digest(names),
        "report_sha256": hashlib.sha256(data).hexdigest(),
    }


def _legacy_junit_path(root: Path, marker: Path) -> Path:
    root = Path(root)
    marker = Path(marker)
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise EvidenceError(f"cannot inspect legacy evidence root: {exc}") from exc
    if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid() or root_info.st_mode & 0o077:
        raise EvidenceError("legacy evidence root is not an owned private directory")
    _read_regular(marker)
    marker_info = marker.stat(follow_symlinks=False)

    try:
        candidates = []
        for path in root.iterdir():
            if not path.name.startswith("clavain-verification."):
                continue
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise EvidenceError("unsafe legacy verification directory entry")
            candidates.append(path)
        if len(candidates) != 1:
            raise EvidenceError(f"expected exactly one legacy verification directory, observed {len(candidates)}")
        reports = []
        for base, directories, files in os.walk(candidates[0], topdown=True, followlinks=False):
            base_path = Path(base)
            for name in directories:
                info = (base_path / name).lstat()
                if not stat.S_ISDIR(info.st_mode):
                    raise EvidenceError("unsafe legacy evidence directory entry")
            for name in files:
                path = base_path / name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise EvidenceError("unsafe legacy evidence file entry")
                if name == "pilot.xml":
                    reports.append(path)
    except OSError as exc:
        raise EvidenceError(f"cannot enumerate legacy evidence: {exc}") from exc
    if len(reports) != 1:
        raise EvidenceError(f"expected exactly one legacy pilot report, observed {len(reports)}")
    report = reports[0]
    parts = report.relative_to(root).parts
    if (len(parts) != 3 or not parts[0].startswith("clavain-verification.")
            or not parts[1].startswith("verify-") or parts[2] != "pilot.xml"):
        raise EvidenceError("legacy pilot report has an unexpected path")
    report_info = report.stat(follow_symlinks=False)
    if report_info.st_mtime_ns < marker_info.st_mtime_ns:
        raise EvidenceError("legacy pilot report predates this invocation")
    return report


def _legacy_export(log_path: Path, report_path: Path) -> dict:
    data = _read_regular(log_path)
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise EvidenceError("legacy verification output is not ASCII") from exc
    prefix = "BEGIN_VERIFICATION_EVIDENCE_TGZ_BASE64 sha256="
    if len(lines) < 4 or not lines[1].startswith(prefix) or lines[-1] != "END_VERIFICATION_EVIDENCE_TGZ_BASE64":
        raise EvidenceError("legacy verification output is missing its complete artifact export")
    expected_digest = lines[1][len(prefix):]
    if not SHA256.fullmatch(expected_digest):
        raise EvidenceError("legacy artifact export has an invalid digest")
    try:
        step = json.loads(lines[0])
        archive = base64.b64decode("".join(lines[2:-1]), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError(f"invalid legacy receipt or artifact export: {exc}") from exc
    if not isinstance(step, dict) or step.get("state") not in {"VERIFIED", "FAILED_VERIFICATION", "UNVERIFIABLE"}:
        raise EvidenceError("legacy verification receipt has an invalid state")
    if len(archive) > LEGACY_ARCHIVE_LIMIT:
        raise EvidenceError("legacy artifact export exceeds 32 MiB compressed limit")
    observed_digest = hashlib.sha256(archive).hexdigest()
    if observed_digest != expected_digest:
        raise EvidenceError("legacy artifact export digest mismatch")

    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            members = []
            for member in bundle:
                if len(members) >= 4096:
                    raise EvidenceError("legacy artifact export has too many entries")
                members.append(member)
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise EvidenceError("legacy artifact export has duplicate paths")
            total = 0
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
                    raise EvidenceError("legacy artifact export has an unsafe path")
                if not (member.isfile() or member.isdir()):
                    raise EvidenceError("legacy artifact export has an unsafe entry type")
                if member.isfile():
                    total += member.size
                    if member.size > LIMIT or total > LIMIT:
                        raise EvidenceError("legacy artifact export is too large when expanded")
            step_members = [member for member in members if member.name == "step.json" and member.isfile()]
            pilot_members = [member for member in members if member.name.endswith("/pilot.xml") and member.isfile()]
            receipt_members = [member for member in members if member.name.endswith("/receipt.json") and member.isfile()]
            if len(step_members) != 1 or len(pilot_members) != 1 or len(receipt_members) != 1:
                raise EvidenceError("legacy artifact export is missing its step, receipt or pilot report")
            archived_step = bundle.extractfile(step_members[0]).read()
            archived_pilot = bundle.extractfile(pilot_members[0]).read()
    except (OSError, tarfile.TarError) as exc:
        raise EvidenceError(f"invalid legacy artifact archive: {exc}") from exc
    if archived_step != (lines[0] + "\n").encode("ascii"):
        raise EvidenceError("legacy artifact step differs from captured receipt")
    if hashlib.sha256(archived_pilot).hexdigest() != hashlib.sha256(_read_regular(report_path)).hexdigest():
        raise EvidenceError("legacy artifact pilot differs from fresh report")
    if step["state"] != "VERIFIED":
        raise EvidenceFailure(f"legacy verification state is {step['state']}")
    return {
        "state": step["state"],
        "log_sha256": hashlib.sha256(data).hexdigest(),
        "archive_sha256": observed_digest,
        "archive_bytes": len(archive),
        "member_count": len(members),
    }


def _parse_tap(path: Path, expected_count: int, expected_digest: str) -> dict:
    data = _read_regular(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError("TAP is not UTF-8") from exc
    plan = None
    results = []
    result_pattern = re.compile(r"(not )?ok\s+([0-9]+)\s+(.+?)(?:\s+#\s*(skip|todo)\b.*)?", re.I)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line == "TAP version 13":
            continue
        match = re.fullmatch(r"1\.\.([0-9]+)", line)
        if match:
            if plan is not None:
                raise EvidenceError("duplicate TAP plan")
            plan = int(match.group(1))
            continue
        match = result_pattern.fullmatch(line)
        if not match:
            raise EvidenceError(f"unknown TAP line: {line[:120]}")
        failed, number, name, directive = match.groups()
        if not name or "\0" in name:
            raise EvidenceError("TAP identity is incomplete")
        results.append((int(number), name, bool(failed), directive and directive.lower()))
    if plan is None or plan != len(results):
        raise EvidenceFailure(f"TAP plan/result mismatch: plan={plan} results={len(results)}")
    if [number for number, *_ in results] != list(range(1, len(results) + 1)):
        raise EvidenceError("TAP result numbering is not exact and sequential")
    names = [name for _, name, _, _ in results]
    _require_expected(names, expected_count, expected_digest, "Bats")
    failures = sum(failed for _, _, failed, _ in results)
    skipped = sum(directive == "skip" for *_, directive in results)
    todos = sum(directive == "todo" for *_, directive in results)
    if failures or skipped or todos:
        raise EvidenceFailure(
            f"Bats outcomes are not all passing: failures={failures} skipped={skipped} todo={todos}"
        )
    return {
        "tests": len(results), "executed": len(results), "failures": 0, "skipped": 0, "todo": 0,
        "identities": sorted(names), "identities_sha256": _identity_digest(names),
        "report_sha256": hashlib.sha256(data).hexdigest(),
    }


def validate(junit_path: Path, pytest_count: int, pytest_digest: str,
             tap_path: Path, bats_count: int, bats_digest: str, output: Path, *,
             legacy_root: Path | None = None, legacy_marker: Path | None = None,
             legacy_log: Path | None = None, legacy_count: int | None = None,
             legacy_digest: str | None = None) -> dict:
    legacy_contract = (legacy_root, legacy_marker, legacy_log, legacy_count, legacy_digest)
    if any(value is not None for value in legacy_contract) and not all(
            value is not None for value in legacy_contract):
        raise EvidenceError("legacy arguments must be provided together")
    summary = {
        "schema": 1,
        "pytest": _parse_junit(junit_path, pytest_count, pytest_digest),
        "bats": _parse_tap(tap_path, bats_count, bats_digest),
    }
    if legacy_root is not None:
        report = _legacy_junit_path(legacy_root, legacy_marker)
        summary["legacy_pytest"] = _parse_junit(
            report, legacy_count, legacy_digest, label="legacy pytest")
        summary["legacy_export"] = _legacy_export(legacy_log, report)
    output = Path(output)
    encoded = json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise EvidenceError(f"cannot exclusively create summary: {exc}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            output.unlink()
        except OSError:
            pass
        raise
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--pytest-count", required=True, type=int)
    parser.add_argument("--pytest-identities-sha256", required=True)
    parser.add_argument("--tap", required=True, type=Path)
    parser.add_argument("--bats-count", required=True, type=int)
    parser.add_argument("--bats-identities-sha256", required=True)
    parser.add_argument("--legacy-root", type=Path)
    parser.add_argument("--legacy-marker", type=Path)
    parser.add_argument("--legacy-log", type=Path)
    parser.add_argument("--legacy-count", type=int)
    parser.add_argument("--legacy-identities-sha256")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        validate(args.junit, args.pytest_count, args.pytest_identities_sha256,
                 args.tap, args.bats_count, args.bats_identities_sha256, args.output,
                 legacy_root=args.legacy_root, legacy_marker=args.legacy_marker,
                 legacy_log=args.legacy_log,
                 legacy_count=args.legacy_count,
                 legacy_digest=args.legacy_identities_sha256)
    except EvidenceFailure as exc:
        print(f"FAILED_VERIFICATION: {exc}", file=sys.stderr)
        return 1
    except (EvidenceError, OSError, ValueError, TypeError) as exc:
        print(f"UNVERIFIABLE: {exc}", file=sys.stderr)
        return 2
    scope = "legacy pilot, usage pytest and dispatch Bats" if args.legacy_root else "usage pytest and dispatch Bats"
    print(f"VERIFIED: exact {scope} identities/counts; zero skips/failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
