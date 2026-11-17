"""Closed hosted-observer contract, checked before credential or egress work."""
import re
import hashlib
import hmac
import os
from pathlib import Path

VERSION = 'shadow-observer-v1'
SITES = {
    'route-4b': ('sprint', 'work'),
    'route-staleness': ('implemented', 'not_implemented'),
    'route-sweep': ('implemented', 'not_implemented'),
    'sprint-lane-intent': ('contradicts', 'aligned'),
}


def enabled(policy):
    return policy.get('backend') == 'jev' and policy.get('privacy_contract') == VERSION


def project_scope(root):
    """Use the shared Git directory so worktrees cannot multiply the daily cap."""
    from clavain_selector.egress import _resolve_git_config_path
    root = Path(root).resolve()
    for parent in (root, *root.parents):
        config = _resolve_git_config_path(parent)
        if config is not None:
            return config.resolve().parent
    raise ValueError('unknown project')


def wire_state(state):
    """Fresh per-call pseudonyms prevent dictionary matching and correlation."""
    key = os.urandom(32)
    return {k: hmac.new(key, (k + ':' + v).encode(), hashlib.sha256).hexdigest()
            if k in ('subject_sha256', 'loop_hash') else v for k, v in state.items()}


def _count(value, low=0, high=10**9):
    return type(value) is int and low <= value <= high


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate(obj):
    """Reject extras as well as bad values; never sanitize away forbidden data.

    Native choice and accounting metadata are local only. The accepted question
    and state are the sole inputs to the existing admitted request serializer.
    """
    keys = {'privacy_contract', 'question', 'state', 'native_choice', 'egress_allowed', 'sources'}
    if type(obj) is not dict or set(obj) - {'observation_metadata'} != keys:
        raise ValueError
    if obj['privacy_contract'] != VERSION or obj['sources'] != [] or obj['egress_allowed'] is not True:
        raise ValueError
    q, state = obj['question'], obj['state']
    if type(q) is not dict or set(q) != {'id', 'text', 'candidates'} or type(state) is not dict:
        raise ValueError
    if q['id'] == 'route':
        if set(state) != {'site_id', 'subject_sha256', 'input_bytes', 'output_bytes', 'batch_size'}:
            raise ValueError
        if type(state['site_id']) is not str or state['site_id'] not in SITES:
            raise ValueError
        if not (_hash(state['subject_sha256']) and _count(state['input_bytes'])
                and _count(state['output_bytes']) and _count(state['batch_size'], 1, 1000)):
            raise ValueError
        choices = SITES[state['site_id']]
        text = 'Observe native classification'
        candidates = [dict(id=c, description=c) for c in choices]
    elif q['id'] == 'review_exit':
        if 'observation_metadata' in obj or set(state) != {'findings', 'loop_hash'}:
            raise ValueError
        if not _hash(state['loop_hash']) or not (state['findings'] is None or _count(state['findings'])):
            raise ValueError
        choices = ('exit', 'continue')
        text = 'Could this review round have exited early?'
        candidates = [dict(id='exit', description='Exit the review loop'),
                      dict(id='continue', description='Continue reviewing')]
    else:
        raise ValueError
    if q['text'] != text or q['candidates'] != candidates or obj['native_choice'] not in choices:
        raise ValueError
