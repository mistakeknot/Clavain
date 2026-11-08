#!/usr/bin/env python3
"""Observe-mode phase evidence ledger (mk-4xzwm.1).

Records what each session actually did and reports, without ever blocking,
when workflow-phase evidence is missing:

  read-before-edit   an existing file was edited with no earlier Read/Edit/Write of it
  verify-after-edit  code was edited and no verification command ran afterwards
  decision-context   code was edited and no valid decision context was recorded

The ledger is an append-only JSONL file per session. Each row carries the
OODARC leg (`oodarc_role`) using the same vocabulary as intercore's
PhaseToOODARCRole, so rows join with the observation stream instead of
starting a second ledger.

Modes (CLAVAIN_PHASE_EVIDENCE_MODE): observe (default, record and warn),
off (do nothing). There is deliberately no enforcing mode yet; promoting a
rule to a gate is a separate decision made from ledger data.

Commands:
  hook pre|post|stop   Claude Code hook; JSON payload on stdin, exit 0 always
  check [--session S] [--phase P] [--json]
                       report missing evidence for a session (and the OODARC
                       leg a lifecycle phase maps to); exit 0 always
  dispatch --context FILE [--role R]
                       record a dispatch and warn if its decision context is
                       missing or unusable; exit 0 always
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Mirrors intercore pkg/phase/roles.go PhaseToOODARCRole.
PHASE_ROLE = {
    'brainstorm': 'observe',
    'brainstorm-reviewed': 'observe',
    'strategized': 'orient',
    'planned': 'decide',
    'executing': 'act',
    'review': 'observe',
    'polish': 'act',
    'reflect': 'reflect+compound',
    'done': 'terminal',
}
# Evidence a lifecycle phase's OODARC leg expects to exist before it is entered.
LEG_NEEDS = {
    'act': ['decision-context'],
    'reflect+compound': ['verify-after-edit'],
    'terminal': ['verify-after-edit'],
}
TOOL_ROLE = {'Read': 'observe', 'Grep': 'observe', 'Glob': 'observe',
             'Edit': 'act', 'Write': 'act', 'MultiEdit': 'act', 'NotebookEdit': 'act'}
EDIT_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
VERIFY = re.compile(
    r'(^|[\s;&|(])(pytest|bats|shellcheck|ruff|mypy|tsc|eslint|golangci-lint|'
    r'go\s+(test|vet)|cargo\s+(test|check|clippy)|(npm|pnpm|yarn|bun)\s+(run\s+)?(test|lint|check)|'
    r'make\s+(test|check|lint)|uv\s+run\s+(pytest|ruff|mypy)|python3?\s+-m\s+(pytest|py_compile|unittest)|'
    r'bash\s+-n|git\s+diff\s+--check)\b')
DOC_SUFFIXES = {'.md', '.txt', '.rst'}
CONTEXT_REF = re.compile(r'--context-file|CLAVAIN_DECISION_CONTEXT|route\s+dispatch')
EVIDENCE = ('read-before-edit', 'verify-after-edit', 'decision-context')


def mode():
    return os.environ.get('CLAVAIN_PHASE_EVIDENCE_MODE', 'observe')


def state_dir():
    base = os.environ.get('CLAVAIN_PHASE_EVIDENCE_DIR')
    if base:
        return Path(base)
    root = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(root) / 'clavain' / 'phase-evidence'


def session_id(payload=None):
    sid = (payload or {}).get('session_id') or os.environ.get('DISPATCH_SESSION_ID') \
        or os.environ.get('CLAUDE_SESSION_ID') or 'no-session'
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(sid))[:96]


def ledger_path(sid):
    return state_dir() / f'{sid}.jsonl'


def append(sid, row):
    row = dict(row, ts=int(time.time()))
    path = ledger_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as fh:
        fh.write(json.dumps(row, sort_keys=True) + '\n')


def load(sid):
    path = ledger_path(sid)
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def norm(path):
    try:
        return os.path.realpath(path)
    except (TypeError, ValueError):
        return ''


def valid_context(path):
    """A decision context is usable when it is JSON with `reasons` and a nonempty `rationale`."""
    if not path:
        return False
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and isinstance(data.get('reasons'), list) \
        and isinstance(data.get('rationale'), str) and bool(data['rationale'].strip())


def is_code(path):
    return Path(path).suffix.lower() not in DOC_SUFFIXES


def analyse(rows):
    """Return the list of missing-evidence findings for a session's rows."""
    findings = []
    seen = set()
    last_edit = last_verify = -1
    edits = 0
    context = False
    for i, row in enumerate(rows):
        kind = row.get('kind')
        if kind == 'missing' and row.get('evidence') == 'read-before-edit':
            findings.append({'evidence': 'read-before-edit', 'detail': row.get('path', '')})
        if kind in ('read', 'edit'):
            seen.add(row.get('path'))
        if kind == 'edit' and row.get('code'):
            last_edit = i
            edits += 1
        if kind == 'verify':
            last_verify = i
        if row.get('decision_context') or kind == 'context':
            context = True
    if edits and last_verify < last_edit:
        findings.append({'evidence': 'verify-after-edit',
                         'detail': f'{edits} code edit(s), none followed by a verification command'})
    if edits and not context:
        findings.append({'evidence': 'decision-context',
                         'detail': 'code was edited with no valid decision context recorded'})
    return findings


