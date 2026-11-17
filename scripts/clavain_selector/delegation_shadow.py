"""Shadow observations for main-thread delegation choices (mk-42j9.7.8).

An instruction call site makes its delegation choice, then calls this helper
with the choice it actually made. The helper never changes that choice and
never prints. It does nothing unless `decision_models.flux_triage.mode` is
exactly `shadow` and the global kill switch is unset. Otherwise it runs
`clavain-cli decide` (egress always false) and appends a companion record, via
the S1 locked private writer, next to the decide record. Every failure,
including a timeout, is silent: the caller's flow is untouched.

Contract: docs/reference/delegation-shadow.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

if __name__ == '__main__':
    # Running as a script puts this directory first; modules here would shadow
    # nothing intended. Use the package root instead.
    sys.path[:] = [str(Path(__file__).resolve().parents[1])] + [
        p for p in sys.path if Path(p or '.').resolve() != Path(__file__).resolve().parent]

import yaml

from clavain_selector import flags, records
from clavain_selector.accounting import digest, stamp

DEADLINE_S = 6  # whole-helper cap, matching the Go wrapper's.
QUESTION_ID = 'flux_triage'
SCHEMA = 'clavain-delegation-shadow-v1'
ESTIMATE_METHOD = 'main_thread_decision_tokens_if_agree_accept_v1'
# Call-site labels. The question text is fixed here so no caller prose is sent.
SITES = {
    'quality-gates': 'Which executor performs this change review?',
    'codex-delegate': 'Which executor role handles this delegated task?',
    'interserve-engine': 'Which dispatch mode fits this task set?',
}
OUTCOMES = frozenset({'success', 'warn', 'failure'})
_ID = re.compile(r'[A-Za-z0-9_.-]{1,64}')
_MAX_TOKENS = 2 ** 40
_WRITE_RESERVE_S = .25


class _Deadline(BaseException):
    pass


def _token_count(value):
    if type(value) is str and re.fullmatch(r'[0-9]{1,13}', value.strip() or 'x'):
        value = int(value)
    return value if type(value) is int and 0 <= value <= _MAX_TOKENS else None


def _clean_state(state):
    """State holds numbers, booleans and short identifiers only: no free text."""
    if not isinstance(state, dict) or len(state) > 16:
        return None
    for key, value in state.items():
        if not isinstance(key, str) or not _ID.fullmatch(key):
            return None
        if isinstance(value, float):
            if not math.isfinite(value):
                return None
        elif type(value) is int:
            if abs(value) > _MAX_TOKENS:
                return None
        elif not (type(value) is bool or (isinstance(value, str) and _ID.fullmatch(value))):
            return None
    return dict(state)


def _clean_candidates(candidates, native):
    try:
        pairs = [(str(i), str(d)) for i, d in candidates]
    except (TypeError, ValueError):
        return None
    ids = [i for i, _ in pairs]
    if not 1 <= len(pairs) <= 16 or len(set(ids)) != len(ids) or native not in ids:
        return None
    if not all(_ID.fullmatch(i) and 0 < len(d) <= 200 for i, d in pairs):
        return None
    return pairs


def _root():
    return Path(__file__).resolve().parents[2]


def _policy_mode(config):
    try:
        data = yaml.safe_load(Path(config).read_text(encoding='utf-8'))
        policy = (data.get('decision_models') or {}).get(QUESTION_ID)
        return policy.get('mode') if isinstance(policy, dict) else None
    except Exception:
        return None


def prepare(*, site, native_choice, candidates, state, config):
    """Return (None, request) when an observation may run, else (reason, None)."""
    if str(os.environ.get(flags.GLOBAL_KILL_SWITCH, '')).strip().lower() == 'off':
        return 'off', None
    if _policy_mode(config) != 'shadow':
        return 'off', None
    pairs = _clean_candidates(candidates, native_choice)
    clean = _clean_state(state)
    if site not in SITES or pairs is None or clean is None:
        return 'invalid_input', None
    request = dict(
        question=dict(id=QUESTION_ID, text=SITES[site],
                      candidates=[dict(id=i, description=d) for i, d in pairs]),
        state=clean, native_choice=native_choice, egress_allowed=False, sources=[])
    return None, request


def build_companion(answer, *, site, question_id, native_choice, candidate_ids,
                    main_thread_tokens, native_outcome):
    """One companion record. Only hashes, numbers and fixed labels; no raw text.

    `agreement` is computed only for a completed observation (reason
    `shadow_mode`); otherwise it is null. Savings count the main thread's own
    decision tokens when that observation agreed at band `accept`, are 0 when it
    would not have been safe to follow, and stay null when the estimate or the
    observation is unknown.
    """
    shadow = answer.get('shadow_choice')
    completed = answer.get('reason') == 'shadow_mode' and isinstance(shadow, str)
    agreement = (shadow == native_choice) if completed else None
    tokens = _token_count(main_thread_tokens)
    if tokens is None or agreement is None:
        saved = None
    else:
        saved = tokens if agreement and answer.get('band') == 'accept' else 0
    confidence = answer.get('confidence')
    latency = answer.get('latency_ms')
    return dict(
        schema=SCHEMA, decision_id=answer['decision_id'], created_at=stamp(), site=site,
        mode='shadow', applied='native', egress_allowed=False, identifier_encoding='sha256',
        question_id=digest(question_id.encode()),
        candidates=[digest(c.encode()) for c in candidate_ids],
        native_choice=digest(native_choice.encode()),
        shadow_choice=digest(shadow.encode()) if isinstance(shadow, str) else None,
        agreement=agreement, backend=answer.get('backend'), reason=answer.get('reason'),
        band=answer.get('band'),
        confidence=float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None,
        latency_ms=latency if type(latency) is int else None,
        main_thread_tokens=tokens, estimated_claude_tokens_saved=saved,
        estimate_method=ESTIMATE_METHOD,
        native_actual_outcome=native_outcome if native_outcome in OUTCOMES else None)


def _find_cli(plugin_root):
    candidates = [os.environ.get('CLAVAIN_CLI'), str(Path(plugin_root) / 'bin' / 'clavain-cli'),
                  shutil.which('clavain-cli')]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _run_decide(cmd, request, timeout):
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        out, _ = proc.communicate(json.dumps(request).encode(), timeout=timeout)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return None, None
    finally:
        # The leader may have exited while descendants still hold its group.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=1)
            except Exception:
                pass


def observe(*, site, native_choice, candidates, state, main_thread_tokens=None,
            native_outcome=None, project_root='.', config=None, plugin_root=None,
            deadline_s=DEADLINE_S):
    """Run one observation. Never raises; `native_choice` is echoed unchanged."""
    start = time.monotonic()
    result = dict(status='inert', reason='off', native_choice=native_choice)
    try:
        plugin_root = Path(plugin_root) if plugin_root else _root()
        config = config or plugin_root / 'config' / 'routing.yaml'
        reason, request = prepare(site=site, native_choice=native_choice,
                                  candidates=candidates, state=state, config=config)
        if request is None:
            result['reason'] = reason
            return result
        result.update(status='failed', reason='cli_unavailable')
        cli = _find_cli(plugin_root)
        if cli is None:
            return result
        root = Path(project_root).resolve()
        cmd = [cli, 'decide', '--plugin-root', str(plugin_root), '--config', str(config),
               '--project-root', str(root)]
        remaining = deadline_s - (time.monotonic() - start) - _WRITE_RESERVE_S
        result['reason'] = 'timeout'
        if remaining <= 0:
            return result
        code, out = _run_decide(cmd, request, remaining)
        if code is None:
            return result
        result['reason'] = 'backend_unavailable'
        if code != 0:
            return result
        result['reason'] = 'invalid_response'
        answer = json.loads(out)
        if not isinstance(answer, dict) or answer.get('fallback') is not True:
            return result
        if not isinstance(answer.get('decision_id'), str):
            result['reason'] = str(answer.get('reason') or 'no_record')[:40]
            return result
        companion = build_companion(
            answer, site=site, question_id=QUESTION_ID, native_choice=native_choice,
            candidate_ids=[c['id'] for c in request['question']['candidates']],
            main_thread_tokens=main_thread_tokens, native_outcome=native_outcome)
        result['reason'] = 'record_unwritable'
        records.append_record(companion, record_dir=root / '.clavain' / 'decisions',
                              project_root=root)
        result.update(status='observed', reason=companion['reason'],
                      decision_id=answer['decision_id'])
    except Exception:
        # Never echo exception text: it may carry provider or path detail.
        if result['status'] != 'observed':
            result['status'] = 'failed' if result['reason'] != 'off' else 'inert'
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

    def exit(self, status=0, message=None):
        raise ValueError(message or 'exit')


def parse_args(argv):
    p = _Parser(prog='delegation_shadow.py', add_help=False)
    p.add_argument('--site', required=True)
    p.add_argument('--native', required=True)
    p.add_argument('--candidate', action='append', default=[])
    p.add_argument('--state', action='append', default=[])
    p.add_argument('--main-thread-tokens', default='')
    p.add_argument('--native-outcome', default='')
    p.add_argument('--project-root')
    p.add_argument('--config')
    p.add_argument('--foreground', action='store_true')
    ns = p.parse_args(argv)
    ns.pairs = [tuple(c.split('=', 1)) for c in ns.candidate]
    if any(len(c) != 2 for c in ns.pairs) or any('=' not in s for s in ns.state):
        raise ValueError('malformed pair')
    ns.state_map = {}
    for item in ns.state:
        key, raw = item.split('=', 1)
        if re.fullmatch(r'-?[0-9]{1,15}', raw):
            ns.state_map[key] = int(raw)
        elif re.fullmatch(r'-?[0-9]+\.[0-9]+', raw):
            ns.state_map[key] = float(raw)
        else:
            ns.state_map[key] = {'true': True, 'false': False}.get(raw, raw)
    return ns


def _alarm(signum, frame):
    raise _Deadline


def main(argv=None, project_root=None, config=None):
    """Always returns 0 and prints nothing. Detaches unless --foreground."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        ns = parse_args(argv)
        root = Path(project_root or ns.project_root or '.').resolve()
        config = config or ns.config or _root() / 'config' / 'routing.yaml'
        if ns.foreground:
            signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL, DEADLINE_S)
            observe(site=ns.site, native_choice=ns.native, candidates=ns.pairs,
                    state=ns.state_map, main_thread_tokens=ns.main_thread_tokens,
                    native_outcome=ns.native_outcome, project_root=root, config=config)
            return 0
        reason, request = prepare(site=ns.site, native_choice=ns.native, candidates=ns.pairs,
                                  state=ns.state_map, config=config)
        if request is None:
            return 0
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(
            [str(Path(__file__).resolve().parents[1])] + [p for p in [os.environ.get('PYTHONPATH')] if p]))
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), '--foreground', *argv,
             '--project-root', str(root), '--config', str(config)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True, env=env)
    except BaseException:
        pass
    return 0


if __name__ == '__main__':
    main()
    sys.exit(0)
