import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import functools
import tempfile
import atexit
import shutil
from types import SimpleNamespace

import pytest


@functools.lru_cache(maxsize=1)
def pinned_native_schema():
    executable = Path(os.environ.get("NATIVE_TEST_CODEX", ""))
    assert executable.is_absolute() and executable.is_file(), "NATIVE_TEST_CODEX must select the declared pinned 0.154.0 executable"
    expected = os.environ.get("NATIVE_TEST_CODEX_SHA256")
    if sys.platform == "darwin": expected = "4f85982624b3898c8991cb80c0981b2aa71070e3537046c9a95950318a95afcc"
    assert expected and digest(executable) == expected, "pinned Codex executable digest mismatch"
    directory = Path(tempfile.mkdtemp(prefix="native-schema-"))
    atexit.register(shutil.rmtree, directory)
    result = subprocess.run([str(executable), "app-server", "generate-json-schema", "--experimental", "--out", str(directory)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert len(list(directory.rglob("*.json"))) == 426
    return directory


def subject():
    path = Path(os.environ.get("NATIVE_TEST_SOURCE", Path(__file__).parents[1])) / "scripts/dispatch_control.py"
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
        directory = tmp_path/"prior-compact"; directory.mkdir(mode=0o700)
        snapshot = directory/"binding.snapshot.json"; snapshot.write_text(json.dumps(binding)+"\n")
        db = Path(binding["authority"]["database"]); db.touch()
        a = {"operation":"compact", "operation_key":m.native_operation_key(thread,"compact"), "dispatch_id":"dispatch-compact",
            "attempt_id":"attempt-compact", "seed_dispatch_id":binding["seed"]["dispatch_id"], "seed_attempt_id":binding["seed"]["attempt_id"],
            "seed_thread_id":thread, "binding_sha256":digest(snapshot), "resolved_route_sha256":hashlib.sha256(m.canonical(execution_context["resolved_route"]).encode()).hexdigest(),
            "database_identity":m.database_identity(db), "started_at":"2026-09-12T00:00:00Z",
            "native_budget":{"scope_id":"scope", "manifest_sha256":"a"*64, "allocation_tokens":20, "scope_limit_tokens":100}}
        usage = {"inputTokens":8,"cachedInputTokens":2,"outputTokens":1,"reasoningOutputTokens":1,"totalTokens":9}
        result=m.fixture_result({"admission":a,"binding":binding},6,{"send_intent_at":"2026-09-12T00:00:01Z"},
            {"status":"completed","remote_completion":"completed","configuration_status":"verified","accounting_status":"complete",
             "effective_configuration":effective,"native_usage":m.validate_usage({"last":usage,"total":usage})},
            {"exit_code":0,"reaped":True,"termination_reason":None},time.monotonic())
        envelope=m.seal_operation_result(directory,result)
        compact_context=json.loads(json.dumps(execution_context))
        compact_context.update(dispatch_id="dispatch-compact",attempt_id="attempt-compact",fixture_only=True,eligible=False,terminal=True)
        compact_context["execution"]["native_operation"]=envelope
        compact_receipt=tmp_path/"compact.receipt.json"; compact_receipt.write_text(json.dumps(compact_context)+"\n")
        binding["authority"].update(compaction_dispatch_request_decision_id=5,compaction_execution_decision_id=8)
        binding["compaction"]={"dispatch_id":"dispatch-compact","attempt_id":"attempt-compact","status":"completed",
            "accounting_status":"complete","configuration_status":"verified","receipt":{"path":str(compact_receipt),"sha256":digest(compact_receipt)},
            "operation_result":envelope["operation_result"]}
        records.extend([
            {"id":5,"rule_matched":"measured-delivery-dispatch-request","context_json":{**binding["enrollment"],"dispatch_id":"dispatch-compact","role":"routine-execution"}},
            {"id":6,"rule_matched":"dispatch-profile","context_json":{"execution":{"native_admission":a}}},
            {"id":8,"rule_matched":"dispatch-profile","context_json":compact_context}])
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
    with pytest.raises(ValueError, match="already admitted|ambiguous legacy"):
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
# The protocol fixture also exercises the TERM-ignoring/KILL cleanup path.
# Normal TERM exit has its own required regression below; neither is skipped.
signal.signal(signal.SIGTERM,signal.SIG_IGN)
if os.environ.get('NATIVE_MASK_LOG'):
 import pathlib
 pathlib.Path(os.environ['NATIVE_MASK_LOG']).write_text(json.dumps([int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK,set())]))
thread=os.environ["CONTROL_THREAD"]
effective=json.loads(os.environ["CONTROL_EFFECTIVE"])
turn="01900000-0000-7000-8000-000000000001"
item="01900000-0000-7000-8000-000000000002"
def emit(v): print(json.dumps(v,ensure_ascii=False),flush=True)
def linger():
 import subprocess,pathlib
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
 pathlib.Path(os.environ['OWNED_PIDS']).write_text(str(os.getpid())+' '+str(child.pid)+' '+str(os.getppid()))
 time.sleep(60)
if len(sys.argv)>1 and sys.argv[1]=='exec':
 import pathlib
 prompt=sys.stdin.read()
 pathlib.Path(os.environ['NATIVE_ARGV_LOG']).write_text(json.dumps({'argv':sys.argv,'stdin':prompt}))
 output=pathlib.Path(sys.argv[sys.argv.index('-o')+1]);output.write_text('fixture resumed message\n')
 emit({'type':'thread.started','thread_id':thread});emit({'type':'turn.started'})
 if scenario=='ignore-term-cli': linger()
 emit({'type':'turn.completed','usage':{'input_tokens':5,'cached_input_tokens':1,'output_tokens':2}})
 sys.exit(0)
for line in sys.stdin:
 r=json.loads(line); method=r.get("method")
 if method=="initialize":
  assert r['params']['capabilities']['experimentalApi'] is True
  emit({"id":True if scenario=='bool-response' else r["id"],"result":{"codexHome":"/fixture/home","platformFamily":"unix","platformOs":"fixture","userAgent":"fixture"}})
 elif method=="initialized": pass
 elif method=="thread/resume":
  if scenario=='ignore-term-resume-wait': linger()
  result=dict(effective); result["thread"]={"id":thread,"turns":[],"cliVersion":"0.154.0","createdAt":1,"updatedAt":2,"cwd":effective['cwd'],"ephemeral":False,"modelProvider":"openai","preview":"PRIVATE_HISTORY_SENTINEL","projectId":None,"sessionId":thread,"source":"exec","status":{"type":"idle"}}
  if scenario=="resume-notification": emit({"method":"thread/status/changed","params":{"threadId":thread,"status":{"type":"idle"}}})
  if scenario=="hydrated": result["thread"]["turns"]=[{"id":"private-history","items":[],"status":"completed"}]
  if scenario=="settingsdiff": result["cwd"]="/wrong"
  if scenario=="empty-page": result["initialTurnsPage"]={'data':[]}
  emit({"id":r["id"],"result":result})
 elif method=="thread/compact/start":
  if os.environ.get('NATIVE_SEND_LOG'):
   with open(os.environ['NATIVE_SEND_LOG'],'a') as log: log.write(str(os.getpid())+'\n')
  if scenario!="preack": emit({"id":r["id"],"result":{}})
  if scenario=="timeout": time.sleep(30)
  elif scenario=="ignore-term":
   linger()
  elif scenario=="malformed": print("not-json",flush=True)
  elif scenario=="oversized": print("{"+"雪"*400000+"}",flush=True)
  elif scenario in ("request","auth"):
   emit({"id":"server-1","method":"account/chatgptAuthTokens/refresh" if scenario=="auth" else "item/commandExecution/requestApproval","params":{"credential":"do-not-save"}})
  elif scenario=="unknown": emit({"method":"new/event","params":{}})
  elif scenario=="reroute": emit({"method":"model/rerouted","params":{"threadId":thread,"turnId":turn,"fromModel":"a","toModel":"b","reason":"highRiskCyberActivity"}})
  elif scenario=="warning": emit({"method":"configWarning","params":{"summary":"bad config","details":"private"}})
  elif scenario.startswith('error:'):
   emit({'method':'error','params':{'threadId':thread,'turnId':turn,'willRetry':False,'error':{'message':'PRIVATE_ERROR_SENTINEL','codexErrorInfo':scenario.split(':')[1],'additionalDetails':None}}})
  else:
   events=[
    {"method":"turn/started","params":{"threadId":thread,"turn":{"id":turn,"items":[],"status":"inProgress"}}},
    {"method":"item/started","params":{"threadId":thread,"turnId":turn,"startedAtMs":1,"item":{"id":item,"type":"contextCompaction"}}},
    {"method":"item/completed","params":{"threadId":thread,"turnId":turn,"completedAtMs":2,"item":{"id":item,"type":"contextCompaction"}}},
    {"method":"thread/tokenUsage/updated","params":{"threadId":thread,"turnId":turn,"tokenUsage":{"last":{"inputTokens":8,"cachedInputTokens":2,"outputTokens":1,"reasoningOutputTokens":1,"totalTokens":9},"total":{"inputTokens":20,"cachedInputTokens":4,"outputTokens":3,"reasoningOutputTokens":2,"totalTokens":23},"modelContextWindow":1000}}},
    {"method":"account/rateLimits/updated","params":{"rateLimits":{"primary":{"usedPercent":12,"resetsAt":200},"limitName":"DO_NOT_SAVE"}}},
    {"method":"thread/compacted","params":{"threadId":thread,"turnId":turn}},
    {"method":"turn/completed","params":{"threadId":thread,"turn":{"id":turn,"items":[{"id":item,"type":"contextCompaction"}],"status":"completed"}}},
   ]
   if os.environ.get('CONTROL_SCHEMA_ROOT'):
    import pathlib,jsonschema
    names={'turn/started':'TurnStartedNotification','item/started':'ItemStartedNotification','item/completed':'ItemCompletedNotification',
      'thread/tokenUsage/updated':'ThreadTokenUsageUpdatedNotification','account/rateLimits/updated':'AccountRateLimitsUpdatedNotification',
      'thread/compacted':'ContextCompactedNotification','turn/completed':'TurnCompletedNotification'}
    schemas={method:json.loads((pathlib.Path(os.environ['CONTROL_SCHEMA_ROOT'])/'v2'/(name+'.json')).read_text()) for method,name in names.items()}
    for event in events: jsonschema.Draft7Validator(schemas[event['method']]).validate(event['params'])
   if scenario=='succeeded':
    events[-1]['params']['turn']['status']='succeeded'
    assert not jsonschema.Draft7Validator(schemas['turn/completed']).is_valid(events[-1]['params'])
   if scenario=='wrong-turn': events[-1]['params']['turn']['id']='wrong'
   if scenario=='partial-items': events[-1]['params']['turn']['itemsView']='summary'
   if scenario=='bool-usage':
    events[3]['params']['tokenUsage']['last']['inputTokens']=True
    assert not jsonschema.Draft7Validator(schemas['thread/tokenUsage/updated']).is_valid(events[3]['params'])
   if scenario=='unknown-active-flags': events.insert(-1,{'method':'thread/status/changed','params':{'threadId':thread,'status':{'type':'active','activeFlags':['unknown']}}})
   if scenario=="outoforder": events[0],events[1]=events[1],events[0]
   if scenario=="missingusage": events=[e for e in events if e["method"]!="thread/tokenUsage/updated"]
   if scenario=="late-usage": events.append(events.pop(3))
   if scenario in ("settingsok","settingseventdiff"):
    settings={"model":effective["model"],"modelProvider":effective["modelProvider"],"effort":effective["reasoningEffort"],
     "serviceTier":effective["serviceTier"],"cwd":effective["cwd"],"approvalPolicy":effective["approvalPolicy"],
     "approvalsReviewer":effective["approvalsReviewer"],"sandboxPolicy":effective["sandbox"],
     "activePermissionProfile":effective["activePermissionProfile"],"collaborationMode":{"mode":"default","settings":{"model":effective['model'],"reasoning_effort":"high","developer_instructions":None}}}
    if scenario=="settingseventdiff": settings["model"]="rerouted-model"
    events.insert(-1,{"method":"thread/settings/updated","params":{"threadId":thread,"threadSettings":settings}})
   for event in events: emit(event)
   if scenario=="preack": emit({"id":r["id"],"result":{}})
while True: time.sleep(1)
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


def run_control(tmp_path, monkeypatch, scenario="success", timeout=3, frame=1024 * 1024):
    m = subject(); executable = fake_server(tmp_path); request, effective = control_config(tmp_path)
    thread = "018f47bb-4e58-7abc-8def-0123456789ab"
    monkeypatch.setenv("CONTROL_SCENARIO", scenario); monkeypatch.setenv("CONTROL_THREAD", thread)
    monkeypatch.setenv("CONTROL_EFFECTIVE", json.dumps(effective))
    monkeypatch.setenv("CONTROL_SCHEMA_ROOT",str(pinned_native_schema()))
    # The fake validates complete pinned schemas before replying. Its local
    # Python/jsonschema startup is not part of the deliberately short operation
    # timeout; production retains its independent ten-second handshake bound.
    control = m.AppServerControl(str(executable), handshake_timeout=3,
        operation_timeout=timeout, max_frame=frame, schema_root=pinned_native_schema())
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
    assert run_control(tmp_path / "preack", monkeypatch, "preack")["status"] == "completed"
    assert run_control(tmp_path / "late", monkeypatch, "late-usage")["status"] == "completed"
    assert run_control(tmp_path / "resume", monkeypatch, "resume-notification")["status"] == "completed"


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
    ("bool-response", "malformed-jsonrpc-id"),
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
c=m.AppServerControl(sys.argv[2],operation_timeout=30,schema_root=os.environ['NATIVE_TEST_SCHEMA_ROOT'])
signal.signal(signal.SIGTERM,c.cancel)
open(sys.argv[3]+'.ready','x').close()
try: c.compact(os.environ["CONTROL_THREAD"],request,effective)
except m.Cancelled as e: m.write_private(sys.argv[3],{"status":"cancelled","remote_completion":"unknown"}); code=128+e.signum
finally: c.close()
raise SystemExit(code)
''')
    env["CONTROL_SCENARIO"] = "timeout"
    env["CONTROL_REQUEST"] = json.dumps(request)
    env["NATIVE_TEST_SCHEMA_ROOT"] = str(pinned_native_schema())
    process = subprocess.Popen([sys.executable, str(wrapper), m.__file__, str(executable), str(cancelled)], env=env)
    ready=Path(str(cancelled)+'.ready');deadline=time.monotonic()+10
    while not ready.exists():
        assert process.poll() is None and time.monotonic()<deadline
        time.sleep(.01)
    process.send_signal(signal.SIGTERM); process.wait(timeout=4)
    assert process.returncode == 143
    assert json.loads(cancelled.read_text())["remote_completion"] == "unknown"


def test_resume_seal_is_private_fresh_and_links_exact_evidence(tmp_path):
    m, binding_path, binding, records, _ = make_binding(tmp_path, "resume")
    envelope=next(m.context(r)["execution"]["native_operation"] for r in records if "native_operation" in m.context(r).get("execution",{}))
    result=m.read_operation_envelope(envelope)
    result_path=Path(envelope["operation_result"]["path"])
    manifest_path=Path(envelope["artifact_manifest"]["path"])
    assert result["seed_thread_id"]==binding["seed"]["native_thread_id"]
    assert result["control_result_is_approval"] is False and result["control_result_is_last_message_verdict"] is False
    assert result_path.stat().st_mode & 0o777==0o600 and manifest_path.stat().st_mode & 0o777==0o600
    with pytest.raises(FileExistsError): m.seal_operation_result(result_path.parent,result)
    with pytest.raises(ValueError,match="unavailable"): m.seal_resume(binding_path, None, None, None, 0)


def test_old_source_reproducer_reformatted_binding_cannot_reopen_native_uuid(tmp_path):
    """Replay is a remote-resource fact, not a byte-formatting fact."""
    m, path, binding, records, manifest = make_binding(tmp_path)
    original_digest = digest(path)
    records.append({
        "id": 9,
        "rule_matched": "dispatch-profile",
        "context_json": {
            "execution": {
                "native_operation": {
                    "operation": "compact",
                    "seed_thread_id": binding["seed"]["native_thread_id"],
                    "binding_sha256": original_digest,
                    "status": "failed",
                    "remote_completion": "unknown",
                }
            }
        },
    })
    path.write_text(json.dumps(binding, indent=2) + "\n")
    assert digest(path) != original_digest
    with pytest.raises(ValueError, match="consumed|already admitted"):
        validate_fixture(m, path, records, manifest)


def test_old_source_reproducer_started_request_consumes_native_uuid(tmp_path):
    m, path, binding, records, manifest = make_binding(tmp_path)
    records.append({
        "id": 9,
        "rule_matched": "dispatch-profile",
        "context_json": {
            "state": "started",
            "execution": {
                "operation_request": {
                    "operation": "compact",
                    "seed_thread_id": binding["seed"]["native_thread_id"],
                    "binding_sha256": "f" * 64,
                }
            },
        },
    })
    with pytest.raises(ValueError, match="consumed|already admitted"):
        validate_fixture(m, path, records, manifest)


def test_old_source_reproducer_retrospective_enrollment_is_not_prospective(tmp_path):
    m, path, binding, records, manifest = make_binding(tmp_path)
    records[0]["id"] = 30
    records[1]["id"] = 31
    binding["authority"]["enrollment_decision_id"] = 30
    binding["authority"]["dispatch_request_decision_id"] = 31
    path.write_text(json.dumps(binding) + "\n")
    with pytest.raises(ValueError, match="prospective|order"):
        validate_fixture(m, path, records, manifest)


def test_native_operation_key_is_remote_resource_identity():
    m = subject()
    thread = "018F47BB-4E58-7ABC-8DEF-0123456789AB"
    key = m.native_operation_key(thread, "compact")
    assert key == m.native_operation_key(thread.lower(), "compact")
    assert key != m.native_operation_key(thread, "resume")
    with pytest.raises(ValueError):
        m.native_operation_key("not-a-uuid", "compact")


def test_binding_snapshot_hashes_the_opened_buffer_and_rejects_aliases(tmp_path):
    m = subject()
    source = tmp_path / "binding.json"
    source.write_bytes(b'{"fixture":"one"}\n')
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    captured = m.capture_binding_snapshot(source, private)
    snapshot = Path(captured["path"])
    assert snapshot.read_bytes() == b'{"fixture":"one"}\n'
    assert captured["sha256"] == digest(snapshot)
    assert snapshot.stat().st_mode & 0o777 == 0o600
    alias = tmp_path / "alias.json"
    alias.symlink_to(source)
    with pytest.raises(ValueError, match="nonregular|alias"):
        m.capture_binding_snapshot(alias, private)
    hardlink = tmp_path / "hardlink.json"
    os.link(source, hardlink)
    with pytest.raises(ValueError, match="hardlink|alias"):
        m.capture_binding_snapshot(source, private)


def test_framed_handoff_is_bounded_digest_checked_one_use():
    m = subject()
    packet = {"reservation_decision_id": 7, "payload": "snowman ☃"}
    read_fd, write_fd = os.pipe()
    m.write_framed_handoff(write_fd, packet)
    assert m.read_framed_handoff(read_fd) == packet
    with pytest.raises(ValueError, match="truncated|consumed"):
        m.read_framed_handoff(read_fd)
    os.close(read_fd)


def test_resume_argv_uses_one_pinned_grammar_and_stdin_prompt(tmp_path):
    m = subject()
    request, _ = control_config(tmp_path)
    request["config"].update({"approvals_reviewer": "user", "model_provider": "openai"})
    admitted = {
        "executable": "/fixture/codex", "native_thread_id": "018f47bb-4e58-7abc-8def-0123456789ab",
        "configuration": {"request": request},
    }
    argv = m.build_native_resume_argv(admitted, tmp_path / "last-message")
    assert argv[:2] == ["/fixture/codex", "exec"]
    assert argv[-8:] == ["resume", "--json", "-m", "gpt-fixture", "-o", str(tmp_path / "last-message"),
                         "018f47bb-4e58-7abc-8def-0123456789ab"] + ["-"]
    assert "approval_policy=\"never\"" in argv
    assert "resume prompt" not in argv


def test_resume_argv_parses_with_pinned_cli_help_only(tmp_path):
    m = subject()
    pinned_native_schema()
    executable = Path(os.environ["NATIVE_TEST_CODEX"])
    request, _ = control_config(tmp_path)
    request["config"].update({"approvals_reviewer": "user", "model_provider": "openai"})
    admitted = {"executable": str(executable), "native_thread_id": "018f47bb-4e58-7abc-8def-0123456789ab",
                "configuration": {"request": request}}
    argv = m.build_native_resume_argv(admitted, tmp_path / "last-message")
    parsed = subprocess.run(argv[:-1] + ["--help"], text=True, capture_output=True, timeout=10)
    assert parsed.returncode == 0, parsed.stderr


def test_usage_rejects_bool_overflow_and_impossible_subsets():
    m = subject()
    row = {"inputTokens": 8, "cachedInputTokens": 2, "outputTokens": 3,
           "reasoningOutputTokens": 1, "totalTokens": 11}
    assert m.validate_usage({"last": row, "total": row})["last"] == row | {"cacheWriteInputTokens": 0}
    for changed in (
        row | {"inputTokens": True},
        row | {"inputTokens": 2 ** 63},
        row | {"reasoningOutputTokens": 4},
        row | {"totalTokens": 99},
    ):
        with pytest.raises(Exception, match="malformed-native-usage"):
            m.validate_usage({"last": changed, "total": row})


def test_native_budget_reserves_ordered_prefix_and_blocks_unknown_spending():
    m = subject()
    key_a = m.native_operation_key("018f47bb-4e58-7abc-8def-0123456789ab", "compact")
    key_b = m.native_operation_key("019f47bb-4e58-7abc-8def-0123456789ab", "compact")
    def row(ident, key, allocation):
        return {"id": ident, "rule_matched": "dispatch-profile", "context_json": {
            "execution": {"native_admission": {"fixture_only": True, "eligible": False,
                "operation_key": key, "native_budget": {"scope_id": "scope", "allocation_tokens": allocation}}}}}
    records = [row(10, key_a, 6), row(11, key_b, 6)]
    with pytest.raises(ValueError, match="budget"):
        m.evaluate_native_budget(records, "scope", 10, 11)
    records.append({"id": 12, "rule_matched": "dispatch-profile", "context_json": {
        "execution": {"native_operation": {"admission_decision_id": 10, "native_launched": False,
            "remote_completion": "not-started", "accounting_status": "missing"}}}})
    assert m.evaluate_native_budget(records, "scope", 10, 11)["reserved_tokens"] == 6
    records.insert(-1, {"id": 9, "rule_matched": "dispatch-profile", "context_json": {
        "execution": {"native_send_intent": {"admission_decision_id": 10}}}})
    records[-1]["context_json"]["execution"]["native_operation"]["native_launched"] = True
    records[-1]["context_json"]["execution"]["native_operation"]["remote_completion"] = "unknown"
    with pytest.raises(ValueError, match="unknown.*spending"):
        m.evaluate_native_budget(records, "scope", 20, 11)


def test_fixture_handoff_supervises_one_owned_group_and_marks_result_ineligible(tmp_path, monkeypatch):
    m,db,spec,_=real_native_fixture(tmp_path,monkeypatch)
    process=run_fixture_shell(spec,db)
    assert process.returncode==0,process.stderr
    envelope=json.loads((tmp_path/"operation/envelope.json").read_text())
    result=m.read_operation_envelope(envelope)
    assert result["fixture_only"] is True and result["eligible"] is False
    assert result["process"]=={"exit_code":0,"reaped":True,"termination_reason":None}


def reservation(m, ident, thread, key=None, seed="seed", allocation=6):
    return {"id": ident, "rule_matched": "dispatch-profile", "context_json": {
        "dispatch_id": str(ident), "attempt_id": str(ident), "state": "started",
        "fixture_only": True, "eligible": False, "execution": {"native_admission": {
            "fixture_only": True, "eligible": False, "provider": "codex", "operation": "compact",
            "seed_thread_id": thread, "seed_dispatch_id": seed, "seed_attempt_id": seed,
            "operation_key": key or m.native_operation_key(thread, "compact"),
            "native_budget": {"scope_id": "scope", "allocation_tokens": allocation,
                "max_allocation_tokens": 10, "scope_limit_tokens": 20, "manifest_sha256": "a"*64}}}}}


@pytest.mark.parametrize("case", ["forged-key", "legacy", "ambiguous", "provenance"])
def test_election_recomputes_keys_and_poisoned_history(tmp_path, case):
    m = subject(); thread = "018f47bb-4e58-7abc-8def-0123456789ab"
    row = reservation(m, 10, thread, "a"*64 if case == "forged-key" else None)
    records = [row]
    if case in {"legacy", "ambiguous"}:
        native = {"operation": "compact", "binding_sha256": "b"*64}
        if case == "legacy": native["seed_thread_id"] = thread
        records.insert(0, {"id": 1, "context_json": {"execution": {"native_operation": native}}})
    if case == "provenance": records.append(reservation(m, 11, thread, seed="changed"))
    with pytest.raises(ValueError):
        m.elect_native_reservation(records, row["context_json"]["execution"]["native_admission"]["operation_key"], 10)


def test_send_intent_cannot_be_refunded_by_not_started_terminal():
    m = subject(); thread = "018f47bb-4e58-7abc-8def-0123456789ab"
    rows = [reservation(m, 10, thread), reservation(m, 13, "019f47bb-4e58-7abc-8def-0123456789ab")]
    rows.extend([{"id": 11, "context_json": {"execution": {"native_send_intent": {"admission_decision_id": 10}}}},
                 {"id": 12, "context_json": {"execution": {"native_operation": {"admission_decision_id": 10,
                    "native_launched": False, "remote_completion": "not-started", "accounting_status": "missing"}}}}])
    with pytest.raises(ValueError, match="spending|intent"):
        m.evaluate_native_budget(rows, "scope", 20, 13)


def test_resume_builder_rejects_unallowlisted_config(tmp_path):
    m = subject(); request, _ = control_config(tmp_path)
    request["config"]["dangerous_unknown"] = True
    with pytest.raises(ValueError, match="config"):
        m.build_native_resume_argv({"configuration": {"request": request}, "executable": "/fixture/codex",
            "native_thread_id": "018f47bb-4e58-7abc-8def-0123456789ab"}, tmp_path/"out")


def test_partial_handoff_deadline_is_enforced_without_writer_eof():
    m = subject(); reader, writer = os.pipe()
    started = time.monotonic()
    # A delayed closer prevents an old blocking read from hanging the test suite.
    import threading
    closer = threading.Timer(.3, lambda: os.close(writer)); closer.start()
    try:
        with pytest.raises(ValueError): m.read_framed_handoff(reader, deadline_seconds=.05)
        assert time.monotonic()-started < .2
    finally:
        closer.join(); os.close(reader)


def ic_fixture(db, *args):
    exe = shutil.which("ic")
    assert exe, "declared pinned Intercore required"
    result = subprocess.run([exe, "--db="+str(db), "--json", *args], cwd=db.parent, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() and args[0] != "init" else None


def real_native_fixture(tmp_path, monkeypatch, scenario="success", scope_limit=100, prompt="--leading ☃ prompt"):
    m, path, bound, rows, manifest = make_binding(tmp_path)
    transport = fake_server(tmp_path)
    executable = Path(bound["executable"]["path"])
    executable.write_bytes(transport.read_bytes()); executable.chmod(0o700)
    # --version cannot start the fake transport; the real audit calls it.
    executable.write_text(executable.read_text().replace('scenario=os.environ', 'if "--version" in sys.argv: print("codex-cli fixture"); sys.exit(0)\nscenario=os.environ'))
    manifest_value = json.loads(manifest.read_text()); manifest_value["executable_sha256"] = digest(executable)
    # Every composed fixture consumes the complete schema emitted by the actual
    # pinned CLI. The transport remains fake and the artifacts remain ineligible.
    schema = tmp_path/'native-schema'
    (schema/'required.json').unlink()
    shutil.copytree(pinned_native_schema(), schema, dirs_exist_ok=True)
    manifest_value['files']=[{'path':str(p.relative_to(schema)),'sha256':digest(p)} for p in sorted(schema.rglob('*.json'))]
    manifest.write_text(json.dumps(manifest_value)+"\n")
    bound["executable"]["sha256"] = digest(executable)
    bound["native_schema"]["manifest_sha256"] = digest(manifest)
    capfile = Path(bound["capability_evidence"]["path"]); cap = json.loads(capfile.read_text())
    cap.update(executable_sha256=digest(executable), native_schema_manifest_sha256=digest(manifest))
    capfile.write_text(json.dumps(cap)+"\n"); bound["capability_evidence"]["sha256"] = digest(capfile)
    for row in rows[2:]:
        value = row["context_json"]; target = value["execution"] if row["id"] == 3 else value
        target["executable_sha256"] = digest(executable)
        target["native_schema_manifest"]["sha256"] = digest(manifest)
        target["native_capability_evidence"]["sha256"] = digest(capfile)
    Path(bound["seed"]["receipt"]["path"]).write_text(json.dumps(rows[2]["context_json"])+"\n")
    bound["seed"]["receipt"]["sha256"] = digest(bound["seed"]["receipt"]["path"])
    budget = tmp_path/"budget.json"
    budget.write_text(json.dumps({"scope_id": str(tmp_path), "units":"native_input_plus_output_tokens", "scope_limit_tokens":scope_limit,
        "max_allocation_tokens":{"compact":20,"resume":20}}))
    rows[0]["context_json"]["native_budget_manifest"] = {"path":str(budget),"sha256":digest(budget)}
    rows[0]["context_json"].update(model='gpt-fixture',parent_session_id='fixture-parent',bead_id='fixture-bead')
    # A composed fixture has the complete prospective seed start/terminal chain.
    # Pure v1 predicate fixtures above remain legacy/ineligible inputs only.
    seed_started=json.loads(json.dumps(rows[2]['context_json']))
    seed_started.update(state='started',terminal=False)
    seed_started.pop('result')
    rows.insert(2,{'rule_matched':'dispatch-profile','context_json':seed_started})
    for index,row in enumerate(rows,1):row['id']=index
    bound['schema_version']=2
    bound['authority'].update(seed_started_decision_id=3,seed_execution_decision_id=4,seed_native_binding_decision_id=5)
    db = tmp_path/"intercore.db"
    ic_fixture(db,"init")
    for row in rows:
        ident = ic_fixture(db, "route", "record", "--agent=fixture", "--model=gpt-fixture", "--rule="+row["rule_matched"],
                   "--context="+json.dumps(row["context_json"]))["id"]
        assert ident == row["id"]
    path.write_text(json.dumps(bound)+"\n")
    request = {**native_dispatch_request(rows,bound,'compact',prompt), "operation":"compact",
        "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
        "seed_dispatch_id":bound["seed"]["dispatch_id"], "seed_attempt_id":bound["seed"]["attempt_id"], "allocation_tokens":20,
        "resolved_route":rows[2]["context_json"]["resolved_route"]}
    request_id=ic_fixture(db,"route","record","--agent=fixture","--model=gpt-fixture","--rule=measured-delivery-dispatch-request","--context="+json.dumps(request))["id"]
    spec = {"binding":str(path),"request_id":request_id,"attempt_id":"attempt-compact","directory":str(tmp_path/"operation"),
        "ic":shutil.which("ic"),"schema_root":str(schema),"prompt":prompt}
    spec_path=tmp_path/"spec.json"; spec_path.write_text(json.dumps(spec))
    monkeypatch.setenv("CONTROL_SCENARIO",scenario); monkeypatch.setenv("CONTROL_THREAD",bound["seed"]["native_thread_id"])
    monkeypatch.setenv("CONTROL_EFFECTIVE",json.dumps(bound["configuration"]["effective"]))
    monkeypatch.setenv("CONTROL_SCHEMA_ROOT",str(schema))
    return m, db, spec_path, bound


def run_fixture_shell(spec, db):
    lib = Path(__file__).parents[1]/"scripts/lib-dispatch-native.sh"
    return subprocess.run(["bash","-c", 'source "$1"; NATIVE_FIXTURE_ROOT="$3"; native_fixture_run "$2"',
        "fixture",str(lib),str(spec),str(db.parent)],cwd=db.parent,text=True,capture_output=True,timeout=20)


def native_dispatch_request(rows,bound,operation,prompt="--leading ☃ prompt"):
    spec=importlib.util.spec_from_file_location('task_delivery_fixture',Path(__file__).parents[1]/'scripts/task-delivery.py')
    delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)
    argv,env,receipt=delivery.prepare_dispatch(rows,bound['enrollment']['enrollment_id'],'routine-execution',
        ['--operation',operation,'--resume-from','fixture-binding.json',prompt])
    assert argv[:2]==['bash',str(delivery.CANONICAL_ROOT/'scripts/dispatch.sh')]
    assert receipt['dispatch_id']==env['CLAVAIN_DISPATCH_ID']
    return receipt


def test_real_composed_audit_transport_result_reader(tmp_path, monkeypatch):
    m, db, spec, bound = real_native_fixture(tmp_path, monkeypatch)
    process=run_fixture_shell(spec, db)
    assert process.returncode == 0, process.stdout+process.stderr
    rows=m.load_records(db, shutil.which("ic"))
    terminal=m.context(rows[0]) if rows[0].get("id")==8 else next(m.context(r) for r in rows if m.context(r).get("terminal"))
    envelope=terminal["execution"]["native_operation"]
    result=m.read_operation_envelope(envelope)
    assert result["status"]=="completed" and result["budget"]["debit_tokens"]==9
    assert result["admission_decision_id"]==json.loads(spec.read_text())['request_id']+1
    assert terminal["state"]=="completed" and terminal["fixture_only"] is True and terminal["eligible"] is False
    assert json.loads((tmp_path/"operation/receipt.json").read_text())==terminal
    assert "PRIVATE_HISTORY_SENTINEL" not in json.dumps(result)
    assert "DO_NOT_SAVE" not in json.dumps(result)
    assert "operation_result_path" not in result
    assert all(m.context(r).get("fixture_only") is True for r in rows if r["id"]>=result['admission_decision_id'])


def test_real_binding_reader_then_resume_executes_exact_argv_and_stdin(tmp_path, monkeypatch):
    m,db,resume_path,bound,admitted=real_resume_fixture(tmp_path,monkeypatch)
    p=run_fixture_shell(resume_path,db)
    observed=json.loads((tmp_path/'argv.json').read_text())
    expected=m.build_native_resume_argv(admitted,tmp_path/'resume/last-message')
    assert observed['argv']==expected
    assert observed['stdin']==bound['configuration']['request']['baseInstructions']+'\n\n'+bound['configuration']['request']['developerInstructions']+'\n\n--leading ☃ prompt'
    assert p.returncode==0,p.stdout+p.stderr
    result=m.read_operation_envelope(json.loads((tmp_path/'resume/envelope.json').read_text()))
    assert result['budget']['debit_tokens']==7 and result['native_usage']=={'input_tokens':5,'cached_input_tokens':1,'output_tokens':2}
    assert result['configuration_status']=='unknown'  # CLI usage is not configuration proof.


def real_resume_fixture(tmp_path,monkeypatch):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    p=run_fixture_shell(spec,db); assert p.returncode==0,p.stderr
    rows=m.load_records(db,shutil.which('ic'))
    terminal=max((r for r in rows if m.context(r).get('terminal')),key=lambda r:r['id'])
    binding=tmp_path/'resume-binding.json'
    admitted=m.bind_fixture_compaction(tmp_path/'operation/binding.snapshot.json',db,terminal['id'],json.loads(spec.read_text())['request_id'],
        tmp_path/'operation/receipt.json',binding,shutil.which('ic'))
    assert admitted['fixture_only'] is True and admitted['operation']=='resume'
    request={**native_dispatch_request(rows,bound,'resume'),'operation':'resume',
        'prompt_sha256':hashlib.sha256('--leading ☃ prompt'.encode()).hexdigest(),
        'seed_dispatch_id':bound['seed']['dispatch_id'],'seed_attempt_id':bound['seed']['attempt_id'],'allocation_tokens':20,
        'resolved_route':m.context(terminal)['resolved_route']}
    request_id=ic_fixture(db,'route','record','--agent=fixture','--model=gpt-fixture','--rule=measured-delivery-dispatch-request','--context='+json.dumps(request))['id']
    resume_spec=json.loads(spec.read_text())|{'binding':str(binding),'request_id':request_id,'attempt_id':'attempt-resume','directory':str(tmp_path/'resume')}
    resume_path=tmp_path/'resume-spec.json';resume_path.write_text(json.dumps(resume_spec))
    monkeypatch.setenv('NATIVE_ARGV_LOG',str(tmp_path/'argv.json'))
    return m,db,resume_path,bound,admitted


@pytest.mark.parametrize("scenario,failure,configuration", [
    ("request","operational_permissions","verified"), ("auth","operational_auth","verified"),
    ("warning","terminal_configuration","invalid"), ("unknown","terminal_protocol","verified")])
def test_real_failure_audit_preserves_independent_outcome(tmp_path, monkeypatch, scenario, failure, configuration):
    m, db, spec, bound=real_native_fixture(tmp_path,monkeypatch,scenario)
    p=run_fixture_shell(spec,db)
    assert p.returncode != 0
    terminal=next(m.context(r) for r in m.load_records(db,shutil.which('ic')) if m.context(r).get('terminal'))
    result=m.read_operation_envelope(terminal['execution']['native_operation'])
    assert terminal['state']=='failed' and result['failure']['class']==failure
    assert result['configuration_status']==configuration
    assert result['remote_completion']=='unknown' and result['accounting_status']=='missing'
    assert 'do-not-save' not in json.dumps(result)


@pytest.mark.parametrize('mode',['same','conflicting','cross-seed-budget'])
def test_real_contenders_elect_once_without_advisory_lock_authority(tmp_path, monkeypatch,mode):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch,scope_limit=30 if mode=='cross-seed-budget' else 100)
    prepared=m.prepare_fixture_operation(str(spec),str(os.getpid()))
    admission=prepared['admission']
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    # Two real long-lived Bash dispatchers synchronize before each actual append.
    gate=tmp_path/'go'
    script='''source "$1"
NATIVE_FIXTURE_ROOT="$2" WORKDIR="$2" OPERATION=compact ENGINE=codex VIA=exec
DISPATCH_EXECUTABLE="$5" MODEL=gpt-fixture ROLE=routine-execution ROLE_RESOLVED=true
DISPATCH_ID="dispatch-$6" ATTEMPT_ID="attempt-$6" BOUND_NATIVE_THREAD_ID="$7"
touch "$2/ready-$6"
while [[ ! -f "$2/go" ]]; do sleep .01; done
id="$(native_fixture_append_audit "$3" started "$4")" || exit 2
printf '%s' "$id" > "$2/reserved-$6"
while [[ ! -f "$2/reserved-1" || ! -f "$2/reserved-2" ]]; do sleep .01; done
native_fixture_elect "$3" "$8" "$id" > "$2/election-$6" || exit 1
if [[ "$9" == cross-seed-budget ]]; then
 python3 - "$(dirname "$1")/dispatch_control.py" "$3" "$2" "$id" <<'PY'
import importlib.util,sys
s=importlib.util.spec_from_file_location('c',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.evaluate_native_budget(m.load_records(sys.argv[2]),sys.argv[3],30,int(sys.argv[4]))
PY
fi
'''
    processes=[]
    for i in (1,2):
        proposed=dict(admission)
        if i==2 and mode!='same':proposed.update(seed_dispatch_id='other-seed',seed_attempt_id='other-attempt')
        if i==2 and mode=='cross-seed-budget':
            proposed['seed_thread_id']='01900000-0000-7000-8000-000000000099'
            proposed['operation_key']=m.native_operation_key(proposed['seed_thread_id'],'compact')
        args=['bash','-c',script,'fixture',str(lib),str(tmp_path),str(db),json.dumps(proposed),prepared['executable'],
            str(i),proposed['seed_thread_id'],proposed['operation_key'],mode]
        processes.append(subprocess.Popen(args,cwd=tmp_path,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
    try:
        deadline=time.monotonic()+5
        while not all((tmp_path/f'ready-{i}').exists() for i in (1,2)):
            assert time.monotonic()<deadline; time.sleep(.01)
        gate.touch()
        outputs=[p.communicate(timeout=10) for p in processes]
        assert sorted(p.returncode for p in processes)==([1,1] if mode=='conflicting' else [0,1]),outputs
        rows=m.load_records(db,shutil.which('ic'))
        assert len([r for r in rows if m.context(r).get('execution',{}).get('native_admission')])==2
    finally:
        for p in processes:
            if p.poll() is None: p.terminate(); p.wait(timeout=3)


@pytest.mark.parametrize('signum',[signal.SIGINT,signal.SIGTERM,signal.SIGKILL])
@pytest.mark.parametrize('phase',['compact','resume-wait','cli'])
def test_dispatcher_only_signal_reaps_owned_transport(tmp_path,monkeypatch,signum,phase):
    if phase=='cli':
        m,db,spec,bound,_=real_resume_fixture(tmp_path,monkeypatch)
        monkeypatch.setenv('CONTROL_SCENARIO','ignore-term-cli')
    else:
        m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch,'ignore-term' if phase=='compact' else 'ignore-term-resume-wait')
    monkeypatch.setenv('OWNED_PIDS',str(tmp_path/'owned-pids'))
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    p=subprocess.Popen(['bash','-c','source "$1"; NATIVE_FIXTURE_ROOT="$3"; native_fixture_run "$2"','fixture',str(lib),str(spec),str(tmp_path)],cwd=tmp_path,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+8
        while not (tmp_path/'owned-pids').exists():
            assert p.poll() is None, p.communicate()
            assert time.monotonic()<deadline; time.sleep(.01)
        owned=[int(x) for x in (tmp_path/'owned-pids').read_text().split()]
        start=time.monotonic(); os.kill(p.pid,signum)
        out,err=p.communicate(timeout=3)
        assert time.monotonic()-start<2, (out,err)
        assert p.returncode==(-signal.SIGKILL if signum==signal.SIGKILL else 128+signum),(out,err)
        deadline=start+2
        while any(pid_running(pid) for pid in owned) and time.monotonic()<deadline: time.sleep(.01)
        assert not any(pid_running(pid) for pid in owned)
        if signum!=signal.SIGKILL:
            result=m.read_operation_envelope(json.loads((Path(json.loads(spec.read_text())['directory'])/'envelope.json').read_text()))
            assert result['process']['exit_code']==128+signum and result['status']=='cancelled'
    finally:
        if p.poll() is None: p.terminate(); p.wait(timeout=3)


def pid_running(pid):
    result=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True)
    if result.returncode not in {0,1} or result.stderr.strip():
        raise AssertionError('owned process observation unavailable: '+result.stderr)
    return result.returncode==0 and bool(result.stdout.strip()) and not result.stdout.strip().startswith('Z')


def test_two_real_composed_dispatchers_send_once(tmp_path,monkeypatch):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    value=json.loads(spec.read_text()); second=value|{'attempt_id':'contender','directory':str(tmp_path/'contender')}
    second_path=tmp_path/'contender-spec.json';second_path.write_text(json.dumps(second))
    monkeypatch.setenv('NATIVE_SEND_LOG',str(tmp_path/'sends'))
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    script='''source "$1"
NATIVE_FIXTURE_ROOT="$3"
eval "$(declare -f native_fixture_append_audit | sed '1s/native_fixture_append_audit/real_append/')"
native_fixture_append_audit() {
 if [[ "$2" == started ]]; then
  touch "$NATIVE_FIXTURE_ROOT/ready-$4"
  while [[ ! -f "$NATIVE_FIXTURE_ROOT/go" ]]; do sleep .01; done
 fi
 real_append "$@"
}
native_fixture_run "$2"
'''
    # The wrapper changes scheduling only. Every append, readback, election,
    # budget, handoff, launch and terminal still runs the source implementation.
    script=script.replace('ready-$4','ready-$$')
    processes=[subprocess.Popen(['bash','-c',script,'fixture',str(lib),str(s),str(tmp_path)],cwd=tmp_path,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for s in (spec,second_path)]
    try:
        end=time.monotonic()+8
        while len(list(tmp_path.glob('ready-*')))<2:
            assert all(p.poll() is None for p in processes),[p.communicate() for p in processes if p.poll() is not None]
            assert time.monotonic()<end;time.sleep(.01)
        (tmp_path/'go').touch()
        outputs=[p.communicate(timeout=10) for p in processes]
        assert sorted(p.returncode for p in processes)==[0,1],outputs
        assert len((tmp_path/'sends').read_text().splitlines())==1
        rows=m.load_records(db,shutil.which('ic'))
        assert len([r for r in rows if m.context(r).get('execution',{}).get('native_admission')])==2
    finally:
        for p in processes:
            if p.poll() is None:p.terminate();p.wait(timeout=3)


@pytest.mark.parametrize('phase',['started','send-intent'])
def test_committed_append_with_lost_reply_or_owner_crash_burns_resource(tmp_path,monkeypatch,phase):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    script='''source "$1"; NATIVE_FIXTURE_ROOT="$3"
eval "$(declare -f native_fixture_append_audit | sed '1s/native_fixture_append_audit/real_append/')"
native_fixture_append_audit() { real_append "$@" > "$NATIVE_FIXTURE_ROOT/committed-id"; if [[ "$2" == "$CRASH_PHASE" ]]; then return 91; fi; cat "$NATIVE_FIXTURE_ROOT/committed-id"; }
native_fixture_run "$2"
'''
    env=os.environ|{'CRASH_PHASE':phase,'NATIVE_SEND_LOG':str(tmp_path/'sends')}
    p=subprocess.run(['bash','-c',script,'fixture',str(lib),str(spec),str(tmp_path)],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert p.returncode!=0 and not (tmp_path/'sends').exists()
    rows=m.load_records(db,shutil.which('ic'))
    assert any(m.context(r).get('execution',{}).get('native_admission') for r in rows)
    retry=json.loads(spec.read_text())|{'directory':str(tmp_path/'retry'),'attempt_id':'retry'}
    retry_path=tmp_path/'retry.json';retry_path.write_text(json.dumps(retry))
    retry_process=run_fixture_shell(retry_path,db)
    assert retry_process.returncode!=0 and not (tmp_path/'sends').exists()


@pytest.mark.parametrize('scenario,reason',[('succeeded','native-schema-invalid'),('wrong-turn','terminal-turn-failed'),
    ('partial-items','terminal-item-mismatch'),('bool-usage','native-schema-invalid'),('empty-page','hydrated-history'),
    ('unknown-active-flags','native-schema-invalid')])
def test_complete_native_schema_then_adversarial_adapter_frame(tmp_path,monkeypatch,scenario,reason):
    with pytest.raises(Exception,match=reason): run_control(tmp_path,monkeypatch,scenario,timeout=1)


@pytest.mark.parametrize('target',['original','snapshot'])
def test_composed_snapshot_swap_cannot_change_launched_inputs(tmp_path,monkeypatch,target):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    original_digest=digest(json.loads(spec.read_text())['binding'])
    monkeypatch.setenv('NATIVE_SEND_LOG',str(tmp_path/'sends'))
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    victim=tmp_path/'binding.json' if target=='original' else tmp_path/'operation/binding.snapshot.json'
    script='''source "$1"; NATIVE_FIXTURE_ROOT="$3"
eval "$(declare -f native_fixture_handoff_to_python | sed '1s/native_fixture_handoff_to_python/real_handoff/')"
native_fixture_handoff_to_python() { printf '{}\\n' > "$MUTATE_PATH"; real_handoff "$@"; }
native_fixture_run "$2"
'''
    p=subprocess.run(['bash','-c',script,'fixture',str(lib),str(spec),str(tmp_path)],env=os.environ|{'MUTATE_PATH':str(victim)},cwd=tmp_path,capture_output=True,text=True,timeout=10)
    result=json.loads((tmp_path/'operation/operation-result.json').read_text())
    assert result['binding_sha256']==original_digest
    if target=='original':
        assert p.returncode==0,p.stderr
        assert len((tmp_path/'sends').read_text().splitlines())==1
    else:
        assert p.returncode!=0 and not (tmp_path/'sends').exists()
        assert result['status']=='failed' and result['remote_completion']=='not-started'


def test_large_partial_frame_and_extra_bytes_use_real_pipe():
    m=subject(); packet={'large':'雪'*30000}; reader,writer=os.pipe()
    script='import importlib.util,sys; s=importlib.util.spec_from_file_location("m",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.write_framed_handoff(int(sys.argv[2]),{"large":"雪"*30000})'
    p=subprocess.Popen([sys.executable,'-c',script,m.__file__,str(writer)],pass_fds=(writer,))
    os.close(writer)
    try: assert m.read_framed_handoff(reader)==packet
    finally: os.close(reader);p.wait(timeout=3)
    assert p.returncode==0
    reader,writer=os.pipe()
    payload=b'{}';os.write(writer,m.HANDOFF_HEADER.pack(m.HANDOFF_MAGIC,len(payload),hashlib.sha256(payload).digest())+payload+b'x');os.close(writer)
    try:
        with pytest.raises(ValueError,match='trailing'):m.read_framed_handoff(reader)
    finally:os.close(reader)


@pytest.mark.parametrize('allocation',[1,21])
def test_real_budget_maximum_and_overrun_are_terminal(tmp_path,monkeypatch,allocation):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    value=json.loads(spec.read_text());rows=m.load_records(db,shutil.which('ic'))
    request=m.decision(rows,value['request_id'],'measured-delivery-dispatch-request','request')|{'dispatch_id':'budget-test','allocation_tokens':allocation}
    value['request_id']=ic_fixture(db,'route','record','--agent=fixture','--model=gpt-fixture','--rule=measured-delivery-dispatch-request','--context='+json.dumps(request))['id']
    spec.write_text(json.dumps(value));p=run_fixture_shell(spec,db)
    assert p.returncode!=0
    if allocation==21:
        assert 'maximum' in p.stderr
        assert not (tmp_path/'operation/envelope.json').exists()
    else:
        result=m.read_operation_envelope(json.loads((tmp_path/'operation/envelope.json').read_text()))
        assert result['budget']['status']=='overrun' and result['budget']['debit_tokens']==9
        assert result['failure']['class']=='terminal_accounting'


def test_native_child_does_not_inherit_supervisor_registration_signal_mask(tmp_path,monkeypatch):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    monkeypatch.setenv('NATIVE_MASK_LOG',str(tmp_path/'mask.json'))
    p=run_fixture_shell(spec,db)
    assert p.returncode==0,p.stderr
    mask=json.loads((tmp_path/'mask.json').read_text())
    assert int(signal.SIGINT) not in mask and int(signal.SIGTERM) not in mask


@pytest.mark.parametrize('native,category',[('unauthorized','operational_auth'),('sandboxError','operational_permissions'),
    ('cyberPolicy','terminal_policy'),('misalignmentPolicyViolation','terminal_policy'),('usageLimitExceeded','operational_quota'),
    ('rateLimitExceeded','operational_rate'),('sessionBudgetExceeded','operational_budget'),('serverOverloaded','operational_infrastructure')])
def test_native_error_enums_produce_typed_real_terminal(tmp_path,monkeypatch,native,category):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch,'error:'+native)
    p=run_fixture_shell(spec,db);assert p.returncode!=0
    result=m.read_operation_envelope(json.loads((tmp_path/'operation/envelope.json').read_text()))
    assert result['failure']['class']==category
    assert result['configuration_status']=='verified' and result['accounting_status']=='missing'
    assert 'PRIVATE_ERROR_SENTINEL' not in json.dumps(result)


def test_composed_rejects_missing_prospective_seed_start(tmp_path,monkeypatch):
    m,db,spec,bound=real_native_fixture(tmp_path,monkeypatch)
    path=Path(json.loads(spec.read_text())['binding'])
    bound['schema_version']=1
    bound['authority'].pop('seed_started_decision_id',None)
    path.write_text(json.dumps(bound))
    with pytest.raises(ValueError,match='prospective seed started'):
        m.prepare_fixture_operation(str(spec),str(os.getpid()))


def test_owned_group_normal_term_exit_is_verifiably_reaped():
    m=subject()
    process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'],start_new_session=True)
    try:
        m._terminate_group(process,time.monotonic()+2)
        assert process.returncode==-signal.SIGTERM
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=2)


def test_result_reader_rejects_attribution_different_from_native_counters(tmp_path):
    m,_,_,_,_=make_binding(tmp_path,'resume')
    result=json.loads((tmp_path/'prior-compact/operation-result.json').read_text())
    m.validate_operation_result(result)
    result['budget']['attributable_input_tokens']+=1
    with pytest.raises(ValueError,match='attributable counters'):
        m.validate_operation_result(result)


def test_duplicate_real_handoff_cannot_send_twice_or_mislabel_terminal(tmp_path,monkeypatch):
    m,db,spec,_=real_native_fixture(tmp_path,monkeypatch)
    monkeypatch.setenv('NATIVE_SEND_LOG',str(tmp_path/'sends'))
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    script='''source "$1"; NATIVE_FIXTURE_ROOT="$3"
eval "$(declare -f native_fixture_handoff_to_python | sed '1s/native_fixture_handoff_to_python/real_handoff/')"
native_fixture_handoff_to_python() { real_handoff "$@" || return; real_handoff "$@"; }
native_fixture_run "$2"
'''
    p=subprocess.run(['bash','-c',script,'fixture',str(lib),str(spec),str(tmp_path)],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert p.returncode!=0
    assert len((tmp_path/'sends').read_text().splitlines())==1
    rows=m.load_records(db,shutil.which('ic'))
    # The second private invocation cannot overwrite the first result or append
    # a failed audit that falsely points at its completed result.
    assert not any(m.context(r).get('terminal') for r in rows)
    original=json.loads((tmp_path/'operation/operation-result.json').read_text())
    assert original['status']=='completed'


def test_large_composed_handoff_streams_data_without_large_exec_arguments(tmp_path,monkeypatch):
    prompt='--leading '+('雪'*60000)
    m,db,spec,_=real_native_fixture(tmp_path,monkeypatch,prompt=prompt)
    bin_dir=tmp_path/'probe-bin';bin_dir.mkdir()
    probe=bin_dir/'python3';log=tmp_path/'python-argv-lengths.jsonl'
    # Observe and exec the actual interpreter. No validator, audit, budget,
    # schema generator, or handoff implementation is substituted.
    probe.write_text('#!'+sys.executable+'\n'+f'''import json,os,sys
with open({str(log)!r},'a') as f:f.write(json.dumps([len(s.encode()) for s in sys.argv[1:]])+'\\n')
os.execv({sys.executable!r},[{sys.executable!r},*sys.argv[1:]])
''');probe.chmod(0o700)
    monkeypatch.setenv('PATH',str(bin_dir)+os.pathsep+os.environ['PATH'])
    p=run_fixture_shell(spec,db);assert p.returncode==0,p.stderr
    lengths=[n for row in log.read_text().splitlines() for n in json.loads(row)]
    assert lengths and max(lengths)<32768
    result=m.read_operation_envelope(json.loads((tmp_path/'operation/envelope.json').read_text()))
    assert result['status']=='completed'


@pytest.mark.parametrize('text', ['', '12 12', 'x 12 Z', '12 12 Z extra',
    '12 12 Z\n12 12 Z', '13 12 Z', '12 12 S', '12 12 Z\n13 12 S',
    '12 12 Z\n99 x S', '12 12 Z\n99 99 ???'])
def test_owned_group_parser_rejects_unproven_inventory(text):
    assert not subject()._owned_group_exited_only(text,12)


def test_owned_group_parser_accepts_only_exited_members_and_ignores_other_groups():
    assert subject()._owned_group_exited_only('12 12 Z\n13 12 Z+\n99 99 S',12)
    assert subject()._owned_group_exited_only('12 12 Z\n99 99 ?+',12)
    assert not subject()._owned_group_exited_only('12 12 Z\n13 12 ?',12)


def test_owned_group_observer_never_queries_linux_or_reaped_leader(monkeypatch):
    m=subject()
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k: pytest.fail('unexpected query'))
    monkeypatch.setattr(m.sys,'platform','linux')
    assert not m._observe_owned_group_exited(SimpleNamespace(pid=12,returncode=None),time.monotonic()+1)
    monkeypatch.setattr(m.sys,'platform','darwin')
    assert not m._observe_owned_group_exited(SimpleNamespace(pid=12,returncode=0),time.monotonic()+1)


def test_owned_group_unproven_permission_failure_is_sticky(monkeypatch):
    m=subject();events=[]
    class Child:
        pid=12
        returncode=None
        def wait(self,timeout):
            events.append('wait');self.returncode=0
    def send(pid,sig):
        assert 'wait' not in events
        events.append(sig)
        if sig==signal.SIGTERM: raise PermissionError(1,'denied')
    monkeypatch.setattr(m.os,'killpg',send)
    monkeypatch.setattr(m,'_observe_owned_group_exited',lambda *a:False)
    with pytest.raises(PermissionError):m._terminate_group(Child(),time.monotonic()+.1)
    assert events==[signal.SIGTERM,signal.SIGKILL,'wait']


def test_owned_group_already_exited_is_reaped_without_grace_delay():
    m=subject();p=subprocess.Popen([sys.executable,'-c','pass'],start_new_session=True)
    try:
        deadline=time.monotonic()+2
        while os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None:
            assert time.monotonic()<deadline;time.sleep(.01)
        started=time.monotonic();m._terminate_group(p,started+2)
        assert p.returncode==0
        assert time.monotonic()-started<1
    finally:
        if p.poll() is None:p.kill();p.wait()


@pytest.mark.parametrize('code', [
    'raise SystemExit(1)',
    'import sys;sys.stderr.write("denied");print("12 12 Z")',
    'print("x"*1100000)',
    'import time;time.sleep(10)',
    'print("12 12 S")',
])
def test_owned_group_observer_rejects_failed_oversized_hanging_or_live_query(monkeypatch,code):
    m=subject();original=subprocess.Popen;children=[]
    def query(argv,**kwargs):
        assert argv==['/bin/ps','-A','-o','pid=,pgid=,stat=']
        assert kwargs['env']=={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
        p=original([sys.executable,'-c',code],**kwargs);children.append(p);return p
    monkeypatch.setattr(m.sys,'platform','darwin')
    monkeypatch.setattr(m.subprocess,'Popen',query)
    started=time.monotonic()
    assert not m._observe_owned_group_exited(SimpleNamespace(pid=12,returncode=None),started+.3)
    assert time.monotonic()-started<.6
    assert children and all(p.poll() is not None for p in children)


def test_owned_group_observer_denial_remains_unproven(monkeypatch):
    m=subject()
    monkeypatch.setattr(m.sys,'platform','darwin')
    def denied(*a,**k):raise PermissionError(1,'denied')
    monkeypatch.setattr(m.subprocess,'Popen',denied)
    assert not m._observe_owned_group_exited(SimpleNamespace(pid=12,returncode=None),time.monotonic()+1)


def test_owned_group_exited_leader_does_not_hide_live_descendant():
    m=subject()
    child='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(20)'
    leader='import subprocess,sys;p=subprocess.Popen([sys.executable,"-c",'+repr(child)+']);p.wait()'
    # Both processes hold the pipe. Stop only the leader after child readiness;
    # EOF proves the descendant closed its writer without trusting a reused PID.
    p=subprocess.Popen([sys.executable,'-c',leader],stdout=subprocess.PIPE,text=True,start_new_session=True)
    try:
        assert p.stdout.readline().strip()=='ready'
        os.kill(p.pid,signal.SIGKILL)
        deadline=time.monotonic()+2
        while os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None:
            assert time.monotonic()<deadline;time.sleep(.01)
        m._terminate_group(p,time.monotonic()+2)
        with m.selectors.DefaultSelector() as selector:
            selector.register(p.stdout,m.selectors.EVENT_READ)
            assert selector.select(.5)
        assert p.stdout.read()==''
    finally:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGKILL);p.wait()
        p.stdout.close()


def test_dispatcher_interrupt_before_python_handler_never_sends(tmp_path,monkeypatch):
    m,db,spec,_=real_native_fixture(tmp_path,monkeypatch)
    ready=tmp_path/'bootstrap-ready';sent=tmp_path/'native-sends'
    monkeypatch.setenv('NATIVE_SEND_LOG',str(sent))
    bin_dir=tmp_path/'bootstrap-bin';bin_dir.mkdir();shim=bin_dir/'python3'
    shim.write_text('#!'+sys.executable+'\n'+f'''import os,sys,time
from pathlib import Path
if len(sys.argv)>2 and sys.argv[1]=='-c' and 'run_fixture_handoff' in sys.argv[2]:
 Path({str(ready)!r}).write_text('before-handler')
 time.sleep(.5)
os.execv({sys.executable!r},[{sys.executable!r},*sys.argv[1:]])
''');shim.chmod(0o700)
    monkeypatch.setenv('PATH',str(bin_dir)+os.pathsep+os.environ['PATH'])
    lib=Path(__file__).parents[1]/'scripts/lib-dispatch-native.sh'
    p=subprocess.Popen(['bash','-c','source "$1"; NATIVE_FIXTURE_ROOT="$3"; native_fixture_run "$2"',
        'fixture',str(lib),str(spec),str(tmp_path)],cwd=tmp_path,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+10
        while not ready.exists():
            assert p.poll() is None,p.communicate()
            assert time.monotonic()<deadline;time.sleep(.005)
        start=time.monotonic();os.kill(p.pid,signal.SIGINT)
        out,err=p.communicate(timeout=3)
        assert not sent.exists(), 'native send occurred after pre-handler cancellation'
        assert time.monotonic()-start<2
        assert p.returncode==130,(out,err)
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=3)
