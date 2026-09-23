"""Real ic policy resolution, synthetic pool and model CLIs, immutable receipts."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_pool_headroom import account

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.requires_ic


@pytest.fixture
def dispatch(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    subprocess.run(['git', '-C', str(work), '-c', 'user.name=Fixture', '-c',
                    'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)
    bins = tmp_path / 'bin'
    bins.mkdir()
    real_ic = shutil.which('ic')
    scripts = {
        'ic': f'''#!/usr/bin/env python3
import os, sys
from pathlib import Path
if sys.argv[1:3] == ['route', 'record']:
    with Path(os.environ['RECEIPTS']).open('a') as f:
        f.write(next(a.split('=',1)[1] for a in sys.argv if a.startswith('--context='))+'\\n')
    sys.exit(0)
if sum(a.startswith('--context-file=') for a in sys.argv) > 1:
    sys.exit('duplicate context flag')
os.execv({real_ic!r}, [{real_ic!r}, *sys.argv[1:]])
''',
        'bb': '''#!/usr/bin/env python3
import os,sys
from pathlib import Path
if sys.argv[1:] != ['pool','status','--json']: sys.exit(1)
with Path(os.environ['POOL_CALLS']).open('a') as f: f.write('status\\n')
print(os.environ['POOL_FIXTURE'])
''',
        'codex': '''#!/usr/bin/env python3
import sys
from pathlib import Path
if '--version' in sys.argv: print('codex-cli 0.153.3'); sys.exit(0)
if '-o' in sys.argv: Path(sys.argv[sys.argv.index('-o')+1]).write_text('VERDICT: CLEAN')
print('{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}')
''',
        'claude': '''#!/usr/bin/env python3
import sys
sys.stdin.read()
print('{"type":"result","subtype":"success","is_error":false,"result":"VERDICT: CLEAN"}')
''',
    }
    for name, source in scripts.items():
        (bins / name).write_text(source)
        (bins / name).chmod(0o755)
    receipt = tmp_path / 'receipts'
    calls = tmp_path / 'calls'
    context = tmp_path / 'context.json'
    def run(accounts, role='routine-execution', available=None, disabled=False, broken_probe=False, bsd_temp=False):
        if broken_probe:
            (bins/'python3').write_text('#!/bin/sh\ncase "$1" in */pool-headroom.py) exit 70 ;; esac\nexec '+shutil.which('python3')+' "$@"\n')
            (bins/'python3').chmod(0o755)
        if bsd_temp:
            (bins/'mktemp').write_text('#!/bin/sh\ncase "$*" in *XXXXXX-*) exit 2 ;; esac\nexec '+shutil.which('mktemp')+' "$@"\n')
            (bins/'mktemp').chmod(0o755)
        ctx = {'reasons': [], 'rationale': 'fixture'}
        if available is not None:
            ctx['available_models'] = available
        context.write_text(json.dumps(ctx))
        receipt.write_text('')
        calls.write_text('')
        env = dict(os.environ, PATH=str(bins)+':'+os.environ['PATH'], BB_CLI=str(bins/'bb'),
                   POOL_FIXTURE=json.dumps({'accounts': accounts}), POOL_CALLS=str(calls),
                   RECEIPTS=str(receipt), CLAVAIN_CONTEXT_GATEWAY_MODE='off',
                   CLAVAIN_BB_DIRECT_POOL='0', CLAVAIN_POOL_HEADROOM='0' if disabled else '1',
                   CLAVAIN_REQUIRE_USAGE='0')
        args = ['bash', str(ROOT/'scripts/dispatch.sh'), '--role', role, '--context-file', str(context),
                '-C', str(work), '-o', str(tmp_path/'out')]
        if role in ('plan-review', 'validation', 'cross-lab-review'):
            args += ['--producer-identity', 'gpt-6-astra']
        p = subprocess.run(args+['fixture only'], env=env, text=True, capture_output=True, timeout=20)
        rows = [json.loads(line) for line in receipt.read_text().splitlines()]
        return p, rows, calls.read_text(), work
    return run


def test_execution_reorders_and_receipt_preserves_ic_profile(dispatch):
    p, rows, calls, _ = dispatch([account('codex', .8), account('claude', .2)])
    assert p.returncode == 0, p.stderr
    assert calls == 'status\n'
    r = rows[-1]
    assert r['execution']['model'] == 'claude-sonnet-5'
    assert r['profile_ref'] == r['resolved_route']['profile_ref'] == 'routine-sol'
    assert r['resolved_profile']['profile_ref'] == 'routine-sonnet'
    assert r['headroom_reorder']['to'][0] == 'routine-sonnet'


def test_forecast_exclusion_has_evidence_and_separate_label(dispatch):
    p, rows, _, work = dispatch([account('codex', .99), account('claude', .2)])
    assert p.returncode == 0, p.stderr
    r = rows[-1]
    assert r['execution']['model'] == 'claude-sonnet-5'
    assert r['headroom_exclusion'] == ['gpt-5.6-sol']
    assert r['resolved_route']['headroom_exclusion'] == ['gpt-5.6-sol']
    assert not any(e['reason'] == 'model_unavailable' for e in r['resolved_route'].get('excluded', []))
    ctx = r['resolved_route']['decision_context']
    assert 'forecast from bb pool headroom' in ctx['rationale']
    assert 'Observed capacity failure' not in ctx['rationale']
    evidence = list((work/'.clavain/capacity').glob('*-headroom.json'))
    assert len(evidence) == 1 and json.loads(evidence[0].read_text())['status'] == 'known'


@pytest.mark.parametrize('role', ['plan-review', 'validation', 'escalation', 'planning', 'cross-lab-review'])
def test_protected_resolution_never_probes_pool(dispatch, role):
    accounts = [account('codex', .1), account('claude', .99, familyWeekly={'fable': {'utilization': 1}})]
    p, baseline, _, _ = dispatch(accounts, role, disabled=True)
    assert p.returncode == 0, p.stderr
    p, rows, calls, _ = dispatch(accounts, role)
    assert p.returncode == 0, p.stderr
    assert calls == ''
    assert rows[-1]['resolved_route'] == baseline[-1]['resolved_route']
    assert rows[-1]['resolved_profile'] == baseline[-1]['resolved_profile']


def test_unknown_pool_does_not_change_execution(dispatch):
    p, rows, _, work = dispatch([])
    assert p.returncode == 0, p.stderr
    assert rows[-1]['execution']['model'] == 'gpt-5.6-sol'
    assert rows[-1].get('headroom_exclusion', []) == []
    assert not list(work.glob('.clavain/capacity/*'))


def test_forecast_does_not_resurrect_previously_unavailable_models(dispatch):
    p, rows, _, _ = dispatch([account('codex', .99), account('claude', .2)],
                            available=['gpt-5.6-sol'])
    assert p.returncode != 0
    assert not rows  # No eligible seat remains; never invoke Claude.


def test_probe_wrapper_failure_leaves_route_unchanged(dispatch):
    p, rows, _, _ = dispatch([], broken_probe=True)
    assert p.returncode == 0, p.stderr
    assert rows[-1]['execution']['model'] == 'gpt-5.6-sol'


def test_evidence_creation_is_portable(dispatch):
    p, rows, _, _ = dispatch([account('codex', .99), account('claude', .2)], bsd_temp=True)
    assert p.returncode == 0, p.stderr
    assert rows[-1]['headroom_exclusion'] == ['gpt-5.6-sol']
