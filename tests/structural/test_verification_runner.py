"""Real subprocess and filesystem regression tests for the bounded verifier."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest


@pytest.fixture
def runner(project_root):
    path = project_root / "scripts/verification_runner.py"
    assert path.exists(), "standalone verification runner has not been implemented"
    sys.path.insert(0, str(path.parent))
    import verification_runner
    return verification_runner


@pytest.fixture
def repo(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    (p / "source").write_text("original\n")
    subprocess.run(["git", "-C", str(p), "add", "source"], check=True)
    subprocess.run(["git", "-C", str(p), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "-qm", "initial"], check=True)
    return p


def spec(command="true", expect="exit 0", **config):
    return {"required": True, "checks": [{"id": "check", "run": command, "expect": expect}], **config}


def execute(runner, repo, tmp_path, contract=None, **kwargs):
    return runner.verify(contract or spec(), repo, tmp_path / "evidence",
                         run_id="pilot", task_id="task-1", attempt=0, **kwargs)


@pytest.mark.parametrize("command,expect,state", [
    ('echo expected; exit 7', 'contains "expected"', "FAILED_VERIFICATION"),
    ('false | tail -2', 'exit 0', "FAILED_VERIFICATION"),
    ('exit 7', 'exit 7', "VERIFIED"),
    ('echo expected', 'contains "expected"', "VERIFIED"),
    ('read ignored', 'exit 1', "VERIFIED"),
])
def test_exit_semantics(runner, repo, tmp_path, command, expect, state):
    result = execute(runner, repo, tmp_path, spec(command, expect))
    assert result.step.state.value == state
    assert result.machine_eligible == (state == "VERIFIED")


@pytest.mark.parametrize("bad", [
    {"expect": "exit zero"}, {"expect": 'contains "x" trailing'},
    {"expect": "success"}, {"extra": True}, {"run": ""},
    {"timeout": 0}, {"timeout": float('nan')}, {"output_limit": True},
])
def test_whole_contract_validated_before_execution(runner, repo, tmp_path, bad):
    contract = spec("touch should-not-run")
    contract["checks"].append({"id": "bad", "run": "true", "expect": "exit 0", **bad})
    result = execute(runner, repo, tmp_path, contract)
    assert result.step.state.value == "UNVERIFIABLE"
    assert not (repo / "should-not-run").exists()
    assert not result.repairable


@pytest.mark.parametrize("contract", [
    {"required": True, "checks": []},
    {"required": True, "checks": [{"id": "x", "run": "true", "expect": "exit 0"}]*2},
    {"required": False, "checks": [], "unknown": True},
    {"required": "false", "checks": []},
])
def test_invalid_contract(runner, repo, tmp_path, contract):
    result = execute(runner, repo, tmp_path, contract)
    assert result.step.state.value == "UNVERIFIABLE"
    assert not result.review_allowed


def test_optional_empty_has_no_machine_acceptance(runner, repo, tmp_path):
    result = execute(runner, repo, tmp_path, {"required": False, "checks": []})
    assert result.review_allowed
    assert not result.machine_eligible
    assert result.step.state.value == "UNVERIFIABLE"


@pytest.mark.parametrize("body", [
    '<verify>\n- run: `true`\n</verify>',
    '<verify>\n- run: `true`\n  expect: exit 0\n junk\n</verify>',
    '<verify>\n- run: `true`\n  expect: exit 0',
    '<verify x>\n</verify>',
    '<verify>\n- run: `true`\n  expect: unknown\n</verify>',
])
def test_strict_legacy_parser(runner, body):
    with pytest.raises(ValueError):
        runner.parse_verify_blocks(body)


def test_valid_legacy_parser(runner):
    assert runner.parse_verify_blocks('<verify>\n- run: `echo ok`\n  expect: contains "ok"\n</verify>') == [
        {"run": "echo ok", "expect": 'contains "ok"'}]


@pytest.mark.parametrize("prerequisites", [
    {"paths": ["missing"]},
    {"repositories": [{"path": "missing", "revision": "0"*40}]},
    {"repositories": [{"path": ".", "revision": "0"*40}]},
    {"executables": [{"name": "surely-no-such-verifier"}]},
    {"executables": [{"name": "bash", "sha256": "0"*64}]},
    {"executables": [{"name": "bash", "version_args": ["-c", "touch should-not-run"]}]},
])
def test_missing_and_wrong_prerequisites(runner, repo, tmp_path, prerequisites):
    result = execute(runner, repo, tmp_path, spec("touch should-not-run", prerequisites=prerequisites))
    assert result.step.state.value == "UNVERIFIABLE"
    assert not result.repairable
    assert not (repo / "should-not-run").exists()


def test_receipt_private_complete_hashed_and_compact(runner, repo, tmp_path):
    command = f"{sys.executable} -c 'print(\"needle\" + \"x\"*12000)'"
    result = execute(runner, repo, tmp_path, spec(command, 'contains "needle"'))
    assert result.machine_eligible
    receipt_path = Path(result.receipt_path)
    receipt = json.loads(receipt_path.read_text())
    assert receipt["run_id"] == "pilot" and receipt["attempt"] == 0
    assert len(result.summary) <= 6000
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    assert receipt_path.parent.stat().st_mode & 0o777 == 0o700
    for artifact in receipt["artifacts"]:
        data = (receipt_path.parent / artifact["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
    assert receipt["checks"][0]["output_bytes"] > 12000


@pytest.mark.parametrize("command,config,kind", [
    ('sleep 10 & wait', {"timeout": .15}, "timeout"),
    (f'{sys.executable} -c \'print("x"*100000)\'', {"output_limit": 1024}, "output-limit"),
])
def test_operational_limits(runner, repo, tmp_path, command, config, kind):
    start = time.monotonic()
    result = execute(runner, repo, tmp_path, spec(command, **config))
    assert time.monotonic() - start < 4
    assert result.failure_kind == kind
    assert not result.repairable and not result.machine_eligible


def test_cancellation(runner, repo, tmp_path):
    cancel = threading.Event()
    timer = threading.Timer(.15, cancel.set)
    timer.start()
    try:
        result = execute(runner, repo, tmp_path, spec("sleep 10"), cancel=cancel)
    finally:
        timer.join()
    assert result.failure_kind == "cancelled"
    assert result.step.state.value == "UNVERIFIABLE"


@pytest.mark.parametrize("command", ['echo changed >> source', 'git add source',
    'chmod +x source', 'echo changed >> declared'])
def test_source_changes_invalidate(runner, repo, tmp_path, command):
    (repo / "source").write_text("dirty before\n")
    (repo / "declared").write_text("input\n")
    result = execute(runner, repo, tmp_path, spec(command, inputs=["declared"]))
    assert result.failure_kind == "source-changed"
    assert not result.machine_eligible


def test_stable_dirty_work_preserved(runner, repo, tmp_path):
    (repo / "source").write_text("dirty before\n")
    (repo / "unrelated").write_text("do not touch\n")
    result = execute(runner, repo, tmp_path)
    assert result.machine_eligible
    assert (repo / "source").read_text() == "dirty before\n"
    assert (repo / "unrelated").read_text() == "do not touch\n"


def test_containment_and_symlink_rejected(runner, repo, tmp_path):
    for path in (repo / "evidence", tmp_path / "link"):
        if path.name == "link":
            path.symlink_to(repo, target_is_directory=True)
        result = runner.verify(spec(), repo, path)
        assert result.step.state.value == "UNVERIFIABLE"


@pytest.mark.parametrize("xml,eligible,kind", [
    ('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite></testsuites>', True, None),
    ('<testsuites><testsuite tests="0" failures="0" errors="0" skipped="0"/></testsuites>', False, "test-report"),
    ('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite></testsuites>', False, "test-report"),
    ('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="1"><testcase name="skip"><skipped/></testcase></testsuite></testsuites>', False, "test-report"),
    ('invalid', False, "test-report"),
])
def test_fresh_junit_counts(runner, repo, tmp_path, xml, eligible, kind):
    import shlex
    contract = spec('printf %s ' + shlex.quote(xml) + ' > "$VERIFY_EVIDENCE_DIR/junit.xml"')
    contract["checks"][0]["test_count"] = {"parser": "pytest-junit", "report": "junit.xml"}
    result = execute(runner, repo, tmp_path, contract)
    assert result.machine_eligible is eligible
    if kind:
        assert result.failure_kind == kind


def test_missing_report_cannot_pass(runner, repo, tmp_path):
    contract = spec()
    contract["checks"][0]["test_count"] = {"parser": "pytest-junit", "report": "junit.xml"}
    assert execute(runner, repo, tmp_path, contract).failure_kind == "test-report"


def test_persistence_failure_cannot_emit_pass(runner, repo, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated disk full")
    monkeypatch.setattr(runner.Evidence, "receipt", fail)
    result = execute(runner, repo, tmp_path)
    assert result.step.state.value == "UNVERIFIABLE"
    assert result.failure_kind == "persistence"
    assert result.receipt_path is None
    assert not result.review_allowed


def test_failed_log_write_cannot_emit_pass(runner, repo, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated disk full")
    monkeypatch.setattr(runner.Evidence, "create", fail)
    result = execute(runner, repo, tmp_path)
    assert result.step.state.value == "UNVERIFIABLE"
    assert not result.review_allowed


def test_escaped_output_descriptor_is_bounded(runner, repo, tmp_path):
    # This child escapes killpg but keeps stdout. Give it a short lifetime and
    # always explicitly clean it up: the runner must report incomplete evidence.
    import shlex
    child = "import os,time; os.setsid(); open('escaped.pid','w').write(str(os.getpid())); time.sleep(4)"
    command = shlex.quote(sys.executable) + " -c " + shlex.quote(child) + " & sleep .1"
    start = time.monotonic()
    try:
        result = execute(runner, repo, tmp_path, spec(command, timeout=2))
        assert time.monotonic() - start < 2
        assert result.failure_kind == "incomplete-output"
        assert not result.repairable
    finally:
        if (repo / "escaped.pid").exists():
            try:
                os.kill(int((repo / "escaped.pid").read_text()), 9)
            except ProcessLookupError:
                pass


def test_timeout_kills_descendant(runner, repo, tmp_path):
    result = execute(runner, repo, tmp_path, spec('(sleep .5; touch survived) & wait', timeout=.15))
    assert result.failure_kind == "timeout"
    time.sleep(.6)
    assert not (repo / "survived").exists(), "timeout descendant was still able to write"


def test_stale_report_rejected(runner, repo, tmp_path):
    contract = spec('echo stale > "$VERIFY_EVIDENCE_DIR/junit.xml"; touch -t 200001010000 "$VERIFY_EVIDENCE_DIR/junit.xml"')
    contract["checks"][0]["test_count"] = {"parser": "pytest-junit", "report": "junit.xml"}
    assert execute(runner, repo, tmp_path, contract).failure_kind == "test-report"


@pytest.mark.parametrize("stale", [False, True])
def test_report_freshness_uses_filesystem_clock(runner, repo, tmp_path, monkeypatch, stale):
    # Linux filesystem timestamps can lag CLOCK_REALTIME even for a fresh write.
    import shlex
    wall_time = time.time_ns
    monkeypatch.setattr(runner.time, "time_ns", lambda: wall_time() + 2_000_000_000)
    xml = '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite></testsuites>'
    command = 'printf %s ' + shlex.quote(xml) + ' > "$VERIFY_EVIDENCE_DIR/junit.xml"'
    if stale:
        command += '; touch -t 200001010000 "$VERIFY_EVIDENCE_DIR/junit.xml"'
    contract = spec(command)
    contract["checks"][0]["test_count"] = {"parser": "pytest-junit", "report": "junit.xml"}
    result = execute(runner, repo, tmp_path, contract)
    assert result.machine_eligible is (not stale)
    assert result.failure_kind == ("test-report" if stale else None)


def test_reused_report_rejected_before_second_command(runner, repo, tmp_path):
    contract = spec('echo stale > "$VERIFY_EVIDENCE_DIR/junit.xml"')
    contract["checks"].append({"id": "second", "run": "touch should-not-run", "expect": "exit 0",
        "test_count": {"parser": "pytest-junit", "report": "junit.xml"}})
    result = execute(runner, repo, tmp_path, contract)
    assert result.failure_kind == "test-report"
    assert not (repo / "should-not-run").exists()


def test_duplicate_declared_reports_rejected_before_any_command(runner, repo, tmp_path):
    contract = spec('touch first-ran')
    count = {"parser": "pytest-junit", "report": "duplicate.xml"}
    contract['checks'][0]['test_count'] = count
    contract['checks'].append({'id': 'second', 'run': 'true', 'expect': 'exit 0', 'test_count': count})
    result = execute(runner, repo, tmp_path, contract)
    assert result.failure_kind == 'contract'
    assert not (repo / 'first-ran').exists()


def test_executable_inventory(runner, repo, tmp_path):
    result = execute(runner, repo, tmp_path, spec(prerequisites={"executables": [{"name": "bash"}]}))
    assert result.machine_eligible
    inventory = json.loads(Path(result.receipt_path).read_text())["executable_inventory"]
    assert len(inventory) == 1 and inventory[0]["sha256"]
    assert inventory[0]["version"]["exit_status"] == 0


def test_git_status_does_not_invalidate_stale_stat_cache(runner, repo, tmp_path):
    os.utime(repo / "source", (0, 0))
    assert execute(runner, repo, tmp_path, spec('git status --porcelain')).machine_eligible


def test_exported_bash_function_cannot_shadow_inventory(runner, repo, tmp_path, monkeypatch):
    monkeypatch.setenv('BASH_FUNC_git%%', '() { echo HIJACKED; }')
    contract = spec('git --version', expect='contains "git version"',
                    prerequisites={"executables": [{"name": "git"}]})
    assert execute(runner, repo, tmp_path, contract).machine_eligible


def test_executable_probe_cannot_collide_with_check_log(runner, repo, tmp_path):
    contract = spec(prerequisites={"executables": [{"name": "bash"}]})
    contract['checks'][0]['id'] = 'executable-0'
    assert execute(runner, repo, tmp_path, contract).machine_eligible


def test_relative_toolchain_probe_missing_module_is_prerequisite(runner, repo, tmp_path, monkeypatch):
    import shutil
    probe = repo / 'toolchain.py'
    shutil.copyfile(Path(runner.__file__).with_name('verification-toolchain.py'), probe)
    probe.chmod(0o755)
    modules = tmp_path / 'modules'
    modules.mkdir()
    (modules / 'yaml.py').write_text('raise ImportError("missing YAML fixture")\n')
    monkeypatch.setenv('PYTHONPATH', str(modules))
    contract = spec('touch should-not-run', prerequisites={'executables': [{'name': './toolchain.py'}]})
    result = execute(runner, repo, tmp_path, contract)
    assert result.failure_kind == 'prerequisite'
    assert not result.repairable and not (repo / 'should-not-run').exists()
    receipt = json.loads(Path(result.receipt_path).read_text())
    assert receipt['artifacts'], 'the module probe must actually run, not fail path lookup'


@pytest.mark.parametrize('raw,code', [
    ('{"checks":[{"run":"true","expect":"exit 0"}]}', 0),
    ('{"checks":[{"run":"false","expect":"exit 0"}]}', 1),
    ('{"checks":[],"required":false}', 2),
    ('{"checks":[],"checks":[]}', 2),
    ('{broken', 2),
])
def test_cli_exit_contract(runner, repo, tmp_path, raw, code):
    source = tmp_path / 'spec.json'
    source.write_text(raw)
    result = subprocess.run([sys.executable, runner.__file__, '--spec', str(source),
                             '--project-dir', str(repo), '--evidence-dir', str(tmp_path / 'cli-evidence')],
                            capture_output=True, text=True)
    assert result.returncode == code
    assert json.loads(result.stdout)['state'] in {'VERIFIED', 'FAILED_VERIFICATION', 'UNVERIFIABLE'}


def test_dependency_change_invalidates(runner, repo, tmp_path):
    dep = tmp_path / "dependency"
    subprocess.run(["git", "clone", "-q", str(repo), str(dep)], check=True)
    revision = subprocess.check_output(["git", "-C", str(dep), "rev-parse", "HEAD"], text=True).strip()
    contract = spec('echo changed >> ../dependency/source', prerequisites={"repositories": [
        {"path": str(dep), "revision": revision}]})
    result = execute(runner, repo, tmp_path, contract)
    assert result.failure_kind == "source-changed"


def test_launch_failure_is_operational(runner, repo, tmp_path, monkeypatch):
    launch = runner.subprocess.Popen
    def fail_bash(argv, *args, **kwargs):
        if argv[0] == "/bin/bash":
            raise OSError("not executable")
        return launch(argv, *args, **kwargs)
    monkeypatch.setattr(runner.subprocess, "Popen", fail_bash)
    result = execute(runner, repo, tmp_path)
    assert result.failure_kind == "launch"
    assert not result.repairable


def test_background_work_with_closed_output_is_not_a_completed_check(runner, repo, tmp_path):
    result = execute(runner, repo, tmp_path, spec('(sleep .5; touch survived) >/dev/null 2>&1 &'))
    assert result.step.state.value == "UNVERIFIABLE"
    assert result.failure_kind == "incomplete-processes"
    time.sleep(.6)
    assert not (repo / "survived").exists()


def test_nested_junit_suite_cannot_hide_tests(runner, repo, tmp_path):
    import shlex
    xml = '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/><testsuite tests="1"><testcase name="bad"><failure/></testcase></testsuite></testsuite></testsuites>'
    contract = spec('printf %s ' + shlex.quote(xml) + ' > "$VERIFY_EVIDENCE_DIR/junit.xml"')
    contract["checks"][0]["test_count"] = {"parser": "pytest-junit", "report": "junit.xml"}
    assert execute(runner, repo, tmp_path, contract).failure_kind == "test-report"


@pytest.mark.parametrize('hidden', [
    '<properties><testcase name="hidden"><failure/></testcase></properties>',
    '<testcase name="ok"><properties><failure/></properties></testcase>',
])
def test_nested_junit_outcomes_cannot_be_ignored(runner, repo, tmp_path, hidden):
    import shlex
    cases = '<testcase name="ok"/>' if hidden.startswith('<properties>') else ''
    xml = '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">' + cases + hidden + '</testsuite></testsuites>'
    contract = spec('printf %s ' + shlex.quote(xml) + ' > "$VERIFY_EVIDENCE_DIR/junit.xml"')
    contract["checks"][0]["test_count"] = {"parser": "pytest-junit", "report": "junit.xml"}
    assert execute(runner, repo, tmp_path, contract).failure_kind == "test-report"


def test_process_group_cleanup_has_one_owner(runner, repo, tmp_path, monkeypatch):
    cleanup = runner._kill_group
    calls = []
    def count(proc):
        calls.append(proc.pid)
        return cleanup(proc)
    monkeypatch.setattr(runner, "_kill_group", count)
    assert execute(runner, repo, tmp_path).machine_eligible
    assert len(calls) == 1


def test_summary_keeps_failure_when_many_checks_pass(runner, repo, tmp_path):
    contract = {"required": True, "checks": [
        {"id": f"passing-{i}-" + "x"*65, "run": "true", "expect": "exit 0"}
        for i in range(60)] + [
        {"id": "last", "run": "echo late failure evidence; false", "expect": "exit 0"}]}
    result = execute(runner, repo, tmp_path, contract)
    assert len(result.summary) <= 6000
    assert "late failure evidence" in result.summary
    assert result.receipt_path in result.summary
