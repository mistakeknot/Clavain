import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


def subject():
    path = Path(__file__).parents[1] / "scripts/dispatch_control.py"
    spec = importlib.util.spec_from_file_location("dispatch_control", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def make_protocol_pin(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    schema = tmp_path / "native-schema"
    schema.mkdir()
    (schema / "required.json").write_text('{"title":"fixture"}\n')
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    manifest = tmp_path / "native-schema-manifest.json"
    value = {
        "schema_version": 1,
        "codex_executable": str(executable),
        "executable_sha256": digest(executable),
        "codex_version": "codex-cli fixture",
        "experimental": True,
        "files": [{"path": "required.json", "sha256": digest(schema / "required.json")}],
    }
    manifest.write_text(json.dumps(value) + "\n")
    return manifest, executable


def make_binding(tmp_path, operation="compact"):
    m = subject()
    manifest, executable = make_protocol_pin(tmp_path)
    source = tmp_path / "source.json"
    policy = tmp_path / "routing.yaml"
    events = tmp_path / "seed.events.jsonl"
    capability = tmp_path / "capability.json"
    for path, body in ((source, "source-v1\n"), (policy, "policy-v1\n")):
        path.write_text(body)
    thread = "018f47bb-4e58-7abc-8def-0123456789ab"
    events.write_text(json.dumps({"type": "thread.started", "thread_id": thread}) + "\n")
    request = {
        "model": "gpt-fixture", "modelProvider": "openai", "cwd": str(tmp_path),
        "runtimeWorkspaceRoots": [str(tmp_path)], "approvalPolicy": "never",
        "approvalsReviewer": "user", "sandbox": "workspace-write", "serviceTier": "default",
        "baseInstructions": "governed base", "developerInstructions": "scoped skill body",
        "config": {"model_reasoning_effort": "high", "sandbox_workspace_write.network_access": False},
        "excludeTurns": True,
    }
    effective = {
        "model": "gpt-fixture", "modelProvider": "openai", "reasoningEffort": "high",
        "serviceTier": "default", "cwd": str(tmp_path), "runtimeWorkspaceRoots": [str(tmp_path)],
        "approvalPolicy": "never", "approvalsReviewer": "user",
        "sandbox": {"type": "workspaceWrite", "networkAccess": False},
        "activePermissionProfile": None, "instructionSources": [],
    }
    configuration = {"request": request, "effective": effective}
    configuration["sha256"] = hashlib.sha256(canonical(configuration).encode()).hexdigest()
    cap = {
        "schema_version": 1, "status": "verified", "native_thread_id": thread,
        "source_sha256": digest(source), "policy_sha256": digest(policy),
        "executable_sha256": digest(executable), "configuration_sha256": configuration["sha256"],
        "native_schema_manifest_sha256": digest(manifest),
        "verified": {
            "model_provider_effort_tier": True, "cwd_and_writable_roots": True,
            "approval_reviewer_sandbox_network": True, "instructions_config_and_skills": True,
            "exclude_turns_suppresses_history": True,
        },
    }
    capability.write_text(json.dumps(cap) + "\n")
    execution_context = {
        "schema_version": 1, "dispatch_id": "dispatch-seed", "attempt_id": "attempt-seed",
        "state": "completed", "resolved_route": {"policy_source": str(policy), "policy_hash": digest(policy)},
        "resolved_profile": {"profile": {"role": "routine-execution"}},
        "execution": {
            "backend": "codex", "model": "gpt-fixture", "reasoning_effort": "high",
            "service_tier": "default", "executable": str(executable),
            "executable_sha256": digest(executable), "configuration_sha256": configuration["sha256"],
            "source_path": str(source), "source_sha256": digest(source), "event_log": str(events),
            "native_schema_manifest": {"path": str(manifest), "sha256": digest(manifest)},
            "native_capability_evidence": {"path": str(capability), "sha256": digest(capability), "status": "verified"},
            "arm_id": "arm-a",
        },
        "task_envelope": {"enrollment_id": "enroll-a", "cohort_id": "cohort-a", "manifest_sha256": "a" * 64},
        "result": {"exit_code": 0},
    }
    receipt = tmp_path / "seed.receipt.json"
    receipt.write_text(json.dumps(execution_context) + "\n")
    binding = {
        "schema_version": 1, "arm_id": "arm-a",
        "authority": {
            "database": str(tmp_path / "intercore.db"), "enrollment_decision_id": 1,
            "dispatch_request_decision_id": 2, "seed_execution_decision_id": 3,
            "seed_native_binding_decision_id": 4,
        },
        "enrollment": {"enrollment_id": "enroll-a", "cohort_id": "cohort-a", "manifest_sha256": "a" * 64},
        "seed": {
            "dispatch_id": "dispatch-seed", "attempt_id": "attempt-seed", "role": "routine-execution",
            "native_thread_id": thread, "receipt": {"path": str(receipt), "sha256": digest(receipt)},
            "events": {"path": str(events), "sha256": digest(events)},
        },
        "source": {"path": str(source), "sha256": digest(source)},
        "policy": {"path": str(policy), "sha256": digest(policy)},
        "executable": {"path": str(executable), "sha256": digest(executable)},
        "native_schema": {"manifest_path": str(manifest), "manifest_sha256": digest(manifest)},
        "configuration": configuration,
        "capability_evidence": {"path": str(capability), "sha256": digest(capability)},
        "compaction": None,
    }
    records = [
        {"id": 1, "rule_matched": "measured-delivery-enrollment", "context_json": {
            **binding["enrollment"], "arm_id": "arm-a", "implementation_dispatched": False,
            "enrolled_at": "2026-09-12T00:00:00Z"}},
        {"id": 2, "rule_matched": "measured-delivery-dispatch-request", "context_json": {
            **binding["enrollment"], "dispatch_id": "dispatch-seed", "role": "routine-execution"}},
        {"id": 3, "rule_matched": "dispatch-profile", "context_json": execution_context},
        {"id": 4, "rule_matched": "measured-delivery-binding", "context_json": {
            **binding["enrollment"], "arm_id": "arm-a", "dispatch_id": "dispatch-seed",
            "attempt_id": "attempt-seed", "role": "routine-execution", "provider": "codex",
            "model": "gpt-fixture", "session_id": thread, "thread_id": thread,
            "source_path": str(source), "source_sha256": digest(source),
            "policy_path": str(policy), "policy_sha256": digest(policy),
            "executable": str(executable), "executable_sha256": digest(executable),
            "configuration_sha256": configuration["sha256"], "evidence_path": str(events),
            "native_thread_id": thread,
            "native_schema_manifest": {"path": str(manifest), "sha256": digest(manifest)},
            "native_capability_evidence": {"path": str(capability), "sha256": digest(capability), "status": "verified"},
        }},
    ]
    if operation == "resume":
        compact_context = json.loads(json.dumps(execution_context))
        compact_context.update(dispatch_id="dispatch-compact", attempt_id="attempt-compact")
        compact_context["execution"]["native_operation"] = {
            "operation": "compact", "seed_thread_id": thread, "status": "completed",
            "configuration_status": "verified", "accounting_status": "complete",
            "native_usage": {"total": {"inputTokens": 8, "cachedInputTokens": 2,
                "outputTokens": 1, "reasoningOutputTokens": 1, "totalTokens": 9},
                "last": {"inputTokens": 8, "cachedInputTokens": 2, "outputTokens": 1,
                "reasoningOutputTokens": 1, "totalTokens": 9}},
        }
        compact_context["result"] = {"exit_code": 0}
        compact_receipt = tmp_path / "compact.receipt.json"
        compact_receipt.write_text(json.dumps(compact_context) + "\n")
        compact_result = tmp_path / "compact.result.json"
        compact_result.write_text(json.dumps(compact_context["execution"]["native_operation"]) + "\n")
        binding["authority"].update(compaction_dispatch_request_decision_id=5, compaction_execution_decision_id=6)
        binding["compaction"] = {
            "dispatch_id": "dispatch-compact", "attempt_id": "attempt-compact", "status": "completed",
            "accounting_status": "complete", "configuration_status": "verified",
            "receipt": {"path": str(compact_receipt), "sha256": digest(compact_receipt)},
            "operation_result": {"path": str(compact_result), "sha256": digest(compact_result)},
        }
        records.extend([
            {"id": 5, "rule_matched": "measured-delivery-dispatch-request", "context_json": {
                **binding["enrollment"], "dispatch_id": "dispatch-compact", "role": "routine-execution"}},
            {"id": 6, "rule_matched": "dispatch-profile", "context_json": compact_context},
        ])
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(binding) + "\n")
    return m, path, binding, records, manifest


def validate_fixture(m, path, records, manifest, operation="compact"):
    return m.validate_binding(path, operation, records=records,
        expected_manifest_sha256=digest(manifest), expected_manifest_file_count=1)


def test_binding_requires_authoritative_records_and_all_exact_pins(tmp_path):
    m, path, binding, records, manifest = make_binding(tmp_path)
    result = validate_fixture(m, path, records, manifest)
    assert result["native_thread_id"] == binding["seed"]["native_thread_id"]
    assert result["role"] == "routine-execution"
    assert result["binding_sha256"] == digest(path)
    for mutate, message in (
        (lambda b: b["enrollment"].update(cohort_id="other"), "cohort"),
        (lambda b: b.update(arm_id="arm-b"), "arm"),
        (lambda b: b["source"].update(sha256="b" * 64), "source"),
        (lambda b: b["seed"].update(native_thread_id="not-the-native-uuid"), "UUID"),
    ):
        changed = json.loads(json.dumps(binding))
        mutate(changed)
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match=message):
            validate_fixture(m, path, records, manifest)
    path.write_text(json.dumps(binding))
    with pytest.raises(ValueError, match="authoritative"):
        validate_fixture(m, path, records[:2], manifest)


