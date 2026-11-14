"""Run the real probe with deterministic dummy transport responses."""
import io
import json
import os
from pathlib import Path
import runpy
import socket
import ssl
import sys
from unittest.mock import patch
from urllib.error import HTTPError, URLError

probe, provider = sys.argv[1:]
counter = Path(os.environ['PROBE_COUNT'])
attempt = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(attempt))
scenario = os.environ.get('PROBE_SCENARIO', 'success')
if scenario == 'missing-token':
    os.environ.pop('ANTHROPIC_AUTH_TOKEN', None)
    os.environ.pop('CODEX_POOL_AUTH_TOKEN', None)


class Opener:
    def open(self, request, timeout):
        assert timeout == 5
        if scenario == 'timeout' or (scenario == 'recover' and attempt < 3):
            raise TimeoutError('dummy timeout')
        if scenario == 'transport':
            raise URLError(ConnectionResetError('dummy reset'))
        if scenario == 'refused':
            raise ConnectionRefusedError('dummy refusal')
        if scenario == 'wrapped-timeout':
            raise URLError(TimeoutError('dummy timeout'))
        errors = {
            'tls-cert': URLError(ssl.SSLCertVerificationError('dummy certificate')),
            'tls': URLError(ssl.SSLError('dummy TLS')),
            'dns': URLError(socket.gaierror(socket.EAI_NONAME, 'dummy DNS')),
            'nested-tls': URLError(URLError(ssl.SSLError('dummy TLS'))),
            'nested-dns': URLError(URLError(socket.gaierror(socket.EAI_NONAME, 'dummy DNS'))),
            'direct-tls': ssl.SSLError('dummy TLS'),
            'direct-dns': socket.gaierror(socket.EAI_NONAME, 'dummy DNS'),
        }
        if scenario in errors:
            raise errors[scenario]
        if scenario.startswith('http'):
            raise HTTPError(request.full_url, int(scenario[4:]), 'dummy', {}, None)
        if scenario == 'malformed':
            return io.StringIO('{')
        return io.StringIO(json.dumps({
            'threadId': 'fixture',
            'availability': {'claude': scenario != 'ineligible', 'codex': scenario != 'ineligible'},
        }))


sys.argv = [probe, provider]
with patch('urllib.request.build_opener', return_value=Opener()):
    runpy.run_path(probe, run_name='__main__')
