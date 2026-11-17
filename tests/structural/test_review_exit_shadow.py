"""Review exit observations never authorize skipping a round."""
import hashlib
import sys
from pathlib import Path

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
