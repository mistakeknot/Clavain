"""Direct dispatch integration: stdin, workspace admission and provider errors."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest

ROOT = Path(__file__).resolve().parents[2]


def pool_server(response=None, status=200, delay=0):
    body = response or json.dumps({
        'threadId': 'thr_fixture',
        'availability': {'claude': True, 'codex': True},
    })

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if delay:
                time.sleep(delay)
            allowed = False
            if not self.path.startswith('/api/v1/plugins/account-pool/http/availability?threadId='):
                self.send_response(404)
            elif not self.headers.get('x-bb-account-pool-token'):
                self.send_response(401)
            else:
                self.send_response(status)
                if status == 302:
                    self.send_header('Location', 'https://untrusted.example/steal')
                else:
                    self.send_header('Content-Type', 'application/json')
                    allowed = True
            try:
                self.end_headers()
            except BrokenPipeError:
                return
            if allowed:
                try:
                    self.wfile.write(body.encode())
                except BrokenPipeError:
                    pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f'http://127.0.0.1:{server.server_port}'


def run_dispatch(tmp_path, events=(), *, git=True, sandbox="workspace-write", stderr="", exit_code=0, budget=False, pool=False, block_intercept=False, env_override=None, engine="codex"):
    server = None
    pool_origin = 'https://bb.example'
    if pool:
        server, pool_origin = pool_server(
            response=(env_override or {}).get('BB_ELIGIBILITY_RESPONSE'),
            status=int((env_override or {}).get('BB_ELIGIBILITY_STATUS') or (401 if (env_override or {}).get('BB_ELIGIBILITY_EXIT') else 200)),
            delay=int((env_override or {}).get('BB_ELIGIBILITY_DELAY') or 0),
        )
        (tmp_path/'pool-origin').write_text(pool_origin)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    if git:
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        if engine == "claude":
            subprocess.run(["git", "-C", str(work), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                            "commit", "-q", "--allow-empty", "-m", "fixture"], check=True)
    if block_intercept:
        (work / ".clavain").mkdir()
        (work / ".clavain" / "intercept").write_text("not a directory")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "codex"
    stub.write_text("""#!/usr/bin/env python3
