"""Hosted observers admit only a closed projection; the client is always stubbed."""
import hashlib
import json
from pathlib import Path

import pytest

CONTRACT = 'shadow-observer-v1'
POLICY = dict(mode='shadow', backend='jev', privacy_contract=CONTRACT)


def route():
    return dict(privacy_contract=CONTRACT, question=dict(id='route',
        text='Observe native classification', candidates=[dict(id=c, description=c) for c in ('sprint', 'work')]),
        state=dict(site_id='route-4b', subject_sha256='a'*64, input_bytes=11,
                   output_bytes=6, batch_size=1), native_choice='work', egress_allowed=True, sources=[])


def review():
    return dict(privacy_contract=CONTRACT, question=dict(id='review_exit',
        text='Could this review round have exited early?', candidates=[
            dict(id='exit', description='Exit the review loop'),
            dict(id='continue', description='Continue reviewing')]),
        state=dict(findings=2, loop_hash='b'*64), native_choice='continue', egress_allowed=True, sources=[])


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    from clavain_selector import decide as d
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git/config').write_text('[core]\n')
    monkeypatch.delenv('CLAVAIN_SELECTOR', raising=False)
    monkeypatch.setenv('CLAVAIN_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(d.flags, 'load_registry', lambda _: {'integrations': {'decision_models': {'enabled': True, 'daily_budget': 8}}})
    monkeypatch.setattr(d.egress, 'project_owner', lambda _: 'mistakeknot')
    monkeypatch.setattr(d.credentials, 'load', lambda: d.credentials.SecretStr('synthetic-key'))
    calls = []
    class Client:
        def __init__(self, key): pass
        def call(self, call, *, log):
            assert d.egress.verify(call.admitted)
            body = json.loads(call.admitted.body)
            wire = json.loads(call.wire_body())
            assert set(wire) == {'model', 'state', 'questions'}
            assert set(wire['state']) == {'schema', 'point', 'task', 'context', 'candidates'}
            assert wire['state']['context'] == body['context']
            assert wire['state']['task'] == body['task']
            assert wire['state']['candidates'] == body['candidates']
            assert set(wire['questions']) == {'select'}
            calls.append(body)
            entry = log.begin(1)
            log.progress(entry, 'response_read')
            log.finalize(entry, dict(status=200, data=b'{"usage":{"input_tokens":20,"output_tokens":3}}'))
            choices = [c['id'] for c in body['candidates']]
            selected = 'sprint' if 'sprint' in choices else 'exit'
            answer = d.j.ChoiceAnswer(selected, .9, tuple((c, float(c == selected)) for c in choices))
            return d.j.JevOk(d.j.JevResponse(d.j.PINNED_MODEL, answer, (), d.j.Usage(20, 3)), 1, 200, 10)
    monkeypatch.setattr(d.j, 'JevClient', Client)
    return d, calls


@pytest.mark.parametrize('factory', [route, review])
def test_allowlist_and_native_authority(hosted, tmp_path, factory):
    d, calls = hosted
    obj = factory()
    result = d.decide(obj, POLICY, tmp_path)
    assert len(calls) == 1
    assert result['reason'] == 'shadow_mode'
    assert result['choice'] == obj['native_choice'] and result['fallback']
    assert result['shadow_choice'] != obj['native_choice']
    assert result['confidence'] == .9
    state = json.loads(calls[0]['context'])
    for key, value in obj['state'].items():
        if key not in ('subject_sha256', 'loop_hash'):
            assert state[key] == value
        else:
            assert len(state[key]) == 64 and state[key] != value
    assert 'native_choice' not in calls[0]
    assert result['jev_usage_accounting']['known_total'] == dict(input_tokens=20, output_tokens=3)
    row = json.loads(next((tmp_path / '.clavain/decisions').glob('*.jsonl')).read_text())
    assert row['cost'] is None  # unknown money is never represented as zero
    assert row['privacy_contract'] == CONTRACT
    assert 'context' not in row and 'state' not in row


@pytest.mark.parametrize('mutation', [
    lambda o: o['state'].update(prompt='private text'),
    lambda o: o['state'].update(input_bytes=True),
    lambda o: o['state'].update(input_bytes=10**9+1),
    lambda o: o['state'].update(subject_sha256='/home/private/file'),
    lambda o: o['question'].update(text='private prompt'),
    lambda o: o['question']['candidates'][0].update(description='private file contents'),
    lambda o: o['question']['candidates'][0].update(payload='private'),
    lambda o: o.update(sources=['/home/private/file']),
    lambda o: o.update(prompt='private'),
    lambda o: o.update(privacy_contract='unknown'),
])
def test_forbidden_fields_rejected_before_admission(hosted, tmp_path, monkeypatch, mutation):
    d, calls = hosted
    monkeypatch.setattr(d.egress, 'admit', lambda *a, **kw: pytest.fail('admission before allowlist'))
    obj = route()
    mutation(obj)
    result = d.decide(obj, POLICY, tmp_path)
    assert result['reason'] == 'invalid_input'
    assert not calls


@pytest.mark.parametrize('factory', [route, review])
def test_shared_eight_call_budget(hosted, tmp_path, factory):
    d, calls = hosted
    for _ in range(8):
        assert d.decide(factory(), POLICY, tmp_path)['reason'] == 'shadow_mode'
    result = d.decide(review() if factory is route else route(), POLICY, tmp_path)
    assert result['reason'] == 'budget_exhausted' and result['choice'] == ('continue' if factory is route else 'work')
    assert len(calls) == 8


def test_breaker_falls_back_native(hosted, tmp_path):
    d, calls = hosted
    failure = d.j.JevFailure(d.contract.FallbackReason.TIMEOUT, d.j.FailureDetail.DEADLINE, 1, None, 1)
    for _ in range(3):
        d.j.Breaker().record(failure)
    result = d.decide(route(), POLICY, tmp_path)
    assert result['reason'] == 'circuit_open' and result['choice'] == 'work'
    assert not calls


def test_observer_policy_switch_is_required(hosted, tmp_path):
    d, calls = hosted
    result = d.decide(route(), dict(mode='shadow', backend='jev'), tmp_path)
    assert result['reason'] == 'egress_not_authorized' and not calls


def test_jev_route_bridge(hosted, tmp_path, monkeypatch):
    from clavain_selector import route_shadow as s
    d, calls = hosted
    config = tmp_path / 'routing.yaml'
    config.write_text('decision_models:\n  route: {mode: shadow, backend: jev, privacy_contract: shadow-observer-v1}\n')
    results = []
    def bridge(cmd, **kw):
        results.append(d.decide(json.loads(kw['input']), POLICY, tmp_path))
    monkeypatch.setattr(s.subprocess, 'run', bridge)
    s.observe(site='route-4b', native_choice='work', subject_sha256='a'*64,
              input_bytes=11, output_bytes=6, plugin_root=tmp_path, config=config, project_root=tmp_path)
    assert len(calls) == len(results) == 1
    assert results[0]['choice'] == 'work' and results[0]['shadow_choice'] == 'sprint'


def test_jev_review_bridge(hosted, tmp_path, monkeypatch):
    import review_exit_shadow as r
    d, calls = hosted
    root = tmp_path / 'plugin'
    (root / 'config').mkdir(parents=True)
    (root / 'config/routing.yaml').write_text('decision_models:\n  review_exit: {mode: shadow, backend: jev, privacy_contract: shadow-observer-v1}\n')
    monkeypatch.setattr(r, 'call_decide', lambda obj, *args: d.decide(obj, POLICY, tmp_path))
    r.observe(root, tmp_path, '/home/private/loop', 'continue', 2, 90)
    assert len(calls) == 1
    assert '/home/private' not in json.dumps(calls)
    state = json.loads(calls[0]['context'])
    assert state['findings'] == 2
    assert state['loop_hash'] != hashlib.sha256(b'/home/private/loop').hexdigest()


def test_hosted_credentials_cannot_be_redirected(hosted, tmp_path, monkeypatch):
    d, calls = hosted
    monkeypatch.setenv('CLAVAIN_JEV_SECRETS_FILE', str(tmp_path / 'outside.env'))
    monkeypatch.setattr(d.credentials, 'load', lambda: pytest.fail('outside credential loaded'))
    result = d.decide(route(), POLICY, tmp_path)
    assert result['reason'] == 'credential_unavailable' and not calls


@pytest.mark.parametrize('factory', [route, review])
def test_hosted_global_kill_is_inert(hosted, tmp_path, monkeypatch, factory):
    d, calls = hosted
    monkeypatch.setenv('CLAVAIN_SELECTOR', ' OFF ')
    assert d.decide(factory(), POLICY, tmp_path)['reason'] == 'off'
    assert not calls and not (tmp_path / '.clavain').exists()


@pytest.mark.parametrize('findings', [True, -1, 10**9+1, 'private', float('nan')])
def test_review_forbidden_values(hosted, tmp_path, findings):
    d, calls = hosted
    obj = review()
    obj['state']['findings'] = findings
    assert d.decide(obj, POLICY, tmp_path)['reason'] == 'invalid_input'
    assert not calls


@pytest.mark.parametrize('factory', [route, review])
def test_hosted_registry_disabled(hosted, tmp_path, monkeypatch, factory):
    d, calls = hosted
    monkeypatch.setattr(d.flags, 'load_registry', lambda _: {'integrations': {'decision_models': {'enabled': False, 'daily_budget': 8}}})
    result = d.decide(factory(), POLICY, tmp_path)
    assert result['reason'] == 'registry_disabled' and not calls
    assert result['choice'] == factory()['native_choice']


def test_opted_in_policy_cannot_bypass_contract_by_dropping_marker(hosted, tmp_path):
    d, calls = hosted
    obj = route()
    del obj['privacy_contract']
    obj['state']['prompt'] = 'private native prompt'
    assert d.decide(obj, POLICY, tmp_path)['reason'] == 'invalid_input'
    assert not calls


def test_budget_scope_is_shared_by_worktrees(tmp_path):
    from clavain_selector.observer_privacy import project_scope
    common = tmp_path / 'source/.git'
    common.mkdir(parents=True)
    (common / 'config').write_text('[core]\n')
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    gitdir = common / 'worktrees/checkout'
    gitdir.mkdir(parents=True)
    (gitdir / 'commondir').write_text('../..')
    (checkout / '.git').write_text('gitdir: ' + str(gitdir))
    child = checkout / 'src'
    child.mkdir()
    assert project_scope(child) == project_scope(common.parent) == common


def test_wire_ids_are_unlinkable_pseudonyms(hosted, tmp_path):
    d, calls = hosted
    for _ in range(2):
        d.decide(route(), POLICY, tmp_path)
    states = [json.loads(c['context']) for c in calls]
    assert states[0]['subject_sha256'] != states[1]['subject_sha256']
    assert all(s['subject_sha256'] != 'a'*64 for s in states)


@pytest.mark.parametrize('site,choices', [
    ('route-4b', ('sprint', 'work')),
    ('route-staleness', ('implemented', 'not_implemented')),
    ('route-sweep', ('implemented', 'not_implemented')),
    ('sprint-lane-intent', ('contradicts', 'aligned'))])
def test_each_hosted_route_site_has_only_frozen_wire_fields(hosted, tmp_path, site, choices):
    d, calls = hosted
    obj = route()
    obj['state']['site_id'] = site
    obj['question']['candidates'] = [dict(id=c, description=c) for c in choices]
    obj['native_choice'] = choices[1]
    d.decide(obj, POLICY, tmp_path)
    assert len(calls) == 1
    body = calls[0]
    assert body['task'] == 'Observe native classification'
    assert sorted(body['candidates'], key=lambda c: c['id']) == sorted(obj['question']['candidates'], key=lambda c: c['id'])
    state = json.loads(body['context'])
    assert set(state) == {'site_id', 'subject_sha256', 'input_bytes', 'output_bytes', 'batch_size'}
    assert state['site_id'] == site


@pytest.mark.parametrize('refusal', ['credential', 'egress', 'budget', 'build'])
def test_hosted_half_open_refusals_preserve_upstream_guards(hosted, tmp_path, monkeypatch, refusal):
    d, calls = hosted
    path = tmp_path / 'state/selector/breaker.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(opened_until=0, probe_pending=False)))
    # The first admission precedes the breaker; the second is loaded-key admission.
    admit = d.egress.admit
    if refusal == 'credential':
        def load():
            raise d.credentials.CredentialUnavailable()
        monkeypatch.setattr(d.credentials, 'load', load)
    elif refusal == 'egress':
        monkeypatch.setattr(d.egress, 'admit', lambda *a, **kw:
            d.egress.Refusal(('cred.loaded_key',)) if kw.get('key_literal') else admit(*a, **kw))
    elif refusal == 'build':
        monkeypatch.setattr(d.j.JevCall, 'build', lambda *a, **kw: (_ for _ in ()).throw(ValueError()))
    else:
        monkeypatch.setattr(d.j.Budget, 'consume', lambda _: d.contract.FallbackReason.BUDGET_EXHAUSTED)
    if refusal != 'budget':
        monkeypatch.setattr(d.j.Budget, 'consume', lambda _: pytest.fail('pre-call refusal spent budget'))
    result = d.decide(route(), POLICY, tmp_path)
    assert result['choice'] == 'work' and result['fallback'] and not calls
    assert result['reason'] == dict(credential='credential_unavailable', egress='egress_refused',
                                  budget='budget_exhausted', build='invalid_input')[refusal]
    assert json.loads(path.read_text())['probe_pending'] is False
    assert d.j.Breaker().check() is None


def test_hosted_shadow_log_cap_refuses_before_spend(hosted, tmp_path, monkeypatch):
    d, calls = hosted
    monkeypatch.setattr(d, 'SHADOW_LOG_MAX_BYTES', 1)
    result = d.decide(route(), POLICY, tmp_path)
    assert not calls
    assert result['choice'] == 'work' and result['fallback']
    assert result['reason'] == 'log_capacity_exhausted'
    assert sum(p.stat().st_size for p in (tmp_path / '.clavain/decisions').glob('*.jsonl')) == 0


@pytest.mark.parametrize('remaining', [0, 100])
def test_full_or_near_cap_never_spends_budget_and_keeps_consistent_state(hosted, tmp_path, monkeypatch, remaining):
    d, calls = hosted
    directory = tmp_path / '.clavain/decisions'
    directory.mkdir(parents=True)
    (directory / 'old.jsonl').write_bytes(b' ' * (d.SHADOW_LOG_MAX_BYTES - remaining))
    monkeypatch.setattr(d.j.Budget, 'consume', lambda _: pytest.fail('cap refusal spent budget'))
    result = d.decide(route(), POLICY, tmp_path)
    assert not calls
    assert result['choice'] == result['shadow_choice'] == 'work'
    assert result['reason'] == 'log_capacity_exhausted'
    assert result['confidence'] == 0 and result['probs'] == {} and result['fallback']
    assert result['band'] == 'escalate'
    assert result['jev_usage_accounting']['attempts'] == 0
    assert result['jev_usage_accounting']['known_total'] == dict(input_tokens=0, output_tokens=0)
    assert result['jev_usage_accounting']['complete'] is True


def test_admitted_call_persists_physical_usage(hosted, tmp_path):
    d, calls = hosted
    result = d.decide(route(), POLICY, tmp_path)
    assert len(calls) == 1 and result['reason'] == 'shadow_mode'
    rows = d.records.read_records(record_dir=tmp_path / '.clavain/decisions')
    row = next(r for r in rows if r['decision_id'] == result['decision_id'])
    assert row['jev_usage_accounting'] == result['jev_usage_accounting']
    assert row['attempt_records'] == result['attempt_records']
    assert row['jev_usage_accounting']['known_total'] == dict(input_tokens=20, output_tokens=3)
    assert row['attempt_records'][0]['usage_basis'] == 'reported'


def test_marked_packet_with_heuristic_policy_is_inert(hosted, tmp_path, monkeypatch):
    d, calls = hosted
    monkeypatch.setattr(d.egress, 'admit', lambda *a, **kw: pytest.fail('admission ran'))
    result = d.decide(route(), dict(POLICY, backend='heuristic'), tmp_path)
    assert result['reason'] == 'egress_not_authorized'
    assert result['choice'] == 'work' and result['fallback'] and not calls
    assert not (tmp_path / '.clavain').exists()


@pytest.mark.parametrize('extra', [0, -1])
def test_capacity_admission_exact_headroom_boundary(hosted, tmp_path, monkeypatch, extra):
    d, calls = hosted
    maximum = 2 * d.SHADOW_RECORD_HEADROOM
    monkeypatch.setattr(d, 'SHADOW_LOG_MAX_BYTES', maximum)
    directory = tmp_path / '.clavain/decisions'
    directory.mkdir(parents=True)
    (directory / 'old.jsonl').write_bytes(b' ' * (maximum - d.SHADOW_RECORD_HEADROOM - extra))
    result = d.decide(route(), POLICY, tmp_path)
    assert len(calls) == (1 if extra == 0 else 0)
    assert result['reason'] == ('shadow_mode' if extra == 0 else 'log_capacity_exhausted')
    assert sum(p.stat().st_size for p in directory.glob('*.jsonl')) <= maximum


def test_guard_shares_lock_with_public_append_and_expires(tmp_path):
    import fcntl
    import os
    import subprocess
    import sys
    import time
    from clavain_selector import records
    directory = tmp_path / '.clavain/decisions'
    marker = tmp_path / 'ready'
    script = '''import sys
from pathlib import Path
from clavain_selector import records
root=Path(sys.argv[1])
Path(sys.argv[2]).touch()
records.append_record({'decision_id':'other','created_at':'2020-01-01T00:00:00Z'},
    record_dir=root/'.clavain/decisions', project_root=root, max_bytes=4096)
'''
    with records.admit_project_record(tmp_path, max_bytes=4096, reserve_bytes=1024) as append:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        proc = subprocess.Popen([sys.executable, '-c', script, str(tmp_path), str(marker)],
            env=dict(os.environ, PYTHONPATH=str(Path(records.__file__).parents[1])))
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert marker.exists()
            with pytest.raises(subprocess.TimeoutExpired):
                proc.wait(timeout=.1)
            append(dict(decision_id='guarded', created_at='2021-01-01T00:00:00Z'))
        except BaseException:
            proc.kill()
            proc.wait()
            raise
    assert proc.wait(timeout=5) == 0
    assert {r['decision_id'] for r in records.read_records(record_dir=directory)} == {'guarded', 'other'}
    with pytest.raises(records.RecordUnwritable):
        append({})


def test_largest_supported_accounting_shape_fits_admission(hosted, tmp_path, monkeypatch):
    d, calls = hosted
    def call(self, call, *, log):
        assert d.egress.verify(call.admitted)
        for n in [1, 2]:
            entry = log.begin(n, 'a'*64)
            log.progress(entry, 'response_read')
            log.finalize(entry, dict(status=200, data=json.dumps(dict(usage=dict(
                input_tokens=d.contract.MAX_TOKENS_COUNTER,
                output_tokens=d.contract.MAX_TOKENS_COUNTER))).encode(),
                headers={'x-request-id':'z'*100, 'retry-after':'999999999'}))
        choices = tuple((f'candidate_{i}', .9 if i == 0 else .1/16) for i in range(16)) + (('escalate', .1/16),)
        return d.j.JevOk(d.j.JevResponse(d.j.PINNED_MODEL,
            d.j.ChoiceAnswer('candidate_0', .9, choices), (),
            d.j.Usage(d.contract.MAX_TOKENS_COUNTER, d.contract.MAX_TOKENS_COUNTER)), 2, 200, 5000)
    monkeypatch.setattr(d.j.JevClient, 'call', call)
    obj = dict(question=dict(id='generic', text='Choose', candidates=[dict(
        id=f'candidate_{i}', description='choice') for i in range(16)]),
        state={}, native_choice='candidate_1', egress_allowed=True)
    result = d.decide(obj, dict(mode='shadow', backend='jev'), tmp_path)
    assert result['reason'] == 'shadow_mode'
    path, = (tmp_path / '.clavain/decisions').glob('*.jsonl')
    assert path.stat().st_size < d.SHADOW_RECORD_HEADROOM
    row = json.loads(path.read_text())
    assert len(row['attempt_records']) == 2 and len(row['candidates']) == 16
    assert len(row['decide_answer']['probs']) == 17
    assert row['jev_usage_accounting']['known_total']['input_tokens'] == 2*d.contract.MAX_TOKENS_COUNTER


def test_busy_admission_does_not_spend_or_wait(hosted, tmp_path, monkeypatch):
    d, calls = hosted
    monkeypatch.setattr(d.j.Budget, 'consume', lambda _: pytest.fail('busy guard spent budget'))
    with d.records.admit_project_record(tmp_path, max_bytes=d.SHADOW_LOG_MAX_BYTES,
                                       reserve_bytes=d.SHADOW_RECORD_HEADROOM):
        result = d.decide(route(), POLICY, tmp_path)
    assert not calls and result['reason'] == 'record_unwritable'
    assert result['choice'] == 'work'


def test_client_exception_still_persists_unknown_usage_and_releases_lock(hosted, tmp_path, monkeypatch):
    d, calls = hosted
    def fail(self, call, *, log):
        log.begin(1)
        raise RuntimeError('synthetic')
    monkeypatch.setattr(d.j.JevClient, 'call', fail)
    result = d.decide(route(), POLICY, tmp_path)
    row, = d.records.read_records(record_dir=tmp_path / '.clavain/decisions')
    assert row['jev_usage_accounting']['unknown_attempts'] == 1
    assert row['attempt_records'][0]['state'] == 'interrupted'
    assert result['choice'] == 'work' and result['reason'] == 'internal_error'
    with d.records.admit_project_record(tmp_path, max_bytes=d.SHADOW_LOG_MAX_BYTES,
                                       reserve_bytes=d.SHADOW_RECORD_HEADROOM):
        pass
