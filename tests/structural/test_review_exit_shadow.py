"""Review exit observations never authorize skipping a round."""
import hashlib
import sys
from pathlib import Path
import json
import os
import subprocess
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))


def test_later_rounds_and_unknown_usage():
    from review_exit_shadow import outcome
    later = [dict(findings=0, claude_tokens=120), dict(findings=0, claude_tokens=None)]
    assert outcome(later) == dict(later_findings=0, could_exit=True,
        estimated_claude_tokens_saved=120, token_estimate_complete=False)
    assert outcome([dict(findings=2, claude_tokens=90)])['could_exit'] is False
    assert outcome([dict(findings=None, claude_tokens=90)])['could_exit'] is None
    assert outcome([])['could_exit'] is None
    assert outcome([dict(findings=1, claude_tokens=2),
                    dict(findings=None, claude_tokens=None)])['could_exit'] is False


def test_off_is_inert(tmp_path):
    from review_exit_shadow import observe
    root = tmp_path / 'plugin'
    (root / 'config').mkdir(parents=True)
    (root / 'config/routing.yaml').write_text('decision_models:\n  review_exit: {mode: off}\n')
    observe(root, tmp_path, 'private loop', 'continue', 0, 20)
    assert not (tmp_path / '.clavain').exists()


def test_timeout_and_wiring(monkeypatch, tmp_path):
    import review_exit_shadow as r
    import subprocess
    def run(*args, **kwargs):
        assert kwargs['timeout'] == 6
        raise subprocess.TimeoutExpired('decide', 6)
    monkeypatch.setattr(r.subprocess, 'run', run)
    import pytest
    with pytest.raises(subprocess.TimeoutExpired):
        r.call_decide({}, tmp_path, tmp_path)
    root = Path(__file__).resolve().parents[2]
    shell = (root / 'scripts/review-round.sh').read_text()
    assert 'review_exit_shadow.py' in shell
    assert '</dev/null >/dev/null 2>&1 & ) || true' in shell
    assert 'review_exit_shadow.py' in (root / 'commands/quality-gates.md').read_text()


def test_shadow_join_and_privacy(tmp_path, monkeypatch):
    import review_exit_shadow as r
    from clavain_selector import records
    root = tmp_path / 'plugin'
    (root / 'config').mkdir(parents=True)
    (root / 'config/routing.yaml').write_text('decision_models:\n  review_exit: {mode: shadow, backend: heuristic}\n')
    def call(request, *args):
        from clavain_selector.decide import decide
        return decide(request, dict(mode='shadow', backend='heuristic'), tmp_path)
    monkeypatch.setattr(r, 'call_decide', call)
    r.observe(root, tmp_path, 'private loop', 'continue', 1, 90)
    r.observe(root, tmp_path, 'private loop', 'exit', 0, 130)
    rows = records.read_records(record_dir=tmp_path / '.clavain/decisions')
    observations = [x for x in rows if x.get('schema') == 'review-exit-observation-v1']
    assert len(observations) == 2
    assert observations[0]['native_agreement'] is True
    outcomes = [x for x in rows if x.get('schema') == 'review-exit-outcome-v1']
    assert outcomes[-1]['decision_id'] == observations[0]['decision_id']
    assert outcomes[-1]['could_exit'] is True
    assert outcomes[-1]['estimated_claude_tokens_saved'] == 130
    assert 'private loop' not in str(rows)
    assert observations[0]['loop_hash'] == hashlib.sha256(b'private loop').hexdigest()


@pytest.fixture
def main_runner(tmp_path, monkeypatch):
    import review_exit_shadow as r
    from clavain_selector.decide import decide
    root = tmp_path / 'plugin'
    (root / 'config').mkdir(parents=True)
    (root / 'scripts').mkdir()
    config = root / 'config/routing.yaml'
    config.write_text('decision_models:\n  review_exit: {mode: shadow, backend: heuristic}\n')
    monkeypatch.setattr(r, '__file__', str(root / 'scripts/review_exit_shadow.py'))
    monkeypatch.delenv('CLAVAIN_SELECTOR', raising=False)
    monkeypatch.setattr(r, 'call_decide', lambda req, plugin, project:
        decide(req, dict(mode='shadow', backend='heuristic'), project))
    project = tmp_path / 'source'
    project.mkdir()
    def run(*extra):
        monkeypatch.setattr(sys, 'argv', ['review_exit_shadow.py', '--project', str(project),
            '--loop', 'change', '--native', 'exit', *map(str, extra)])
        r.main()
        from clavain_selector.records import read_records
        return [x for x in read_records(record_dir=project / '.clavain/decisions')
                if x.get('schema') == 'review-exit-observation-v1']
    return run, config, project


@pytest.mark.parametrize('count,expected', [(0, 0), (2, 2), ('0', None),
    (True, None), (-1, None), (None, None), ([], None)])
def test_main_only_counts_explicit_current_run_files(main_runner, tmp_path, count, expected):
    run, _, _ = main_runner
    stale = tmp_path / 'stale.json'
    stale.write_text(json.dumps(dict(findings_count=99)))
    current = tmp_path / 'current.json'
    current.write_text(json.dumps(dict(findings_count=count)))
    row = run('--verdict-file', current)[0]
    assert row['findings'] == expected
    assert row['claude_tokens'] == (len(current.read_bytes()) + 3) // 4