import hashlib, json, os, sys
from pathlib import Path
if '--version' in sys.argv: print('codex-cli 0.153.3'); sys.exit(0)
sys.stdin.read()
Path(os.environ['CALL']).write_text(json.dumps(sys.argv))
token = os.environ.get('CODEX_POOL_AUTH_TOKEN', '')
Path(os.environ['CALL']+'.pooltoken').write_text(hashlib.sha256(token.encode()).hexdigest() if token else '')
if '-o' in sys.argv: Path(sys.argv[sys.argv.index('-o')+1]).write_text('VERDICT: CLEAN')
for event in json.loads(os.environ['EVENTS']): print(json.dumps(event))
print(os.environ['STDERR'], file=sys.stderr)
sys.exit(int(os.environ['EXIT_CODE']))
""")
    stub.chmod(0o755)
    claude = bin_dir / "claude"
    claude.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
sys.stdin.read()
Path(os.environ['CALL']).write_text(json.dumps({
    'argv': sys.argv,
    'base_url': os.environ.get('ANTHROPIC_BASE_URL'),
    'token_matches': os.environ.get('ANTHROPIC_AUTH_TOKEN') == os.environ.get('POOL_TOKEN_SENTINEL'),
    'tool_search': os.environ.get('ENABLE_TOOL_SEARCH'),
}))
print(json.dumps({'type':'result','is_error':False,'result':'VERDICT: CLEAN'}))
""")
    claude.chmod(0o755)
    bb = bin_dir/'bb'
    bb.write_text("""#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:] == ['status', '--json']:
    print(json.dumps({'thread': {'id': 'thr_fixture', 'environment': {'hostId': 'host_pda34naxgq'}}}))
else:
    sys.exit(1)
""")
    bb.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir)+":"+os.environ["PATH"], CALL=str(tmp_path/"call"),
               EVENTS=json.dumps(events), STDERR=stderr, EXIT_CODE=str(exit_code), CLAVAIN_CONTEXT_GATEWAY_MODE="off",
               CLAVAIN_DISPATCH_FAILURE_FILE=str(tmp_path/"failure"),
               CLAVAIN_BB_DIRECT_POOL="1" if pool else "0", BB_CLI=str(bb), BB_THREAD_ID='thr_fixture',
               BB_SERVER_URL=pool_origin, CODEX_POOL_AUTH_TOKEN='fixture-only',
               CODEX_OPENAI_BASE_URL=pool_origin+'/api/v1/plugins/account-pool/http/v1',
               POOL_TOKEN_SENTINEL='fixture-only',
               CLAVAIN_REQUIRE_USAGE="1" if budget else "0", CLAVAIN_REVIEW_EVENTS=str(tmp_path/"events"))
    for key, value in (env_override or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value.replace('https://bb.example', pool_origin) if pool else value
    # Keep stdin open deliberately: communicate() would close it and mask the bug.
    p = subprocess.Popen(["bash", str(ROOT/"scripts/dispatch.sh"), "--to", engine, "-s", sandbox, "-C", str(work),
                          "-o", str(tmp_path/"out"), "fixture"], env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return p.wait(timeout=8 if (env_override or {}).get('BB_ELIGIBILITY_DELAY') else 5)
    finally:
        p.kill()
        p.wait()
        p.stdin.close()
        if server is not None:
            server.shutdown()
            server.server_close()


def test_codex_stdin_is_closed(tmp_path):
    assert run_dispatch(tmp_path) == 0


def test_read_only_non_git_gets_skip_flag(tmp_path):
    assert run_dispatch(tmp_path, git=False, sandbox="read-only") == 0
    assert "--skip-git-repo-check" in json.loads((tmp_path/"call").read_text())


def test_write_non_git_refused_before_provider(tmp_path):
    assert run_dispatch(tmp_path, git=False) != 0
    assert not (tmp_path/"call").exists()


def test_structured_quota_exit_zero(tmp_path):
    event = {"type":"event_msg", "payload":{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}}}
    assert run_dispatch(tmp_path, [event]) != 0
    assert (tmp_path/"failure").read_text().strip() == "quota_exhausted"


def test_quoted_quota_is_not_provider_failure(tmp_path):
    event = {"type":"item.completed", "item":{"type":"agent_message", "text":"ERROR: You've hit your usage limit. Quoted task text."}}
    assert run_dispatch(tmp_path, [event]) == 0


def test_stderr_only_usage_limit_is_provider_failure(tmp_path):
    assert run_dispatch(tmp_path, stderr="ERROR: You've hit your usage limit.", exit_code=7) != 0
    assert (tmp_path / "failure").read_text().strip() == "quota_exhausted"


def test_failed_dispatch_persists_redacted_intercept_evidence(tmp_path):
    event = {
        "type": "turn.failed",
        "request_id": "req-fixture",
        "error": {
            "code": "unknown_failure",
            "provider_reason": "seat_exhausted",
            "provider_token": "tok-provider-fixture-secret",
        },
    }
    stderr = "Authorization: Bearer bearer-fixture-secret\ncontact dev@example.test\n"

    assert run_dispatch(tmp_path, [event], stderr=stderr) != 0

    artifacts = list((tmp_path / "work" / ".clavain" / "intercept").glob("*.json"))
    assert len(artifacts) == 1
    raw = artifacts[0].read_text()
    assert "bearer-fixture-secret" not in raw
    assert "tok-provider-fixture-secret" not in raw
    assert "dev@example.test" not in raw
    evidence = json.loads(raw)
    assert evidence["unmapped_provider_fields"] == [
        {
            "event_type": "turn.failed",
            "fields": {
                "request_id": "<id>",
                "error": {
                    "code": "unknown_failure",
                    "provider_reason": "seat_exhausted",
                    "provider_token": "<redacted>",
                },
            },
        }
    ]
    assert (tmp_path / "work" / ".clavain" / "intercept" / ".gitignore").read_text() == "*\n"
    status = subprocess.run(
        ["git", "-C", str(tmp_path / "work"), "status", "--porcelain", "--", ".clavain/intercept"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert status.stdout == ""


def test_evidence_write_failure_preserves_provider_class(tmp_path):
    event = {
        "type": "task_complete",
        "error": {"codex_error_info": "usage_limit_exceeded"},
    }

    assert run_dispatch(tmp_path, [event], block_intercept=True) != 0
    assert (tmp_path / "failure").read_text().strip() == "quota_exhausted"


def test_denial_dominates_quota(tmp_path):
    events = [{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}},
              {"type":"error", "error":{"code":"permission_denied"}}]
    assert run_dispatch(tmp_path, events) != 0
    assert (tmp_path/"failure").read_text().strip() == "terminal_policy"


def test_recovered_codex_error_is_not_terminal(tmp_path):
    events = [{"type":"error", "message":"Transient stream error; reconnecting"},
              {"type":"turn.completed", "usage":{"input_tokens":10,"output_tokens":2}}]
    assert run_dispatch(tmp_path, events) == 0


@pytest.mark.parametrize('code,expected',[
    ('permission_denied','terminal_policy'),
    ('authentication_error','terminal_configuration'),
    ('usage_limit_exceeded','quota_exhausted'),
])
def test_coded_error_is_sticky_after_success(tmp_path,code,expected):
    events=[{'type':'error','error':{'code':code}}, {'type':'turn.completed'}]
    assert run_dispatch(tmp_path,events)!=0
    assert (tmp_path/'failure').read_text().strip()==expected


def test_error_after_success_remains_terminal(tmp_path):
    events = [{"type":"turn.completed"}, {"type":"error", "message":"Stream failed"}]
    assert run_dispatch(tmp_path, events) != 0


def test_success_does_not_erase_failed_turn(tmp_path):
    events = [{"type":"turn.failed", "error":{"code":"permission_denied"}},
              {"type":"turn.completed"}]
    assert run_dispatch(tmp_path, events) != 0
    assert (tmp_path/"failure").read_text().strip() == 'terminal_policy'


def test_budget_error_remains_terminal_accounting(tmp_path):
    assert run_dispatch(tmp_path, [{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}}], budget=True) != 0
    assert (tmp_path/"failure").read_text().strip() == "terminal_accounting"


def test_stderr_denial_dominates_quota(tmp_path):
    assert run_dispatch(tmp_path, [{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}}],
                        stderr="HTTP 403 Forbidden: policy denied") != 0
    assert (tmp_path/"failure").read_text().strip() == "terminal_policy"


