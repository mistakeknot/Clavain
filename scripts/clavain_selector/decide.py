"""S1 decision observations. No backend result can authorize an action.

Input carries a typed candidate question, JSON state, and native_choice (the
answer today's caller chose). State is never recorded. Hosted state requires
explicit egress_allowed=true in addition to the selector's whole-request guard.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import time
import uuid

from clavain_selector import contract, credentials, egress, jev_client as j, records
from clavain_selector.accounting import AttemptLog, digest, stamp


def band(confidence):
    return 'accept' if confidence >= .8 else 'escalate' if confidence < .6 else 'review'


def decide(obj, policy, project_root):
    start = time.monotonic_ns()
    log = AttemptLog()
    native = obj.get('native_choice') if isinstance(obj, dict) else None
    backend = policy.get('backend', 'heuristic')
    backend = backend if backend in ('jev', 'heuristic') else 'unsupported'
    result = dict(choice=native, probs={}, confidence=0., fallback=True,
                  band='escalate', backend=backend, reason='off')
    mode = policy.get('mode', 'off')
    if mode != 'shadow':
        result['reason'] = 'enforce_disabled' if mode == 'enforce' else 'off'
        return result
    request = None
    admitted = None
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
            task=question['text'], context=json.dumps(obj['state'], allow_nan=False),
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
        record['decide_answer'] = dict(choice=digest(str(result['choice']).encode()),
                                       confidence=result['confidence'],
                                       probs={digest(k.encode()): v for k, v in result['probs'].items()})
        record['identifier_encoding'] = 'sha256'
    # Avoid duplicating unscanned identifiers from the output in the log.
    record.pop('choice', None)
    record.pop('probs', None)
    try:
        records.append_record(record, record_dir=Path(project_root) / '.clavain' / 'decisions')
        result['decision_id'] = record['decision_id']
    except Exception:
        result['reason'] = 'record_unwritable'
    return result


def _jev(request, obj, policy, result, log):
    # Same shared breaker and conservative call budget as selector.select.
    budget = j.Budget(str(obj.get('session_id', 'decide')), 'decision_models', limit=8)
    if budget.consume() is not None:
        result['reason'] = 'budget_exhausted'
        return
    breaker = j.Breaker()
    if breaker.check() is not None:
        result['reason'] = 'circuit_open'
        return
    try:
        key = credentials.load()
    except credentials.CredentialUnavailable:
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
        envelope = json.loads(sys.stdin.buffer.read(contract.MAX_REQUEST_BYTES + 1))
        result = decide(envelope['request'], envelope['policy'], envelope['project_root'])
    except Exception:
        result = dict(choice=None, probs={}, confidence=0., fallback=True, reason='invalid_input')
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
