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
    assert proc.returncode == 0 and proc.stdout == '' and time.time() - start < 6


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
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_ledger_holds_no_raw_paths_or_command_text(env, tmp_path):
    secret_cmd = 'pytest --opt=sentinel-value-xyz tests/'
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


# --- round 3: deadline without `timeout`, relay filter, tab prefilter, non-verifying calls, directory mode ---

@pytest.fixture(scope='session')
def no_timeout_path(tmp_path_factory):
    """A PATH holding every command the real PATH has except `timeout`."""
    d = tmp_path_factory.mktemp('nobin')
    for part in os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin').split(':'):
        if not part or not os.path.isdir(part):
            continue
        for name in os.listdir(part):
            src = os.path.join(part, name)
            if name != 'timeout' and not (d / name).exists() and os.path.isfile(src) and os.access(src, os.X_OK):
                os.symlink(src, d / name)
    assert shutil.which('timeout', path=str(d)) is None and shutil.which('python3', path=str(d))
    return str(d)


def test_hook_deadline_holds_without_the_timeout_command(env, tmp_path, no_timeout_path):
    start = time.time()
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, 'sleep 60', no_timeout_path))
    assert proc.returncode == 0 and proc.stdout == '' and proc.stderr == ''
    assert time.time() - start < 5  # python is killed after 2 s; the host allows 5


def test_hook_still_records_and_warns_without_the_timeout_command(env, tmp_path, no_timeout_path):
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Edit', 'tool_input': {'file_path': str(tmp_path / 'a.py')}},
            path=no_timeout_path)
    proc = wrapper('stop', env, {'session_id': 's1', 'tool_name': ''}, path=no_timeout_path)
    assert proc.returncode == 0 and 'verify-after-edit' in warning(proc)
    assert [r['kind'] for r in ledger(env)][:1] == ['edit']


def test_hook_gives_up_on_an_incomplete_stdin_stream(env):
    """A host that never closes stdin must not hold the hook past its deadline."""
    start = time.time()
    proc = subprocess.Popen(['/bin/bash', str(HOOK), 'post'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, text=True)
    try:
        assert proc.stdin is not None
        proc.stdin.write('{"session_id": "s1", "tool_na'); proc.stdin.flush()  # never completed, never closed
        rc = proc.wait(timeout=8)
        out = proc.stdout.read() if proc.stdout else ''
    finally:
        proc.kill()
    assert rc == 0 and out == '' and time.time() - start < 5
    assert ledger(env) == []  # the cut-off payload is invalid JSON, so nothing is recorded


def test_hook_gives_up_when_stdin_stays_silent(env):
    start = time.time()
    proc = subprocess.Popen(['/bin/bash', str(HOOK), 'stop'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, text=True)
    try:
        rc = proc.wait(timeout=8)
    finally:
        proc.kill()
    assert rc == 0 and time.time() - start < 5


@pytest.mark.parametrize('out', [
    '{"systemMessage": "x", "hookSpecificOutput": {"permissionDecision": "deny"}}',
    '{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "x"}',
    '{"systemMessage": "x", "continue": false}',
    '{"systemMessage": "x", "decision": "block"}',
    '{"systemMessage": "x", "suppressOutput": true}',
    '{"systemMessage": "x"} trailing',
    '{"systemMessage": "one"}\n{"systemMessage": "two"}',
    '{"systemMessage": "bad \\q}',
    '{"systemMessage": "bad \\q"}',
    '{"systemMessage": "bad \\u12G4"}',
    '{"systemMessage": "short \\u12"}',
    '{"systemMessage": "ends with a lone backslash \\"}',
    '{"systemMessage": 1}',
    '[{"systemMessage": "x"}]',
])
def test_wrapper_relays_nothing_but_a_pure_system_message(env, tmp_path, out):
    body = "cat <<'EOF'\n" + out + "\nEOF"
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, body, env['PATH']))
    assert proc.returncode == 0 and proc.stdout == ''


def test_wrapper_relays_a_pure_system_message_verbatim(env, tmp_path):
    line = r'{"systemMessage": "phase evidence missing: \"quoted\" back\\slash\nline two"}'
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, "cat <<'EOF'\n" + line + "\nEOF", env['PATH']))
    assert proc.returncode == 0 and proc.stdout == line + '\n'


@pytest.mark.parametrize('cmd', ['go\ttest ./...', 'git\tdiff\t--check', 'bash\t-n hooks/x.sh', 'cd x &&\tmake\ttest',
                                 'cd tests\npytest -q', 'cd x\n\tgo\tvet ./...'])
