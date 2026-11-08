"""Observe-mode phase evidence ledger (mk-4xzwm.1): records and warns, never blocks."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/phase-evidence.py'
HOOK = ROOT / 'hooks/phase-evidence.sh'
GOOD_CONTEXT = {'reasons': [], 'rationale': 'Settled routine change; tests define acceptance'}


@pytest.fixture
def env(tmp_path):
    e = dict(os.environ)
    e['CLAVAIN_PHASE_EVIDENCE_DIR'] = str(tmp_path / 'ledger')
    for k in ('CLAVAIN_DECISION_CONTEXT', 'CLAVAIN_PHASE_EVIDENCE_MODE'):
        e.pop(k, None)
    return e


def run(args, env, payload=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=json.dumps(payload) if payload is not None else '',
                          capture_output=True, text=True, env=env, timeout=30)


def hook(event, env, tool, session='s1', stop_hook_active=False, **tool_input):
    payload = {'session_id': session, 'tool_name': tool, 'tool_input': tool_input}
    if stop_hook_active:
        payload['stop_hook_active'] = True
    return run(['hook', event], env, payload)


def warning(proc):
    return json.loads(proc.stdout)['systemMessage'] if proc.stdout.strip() else ''


def ledger(env, session='s1'):
    path = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']) / f'{session}.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_edit_without_prior_read_warns_but_never_blocks(env, tmp_path):
    target = tmp_path / 'a.py'; target.write_text('x = 1\n')
    proc = hook('pre', env, 'Edit', file_path=str(target))
    assert proc.returncode == 0
    assert 'read-before-edit' in warning(proc)
    assert 'decision' not in json.loads(proc.stdout) and 'block' not in json.loads(proc.stdout)
    assert any(r.get('evidence') == 'read-before-edit' for r in ledger(env))


def test_read_then_edit_is_silent(env, tmp_path):
    target = tmp_path / 'a.py'; target.write_text('x = 1\n')
    hook('post', env, 'Read', file_path=str(target))
    proc = hook('pre', env, 'Edit', file_path=str(target))
    assert proc.returncode == 0 and proc.stdout.strip() == ''


def test_write_of_new_file_and_reedit_after_own_write_are_silent(env, tmp_path):
    target = tmp_path / 'new.py'
    assert hook('pre', env, 'Write', file_path=str(target)).stdout.strip() == ''
    target.write_text('x = 1\n')
    hook('post', env, 'Write', file_path=str(target))
    assert hook('pre', env, 'Edit', file_path=str(target)).stdout.strip() == ''


def test_stop_warns_when_code_edit_has_no_verification_or_context(env, tmp_path):
    target = tmp_path / 'a.py'
    hook('post', env, 'Edit', file_path=str(target))
    msg = warning(hook('stop', env, ''))
    assert 'verify-after-edit' in msg and 'decision-context' in msg
    assert 'not blocking' in msg


def test_verification_after_edit_and_valid_context_satisfy_stop(env, tmp_path):
    ctx = tmp_path / 'ctx.json'; ctx.write_text(json.dumps(GOOD_CONTEXT))
    env['CLAVAIN_DECISION_CONTEXT'] = str(ctx)
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command='cd tests && uv run pytest -q -n 4')
    assert hook('stop', env, '').stdout.strip() == ''


def test_verification_before_the_last_edit_does_not_count(env, tmp_path):
    ctx = tmp_path / 'ctx.json'; ctx.write_text(json.dumps(GOOD_CONTEXT))
    env['CLAVAIN_DECISION_CONTEXT'] = str(ctx)
    hook('post', env, 'Bash', command='pytest -q')
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    msg = warning(hook('stop', env, ''))
    assert 'verify-after-edit' in msg and 'decision-context' not in msg


def test_unusable_context_does_not_count(env, tmp_path):
    ctx = tmp_path / 'ctx.json'; ctx.write_text(json.dumps({'reasons': [], 'rationale': '  '}))
    env['CLAVAIN_DECISION_CONTEXT'] = str(ctx)
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command='pytest')
    assert 'decision-context' in warning(hook('stop', env, ''))


def test_doc_only_edits_need_neither_verification_nor_context(env, tmp_path):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'notes.md'))
    assert hook('stop', env, '').stdout.strip() == ''


def test_stop_warns_once_per_edit_burst_and_respects_stop_hook_active(env, tmp_path):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    assert warning(hook('stop', env, ''))
    assert hook('stop', env, '').stdout.strip() == ''
    hook('post', env, 'Edit', file_path=str(tmp_path / 'b.py'))
    assert hook('stop', env, '', stop_hook_active=True).stdout.strip() == ''
    assert warning(hook('stop', env, ''))


def test_ledger_rows_carry_oodarc_role(env, tmp_path):
    hook('post', env, 'Read', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    roles = [r['oodarc_role'] for r in ledger(env)]
    assert roles == ['observe', 'act']


def test_off_mode_records_nothing(env, tmp_path):
    env['CLAVAIN_PHASE_EVIDENCE_MODE'] = 'off'
    proc = hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    assert proc.returncode == 0 and ledger(env) == []


def test_bad_input_never_fails(env):
    for raw in ('', 'not json', '[]', '{"tool_name": 7}'):
        proc = subprocess.run([sys.executable, str(SCRIPT), 'hook', 'post'], input=raw,
                              capture_output=True, text=True, env=env, timeout=30)
        assert proc.returncode == 0


def test_hook_wrapper_exits_zero_even_without_python_payload(env):
    proc = subprocess.run(['bash', str(HOOK), 'post'], input='garbage', capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0


def test_hooks_json_registers_pre_post_stop():
    hooks = json.loads((ROOT / 'hooks/hooks.json').read_text())['hooks']
    def args(event):
        return [h['args'] for g in hooks[event] for h in g['hooks'] if h['command'].endswith('/phase-evidence.sh')]
    assert args('PreToolUse') == [['pre']]
    assert args('PostToolUse') == [['post']]
    assert args('Stop') == [['stop']]


def test_check_reports_leg_needs_for_lifecycle_phase(env, tmp_path):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    act = json.loads(run(['check', '--session', 's1', '--phase', 'executing', '--json'], env).stdout)
    assert act['oodarc_role'] == 'act'
    assert [m['evidence'] for m in act['missing']] == ['decision-context']
    reflect = json.loads(run(['check', '--session', 's1', '--phase', 'reflect', '--json'], env).stdout)
    assert reflect['oodarc_role'] == 'reflect+compound'
    assert [m['evidence'] for m in reflect['missing']] == ['verify-after-edit']
    unknown = json.loads(run(['check', '--session', 's1', '--phase', 'nonsense', '--json'], env).stdout)
    assert unknown['missing'][0]['evidence'] == 'unknown-phase'


def test_phase_roles_match_intercore_vocabulary():
    spec = {'brainstorm': 'observe', 'brainstorm-reviewed': 'observe', 'strategized': 'orient',
            'planned': 'decide', 'executing': 'act', 'review': 'observe', 'polish': 'act',
            'reflect': 'reflect+compound', 'done': 'terminal'}
    ns = {}
    exec(compile(SCRIPT.read_text().split('\nLEG_NEEDS')[0], str(SCRIPT), 'exec'), {'__name__': 'x'}, ns)
    assert ns['PHASE_ROLE'] == spec


def test_dispatch_check_records_and_warns_without_failing(env, tmp_path):
    missing = run(['dispatch', '--role', 'planning'], env)
    assert missing.returncode == 0 and 'decision-context missing' in missing.stderr
    ctx = tmp_path / 'ctx.json'; ctx.write_text(json.dumps(GOOD_CONTEXT))
    ok = run(['dispatch', '--role', 'planning', '--context', str(ctx)], env)
    assert ok.returncode == 0 and ok.stderr == ''
    rows = ledger(env, 'no-session')
    assert [r['context_state'] for r in rows] == ['missing', 'ok']


def test_lib_gates_check_phase_gate_warns_but_returns_success(env, tmp_path):
    env['DISPATCH_SESSION_ID'] = 's9'
    env['HOME'] = str(tmp_path)  # no interphase companion, so the shim fallback is used
    hook('post', env, 'Edit', session='s9', file_path=str(tmp_path / 'a.py'))
    proc = subprocess.run(['bash', '-c', f'source "{ROOT}/hooks/lib-gates.sh"; check_phase_gate B-1 executing; echo rc=$?'],
                          capture_output=True, text=True, env=env, timeout=30)
    assert 'rc=0' in proc.stdout
    assert 'decision-context' in proc.stderr
