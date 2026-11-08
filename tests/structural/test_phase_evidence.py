"""Observe-mode phase evidence ledger (mk-4xzwm.1): records and warns, never blocks."""
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/phase-evidence.py'
HOOK = ROOT / 'hooks/phase-evidence.sh'
GOOD_CONTEXT = {'reasons': [], 'rationale': 'Settled routine change; tests define acceptance'}


def minimal_env(home):
    """A small, explicit environment for subprocesses.

    Nothing is copied wholesale from the parent, so an inherited credential can
    neither reach a subprocess nor be printed in a failure message. Only the
    command search path and locale are taken from the parent.
    """
    return {
        'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
        'HOME': str(home),
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'TMPDIR': str(home),
    }


def make_env(tmp_path):
    home = tmp_path / 'home'; home.mkdir(exist_ok=True)
    e = minimal_env(home)
    e['CLAVAIN_PHASE_EVIDENCE_DIR'] = str(tmp_path / 'ledger')
    return e


@pytest.fixture
def env(tmp_path):
    return make_env(tmp_path)


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
    env['DISPATCH_SESSION_ID'] = 'sd'
    missing = run(['dispatch', '--role', 'planning'], env)
    assert missing.returncode == 0 and 'decision-context missing' in missing.stderr
    ctx = tmp_path / 'ctx.json'; ctx.write_text(json.dumps(GOOD_CONTEXT))
    ok = run(['dispatch', '--role', 'planning', '--context', str(ctx)], env)
    assert ok.returncode == 0 and ok.stderr == ''
    rows = ledger(env, 'sd')
    assert [r['context_state'] for r in rows] == ['missing', 'ok']


def test_lib_gates_check_phase_gate_warns_but_returns_success(env, tmp_path):
    env['DISPATCH_SESSION_ID'] = 's9'
    env['HOME'] = str(tmp_path)  # no interphase companion, so the shim fallback is used
    hook('post', env, 'Edit', session='s9', file_path=str(tmp_path / 'a.py'))
    proc = subprocess.run(['bash', '-c', f'source "{ROOT}/hooks/lib-gates.sh"; check_phase_gate B-1 executing; echo rc=$?'],
                          capture_output=True, text=True, env=env, timeout=30)
    assert 'rc=0' in proc.stdout
    assert 'decision-context' in proc.stderr


# --- round 2 (review of the first head): fail open, privacy, bounds, cost ---

def wrapper(event, env, payload, path=None):
    e = dict(env)
    if path is not None:
        e['PATH'] = path
    return subprocess.run(['/bin/bash', str(HOOK), event], input=payload if isinstance(payload, str) else json.dumps(payload),
                          capture_output=True, text=True, env=e, timeout=30)


def fake_python(tmp_path, body, base_path):
    """A directory with a python3 that behaves badly, placed first on PATH."""
    d = tmp_path / 'badpy'; d.mkdir()
    exe = d / 'python3'; exe.write_text('#!/bin/sh\n' + body + '\n'); exe.chmod(0o755)
    return f'{d}:{base_path}'


EDIT_PAYLOAD = {'session_id': 's1', 'tool_name': 'Edit', 'tool_input': {'file_path': '/nonexistent/x.py'}}


def test_wrapper_without_python3_exits_zero_silently(env, tmp_path):
    empty = tmp_path / 'empty'; empty.mkdir()
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=str(empty))
    assert proc.returncode == 0 and proc.stdout == '' and proc.stderr == ''


@pytest.mark.parametrize('body', ['exit 3', 'echo \'{"decision": "block", "reason": "no"}\'; exit 0',
                                  'echo garbage; exit 0', 'echo \'{"systemMessage": "x"}\'; exit 7',
                                  'kill -SEGV $$'])
def test_wrapper_survives_python_crash_and_never_relays_a_block(env, tmp_path, body):
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, body, env['PATH']))
    assert proc.returncode == 0
    assert 'block' not in proc.stdout and 'garbage' not in proc.stdout
    assert proc.stdout == ''


def test_wrapper_relays_only_the_system_message(env, tmp_path):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    proc = wrapper('stop', env, {'session_id': 's1', 'tool_name': ''})
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert list(out) == ['systemMessage']


def test_wrapper_gives_up_on_a_hung_python(env, tmp_path):
    start = time.time()
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, 'sleep 30', env['PATH']))
    assert proc.returncode == 0 and proc.stdout == '' and time.time() - start < 10


def test_wrapper_skips_python_for_bash_commands_that_cannot_verify(env, tmp_path):
    # python3 would crash loudly if started; the prefilter must not start it
    path = fake_python(tmp_path, 'touch "$0.ran"; exit 1', env['PATH'])
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Bash', 'tool_input': {'command': 'ls -la'}}, path=path)
    assert not (tmp_path / 'badpy/python3.ran').exists()
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Bash', 'tool_input': {'command': 'pytest -q'}}, path=path)
    assert (tmp_path / 'badpy/python3.ran').exists()


