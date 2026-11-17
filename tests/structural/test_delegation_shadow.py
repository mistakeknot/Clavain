"""System One main-thread delegation shadow observations.

The helper observes a delegation choice the instruction already made. It never
changes that choice, never calls out unless the question's policy is `shadow`,
and fails open. A stub `clavain-cli` stands in for the Go wrapper but drives the
real decide.py and the real locked record writer.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

STUB = '''#!{python}
import io, json, os, sys, time, types
from pathlib import Path
args = sys.argv[1:]
assert args[0] == 'decide', args
opts = dict(zip(args[1::2], args[2::2]))
if os.environ.get('STUB_MARKER'):
    Path(os.environ['STUB_MARKER']).open('a').write('called\\n')
raw = sys.stdin.read()
if os.environ.get('STUB_CAPTURE'):
    Path(os.environ['STUB_CAPTURE']).write_text(raw)
mode = os.environ.get('STUB_MODE', 'real')
if mode == 'sleep':
    time.sleep(30)
if mode == 'slow':
    time.sleep(2)
if mode == 'crash':
    sys.exit(3)
if mode == 'garbage':
    print('not json')
    sys.exit(0)
sys.path.insert(0, {scripts!r})
import yaml
req = json.loads(raw)
policy = (yaml.safe_load(open(opts['--config'])).get('decision_models') or {{}}).get(req['question']['id'])
if policy is None:
    print(json.dumps(dict(choice=req['native_choice'], probs={{}}, confidence=0, fallback=True, reason='off')))
    sys.exit(0)
envelope = json.dumps(dict(request=req, policy=policy, project_root=str(Path(opts['--project-root']).resolve())))
sys.stdin = types.SimpleNamespace(buffer=io.BytesIO(envelope.encode()))
from clavain_selector.decide import main
main()
'''

CANDIDATES = [('plan', 'Plan the work'), ('build', 'Build the work')]


def test_wrapper_exit_cleans_up_surviving_descendant(tmp_path):
    from clavain_selector import delegation_shadow as ds
    import signal
    marker = tmp_path / 'child.pid'
    script = (
        'import subprocess,sys; '
        'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"],'
        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
        'open(sys.argv[1],"w").write(str(p.pid))'
    )
    ds._run_decide([sys.executable, '-c', script, str(marker)], {}, 1)
    pid = int(marker.read_text())
    try:
        for _ in range(50):
            status = Path(f'/proc/{pid}/stat')
            if not status.exists() or status.read_text().split()[2] == 'Z':
                break
            time.sleep(.01)
        else:
            pytest.fail('CLI descendant survived wrapper exit')
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
SECRET_STATE = 'sk-AAAA-private-state-value'
SECRET_DESC = 'PRIVATE-DESCRIPTION-SENTINEL'
SECRET_TEXT = 'PRIVATE-TEXT-SENTINEL'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def env(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    cli = tmp_path / 'clavain-cli'
    cli.write_text(STUB.format(python=sys.executable, scripts=str(ROOT / 'scripts')))
    cli.chmod(0o755)
    monkeypatch.setenv('CLAVAIN_CLI', str(cli))
    monkeypatch.setenv('STUB_MARKER', str(tmp_path / 'marker'))
    monkeypatch.setenv('STUB_CAPTURE', str(tmp_path / 'capture.json'))
    monkeypatch.delenv('CLAVAIN_SELECTOR', raising=False)
    monkeypatch.delenv('STUB_MODE', raising=False)

    def config(mode='shadow', backend='heuristic', question='flux_triage'):
        path = tmp_path / 'routing.yaml'
        path.write_text(yaml.safe_dump({'decision_models': {question: {'backend': backend, 'mode': mode}}}))
        return path

    class Env:
        pass
    e = Env()
    e.tmp, e.project, e.config = tmp_path, project, config
    e.called = lambda: (tmp_path / 'marker').exists()
    e.records = lambda: [json.loads(line) for p in sorted((project / '.clavain/decisions').glob('*.jsonl'))
                         for line in p.read_text().splitlines()] if (project / '.clavain').exists() else []
    return e


def run(env, config=None, **overrides):
    from clavain_selector import delegation_shadow as ds
    kwargs = dict(site='codex-delegate', native_choice='plan', candidates=list(CANDIDATES),
                  state={'files': 3, 'kind': 'docs'}, main_thread_tokens=1200,
                  native_outcome='success', project_root=env.project,
                  config=config or env.config(), deadline_s=5)
    kwargs.update(overrides)
    return ds.observe(**kwargs)


def companion_of(records):
    found = [r for r in records if r.get('schema') == 'clavain-delegation-shadow-v1']
    assert len(found) == 1
    return found[0]


# --- heuristic record: agreement, savings, privacy ---------------------------------

def test_heuristic_shadow_writes_linked_companion_record(env):
    result = run(env, candidates=[('plan', SECRET_DESC), ('build', 'Build the work')],
                 state={'files': 3, 'label': 'docs'})
    assert result['status'] == 'observed'
    assert result['native_choice'] == 'plan'
    records = env.records()
    decide = next(r for r in records if r['schema'] == 'clavain-decide-v1')
    comp = companion_of(records)
    # Documented join: companion.decision_id == decide.decision_id.
    assert comp['decision_id'] == decide['decision_id'] == result['decision_id']
    assert comp['question_id'] == sha('flux_triage') == decide['question_id']
    assert comp['native_choice'] == sha('plan') == decide['native_choice']
    assert comp['shadow_choice'] == sha('plan')
    assert comp['candidates'] == [sha('plan'), sha('build')]
    assert comp['agreement'] is True
    assert comp['confidence'] == 1 and comp['band'] == 'accept' and comp['backend'] == 'heuristic'
    assert comp['reason'] == 'shadow_mode'
    assert comp['native_actual_outcome'] == 'success'
    assert comp['main_thread_tokens'] == 1200
    assert comp['estimated_claude_tokens_saved'] == 1200
    assert comp['estimate_method'] == 'main_thread_decision_tokens_if_agree_accept_v1'
    assert comp['site'] == 'codex-delegate'
    assert comp['applied'] == 'native' and comp['mode'] == 'shadow'
    assert comp['egress_allowed'] is False
    assert comp['identifier_encoding'] == 'sha256'


def test_records_hold_no_raw_text_and_stay_private(env):
    run(env, candidates=[('plan', SECRET_DESC), ('build', 'Build the work')],
        state={'files': 3, 'label': 'docs'})
    day_files = list((env.project / '.clavain/decisions').glob('*.jsonl'))
    assert day_files
    blob = ''.join(p.read_text() for p in day_files)
    for needle in (SECRET_DESC, 'Choose', '"plan"', '"build"', 'flux_triage', 'docs'):
        assert needle not in blob, needle
    assert (env.project / '.clavain/decisions').stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in day_files)


def test_unknown_estimate_stays_null(env):
    for bad in (None, 'many', -5, True, float('nan'), 1.5):
        env.project  # fresh project root each time
        root = env.tmp / f'p{abs(hash(repr(bad)))}'
        root.mkdir()
        run(env, project_root=root, main_thread_tokens=bad)
        comp = companion_of([json.loads(l) for p in (root / '.clavain/decisions').glob('*.jsonl')
                             for l in p.read_text().splitlines()])
        assert comp['estimated_claude_tokens_saved'] is None, bad
        assert comp['main_thread_tokens'] is None, bad
        assert comp['estimate_method'] == 'main_thread_decision_tokens_if_agree_accept_v1'


def test_unknown_native_outcome_stays_null(env):
    for bad in (None, 'because I said so', 'Success', ''):
        root = env.tmp / f'o{abs(hash(repr(bad)))}'
        root.mkdir()
        run(env, project_root=root, native_outcome=bad)
        comp = companion_of([json.loads(l) for p in (root / '.clavain/decisions').glob('*.jsonl')
                             for l in p.read_text().splitlines()])
        assert comp['native_actual_outcome'] is None


@pytest.mark.parametrize('shadow,confidence,band,reason,agree,saved', [
    ('plan', 1.0, 'accept', 'shadow_mode', True, 900),
    ('build', 0.9, 'accept', 'shadow_mode', False, 0),
    ('plan', 0.7, 'review', 'shadow_mode', True, 0),
    ('plan', 0.0, 'escalate', 'egress_not_authorized', None, None),
    ('plan', 0.0, 'escalate', 'timeout', None, None),
])
def test_agreement_and_savings_rules(shadow, confidence, band, reason, agree, saved):
    from clavain_selector import delegation_shadow as ds
    answer = dict(shadow_choice=shadow, confidence=confidence, band=band, reason=reason,
                  backend='jev', decision_id='d-1', latency_ms=4, fallback=True)
    comp = ds.build_companion(answer, site='quality-gates', question_id='flux_triage',
                              native_choice='plan', candidate_ids=['plan', 'build'],
                              main_thread_tokens=900, native_outcome=None)
    assert comp['agreement'] is agree
    assert comp['estimated_claude_tokens_saved'] == saved
    assert comp['decision_id'] == 'd-1'
    assert comp['shadow_choice'] == sha(shadow)


# --- inert: off / enforce / kill / missing policy ----------------------------------

@pytest.mark.parametrize('mode', ['off', 'enforce', 'Shadow', 'on', '', None])
def test_non_shadow_policy_is_inert(env, mode, monkeypatch):
    from clavain_selector import delegation_shadow as ds
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('spawned'))
    result = run(env, config=env.config(mode=mode))
    assert result['status'] == 'inert' and result['native_choice'] == 'plan'
    assert not env.called()
    assert not (env.project / '.clavain').exists()
    assert ds.main(_argv(), project_root=env.project, config=env.config(mode=mode)) == 0
    assert not env.called() and not (env.project / '.clavain').exists()


def test_kill_switch_and_missing_question_are_inert(env, monkeypatch):
    monkeypatch.setenv('CLAVAIN_SELECTOR', ' OFF ')
    assert run(env)['status'] == 'inert'
    monkeypatch.delenv('CLAVAIN_SELECTOR')
    assert run(env, config=env.config(question='route'))['status'] == 'inert'
    assert run(env, config=env.tmp / 'missing.yaml')['status'] == 'inert'
    assert not env.called()
    assert not (env.project / '.clavain').exists()


def test_invalid_input_is_inert_and_makes_no_call(env):
    bad = [dict(native_choice='unknown'),
           dict(state={'note': 'free text with spaces and a secret ' + SECRET_STATE}),
           dict(state={'nested': {'a': 1}}),
           dict(candidates=[]),
           dict(candidates=[('plan', 'x'), ('plan', 'y')]),
           dict(candidates=[('bad id!', 'x'), ('plan', 'y')]),
           dict(site='not-a-site')]
    for overrides in bad:
        result = run(env, **overrides)
        assert result['status'] == 'inert', overrides
        assert result['reason'] == 'invalid_input', overrides
    assert not env.called()
    assert not (env.project / '.clavain').exists()


# --- request shape: egress false, typed, native untouched ---------------------------

def test_request_sent_to_decide_is_typed_and_never_egresses(env):
    run(env, state={'files': 3, 'kind': 'docs'})
    sent = json.loads((env.tmp / 'capture.json').read_text())
    assert sent['egress_allowed'] is False
    assert sent['sources'] == []
    assert sent['native_choice'] == 'plan'
    assert sent['question']['id'] == 'flux_triage'
    assert [c['id'] for c in sent['question']['candidates']] == ['plan', 'build']
    assert sent['state'] == {'files': 3, 'kind': 'docs'}


def test_jev_policy_without_egress_never_leaves_machine(env):
    result = run(env, config=env.config(backend='jev'))
    comp = companion_of(env.records())
    assert result['native_choice'] == 'plan'
    assert comp['reason'] == 'egress_not_authorized'
    assert comp['agreement'] is None and comp['estimated_claude_tokens_saved'] is None
    assert comp['confidence'] == 0


# --- fail open -----------------------------------------------------------------------

@pytest.mark.parametrize('mode', ['crash', 'garbage'])
def test_cli_failure_fails_open(env, monkeypatch, mode):
    monkeypatch.setenv('STUB_MODE', mode)
    result = run(env)
    assert result['status'] == 'failed' and result['native_choice'] == 'plan'
    assert env.records() == []


def test_missing_cli_fails_open(env, monkeypatch):
    monkeypatch.setenv('CLAVAIN_CLI', str(env.tmp / 'nope'))
    (env.tmp / 'empty').mkdir()
    monkeypatch.setenv('PATH', str(env.tmp / 'empty'))
    result = run(env, plugin_root=env.tmp / 'empty')
    assert result['status'] == 'failed' and result['reason'] == 'cli_unavailable'


def test_timeout_fails_open_and_is_bounded(env, monkeypatch):
    monkeypatch.setenv('STUB_MODE', 'sleep')
    start = time.monotonic()
    result = run(env, deadline_s=1)
    assert time.monotonic() - start < 3
    assert result['status'] == 'failed' and result['reason'] == 'timeout'
    assert result['native_choice'] == 'plan'
    assert env.records() == []


def test_total_cap_is_six_seconds():
    from clavain_selector import delegation_shadow as ds
    assert ds.DEADLINE_S == 6


def test_record_write_error_fails_open(env, monkeypatch):
    from clavain_selector import delegation_shadow as ds
    monkeypatch.setattr(ds.records, 'append_record',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('disk exploded')))
    result = run(env)
    assert result['status'] == 'failed' and result['native_choice'] == 'plan'


def test_symlinked_log_dir_is_refused_not_followed(env):
    outside = env.tmp / 'outside'
    outside.mkdir(mode=0o755)
    (env.project / '.clavain').symlink_to(outside, target_is_directory=True)
    result = run(env)
    assert result['native_choice'] == 'plan'
    assert list(outside.iterdir()) == []
    assert outside.stat().st_mode & 0o777 == 0o755


# --- CLI: detached, silent, always exit 0 ---------------------------------------------

def _argv(**extra):
    argv = ['--site', 'codex-delegate', '--native', 'plan',
            '--candidate', 'plan=Plan the work', '--candidate', 'build=Build the work',
            '--state', 'files=3', '--main-thread-tokens', '1200', '--native-outcome', 'success']
    for key, value in extra.items():
        argv += [f'--{key.replace("_", "-")}', value]
    return argv


def test_main_returns_before_slow_observation_and_record_lands_later(env, monkeypatch, capsys):
    from clavain_selector import delegation_shadow as ds
    monkeypatch.setenv('STUB_MODE', 'slow')
    start = time.monotonic()
    code = ds.main(_argv(), project_root=env.project, config=env.config())
    assert code == 0
    assert time.monotonic() - start < 1.5
    assert capsys.readouterr().out == ''
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not any(
            r.get('schema') == 'clavain-delegation-shadow-v1' for r in env.records()):
        time.sleep(0.2)
    assert companion_of(env.records())['native_choice'] == sha('plan')


def test_main_is_silent_and_exits_zero_on_garbage_args(env, capsys):
    from clavain_selector import delegation_shadow as ds
    for argv in (['--bogus'], [], ['--native'], _argv(main_thread_tokens='lots')):
        assert ds.main(argv, project_root=env.project, config=env.config()) == 0
    out = capsys.readouterr()
    assert out.out == '' and out.err == ''


def test_script_entry_point_is_silent_and_inert_by_default(env):
    proc = subprocess.run([sys.executable, str(ROOT / 'scripts/clavain_selector/delegation_shadow.py'),
                           '--foreground', '--project-root', str(env.project)] + _argv()[0:],
                          capture_output=True, text=True, timeout=20,
                          env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts')})
    assert proc.returncode == 0 and proc.stdout == '' and proc.stderr == ''
    # The shipped routing.yaml keeps flux_triage off, so nothing may be written.
    assert not (env.project / '.clavain').exists()


# --- shipped configuration is untouched -----------------------------------------------

def test_shipped_policy_stays_off_and_budget_unchanged():
    routing = yaml.safe_load((ROOT / 'config/routing.yaml').read_text())
    policy = routing['decision_models']['flux_triage']  # YAML 1.1 reads a bare `off` as False
    assert policy['backend'] == 'heuristic' and policy['mode'] in ('off', False)
    registry = json.loads((ROOT / 'config/selector-integrations.json').read_text())
    entry = registry['integrations']['decision_models']
    assert entry['enabled'] is False and entry['daily_budget'] == 8


# --- instruction call sites ------------------------------------------------------------

SITES = {
    'quality-gates': ROOT / 'commands/quality-gates.md',
    'codex-delegate': ROOT / 'skills/codex-delegate/SKILL.md',
    'interserve-engine': ROOT / 'skills/interserve-engine/SKILL.md',
}


def helper_commands(path):
    text = path.read_text()
    found = []
    for block in re.findall(r'```bash\n(.*?)```', text, re.S):
        joined = block.replace('\\\n', ' ')
        for line in joined.splitlines():
            if 'delegation_shadow.py' in line:
                found.append((text.index(block), line))
    return found


@pytest.mark.parametrize('site', sorted(SITES))
def test_call_site_invokes_helper_with_actual_native_choice(site, env):
    from clavain_selector import delegation_shadow as ds
    path = SITES[site]
    found = helper_commands(path)
    assert len(found) == 1, f'{path} must carry exactly one helper call'
    offset, line = found[0]
    assert line.rstrip().endswith('|| true'), 'observation must never fail the workflow'
    assert 'egress' not in line and '--foreground' not in line
    tail = line.split('delegation_shadow.py', 1)[1].replace('|| true', '').replace('>/dev/null 2>&1', '').lstrip('"')
    words = shlex.split(tail)
    ns = ds.parse_args([re.sub(r'\$\{?[A-Za-z_]+[^ ]*', 'x', w) if w.startswith('$') or '$' in w else w
                        for w in words])
    assert ns.site == site
    # The native choice is a variable holding the choice already made, never a literal label.
    assert re.search(r'--native\s+"?\$', line), 'pass the actual choice via a variable'
    assert ds.SITES[site]


def test_quality_gates_call_site_follows_the_fixed_delegation():
    text = SITES['quality-gates'].read_text()
    assert text.index('/interflux:flux-drive $DIFF_PATH --phase=quality-gates') < text.index('delegation_shadow.py')
    assert text.index('delegation_shadow.py') < text.index('## Phase 2b')
    assert 'FLUX_DRIVE_STATUS' in text[text.index('delegation_shadow.py') - 400:text.index('delegation_shadow.py')]


def test_codex_delegate_call_site_follows_dispatch():
    text = SITES['codex-delegate'].read_text()
    assert text.index('**3. Dispatch**') < text.index('delegation_shadow.py') < text.index('**5. Reflect')


def test_interserve_call_site_follows_the_mode_choice():
    text = SITES['interserve-engine'].read_text()
    assert text.index('## Dispatch Routing') < text.index('delegation_shadow.py') < text.index('## Megaprompt Mode')


# --- doc ---------------------------------------------------------------------------------

def test_doc_states_method_paths_join_and_log_reading():
    doc = (ROOT / 'docs/reference/delegation-shadow.md').read_text()
    for needle in ('main thread decision tokens only', 'estimate_method',
                   'main_thread_decision_tokens_if_agree_accept_v1', '.clavain/decisions',
                   'clavain-delegation-shadow-v1', 'clavain-decide-v1', 'decision_id',
                   'estimated_claude_tokens_saved', 'agreement', 'native_actual_outcome',
                   'jq', 'egress', 'CLAVAIN_SELECTOR=off'):
        assert needle in doc, needle
    assert 'delegation-shadow.md' in (ROOT / 'docs/reference/decide.md').read_text()
