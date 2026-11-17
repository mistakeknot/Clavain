"""S1 decision observations. No backend result can authorize an action.

Input carries a typed candidate question, JSON state, and native_choice (the
answer today's caller chose). State is never recorded. Hosted state requires
explicit egress_allowed=true in addition to the selector's whole-request guard.
"""
from __future__ import annotations

import json
import datetime as dt
import os
from pathlib import Path
import re
import sys
import time
import uuid

from clavain_selector import contract, credentials, egress, flags, jev_client as j, records
from clavain_selector.accounting import AttemptLog, digest, stamp
from clavain_selector import observer_privacy


def band(confidence):
    return 'accept' if confidence >= .8 else 'escalate' if confidence < .6 else 'review'


def observation_metadata(value):
    """Closed, opt-in numeric/hash projection; no caller-provided prose."""
    counts = {'input_bytes', 'output_bytes', 'batch_size', 'estimate_method',
              'estimated_claude_tokens_saved', 'observed_claude_tokens_saved'}
    hashes = {'site_sha256', 'subject_sha256'}
    if type(value) is not dict or set(value) != counts | hashes:
        raise ValueError
    if any(type(value[k]) is not int or not 0 <= value[k] <= 10**9 for k in counts):
        raise ValueError
    if any(type(value[k]) is not str or not re.fullmatch('[0-9a-f]{64}', value[k])
           for k in hashes):
        raise ValueError
    if not 1 <= value['batch_size'] <= 1000 or value['estimate_method'] != 1:
        raise ValueError
    divisor = 4 * value['batch_size']
    estimate = (value['input_bytes'] + value['output_bytes'] + divisor - 1) // divisor
    if value['estimated_claude_tokens_saved'] != estimate or value['observed_claude_tokens_saved'] != 0:
        raise ValueError
    return dict(value)


