"""S1 decisions never change the native answer."""
import io
import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))


def request():
    return dict(question=dict(id='route', text='Choose a route', candidates=[
        dict(id='plan', description='Plan work'), dict(id='build', description='Build work')]),
        state={}, native_choice='plan', egress_allowed=False)


@pytest.mark.parametrize('track', ['flux_triage', 'route', 'review_exit', 'learned_router'])
def test_shipped_shadow_is_log_only_and_kill_switch_is_inert(track, tmp_path, monkeypatch):
    import yaml
    from clavain_selector import decide as d
    policy = yaml.safe_load((Path(__file__).resolve().parents[2] /
                             'config/routing.yaml').read_text())['decision_models'][track]
    monkeypatch.delenv('CLAVAIN_SELECTOR', raising=False)
    monkeypatch.setattr(d.egress, 'admit', lambda *a, **kw: pytest.fail('egress ran'))
    monkeypatch.setattr(d.credentials, 'load', lambda: pytest.fail('credentials read'))
    obj = request()
    obj['question']['id'] = track
    (tmp_path / 'enabled').mkdir()
    answer = d.decide(obj, policy, tmp_path / 'enabled')
    assert answer['choice'] == obj['native_choice'] and answer['fallback'] is True
    assert answer['reason'] == 'shadow_mode'
    assert len(list((tmp_path / 'enabled/.clavain/decisions').glob('*.jsonl'))) == 1
    monkeypatch.setenv('CLAVAIN_SELECTOR', ' OFF ')
    answer = d.decide(obj, policy, tmp_path / 'disabled')
    assert answer['choice'] == obj['native_choice'] and answer['reason'] == 'off'
    assert not (tmp_path / 'disabled/.clavain').exists()


def test_shadow_heuristic_and_log(tmp_path):
    from clavain_selector.decide import decide
    result = decide(request(), dict(mode='shadow', backend='heuristic'), tmp_path)
    assert result['choice'] == 'plan'
    assert result['fallback'] is True
    assert result['band'] == 'accept'
    assert result['confidence'] == 1
    paths = list((tmp_path / '.clavain/decisions').glob('*.jsonl'))
    record = json.loads(paths[0].read_text())
    import hashlib
    assert record['native_choice'] == record['decide_answer']['choice'] == hashlib.sha256(b'plan').hexdigest()
    assert record['observed_outcome'] is None
    assert record['jev_usage_accounting']['attempts'] == 0


def test_off_and_enforce_do_not_call_or_log(tmp_path):
    from clavain_selector.decide import decide
    for mode, reason in [('off', 'off'), ('enforce', 'enforce_disabled')]:
        result = decide(request(), dict(mode=mode, backend='jev'), tmp_path)
        assert result['fallback'] and result['reason'] == reason
    assert not (tmp_path / '.clavain').exists()