def test_real_rollout_quota_fixture(tmp_path):
    event = json.loads((ROOT / "tests/fixtures/codex-usage-limit-rollout.jsonl").read_text())
    assert run_dispatch(tmp_path, [event]) != 0
    assert (tmp_path/"failure").read_text().strip() == "quota_exhausted"


def test_real_stdout_quota_fixture(tmp_path):
    events=[json.loads(line) for line in (ROOT/'tests/fixtures/codex-usage-limit-stdout.jsonl').read_text().splitlines()]
    assert run_dispatch(tmp_path, events) != 0
    assert (tmp_path/'failure').read_text().strip() == 'quota_exhausted'


def test_pooled_unknown_account_blocks_budget_acceptance(tmp_path):
    assert run_dispatch(tmp_path, pool=True, budget=True) != 0
    assert (tmp_path/'failure').read_text().strip() == 'terminal_accounting'


def test_claude_structured_quota_and_response(tmp_path):
    stub = tmp_path / "claude"
    stub.write_text("#!/usr/bin/env python3\nimport os,sys\nsys.stdin.read()\nprint(os.environ['EVENT'])\n")
    stub.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path)+":"+os.environ["PATH"], CLAVAIN_CONTEXT_GATEWAY_MODE="off", CLAVAIN_BB_DIRECT_POOL="0",
               CLAVAIN_DISPATCH_FAILURE_FILE=str(tmp_path/"failure"))
    command = ["bash", str(ROOT/"scripts/dispatch.sh"), "--to", "claude", "-C", str(tmp_path), "-o", str(tmp_path/"out"), "fixture"]
    for event, expected in [({"type":"result", "is_error":False,"result":"VERDICT: CLEAN"}, 0),
                            ({"type":"assistant", "error":"usage_limit_exceeded"}, 1)]:
        p = subprocess.run(command, env=env | {"EVENT":json.dumps(event)}, capture_output=True, timeout=10)
        assert p.returncode == expected, p.stderr
        if not expected:
            assert "VERDICT: CLEAN" in (tmp_path/"out").read_text()
        else:
            assert (tmp_path/"failure").read_text().strip() == "quota_exhausted"


