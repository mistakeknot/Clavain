"""After-the-fact B6 observations. Never returns routing advice to dispatch."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
import uuid

import yaml

from clavain_selector import records
from clavain_selector.accounting import stamp


def hashed(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def seat_cost(profile):
    # Design choice: ordinal proxy, not a price or a quality judgement.
    if profile.get('backend') == 'codex':
        return 0
    if profile.get('backend') == 'claude':
        model = profile.get('model', '')
        for family, rank in [('haiku', 1), ('sonnet', 2), ('opus', 3)]:
            if family in model:
                return rank
    return None


def observe(root, policy, project, event):
    started = time.monotonic()
    if os.environ.get('CLAVAIN_SELECTOR', '').strip().lower() == 'off':
        return
    settings = yaml.safe_load(Path(policy).read_text())['decision_models']['learned_router']
    # This track intentionally has no hosted path, even in an opted-in policy.
    if settings.get('mode') != 'shadow' or settings.get('backend', 'heuristic') != 'heuristic':
        return
    route = event['route']
    seats = [{k: route[k] for k in ('profile_ref', 'profile')}] + route.get('fallback_chain', [])
    seats = {s['profile_ref']: s['profile'] for s in seats}
    native = event['native']
    if native not in seats or len(seats) > 16:
        return
    request = dict(question=dict(id='learned_router', text='Choose a dispatch model seat',
                   candidates=[dict(id=k, description=f"{v['backend']} {v['model']}") for k, v in seats.items()]),
                   native_choice=native, state=dict(role_sha256=hashed(event['role']),
                   policy_sha256=hashlib.sha256(Path(policy).read_bytes()).hexdigest()),
                   egress_allowed=False, sources=[str(policy)])
    answer = json.loads(subprocess.run(
        ['clavain-cli', 'decide', '--plugin-root', str(root), '--config', str(policy),
         '--project-root', str(project)], input=json.dumps(request), text=True,
        capture_output=True, check=True, timeout=max(.001, 6 - (time.monotonic() - started))).stdout)
    if not answer.get('decision_id'):
        return
    choice = answer.get('shadow_choice')
    confidence = answer.get('confidence', 0)
    proposed = seats.get(choice, {})
    original = seats[native]
    chars = event.get('prompt_chars')
    estimate = (chars + 3) // 4 if type(chars) is int and chars >= 0 else None
    old_cost, new_cost = seat_cost(original), seat_cost(proposed)
    saved = 0
    if confidence >= .6 and original.get('backend') == 'claude' and choice != native:
        if old_cost is None or new_cost is None:
            saved = None
        elif new_cost < old_cost:
            saved = estimate
    observed = answer.get('reason') == 'shadow_mode'
    row = dict(schema='clavain-learned-router-v1', decision_id=str(uuid.uuid4()),
               s1_decision_id=answer['decision_id'], created_at=stamp(),
               question_id=hashed('learned_router'), role_id=hashed(event['role']),
               native_choice=hashed(native), shadow_choice=hashed(choice),
               agreement=choice == native if observed and choice in seats else None,
               confidence=confidence, mode='shadow', applied='native',
               estimated_input_tokens=estimate, estimated_claude_tokens_saved=saved,
               token_estimate_method='ceil_prompt_characters_div_4_input_only_seat_rank_v1',
               exit_code=event['exit_code'])
    # The observer runs on the main thread of its own detached process. Bound
    # lock acquisition and append by the remaining six-second helper budget,
    # at most one second, without changing the shared writer's semantics.
    def expired(signum, frame):
        raise TimeoutError('observer append deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(.001, min(1, 6 - (time.monotonic() - started))))
    try:
        records.append_record(row, record_dir=Path(project).resolve() / '.clavain/decisions', project_root=project, max_bytes=records.PROJECT_LOG_MAX_BYTES)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main():
    try:
        root, policy, project = map(Path, sys.argv[1:])
        event = json.loads(sys.stdin.read(90001))
        observe(root, policy, project, event)
    except Exception:
        # Best effort only: never echo state, credentials, or provider errors.
        pass


if __name__ == '__main__':
    main()
