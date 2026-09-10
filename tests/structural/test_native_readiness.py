import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("native_readiness", SCRIPTS / "native-readiness.py")
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)


def test_preparation_replaces_write_tools_and_denies_all_skills(tmp_path):
    command = ["/host/claude", "--tools", "default", "--allowedTools", "Bash,Write,Skill",
               "--permission-mode", "default", "--disallowedTools", "Read(secret.txt)", "-p"]
    prepared = native.preparation_command("claude", command, tmp_path)
    assert prepared[prepared.index("--tools") + 1] == "Read,Glob,Grep"
    assert prepared[prepared.index("--permission-mode") + 1] == "dontAsk"
    denies = prepared[prepared.index("--disallowedTools") + 1]
    assert "Skill" in denies.split(",")
    assert "Read(secret.txt)" in denies
    settings = json.loads(prepared[prepared.index("--settings") + 1])
    assert settings["disableSkillShellExecution"] is True
    assert "--restricted" not in prepared  # This hid real native skills in the canary.


def test_codex_preparation_uses_current_agent_control_and_disables_each_connector(tmp_path):
    prepared = native.preparation_command("codex", ["/host/codex", "exec", "-s", "workspace-write"],
                                           tmp_path, mcp_servers=["example"])
    assert prepared[prepared.index("-s") + 1] == "read-only"
    assert "agents.enabled=false" in prepared
    assert 'mcp_servers."example".enabled=false' in prepared
    assert 'approval_policy="never"' in prepared


@pytest.mark.parametrize("unsafe", ["--dangerously-skip-permissions", "--yolo", "--resume", "--plugin-url"])
def test_unsafe_or_nonfresh_native_requests_are_rejected(tmp_path, unsafe):
    request = valid_request(tmp_path, "claude")
    request["command"].append(unsafe)
    with pytest.raises(ValueError, match="unsafe or nonfresh"):
        native.validate_request(request)