POOL_ROUTE = 'https://bb.example/api/v1/plugins/account-pool/http'


def test_codex_parent_dispatches_claude_through_eligible_pool(tmp_path):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_BASE_URL': None,
    }) == 0
    call = json.loads((tmp_path/'call').read_text())
    assert call['base_url'] == (tmp_path/'pool-origin').read_text()+'/api/v1/plugins/account-pool/http'
    assert call['token_matches'] is True
    assert call['tool_search'] == 'true'


def test_claude_parent_keeps_eligible_inherited_pool(tmp_path):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'CODEX_POOL_AUTH_TOKEN': None, 'ANTHROPIC_AUTH_TOKEN': 'fixture-only',
        'ANTHROPIC_BASE_URL': POOL_ROUTE,
    }) == 0
    call = json.loads((tmp_path/'call').read_text())
    assert call['base_url'] == (tmp_path/'pool-origin').read_text()+'/api/v1/plugins/account-pool/http'
    assert call['token_matches'] is True


@pytest.mark.parametrize('engine', ['claude', 'codex'])
def test_native_pool_remains_usable_with_legacy_bb_availability(tmp_path, engine):
    response = json.dumps({'claude': True, 'codex': True})
    env_override = {'BB_ELIGIBILITY_RESPONSE': response}
    if engine == 'claude':
        env_override.update(ANTHROPIC_AUTH_TOKEN='fixture-only', ANTHROPIC_BASE_URL=POOL_ROUTE)
    assert run_dispatch(tmp_path, pool=True, engine=engine, env_override=env_override) == 0
    if engine == 'claude':
        assert json.loads((tmp_path/'call').read_text())['token_matches'] is True
    else:
        assert 'model_provider="bb-account-pool"' in json.loads((tmp_path/'call').read_text())


def test_disabled_provider_in_legacy_bb_drops_inherited_route(tmp_path):
    response = json.dumps({'claude': False, 'codex': True})
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': 'fixture-only', 'ANTHROPIC_BASE_URL': POOL_ROUTE,
        'BB_ELIGIBILITY_RESPONSE': response,
    }) == 0
    call = json.loads((tmp_path/'call').read_text())
    assert call['base_url'] is None
    assert call['token_matches'] is False


def test_pool_bypass_uses_local_claude_credentials(tmp_path):
    response = json.dumps({'threadId': 'thr_fixture', 'availability': {'claude': False, 'codex': False}})
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': 'fixture-only', 'ANTHROPIC_BASE_URL': POOL_ROUTE,
        'BB_ELIGIBILITY_RESPONSE': response,
    }) == 0
    call = json.loads((tmp_path/'call').read_text())
    assert call['base_url'] is None
    assert call['token_matches'] is False


def test_disabled_codex_pool_uses_local_login(tmp_path):
    response = json.dumps({'threadId': 'thr_fixture', 'availability': {'claude': True, 'codex': False}})
    assert run_dispatch(tmp_path, pool=True, env_override={'BB_ELIGIBILITY_RESPONSE': response}) == 0
    assert 'model_provider="bb-account-pool"' not in json.loads((tmp_path/'call').read_text())
    assert (tmp_path/'call.pooltoken').read_text() == ''


@pytest.mark.parametrize('claude_env', [
    {'ANTHROPIC_AUTH_TOKEN': '', 'ANTHROPIC_BASE_URL': ''},
    {'ANTHROPIC_AUTH_TOKEN': 'fixture-only', 'ANTHROPIC_BASE_URL': 'https://api.anthropic.com'},
])
def test_explicit_claude_environment_is_preserved(tmp_path, claude_env):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override=claude_env) == 0
    call = json.loads((tmp_path/'call').read_text())
    assert call['base_url'] == claude_env['ANTHROPIC_BASE_URL']


