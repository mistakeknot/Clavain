import json
from pathlib import Path

from clavain_selector import learned_router_shadow as shadow


def test_observe_heuristic(tmp_path, monkeypatch):
    from clavain_selector.decide import decide
    policy = tmp_path / 'routing.yaml'
    policy.write_text('decision_models:\n  learned_router: {mode: shadow, backend: heuristic}\n')
    def run(cmd, **kwargs):
        request = json.loads(kwargs['input'])
        assert request['egress_allowed'] is False
        assert 'secret task' not in kwargs['input']
        answer = decide(request, dict(mode='shadow', backend='heuristic'), tmp_path)
        return type('Result', (), {'stdout': json.dumps(answer)})()
    monkeypatch.setattr(shadow.subprocess, 'run', run)
    route = {'profile_ref': 'opus', 'profile': {'backend': 'claude', 'model': 'claude-opus-5-5'},
             'fallback_chain': [{'profile_ref': 'sol', 'profile': {'backend': 'codex', 'model': 'gpt-6.1-sol'}}]}
    shadow.observe(Path(__file__).resolve().parents[2], policy, tmp_path,
                   dict(route=route, native=route['profile_ref'], role='routine-execution',
                        prompt_chars=401, exit_code=0))
    rows = [json.loads(line) for p in (tmp_path / '.clavain/decisions').glob('*.jsonl') for line in p.read_text().splitlines()]
    row = next(r for r in rows if r['schema'] == 'clavain-learned-router-v1')
    assert row['agreement'] is True
    assert row['estimated_claude_tokens_saved'] == 0
    assert row['estimated_input_tokens'] == 101
    assert row['confidence'] == 1
    assert row['exit_code'] == 0
    assert 'opus' not in json.dumps(row)


def test_off_enforce_and_jev_inert(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('called decide')
    monkeypatch.setattr(shadow.subprocess, 'run', forbidden)
    policy = tmp_path / 'routing.yaml'
    for mode, backend in [('off', 'heuristic'), ('enforce', 'heuristic'), ('shadow', 'jev')]:
        policy.write_text(f'decision_models:\n  learned_router: {{mode: {mode}, backend: {backend}}}\n')
        shadow.observe(tmp_path, policy, tmp_path, {})
    assert not (tmp_path / '.clavain').exists()


def test_detached_dispatch_hook_preserves_status(tmp_path):
    import subprocess
    import time
    root = Path(__file__).resolve().parents[2]
    script = (root / 'scripts/dispatch.sh').read_text()
    hook = script.split('  DISPATCH_FINAL_RC="$_rc"', 1)[1].split('  if [[ "${CLAVAIN_HELD_SNAPSHOT_OWNER', 1)[0]
    # A deliberately slow Python worker must not hold stdout or the caller.
    worker = tmp_path / 'python3'
    worker.write_text('#!/bin/sh\nsleep 2\n')
    worker.chmod(0o755)
    import os
    env = dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}')
    start = time.monotonic()
    result = subprocess.run(['bash', '-c', '''
RUN_RECEIPT_ARMED=true; ROLE_RESOLVED=true; RESOLVED_ROUTE_JSON='{}'
RESOLVED_PROFILE_REF=seat; ROLE=scout; _rc=7; PROMPT='private task'
DISPATCH_SCRIPT_DIR=/irrelevant
''' + hook + '\nexit "$_rc"'], env=env, capture_output=True, timeout=1)
    assert result.returncode == 7
    assert result.stdout == result.stderr == b''
    assert time.monotonic() - start < 1
