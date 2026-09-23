"""Headroom forecasts: sanitized fixtures, no account or model-service calls."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/pool-headroom.sh'


def account(provider, weekly, five=0.1, **extra):
    return dict(id=provider + '-fixture', provider=provider, enabled=True,
                sevenDayUtilization=weekly, fiveHourUtilization=five, **extra)


HEALTHY = {'snapshot_at': '2026-09-22T23:00:00Z', 'accounts': [
    account('codex', 0.2), account('claude', 0.5, familyWeekly={
        'fable': {'utilization': 0.3, 'resetAt': 1790388000419}})]}


def core(value, *args):
    p = subprocess.run(['bash', str(SCRIPT), '--stdin', *args], input=json.dumps(value),
                       text=True, capture_output=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def route():
    return {'profile_ref': 'routine-sol', 'profile': {'backend': 'codex', 'model': 'gpt-5.6-sol'},
            'fallback_chain': [{'profile_ref': 'routine-sonnet', 'profile': {
                'backend': 'claude', 'model': 'claude-sonnet-5'}}]}


def advise(snapshot, role='routine-execution', resolved=None):
    return core({'snapshot': snapshot, 'route': resolved or route()}, '--role', role)


def test_healthy():
    snapshot = core(HEALTHY)
    assert snapshot['status'] == 'known'
    codex = snapshot['providers']['codex']
    assert codex['best_account'] == 'codex-fixture'
    assert codex['remaining_7d'] == pytest.approx(0.8)
    assert codex['remaining_5h'] == pytest.approx(0.9)
    assert snapshot['providers']['claude']['families']['fable']['remaining_7d'] == pytest.approx(0.7)
    assert advise(snapshot)['exclude'] == []


def test_real_pool_schema_sanitized_capture():
    # Captured with read-only bb pool status; labels, email and account IDs removed.
    data = json.loads((ROOT/'tests/fixtures/pool-headroom/bb-status-sanitized.json').read_text())
    assert {a['provider'] for a in data['accounts']} == {'claude', 'codex'}
    snapshot = core(data)
    assert snapshot['status'] == 'known'
    assert snapshot['providers']['codex']['score'] == pytest.approx(.85)
    assert snapshot['providers']['claude']['score'] == pytest.approx(.38)
    result = advise(snapshot)
    assert result['exclude'] == [] and result['headroom_reorder'] is None
    assert result['candidates'][0]['profile_ref'] == 'routine-sol'


def test_unreachable_cli_is_unknown(tmp_path):
    import os
    result = subprocess.run(['bash', str(SCRIPT)], env=dict(os.environ, BB_CLI=str(tmp_path/'absent')),
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['status'] == 'unknown'


def test_unknown_family_cannot_be_overtaken_by_its_provider_fallback():
    snapshot = core({'accounts': [account('codex', .7),
        account('claude', None, None, familyWeekly={'opus': {'utilization': .1}})]})
    resolved = {'profile_ref': 'astra', 'profile': {'backend': 'codex', 'model': 'gpt-6-astra'},
                'fallback_chain': [{'profile_ref': family, 'profile': {
                    'backend': 'claude', 'model': 'claude-' + family}} for family in ('fable', 'opus')]}
    assert advise(snapshot, 'deep-execution', resolved)['headroom_reorder'] is None


def test_one_family_exhausted():
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][1]['familyWeekly']['fable']['utilization'] = .99
    snapshot = core(fixture)
    resolved = {'profile_ref': 'fable', 'profile': {'backend': 'claude', 'model': 'claude-fable-5-1'},
                'fallback_chain': route()['fallback_chain']}
    assert advise(snapshot, 'deep-execution', resolved)['exclude'] == ['claude-fable-5-1']


@pytest.mark.parametrize('bad', [None, {}, {'accounts': []}, {'ok': False}, {'accounts': 'broken'}])
def test_unknown_keeps_chain(bad):
    snapshot = core(bad)
    assert snapshot['status'] == 'unknown'
    result = advise(snapshot)
    assert result['exclude'] == [] and result['headroom_reorder'] is None
    assert [c['profile_ref'] for c in result['candidates']] == ['routine-sol', 'routine-sonnet']


def test_limit_windows_and_disabled_accounts():
    fixture = {'accounts': [account('codex', None, None, limitWindows=[
        {'windowMinutes': 10080, 'utilization': .96, 'resetAt': 1790388000419}]),
        dict(account('codex', 0), enabled=False)]}
    snapshot = core(fixture)
    assert snapshot['providers']['codex']['soonest_reset'] == 1790388000419
    assert advise(snapshot)['exclude'] == ['gpt-5.6-sol']


def test_best_account_is_family_specific_and_unknown_is_not_exhausted():
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][1]['familyWeekly']['fable']['utilization'] = 1
    fixture['accounts'].append(account('claude', .6, familyWeekly={'fable': {'utilization': .1}}))
    fixture['accounts'][-1]['id'] = 'second'
    assert core(fixture)['providers']['claude']['families']['fable']['best_account'] == 'second'
    fixture['accounts'] = [account('codex', 1), account('codex', None, None)]
    assert advise(core(fixture))['exclude'] == []


def test_floor_and_switch_boundary():
    assert advise(core({'accounts': [account('codex', .9, .97)]}))['exclude'] == []
    assert advise(core({'accounts': [account('codex', .9, .98)]}))['exclude'] == ['gpt-5.6-sol']


def test_reorder_retains_ic_profile():
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][0]['sevenDayUtilization'] = .8
    result = advise(core(fixture))
    assert result['headroom_reorder'] == {'from': ['routine-sol', 'routine-sonnet'],
        'to': ['routine-sonnet', 'routine-sol'], 'snapshot_at': HEALTHY['snapshot_at']}


def test_cross_provider_preference_preserves_each_providers_policy_order():
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][0]['sevenDayUtilization'] = .7
    fixture['accounts'][1]['sevenDayUtilization'] = .1
    fixture['accounts'][1]['familyWeekly'] = {'fable': {'utilization': .5}, 'opus': {'utilization': .1}}
    resolved = {'profile_ref': 'astra', 'profile': {'backend': 'codex', 'model': 'gpt-6-astra'},
                'fallback_chain': [{'profile_ref': family, 'profile': {
                    'backend': 'claude', 'model': 'claude-' + family}} for family in ('fable', 'opus')]}
    result = advise(core(fixture), 'deep-execution', resolved)
    assert [c['profile_ref'] for c in result['candidates']] == ['fable', 'opus', 'astra']


@pytest.mark.parametrize('role', ['plan-review', 'validation', 'escalation', 'planning', 'cross-lab-review'])
def test_protected_roles_ignore_exhausted_fable(role):
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][1]['familyWeekly']['fable']['utilization'] = 1
    resolved = route()
    resolved['profile'] = {'backend': 'claude', 'model': 'claude-fable-5-1'}
    result = advise(core(fixture), role, resolved)
    assert result['exclude'] == [] and result['headroom_reorder'] is None
    assert result['candidates'][0]['profile'] == resolved['profile']
