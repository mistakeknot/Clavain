"""mk-28gt: observed-model capture from a codex session rollout (no model calls)."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts' / 'codex-observed-model.py'
ANSWER = {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant'}}
TID = '01a0f12b-4441-7732-b494-da5347122cea'


def run(events, sessions, requested='', env=None):
    cmd = [sys.executable, str(HELPER), str(events), '--sessions-dir', str(sessions)]
    if requested:
        cmd += ['--requested-model', requested]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def events(path, *tids):
    path.write_text('\n'.join(json.dumps({'type': 'thread.started', 'thread_id': t}) for t in tids)
                    + '\n{"type":"turn.completed"}\n')
    return path


def rollout(root, tid, models, meta_id=None, effort='high'):
    d = root / '2026' / '09' / '30'
    d.mkdir(parents=True, exist_ok=True)
    rows = [{'type': 'session_meta', 'payload': {'id': meta_id or tid}}]
    for m in models:
        rows += [{'type': 'turn_context', 'payload': {'model': m, 'effort': effort}}, ANSWER]
    (d / f'rollout-2026-09-30T00-00-00-{tid}.jsonl').write_text('\n'.join(map(json.dumps, rows)) + '\n')


def test_observed_model_read_from_session_rollout(tmp_path):
    rollout(tmp_path / 's', TID, ['gpt-6.1-sol'])
    r = run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's', 'gpt-6.1-sol')
    assert (r['observed_model'], r['observed_effort'], r['observed_source']) == ('gpt-6.1-sol', 'high', 'codex-session-rollout')
    assert r['observed_thread_id'] == TID and r['observed_model_matches_requested'] is True


def test_mismatch_with_request_is_reported_not_hidden(tmp_path):
    rollout(tmp_path / 's', TID, ['gpt-6.1-sol'])
    r = run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's', 'gpt-6-astra')
    assert r['observed_model'] == 'gpt-6.1-sol' and r['observed_model_matches_requested'] is False


def test_model_switch_mid_session_lists_every_model_and_never_matches(tmp_path):
    rollout(tmp_path / 's', TID, ['gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-astra'])
    r = run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's', 'gpt-6.1-sol')
    assert r['observed_models'] == ['gpt-6.1-sol', 'gpt-6-astra'] and r['observed_model'] == 'gpt-6-astra'
    assert r['observed_model_matches_requested'] is False


def test_no_requested_model_leaves_match_null(tmp_path):
    rollout(tmp_path / 's', TID, ['gpt-6.1-sol'])
    assert run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's')['observed_model_matches_requested'] is None


@pytest.mark.parametrize('case', ['no_thread_event', 'no_rollout', 'wrong_meta_id', 'no_turn_context', 'missing_events_file', 'bad_thread_id'])
def test_unprovable_is_unknown_never_the_requested_model(tmp_path, case):
    s = tmp_path / 's'; s.mkdir()
    ev = tmp_path / 'e.jsonl'
    if case == 'no_thread_event':
        ev.write_text('{"type":"turn.completed"}\nnot json\n')
    elif case == 'no_rollout':
        events(ev, TID)
    elif case == 'wrong_meta_id':
        events(ev, TID); rollout(s, TID, ['gpt-6.1-sol'], meta_id='00000000-0000-4000-8000-000000000000')
    elif case == 'no_turn_context':
        events(ev, TID); rollout(s, TID, [])
    elif case == 'bad_thread_id':
        events(ev, '../../etc/*')
    else:
        ev = tmp_path / 'absent.jsonl'
    r = run(ev, s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown' and r['observed_source'] == 'unavailable'
    assert r['observed_model_matches_requested'] is None and r.get('observed_reason')


def test_codex_home_is_the_default_sessions_root(tmp_path):
    home = tmp_path / 'home'
    rollout(home / 'sessions', TID, ['gpt-6.1-sol'])
    ev = events(tmp_path / 'e.jsonl', TID)
    p = subprocess.run([sys.executable, str(HELPER), str(ev)], capture_output=True, text=True, env={**os.environ, 'CODEX_HOME': str(home)})
    assert json.loads(p.stdout)['observed_model'] == 'gpt-6.1-sol'


def test_reads_the_real_rollout_shape_seen_in_codex_0_159(tmp_path):
    """Codex 0.159.2 puts model/effort on turn_context and the id on session_meta."""
    d = tmp_path / 's' / '2026' / '09' / '30'; d.mkdir(parents=True)
    (d / f'rollout-2026-09-30T01-15-40-{TID}.jsonl').write_text(
        json.dumps({'type': 'session_meta', 'payload': {'id': TID, 'session_id': TID, 'originator': 'codex_exec', 'model_provider': 'bb-account-pool'}}) + '\n'
        + json.dumps({'type': 'event_msg', 'payload': {'type': 'task_started'}}) + '\n'
        + json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'effort': 'medium', 'collaboration_mode': {'settings': {'model': 'gpt-6.1-sol'}}}}) + '\n'
        + json.dumps(ANSWER) + '\n')
    r = run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's', 'gpt-6.1-sol')
    assert r['observed_model'] == 'gpt-6.1-sol' and r['observed_effort'] == 'medium'


def test_switch_back_reports_the_final_model_not_the_last_new_one(tmp_path):
    rollout(tmp_path / 's', TID, ['gpt-6.1-sol', 'gpt-6-astra', 'gpt-6.1-sol'])
    r = run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's', 'gpt-6.1-sol')
    assert r['observed_model'] == 'gpt-6.1-sol' and r['observed_models'] == ['gpt-6.1-sol', 'gpt-6-astra']
    assert r['observed_model_matches_requested'] is False


def test_two_rollouts_claiming_one_thread_id_are_ambiguous_not_last_wins(tmp_path):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'])
    d = s / '2026' / '10' / '01'; d.mkdir(parents=True)
    (d / f'rollout-2026-10-01T00-00-00-{TID}.jsonl').write_text(
        json.dumps({'type': 'session_meta', 'payload': {'id': TID}}) + '\n'
        + json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-6-astra'}}) + '\n')
    r = run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6-astra')
    assert r['observed_model'] == 'unknown' and r['observed_model_matches_requested'] is None
    assert 'claim thread' in r['observed_reason']


@pytest.mark.parametrize('bad', ['x' * 129, 'gpt 6', 'gpt-6\n', '$(id)', ';rm'])
def test_a_value_that_is_not_a_model_id_is_unprovable(tmp_path, bad):
    rollout(tmp_path / 's', TID, [bad])
    r = run(events(tmp_path / 'e.jsonl', TID), tmp_path / 's', 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown' and r['observed_source'] == 'unavailable'


def test_a_fifo_for_events_or_rollout_never_blocks_the_helper(tmp_path):
    s = tmp_path / 's'; s.mkdir()
    fifo = tmp_path / 'e.fifo'; os.mkfifo(fifo)
    p = subprocess.run([sys.executable, str(HELPER), str(fifo), '--sessions-dir', str(s)], capture_output=True, text=True, timeout=10)
    assert json.loads(p.stdout)['observed_source'] == 'unavailable'
    d = s / '2026' / '09' / '30'; d.mkdir(parents=True)
    os.mkfifo(d / f'rollout-2026-09-30T00-00-00-{TID}.jsonl')
    p = subprocess.run([sys.executable, str(HELPER), str(events(tmp_path / 'e.jsonl', TID)), '--sessions-dir', str(s)], capture_output=True, text=True, timeout=10)
    r = json.loads(p.stdout)
    assert r['observed_model'] == 'unknown' and 'regular file' in r['observed_reason']


def test_a_later_turn_without_a_model_is_unprovable_not_the_earlier_model(tmp_path):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'])
    f = next(s.rglob('rollout-*.jsonl'))
    f.write_text(f.read_text() + json.dumps({'type': 'turn_context', 'payload': {'effort': 'high'}}) + '\n')
    r = run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown' and r['observed_model_matches_requested'] is None


def test_threads_that_ran_different_models_name_no_single_final_model(tmp_path):
    other = '02b1f23c-5552-7843-c5a5-eb6458233dfb'
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol']); rollout(s, other, ['gpt-6-astra'])
    r = run(events(tmp_path / 'e.jsonl', TID, other), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown' and r['observed_models'] == ['gpt-6.1-sol', 'gpt-6-astra']
    assert r['observed_model_matches_requested'] is False and 'several threads' in r['observed_reason']


def test_two_threads_on_one_model_still_observe_it(tmp_path):
    other = '02b1f23c-5552-7843-c5a5-eb6458233dfb'
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol']); rollout(s, other, ['gpt-6.1-sol'])
    r = run(events(tmp_path / 'e.jsonl', TID, other), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'gpt-6.1-sol' and r['observed_model_matches_requested'] is True


def test_helper_bounds_itself_without_timeout_1(tmp_path):
    """A stalled read ends at the helper's own deadline; it does not rely on timeout(1)."""
    import time
    h = tmp_path / 'h.py'; h.write_text(HELPER.read_text().replace('DEADLINE_S = 20', 'DEADLINE_S = 1'))
    s = tmp_path / 's'; rollout(s, TID, ['gpt-6.1-sol'])
    ev = events(tmp_path / 'e.jsonl', TID)
    stall = ("import importlib.util as u, sys, time\n"
             f"sp = u.spec_from_file_location('h', {str(h)!r}); m = u.module_from_spec(sp); sp.loader.exec_module(m)\n"
             "m.read_rollout = lambda *a: time.sleep(30)\n"
             f"sys.argv = ['h', {str(ev)!r}, '--sessions-dir', {str(s)!r}]\n"
             "try:\n    m.main()\nexcept Exception as e:\n    print(type(e).__name__)\n")
    t = time.time()
    p = subprocess.run([sys.executable, '-c', stall], capture_output=True, text=True, timeout=20)
    assert time.time() - t < 10 and p.stdout.strip() == 'Expired'