def test_invalid_readiness_does_not_create_execution_request(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with pytest.raises(ValueError):
        native.authorize_resume(evidence, {"reasons": [], "rationale": ""}, {"session_id": "test"})
    assert not (evidence / "resume-authorized.json").exists()


def test_existing_attempt_directory_cannot_be_reused(tmp_path):
    evidence = tmp_path / "attempt"
    evidence.mkdir()
    with pytest.raises(FileExistsError):
        native.execute_request({}, evidence)


def valid_request(project, host="codex"):
    command = ([sys.executable, "exec", "--json", "-m", "gpt-6-astra", "-c", 'model_reasoning_effort="high"']
               if host == "codex" else [sys.executable, "--model", "claude-fable-5-1", "--effort", "high",
                                       "--output-format", "stream-json", "--verbose", "-p"])
    return dict(host=host, command=command, project=str(project), source=str(SCRIPTS.parent.resolve()), prompt="task")


@pytest.mark.parametrize("host", ["codex", "claude"])
def test_valid_request_and_invalid_assignment(tmp_path, host):
    request = valid_request(tmp_path, host)
    assert native.validate_request(request) == native.readiness.MODELS[host]
    request["expected_model"] = "other"
    with pytest.raises(ValueError): native.validate_request(request)


@pytest.mark.parametrize("custom", [False, True, "alternate"])
def test_runtime_counters_change_but_permission_projection_is_stable(tmp_path, custom):
    directory = tmp_path / ".claude" if custom else tmp_path
    directory.mkdir(exist_ok=True)
    config = directory / (".config.json" if custom == "alternate" else ".claude.json")
    config.write_text(json.dumps({"numStartups": 1, "mcpServers": {}, "projects": {str(tmp_path): {"lastCost": 0}}}))
    env = {"HOME": str(tmp_path)}
    if custom: env["CLAUDE_CONFIG_DIR"] = str(directory)
    args = ([sys.executable], SCRIPTS.parent, tmp_path, env)
    before = native.input_snapshot(*args)
    value = json.loads(config.read_text()); value["numStartups"] = 2; value["projects"][str(tmp_path)]["lastCost"] = 1
    config.write_text(json.dumps(value))
    assert native.input_snapshot(*args) == before
    value["projects"][str(tmp_path)]["allowedTools"] = ["Bash"]
    config.write_text(json.dumps(value))
    assert native.input_snapshot(*args) != before


@pytest.mark.parametrize("failure", ["invalid-decision", "binding", "project-change"])
def test_full_launch_failure_never_starts_execution(tmp_path, monkeypatch, failure):
    project = tmp_path / "project"; project.mkdir()
    calls = []
    decision = {"reasons": [], "rationale": "settled"}
    monkeypatch.setattr(native, "codex_config", lambda *a: dict(approval_policy="never", sandbox_mode="workspace-write", mcp_server_names=[]))
    def run(command, prompt, folder, project, env, name, *args):
        calls.append(name)
        assert name == "preparation"
        native.save(folder / "decision-output.json", decision if failure != "invalid-decision" else {})
        if failure == "project-change": (project / "unexpected").write_text("changed")
        return {"exit_code": 0}, [{"type": "thread.started", "thread_id": "subject"}, {"type": "turn.completed"}]
    monkeypatch.setattr(native, "bounded", run)
    transcript = tmp_path / "native.jsonl"; transcript.write_text("{}\n")
    monkeypatch.setattr(native, "native_path", lambda *a: transcript)
    def fail(*a): raise ValueError("binding rejected")
    if failure == "binding": monkeypatch.setattr(native.readiness, "bind_decision", fail)
    evidence = tmp_path / "attempt"
    error = {"binding": "binding rejected", "invalid-decision": "decision requires", "project-change": "task or launch inputs changed"}[failure]
    with pytest.raises(ValueError, match=error): native.execute_request(valid_request(project), evidence, {"HOME": str(tmp_path)})
    assert calls == ["preparation"]
    assert (evidence / "failure.json").exists()
    assert not (evidence / "resume-request.json").exists()
    assert not (evidence / "resume-authorized.json").exists()


@pytest.mark.parametrize("init", [None, {}, {"tools": ["Write"]}, {"tools": ["Read"], "mcp_servers": ["external"]}])
def test_claude_missing_or_invalid_init_fails_closed(tmp_path, monkeypatch, init):
    rows = [{"type": "control_response", "response": {"subtype": "success", "request_id": "inventory"}}]
    if init is not None: rows.append(dict(init, type="system", subtype="init"))
    rows.append(dict(type="result", subtype="success", session_id="subject"))
    class Fake:
        def __init__(self, *a, **kw): self.rows = iter(rows)
        def send(self, value): pass
        def receive(self): return next(self.rows)
        def close(self, abort=False): return {"exit_code": -15 if abort else 0}
    monkeypatch.setattr(native, "NativeProcess", Fake)
    with pytest.raises(ValueError):
        native.claude_control([], tmp_path, tmp_path, {}, "prep", "prompt", "subject", "claude-fable-5-1")


def test_interrupt_terminates_detached_child(tmp_path, monkeypatch):
    signals = []
    class Fake:
        pid = 123
        returncode = None
        def __init__(self, *a, **kw): pass
        def communicate(self, *a, **kw): raise KeyboardInterrupt()
        def poll(self): return self.returncode
        def wait(self, **kw): self.returncode = -15
    monkeypatch.setattr(native.subprocess, "Popen", Fake)
    monkeypatch.setattr(native.os, "killpg", lambda *a: signals.append(a))
    with pytest.raises(KeyboardInterrupt): native.bounded([], "", tmp_path, tmp_path, {}, "stage")
    assert signals == [(123, native.signal.SIGTERM), (123, native.signal.SIGKILL)]


def test_native_execution_requires_unchanged_prefix_and_model(tmp_path):
    prefix = tmp_path / "prefix"; prefix.write_text('{}\n')
    actual = tmp_path / "actual"
    actual.write_text('{}\n' + json.dumps({"type": "turn_context", "payload": {"model": "gpt-6-astra", "effort": "high"}}) + '\n')
    assert native.verify_execution_native("codex", actual, prefix, "subject", "gpt-6-astra")["effort"] == "high"
    with pytest.raises(ValueError): native.verify_execution_native("codex", actual, prefix, "subject", "other")
    prefix.write_text('{"changed":true}\n')
    with pytest.raises(ValueError): native.verify_execution_native("codex", actual, prefix, "subject", "gpt-6-astra")


@pytest.mark.parametrize("mutation", [None, "model", "session", "mode", "duplicate", "error"])
def test_claude_init_positive_control_and_individual_failures(tmp_path, monkeypatch, mutation):
    init = dict(type="system", subtype="init", tools=["Read", "Glob", "Grep", "StructuredOutput"],
                mcp_servers=[], permissionMode="dontAsk", model="claude-fable-5-1", session_id="subject")
    result = dict(type="result", subtype="success", session_id="subject")
    if mutation == "model": init["model"] = "other"
    if mutation == "session": init["session_id"] = "other"
    if mutation == "mode": init["permissionMode"] = "default"
    if mutation == "error": result["is_error"] = True
    rows = [{"type": "control_response", "response": {"subtype": "success", "request_id": "inventory"}}, init]
    if mutation == "duplicate": rows.append(init)
    rows.append(result)
    class Fake:
        def __init__(self, *a, **kw): self.rows = iter(rows)
        def send(self, value): pass
        def receive(self): return next(self.rows)
        def close(self, abort=False): return {"exit_code": -15 if abort else 0}
    monkeypatch.setattr(native, "NativeProcess", Fake)
    if mutation:
        with pytest.raises(ValueError): native.claude_control([], tmp_path, tmp_path, {}, "prep", "prompt", "subject", "claude-fable-5-1")
    else:
        assert native.claude_control([], tmp_path, tmp_path, {}, "prep", "prompt", "subject", "claude-fable-5-1")[-1] == result


@pytest.mark.parametrize("mutation", [None, "prefix-only", "edit-first", "wrong-root", "missing-result", "wrong-call"])
def test_router_requires_ordered_execution_call_result_and_body(tmp_path, mutation):
    source = tmp_path / "source"
    rows = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "router", "name": "Skill", "input": {"skill": native.ROUTER}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "router"}]}},
        {"type": "user", "isMeta": True, "sourceToolUseID": "router", "message": {"content": [{"type": "text", "text": "Base directory for this skill: " + str(source / "skills/using-clavain") + "\nbody"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write"}]}}
    ]
    if mutation == "edit-first": rows.insert(0, rows.pop())
    if mutation == "wrong-root": rows[2]["message"]["content"][0]["text"] = "Base directory for this skill: /other\nbody"
    if mutation == "missing-result": rows.pop(1)
    if mutation == "wrong-call": rows[2]["sourceToolUseID"] = "unrelated"
    raw = b"".join((json.dumps(r) + "\n").encode() for r in rows)
    snapshot = tmp_path / "prefix"; snapshot.write_bytes(raw if mutation == "prefix-only" else b"{}\n")
    original = tmp_path / "native"; original.write_bytes(snapshot.read_bytes() + (b"" if mutation == "prefix-only" else raw))
    if mutation:
        with pytest.raises(ValueError): native.verify_router_loaded(original, snapshot, source, "body")
    else: native.verify_router_loaded(original, snapshot, source, "body")


@pytest.mark.parametrize("mutation", [None, "sidechain", "session", "effort"])
def test_claude_execution_native_checks(tmp_path, mutation):
    snapshot = tmp_path / "prefix"; snapshot.write_text('{}\n')
    row = dict(type="assistant", sessionId="subject", effort="high", message={"model": "claude-opus-5", "content": [{"type": "text", "text": "done"}]})
    if mutation == "sidechain": row["isSidechain"] = True
    if mutation == "session": row["sessionId"] = "other"
    if mutation == "effort": row["effort"] = "low"
    synthetic = dict(type="assistant", sessionId="subject", message={"model": "<synthetic>", "content": [{"type": "text", "text": "done"}]})
    actual = tmp_path / "native"; actual.write_text('{}\n' + json.dumps(row) + '\n' + json.dumps(synthetic) + '\n')
    if mutation:
        with pytest.raises(ValueError): native.verify_execution_native("claude", actual, snapshot, "subject", "claude-opus-5")
    else: assert native.verify_execution_native("claude", actual, snapshot, "subject", "claude-opus-5")["model"] == "claude-opus-5"


def test_closed_leader_still_gets_group_cleanup(tmp_path, monkeypatch):
    signals = []
    class Exited:
        pid = 123
        returncode = 0
        def wait(self, **kw): return 0
    monkeypatch.setattr(native.os, "killpg", lambda *a: signals.append(a))
    native.stop_group(Exited())
    assert signals == [(123, native.signal.SIGTERM), (123, native.signal.SIGKILL)]
    assert not issubclass(native.LauncherInterrupted, OSError)


@pytest.mark.parametrize("tamper", [None, "preparation.stage.json", "prelaunch.json", "preparation.stdout"])
def test_full_flow_rechecks_every_preparation_artifact(tmp_path, monkeypatch, tamper):
    project = tmp_path / "project"; project.mkdir()
    original = tmp_path / "native.jsonl"
    session = "00000000-0000-0000-0000-000000000001"
    decision = {"reasons": [], "rationale": "Settled fixture."}
    context = dict(model="gpt-6-astra", effort="high", turn_id="turn", approval_policy="never", sandbox_policy={"type": "read-only"})
    prefix = [dict(type="session_meta", payload=dict(id=session, source="exec", thread_source="user")),
              dict(type="turn_context", payload=context),
              dict(type="response_item", payload=dict(type="message", role="assistant", phase="final_answer", id="msg",
                  content=[dict(type="output_text", text=json.dumps(decision))]))]
    calls = []
    monkeypatch.setattr(native, "codex_config", lambda *a: dict(approval_policy="never", sandbox_mode="workspace-write", mcp_server_names=[]))
    monkeypatch.setattr(native, "native_path", lambda *a: original)
    def run(command, prompt, folder, project, env, name, *args):
        calls.append(name)
        (folder / (name + ".stdout")).write_text('{}\n')
        (folder / (name + ".stderr")).write_text('')
        if name == "preparation":
            native.save(folder / "decision-output.json", decision)
            original.write_text(''.join(json.dumps(r) + '\n' for r in prefix))
        else:
            with original.open('a') as stream:
                stream.write(json.dumps(dict(type="turn_context", payload=dict(context, sandbox_policy={"type": "workspace-write"}))) + '\n')
            if tamper: (folder / tamper).write_text('{"changed":true}\n')
        return {"exit_code": 0}, [{"type": "thread.started", "thread_id": session}, {"type": "turn.completed"}]
    monkeypatch.setattr(native, "bounded", run)
    folder = tmp_path / "attempt"
    if tamper:
        with pytest.raises(ValueError, match="preparation evidence changed"):
            native.execute_request(valid_request(project), folder, {"HOME": str(tmp_path)})
        assert not (folder / "result.json").exists()
    else:
        result = native.execute_request(valid_request(project), folder, {"HOME": str(tmp_path)})
        assert result["preparation_stage"] == {"exit_code": 0}
        assert "preparation.stdout" in result["preparation_evidence_sha256"]
    assert calls == ["preparation", "execution"]


@pytest.mark.parametrize("option,value", [("--effort", "low"), ("--model", "other"), ("--setting-sources", "user")])
def test_duplicate_native_options_rejected_before_launch(tmp_path, option, value):
    request = valid_request(tmp_path, "claude")
    if option == "--setting-sources": request["command"].extend([option, "project"])
    request["command"].extend([option, value])
    with pytest.raises(ValueError, match="duplicate native option"): native.validate_request(request)


def test_session_glob_patterns_are_not_native_ids(tmp_path):
    with pytest.raises(ValueError): native.native_path("claude", "*", {"HOME": str(tmp_path)})


def test_invalid_claude_init_preserves_original_error_after_abort(tmp_path, monkeypatch):
    rows=iter([{"type":"control_response","response":{"subtype":"success","request_id":"inventory"}},
               {"type":"system","subtype":"init","tools":["Write"]}])
    aborts=[]
    class Fake:
        def __init__(self,*a,**kw): pass
        def send(self,value): pass
        def receive(self): return next(rows)
        def close(self,abort=False): aborts.append(abort); return {"exit_code":-15}
    monkeypatch.setattr(native,"NativeProcess",Fake)
    with pytest.raises(ValueError,match="unexpected preparation tool or connector"):
        native.claude_control([],tmp_path,tmp_path,{},"prep","prompt","subject","claude-fable-5-1")
    assert aborts==[True]
    assert json.loads((tmp_path/'prep.stage.json').read_text())['exit_code']==-15


def test_signal_during_real_reader_cleanup_is_delayed_until_child_reaped(tmp_path):
    import subprocess
    code='''import importlib.util,os,signal,subprocess,sys
from pathlib import Path
scripts=Path(sys.argv[1]);sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('native',scripts/'native-readiness.py');native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
def interrupted(signum,frame): raise native.LauncherInterrupted('test signal')
signal.signal(signal.SIGTERM,interrupted)
folder=Path(sys.argv[2])
process=native.NativeProcess([sys.executable,'-c','import time;time.sleep(30)'],folder,folder,dict(os.environ),'real-reader')
sender=subprocess.Popen([sys.executable,'-c','import os,signal,time,sys;time.sleep(.1);os.kill(int(sys.argv[1]),signal.SIGTERM)',str(os.getpid())])
received=False
try: process.close()
except native.LauncherInterrupted: received=True
finally: sender.wait(timeout=5)
assert received and process.process.poll() is not None and not process.reader.is_alive()
print('reaped before interruption')
'''
    result=subprocess.run([sys.executable,'-c',code,str(SCRIPTS),str(tmp_path)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='reaped before interruption'


def test_nonobject_native_json_returns_error_without_waiting_for_deadline(tmp_path):
    import os
    process=native.NativeProcess([sys.executable,'-c','print("[]")'],tmp_path,tmp_path,dict(os.environ),'malformed')
    try:
        with pytest.raises(ValueError,match='native stream ended'): process.receive()
    finally: process.close(abort=True)
