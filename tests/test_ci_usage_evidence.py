import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "ci-usage-evidence.py"


def subject():
    spec = importlib.util.spec_from_file_location("ci_usage_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity_hash(names):
    return hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()


def junit(names, *, failures=0, errors=0, skipped=0):
    cases = []
    for index, identity in enumerate(names):
        classname, name = identity.split("::", 1)
        child = ""
        if index < failures:
            child = '<failure message="failed" />'
        elif index < failures + errors:
            child = '<error message="error" />'
        elif index < failures + errors + skipped:
            child = '<skipped message="skipped" />'
        cases.append(f'<testcase classname="{classname}" name="{name}">{child}</testcase>')
    return (
        f'<testsuites><testsuite tests="{len(names)}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}">{"".join(cases)}</testsuite></testsuites>'
    )


def tap(names, *, failing=None, directive=None, plan=None):
    lines = [f"1..{len(names) if plan is None else plan}"]
    for number, name in enumerate(names, 1):
        state = "not ok" if name == failing else "ok"
        suffix = f" # {directive}" if name == directive else ""
        lines.append(f"{state} {number} {name}{suffix}")
    return "\n".join(lines) + "\n"


def write_reports(tmp_path, py_names=("pkg::test_a", "pkg::test_b"), tap_names=("shell a", "shell b"), **kwargs):
    junit_path = tmp_path / "usage.xml"
    tap_path = tmp_path / "dispatch.tap"
    junit_path.write_text(junit(py_names, **kwargs.get("junit_kwargs", {})))
    tap_path.write_text(tap(tap_names, **kwargs.get("tap_kwargs", {})))
    return junit_path, tap_path, list(py_names), list(tap_names)


def write_legacy_report(tmp_path, names=("legacy::test_a", "legacy::test_b")):
    root = tmp_path / "legacy-tmp"
    root.mkdir(mode=0o700)
    marker = tmp_path / "legacy-start.marker"
    marker.write_bytes(b"")
    marker.chmod(0o600)
    report_dir = root / "clavain-verification.ABC123" / "verify-0123456789abcdef"
    report_dir.mkdir(parents=True, mode=0o700)
    report = report_dir / "pilot.xml"
    report.write_text(junit(names))
    report.chmod(0o600)
    (report_dir / "receipt.json").write_text('{"state":"VERIFIED"}\n')
    step = report_dir.parent / "step.json"
    step_line = json.dumps({"name": "task-verification", "state": "VERIFIED"}, separators=(",", ":")) + "\n"
    step.write_text(step_line)
    with io.BytesIO() as archive:
        with tarfile.open(fileobj=archive, mode="w:gz") as bundle:
            bundle.add(step, arcname="step.json")
            bundle.add(report_dir.parent / report_dir.name, arcname=report_dir.name)
        payload = archive.getvalue()
    legacy_log = tmp_path / "legacy-verification.stdout"
    legacy_log.write_text(
        step_line
        + "BEGIN_VERIFICATION_EVIDENCE_TGZ_BASE64 sha256=" + hashlib.sha256(payload).hexdigest() + "\n"
        + base64.encodebytes(payload).decode("ascii")
        + "END_VERIFICATION_EVIDENCE_TGZ_BASE64\n"
    )
    legacy_log.chmod(0o600)
    os.utime(marker, ns=(1_000_000_000, 1_000_000_000))
    os.utime(report, ns=(2_000_000_000, 2_000_000_000))
    return root, marker, legacy_log, report, list(names)


def test_exact_junit_and_tap_evidence_is_summarized_privately(tmp_path):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    output = tmp_path / "summary.json"
    summary = module.validate(
        junit_path, len(py_names), identity_hash(py_names),
        tap_path, len(tap_names), identity_hash(tap_names), output,
    )
    assert summary == json.loads(output.read_text())
    assert summary["pytest"]["executed"] == 2
    assert summary["bats"]["executed"] == 2
    assert output.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("names", [(), ("pkg::test_a",), ("pkg::test_a", "pkg::test_a")])
def test_junit_rejects_missing_extra_or_duplicate_identities(tmp_path, names):
    module = subject()
    junit_path, tap_path, _, tap_names = write_reports(tmp_path, py_names=names)
    with pytest.raises(module.EvidenceFailure):
        module.validate(junit_path, 2, identity_hash(["pkg::test_a", "pkg::test_b"]),
                        tap_path, 2, identity_hash(tap_names), tmp_path / "summary.json")


@pytest.mark.parametrize("outcome", ["failures", "errors", "skipped"])
def test_junit_rejects_nonpassing_or_skipped_cases(tmp_path, outcome):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(
        tmp_path, junit_kwargs={outcome: 1})
    with pytest.raises(module.EvidenceFailure):
        module.validate(junit_path, 2, identity_hash(py_names),
                        tap_path, 2, identity_hash(tap_names), tmp_path / "summary.json")


@pytest.mark.parametrize("tap_kwargs", [
    {"failing": "shell a"}, {"directive": "shell a"}, {"plan": 3},
])
def test_tap_rejects_failure_skip_or_plan_mismatch(tmp_path, tap_kwargs):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path, tap_kwargs=tap_kwargs)
    with pytest.raises(module.EvidenceFailure):
        module.validate(junit_path, 2, identity_hash(py_names),
                        tap_path, 2, identity_hash(tap_names), tmp_path / "summary.json")


