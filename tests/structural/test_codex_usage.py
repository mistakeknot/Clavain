"""Scoped Codex accounting uses pool-selected accounts, never CLI guesses."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location('codex_usage', ROOT / 'scripts/codex_usage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_cache_is_disjoint_and_reasoning_is_not_added():
    m = load().Meter('gpt-6-astra', 'dispatch', 'invocation', 'session', '')
    m.event(dict(type='thread.started', thread_id='session'))
    m.event(dict(type='turn.started'))
    m.event(dict(type='turn.completed', usage=dict(input_tokens=40, cached_input_tokens=30,
        cache_write_input_tokens=0, output_tokens=9, reasoning_output_tokens=4)))
    assert m.total == dict(input_tokens=10, cache_read_input_tokens=30,
                          cache_creation_input_tokens=0, output_tokens=9)


@pytest.mark.parametrize('usage', [dict(input_tokens=2, cached_input_tokens=3, output_tokens=1),
    dict(input_tokens=True, cached_input_tokens=0, output_tokens=1),
    dict(input_tokens=3, output_tokens=1),
    dict(input_tokens=3, cached_input_tokens=0, output_tokens=1, new_tokens=5)])
def test_unknown_or_invalid_usage_fails_closed(usage):
    m = load().Meter('gpt-6-astra', 'dispatch', 'invocation', 'session', '')
    m.event(dict(type='thread.started', thread_id='session'))
    m.event(dict(type='turn.started'))
    with pytest.raises(ValueError):
        m.event(dict(type='turn.completed', usage=usage))


@pytest.mark.requires_ic
@pytest.mark.parametrize('mode', ['success', 'refused', 'missing-account', 'wrong-totals',
    'wrong-model', 'wrong-provider', 'unknown-hop', 'provider-fail', 'truncated', 'budget'])
def test_dispatch_scoped_codex_receipt(tmp_path, mode):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(dict(threadId='fixture-thread', availability=dict(codex=True, claude=True))).encode())
        def do_POST(self):
            action = self.path.rsplit('/', 1)[-1]
            calls.append(action)
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.headers['x-bb-account-pool-token'] == 'synthetic-host-token'
            self.send_response(503 if mode == 'refused' else 200); self.end_headers()
            if mode == 'refused': return
            data = dict(version=1, id='a'*32, host_id='fixture-host',
                        attempt_id=payload['attempt_id'], provider='codex')
            if action == 'begin':
                assert payload['provider'] == 'codex'
                data.update(token='synthetic-scoped-token', expires_at=9999999999999)
            else:
                hop = dict(index=1, account_id='fixture-account', provider='codex', status=200,
                    state='complete', model='gpt-6-astra', usage=dict(input_tokens=10,
                    output_tokens=9, cache_read_input_tokens=30, cache_creation_input_tokens=0))
                if mode == 'missing-account': hop['account_id'] = None
                if mode == 'wrong-totals': hop['usage']['input_tokens'] += 1
                if mode == 'wrong-model': hop['model'] = 'gpt-6.2-sol'
                if mode == 'unknown-hop': hop.update(state='unknown', usage=None)
                if mode == 'wrong-provider': hop['provider'] = 'claude'
                data.update(sealed=True, valid=True, complete=True, requests=[dict(
                    id=1, kind='inference', state='finished', hops=[hop])])
            self.wfile.write(json.dumps(data).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    child = bin_dir / 'codex'
    child.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '--version' in sys.argv: print('codex-cli 0.167.0'); sys.exit(0)
assert os.environ['CODEX_POOL_AUTH_TOKEN'] == 'synthetic-scoped-token'
assert 'synthetic-host-token' not in os.environ.values()
Path(os.environ['CALLS']).write_text('called')
out = sys.argv[sys.argv.index('-o')+1]
Path(out).write_text('VERDICT: PASS\\n')
print(json.dumps(dict(type='thread.started', thread_id='fixture-session')))
print(json.dumps(dict(type='turn.started')))
if os.environ['MODE'] != 'truncated':
    print(json.dumps(dict(type='turn.completed', usage=dict(input_tokens=40,
        cached_input_tokens=30, output_tokens=9, reasoning_output_tokens=4))))
sys.exit(7 if os.environ['MODE'] == 'provider-fail' else 0)
''')
    child.chmod(0o755)
    host = json.loads((ROOT/'config/bb-integration.json').read_text())['allowed_host_ids'][0]
    bb = bin_dir/'bb'
    bb.write_text('#!/usr/bin/env python3\nimport json\nprint(' + repr(json.dumps(dict(
        thread=dict(id='fixture-thread', environment=dict(hostId=host))))) + ')\n')
    bb.chmod(0o755)
    origin = 'http://127.0.0.1:' + str(server.server_port)
    env = {**os.environ, 'PATH': str(bin_dir)+os.pathsep+os.environ['PATH'],
        'BB_CLI': str(bb), 'BB_SERVER_URL': origin, 'BB_THREAD_ID': 'fixture-thread',
        'CODEX_POOL_AUTH_TOKEN': 'synthetic-host-token', 'CLAVAIN_BB_DIRECT_POOL': '1',
        'CODEX_OPENAI_BASE_URL': origin + '/api/v1/plugins/account-pool/http/v1',
        'ANTHROPIC_AUTH_TOKEN': '', 'MODE': mode, 'CALLS': str(tmp_path/'calls'),
        'CLAVAIN_REQUIRE_USAGE': '1', 'CLAVAIN_REVIEW_EVENTS': str(tmp_path/'events.jsonl'),
        'CLAVAIN_TOKEN_BUDGET': '1' if mode == 'budget' else '10000',
        'CLAVAIN_DISPATCH_ID': 'fixture-dispatch', 'CLAVAIN_CONTEXT_GATEWAY_MODE': 'off'}
    try:
        proc = subprocess.run(['bash', str(ROOT/'scripts/dispatch.sh'), '--to', 'codex',
            '--model', 'gpt-6-astra', '-s', 'read-only', '-C', str(tmp_path),
            '-o', str(tmp_path/'review.md'), 'Review fixture only'],
            env=env, capture_output=True, text=True, timeout=30)
    finally:
        server.shutdown(); server.server_close(); thread.join()
    if mode == 'refused':
        assert proc.returncode != 0
        assert calls == ['begin']
        assert not (tmp_path/'calls').exists()
        return
    assert calls == ['begin', 'finalize'], proc.stderr
    ledger, = tmp_path.glob('events.jsonl.*.pool-usage.jsonl')
    final = json.loads(ledger.read_text().splitlines()[-1])
    if mode == 'success':
        assert proc.returncode == 0, proc.stderr
        assert final['status'] == 'success' and final['complete']
        assert final['model_identity'] == final['requested_identity'] == 'gpt-6-astra'
        assert final['budget_tokens'] == 49
        evidence = Path(final['pool_receipt']['path'])
        assert evidence.stat().st_mode & 0o777 == 0o600
        assert json.loads(evidence.read_text())['requests'][0]['hops'][0]['account_id'] == 'fixture-account'
        assert 'synthetic-host-token' not in evidence.read_text()
        assert 'synthetic-scoped-token' not in evidence.read_text()
        from pool_receipt import check_ledger
        check_ledger(ledger, final['pool_receipt']['attempt_id'], 'codex')
        evidence.write_text('{}')
        with pytest.raises(ValueError):
            check_ledger(ledger, final['pool_receipt']['attempt_id'], 'codex')
    else:
        assert proc.returncode != 0, proc.stderr
        assert final['status'] != 'success'