@pytest.mark.parametrize('tail', ['{"type":"turn_context","payload":{"model":"gpt-6.1-so', '{"type":"turn_context","payload":null}', '{"type":"turn_context"}', '{"type":"turn_con'])
def test_a_damaged_later_turn_is_unprovable(tmp_path, tail):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'])
    f = next(s.rglob('rollout-*.jsonl'))
    f.write_text(f.read_text() + tail + '\n')
    r = run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown' and r['observed_model_matches_requested'] is None


def test_effort_is_the_final_turns_not_an_earlier_one(tmp_path):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'], effort='high')
    f = next(s.rglob('rollout-*.jsonl'))
    f.write_text(f.read_text() + json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol'}}) + '\n' + json.dumps(ANSWER) + '\n')
    r = run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'gpt-6.1-sol' and r['observed_effort'] == 'unknown'


def test_an_oversized_record_is_bounded_and_unprovable(tmp_path):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'])
    f = next(s.rglob('rollout-*.jsonl'))
    f.write_text(f.read_text() + '{"type":"x","payload":{"pad":"' + 'a' * (33 << 20) + '"}}\n')
    r = run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown'
    ev = tmp_path / 'e2.jsonl'
    ev.write_text('{"pad":"' + 'a' * (33 << 20) + '"}\n' + json.dumps({'type': 'thread.started', 'thread_id': TID}) + '\n')
    rollout(tmp_path / 's2', TID, ['gpt-6.1-sol'])
    assert run(ev, tmp_path / 's2', 'gpt-6.1-sol')['observed_model'] == 'gpt-6.1-sol'


def test_a_turn_the_model_never_answered_is_not_a_model_that_ran(tmp_path):
    """A configured-but-refused turn (e.g. a usage limit) leaves a turn_context and no answer."""
    s = tmp_path / 's'
    rollout(s, TID, [])
    f = next(s.rglob('rollout-*.jsonl'))
    f.write_text(f.read_text() + json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'effort': 'high'}}) + '\n'
                 + json.dumps({'type': 'event_msg', 'payload': {'type': 'error', 'codex_error_info': 'usage_limit_exceeded'}}) + '\n')
    r = run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'unknown' and r['observed_model_matches_requested'] is None


