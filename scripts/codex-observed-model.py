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
import argparse, json, os, re, signal, stat, sys
from pathlib import Path

MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}')
MAX_MODELS = 16
DEADLINE_S = 20  # own bound: must hold even where `timeout(1)` is absent
MAX_LINE = 1 << 25  # 32 MiB; real tool-output records reach a few MiB
UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')

class Expired(Exception):
    pass

def regular(path):
    """True only for a regular file: a FIFO or device at the path must never block the reader."""
    try: return stat.S_ISREG(os.stat(path).st_mode)
    except OSError: return False

def lines(f):
    """(line, oversized): reads at most MAX_LINE bytes of a line at a time, so a huge record cannot balloon memory."""
    while True:
        line = f.readline(MAX_LINE + 1)
        if not line: return
        if len(line) > MAX_LINE and not line.endswith('\n'):
            while True:  # drain the rest of the oversized record without keeping it
                rest = f.readline(MAX_LINE)
                if not rest or rest.endswith('\n'): break
            yield '', True
        else:
            yield line, False

def thread_ids(events):
    ids = []
    if not regular(events): return ids
    try:
        with open(events, errors='replace') as f:
            for line, big in lines(f):
                if big: continue
                try: o = json.loads(line)
                except ValueError: continue
                t = o.get('thread_id') if isinstance(o, dict) and o.get('type') == 'thread.started' else None
                if isinstance(t, str) and UUID.fullmatch(t) and t not in ids: ids.append(t)
    except OSError: pass
    return ids

def find_rollouts(root, tid):
    return sorted(root.glob(f'*/*/*/rollout-*-{tid}.jsonl'))

def responded(o, p):
    """A record proving the model answered: an assistant message, or usage counted for the turn."""
    return (o.get('type') == 'response_item' and p.get('type') == 'message' and p.get('role') == 'assistant') or \
           (o.get('type') == 'event_msg' and p.get('type') == 'token_count' and bool(p.get('info')))

def read_rollout(path, tid):
    """(model of every turn in order, final turn's effort) for the session `tid`.

    Unprovable (([], None)) when anything about a turn is doubtful: an unparsable
    record, a turn without a valid model, or a turn with no sign the model answered
    (a configured-but-refused turn, e.g. a usage limit, is not a model that ran)."""
    models, effort, meta_ok, answered = [], None, False, True
    with open(path, errors='replace') as f:
        for line, big in lines(f):
            if big: return [], None
            if not line.strip(): continue
            try: o = json.loads(line)
            except ValueError: return [], None  # a damaged record could be a damaged turn
            if not isinstance(o, dict): return [], None
            p = o.get('payload')
            if o.get('type') == 'turn_context' and not isinstance(p, dict): return [], None
            if not isinstance(p, dict): continue
            if o.get('type') == 'session_meta':
                meta_ok = p.get('id') == tid
            elif o.get('type') == 'turn_context':
                if not answered: return [], None
                m = p.get('model')
                # A turn with no valid model is unprovable: skipping it would credit the earlier turn's model.
                if not isinstance(m, str) or not MODEL.fullmatch(m) or len(models) >= 100000: return [], None
                models.append(m); answered = False
                # Effort belongs to the turn that carries it; a later turn without one must not inherit it.
                effort = p['effort'] if isinstance(p.get('effort'), str) and MODEL.fullmatch(p['effort']) else None
            elif responded(o, p):
                answered = True
    return (models, effort) if meta_ok and answered else ([], None)

def observe(events, sessions, requested_model=''):
    out = {'observed_model': 'unknown', 'observed_models': [], 'observed_effort': 'unknown',
           'observed_source': 'codex-session-rollout', 'observed_thread_id': '',
           'observed_model_matches_requested': None}
    ids = thread_ids(events)
    if not ids:
        return {**out, 'observed_source': 'unavailable', 'observed_reason': 'no thread.started event in provider events'}
    out['observed_thread_id'] = ids[0]
    turns, efforts = [], []
    for tid in ids:
        paths = find_rollouts(sessions, tid)
        if len(paths) != 1:  # none, or several files claiming one thread id: cannot say which run this was
            why = f'no session rollout for thread {tid} under {sessions}' if not paths else f'{len(paths)} session rollouts claim thread {tid}'
            return {**out, 'observed_source': 'unavailable', 'observed_reason': why}
        if not regular(paths[0]):
            return {**out, 'observed_source': 'unavailable', 'observed_reason': f'rollout for thread {tid} is not a regular file'}
        try: m, e = read_rollout(paths[0], tid)
        except OSError as err:
            return {**out, 'observed_source': 'unavailable', 'observed_reason': f'cannot read rollout: {err.strerror}'}
        if not m:
            return {**out, 'observed_source': 'unavailable', 'observed_reason': f'rollout for thread {tid} has no matching session_meta or a valid turn_context model'}
        turns += m
        efforts.append(e)
    models = list(dict.fromkeys(turns))
    # Threads finish in an unknown order: an effort is only claimed when every thread agrees.
    effort = efforts[0] if len(set(efforts)) == 1 else None
    if len(models) > MAX_MODELS:
        return {**out, 'observed_source': 'unavailable', 'observed_reason': 'implausibly many distinct models in session'}
    out['observed_models'] = models
    if len(ids) > 1 and len(models) > 1:
        # Threads are ordered by start, not by finish, so no single final model can be named.
        out['observed_reason'] = 'several threads ran different models'
        if requested_model: out['observed_model_matches_requested'] = False
        out['observed_effort'] = effort or 'unknown'
        return out
    out['observed_model'] = turns[-1]  # the model of the final turn, even when it switched back to an earlier one
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
    def expired(*_): raise Expired
    signal.signal(signal.SIGALRM, expired); signal.alarm(DEADLINE_S)
    root = Path(a.sessions_dir) if a.sessions_dir else Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'sessions'
    print(json.dumps(observe(a.events, root, a.requested_model), separators=(',', ':')))

if __name__ == '__main__':
    try: main()
    except Exception as err:  # evidence must never fail a dispatch
        print(json.dumps({'observed_model': 'unknown', 'observed_source': 'unavailable', 'observed_reason': f'helper error: {type(err).__name__}'}))
