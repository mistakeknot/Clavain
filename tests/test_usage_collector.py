import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


def subject():
    path = Path(__file__).parents[1] / "scripts/usage_collector.py"
    spec = importlib.util.spec_from_file_location("usage_collector", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_identity_comes_only_from_unambiguous_native_events(tmp_path, monkeypatch):
    m = subject()
    monkeypatch.setenv("CODEX_THREAD_ID", "parent")
    path = tmp_path / "events.jsonl"
    path.write_text('{"type":"turn.completed","usage":{"input_tokens":3}}\n')
    assert m.native_identity(path)["thread_id"] is None
    path.write_text('{"type":"thread.started","thread_id":"native-1"}\n')
    assert m.native_identity(path)["thread_id"] == "native-1"
    path.write_text(path.read_text() + '{"type":"thread.started","thread_id":"native-2"}\n')
    assert m.native_identity(path)["thread_id"] is None


def test_malformed_duplicate_and_missing_native_events(tmp_path):
    m = subject()
    assert m.native_identity(tmp_path / "absent")["identity_coverage"] == "incomplete"
    path = tmp_path / "events"
    for text in ('{"type":"thread.started","thread_id":"t","thread_id":"x"}\n',
                 '{"type":"thread.started","thread_id":"t"}\nnot-json\n'):
        path.write_text(text)
        assert m.native_identity(path)["thread_id"] is None


def test_identity_digest_excludes_unrelated_private_event_fields(tmp_path):
    m = subject()
    path = tmp_path / "events"
    path.write_text('{"type":"thread.started","thread_id":"native","account":"private-one"}\n')
    first = m.native_identity(path)
    path.write_text('{"type":"thread.started","thread_id":"native","account":"private-two"}\n'
                    '{"type":"item.completed","text":"credential-like-private-content"}\n')
    assert m.native_identity(path) == first
    assert "event_sha256" not in first


def test_rate_limits_sanitized_before_hash_and_sources_not_merged():
    m = subject()
    raw = {"rateLimits": {"primary": {"usedPercent": 12, "resetsAt": 200,
             "windowDurationMins": 300}, "accountId": "private-account"},
           "credential": "secret"}
    clean = m.sanitize_rate_limits(raw)
    assert clean == [{"bucket": "primary", "used_percent": 12,
                      "resets_at": 200, "window_minutes": 300}]
    other = dict(raw, credential="another-secret")
    assert m.payload_hash(clean) == m.payload_hash(m.sanitize_rate_limits(other))
    assert "private-account" not in json.dumps(clean)


def test_nullable_thread_counters_and_identity_mismatch():
    m = subject()
    assert m.sanitize_thread_usage({"threadUsage": None}, "t") is None
    raw = {"threadUsage": {"threadId": "t", "estimatedUsageCreditsMicros": 7,
        "estimatedUsageUsdMicros": None, "groups": [{"inputTokens": 11,
        "cachedInputTokens": 4, "outputTokens": None, "estimatedUsageCreditsMicros": 7,
        "apiKey": "secret"}]}}
    clean = m.sanitize_thread_usage(raw, "t")
    assert clean["groups"][0]["output_tokens"] is None
    assert clean["groups"][0]["cached_input_tokens"] == 4
    assert "secret" not in json.dumps(clean)
    with pytest.raises(ValueError):
        m.sanitize_thread_usage(raw, "other")


def test_invalid_counters_rejected_instead_of_coerced():
    m = subject()
    for value in (-1, True, float("nan"), "12", 101):
        with pytest.raises(ValueError):
            m.sanitize_rate_limits({"rateLimits": {"primary": {"usedPercent": value}}})


def test_account_tokens_not_credits_or_percent():
    m = subject()
    assert m.sanitize_account_usage({"summary": {"lifetimeTokens": None,
        "peakDailyTokens": 20, "accountId": "secret"}}) == {
            "lifetime_tokens": None, "peak_daily_tokens": 20}


def fake_server(tmp_path, body):
    import sys
    path = tmp_path / "fake-codex"
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o700)
    return str(path)


def test_transport_only_reads_and_reaps(tmp_path):
    m = subject()
    log = tmp_path / "requests"
    executable = fake_server(tmp_path, f'''import json,sys
for line in sys.stdin:
 r=json.loads(line)
 with open({str(log)!r},'a') as f:f.write(r['method']+'\\n')
 if 'id' in r:print(json.dumps({{'id':r['id'],'result':{{}}}}),flush=True)
''')
    server = m.AppServer(executable, timeout=3)
    pid = server.process.pid
    try:
        server.initialize()
        assert server.request("account/usage/read", {"threadId": "t"}) == {}
        with pytest.raises(ValueError):
            server.request("turn/start")
    finally:
        metadata = server.close()
    assert log.read_text().splitlines() == ["initialize", "initialized", "account/usage/read"]
    assert metadata["allowance_effect"] == "unknown"
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_transport_timeout_and_malformed_response_are_distinct(tmp_path):
    m = subject()
    ready = tmp_path / "malformed-output-ready"
    for body, expected in (("import time; time.sleep(30)\n", "timeout"),
                           ("print('not-json',flush=True)\nfrom pathlib import Path\n"
                            + f"Path({str(ready)!r}).touch()\n"
                            + "import time; time.sleep(30)\n", "malformed-response")):
        executable = fake_server(tmp_path, body)
        server = m.AppServer(executable, timeout=0.15)
        try:
            if expected == "malformed-response":
                # Test parsing after bytes exist, rather than racing interpreter
                # startup against the independently tested response timeout.
                deadline = time.monotonic() + 1
                while not ready.exists():
                    assert server.process.poll() is None
                    assert time.monotonic() < deadline
                    time.sleep(0.005)
            with pytest.raises(m.RPCError) as error:
                server.initialize()
            assert error.value.status == expected
        finally:
            metadata = server.close()
        assert metadata["duration_seconds"] < 2


