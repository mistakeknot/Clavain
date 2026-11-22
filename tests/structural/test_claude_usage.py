"""Exercise budgeted dispatch with a real child process and synthetic provider events."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-opus-5-5"


def events():
    usage = dict(input_tokens=10, cache_read_input_tokens=30,
                 cache_creation_input_tokens=20, output_tokens=1)
    message = dict(id="msg1", model=MODEL, usage=usage, content=[])
    return [
        dict(type="system", subtype="init", session_id="$SESSION", model=MODEL),
        dict(type="stream_event", session_id="$SESSION", event=dict(
            type="message_start", message=message)),
        dict(type="assistant", session_id="$SESSION", message=message),
        dict(type="assistant", session_id="$SESSION", message=message),
        dict(type="stream_event", session_id="$SESSION", event=dict(
            type="message_delta", usage=dict(output_tokens=7))),
        dict(type="result", subtype="success", is_error=False,
             session_id="$SESSION", result="Reviewed.\nVERDICT: PASS",
             usage={**usage, "output_tokens": 9}, modelUsage={MODEL: dict(
                 inputTokens=10, cacheReadInputTokens=30,
                 cacheCreationInputTokens=20, outputTokens=9)}),
    ]


def dispatch(tmp_path, stream, *, exit_code=0, stderr="", budget=10000, via=None, cancel=False, governed=False, pool_env=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fixture = tmp_path / "provider.json"
    fixture.write_text(json.dumps(stream))
    child = bin_dir / "claude"
    child.write_text("""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.267 (Claude Code)'); sys.exit(0)
sys.stdin.read()
if os.environ.get('EXPECTED_POOL_TOKEN'):
    assert os.environ.get('ANTHROPIC_AUTH_TOKEN') == os.environ['EXPECTED_POOL_TOKEN']
session = sys.argv[sys.argv.index('--session-id')+1] if '--session-id' in sys.argv else 'legacy'
with open(os.environ['CALLS'], 'a') as f: f.write('called\\n')
for event in json.loads(Path(os.environ['FIXTURE']).read_text()):
    text = event if isinstance(event, str) else json.dumps(event)
    print(text.replace('$SESSION', session), flush=True)
