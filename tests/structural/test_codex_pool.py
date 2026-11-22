"""Run the packaged dispatcher against a synthetic authenticated pool service."""
import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("source", ["native", "borrowed"])
@pytest.mark.parametrize("mode", ["success", "refused", "missing-account", "wrong-totals",
                                  "wrong-provider", "wrong-model", "unknown-hop", "provider-fail",
                                  "truncated", "missing-cache", "budget"])
def test_budgeted_codex_pool(tmp_path, mode, source):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(dict(threadId="fixture-thread", availability=dict(codex=True))).encode())
        def do_POST(self):
            action = self.path.rsplit("/", 1)[-1]
            calls.append(action)
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert payload['attempt_id']
            assert self.headers['x-bb-account-pool-token'] == 'synthetic-host-token'
            self.send_response(503 if mode == 'refused' else 200); self.end_headers()
            if mode == 'refused': return
            data = dict(version=1, id='a'*32, host_id='fixture-host', attempt_id=payload['attempt_id'], provider='codex')
            if action == 'begin':
                assert payload['provider'] == 'codex'
                data.update(token='synthetic-scoped-token', expires_at=9999999999999)
            else:
                hop = dict(index=1, account_id='fixture-account', provider='codex', status=200,
                           state='complete', model='gpt-6-astra', usage=dict(input_tokens=10,
                           output_tokens=9, cache_read_input_tokens=30, cache_creation_input_tokens=0))
                if mode == 'missing-account': hop['account_id'] = None
                if mode == 'wrong-totals': hop['usage']['input_tokens'] = 11
                if mode == 'wrong-provider': hop['provider'] = 'claude'
                if mode == 'wrong-model': hop['model'] = 'gpt-6.1-sol'
                if mode == 'unknown-hop': hop['state'] = 'unknown'
                data.update(sealed=True, valid=True, complete=True, requests=[dict(
                    id=1, kind='inference', state='finished', hops=[hop])])
            self.wfile.write(json.dumps(data).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    codex = bin_dir / 'codex'
    codex.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '--version' in sys.argv:
    print('codex-cli 0.167.0'); sys.exit(0)
assert os.environ['CODEX_POOL_AUTH_TOKEN'] == 'synthetic-scoped-token'
assert 'synthetic-host-token' not in os.environ.values()
Path('called').write_text('yes')
print(json.dumps(dict(type='thread.started', thread_id='fixture-session')), flush=True)
print(json.dumps(dict(type='turn.started')), flush=True)
usage = dict(input_tokens=40, cached_input_tokens=30, output_tokens=9)
if os.environ['MODE'] == 'missing-cache': del usage['cached_input_tokens']
if os.environ['MODE'] == 'truncated':
    print('{', end='', flush=True); sys.exit(0)
print(json.dumps(dict(type='turn.completed', usage=usage)), flush=True)
if '-o' in sys.argv: Path(sys.argv[sys.argv.index('-o')+1]).write_text('PASS')
sys.exit(7 if os.environ['MODE'] == 'provider-fail' else 0)
''')
    codex.chmod(0o755)
    host = json.loads((ROOT/'config/bb-integration.json').read_text())['allowed_host_ids'][0]
    bb = bin_dir / 'bb'
    bb.write_text('#!/usr/bin/env python3\nimport json\nprint(' + repr(json.dumps(dict(thread=dict(id='fixture-thread', environment=dict(hostId=host))))) + ')\n')
    bb.chmod(0o755)
    ledger = tmp_path / 'events.jsonl'
    env = {**os.environ, 'PATH': str(bin_dir)+os.pathsep+os.environ['PATH'], 'BB_CLI': str(bb),
           'BB_SERVER_URL': 'http://127.0.0.1:'+str(server.server_port), 'BB_THREAD_ID': 'fixture-thread',
           'CODEX_POOL_AUTH_TOKEN': 'synthetic-host-token', 'CLAVAIN_BB_DIRECT_POOL': '1',
           'CODEX_OPENAI_BASE_URL': 'http://127.0.0.1:'+str(server.server_port)+'/api/v1/plugins/account-pool/http/v1',
           'CLAVAIN_REQUIRE_USAGE': '1', 'CLAVAIN_REVIEW_EVENTS': str(ledger),
           'CLAVAIN_TOKEN_BUDGET': '1' if mode == 'budget' else '10000',
           'CLAVAIN_CONTEXT_GATEWAY_MODE': 'off', 'MODE': mode}
    if source == 'borrowed':
        env.pop('CODEX_POOL_AUTH_TOKEN', None)
        env.pop('CODEX_OPENAI_BASE_URL', None)
        env.update(ANTHROPIC_AUTH_TOKEN='synthetic-host-token',
                   ANTHROPIC_BASE_URL=env['BB_SERVER_URL']+'/api/v1/plugins/account-pool/http')
    try:
        proc = subprocess.run(['bash', str(ROOT/'scripts/dispatch.sh'), '--to', 'codex',
            '--model', 'gpt-6-astra', '-s', 'read-only', '-C', str(tmp_path), '-o', str(tmp_path/'review.md'),
            'Review this fixture only'], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    finally:
        server.shutdown(); server.server_close(); thread.join()
    if mode == 'success':
        assert proc.returncode == 0, proc.stderr
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        record = next(row for row in rows if row.get('type') == 'pool.accounting')
        assert record['input_tokens'] == 10
        assert record['cache_read_input_tokens'] == 30
        assert record['status'] == 'success'
        evidence = Path(record['pool_receipt']['path'])
        assert evidence.stat().st_mode & 0o777 == 0o600
        assert 'synthetic-host-token' not in evidence.read_text()
        assert 'synthetic-scoped-token' not in evidence.read_text()
    else:
        assert proc.returncode != 0, proc.stderr
    if mode == 'refused':
        assert calls == ['begin']
        assert not (tmp_path/'called').exists()
    else:
        assert calls == ['begin', 'finalize']