def test_wrapper_records_through_the_real_hook(env, tmp_path):
    target = tmp_path / 'a.py'; target.write_text('x = 1\n')
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Read', 'tool_input': {'file_path': str(target)}})
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Bash', 'tool_input': {'command': 'uv run pytest -q'}})
    assert [r['kind'] for r in ledger(env)] == ['read', 'verify']


@pytest.mark.parametrize('umask', [0o077, 0o000, 0o022])
def test_state_is_private_whatever_the_umask(env, tmp_path, umask):
    code = ('import os,subprocess,sys,json; ENV=dict(%r); os.umask(%d); '
            'subprocess.run([sys.executable, %r, "hook", "post"], input=json.dumps({"session_id":"s1","tool_name":"Edit",'
            '"tool_input":{"file_path":"/tmp/zz.py"}}).encode(), env=ENV)' % (env, umask, str(SCRIPT)))
    subprocess.run([sys.executable, '-c', code], env=env, check=True, timeout=30)
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR'])
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    files = list(d.iterdir())
    assert files and all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in files)


def test_existing_loose_files_are_tightened(env, tmp_path):
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']); d.mkdir(); d.chmod(0o755)
    (d / 's1.jsonl').write_text(''); (d / 's1.jsonl').chmod(0o666)
    (d / 's1.sum.json').write_text(''); (d / 's1.sum.json').chmod(0o666)
    hook('post', env, 'Read', file_path=str(tmp_path / 'a.py'))
    assert all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in d.iterdir())


def test_ledger_holds_no_raw_paths_or_command_text(env, tmp_path):
    secret_cmd = 'pytest --marker=sentinel-value-xyz tests/'
    target = tmp_path / 'private-project-name.py'
    hook('post', env, 'Bash', command=secret_cmd)
    hook('post', env, 'Edit', file_path=str(target))
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR'])
    blob = ''.join(f.read_text() for f in d.iterdir())
    assert 'sentinel-value-xyz' not in blob and 'private-project-name' not in blob and str(tmp_path) not in blob
    verify = [r for r in ledger(env) if r['kind'] == 'verify'][0]
    assert verify['cmd_kind'] == 'pytest' and len(verify['h']) == 16 and 'command' not in verify


def test_ledger_growth_is_capped(env, tmp_path):
    for i in range(60):
        hook('post', env, 'Read', file_path=str(tmp_path / f'f{i}.py'))
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR'])
    ledger_file = d / 's1.jsonl'
    ledger_file.write_text(ledger_file.read_text() + ('x' * 1000 + '\n') * 300)  # past the 256 KiB cap
    hook('post', env, 'Read', file_path=str(tmp_path / 'after-cap.py'))
    size = ledger_file.stat().st_size
    for i in range(30):
        hook('post', env, 'Read', file_path=str(tmp_path / f'g{i}.py'))
    assert ledger_file.stat().st_size - size <= 200  # one truncation marker at most, then silence
    # the summary keeps working after the ledger stops growing
    hook('post', env, 'Edit', file_path=str(tmp_path / 'late.py'))
    assert 'verify-after-edit' in warning(hook('stop', env, ''))


def test_old_and_excess_sessions_are_pruned_when_a_new_session_starts(env, tmp_path):
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']); d.mkdir(mode=0o700)
    old = d / 'old.jsonl'; old.write_text('{}\n'); (d / 'old.sum.json').write_text('{}')
    past = time.time() - 30 * 86400
    for f in (old, d / 'old.sum.json'):
        os.utime(f, (past, past))
    for i in range(205):
        (d / f'bulk{i}.jsonl').write_text('{}\n')
        os.utime(d / f'bulk{i}.jsonl', (time.time() - 1000 + i, time.time() - 1000 + i))
    hook('post', env, 'Read', file_path=str(tmp_path / 'a.py'), session='fresh')
    names = {f.name for f in d.iterdir()}
    assert 'old.jsonl' not in names and 'old.sum.json' not in names
    assert 'fresh.jsonl' in names
    assert len([n for n in names if n.endswith('.jsonl')]) <= 200
    assert 'bulk204.jsonl' in names and 'bulk0.jsonl' not in names  # oldest go first