def test_tap_rejects_unknown_or_renumbered_lines(tmp_path):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    tap_path.write_text("1..2\nok 2 shell a\nthis is not TAP\nok 1 shell b\n")
    with pytest.raises(module.EvidenceError):
        module.validate(junit_path, 2, identity_hash(py_names),
                        tap_path, 2, identity_hash(tap_names), tmp_path / "summary.json")


def test_identity_drift_is_rejected_even_when_counts_match(tmp_path):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    with pytest.raises(module.EvidenceFailure):
        module.validate(junit_path, 2, identity_hash(["pkg::test_a", "pkg::renamed"]),
                        tap_path, 2, identity_hash(tap_names), tmp_path / "summary.json")


def test_summary_output_must_not_preexist(tmp_path):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    output = tmp_path / "summary.json"
    output.write_text("stale")
    with pytest.raises(module.EvidenceError):
        module.validate(junit_path, 2, identity_hash(py_names),
                        tap_path, 2, identity_hash(tap_names), output)


def test_exact_legacy_pilot_is_discovered_and_summarized(tmp_path):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    legacy_root, legacy_marker, legacy_log, legacy_report, legacy_names = write_legacy_report(tmp_path)
    output = tmp_path / "summary.json"
    summary = module.validate(
        junit_path, len(py_names), identity_hash(py_names),
        tap_path, len(tap_names), identity_hash(tap_names), output,
        legacy_root=legacy_root,
        legacy_marker=legacy_marker,
        legacy_log=legacy_log,
        legacy_count=len(legacy_names),
        legacy_digest=identity_hash(legacy_names),
    )
    assert summary["legacy_pytest"]["tests"] == 2
    assert summary["legacy_pytest"]["skipped"] == 0
    assert summary["legacy_pytest"]["report_sha256"] == hashlib.sha256(legacy_report.read_bytes()).hexdigest()
    assert summary["legacy_export"]["state"] == "VERIFIED"
    assert summary["legacy_export"]["archive_sha256"]


@pytest.mark.parametrize("problem", [
    "missing", "multiple", "stale", "truncated", "truncated_export", "missing_case", "skipped_case",
])
def test_legacy_pilot_rejects_incomplete_or_ambiguous_evidence(tmp_path, problem):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    legacy_root, legacy_marker, legacy_log, legacy_report, legacy_names = write_legacy_report(tmp_path)
    if problem == "missing":
        legacy_report.unlink()
    elif problem == "multiple":
        other = legacy_root / "clavain-verification.OTHER" / "verify-fedcba9876543210"
        other.mkdir(parents=True)
        (other / "pilot.xml").write_text(junit(legacy_names))
    elif problem == "stale":
        os.utime(legacy_marker, ns=(3_000_000_000, 3_000_000_000))
    elif problem == "truncated":
        legacy_report.write_text("<testsuites><testsuite")
    elif problem == "truncated_export":
        legacy_log.write_text(legacy_log.read_text().rsplit("\n", 2)[0])
    elif problem == "missing_case":
        legacy_report.write_text(junit(legacy_names[:-1]))
    else:
        legacy_report.write_text(junit(legacy_names, skipped=1))
    with pytest.raises(module.EvidenceError):
        module.validate(
            junit_path, len(py_names), identity_hash(py_names),
            tap_path, len(tap_names), identity_hash(tap_names), tmp_path / "summary.json",
            legacy_root=legacy_root,
            legacy_marker=legacy_marker,
            legacy_log=legacy_log,
            legacy_count=len(legacy_names),
            legacy_digest=identity_hash(legacy_names),
        )


@pytest.mark.parametrize("legacy_arg", [
    ("--legacy-root", "unused"),
    ("--legacy-marker", "unused"),
    ("--legacy-log", "unused"),
    ("--legacy-count", "2"),
    ("--legacy-identities-sha256", "0" * 64),
])
def test_cli_rejects_partial_legacy_contract(tmp_path, capsys, legacy_arg):
    module = subject()
    junit_path, tap_path, py_names, tap_names = write_reports(tmp_path)
    result = module.main([
        "--junit", str(junit_path),
        "--pytest-count", str(len(py_names)),
        "--pytest-identities-sha256", identity_hash(py_names),
        "--tap", str(tap_path),
        "--bats-count", str(len(tap_names)),
        "--bats-identities-sha256", identity_hash(tap_names),
        "--output", str(tmp_path / "summary.json"),
        *legacy_arg,
    ])
    assert result == 2
    assert "legacy arguments must be provided together" in capsys.readouterr().err