def test_a_refused_later_turn_does_not_leave_the_earlier_model_observed(tmp_path):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'])
    f = next(s.rglob('rollout-*.jsonl'))
    f.write_text(f.read_text() + json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol'}}) + '\n')
    assert run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')['observed_model'] == 'unknown'


def test_threads_with_different_efforts_claim_no_effort(tmp_path):
    other = '02b1f23c-5552-7843-c5a5-eb6458233dfb'
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'], effort='high'); rollout(s, other, ['gpt-6.1-sol'], effort='low')
    r = run(events(tmp_path / 'e.jsonl', TID, other), s, 'gpt-6.1-sol')
    assert r['observed_model'] == 'gpt-6.1-sol' and r['observed_effort'] == 'unknown'


def test_a_stale_usage_snapshot_does_not_prove_an_unanswered_turn(tmp_path):
    s = tmp_path / 's'
    rollout(s, TID, ['gpt-6.1-sol'])
    f = next(s.rglob('rollout-*.jsonl'))
    usage = json.dumps({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 5}}}})
    f.write_text(f.read_text() + usage + '\n' + json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol'}}) + '\n' + usage + '\n')
    assert run(events(tmp_path / 'e.jsonl', TID), s, 'gpt-6.1-sol')['observed_model'] == 'unknown'