@pytest.mark.parametrize('eligibility', [
    {'BB_ELIGIBILITY_EXIT': '1'},
    {'BB_ELIGIBILITY_RESPONSE': '{invalid'},
    {'BB_ELIGIBILITY_RESPONSE': json.dumps({'threadId': 'different', 'availability': {'claude': True, 'codex': True}})},
    {'BB_ELIGIBILITY_RESPONSE': json.dumps({'claude': True, 'codex': True})},
    {'BB_ELIGIBILITY_RESPONSE': '[]'},
    {'BB_ELIGIBILITY_RESPONSE': json.dumps({'threadId': 'thr_fixture', 'availability': {'claude': 'yes', 'codex': True}})},
])
def test_unknown_pool_eligibility_fails_before_claude_login(tmp_path, eligibility):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_BASE_URL': None,
        **eligibility,
    }) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'
    assert not any('fixture-only' in p.read_text(errors='ignore') for p in tmp_path.rglob('*') if p.is_file())


@pytest.mark.parametrize('eligibility', [
    {'BB_ELIGIBILITY_EXIT': '1'},
    {'BB_ELIGIBILITY_RESPONSE': '{invalid'},
    {'BB_ELIGIBILITY_RESPONSE': json.dumps({'threadId': 'thr_fixture', 'availability': {'claude': True, 'codex': 'yes'}})},
])
def test_unknown_pool_eligibility_fails_before_codex_login(tmp_path, eligibility):
    assert run_dispatch(tmp_path, pool=True, env_override=eligibility) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'


def test_old_bb_availability_cannot_authorize_claude_to_codex_borrowing(tmp_path):
    assert run_dispatch(tmp_path, pool=True, env_override={
        'CODEX_POOL_AUTH_TOKEN': None, 'CODEX_OPENAI_BASE_URL': None,
        'ANTHROPIC_AUTH_TOKEN': 'fixture-only', 'ANTHROPIC_BASE_URL': POOL_ROUTE,
        'BB_ELIGIBILITY_RESPONSE': json.dumps({'claude': True, 'codex': True}),
    }) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'


def test_untrusted_bb_origin_fails_before_claude_login(tmp_path):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_BASE_URL': None,
        'BB_SERVER_URL': 'https://user@bb.example',
        'CODEX_OPENAI_BASE_URL': 'https://user@bb.example/api/v1/plugins/account-pool/http/v1',
    }) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'


def test_unverified_bb_enrollment_fails_before_claude_login(tmp_path):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_BASE_URL': None,
        'BB_THREAD_ID': 'thr_unverified',
    }) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'


def test_pool_eligibility_timeout_fails_before_claude_login(tmp_path):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_BASE_URL': None,
        'BB_ELIGIBILITY_DELAY': '6',
    }) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'


def test_pool_redirect_is_not_followed(tmp_path):
    assert run_dispatch(tmp_path, pool=True, engine='claude', env_override={
        'ANTHROPIC_AUTH_TOKEN': None, 'ANTHROPIC_BASE_URL': None,
        'BB_ELIGIBILITY_STATUS': '302',
    }) != 0
    assert not (tmp_path/'call').exists()
    assert (tmp_path/'failure').read_text().strip() == 'terminal_configuration'


def test_claude_thread_borrows_machine_pool_token_for_codex(tmp_path):
    # A Claude Code BB thread gets no CODEX_POOL_AUTH_TOKEN; the Codex seat must
    # still go through the pool, not the local ~/.codex login.
    assert run_dispatch(tmp_path, pool=True, env_override={
        'CODEX_POOL_AUTH_TOKEN': None, 'CODEX_OPENAI_BASE_URL': None,
        'ANTHROPIC_AUTH_TOKEN': 'machine-fixture', 'ANTHROPIC_BASE_URL': POOL_ROUTE}) == 0
    argv = json.loads((tmp_path/'call').read_text())
    assert 'model_provider="bb-account-pool"' in argv
    assert (tmp_path/'call.pooltoken').read_text() == hashlib.sha256(b'machine-fixture').hexdigest()


def test_codex_stays_direct_without_any_pool_token(tmp_path):
    assert run_dispatch(tmp_path, pool=True, env_override={
        'CODEX_POOL_AUTH_TOKEN': None, 'ANTHROPIC_AUTH_TOKEN': 'machine-fixture',
        'ANTHROPIC_BASE_URL': 'https://api.anthropic.com'}) == 0
    assert 'model_provider="bb-account-pool"' not in json.loads((tmp_path/'call').read_text())
    assert (tmp_path/'call.pooltoken').read_text() == ''