def test_private_state_refused_before_credentials(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    monkeypatch.setattr(d.credentials, 'load', lambda: (_ for _ in ()).throw(AssertionError('credentials read')))
    result = d.decide(request(), dict(mode='shadow', backend='jev'), tmp_path)
    assert result['reason'] == 'egress_not_authorized'


def test_confidence_bands():
    from clavain_selector.decide import band
    assert [band(v) for v in [.59, .6, .79, .8]] == ['escalate', 'review', 'review', 'accept']


def test_invalid_native_and_unsupported_backend(tmp_path):
    from clavain_selector.decide import decide
    obj = request()
    obj['native_choice'] = 'unknown'
    assert decide(obj, dict(mode='shadow', backend='heuristic'), tmp_path)['reason'] == 'invalid_input'
    assert decide(request(), dict(mode='shadow', backend='clef'), tmp_path)['reason'] == 'unsupported_backend'


@pytest.mark.parametrize('confidence,choice,expected', [(.9, 'build', 'shadow_mode'),
    (.8, 'build', 'shadow_mode'), (.6, 'build', 'low_confidence'),
    (.59, 'build', 'low_confidence'), (.95, 'escalate', 'jev_escalated')])
def test_jev_bands_and_abstention(tmp_path, monkeypatch, confidence, choice, expected):
    from clavain_selector import decide as d
    monkeypatch.setenv('CLAVAIN_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(d.flags, 'load_registry', lambda _: {'integrations': {'decision_models': {'enabled': True, 'daily_budget': 8}}})
    monkeypatch.setattr(d.egress, 'project_owner', lambda _: 'mistakeknot')
    monkeypatch.setattr(d.credentials, 'load', lambda: d.credentials.SecretStr('synthetic-key'))
    class Client:
        def __init__(self, key): pass
        def call(self, call, *, log):
            assert d.egress.verify(call.admitted)
            answer = d.j.ChoiceAnswer(choice, confidence, tuple((c, .9 if c == choice else .05) for c in ('plan', 'build', 'escalate')))
            return d.j.JevOk(d.j.JevResponse(d.j.PINNED_MODEL, answer, (), d.j.Usage(20, 3)), 1, 200, 10)
    monkeypatch.setattr(d.j, 'JevClient', Client)
    obj = request()
    obj['egress_allowed'] = True
    result = d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)
    assert result['fallback'] and result['reason'] == expected
    assert result['choice'] == 'plan'
    assert result['shadow_choice'] == choice
    assert result['confidence'] == confidence


def test_secret_state_never_reaches_client_or_log(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    monkeypatch.setattr(d.egress, 'project_owner', lambda _: 'mistakeknot')
    monkeypatch.setattr(d.credentials, 'load', lambda: pytest.fail('loaded credential'))
    obj = request()
    secret = 'sk-' + 'a' * 48
    obj.update(egress_allowed=True, state={'token': secret})
    result = d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)
    assert result['reason'] == 'egress_refused'
    assert secret not in next((tmp_path / '.clavain/decisions').glob('*.jsonl')).read_text()


def test_provider_timeout_keeps_native(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    monkeypatch.setenv('CLAVAIN_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(d.flags, 'load_registry', lambda _: {'integrations': {'decision_models': {'enabled': True, 'daily_budget': 8}}})
    monkeypatch.setattr(d.egress, 'project_owner', lambda _: 'mistakeknot')
    monkeypatch.setattr(d.credentials, 'load', lambda: d.credentials.SecretStr('synthetic-key'))
    class Client:
        def __init__(self, key): pass
        def call(self, call, *, log):
            return d.j.JevFailure(d.contract.FallbackReason.TIMEOUT, d.j.FailureDetail.DEADLINE, 0, None, 1)
    monkeypatch.setattr(d.j, 'JevClient', Client)
    obj = request()
    obj['egress_allowed'] = True
    result = d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)
    assert result['fallback'] and result['choice'] == 'plan' and result['reason'] == 'timeout'


def test_global_kill_is_inert(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    monkeypatch.setenv('CLAVAIN_SELECTOR', ' OFF ')
    monkeypatch.setattr(d.egress, 'admit', lambda *a, **kw: pytest.fail('egress ran'))
    assert d.decide(request(), dict(mode='shadow', backend='jev'), tmp_path)['reason'] == 'off'
    assert not (tmp_path / '.clavain').exists()


@pytest.mark.parametrize('link_component', ['.clavain', 'decisions', 'dayfile'])
def test_log_symlink_refused(tmp_path, link_component):
    import datetime
    from clavain_selector.decide import decide
    root, outside = tmp_path / 'project', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir(mode=0o755)
    if link_component == '.clavain':
        (root / '.clavain').symlink_to(outside, target_is_directory=True)
    else:
        (root / '.clavain').mkdir()
        if link_component == 'decisions':
            (root / '.clavain/decisions').symlink_to(outside, target_is_directory=True)
        else:
            (root / '.clavain/decisions').mkdir()
            (root / '.clavain/decisions' / (datetime.datetime.now(datetime.timezone.utc).date().isoformat()+'.jsonl')).symlink_to(outside / 'data')
    assert decide(request(), dict(mode='shadow', backend='heuristic'), root)['reason'] == 'record_unwritable'
    assert outside.stat().st_mode & 0o777 == 0o755
    assert list(outside.iterdir()) == []


def test_daily_budget_ignores_caller_session(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    monkeypatch.setenv('CLAVAIN_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(d.egress, 'project_owner', lambda _: 'mistakeknot')
    monkeypatch.setattr(d.flags, 'load_registry', lambda _: {'integrations': {'decision_models': {'enabled': True, 'daily_budget': 1}}})
    monkeypatch.setattr(d.credentials, 'load', lambda: (_ for _ in ()).throw(d.credentials.CredentialUnavailable()))
    obj = request()
    obj.update(egress_allowed=True, session_id='first')
    assert d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)['reason'] == 'credential_unavailable'
    obj['session_id'] = 'second'
    assert d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)['reason'] == 'budget_exhausted'


def test_registry_disabled_stops_jev(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    monkeypatch.setattr(d.egress, 'project_owner', lambda _: 'mistakeknot')
    monkeypatch.setattr(d.flags, 'load_registry', lambda _: {'integrations': {'decision_models': {'enabled': False, 'daily_budget': 8}}})
    monkeypatch.setattr(d.credentials, 'load', lambda: pytest.fail('disabled provider loaded credentials'))
    obj = request()
    obj['egress_allowed'] = True
    assert d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)['reason'] == 'registry_disabled'
