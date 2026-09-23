#!/usr/bin/env python3
"""Normalize BB pool telemetry and rank already eligible execution candidates."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
import subprocess
import sys

EXECUTION = ('routine-execution', 'deep-execution', 'scout')
FAMILIES = ('fable', 'opus', 'sonnet')


def utilization(value):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 else None


def window(account, name, minutes):
    values = [(utilization(account.get(name + 'Utilization')), account.get(name + 'ResetAt'))]
    for item in account.get('limitWindows') or []:
        if isinstance(item, dict) and item.get('windowMinutes') == minutes:
            values.append((utilization(item.get('utilization')), item.get('resetAt')))
    # Never let a weaker duplicate observation hide an exhausted window.
    return max((v for v in values if v[0] is not None), default=(None, None), key=lambda v: v[0])


def account_headroom(account, threshold, floor, family=None):
    five, reset5 = window(account, 'fiveHour', 300)
    week, reset7 = window(account, 'sevenDay', 10080)
    family_data = (account.get('familyWeekly') or {}).get(family) or {}
    family_week = utilization(family_data.get('utilization'))
    weeks = [v for v in (week, family_week) if v is not None]
    exhausted = (five is not None and five >= threshold) or any(v > 1 - floor for v in weeks)
    known = [1 - v for v in (five, *weeks) if v is not None]
    resets = [v for v in (reset5, reset7, family_data.get('resetAt')) if type(v) in (int, float) and math.isfinite(v)]
    return {'best_account': account.get('id'), 'remaining_5h': None if five is None else 1 - five,
            'remaining_7d': None if week is None else 1 - week,
            'family_remaining_7d': None if family_week is None else 1 - family_week,
            'score': min(known) if known else None, 'below_floor': exhausted,
            'soonest_reset': min(resets) if resets else None}


def best(accounts, threshold, floor, family=None):
    rows = [account_headroom(a, threshold, floor, family) for a in accounts]
    # A partial/unknown account is never proof that every account is exhausted.
    usable = [r for r in rows if not r['below_floor']]
    winner = max(usable or rows, key=lambda r: r['score'] if r['score'] is not None else -1)
    return dict(winner, below_floor=all(r['below_floor'] for r in rows))


def normalize(data):
    unknown = {'status': 'unknown', 'providers': {}, 'snapshot_at': None}
    if not isinstance(data, dict) or not isinstance(data.get('accounts'), list):
        return unknown
    accounts = [a for a in data['accounts'] if isinstance(a, dict) and a.get('enabled') is True
                and a.get('provider') in ('codex', 'claude')]
    if not accounts or data.get('ok') is False or data.get('accepting') is False:
        return unknown
    threshold = utilization(data.get('switchThreshold'))
    if threshold is None:
        threshold = .98
    providers = {}
    for provider in ('codex', 'claude'):
        rows = [a for a in accounts if a['provider'] == provider]
        if not rows:
            continue
        summary = best(rows, threshold, .1)
        summary['families'] = {}
        if provider == 'claude':
            for family in FAMILIES:
                value = best(rows, threshold, .1, family)
                value['provider_remaining_7d'] = value['remaining_7d']
                value['remaining_7d'] = value.pop('family_remaining_7d')
                summary['families'][family] = value
        providers[provider] = summary
    return {'status': 'known', 'providers': providers, 'switch_threshold': threshold,
            'snapshot_at': data.get('snapshot_at')}


def advice(data, role):
    route, snapshot = data['route'], data['snapshot']
    candidates = [{'profile_ref': route['profile_ref'], 'profile': route['profile']},
                  *route.get('fallback_chain', [])]
    result = {'exclude': [], 'candidates': candidates, 'headroom_reorder': None}
    if role not in EXECUTION or snapshot.get('status') != 'known':
        return result
    scores = {}
    for candidate in candidates:
        profile = candidate['profile']
        provider = snapshot.get('providers', {}).get(profile['backend'], {})
        model = profile['model']
        family = next((f for f in FAMILIES if model.startswith('claude-' + f)), None)
        headroom = provider.get('families', {}).get(family, provider)
        if headroom.get('below_floor'):
            result['exclude'].append(model)
        scores[candidate['profile_ref']] = headroom.get('score')
    # Unknown candidates retain their positions. Only the cross-provider known
    # subsequence is sorted, with stable ties preserving policy preference.
    known = [c for c in candidates if scores[c['profile_ref']] is not None]
    if role != 'scout' and len({c['profile']['backend'] for c in known}) > 1:
        ordered = iter(sorted(known, key=lambda c: -scores[c['profile_ref']]))
        result['candidates'] = [next(ordered) if scores[c['profile_ref']] is not None else c for c in candidates]
        before = [c['profile_ref'] for c in candidates]
        after = [c['profile_ref'] for c in result['candidates']]
        if before != after:
            result['headroom_reorder'] = {'from': before, 'to': after, 'snapshot_at': snapshot.get('snapshot_at')}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stdin', action='store_true')
    parser.add_argument('--role')
    args = parser.parse_args()
    try:
        if args.stdin:
            data = json.load(sys.stdin)
        else:
            value = subprocess.run([os.environ.get('BB_CLI') or 'bb', 'pool', 'status', '--json'],
                                   capture_output=True, text=True, timeout=3, check=True)
            data = json.loads(value.stdout)
            data['snapshot_at'] = datetime.now(timezone.utc).isoformat()
        result = advice(data, args.role) if args.role else normalize(data)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        if args.role:
            raise  # Invalid route is a contract error, never manufacture candidates.
        result = normalize(None)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