def message(findings):
    names = ', '.join(sorted({f['evidence'] for f in findings}))
    lines = [f'phase evidence missing (observe mode, not blocking): {names}']
    lines += [f"  - {f['evidence']}: {f['detail']}" for f in findings[:6]]
    return '\n'.join(lines)


def emit(text):
    sys.stdout.write(json.dumps({'systemMessage': text}) + '\n')


def hook(event):
    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    sid = session_id(payload)
    tool = payload.get('tool_name') or ''
    inp = payload.get('tool_input') or {}
    if event == 'stop':
        if payload.get('stop_hook_active'):
            return 0
        rows = load(sid)
        findings = [f for f in analyse(rows) if f['evidence'] != 'read-before-edit']
        last_edit = max((i for i, r in enumerate(rows) if r.get('kind') == 'edit'), default=-1)
        last_warn = max((i for i, r in enumerate(rows) if r.get('kind') == 'warned'), default=-1)
        if findings and last_warn < last_edit:
            append(sid, {'kind': 'warned', 'evidence': sorted({f['evidence'] for f in findings})})
            emit(message(findings))
        return 0
    base = {'tool': tool, 'oodarc_role': TOOL_ROLE.get(tool, 'act' if tool == 'Bash' else 'observe'),
            'decision_context': valid_context(os.environ.get('CLAVAIN_DECISION_CONTEXT'))}
    path = norm(inp.get('file_path') or inp.get('notebook_path') or '')
    if event == 'pre' and tool in EDIT_TOOLS and path:
        known = {r.get('path') for r in load(sid) if r.get('kind') in ('read', 'edit')}
        if os.path.exists(path) and path not in known:
            append(sid, dict(base, kind='missing', evidence='read-before-edit', path=path))
            emit(f'phase evidence missing (observe mode, not blocking): read-before-edit: {path}')
        return 0
    if event != 'post':
        return 0
    if tool == 'Read' and path:
        append(sid, dict(base, kind='read', path=path))
    elif tool in EDIT_TOOLS and path:
        append(sid, dict(base, kind='edit', path=path, code=is_code(path)))
    elif tool == 'Bash':
        cmd = str(inp.get('command') or '')
        if VERIFY.search(cmd):
            append(sid, dict(base, kind='verify', command=cmd[:200]))
        if CONTEXT_REF.search(cmd):
            append(sid, dict(base, kind='context', command=cmd[:200]))
    return 0


def check(args):
    sid = re.sub(r'[^A-Za-z0-9._-]', '_', args.session) if args.session else session_id()
    rows = load(sid)
    findings = analyse(rows)
    role = PHASE_ROLE.get(args.phase or '')
    if args.phase and role is None:
        findings = findings + [{'evidence': 'unknown-phase', 'detail': args.phase}]
    needs = LEG_NEEDS.get(role, [])
    relevant = [f for f in findings if f['evidence'] in needs or f['evidence'] == 'unknown-phase'] \
        if args.phase else findings
    report = {'session': sid, 'mode': mode(), 'rows': len(rows), 'phase': args.phase,
              'oodarc_role': role, 'missing': relevant}
    if args.json:
        print(json.dumps(report, sort_keys=True))
    elif relevant:
        print(message(relevant), file=sys.stderr)
    return 0


def dispatch(args):
    ok = valid_context(args.context)
    detail = 'ok' if ok else ('missing' if not args.context else 'unusable')
    append(session_id(), {'kind': 'dispatch', 'role': args.role or '', 'oodarc_role': 'act',
                          'decision_context': ok, 'context_state': detail})
    if not ok:
        print(f'phase evidence missing (observe mode, not blocking): decision-context {detail} '
              f'for dispatch; record JSON reasons and a nonempty rationale', file=sys.stderr)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or '').splitlines()[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('hook'); p.add_argument('event', choices=['pre', 'post', 'stop'])
    p = sub.add_parser('check'); p.add_argument('--session'); p.add_argument('--phase')
    p.add_argument('--json', action='store_true')
    p = sub.add_parser('dispatch'); p.add_argument('--context', default=''); p.add_argument('--role')
    args = parser.parse_args(argv)
    if mode() == 'off':
        return 0
    try:
        if args.cmd == 'hook':
            return hook(args.event)
        return check(args) if args.cmd == 'check' else dispatch(args)
    except Exception as exc:  # observe mode must never break a session
        print(f'phase-evidence: {exc}', file=sys.stderr)
        return 0


if __name__ == '__main__':
    sys.exit(main())