def test_tab_and_newline_separated_verifiers_reach_python_and_count(env, tmp_path, cmd):
    edit = {'session_id': 's1', 'tool_name': 'Edit', 'tool_input': {'file_path': str(tmp_path / 'a.py')}}
    wrapper('post', env, edit)
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Bash', 'tool_input': {'command': cmd}})
    assert 'verify-after-edit' not in warning(wrapper('stop', env, {'session_id': 's1', 'tool_name': ''}))
    assert 'verify' in [r['kind'] for r in ledger(env)]


@pytest.mark.parametrize('cmd', ['ls -la', 'ls\t-la', 'cat\tREADME.md', 'echo hello\nls'])
def test_prefilter_still_skips_python_for_plainly_irrelevant_commands(env, tmp_path, cmd):
    path = fake_python(tmp_path, 'touch "$0.ran"; exit 1', env['PATH'])
    wrapper('post', env, {'session_id': 's1', 'tool_name': 'Bash', 'tool_input': {'command': cmd}}, path=path)
    assert not (tmp_path / 'badpy/python3.ran').exists()


@pytest.mark.parametrize('cmd', [
    'pytest --version', 'pytest -V', 'pytest --help', 'pytest --collect-only', 'pytest --fixtures',
    'nice pytest -h', 'ruff format src', 'ruff --version', 'ruff version', 'ruff help', 'ruff clean',
    'mypy --version', 'tsc --init', 'tsc -v', 'shellcheck --version', 'eslint --version', 'eslint --init',
    'bats --version', 'golangci-lint version', 'golangci-lint --help',
])
def test_verifier_invocations_that_verify_nothing_do_not_count(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' in warning(hook('stop', env, ''))
    assert 'verify' not in {r['kind'] for r in ledger(env)}


@pytest.mark.parametrize('cmd', [
    'pytest -q', 'pytest -v tests', 'ruff check .', 'ruff check --fix src', 'ruff .', 'ruff format --check src',
    'ruff format --diff src', 'mypy src', 'tsc --noEmit', 'eslint src', 'bats -r tests', 'shellcheck a.sh',
    'golangci-lint run', 'bats -rt tests', 'shellcheck -ax a.sh',
])
def test_verifier_invocations_that_do_verify_still_count(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' not in warning(hook('stop', env, ''))


@pytest.mark.parametrize('cmd', [
    'python3 -m pytest --version', 'python -m pytest -V', 'python3 -m pytest --help', 'python3 -m pytest -h',
    'python3 -m pytest --collect-only', 'python3.12 -m pytest --co -q', 'uv run python -m pytest --fixtures',
    'nice python3 -m pytest --markers', 'python3 -m unittest -h',
    'go test -h', 'go test -help', 'go test --help ./...', 'go vet -h', 'go vet -help',
    'cargo test --help', 'cargo test -h', 'cargo check --help', 'cargo clippy -h', 'cargo --version test',
    'npm test --help', 'npm run lint -h', 'yarn test --help', 'make test --help', 'make lint -h',
])
def test_module_form_and_help_only_invocations_do_not_count(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' in warning(hook('stop', env, ''))
    assert 'verify' not in {r['kind'] for r in ledger(env)}


@pytest.mark.parametrize('cmd', [
    'python3 -m pytest -q', 'python3 -m pytest tests/', 'python -m pytest -x --tb=short', 'uv run python -m pytest',
    'python3 -m unittest discover', 'python3 -m py_compile a.py', 'go test ./...', 'go vet ./...',
    'cargo test', 'cargo check', 'cargo clippy -- -D warnings', 'npm test', 'npm run lint', 'make test',
])
def test_module_form_and_other_real_runs_still_count(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' not in warning(hook('stop', env, ''))


@pytest.mark.parametrize('cmd', [
    'pytest --collectonly', 'pytest --collect-only=yes', 'pytest --coll', 'pytest --collect', 'pytest --hel', 'pytest --versi',
    'pytest -qh', 'pytest -xqV', 'pytest -lh tests', 'python3 -m pytest --collectonly', 'python3 -m pytest -qh',
    'python3 -m pytest --coll -q', 'python3 -m pytest --help=x', 'uv run python -m pytest -qV',
    'shellcheck -aV', 'bats -rh', 'bats -rv', 'ruff --vers', 'tsc --sho', 'cargo test -- --help', 'cargo test -- -h', 'npm test -- -h', 'npm test -- --help',
])
def test_help_and_collect_flags_match_by_prefix_and_inside_short_groups(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' in warning(hook('stop', env, ''))
    assert 'verify' not in {r['kind'] for r in ledger(env)}


@pytest.mark.parametrize('cmd', [
    'git diff --check -- -h', 'git diff --check -- --help', 'pytest -q -- -h', 'pytest -k help', 'pytest -khelp',
    'pytest --color=yes', 'pytest --cov=src', 'pytest --confcutdir=tests', 'pytest -rA', 'pytest -qx tests',
    'python3 -m pytest --color=yes -q', 'go test -short ./...', 'ruff check --select=E .', 'tsc --noEmit --allowJs',
])
def test_flag_matching_does_not_misread_paths_values_or_other_flags(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' not in warning(hook('stop', env, ''))


def test_wrapper_drops_an_oversized_message_within_the_deadline(env, tmp_path):
    body = ("printf '{\"systemMessage\": \"'; head -c 16777216 /dev/zero | tr '\\0' a; printf '\"}\\n'")
    start = time.time()
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, body, env['PATH']))
    assert proc.returncode == 0 and proc.stdout == ''
    assert time.time() - start < 4


def test_wrapper_still_relays_a_message_under_the_cap(env, tmp_path):
    line = '{"systemMessage": "' + 'a' * 8000 + '"}'
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, "cat <<'EOF'\n" + line + "\nEOF", env['PATH']))
    assert proc.returncode == 0 and proc.stdout == line + '\n'


@pytest.mark.parametrize('mode', [0o755, 0o777, 0o750, 0o700])
def test_existing_override_directory_becomes_private(env, tmp_path, mode):
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']); d.mkdir(); d.chmod(mode)
    hook('post', env, 'Read', file_path=str(tmp_path / 'a.py'))
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert list(d.iterdir()) and all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in d.iterdir())


def test_existing_override_directory_becomes_private_for_dispatch_too(env, tmp_path):
    d = Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']); d.mkdir(); d.chmod(0o755)
    env['DISPATCH_SESSION_ID'] = 'sd'
    assert run(['dispatch', '--role', 'planning'], env).returncode == 0
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def dispatch_stub_path(tmp_path, base):
    bindir = tmp_path / 'stubs'; bindir.mkdir(exist_ok=True)
    (bindir / 'ic').write_text('#!/bin/sh\nexit 1\n'); (bindir / 'ic').chmod(0o755)
    if not (bindir / 'jq').exists():
        (bindir / 'jq').symlink_to(shutil.which('jq') or '/usr/bin/jq')
    return f'{bindir}:{base}'


def run_dispatch(env, tmp_path):
    return subprocess.run(['bash', str(ROOT / 'scripts/dispatch.sh'), '--role', 'planning', '-C', str(tmp_path), 'hello'],
                          input='', capture_output=True, text=True, env=env, timeout=60)


def run_gate(env):
    return subprocess.run(['bash', '-c', f'source "{ROOT}/hooks/lib-gates.sh"; check_phase_gate B-1 executing; echo rc=$?'],
                          capture_output=True, text=True, env=env, timeout=60)


def test_dispatch_deadline_holds_without_the_timeout_command(env, tmp_path, no_timeout_path):
    env['DISPATCH_SESSION_ID'] = 'sdh'
    env['PATH'] = fake_python(tmp_path, 'sleep 60', dispatch_stub_path(tmp_path, no_timeout_path))
    start = time.time()
    proc = run_dispatch(env, tmp_path)
    assert 'could not resolve dispatch role' in proc.stderr  # dispatch.sh carried on to its own outcome
    assert time.time() - start < 15  # python killed after 5 s


def test_dispatch_warns_without_the_timeout_command(env, tmp_path, no_timeout_path):
    env['DISPATCH_SESSION_ID'] = 'sdw2'
    env['PATH'] = dispatch_stub_path(tmp_path, no_timeout_path)
    proc = run_dispatch(env, tmp_path)
    assert 'phase evidence missing (observe mode, not blocking): decision-context' in proc.stderr
    assert [r['kind'] for r in ledger(env, 'sdw2')] == ['dispatch']


def test_gate_deadline_holds_without_the_timeout_command(env, tmp_path, no_timeout_path):
    env['HOME'] = str(tmp_path)  # no interphase companion, so the shim fallback is used
    env['PATH'] = fake_python(tmp_path, 'sleep 60', no_timeout_path)
    start = time.time()
    proc = run_gate(env)
    assert 'rc=0' in proc.stdout and proc.stderr == ''
    assert time.time() - start < 15


def test_gate_warns_without_the_timeout_command(env, tmp_path, no_timeout_path):
    env['DISPATCH_SESSION_ID'] = 's9'; env['HOME'] = str(tmp_path); env['PATH'] = no_timeout_path
    hook('post', env, 'Edit', session='s9', file_path=str(tmp_path / 'a.py'))
    proc = run_gate(env)
    assert 'rc=0' in proc.stdout and 'decision-context' in proc.stderr


@pytest.mark.parametrize('body', ['echo "Traceback (most recent call last):" >&2; echo "boom: no module" >&2; exit 1',
                                  'echo "  - fake detail without a header" >&2; exit 0',
                                  'echo "garbage" >&2; exit 3'])
def test_python_start_up_failures_stay_silent_in_dispatch_and_gate(env, tmp_path, body):
    env['DISPATCH_SESSION_ID'] = 'sq'; env['HOME'] = str(tmp_path)
    env['PATH'] = fake_python(tmp_path, body, dispatch_stub_path(tmp_path, env['PATH']))
    proc = run_dispatch(env, tmp_path)
    for word in ('Traceback', 'boom', 'garbage', 'fake detail'):
        assert word not in proc.stderr
    assert 'could not resolve dispatch role' in proc.stderr
    gate = run_gate(env)
    assert 'rc=0' in gate.stdout and gate.stderr == ''


def test_dispatch_and_gate_relay_only_the_warning_block(env, tmp_path):
    body = ('echo "noise before" >&2; echo "phase evidence missing (observe mode, not blocking): x" >&2; '
            'echo "  - x: detail" >&2; echo "Traceback after" >&2; echo "  - orphan detail" >&2')
    env['DISPATCH_SESSION_ID'] = 'sr'; env['HOME'] = str(tmp_path)
    env['PATH'] = fake_python(tmp_path, body, dispatch_stub_path(tmp_path, env['PATH']))
    for proc in (run_dispatch(env, tmp_path), run_gate(env)):
        assert 'phase evidence missing (observe mode, not blocking): x' in proc.stderr and '  - x: detail' in proc.stderr
        for word in ('noise before', 'Traceback after', 'orphan detail'):
            assert word not in proc.stderr


def test_wrapper_drops_nul_padded_output_even_when_a_valid_relay_follows(env, tmp_path):
    body = ("head -c 32768 /dev/zero; printf '{\"systemMessage\": \"x\"}\\n'")
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, body, env['PATH']))
    assert proc.returncode == 0 and proc.stdout == ''