@pytest.mark.parametrize('codex_env', [
    {'CODEX_POOL_AUTH_TOKEN': '', 'CODEX_OPENAI_BASE_URL': ''},
    {'CODEX_POOL_AUTH_TOKEN': None, 'CODEX_OPENAI_BASE_URL': 'https://other.example/v1'},
])
def test_claude_parent_preserves_explicit_codex_environment(tmp_path, codex_env):
    assert run_dispatch(tmp_path, pool=True, env_override={
        'ANTHROPIC_AUTH_TOKEN': 'fixture-only', 'ANTHROPIC_BASE_URL': POOL_ROUTE,
        **codex_env,
    }) == 0
    assert 'model_provider="bb-account-pool"' not in json.loads((tmp_path/'call').read_text())


def test_codex_thread_token_wins_over_claude_route(tmp_path):
    assert run_dispatch(tmp_path, pool=True, env_override={
        'CODEX_POOL_AUTH_TOKEN': 'codex-fixture', 'ANTHROPIC_AUTH_TOKEN': 'machine-fixture', 'ANTHROPIC_BASE_URL': POOL_ROUTE}) == 0
    assert (tmp_path/'call.pooltoken').read_text() == hashlib.sha256(b'codex-fixture').hexdigest()


def _lib_bb_probe(tmp_path, env_extra):
    """Source lib-bb.sh, run the availability check, report what leaked."""
    server, pool_origin = pool_server()
    bb = tmp_path / 'bb'
    bb.write_text("""#!/usr/bin/env python3
import json, sys
if sys.argv[1:] == ['status', '--json']:
    print(json.dumps({'thread': {'id': 'thr_fixture', 'environment': {'hostId': 'host_pda34naxgq'}}}))
else:
    sys.exit(1)
""")
    bb.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ('CODEX_POOL_AUTH_TOKEN', 'CODEX_OPENAI_BASE_URL', 'CLAVAIN_BB_DIRECT_POOL')}
    env.update(BB_CLI=str(bb), BB_THREAD_ID='thr_fixture', BB_SERVER_URL=pool_origin,
               ANTHROPIC_AUTH_TOKEN='machine-fixture', ANTHROPIC_BASE_URL=pool_origin+'/api/v1/plugins/account-pool/http')
    env.update(env_extra)
    script = (f'source {ROOT}/scripts/lib-bb.sh; '
              'if _bb_pool_available codex; then a=1; else a=0; fi; '
              'printf "%s:%s" "$a" "${CODEX_POOL_AUTH_TOKEN:-}"')
    try:
        return subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True, timeout=20).stdout
    finally:
        server.shutdown()
        server.server_close()


def test_pool_availability_check_exports_nothing(tmp_path):
    # The retry loop calls the check from the parent role shell; an export there
    # would reach later Claude/Kimi/BB candidates.
    assert _lib_bb_probe(tmp_path, {}) == '1:'


def test_failed_enrollment_is_not_pooled(tmp_path):
    assert _lib_bb_probe(tmp_path, {'BB_THREAD_ID': 'thr_someone_else'}) == '0:'


def test_direct_pool_kill_switch_disables_borrowing(tmp_path):
    assert _lib_bb_probe(tmp_path, {'CLAVAIN_BB_DIRECT_POOL': '0'}) == '0:'
    assert run_dispatch(tmp_path, pool=False, env_override={
        'CODEX_POOL_AUTH_TOKEN': None, 'ANTHROPIC_AUTH_TOKEN': 'machine-fixture', 'ANTHROPIC_BASE_URL': POOL_ROUTE}) == 0
    assert 'model_provider="bb-account-pool"' not in json.loads((tmp_path/'call').read_text())
    assert (tmp_path/'call.pooltoken').read_text() == ''


def test_borrowed_token_is_not_persisted_by_dispatch(tmp_path):
    secret = 'borrowed-secret-fixture-7f3a'
    assert run_dispatch(tmp_path, pool=True, env_override={
        'CODEX_POOL_AUTH_TOKEN': None, 'CODEX_OPENAI_BASE_URL': None,
        'ANTHROPIC_AUTH_TOKEN': secret, 'ANTHROPIC_BASE_URL': POOL_ROUTE}) == 0
    leaked = [p for p in tmp_path.rglob('*') if p.is_file()
              and secret in p.read_text(errors='ignore')]
    assert leaked == []
