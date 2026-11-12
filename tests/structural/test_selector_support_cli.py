"""CLI receipts through a socket-guarded isolated child."""
import json
import os
from pathlib import Path
import subprocess
import sys
import io
import pytest
from support_helpers import isolation, require_netns, request_packet  # noqa: F401
from test_selector_support import answer

pytestmark = pytest.mark.usefixtures("isolation", "require_netns")
ROOT = Path(__file__).resolve().parents[2]

def validate_record(record):
    import jsonschema
    schemas = ROOT / "schemas"
    schema = json.loads((schemas / "selector-support-record.v1.schema.json").read_text())
    resolver = jsonschema.RefResolver(base_uri=schemas.as_uri() + "/", referrer=schema)
    jsonschema.Draft202012Validator(schema, resolver=resolver, format_checker=jsonschema.FormatChecker()).validate(record)

def invoke(tmp_path, request, steps, *, mode="shadow", budget=4, daily=8):
    replies = tmp_path / "replies.json"
    replies.write_text(json.dumps(steps))
    registry = json.loads((ROOT / "config/selector-integrations.json").read_text())
    entry = registry["integrations"].setdefault("support_check", {})
    entry.update(enabled=True, session_budget=budget, daily_budget=daily)
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps(registry))
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "CLAVAIN_SELECTOR_SUPPORT_CHECK": mode, "CLAVAIN_SELECTOR_REGISTRY": str(reg), "CLAVAIN_STATE_DIR": str(tmp_path / "state")}
    child = subprocess.run([sys.executable, "-I", str(ROOT / "tests/structural/support_cli_harness.py"), "--replies", str(replies), "--", "support-json"], input=json.dumps(request), text=True, capture_output=True, env=env, cwd=tmp_path)
    assert child.returncode == 0, child.stderr
    record = json.loads(child.stdout)
    validate_record(record)
    return record

def test_cli_label_and_decoy(tmp_path, request_packet):
    (tmp_path / "source.md").write_text("Decoy.\n")
    record = invoke(tmp_path, request_packet, [{"status": 200, "body": json.dumps(answer()), "probe": "socket"}])
    assert record["outcome"] == "label"
    assert record["label"] == "supported"
    assert record["attempts"] == 1
    assert record["jev_usage_accounting"]["complete"] is True
    assert record["section_sha256s"] == [request_packet["sections"][0]["sha256"]]

@pytest.mark.parametrize("mode", ["off", "unknown", "active"])
def test_cli_mode(tmp_path, request_packet, mode):
    record = invoke(tmp_path, request_packet, [{"status": 200, "body": json.dumps(answer())}], mode=mode)
    if mode == "active":
        assert record["effective_mode"] == "shadow" and record["active_denied"] is True
    else:
        assert record["outcome"] == "disabled" and record["attempts"] == 0

def test_cli_session_budget(tmp_path, request_packet):
    steps = [{"status": 200, "body": json.dumps(answer())}]
    assert invoke(tmp_path, request_packet, steps, budget=1)["outcome"] == "label"
    record = invoke(tmp_path, request_packet, [], budget=1)
    assert (record["outcome"], record["subreason"]) == ("unavailable", "budget_session")

def test_cli_daily_budget(tmp_path, request_packet):
    assert invoke(tmp_path, request_packet, [{"status": 200, "body": json.dumps(answer())}], daily=1)["outcome"] == "label"
    request_packet["run_id"] = "rotated"
    record = invoke(tmp_path, request_packet, [], daily=1)
    assert (record["outcome"], record["subreason"]) == ("unavailable", "budget_daily")

@pytest.mark.parametrize("confidence,threshold,outcome", [(.7,.7,"label"),(.699,.7,"abstain"),(.9,0,"label"),(.9,1,"abstain"),(1,1,"label")])
def test_threshold(tmp_path, request_packet, confidence, threshold, outcome):
    request_packet["abstain_below"] = threshold
    record = invoke(tmp_path, request_packet, [{"status": 200, "body": json.dumps(answer(confidence=confidence))}])
    assert record["outcome"] == outcome

@pytest.mark.parametrize("threshold", [True,None,"0.5",float("nan"),float("inf"),-.01,1.01])
def test_bad_threshold(tmp_path, request_packet, threshold):
    request_packet["abstain_below"] = threshold
    record = invoke(tmp_path, request_packet, [])
    assert (record["outcome"],record["subreason"]) == ("invalid","request_schema")
    assert record["label"] is None

@pytest.mark.parametrize("status,subreason", [(201,"http_other"),(204,"http_other"),(206,"http_other"),(301,"http_redirect"),(307,"http_redirect"),(418,"http_4xx"),(400,"http_4xx"),(500,"http_5xx"),(502,"http_5xx"),(99,"http_other"),(600,"http_other"),(401,"credential_rejected"),(403,"credential_rejected"),(429,"http_429")])
def test_statuses(tmp_path,request_packet,status,subreason):
    step = {"status":status,"body":json.dumps(answer())}
    record = invoke(tmp_path, request_packet, [step,step])
    assert (record["outcome"],record["subreason"]) == ("provider_failure",subreason)
    assert record["label"] is None
    assert all(a["usage_basis"] == "unknown_non200" for a in record["attempt_records"])

def test_support_burn_round_trip(tmp_path, request_packet):
    from clavain_selector import burn
    record = invoke(tmp_path, request_packet, [{"status":200,"body":json.dumps(answer())}])
    assert burn.accounting_from_record(record)["complete"] is True
    record["attempts"] += 1
    assert burn.accounting_from_record(record)["complete"] == "invalid"