def test_hook_cost_does_not_grow_with_the_ledger(env, tmp_path):
    # Poison the ledger with unparseable bulk. The hooks must not read it at all,
    # so pre and stop behave identically and stay fast.
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    ledger_file = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']) / 's1.jsonl'
    ledger_file.write_text('{not json\n' * 100000)
    target = tmp_path / 'b.py'; target.write_text('x\n')
    start = time.time()
    assert 'read-before-edit' in warning(hook('pre', env, 'Edit', file_path=str(target)))
    assert 'verify-after-edit' in warning(hook('stop', env, ''))
    assert time.time() - start < 5


def test_huge_stdin_is_dropped_without_reading_it_all(env):
    big = '{"session_id": "s1", "tool_name": "Edit", "tool_input": {"file_path": "/x/a.py", "new_string": "' + 'a' * (5 << 20) + '"}}'
    proc = subprocess.run([sys.executable, str(SCRIPT), 'hook', 'post'], input=big, capture_output=True, text=True,
                          env=env, timeout=30)
    assert proc.returncode == 0 and proc.stdout == '' and proc.stderr == ''
    assert ledger(env) == []


def test_fifo_context_file_does_not_hang(env, tmp_path):
    fifo = tmp_path / 'ctx.fifo'; os.mkfifo(fifo)
    env['CLAVAIN_DECISION_CONTEXT'] = str(fifo)
    start = time.time()
    proc = hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    assert proc.returncode == 0 and time.time() - start < 5
    assert ledger(env)[0]['decision_context'] is False
    assert run(['dispatch', '--context', str(fifo)], env).returncode == 0


def test_oversize_context_file_is_unusable(env, tmp_path):
    ctx = tmp_path / 'ctx.json'
    ctx.write_text(json.dumps({'reasons': [], 'rationale': 'ok ' + 'x' * (200 << 10)}))
    env['CLAVAIN_DECISION_CONTEXT'] = str(ctx)
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    assert ledger(env)[0]['decision_context'] is False


def test_blocking_filesystem_objects_in_the_state_dir_degrade_silently(env, tmp_path):
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']); d.mkdir(mode=0o700)
    os.mkfifo(d / 's1.jsonl'); os.mkfifo(d / 's1.sum.json')
    proc = hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    assert proc.returncode == 0 and proc.stdout == '' and proc.stderr == ''
    assert hook('stop', env, '').stderr == ''


def test_symlinked_ledger_is_not_followed(env, tmp_path):
    victim = tmp_path / 'victim.txt'; victim.write_text('keep')
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']); d.mkdir(mode=0o700)
    (d / 's1.jsonl').symlink_to(victim)
    hook('post', env, 'Read', file_path=str(tmp_path / 'a.py'))
    assert victim.read_text() == 'keep'


def test_unusable_state_dir_is_silent_for_hooks_dispatch_and_check(env, tmp_path):
    blocker = tmp_path / 'file'; blocker.write_text('')
    env['CLAVAIN_PHASE_EVIDENCE_DIR'] = str(blocker / 'sub')  # a path under a regular file
    env['DISPATCH_SESSION_ID'] = 's1'
    for proc in (hook('post', env, 'Edit', file_path='/x/a.py'), hook('stop', env, ''),
                 run(['check', '--json'], env)):
        assert proc.returncode == 0 and proc.stderr == ''
    d = run(['dispatch', '--role', 'planning', '--context', str(tmp_path / 'none.json')], env)
    assert d.returncode == 0
    assert d.stderr.count('\n') == 1 and 'decision-context' in d.stderr  # the warning only, no traceback or error text


def test_sessions_with_colliding_sanitised_names_stay_apart(env, tmp_path):
    hook('post', env, 'Edit', session='a/b', file_path=str(tmp_path / 'x.py'))
    assert hook('stop', env, '', session='a_b').stdout.strip() == ''
    assert warning(hook('stop', env, '', session='a/b'))
    long_a, long_b = 's' * 120 + 'A', 's' * 120 + 'B'
    hook('post', env, 'Edit', session=long_a, file_path=str(tmp_path / 'x.py'))
    assert hook('stop', env, '', session=long_b).stdout.strip() == ''


def test_missing_session_id_records_nothing_and_shares_no_bucket(env, tmp_path):
    proc = run(['hook', 'post'], env, {'tool_name': 'Edit', 'tool_input': {'file_path': str(tmp_path / 'a.py')}})
    assert proc.returncode == 0
    assert not Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']).exists()
    run(['dispatch', '--role', 'planning'], env)  # no DISPATCH_SESSION_ID either
    assert not Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']).exists()


def test_dispatch_with_valid_context_counts_for_the_hook_session(env, tmp_path):
    ctx = tmp_path / 'ctx.json'; ctx.write_text(json.dumps(GOOD_CONTEXT))
    env['DISPATCH_SESSION_ID'] = 's1'  # the id the startup hook gives a dispatching session
    run(['dispatch', '--role', 'planning', '--context', str(ctx)], env)
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    msg = warning(hook('stop', env, ''))
    assert 'verify-after-edit' in msg and 'decision-context' not in msg


