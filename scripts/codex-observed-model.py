#!/usr/bin/env python3
"""Observed model/effort for a finished `codex exec --json` run (mk-28gt).

Codex's --json stream has no model field, so a receipt built from dispatch's own
arguments holds only the *requested* model. Codex does write the model it ran to
its session rollout (`<sessions>/YYYY/MM/DD/rollout-<ts>-<thread_id>.jsonl`, one
`turn_context` record per turn). This reads the thread ids from the events file
dispatch already captured, finds their rollouts, and prints one JSON object:

  observed_model, observed_models, observed_effort, observed_source,
  observed_thread_id, observed_model_matches_requested (true/false/null)

Anything it cannot prove is "unknown" plus observed_reason; it never guesses from
the requested model and always exits 0 so evidence gathering cannot fail a run.
"""
import argparse, json, os, re, sys
from pathlib import Path

UUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

def thread_ids(events):
    ids = []
    try:
        with open(events, errors='replace') as f:
            for line in f:
                try: o = json.loads(line)
                except ValueError: continue
                t = o.get('thread_id') if isinstance(o, dict) and o.get('type') == 'thread.started' else None
                if isinstance(t, str) and UUID.match(t) and t not in ids: ids.append(t)
    except OSError: pass
    return ids

def find_rollout(root, tid):
    hits = sorted(root.glob(f'*/*/*/rollout-*-{tid}.jsonl'))
    return hits[-1] if hits else None

def read_rollout(path, tid):
    """(models in first-seen order, last effort) from turn_context records of the session `tid`."""
    models, effort, meta_ok = [], None, False
    with open(path, errors='replace') as f:
        for line in f:
            try: o = json.loads(line)
            except ValueError: continue
            if not isinstance(o, dict) or not isinstance(o.get('payload'), dict): continue
            p = o['payload']
            if o.get('type') == 'session_meta':
                meta_ok = p.get('id') == tid
            elif o.get('type') == 'turn_context' and isinstance(p.get('model'), str) and p['model']:
                if p['model'] not in models: models.append(p['model'])
                if isinstance(p.get('effort'), str): effort = p['effort']
    return (models, effort) if meta_ok else ([], None)

def observe(events, sessions, requested_model=''):
    out = {'observed_model': 'unknown', 'observed_models': [], 'observed_effort': 'unknown',
           'observed_source': 'codex-session-rollout', 'observed_thread_id': '',
           'observed_model_matches_requested': None}
    ids = thread_ids(events)
    if not ids:
        return {**out, 'observed_source': 'unavailable', 'observed_reason': 'no thread.started event in provider events'}
    out['observed_thread_id'] = ids[0]
    models, effort = [], None
    for tid in ids:
        path = find_rollout(sessions, tid)
        if path is None:
            return {**out, 'observed_source': 'unavailable', 'observed_reason': f'no session rollout for thread {tid} under {sessions}'}
        try: m, e = read_rollout(path, tid)
        except OSError as err:
            return {**out, 'observed_source': 'unavailable', 'observed_reason': f'cannot read rollout: {err.strerror}'}
        if not m:
            return {**out, 'observed_source': 'unavailable', 'observed_reason': f'rollout for thread {tid} has no matching session_meta/turn_context model'}
        models += [x for x in m if x not in models]
        effort = e or effort
    out['observed_models'] = models
    out['observed_model'] = models[-1]
    out['observed_effort'] = effort or 'unknown'
    if requested_model:
        # Every model that actually ran must be the requested one.
        out['observed_model_matches_requested'] = models == [requested_model]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('events')
    ap.add_argument('--sessions-dir')
    ap.add_argument('--requested-model', default='')
    a = ap.parse_args()
    root = Path(a.sessions_dir) if a.sessions_dir else Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'sessions'
    print(json.dumps(observe(a.events, root, a.requested_model), separators=(',', ':')))

if __name__ == '__main__':
    try: main()
    except Exception as err:  # evidence must never fail a dispatch
        print(json.dumps({'observed_model': 'unknown', 'observed_source': 'unavailable', 'observed_reason': f'helper error: {type(err).__name__}'}))
