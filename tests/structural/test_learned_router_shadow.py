import json
from pathlib import Path
import pytest

from clavain_selector import learned_router_shadow as shadow


@pytest.mark.parametrize('linked', [False, True])
def test_observe_heuristic(tmp_path, monkeypatch, linked):
    from clavain_selector.decide import decide
    policy = tmp_path / 'routing.yaml'
    policy.write_text('decision_models:\n  learned_router: {mode: shadow, backend: heuristic}\n')
    def run(cmd, **kwargs):
        request = json.loads(kwargs['input'])
        assert request['egress_allowed'] is False
        answer = decide(request, dict(mode='shadow', backend='heuristic'), tmp_path)
        return type('Result', (), {'stdout': json.dumps(answer)})()
    monkeypatch.setattr(shadow.subprocess, 'run', run)
    route = {'profile_ref': 'opus', 'profile': {'backend': 'claude', 'model': 'claude-opus-5-5'},
             'fallback_chain': [{'profile_ref': 'sol', 'profile': {'backend': 'codex', 'model': 'gpt-6.1-sol'}}]}
    project = tmp_path
    if linked:
        project = tmp_path / 'alias'
        project.symlink_to(tmp_path, target_is_directory=True)
    shadow.observe(Path(__file__).resolve().parents[2], policy, project,
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
    monkeypatch.setenv('CLAVAIN_SELECTOR', ' OFF ')
    # Even an unreadable policy is untouched under the global kill switch.
    shadow.observe(tmp_path, tmp_path / 'missing', tmp_path, {})


@pytest.mark.parametrize('model,expected,reason,agreement', [
    ('claude-sonnet-5-5', 0, 'shadow_mode', False),
    ('claude-opus-5-5', 0, 'shadow_mode', False),
    ('claude-haiku-4-5', 101, 'shadow_mode', False),
    ('claude-opus-5-5', 0, 'invalid_input', None),
])
def test_disagreeing_choice_savings(tmp_path, monkeypatch, model, expected, reason, agreement):
    policy = tmp_path / 'routing.yaml'
    policy.write_text('decision_models:\n  learned_router: {mode: shadow, backend: heuristic}\n')
    monkeypatch.setattr(shadow.subprocess, 'run', lambda *a, **k: type('Result', (), {'stdout': json.dumps(
        dict(decision_id='test-decision', shadow_choice='other', confidence=.9, reason=reason))})())
    shadow.observe(tmp_path, policy, tmp_path, dict(
        route=dict(profile_ref='native', profile=dict(backend='claude', model='claude-sonnet-5-5'),
                   fallback_chain=[dict(profile_ref='other', profile=dict(backend='claude', model=model))]),
        native='native', role='scout', prompt_chars=401, exit_code=0))
    row = json.loads(next((tmp_path / '.clavain/decisions').glob('*.jsonl')).read_text())
    assert row['agreement'] is agreement
    assert row['estimated_claude_tokens_saved'] == expected


def test_append_wait_is_bounded_and_timer_restored(tmp_path, monkeypatch):
    import signal
    import time
    policy = tmp_path / 'routing.yaml'
    policy.write_text('decision_models:\n  learned_router: {mode: shadow, backend: heuristic}\n')
    monkeypatch.setattr(shadow.subprocess, 'run', lambda *a, **k: type('Result', (), {'stdout': json.dumps(
        dict(decision_id='test-decision', shadow_choice='native', confidence=1, reason='shadow_mode'))})())
    monkeypatch.setattr(shadow.records, 'append_record', lambda *a, **k: time.sleep(10))
    before = signal.getsignal(signal.SIGALRM)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        shadow.observe(tmp_path, policy, tmp_path, dict(
            route=dict(profile_ref='native', profile=dict(backend='claude', model='claude-sonnet-5-5')),
            native='native', role='scout', prompt_chars=401, exit_code=0))
    assert time.monotonic() - started < 2
    assert signal.getsignal(signal.SIGALRM) == before
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def test_extracted_detached_hook_starts_worker_and_preserves_status(tmp_path):
    import subprocess
    import time
    root = Path(__file__).resolve().parents[2]
    script = (root / 'scripts/dispatch.sh').read_text()
    hook = script.split('  DISPATCH_FINAL_RC="$_rc"', 1)[1].split('  if [[ "${CLAVAIN_HELD_SNAPSHOT_OWNER', 1)[0]
    # A deliberately slow Python worker must not hold stdout or the caller.
    worker = tmp_path / 'python3'
    worker.write_text('#!/bin/sh\n[ ! -e /proc/$$/fd/3 ] || exit 9\ntouch "$MARKER"\nsleep .15\ntouch "$FINISHED"\n')
    worker.chmod(0o755)
    import os
    env = dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}',
               MARKER=str(tmp_path / 'started'), FINISHED=str(tmp_path / 'finished'))
    start = time.monotonic()
    result = subprocess.run(['bash', '-c', '''
RUN_RECEIPT_ARMED=true; ROLE_RESOLVED=true; RESOLVED_ROUTE_JSON='{}'
RESOLVED_PROFILE_REF=seat; ROLE=scout; _rc=7; PROMPT='private task'
DISPATCH_SCRIPT_DIR=/irrelevant
exec 3>&1
''' + hook + '\nexit "$_rc"'], env=env, capture_output=True, timeout=1)
    assert result.returncode == 7
    assert result.stdout == result.stderr == b''
    assert time.monotonic() - start < 1
    for _ in range(100):
        if (tmp_path / 'finished').exists():
            break
        time.sleep(.01)
    assert (tmp_path / 'started').exists()
    assert (tmp_path / 'finished').exists()