def test_collection_keeps_null_unavailable_and_sensitive_data_out(tmp_path):
    m = subject()
    executable = fake_server(tmp_path, '''import json,sys
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 if r['method']=='initialize':v={}
 elif r['method']=='account/rateLimits/read':v={'rateLimits':{'primary':{'usedPercent':7,'resetsAt':200}},'accountId':'DO_NOT_SAVE'}
 else:v={'summary':{'lifetimeTokens':None},'threadUsage':None,'accessToken':'DO_NOT_SAVE'}
 print(json.dumps({'id':r['id'],'result':v}),flush=True)
''')
    events = tmp_path / "events"
    events.write_text('{"type":"thread.started","thread_id":"actual-thread"}\n')
    value = m.collect(executable, events)
    assert "DO_NOT_SAVE" not in json.dumps(value)
    assert [r["kind"] for r in value["observations"]] == ["rate_limits", "account_usage", "account_usage"]
    assert value["observations"][-1]["reason"] == "thread-usage-null"
    assert value["observations"][0]["source_at"] is None
    assert value["account_attribution"] == "unknown"
    assert all(r["identity"]["native_thread_id"] == "actual-thread" for r in value["observations"])
    missing = m.collect(str(tmp_path / "absent"))
    assert all(r["status"] == "unavailable" for r in missing["observations"])


def test_cli_private_fresh_evidence_even_when_endpoint_unavailable(tmp_path):
    m = subject()
    dest = tmp_path / "private"
    command = [sys.executable, m.__file__, "--codex", str(tmp_path / "absent"),
               "--phase", "boundary", "--output-dir", str(dest)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert dest.stat().st_mode & 0o777 == 0o700
    paths = list(dest.glob("*-observation.json"))
    assert len(paths) == 3
    for path in paths:
        assert path.stat().st_mode & 0o777 == 0o600
        assert json.loads(path.read_text())["status"] == "unavailable"
    before = {p.name: p.read_bytes() for p in dest.iterdir()}
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert before == {p.name: p.read_bytes() for p in dest.iterdir()}


def test_collector_cancellation_reaps_child(tmp_path):
    import signal
    import time
    m = subject()
    pidfile = tmp_path / "pid"
    executable = fake_server(tmp_path, f'import os,time\nopen({str(pidfile)!r},"w").write(str(os.getpid()))\ntime.sleep(30)\n')
    process = subprocess.Popen([sys.executable, m.__file__, "--codex", executable,
        "--phase", "completion", "--output-dir", str(tmp_path / "evidence")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 3
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pidfile.exists()
        pid = int(pidfile.read_text())
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=3)
        assert process.returncode == 143
        evidence = json.loads((tmp_path / "evidence/cancelled-collection.json").read_text())
        assert evidence["transport"]["status"] == "cancelled"
        assert evidence["observations"] and all(r["status"] == "unavailable" for r in evidence["observations"])
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=3)


def test_codexbar_keeps_oauth_and_dashboard_separate_with_source_age():
    m = subject()
    raw = [{"provider": "codex", "source": "oauth", "usage": {
        "updatedAt": "2026-09-10T12:00:00Z", "accountEmail": "DO_NOT_SAVE",
        "primary": {"usedPercent": 11, "windowMinutes": 300, "resetsAt": "2026-09-10T15:00:00Z"}},
        "openaiDashboard": {"updatedAt": "2026-09-09T12:00:00Z", "signedInEmail": "DO_NOT_SAVE",
                            "codeReviewRemainingPercent": 81}}]
    rows = m.codexbar_observations(raw, dict(thread_id=None, identity_coverage="incomplete"))
    assert len(rows) == 2
    assert rows[0]["source"] == "codexbar.oauth"
    assert rows[1]["source"] == "codexbar.dashboard"
    assert rows[0]["source_at"] != rows[1]["source_at"]
    assert rows[0]["counters"][0]["value"] == 11
    assert rows[1]["counters"][0]["value"] == 81  # remaining is not silently inverted
    assert "DO_NOT_SAVE" not in json.dumps(rows)