def decide(obj, policy, project_root):
    start = time.monotonic_ns()
    log = AttemptLog()
    native = obj.get('native_choice') if isinstance(obj, dict) else None
    backend = policy.get('backend', 'heuristic')
    backend = backend if backend in ('jev', 'heuristic') else 'unsupported'
    result = dict(choice=native, probs={}, confidence=0., fallback=True,
                  band='escalate', backend=backend, reason='off')
    mode = policy.get('mode', 'off')
    if str(os.environ.get(flags.GLOBAL_KILL_SWITCH, '')).strip().lower() == 'off':
        return result
    if mode != 'shadow':
        result['reason'] = 'enforce_disabled' if mode == 'enforce' else 'off'
        return result
    request = None
    admitted = None
    metadata = None
    hosted_observer = 'privacy_contract' in policy or (isinstance(obj, dict) and 'privacy_contract' in obj)
    if hosted_observer:
        try:
            observer_privacy.validate(obj)
        except (ValueError, TypeError, KeyError):
            result['reason'] = 'invalid_input'
            return result
        if not observer_privacy.enabled(policy):
            result['reason'] = 'egress_not_authorized'
            return result
    if isinstance(obj, dict) and 'observation_metadata' in obj:
        try:
            metadata = observation_metadata(obj['observation_metadata'])
        except (ValueError, TypeError):
            result['reason'] = 'invalid_input'
            return result
        # Legacy metadata packets stay local even if config changed after
        # preflight. Hosted packets require the independent closed contract.
        if backend != 'heuristic' and not hosted_observer:
            result['reason'] = 'unsupported_backend'
            return result
    try:
        question = obj['question']
        qid = question['id']
        if not isinstance(qid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', qid):
            raise ValueError
        if not isinstance(obj['state'], dict) or not isinstance(question['text'], str):
            raise ValueError
        candidates = tuple(contract.Candidate(c['id'], c['description'], None, 'shadow')
                           for c in question['candidates'])
        if native not in [c.id for c in candidates]:
            raise ValueError
        request = contract.SelectionRequest(
            integration='decision_models', point=contract.Point.LIBRARY,
            task=question['text'], context=json.dumps(observer_privacy.wire_state(obj['state'])
                if hosted_observer else obj['state'], allow_nan=False),
            candidates=candidates, task_revision='shadow',
            session=contract.SessionRef('decide'),
            sources=tuple(Path(p) for p in obj.get('sources', [])),
            project_root=Path(project_root).resolve())
        if contract.validate_request(request) is not None:
            raise ValueError
        # Scan before even the local record projection: no prompt text is logged.
        if result['backend'] == 'heuristic':
            # Conservative deterministic baseline: agree with today's answer.
            result.update(probs={c.id: float(c.id == native) for c in candidates},
                          confidence=1., band='accept', reason='shadow_mode')
        elif result['backend'] != 'jev':
            result['reason'] = 'unsupported_backend'
        elif obj.get('egress_allowed') is not True:
            result['reason'] = 'egress_not_authorized'
        else:
            admitted = egress.admit(request, high_entropy=True)
            if isinstance(admitted, egress.Refusal):
                result['reason'] = 'egress_refused'
            else:
                _jev(request, obj, policy, result, log)
    except (KeyError, ValueError, TypeError, AttributeError):
        result['reason'] = 'invalid_input'
    except Exception:
        # Never echo exception text: credentials/provider responses may be in it.
        result['reason'] = 'internal_error'
    finally:
        log.finalize_open()
    result['latency_ms'] = (time.monotonic_ns() - start) // 1_000_000
    result.update(log.to_fields())
    result['shadow_choice'] = result['choice']
    result['choice'] = native
    # Records reuse the existing locked append, permissions and outcome join.
    # Only identifiers and hashes leave this function; raw state/text never do.
    record = dict(schema='clavain-decide-v1', decision_id=str(uuid.uuid4()),
                  created_at=stamp(), question_id=None, candidates=[],
                  native_choice=None, decide_answer=None, observed_outcome=None,
                  mode='shadow', applied='native', cost=None, **result)
    if request is not None:
        record['question_id'] = digest(str(obj['question']['id']).encode())
        record['candidates'] = [digest(c.id.encode()) for c in request.candidates]
        record['native_choice'] = digest(str(native).encode())
        record['decide_answer'] = dict(choice=digest(str(result['shadow_choice']).encode()),
                                       confidence=result['confidence'],
                                       probs={digest(k.encode()): v for k, v in result['probs'].items()})
        record['identifier_encoding'] = 'sha256'
    # Avoid duplicating unscanned identifiers from the output in the log.
    record.pop('choice', None)
    record.pop('probs', None)
    record.pop('shadow_choice', None)
    if metadata is not None:
        record.update(metadata)
    if hosted_observer:
        record['privacy_contract'] = observer_privacy.VERSION
    try:
        records.append_record(record, record_dir=Path(project_root).resolve() / '.clavain' / 'decisions',
                              project_root=project_root)
        result['decision_id'] = record['decision_id']
    except Exception:
        result['reason'] = 'record_unwritable'
    return result


def _jev(request, obj, policy, result, log):
    # A stable project/day cap cannot be reset by changing a caller session.
    registry = flags.load_registry(Path(__file__).resolve().parents[2] / 'config/selector-integrations.json')
    entry = registry.get('integrations', {}).get('decision_models', {})
    if entry.get('enabled') is not True:
        result['reason'] = 'registry_disabled'
        return
    limit = entry.get('daily_budget', 0)
    if type(limit) is not int or limit < 1:
        result['reason'] = 'budget_exhausted'
        return
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    scope = observer_privacy.project_scope(request.project_root) if 'privacy_contract' in obj else request.project_root
    budget = j.Budget(f'decide:{scope}:{day}', 'decision_models', limit=min(8, limit))
    if budget.consume() is not None:
        result['reason'] = 'budget_exhausted'
        return
    breaker = j.Breaker()
    if breaker.check() is not None:
        result['reason'] = 'circuit_open'
        return
    try:
        if 'privacy_contract' in obj:
            # Hosted observers never redirect credentials outside this directory.
            credentials.secrets_file_path().resolve().relative_to((Path.home() / '.config/jev').resolve())
        key = credentials.load()
    except (credentials.CredentialUnavailable, ValueError, OSError):
        result['reason'] = 'credential_unavailable'
        return
    admitted = egress.admit(request, key_literal=key.reveal(), high_entropy=True)
    if isinstance(admitted, egress.Refusal):
        result['reason'] = 'egress_refused'
        return
    call = j.JevCall.build(admitted, fit_questions=False,
                          deadline=j.Deadline.start(int(policy.get('deadline_ms', 1500))))
    response = j.JevClient(key).call(call, log=log)
    breaker.record(response)
    if isinstance(response, j.JevFailure):
        result['reason'] = response.reason.value
        return
    answer = response.response.select
    result.update(choice=answer.choice, probs=dict(answer.probabilities),
                  confidence=answer.confidence, band=band(answer.confidence))
    verdict = j.apply_floors(response.response, j.Floors(confidence=.8, fit=0.), call.battery)
    result['reason'] = verdict.reason.value if isinstance(verdict, j.Abstention) else 'shadow_mode'
    if isinstance(verdict, j.Selection):
        result['choice'] = verdict.candidate_id


def main():
    try:
        # The Go adapter wraps up to MAX_REQUEST_BYTES with config metadata.
        # Bound the envelope separately so wrapping never truncates a request.
        raw = sys.stdin.buffer.read(2 * contract.MAX_REQUEST_BYTES + 1)
        if len(raw) > 2 * contract.MAX_REQUEST_BYTES:
            raise ValueError
        envelope = json.loads(raw)
        result = decide(envelope['request'], envelope['policy'], envelope['project_root'])
    except Exception:
        result = dict(choice=None, probs={}, confidence=0., fallback=True, reason='invalid_input')
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
