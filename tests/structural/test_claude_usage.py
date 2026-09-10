"""Exercise budgeted dispatch with a real child process and synthetic provider events."""
import json
import os
from pathlib import Path
import subprocess
import signal
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-fable-5-1"


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


def dispatch(tmp_path, stream, *, exit_code=0, stderr="", budget=10000, via=None, cancel=False, governed=False):
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
           "CLAVAIN_REQUIRE_USAGE": "1", "CLAVAIN_REVIEW_EVENTS": str(ledger),
           "CLAVAIN_TOKEN_BUDGET": str(budget), "CLAVAIN_DISPATCH_ID": "fixture-dispatch",
           "CLAVAIN_CONTEXT_GATEWAY_MODE": "off", "CLAVAIN_429_BACKOFF_SECONDS": "0"}
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


def test_delta_null_input_and_cache_fields_are_not_usage(tmp_path):
    stream = events()
    stream[4]["event"]["usage"].update(input_tokens=None, cache_read_input_tokens=None,
                                     cache_creation_input_tokens=None)
    proc, output, records = dispatch(tmp_path, stream)
    assert proc.returncode == 0, proc.stderr
    assert records[-1]["complete"] and records[-1]["budget_tokens"] == 69
    assert any(row["budget_tokens"] == 67 for row in records)
    assert "STATUS: pass" in Path(str(output) + ".verdict").read_text()


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
def test_invalid_thinking_breakdown_blocks_success(tmp_path, thinking, location):
    stream = events()
    if location == "model":
        stream[-1]["modelUsage"][MODEL]["thinkingTokens"] = thinking
    else:
        stream[-1]["usage"]["output_tokens_details"] = {"thinking_tokens": thinking}
    proc, _, records = dispatch(tmp_path, stream)
    assert proc.returncode != 0
    assert records[-1]["terminal"] and not records[-1]["complete"]


@pytest.mark.parametrize("change", ["missing_result", "bad_json", "mismatch", "zeroed", "unknown_tokens"])
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


def test_nonzero_backend_preserved_with_complete_accounting(tmp_path):
    proc, output, records = dispatch(tmp_path, events(), exit_code=7, stderr="rate limit 429")
    assert proc.returncode == 7
    assert records[-1]["budget_tokens"] == 69
    assert records[-1]["complete"]
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()
    assert (tmp_path / "calls").read_text() == "called\n"


def test_cache_tokens_exhaust_budget(tmp_path):
    proc, output, records = dispatch(tmp_path, events(), budget=60)
    assert proc.returncode != 0
    assert records[-1]["budget_tokens"] >= 60
    assert records[-1]["status"] == "budget_exhausted"
    assert not records[-1]["complete"]


def test_zaka_rejected_before_any_model_call(tmp_path):
    proc, _, _ = dispatch(tmp_path, events(), via="zaka")
    assert proc.returncode != 0
    assert not (tmp_path / "calls").exists()
    assert "usage" in proc.stderr.lower()


def test_group_cancellation_retains_usage_and_error_verdict_after_wrapper_exit(tmp_path):
    proc, output, records = dispatch(tmp_path, events()[:2], cancel=True)
    assert proc.returncode != 0
    assert records[-1]["terminal"] and not records[-1]["complete"]
    assert records[-1]["budget_tokens"] == 60
    assert records[-1]["status"] == "cancelled"
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()


@pytest.mark.parametrize("complete", [True, False])
def test_governed_rate_limit_after_spend_never_retries(tmp_path, complete):
    proc, output, records = dispatch(tmp_path, events() if complete else events()[:-1],
                                    exit_code=7, stderr="rate limit 429", governed=True)
    assert proc.returncode == 7, proc.stderr
    assert (tmp_path / "calls").read_text() == "called\n"
    assert records[-1]["complete"] is complete
    assert "STATUS: error" in Path(str(output) + ".verdict").read_text()