@pytest.mark.parametrize('cmd', [
    'echo pytest', 'echo "run pytest later"', 'grep -r ruff src', 'cat tests/pytest.ini', 'ls bats/',
    'echo CLAVAIN_DECISION_CONTEXT=x --context-file y route dispatch',
    'git commit -m "go test passes"', 'printf "make test"',
])
def test_command_text_that_only_mentions_a_verifier_does_not_count(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    msg = warning(hook('stop', env, ''))
    assert 'verify-after-edit' in msg and 'decision-context' in msg
    assert 'context' not in {r['kind'] for r in ledger(env)}


@pytest.mark.parametrize('cmd', [
    'pytest -q', 'cd tests && uv run pytest -n 4', 'nice -n 19 ionice -c3 pytest tests', 'FOO=1 timeout 570 ruff check .',
    'python3 -m pytest', 'bash -n hooks/x.sh', 'git diff --check', 'make test', 'npm run lint', 'go test ./...',
    'cargo clippy', '/usr/bin/shellcheck a.sh', 'echo start; bats tests/shell/x.bats', 'cat f | xargs echo && mypy src',
])
def test_real_verifier_commands_count(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' not in warning(hook('stop', env, ''))


def test_markdown_edits_never_trigger_the_pre_edit_warning(env, tmp_path):
    doc = tmp_path / 'README.md'; doc.write_text('# x\n')
    assert hook('pre', env, 'Edit', file_path=str(doc)).stdout.strip() == ''
    assert hook('stop', env, '').stdout.strip() == ''
    code = tmp_path / 'a.py'; code.write_text('x\n')
    assert 'read-before-edit' in warning(hook('pre', env, 'Edit', file_path=str(code)))


def test_lib_gates_and_dispatch_calls_carry_a_deadline():
    for rel in ('hooks/lib-gates.sh', 'scripts/dispatch.sh'):
        text = (ROOT / rel).read_text()
        assert 'timeout 5' in text and 'phase-evidence.py' in text, rel


def test_real_dispatch_wrapper_records_and_survives_a_bad_python(env, tmp_path):
    """Drive scripts/dispatch.sh itself, not the helper: it must record the dispatch and keep going."""
    bindir = tmp_path / 'bin'; bindir.mkdir()
    (bindir / 'ic').write_text('#!/bin/sh\nexit 1\n'); (bindir / 'ic').chmod(0o755)
    (bindir / 'jq').symlink_to(shutil.which('jq') or '/usr/bin/jq')
    env['DISPATCH_SESSION_ID'] = 'sdw'
    env['PATH'] = f'{bindir}:{env["PATH"]}'
    proc = subprocess.run(['bash', str(ROOT / 'scripts/dispatch.sh'), '--role', 'planning', '-C', str(tmp_path), 'hello'],
                          input='', capture_output=True, text=True, env=env, timeout=60)
    assert 'decision-context missing' in proc.stderr
    assert 'could not resolve dispatch role' in proc.stderr  # dispatch carried on to its own, unchanged outcome
    assert [r['kind'] for r in ledger(env, 'sdw')] == ['dispatch']
    # a python3 that hangs must not stall dispatch.sh past the deadline
    env['PATH'] = fake_python(tmp_path, 'sleep 60', env['PATH'])
    start = time.time()
    proc = subprocess.run(['bash', str(ROOT / 'scripts/dispatch.sh'), '--role', 'planning', '-C', str(tmp_path), 'hello'],
                          input='', capture_output=True, text=True, env=env, timeout=60)
    assert time.time() - start < 20 and 'could not resolve dispatch role' in proc.stderr


def test_subprocess_env_carries_no_inherited_secret(tmp_path, monkeypatch):
    """A credential in the parent environment must reach no subprocess and no failure message."""
    monkeypatch.setenv('FAKE_SECRET_TOKEN', 'sentinel-do-not-leak')
    env = make_env(tmp_path)  # built after the parent variable is set
    assert 'FAKE_SECRET_TOKEN' not in env and 'sentinel-do-not-leak' not in repr(env)
    assert set(env) == {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'CLAVAIN_PHASE_EVIDENCE_DIR'}
    proc = subprocess.run([sys.executable, '-c', 'import os; print(os.environ.get("FAKE_SECRET_TOKEN", "absent"))'],
                          capture_output=True, text=True, env=env, timeout=30)
    assert proc.stdout.strip() == 'absent'
    # the real wrapper and helper run under the same env, so neither can echo it
    wrapped = wrapper('stop', env, EDIT_PAYLOAD)
    assert 'sentinel-do-not-leak' not in wrapped.stdout + wrapped.stderr