def test_binding_rejects_tamper_stale_source_replay_and_schema_drift(tmp_path):
    m, path, binding, records, manifest = make_binding(tmp_path)
    binding["seed"]["receipt"]["sha256"] = "f" * 64
    path.write_text(json.dumps(binding))
    with pytest.raises(ValueError, match="receipt"):
        validate_fixture(m, path, records, manifest)
    m, path, binding, records, manifest = make_binding(tmp_path / "stale")
    Path(binding["source"]["path"]).write_text("changed\n")
    with pytest.raises(ValueError, match="source"):
        validate_fixture(m, path, records, manifest)
    m, path, binding, records, manifest = make_binding(tmp_path / "replay")
    records.append({"id": 9, "rule_matched": "dispatch-profile", "context_json": {
        "execution": {"native_operation": {"operation": "compact", "binding_sha256": digest(path)}}}})
    with pytest.raises(ValueError, match="already admitted"):
        validate_fixture(m, path, records, manifest)
    m, path, binding, records, manifest = make_binding(tmp_path / "schema")
    Path(manifest).parent.joinpath("native-schema/required.json").write_text("tampered\n")
    with pytest.raises(ValueError, match="schema"):
        validate_fixture(m, path, records, manifest)


def test_resume_requires_successful_accounted_compaction(tmp_path):
    m, path, binding, records, manifest = make_binding(tmp_path, "resume")
    assert validate_fixture(m, path, records, manifest, "resume")["operation"] == "resume"
    for field, value in (("status", "unknown"), ("accounting_status", "missing"),
                         ("configuration_status", "invalid")):
        changed = json.loads(json.dumps(binding))
        changed["compaction"][field] = value
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match="compaction"):
            validate_fixture(m, path, records, manifest, "resume")