def test_model_echo_is_hashed(tmp_path, request_packet):
    raw = answer()
    raw["model"] = "dummy-qualification-value" + request_packet["claim"]["text"]
    record = invoke(tmp_path, request_packet, [{"status":200,"body":json.dumps(raw),"headers":{"x-request-id":raw["model"],"retry-after":raw["model"]}}])
    assert record["subreason"] == "model_mismatch"
    assert "dummy-qualification-value" not in json.dumps(record)
    assert request_packet["claim"]["text"] not in json.dumps(record)

def direct(request, *, monkeypatch, loader=None):
    from clavain_selector import support, credentials, jev_client as j
    registry = json.loads((ROOT / "config/selector-integrations.json").read_text())
    registry["integrations"]["support_check"].update(enabled=True,session_budget=4,daily_budget=8)
    output = io.StringIO()
    def transport(body, timeout, progress):
        progress("response_read")
        return j.RawReply(200, {}, json.dumps(answer()).encode())
    support.run(io.StringIO(json.dumps(request)),output,env={"CLAVAIN_SELECTOR_SUPPORT_CHECK":"shadow"},registry=registry,transport=transport,credential_loader=loader or (lambda: credentials.SecretStr("dummy-qualification-value")))
    record = json.loads(output.getvalue())
    validate_record(record)
    return record

def test_persistence_failure_keeps_label(monkeypatch,request_packet):
    from clavain_selector import records
    monkeypatch.setattr(records,"append_record",lambda *a: (_ for _ in ()).throw(OSError("dummy-private-message")))
    record = direct(request_packet,monkeypatch=monkeypatch)
    assert record["outcome"] == "label" and record["persisted"] is False
    assert record["attempts"] == 1
    assert "dummy-private-message" not in json.dumps(record)

def test_validator_failure_keeps_accounting(monkeypatch,request_packet):
    from clavain_selector import support
    monkeypatch.setattr(support,"_validate_support_response",lambda *a: (_ for _ in ()).throw(RuntimeError("dummy")))
    record = direct(request_packet,monkeypatch=monkeypatch)
    assert record["outcome"] == "internal_error"
    assert record["jev_usage_accounting"]["reported_attempts"] == 1

@pytest.mark.parametrize("field", ["run_id","case_id","claim","description","section"])
def test_loaded_key_literal_refused(monkeypatch,request_packet,field):
    literal = "dummy-qualification-value"
    import hashlib
    if field in ("run_id","case_id"): request_packet[field] = literal
    elif field == "claim": request_packet["claim"] = {"text":literal,"sha256":hashlib.sha256(literal.encode()).hexdigest()}
    elif field == "description": request_packet["label_descriptions"]["supported"] = literal
    else:
        # Claim and description cases cover literal scanning; a section must
        # first pass its real source provenance.
        root = Path(request_packet["project_root"])
        (root / "source.md").write_text(literal + "\n")
        env = {"PATH":"/usr/bin:/bin","HOME":str(root.parent),"GIT_CONFIG_GLOBAL":"/dev/null","GIT_CONFIG_NOSYSTEM":"1"}
        subprocess.run(["git","-C",str(root),"add","source.md"],env=env,check=True)
        subprocess.run(["git","-C",str(root),"commit","-qm","Fixture update"],env=env,check=True)
        request_packet["revision"] = subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],env=env,text=True).strip()
        request_packet["sections"][0].update(text=literal+"\n",sha256=hashlib.sha256((literal+"\n").encode()).hexdigest())
    record = direct(request_packet,monkeypatch=monkeypatch)
    assert record["outcome"] == "refused"
    assert record["attempts"] == 0
    assert literal not in json.dumps(record)

def test_credential_unavailable(monkeypatch,request_packet):
    from clavain_selector import credentials
    def unavailable(): raise credentials.CredentialUnavailable("dummy")
    record=direct(request_packet,monkeypatch=monkeypatch,loader=unavailable)
    assert (record["outcome"],record["subreason"]) == ("unavailable","credential_unavailable")
    assert record["attempts"] == 0

def test_circuit_open(monkeypatch,request_packet):
    from clavain_selector import jev_client as j
    monkeypatch.setattr(j.Breaker,"check",lambda *a: "circuit_open")
    record=direct(request_packet,monkeypatch=monkeypatch,loader=lambda: pytest.fail("loaded behind breaker"))
    assert (record["outcome"],record["subreason"]) == ("unavailable","circuit_open")

def test_invalid_response_is_breaker_failure(monkeypatch,request_packet):
    from clavain_selector import support, jev_client as j
    observed=[]
    monkeypatch.setattr(j.Breaker,"record",lambda self,result: observed.append(result))
    monkeypatch.setattr(support,"_validate_support_response",lambda *a: (_ for _ in ()).throw(support.SupportInvalid("usage")))
    record=direct(request_packet,monkeypatch=monkeypatch)
    assert record["outcome"] == "invalid"
    assert isinstance(observed[0],j.JevFailure)

def test_tie_and_unclear(tmp_path,request_packet):
    raw=answer()
    raw["answers"]["support"]["probabilities"]={"supported":.5,"not_supported":.5,"unclear":0}
    record=invoke(tmp_path,request_packet,[{"status":200,"body":json.dumps(raw)}])
    assert (record["outcome"],record["subreason"]) == ("abstain","tie")
    record=invoke(tmp_path,request_packet,[{"status":200,"body":json.dumps(answer("unclear"))}])
    assert (record["outcome"],record["label"]) == ("label","unclear")