def test_wrapper_drops_a_few_nul_bytes_inside_a_small_message(env, tmp_path):
    body = "printf '{\"systemMessage\": \"a\\0b\"}\\n'"
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, body, env['PATH']))
    assert proc.returncode == 0 and proc.stdout == ''


def test_wrapper_ignores_a_huge_sparse_helper_output_within_the_deadline(env, tmp_path):
    body = "truncate -s 1G /proc/self/fd/1"
    start = time.time()
    proc = wrapper('stop', env, EDIT_PAYLOAD, path=fake_python(tmp_path, body, env['PATH']))
    assert proc.returncode == 0 and proc.stdout == ''
    assert time.time() - start < 4


def test_wrapper_ignores_a_1gib_sparse_stdin_within_the_deadline(env, tmp_path):
    sparse = tmp_path / 'sparse'
    subprocess.run(['truncate', '-s', '1G', str(sparse)], check=True)
    start = time.time()
    with open(sparse, 'rb') as fh:
        proc = subprocess.run(['/bin/bash', str(HOOK), 'stop'], stdin=fh, capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0 and proc.stdout == ''
    assert time.time() - start < 4
    assert not Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']).exists() or not any(Path(env['CLAVAIN_PHASE_EVIDENCE_DIR']).iterdir())


def test_wrapper_prefilter_handles_a_large_payload_with_many_escaped_tabs_within_the_deadline(env):
    payload = '{"session_id":"s1","tool_name":"Bash","tool_input":{"command":"echo ' + '\\t' * 131072 + '"}}'
    assert len(payload) > 262000
    start = time.time()
    proc = wrapper('post', env, payload)
    assert proc.returncode == 0 and proc.stdout == ''
    assert time.time() - start < 4


@pytest.mark.parametrize('cmd', ['python3 -m pytest -khelp', 'python3 -m pytest -k help', 'uv run python -m pytest -khelp', 'pytest -khelp'])
def test_pytest_k_value_is_not_a_help_flag_in_module_or_bare_form(env, tmp_path, cmd):
    hook('post', env, 'Edit', file_path=str(tmp_path / 'a.py'))
    hook('post', env, 'Bash', command=cmd)
    assert 'verify-after-edit' not in warning(hook('stop', env, ''))
