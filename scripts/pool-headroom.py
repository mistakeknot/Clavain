#!/usr/bin/env python3
"""Normalize BB pool telemetry and rank already eligible execution candidates."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
import stat
import subprocess
import sys
import tempfile

EXECUTION = ('routine-execution', 'deep-execution', 'scout', 'coordination')
FAMILIES = ('fable', 'opus', 'sonnet')
# Same usability rules and weekly pace guard as the coordinator-side
# executor-headroom helper, so dispatch and spawn gating read one signal.
STALE_MS = 30 * 60 * 1000
WEEK_MIN = 10080
PACE_PENALTY = 0.15
# `bb pool status --json` takes 7-12 s on a busy host, so a snapshot is cached
# briefly and the read deadline is generous. A read failure never proves
# exhaustion: the result is `unknown` and routing is unchanged.
READ_TIMEOUT = float(os.environ.get('CLAVAIN_POOL_HEADROOM_TIMEOUT') or 60)
CACHE_TTL = float(os.environ.get('CLAVAIN_POOL_HEADROOM_CACHE_TTL') or 120)


def now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def skip_reason(account, now):
    """Why an account cannot take new work, or None. Missing fields never disqualify."""
    # Freshness first: an old observation proves nothing, even an old "exhausted".
    seen = account.get('observedAt')
    if type(seen) in (int, float) and now - seen > STALE_MS:
        return 'stale'
    status = account.get('status')
    if status is not None and status != 'ready':
        return 'status'
    held = account.get('heldUntil')
    if type(held) in (int, float) and held > now:
        return 'held'
    if account.get('usageRestriction'):
        return 'restricted'
    return None


def pace_penalty(account, now):
    reset = account.get('sevenDayResetAt')
    used = utilization(account.get('sevenDayUtilization'))
    if used is None or type(reset) not in (int, float):
        return 0
    span = WEEK_MIN * 60 * 1000
    elapsed = min(1 - (reset - now) / span, 1)
    return PACE_PENALTY if (elapsed <= 0 and used > 0) or (elapsed > 0 and used / elapsed > 1) else 0


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


def best(accounts, threshold, floor, family=None, now=None):
    now = now_ms() if now is None else now
    skips = {a.get('id'): skip_reason(a, now) for a in accounts}
    # Exhausted, held or restricted accounts are out; a stale observation says
    # nothing either way, so it is dropped without proving exhaustion.
    accounts_in = [a for a in accounts if skips[a.get('id')] is None]
    if not accounts_in:
        # Exhausted only when every account is provably unavailable; one stale
        # account leaves the provider unknown.
        hard = all(r in ('status', 'held', 'restricted') for r in skips.values())
        return {'best_account': None, 'remaining_5h': None, 'remaining_7d': None,
                'family_remaining_7d': None, 'score': None, 'below_floor': hard,
                'soonest_reset': None}
    rows = []
    for a in accounts_in:
        row = account_headroom(a, threshold, floor, family)
        if row['score'] is not None:
            row['score'] = max(row['score'] - pace_penalty(a, now), 0)
        rows.append(row)
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
    # Freeze a provider with any unknown candidate: moving its known seats could
    # otherwise overtake an unknown primary or strand an unknown fallback ahead.
    unknown_backends = {c['profile']['backend'] for c in candidates if scores[c['profile_ref']] is None}
    known = [c for c in candidates if c['profile']['backend'] not in unknown_backends]
    if role != 'scout' and len({c['profile']['backend'] for c in known}) > 1:
        # A family's extra quota cannot promote a provider's own capacity
        # substitute above its preferred model. Prefer providers, retaining
        # their internal policy order and using their first known candidate.
        backend_scores = {}
        for candidate in known:
            backend_scores.setdefault(candidate['profile']['backend'], scores[candidate['profile_ref']])
        ordered = iter(sorted(known, key=lambda c: -backend_scores[c['profile']['backend']]))
        result['candidates'] = [next(ordered) if c['profile']['backend'] not in unknown_backends else c for c in candidates]
        before = [c['profile_ref'] for c in candidates]
        after = [c['profile_ref'] for c in result['candidates']]
        if before != after:
            result['headroom_reorder'] = {'from': before, 'to': after, 'snapshot_at': snapshot.get('snapshot_at')}
    return result


def cache_path():
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'clavain', 'pool-status.json')


def private(path, want_dir):
    """True when path is ours, not a symlink, and not writable by group or others."""
    info = os.lstat(path)
    kind = stat.S_ISDIR(info.st_mode) if want_dir else stat.S_ISREG(info.st_mode)
    return kind and info.st_uid == os.getuid() and not info.st_mode & 0o022


def read_snapshot():
    """One `bb pool status --json`, reused for CACHE_TTL seconds across dispatches."""
    path = cache_path()
    try:
        if (CACHE_TTL > 0 and private(os.path.dirname(path), True) and private(path, False)
                and datetime.now().timestamp() - os.path.getmtime(path) < CACHE_TTL):
            with open(path) as handle:
                return json.load(handle)
    except (OSError, ValueError):
        pass
    value = subprocess.run([os.environ.get('BB_CLI') or 'bb', 'pool', 'status', '--json'],
                           capture_output=True, text=True, timeout=READ_TIMEOUT, check=True)
    data = json.loads(value.stdout)
    data['snapshot_at'] = datetime.now(timezone.utc).isoformat()
    if CACHE_TTL > 0:
        tmp = None
        try:
            directory = os.path.dirname(path)
            os.makedirs(directory, mode=0o700, exist_ok=True)
            if private(directory, True):
                fd, tmp = tempfile.mkstemp(dir=directory, prefix='.pool-status-')  # exclusive, 0600
                with os.fdopen(fd, 'w') as handle:
                    json.dump(data, handle)
                os.replace(tmp, path)
                tmp = None
        except OSError:
            pass
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stdin', action='store_true')
    parser.add_argument('--role')
    args = parser.parse_args()
    try:
        if args.stdin:
            data = json.load(sys.stdin)
        else:
            data = read_snapshot()
        result = advice(data, args.role) if args.role else normalize(data)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        if args.role:
            raise  # Invalid route is a contract error, never manufacture candidates.
        result = normalize(None)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
