"""Headroom forecasts: sanitized fixtures, no account or model-service calls."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/pool-headroom.sh'


def account(provider, weekly, five=0.1, **extra):
    return {'id': provider + '-fixture', 'provider': provider, 'enabled': True,
            'sevenDayUtilization': weekly, 'fiveHourUtilization': five, **extra}


HEALTHY = {'snapshot_at': '2026-09-22T23:00:00Z', 'accounts': [
    account('codex', 0.2), account('claude', 0.5, familyWeekly={
        'fable': {'utilization': 0.3, 'resetAt': 1790388000419}})]}


def core(value, *args):
    p = subprocess.run(['bash', str(SCRIPT), '--stdin', *args], input=json.dumps(value),
                       text=True, capture_output=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def route():
    return {'profile_ref': 'routine-sol', 'profile': {'backend': 'codex', 'model': 'gpt-6.1-sol'},
            'fallback_chain': [{'profile_ref': 'routine-sonnet', 'profile': {
                'backend': 'claude', 'model': 'claude-sonnet-5-5'}}]}


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
    assert advise(snapshot)['exclude'] == ['gpt-6.1-sol']


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
    assert advise(core({'accounts': [account('codex', .9, .98)]}))['exclude'] == ['gpt-6.1-sol']


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


def test_coordination_follows_headroom_to_sol():
    # Relay and status work has no producer-independence constraint, so under
    # Claude quota pressure it moves to the Codex seat (mk-ji9m).
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][1]['sevenDayUtilization'] = .8
    resolved = {'profile_ref': 'coordination-sonnet', 'profile': {'backend': 'claude', 'model': 'claude-sonnet-5-5'},
                'fallback_chain': [{'profile_ref': 'coordination-sol', 'profile': {
                    'backend': 'codex', 'model': 'gpt-6.1-sol'}}]}
    result = advise(core(fixture), 'coordination', resolved)
    assert [c['profile_ref'] for c in result['candidates']] == ['coordination-sol', 'coordination-sonnet']


@pytest.mark.parametrize('role', ['plan-review', 'validation', 'escalation', 'planning', 'cross-lab-review'])
def test_protected_roles_ignore_exhausted_fable(role):
    fixture = copy.deepcopy(HEALTHY)
    fixture['accounts'][1]['familyWeekly']['fable']['utilization'] = 1
    resolved = route()
    resolved['profile'] = {'backend': 'claude', 'model': 'claude-fable-5-1'}
    result = advise(core(fixture), role, resolved)
    assert result['exclude'] == [] and result['headroom_reorder'] is None
    assert result['candidates'][0]['profile'] == resolved['profile']


NOW = 1_800_000_000_000


def usable(provider, weekly, five=0.1, **extra):
    return account(provider, weekly, five, observedAt=NOW, status='ready', **extra)


def test_exhausted_status_account_is_skipped_not_scored():
    # Live shape: two exhausted Claude accounts plus one ready account.
    snap = core({'accounts': [
        account('claude', 1.0, 0.0, id='a', status='exhausted', observedAt=NOW),
        account('claude', 0.12, 0.51, id='b', status='ready', observedAt=NOW),
        usable('codex', 0.2)]})
    claude = snap['providers']['claude']
    assert claude['best_account'] == 'b'
    assert claude['below_floor'] is False


def test_all_claude_accounts_exhausted_excludes_claude_up_front():
    snap = core({'accounts': [
        account('claude', 1.0, 0.0, id='a', status='exhausted', observedAt=NOW),
        account('claude', 0.99, 0.02, id='b', status='exhausted', observedAt=NOW),
        usable('codex', 0.2)]})
    assert snap['providers']['claude']['below_floor'] is True
    assert advise(snap)['exclude'] == ['claude-sonnet-5-5']


def test_held_and_restricted_accounts_are_skipped():
    far = 9_999_999_999_999
    snap = core({'accounts': [
        account('claude', 0.1, 0.1, id='h', status='ready', heldUntil=far),
        account('claude', 0.1, 0.1, id='r', status='ready', usageRestriction={'kind': 'x'}),
        usable('codex', 0.2)]})
    assert snap['providers']['claude']['below_floor'] is True


def test_stale_observation_is_unknown_not_exhausted():
    snap = core({'accounts': [
        account('claude', 0.1, 0.1, id='s', status='ready', observedAt=1),
        usable('codex', 0.2)]})
    claude = snap['providers']['claude']
    assert claude['score'] is None and claude['below_floor'] is False
    assert advise(snap)['exclude'] == []


def test_weekly_pace_guard_lowers_score():
    # 60% used with 40% of the week elapsed => pace 1.5 > 1, minus 15 points.
    week = 10080 * 60 * 1000
    import time
    now = int(time.time() * 1000)
    paced = core({'accounts': [account('claude', 0.6, 0.1, id='p', status='ready', observedAt=now,
                                       sevenDayResetAt=now + int(week * 0.6))]})
    plain = core({'accounts': [account('claude', 0.6, 0.1, id='p', status='ready', observedAt=now)]})
    assert plain['providers']['claude']['score'] == pytest.approx(.4)
    assert paced['providers']['claude']['score'] == pytest.approx(.25)


def test_live_read_is_cached(tmp_path):
    import os
    calls = tmp_path / 'calls'
    bb = tmp_path / 'bb'
    bb.write_text('#!/bin/sh\necho x >> ' + str(calls) + '\ncat <<EOF\n' + json.dumps(
        {'accounts': [dict(usable('codex', 0.2), observedAt=int(__import__('time').time() * 1000))]}) + '\nEOF\n')
    bb.chmod(0o755)
    env = dict(os.environ, BB_CLI=str(bb), XDG_CACHE_HOME=str(tmp_path / 'c'))
    for _ in range(2):
        out = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, check=True)
        assert json.loads(out.stdout)['status'] == 'known'
    assert len(calls.read_text().split()) == 1


def test_stale_exhausted_account_is_unknown_not_exhausted():
    snap = core({'accounts': [account('claude', 1.0, 0.0, id='s', status='exhausted', observedAt=1),
                              usable('codex', 0.2)]})
    assert snap['providers']['claude']['below_floor'] is False
    assert advise(snap)['exclude'] == []


def test_fresh_exhausted_plus_stale_ready_is_unknown():
    snap = core({'accounts': [account('claude', 1.0, 0.0, id='a', status='exhausted', observedAt=NOW),
                              account('claude', 0.1, 0.1, id='b', status='ready', observedAt=1),
                              usable('codex', 0.2)]})
    assert snap['providers']['claude']['below_floor'] is False
    assert advise(snap)['exclude'] == []


def _cache_env(tmp_path, body):
    import os, time
    bb = tmp_path / 'bb'
    bb.write_text('#!/bin/sh\ncat <<EOF\n' + json.dumps({'accounts': [dict(
        usable('codex', 0.2), observedAt=int(time.time() * 1000))]}) + '\nEOF\n')
    bb.chmod(0o755)
    return dict(os.environ, BB_CLI=str(bb), XDG_CACHE_HOME=str(tmp_path / 'c'))


def test_cache_ignores_poisoned_world_writable_file(tmp_path):
    import os
    env = _cache_env(tmp_path, None)
    d = tmp_path / 'c' / 'clavain'
    d.mkdir(parents=True, mode=0o700)
    f = d / 'pool-status.json'
    f.write_text(json.dumps({'accounts': [account('claude', 1.0, 1.0, id='x', status='exhausted')]}))
    f.chmod(0o666)
    out = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, check=True)
    assert 'claude' not in json.loads(out.stdout)['providers']


def test_cache_does_not_follow_symlinked_directory(tmp_path):
    import os
    env = _cache_env(tmp_path, None)
    target = tmp_path / 'elsewhere'
    target.mkdir()
    (tmp_path / 'c').mkdir()
    os.symlink(target, tmp_path / 'c' / 'clavain')
    subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True, check=True)
    assert list(target.iterdir()) == []