def test_main_empty_manifest_is_unknown(main_runner):
    run, _, _ = main_runner
    row = run()[0]
    assert row['findings'] is None and row['claude_tokens'] is None


def test_main_missing_findings_is_unknown_and_duplicate_paths_count_once(main_runner, tmp_path):
    run, _, _ = main_runner
    current = tmp_path / 'current.json'
    current.write_text('{}')
    row = run('--verdict-file', current, '--verdict-file', current)[0]
    assert row['findings'] is None
    assert row['claude_tokens'] == 1


@pytest.mark.parametrize('mode', ['off', 'enforce', 'invalid'])
def test_main_disabled_skips_even_unreadable_files(main_runner, mode, tmp_path):
    run, config, project = main_runner
    config.write_text(f'decision_models:\n  review_exit: {{mode: {mode}}}\n')
    assert run('--verdict-file', tmp_path / 'missing.json') == []
    assert not (project / '.clavain').exists()


@pytest.mark.parametrize('verdict,expected', [('PASS', 0), ('PASS WITH NOTES', None)])
def test_main_panel_verdict(main_runner, tmp_path, verdict, expected):
    run, _, _ = main_runner
    panel = tmp_path / 'panel'
    panel.mkdir()
    (panel / 'receipt.md').write_text(f'VERDICT: {verdict}\n')
    assert run('--panel', panel)[0]['findings'] == expected


@pytest.mark.parametrize('dispatch_rc,expected_rc', [(0, 0), (7, 3)])
def test_real_round_keeps_exit_and_persists_in_source(tmp_path, dispatch_rc, expected_rc):
    """Real worktrees and cleanup, fake reviewer, real observer main/heuristic."""
    import shutil
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    plugin = tmp_path / 'plugin'
    (plugin / 'scripts').mkdir(parents=True)
    (plugin / 'config').mkdir()
    (plugin / 'config/routing.yaml').write_text(
        'decision_models:\n  review_exit: {mode: shadow, backend: heuristic}\n')
    shutil.copyfile(scripts / 'review-round.sh', plugin / 'scripts/review-round.sh')
    # Run the actual main with a local heuristic bridge instead of a provider.
    (plugin / 'scripts/review_exit_shadow.py').write_text(
        'import sys, time\n'
        'from pathlib import Path\n'
        f'sys.path.insert(0, {str(scripts)!r})\n'
        'import review_exit_shadow as r\n'
        'from clavain_selector.decide import decide\n'
        'r.__file__ = __file__\n'
        'r.call_decide = lambda req, root, project: decide(req, '
        '{"mode":"shadow", "backend":"heuristic"}, project)\n'
        'release = Path(sys.argv[sys.argv.index("--panel")+1]) / "observer.release"\n'
        'deadline = time.monotonic() + 5\n'
        'while not release.exists():\n'
        '    if time.monotonic() > deadline: raise RuntimeError("callback was awaited")\n'
        '    time.sleep(.01)\n'
        'r.main()\n')
    source = tmp_path / 'source'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    source.mkdir()
    git('init', '-q', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    (source / 'file').write_text('fixture')
    git('add', 'file')
    git('commit', '-qm', 'fixture')
    head = git('rev-parse', 'HEAD')
    dispatch = tmp_path / 'dispatch'
    dispatch.write_text('#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n'
        f'rc={dispatch_rc}\n'
        'p=Path(sys.argv[sys.argv.index("-o")+1])\n'
        'p.write_text("ok\\nVERDICT: PASS\\n")\n'
        'Path(str(p)+".verdict").write_text("STATUS: pass\\n")\n'
        'sys.exit(rc)\n')
    dispatch.chmod(0o755)
    env = dict(os.environ, REVIEW_ROUND_DISPATCH=str(dispatch))
    for key in ['CLAVAIN_BEAD_ID', 'REVIEW_EXIT_LOOP_ID', 'CLAVAIN_SELECTOR']:
        env.pop(key, None)
    from clavain_selector.records import read_records
    for number in [1, 2]:
        out = tmp_path / f'round-{number}'
        proc = subprocess.run(['bash', str(plugin / 'scripts/review-round.sh'),
            '--repo', str(source), '--base', 'main', '--head', head,
            '--producer-identity', 'fixture', '--out-dir', str(out)],
            capture_output=True, text=True, env=env, timeout=5)
        assert proc.returncode == expected_rc, proc.stderr
        assert not (out / 'wt').exists()
        # Callback cannot finish until released after the native command exits.
        (out / 'observer.release').write_text('release')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = read_records(record_dir=source / '.clavain/decisions')
            observations = [r for r in rows if r.get('schema') == 'review-exit-observation-v1']
            if len(observations) == number:
                break
            time.sleep(.02)
        assert len(observations) == number
        assert observations[-1]['loop_hash'] == hashlib.sha256(f'{source}:main'.encode()).hexdigest()
        assert observations[-1]['shadow_exit'] is (expected_rc == 0)
