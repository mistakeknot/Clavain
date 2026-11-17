"""After-the-fact B6 observations. Never returns routing advice to dispatch."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
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
                   policy_sha256=hashed(Path(policy).read_bytes().hex())),
                   egress_allowed=False, sources=[str(policy)])
    answer = json.loads(subprocess.run(
        ['clavain-cli', 'decide', '--plugin-root', str(root), '--config', str(policy),
         '--project-root', str(project)], input=json.dumps(request), text=True,
        capture_output=True, check=True, timeout=6).stdout)
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
        saved = estimate if old_cost is not None and new_cost is not None and new_cost < old_cost else None
    row = dict(schema='clavain-learned-router-v1', decision_id=str(uuid.uuid4()),
               s1_decision_id=answer['decision_id'], created_at=stamp(),
               question_id=hashed('learned_router'), role_id=hashed(event['role']),
               native_choice=hashed(native), shadow_choice=hashed(choice),
               agreement=choice == native if choice in seats else None,
               confidence=confidence, mode='shadow', applied='native',
               estimated_input_tokens=estimate, estimated_claude_tokens_saved=saved,
               token_estimate_method='ceil_prompt_characters_div_4_input_only_seat_rank_v1',
               exit_code=event['exit_code'])
    records.append_record(row, record_dir=Path(project) / '.clavain/decisions', project_root=project)


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