if os.environ.get('PROVIDER_WAIT') == '1': time.sleep(30)
print(os.environ['PROVIDER_STDERR'], file=sys.stderr)
sys.exit(int(os.environ['PROVIDER_EXIT']))
""")
    child.chmod(0o755)
    output = tmp_path / "review.md"
    ledger = tmp_path / "usage.jsonl"
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
           "FIXTURE": str(fixture), "CALLS": str(tmp_path / "calls"),
           "PROVIDER_EXIT": str(exit_code), "PROVIDER_STDERR": stderr,
           "PROVIDER_WAIT": "1" if cancel else "0",
           "CLAVAIN_REQUIRE_USAGE": "1", "CLAVAIN_BB_DIRECT_POOL": "0", "CLAVAIN_REVIEW_EVENTS": str(ledger),
           "CLAVAIN_TOKEN_BUDGET": str(budget), "CLAVAIN_DISPATCH_ID": "fixture-dispatch",
           "CLAVAIN_CONTEXT_GATEWAY_MODE": "off"}
    if pool_env:
        env.update(pool_env)
        host = json.loads((ROOT/'config/bb-integration.json').read_text())['allowed_host_ids'][0]
        bb = bin_dir / 'bb'
        bb.write_text('#!/usr/bin/env python3\nimport json\nprint(' + repr(json.dumps(dict(thread=dict(id='fixture-thread', environment=dict(hostId=host))))) + ')\n')
        bb.chmod(0o755)
        env['BB_CLI'] = str(bb)
    cmd = ["bash", str(ROOT / "scripts/dispatch.sh"), "--to", "claude", "--model", MODEL,
           "-C", str(tmp_path), "-o", str(output)]
    if governed:
        subprocess.run(["ic", "init"], cwd=tmp_path, check=True, capture_output=True)
        cmd = ["bash", str(ROOT / "scripts/dispatch.sh"), "--role", "plan-review",
               "--producer-identity", "gpt-6-astra", "-C", str(tmp_path), "-o", str(output)]
    if via:
        cmd += ["--via", via]
    if cancel:
        p = subprocess.Popen(cmd + ["Review this fixture only"], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if ledger.exists() and '"budget_tokens":60' in ledger.read_text():
                    break
                time.sleep(.05)
            os.killpg(p.pid, signal.SIGTERM)
            out, err = p.communicate(timeout=12)
            proc = subprocess.CompletedProcess(p.args, p.returncode, out, err)
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
    else:
        proc = subprocess.run(cmd + ["Review this fixture only"], env=env,
                              capture_output=True, text=True, timeout=30)
    records = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    return proc, output, records


@pytest.mark.requires_ic
@pytest.mark.parametrize("mode", ["success", "refused", "missing-account", "wrong-totals", "provider-fail"])
def test_pooled_dispatch_admits_before_spending_and_retains_attribution(tmp_path, mode):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(dict(threadId="fixture-thread", availability=dict(claude=True, codex=True))).encode())
        def do_POST(self):
            action = self.path.rsplit("/", 1)[-1]
            calls.append(action)
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.headers['x-bb-account-pool-token'] == 'synthetic-host-token'
            self.send_response(503 if mode == 'refused' else 200); self.end_headers()
            if mode == 'refused': return
            data = dict(version=1, id='a'*32, host_id='fixture-host', attempt_id=payload['attempt_id'], provider='claude')
            if action == 'begin':
                data.update(token='synthetic-scoped-token', expires_at=9999999999999)
            else:
                data.update(sealed=True, valid=True, complete=True, requests=[dict(id=1, kind='inference', state='finished', hops=[dict(index=1, account_id='fixture-account', provider='claude', status=200, state='complete', model=MODEL, usage=dict(input_tokens=10, output_tokens=9, cache_read_input_tokens=30, cache_creation_input_tokens=20))])])
                if mode == 'missing-account': data['requests'][0]['hops'][0]['account_id'] = None
                if mode == 'wrong-totals': data['requests'][0]['hops'][0]['usage']['input_tokens'] = 11
            self.wfile.write(json.dumps(data).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    try:
        proc, _, records = dispatch(tmp_path, events(), exit_code=7 if mode == 'provider-fail' else 0, pool_env=dict(
            BB_SERVER_URL=origin, BB_THREAD_ID='fixture-thread', CLAVAIN_BB_DIRECT_POOL='1',
            ANTHROPIC_BASE_URL=origin+'/api/v1/plugins/account-pool/http',
            ANTHROPIC_AUTH_TOKEN='synthetic-host-token', CODEX_POOL_AUTH_TOKEN='',
            EXPECTED_POOL_TOKEN='synthetic-scoped-token'))
    finally:
        server.shutdown(); server.server_close(); thread.join()
    if mode == 'success':
        assert proc.returncode == 0, proc.stderr
        assert calls == ['begin', 'finalize']
        ref = records[-1]['pool_receipt']
        data = json.loads(Path(ref['path']).read_text())
        assert data['requests'][0]['hops'][0]['account_id'] == 'fixture-account'
    elif mode == 'refused':
        assert proc.returncode != 0
        assert calls == ['begin']
        assert not (tmp_path/'calls').exists()
    else:
        assert proc.returncode != 0
        assert calls == ['begin', 'finalize']
        assert records[-1]['status'] != 'success'


@pytest.mark.requires_ic
def test_budgeted_claude_deduplicates_and_reconciles_cache_and_output(tmp_path):
    proc, output, records = dispatch(tmp_path, events())
    assert proc.returncode == 0, proc.stderr
    assert output.read_text() == "Reviewed.\nVERDICT: PASS\n"
    assert records, "budget-required dispatch produced no attributable usage"
    final = records[-1]
    assert final["terminal"] and final["complete"]
    assert final["budget_tokens"] == 69
    assert final["output_tokens"] == 9
    assert final["model_identity"] == MODEL
    assert final["dispatch_id"] == "fixture-dispatch"
    assert any(row["budget_tokens"] == 67 for row in records)
    assert "STATUS: pass" in Path(str(output) + ".verdict").read_text()


@pytest.mark.requires_ic
def test_delta_null_input_and_cache_fields_are_not_usage(tmp_path):
    stream = events()
    stream[4]["event"]["usage"].update(input_tokens=None, cache_read_input_tokens=None,
                                     cache_creation_input_tokens=None)
    proc, output, records = dispatch(tmp_path, stream)
    assert proc.returncode == 0, proc.stderr
    assert records[-1]["complete"] and records[-1]["budget_tokens"] == 69
    assert any(row["budget_tokens"] == 67 for row in records)
    assert "STATUS: pass" in Path(str(output) + ".verdict").read_text()


@pytest.mark.requires_ic
def test_thinking_breakdown_is_not_added_to_output_or_auxiliary_usage(tmp_path):
    stream = events()
    stream[-1]["usage"]["output_tokens_details"] = {"thinking_tokens": 6}
    stream[-1]["modelUsage"][MODEL]["thinkingTokens"] = 6
    stream[-1]["modelUsage"]["claude-haiku-4-5-20251001"] = dict(
        inputTokens=4, outputTokens=2, thinkingTokens=0)
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode == 0, proc.stderr
    assert records[-1]["complete"] and records[-1]["budget_tokens"] == 75
    assert records[-1]["output_tokens"] == 11


@pytest.mark.parametrize("thinking", [-1, 10, True, 1.5, None])
@pytest.mark.parametrize("location", ["model", "main"])
@pytest.mark.requires_ic
def test_invalid_thinking_breakdown_blocks_success(tmp_path, thinking, location):
    stream = events()
    if location == "model":
        stream[-1]["modelUsage"][MODEL]["thinkingTokens"] = thinking
    else:
        stream[-1]["usage"]["output_tokens_details"] = {"thinking_tokens": thinking}
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records[-1]["terminal"] and not records[-1]["complete"]


@pytest.fixture
def meter():
    spec = importlib.util.spec_from_file_location("claude_usage_meter", ROOT / "scripts/claude_usage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class LocalMeter(module.Meter):
        def identity(self, model):
            return model

    return LocalMeter(MODEL, "dispatch", "invocation", "$SESSION", "unused")


def tool_record(name="Bash", source="stream", tool_id="tool-parent"):
    block = dict(type="tool_use", id=tool_id, name=name, input={})
    if source == "stream":
        return dict(type="stream_event", event=dict(
            type="content_block_start", index=0, content_block=block))
    return dict(type="assistant", message=dict(
        id="msg1", model=MODEL, usage=events()[1]["event"]["message"]["usage"],
        content=[block]))


def tool_heartbeat(parent="tool-parent"):
    # Real provider shape: tool_use_id is a heartbeat ID, parent is the Bash call.
    return dict(type="tool_progress", tool_use_id=parent + "-heartbeat-0",
                tool_name="Bash", parent_tool_use_id=parent,
                elapsed_time_seconds=30, heartbeat=True, session_id="$SESSION",
                uuid="00000000-0000-4000-8000-000000000000")


@pytest.mark.parametrize("source", ["stream", "assistant"])
@pytest.mark.parametrize("name", ["Bash", "Read", "Grep"])
@pytest.mark.parametrize("child_kind", ["tool_progress", "user", "stream_event"])
def test_known_ordinary_tool_parent_is_not_subagent(meter, source, name, child_kind):
    meter.event(tool_record(name, source))
    child = tool_heartbeat()
    child["type"] = child_kind
    meter.event(child)


@pytest.mark.parametrize("source", ["stream", "assistant"])
@pytest.mark.parametrize("name", ["Agent", "Task"])
def test_subagent_tool_call_and_children_rejected(meter, source, name):
    with pytest.raises(ValueError, match="subagent activity"):
        meter.event(tool_record(name, source))
    # Even after a caller catches the first error, its child cannot be accepted.
    with pytest.raises(ValueError):
        meter.event(tool_heartbeat())


@pytest.mark.parametrize("child_kind", ["tool_progress", "assistant", "user", "stream_event"])
def test_unknown_parent_fails_closed_despite_ordinary_tool_name(meter, child_kind):
    meter.event(tool_record())
    child = tool_heartbeat("unseen-parent")
    child["type"] = child_kind
    with pytest.raises(ValueError):
        meter.event(child)


def test_duplicate_tool_records_agree_and_conflicts_fail_closed(meter):
    meter.event(tool_record())
    meter.event(tool_record(source="assistant"))
    meter.event(tool_heartbeat())
    with pytest.raises(ValueError):
        meter.event(tool_record("Read"))


@pytest.mark.parametrize("field", ["id", "name"])
@pytest.mark.parametrize("bad", [None, "", True, ["Bash"]])
def test_invalid_tool_identity_fails_closed(meter, field, bad):
    event = tool_record()
    event["event"]["content_block"][field] = bad
    with pytest.raises(ValueError, match="tool use identity"):
        meter.event(event)


def test_subagent_call_under_known_ordinary_parent_is_rejected(meter):
    meter.event(tool_record())
    event = tool_record("Agent", tool_id="agent-call")
    event["parent_tool_use_id"] = "tool-parent"
    with pytest.raises(ValueError, match="subagent activity"):
        meter.event(event)
    with pytest.raises(ValueError, match="subagent activity"):
        meter.event(tool_heartbeat("agent-call"))


@pytest.mark.requires_ic
def test_bash_heartbeat_dispatch_reconciles_without_changing_usage(tmp_path):
    stream = events()
    stream[2:2] = [tool_record(), tool_record(source="assistant"), tool_heartbeat()]
    proc, output, records = dispatch(tmp_path, stream)
    assert proc.returncode == 0, proc.stderr
    assert records[-1]["complete"] and records[-1]["budget_tokens"] == 69
    assert output.read_text() == "Reviewed.\nVERDICT: PASS\n"


@pytest.mark.requires_ic
@pytest.mark.parametrize("parent", ["Agent", "Task", "unknown"])
def test_subagent_or_unknown_parent_dispatch_never_passes(tmp_path, parent):
    stream = events()
    inserted = ([tool_record(parent)] if parent != "unknown" else [])
    stream[2:2] = inserted + [tool_heartbeat()]
    proc, output, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records[-1]["terminal"] and not records[-1]["complete"]
    assert records[-1]["status"] == "accounting_error"
    assert "STATUS: pass" not in Path(str(output) + ".verdict").read_text()


def load_counts():
    spec = importlib.util.spec_from_file_location("claude_usage_under_test", ROOT / "scripts/claude_usage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.counts


STREAM_USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 7,
                "output_tokens": 3, "cache_creation": {"ephemeral_5m_input_tokens": 40,
                                                       "ephemeral_1h_input_tokens": 60}}
MODEL_USAGE = {"inputTokens": 2, "outputTokens": 3, "cacheReadInputTokens": 7, "cacheCreationInputTokens": 100,
               "cacheCreationEphemeral5mInputTokens": 40, "cacheCreationEphemeral1hInputTokens": 60}


def test_ephemeral_cache_breakdown_accepted_without_double_counting():
    counts = load_counts()
    expected = {"input_tokens": 2, "output_tokens": 3, "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 100}
    assert counts(STREAM_USAGE) == expected
    assert counts(MODEL_USAGE, model=True) == expected
    # Breakdown alone (no 5m/1h fields) yields the identical total.
    plain = {k: v for k, v in STREAM_USAGE.items() if k != "cache_creation"}
    assert counts(plain) == counts(STREAM_USAGE)


def test_ephemeral_cache_breakdown_may_be_partial_or_zero():
    counts = load_counts()
    usage = {**STREAM_USAGE, "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                                "ephemeral_1h_input_tokens": 100}}
    assert counts(usage)["cache_creation_input_tokens"] == 100
    model = {k: v for k, v in MODEL_USAGE.items() if k != "cacheCreationEphemeral5mInputTokens"}
    assert counts(model, model=True)["cache_creation_input_tokens"] == 100


@pytest.mark.parametrize("form", ["stream", "model"])
def test_ephemeral_cache_breakdown_exceeding_total_is_rejected(form):
    counts = load_counts()
    if form == "stream":
        usage = {**STREAM_USAGE, "cache_creation": {"ephemeral_5m_input_tokens": 41,
                                                    "ephemeral_1h_input_tokens": 60}}
    else:
        usage = {**MODEL_USAGE, "cacheCreationEphemeral5mInputTokens": 41}
    with pytest.raises(ValueError, match="exceeds total"):
        counts(usage, model=form == "model")


@pytest.mark.parametrize("form", ["stream", "model"])
@pytest.mark.parametrize("bad", [-1, True, 1.5, None, "3", (1 << 53) + 1])
def test_invalid_ephemeral_cache_breakdown_value_is_rejected(form, bad):
    counts = load_counts()
    if form == "stream":
        usage = {**STREAM_USAGE, "cache_creation": {"ephemeral_5m_input_tokens": bad}}
    else:
        usage = {**MODEL_USAGE, "cacheCreationEphemeral1hInputTokens": bad}
    with pytest.raises(ValueError, match="invalid token field"):
        counts(usage, model=form == "model")


def test_unknown_cache_or_token_fields_still_rejected():
    counts = load_counts()
    with pytest.raises(ValueError, match="unknown cache creation field"):
        counts({**STREAM_USAGE, "cache_creation": {"ephemeral_24h_input_tokens": 1}})
    with pytest.raises(ValueError, match="invalid cache creation breakdown"):
        counts({**STREAM_USAGE, "cache_creation": 5})
    with pytest.raises(ValueError, match="unknown token field: cacheCreationEphemeral24hInputTokens"):
        counts({**MODEL_USAGE, "cacheCreationEphemeral24hInputTokens": 1}, model=True)
    with pytest.raises(ValueError, match="unknown token field: mysteryTokens"):
        counts({**MODEL_USAGE, "mysteryTokens": 1}, model=True)
    # The camel breakdown names are not valid in the snake_case stream form.
    with pytest.raises(ValueError, match="unknown token field"):
        counts({**STREAM_USAGE, "cacheCreationEphemeral5mInputTokens": 1})


@pytest.mark.requires_ic
def test_ephemeral_cache_breakdown_in_both_forms_does_not_change_budget(tmp_path):
    stream = events()
    stream[-1]["usage"]["cache_creation"] = {"ephemeral_5m_input_tokens": 5,
                                             "ephemeral_1h_input_tokens": 15}
    stream[-1]["modelUsage"][MODEL].update(cacheCreationEphemeral5mInputTokens=5,
                                           cacheCreationEphemeral1hInputTokens=15)
    proc, output, records = dispatch(tmp_path, stream)
    assert proc.returncode == 0, proc.stderr
    assert records[-1]["complete"] and records[-1]["budget_tokens"] == 69
    assert "STATUS: pass" in Path(str(output) + ".verdict").read_text()


@pytest.mark.requires_ic
def test_ephemeral_cache_breakdown_over_total_blocks_success(tmp_path):
    stream = events()
    stream[-1]["modelUsage"][MODEL].update(cacheCreationEphemeral5mInputTokens=21)
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records[-1]["terminal"] and not records[-1]["complete"]


@pytest.mark.requires_ic
def test_failed_final_retains_observed_main_and_auxiliary_lower_bound(tmp_path):
    stream = events()
    stream[-1].update(subtype="error_during_execution", is_error=True,
                      usage=dict(input_tokens=0, output_tokens=0),
                      modelUsage={"claude-haiku-4-5-20251001": dict(
                          inputTokens=4, outputTokens=2, thinkingTokens=0)})
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    final = records[-1]
    assert final["terminal"] and not final["complete"]
    assert final["budget_tokens"] == 73  # 67 observed main + 6 auxiliary
    assert final["output_tokens"] == 9


@pytest.mark.requires_ic
def test_invalid_model_retains_other_valid_model_usage(tmp_path):
    stream = events()
    stream[-1]["modelUsage"][MODEL]["thinkingTokens"] = -1
    stream[-1]["modelUsage"]["claude-haiku-4-5-20251001"] = dict(inputTokens=4, outputTokens=2)
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records[-1]["budget_tokens"] == 75  # valid main result + valid auxiliary
    assert not records[-1]["complete"]


@pytest.mark.requires_ic
def test_missing_model_totals_retain_valid_main_result(tmp_path):
    stream = events()
    del stream[-1]["modelUsage"]
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records[-1]["budget_tokens"] == 69
    assert not records[-1]["complete"]


@pytest.mark.parametrize("change", ["missing_result", "bad_json", "mismatch", "zeroed", "unknown_tokens"])
@pytest.mark.requires_ic
def test_incomplete_or_inconsistent_usage_never_passes(tmp_path, change):
    stream = events()
    if change == "missing_result":
        stream.pop()
    elif change == "bad_json":
        stream.insert(-1, '{"type":"assistant"')
    elif change == "mismatch":
        stream[0]["model"] = "claude-opus-5"
    elif change == "zeroed":
        stream[-1]["modelUsage"][MODEL]["inputTokens"] = 0
    else:
        stream[-1]["usage"]["unmetered_tokens"] = 3
    proc, output, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records and records[-1]["terminal"]
    assert not records[-1]["complete"]
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()


@pytest.mark.requires_ic
def test_nonzero_backend_preserved_with_complete_accounting(tmp_path):
    proc, output, records = dispatch(tmp_path, events(), exit_code=7, stderr="rate limit 429")
    assert proc.returncode == 7
    assert records[-1]["budget_tokens"] == 69
    assert records[-1]["complete"]
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()
    assert (tmp_path / "calls").read_text() == "called\n"


@pytest.mark.requires_ic
def test_cache_tokens_exhaust_budget(tmp_path):
    proc, output, records = dispatch(tmp_path, events(), budget=60)
    assert proc.returncode != 0
    assert records[-1]["budget_tokens"] >= 60
    assert records[-1]["status"] == "budget_exhausted"
    assert not records[-1]["complete"]


@pytest.mark.parametrize("complete", [True, False])
@pytest.mark.requires_ic
def test_uncapped_claude_retains_usage_and_completeness_gate(tmp_path, complete):
    stream = events() if complete else events()[:-1]
    proc, output, records = dispatch(tmp_path, stream, budget=0)
    assert (proc.returncode == 0) == complete
    assert records[-1]["terminal"]
    assert records[-1]["complete"] == complete
    assert records[-1]["budget_tokens"] > 60
    assert records[-1]["status"] != "budget_exhausted"
    assert ("STATUS: pass" in Path(str(output) + ".verdict").read_text()) == complete


def test_zaka_rejected_before_any_model_call(tmp_path):
    proc, _, _ = dispatch(tmp_path, events(), via="zaka")
    assert proc.returncode != 0
    assert not (tmp_path / "calls").exists()
    assert "usage" in proc.stderr.lower()


@pytest.mark.requires_ic
def test_group_cancellation_retains_usage_and_error_verdict_after_wrapper_exit(tmp_path):
    proc, output, records = dispatch(tmp_path, events()[:2], cancel=True)
    # The shell wrapper can exit before the accounting child flushes its final
    # row. Observe that durable row rather than assuming the child was reaped.
    deadline = time.monotonic() + 10
    while records and not records[-1]["terminal"] and time.monotonic() < deadline:
        time.sleep(.05)
        records = [json.loads(line) for line in (tmp_path / "usage.jsonl").read_text().splitlines()]
    assert proc.returncode != 0
    assert records[-1]["terminal"] and not records[-1]["complete"]
    assert records[-1]["budget_tokens"] == 60
    assert records[-1]["status"] == "cancelled"
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()


@pytest.mark.parametrize("complete", [True, False])
@pytest.mark.requires_ic
def test_governed_rate_limit_after_spend_never_retries(tmp_path, complete):
    proc, output, records = dispatch(tmp_path, events() if complete else events()[:-1],
                                    exit_code=7, stderr="rate limit 429", governed=True)
    assert proc.returncode == 7, proc.stderr
    assert (tmp_path / "calls").read_text() == "called\n"
    assert records[-1]["complete"] is complete
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()
