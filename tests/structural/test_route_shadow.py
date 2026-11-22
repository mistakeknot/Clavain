"""S2 observes native answers without influencing them or exporting text."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('bundled', ['executable', 'missing', 'nonexecutable'])
def test_real_binary_resolution(setup, monkeypatch, tmp_path, bundled):
    s, args = setup
    plugin = tmp_path / 'plugin'
    (plugin / 'bin').mkdir(parents=True)
    path_dir = tmp_path / 'path'
    path_dir.mkdir()
    marker = tmp_path / 'invocation.json'
    monkeypatch.setenv('PATH', str(path_dir))
    monkeypatch.setenv('S2_TEST_MARKER', str(marker))
    for location, label in [(path_dir / 'clavain-cli', 'path'),
                            (plugin / 'bin/clavain-cli', 'bundled')]:
        if label == 'bundled' and bundled == 'missing':
            continue
        location.write_text('#!' + sys.executable + '\n'
            'import json, os, sys\n'
            'from pathlib import Path\n'
            'Path(os.environ["S2_TEST_MARKER"]).write_text(json.dumps('
            '{"binary": ' + repr(label) + ', "args": sys.argv[1:], '
            '"request": json.load(sys.stdin)}))\n')
        location.chmod(0o600 if label == 'bundled' and bundled == 'nonexecutable' else 0o700)
    args['plugin_root'] = plugin
    s.observe(**args)
    record = json.loads(marker.read_text())
    assert record['binary'] == ('bundled' if bundled == 'executable' else 'path')
    assert record['args'][:3] == ['decide', '--plugin-root', str(plugin)]
    assert record['request']['question']['id'] == 'route'
    assert record['request']['native_choice'] == 'work'
    assert record['request']['egress_allowed'] is False


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from clavain_selector import route_shadow as s
    monkeypatch.delenv('CLAVAIN_SELECTOR', raising=False)
    config = tmp_path / 'routing.yaml'
    config.write_text('decision_models:\n  route: {mode: shadow, backend: heuristic}\n')
    args = dict(site='route-4b', native_choice='work', subject_sha256=sha('private bead'),
                input_bytes=11, output_bytes=6, batch_size=1,
                plugin_root=ROOT, config=config, project_root=tmp_path)
    return s, args


@pytest.mark.parametrize('policy', ['{}', 'null', 'decision_models: []',
    'decision_models:\n  route: {mode: off, backend: heuristic}',
    'decision_models:\n  route: {mode: enforce, backend: heuristic}',
    'decision_models:\n  route: {mode: SHADOW, backend: heuristic}',
    'decision_models:\n  route: {mode: unknown, backend: heuristic}',
    'decision_models:\n  route: {mode: shadow, backend: jev}',
    'decision_models:\n  route: {mode: shadow}'])
def test_inert_policy(setup, monkeypatch, policy):
    s, args = setup
    args['config'].write_text(policy)
    monkeypatch.setattr(s.subprocess, 'run', lambda *a, **kw: pytest.fail('subprocess'))
    assert s.observe(**args) is None
    assert not (args['project_root'] / '.clavain').exists()


def test_global_off_before_config(setup, monkeypatch):
    s, args = setup
    monkeypatch.setenv('CLAVAIN_SELECTOR', ' OFF ')
    args['config'].unlink()
    monkeypatch.setattr(s.subprocess, 'run', lambda *a, **kw: pytest.fail('subprocess'))
    assert s.observe(**args) is None


@pytest.mark.parametrize('key,value', [('native_choice', '/work'), ('native_choice', True),
    ('site', 'unknown'), ('subject_sha256', 'private bead'), ('input_bytes', True),
    ('input_bytes', -1), ('output_bytes', 1.5), ('batch_size', 0),
    ('input_bytes', 10**10), ('subject_sha256', 'A'*64)])
def test_invalid_observation_inert(setup, monkeypatch, key, value):
    s, args = setup
    args[key] = value
    monkeypatch.setattr(s.subprocess, 'run', lambda *a, **kw: pytest.fail('subprocess'))
    assert s.observe(**args) is None
    assert not (args['project_root'] / '.clavain').exists()


@pytest.mark.parametrize('site,choices', [
    ('route-4b', ['sprint', 'work']),
    ('route-staleness', ['implemented', 'not_implemented']),
    ('route-sweep', ['implemented', 'not_implemented']),
    ('sprint-lane-intent', ['contradicts', 'aligned'])])
def test_real_heuristic_bridge_and_private_record(setup, monkeypatch, site, choices):
    from clavain_selector.decide import decide
    s, args = setup
    args.update(site=site, native_choice=choices[0], batch_size=3)
    calls = []
    def bridge(cmd, **kw):
        obj = json.loads(kw['input'])
        result = decide(obj, dict(mode='shadow', backend='heuristic'), args['project_root'])
        calls.append((cmd, kw, obj, result))
        return object()  # The observer must never read the returned answer.
    monkeypatch.setattr(s.subprocess, 'run', bridge)
    assert s.observe(**args) is None
    assert len(calls) == 1
    cmd, kw, obj, result = calls[0]
    bundled = ROOT / 'bin' / 'clavain-cli'
    expected = str(bundled) if bundled.is_file() and os.access(bundled, os.X_OK) else 'clavain-cli'
    assert cmd == [expected, 'decide', '--plugin-root', str(ROOT),
                   '--config', str(args['config']), '--project-root', str(args['project_root'])]
    assert 0 < kw['timeout'] <= 6
    assert kw['stdout'] == kw['stderr'] == subprocess.DEVNULL
    assert obj['question']['id'] == 'route'
    assert [c['id'] for c in obj['question']['candidates']] == choices
    assert obj['egress_allowed'] is False and obj['sources'] == []
    assert all(type(v) is int or (type(v) is str and (v == site or len(v) == 64))
               for v in obj['state'].values())
    assert result['choice'] == choices[0] and result['fallback'] is True
    raw = next((args['project_root'] / '.clavain/decisions').glob('*.jsonl')).read_text()
    record = json.loads(raw)
    assert record['native_choice'] == record['decide_answer']['choice'] == sha(choices[0])
    assert record['site_sha256'] == sha(site)
    assert record['subject_sha256'] == sha('private bead')
    assert record['estimated_claude_tokens_saved'] == 2  # ceil(17 / (4*3))
    assert record['observed_claude_tokens_saved'] == 0
    assert record['estimate_method'] == 1
    assert record['confidence'] == 1
    for secret in ['private bead', site, choices[0], 'native classification text', 'state']:
        assert secret not in raw


@pytest.mark.parametrize('error', [OSError(), subprocess.TimeoutExpired('decide', 6)])
def test_failure_is_silent(setup, monkeypatch, capsys, error):
    s, args = setup
    def fail(*a, **kw):
        raise error
    monkeypatch.setattr(s.subprocess, 'run', fail)
    assert s.observe(**args) is None
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('field,value', [('site_sha256', 'text'), ('subject_sha256', 'a'*63),
    ('input_bytes', True), ('output_bytes', -1), ('batch_size', 0),
    ('estimate_method', 2), ('estimated_claude_tokens_saved', 999),
    ('observed_claude_tokens_saved', 1), ('extra', 'native text'),
    ('output_bytes', 1.5), ('input_bytes', 10**10), ('site_sha256', 'A'*64)])
def test_s1_rejects_invalid_opt_in_metadata(setup, monkeypatch, field, value):
    from clavain_selector.decide import decide
    s, args = setup
    results = []
    def bridge(cmd, **kw):
        obj = json.loads(kw['input'])
        obj['observation_metadata'][field] = value
        results.append(decide(obj, dict(mode='shadow', backend='heuristic'), args['project_root']))
    monkeypatch.setattr(s.subprocess, 'run', bridge)
    s.observe(**args)
    assert len(results) == 1 and results[0]['reason'] == 'invalid_input'
    assert not (args['project_root'] / '.clavain').exists()


def test_s1_refuses_backend_change_after_preflight(setup, monkeypatch):
    from clavain_selector import decide as d
    s, args = setup
    results = []
    monkeypatch.setattr(d.credentials, 'load', lambda: pytest.fail('credential access'))
    def bridge(cmd, **kw):
        results.append(d.decide(json.loads(kw['input']), dict(mode='shadow', backend='jev'),
                                args['project_root']))
    monkeypatch.setattr(s.subprocess, 'run', bridge)
    s.observe(**args)
    assert len(results) == 1 and results[0]['reason'] == 'unsupported_backend'
    assert not (args['project_root'] / '.clavain').exists()


def test_cli_invalid_arguments_silent(setup, monkeypatch, capsys):
    s, _ = setup
    monkeypatch.setattr('sys.argv', ['route_shadow.py', '--unknown'])
    s.main()
    assert capsys.readouterr() == ('', '')


def test_command_wiring_preserves_native_paths():
    route = (ROOT / 'commands/route.md').read_text()
    sprint = (ROOT / 'commands/sprint.md').read_text()
    for site, text in [('route-4b', route), ('route-staleness', route),
                       ('route-sweep', route), ('sprint-lane-intent', sprint)]:
        assert text.count('--site ' + site + ' ') == 1
    assert route.count('</dev/null >/dev/null 2>&1 &') == 3
    assert sprint.count('</dev/null >/dev/null 2>&1 &') == 1
    assert 'Parse fails→default `/sprint`.' in route
    assert 'Haiku agent (foreground)' in route
    assert 'single background haiku batch-check. Wait 5s max.' in route
    assert 'Use a haiku agent (foreground, ~500 tokens)' in sprint
    assert 'If no lane intent or `contradicts == false`: proceed silently to Step 5.' in sprint


def test_instruction_eligibility_and_drop_late_constraints():
    route = (ROOT / 'commands/route.md').read_text()
    sprint = (ROOT / 'commands/sprint.md').read_text()
    gate = route[route.index('**S2 measurement'):route.index('**token-attribution')]
    for needle in ['Before any measurement', 'exactly `shadow`', '`heuristic`',
                   'CLAVAIN_SELECTOR', 'silently do nothing', 'already in hand',
                   'heredoc', 'never guess']:
        assert needle in gate
    assert route.count('S2 eligibility and measurement pattern') == 3
    sweep = route[route.index('3. **Staleness sweep'):]
    sweep = sweep[:sweep.index('keep the native background sweep')]
    assert 'within the existing 5s wait' in sweep
    assert 'drop late results and cache hits' in sweep
    assert 'completion handler' not in sweep and 'including results arriving after' not in sweep
    assert 'S2 eligibility and measurement pattern' in sprint
    assert 'exactly `shadow`' in sprint and 'heredocs' in sprint
    doc = (ROOT / 'docs/reference/route-shadow.md').read_text()
    assert 'bin/clavain-cli' in doc and 'no fallback' in doc
    assert 'not evidence' in doc