def fake_server(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "fake-codex"
    path.write_text(f"#!{sys.executable}\n" + r'''
import json, os, signal, sys, time
scenario=os.environ.get("CONTROL_SCENARIO","success")
thread=os.environ["CONTROL_THREAD"]
effective=json.loads(os.environ["CONTROL_EFFECTIVE"])
turn="01900000-0000-7000-8000-000000000001"
item="01900000-0000-7000-8000-000000000002"
def emit(v): print(json.dumps(v,ensure_ascii=False),flush=True)
for line in sys.stdin:
 r=json.loads(line); method=r.get("method")
 if method=="initialize": emit({"id":r["id"],"result":{"serverInfo":{"name":"fixture"}}})
 elif method=="initialized": pass
 elif method=="thread/resume":
  result=dict(effective); result["thread"]={"id":thread,"turns":[]}
  if scenario=="hydrated": result["thread"]["turns"]=[{"id":"private-history"}]
  if scenario=="settingsdiff": result["cwd"]="/wrong"
  emit({"id":r["id"],"result":result})
 elif method=="thread/compact/start":
  emit({"id":r["id"],"result":{}})
  if scenario=="timeout": time.sleep(30)
  elif scenario=="malformed": print("not-json",flush=True)
  elif scenario=="oversized": print("{"+"雪"*400000+"}",flush=True)
  elif scenario in ("request","auth"):
   emit({"id":"server-1","method":"account/chatgptAuthTokens/refresh" if scenario=="auth" else "item/commandExecution/requestApproval","params":{"credential":"do-not-save"}})
  elif scenario=="unknown": emit({"method":"new/event","params":{}})
  elif scenario=="reroute": emit({"method":"model/rerouted","params":{"threadId":thread,"turnId":turn,"fromModel":"a","toModel":"b","reason":"fallback"}})
  elif scenario=="warning": emit({"method":"configWarning","params":{"summary":"bad config","details":"private"}})
  else:
   events=[
    {"method":"turn/started","params":{"threadId":thread,"turn":{"id":turn,"items":[],"status":"inProgress"}}},
    {"method":"item/started","params":{"threadId":thread,"turnId":turn,"startedAtMs":1,"item":{"id":item,"type":"contextCompaction"}}},
    {"method":"item/completed","params":{"threadId":thread,"turnId":turn,"completedAtMs":2,"item":{"id":item,"type":"contextCompaction"}}},
    {"method":"thread/tokenUsage/updated","params":{"threadId":thread,"turnId":turn,"tokenUsage":{"last":{"inputTokens":8,"cachedInputTokens":2,"outputTokens":1,"reasoningOutputTokens":1,"totalTokens":9},"total":{"inputTokens":20,"cachedInputTokens":4,"outputTokens":3,"reasoningOutputTokens":2,"totalTokens":23},"modelContextWindow":1000}}},
    {"method":"account/rateLimits/updated","params":{"rateLimits":{"primary":{"usedPercent":12,"resetsAt":200},"accountId":"DO_NOT_SAVE"}}},
    {"method":"thread/compacted","params":{"threadId":thread,"turnId":turn}},
    {"method":"turn/completed","params":{"threadId":thread,"turn":{"id":turn,"items":[{"id":item,"type":"contextCompaction"}],"status":"completed"}}},
   ]
   if scenario=="outoforder": events[0],events[1]=events[1],events[0]
   if scenario=="missingusage": events=[e for e in events if e["method"]!="thread/tokenUsage/updated"]
   if scenario in ("settingsok","settingseventdiff"):
    settings={"model":effective["model"],"modelProvider":effective["modelProvider"],"effort":effective["reasoningEffort"],
     "serviceTier":effective["serviceTier"],"cwd":effective["cwd"],"approvalPolicy":effective["approvalPolicy"],
     "approvalsReviewer":effective["approvalsReviewer"],"sandboxPolicy":effective["sandbox"],
     "activePermissionProfile":effective["activePermissionProfile"]}
    if scenario=="settingseventdiff": settings["model"]="rerouted-model"
    events.insert(-1,{"method":"thread/settings/updated","params":{"threadId":thread,"threadSettings":settings}})
   for event in events: emit(event)
''')
    path.chmod(0o700)
    return path


def control_config(tmp_path):
    request = {"model": "gpt-fixture", "modelProvider": "openai", "cwd": str(tmp_path),
        "runtimeWorkspaceRoots": [str(tmp_path)], "approvalPolicy": "never", "approvalsReviewer": "user",
        "sandbox": "workspace-write", "serviceTier": "default", "baseInstructions": "base",
        "developerInstructions": "skills", "config": {"model_reasoning_effort": "high"}, "excludeTurns": True}
    effective = {"model": "gpt-fixture", "modelProvider": "openai", "reasoningEffort": "high",
        "serviceTier": "default", "cwd": str(tmp_path), "runtimeWorkspaceRoots": [str(tmp_path)],
        "approvalPolicy": "never", "approvalsReviewer": "user",
        "sandbox": {"type": "workspaceWrite", "networkAccess": False},
        "activePermissionProfile": None, "instructionSources": []}
    return request, effective


def run_control(tmp_path, monkeypatch, scenario="success", timeout=.5, frame=1024 * 1024):
    m = subject(); executable = fake_server(tmp_path); request, effective = control_config(tmp_path)
    thread = "018f47bb-4e58-7abc-8def-0123456789ab"
    monkeypatch.setenv("CONTROL_SCENARIO", scenario); monkeypatch.setenv("CONTROL_THREAD", thread)
    monkeypatch.setenv("CONTROL_EFFECTIVE", json.dumps(effective))
    control = m.AppServerControl(str(executable), handshake_timeout=timeout,
        operation_timeout=timeout, max_frame=frame)
    try:
        return control.compact(thread, request, effective)
    finally:
        metadata = control.close()
        assert metadata["reaped"] is True


def test_compaction_accepts_only_complete_matching_lifecycle_and_usage(tmp_path, monkeypatch):
    result = run_control(tmp_path, monkeypatch)
    assert result["status"] == "completed"
    assert result["accounting_status"] == "complete"
    assert result["configuration_status"] == "verified"
    assert result["native_usage"]["last"]["cachedInputTokens"] == 2
    assert result["account_observations"][0]["rate_limits"][0]["used_percent"] == 12
    assert "DO_NOT_SAVE" not in json.dumps(result)
    assert run_control(tmp_path / "settings", monkeypatch, "settingsok")["configuration_status"] == "verified"


def test_native_usage_follows_pinned_optional_context_window_semantics():
    m = subject()
    row = {"inputTokens": 8, "cachedInputTokens": 2, "outputTokens": 1,
           "reasoningOutputTokens": 1, "totalTokens": 9}
    assert m.validate_usage({"last": row, "total": row})["modelContextWindow"] is None
    with pytest.raises(Exception, match="malformed-native-usage"):
        m.validate_usage({"last": row | {"unknownCounter": 1}, "total": row})


@pytest.mark.parametrize("scenario,reason", [
    ("unknown", "unknown-notification"), ("malformed", "malformed-frame"),
    ("outoforder", "lifecycle-order"), ("missingusage", "missing-native-usage"),
    ("request", "server-request"), ("auth", "auth-refresh-request"),
    ("reroute", "model-rerouted"), ("warning", "config-warning"),
    ("settingsdiff", "effective-settings"), ("settingseventdiff", "effective-settings"),
    ("hydrated", "hydrated-history"),
    ("timeout", "timeout"), ("oversized", "oversized-frame"),
])
def test_compaction_fails_closed(tmp_path, monkeypatch, scenario, reason):
    with pytest.raises(Exception, match=reason):
        run_control(tmp_path, monkeypatch, scenario, frame=1024)


def test_cli_writes_private_bounded_result_and_cancellation_reaps(tmp_path, monkeypatch):
    m = subject(); executable = fake_server(tmp_path); request, effective = control_config(tmp_path)
    thread = "018f47bb-4e58-7abc-8def-0123456789ab"
    output = tmp_path / "result.json"
    env = os.environ | {"CONTROL_SCENARIO": "success", "CONTROL_THREAD": thread,
        "CONTROL_EFFECTIVE": json.dumps(effective)}
    result = run_control(tmp_path, monkeypatch)
    m.write_private(output, result)
    assert output.stat().st_mode & 0o777 == 0o600
    assert len(output.read_bytes()) < 16 * 1024 * 1024
    cancelled = tmp_path / "cancelled.json"
    wrapper = tmp_path / "cancel_fixture.py"
    wrapper.write_text('''import importlib.util,json,os,signal,sys
spec=importlib.util.spec_from_file_location("control",sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
request=json.loads(os.environ["CONTROL_REQUEST"]);effective=json.loads(os.environ["CONTROL_EFFECTIVE"])
c=m.AppServerControl(sys.argv[2],operation_timeout=30)
signal.signal(signal.SIGTERM,c.cancel)
try: c.compact(os.environ["CONTROL_THREAD"],request,effective)
except m.Cancelled as e: m.write_private(sys.argv[3],{"status":"cancelled","remote_completion":"unknown"}); code=128+e.signum
finally: c.close()
raise SystemExit(code)
''')
    env["CONTROL_SCENARIO"] = "timeout"
    env["CONTROL_REQUEST"] = json.dumps(request)
    process = subprocess.Popen([sys.executable, str(wrapper), m.__file__, str(executable), str(cancelled)], env=env)
    time.sleep(.15); process.send_signal(signal.SIGTERM); process.wait(timeout=4)
    assert process.returncode == 143
    assert json.loads(cancelled.read_text())["remote_completion"] == "unknown"


def test_resume_seal_is_private_fresh_and_links_exact_evidence(tmp_path):
    m, binding_path, binding, _, _ = make_binding(tmp_path, "resume")
    output = tmp_path / "last-message.txt"
    output.write_text("fixture result\n")
    artifacts = tmp_path / "resume-artifacts"
    artifacts.mkdir(mode=0o700)
    sealed = m.seal_resume(binding_path, binding["seed"]["events"]["path"], output, artifacts, 0)
    result_path = Path(sealed["operation_result"])
    manifest_path = Path(sealed["manifest"])
    result = json.loads(result_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    assert result["native_thread_id"] == binding["seed"]["native_thread_id"]
    assert result["events_sha256"] == digest(binding["seed"]["events"]["path"])
    assert result["control_result_is_approval"] is False
    assert result["control_result_is_last_message_verdict"] is False
    assert result_path.stat().st_mode & 0o777 == 0o600
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert sealed["manifest_sha256"] == digest(manifest_path)
    assert {item["logical_name"] for item in manifest["artifacts"]} == {
        "binding", "events", "last_message", "operation_result"}
    with pytest.raises(FileExistsError):
        m.seal_resume(binding_path, binding["seed"]["events"]["path"], output, artifacts, 0)
