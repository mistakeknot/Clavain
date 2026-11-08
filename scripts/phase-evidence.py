#!/usr/bin/env python3
"""Observe-mode phase evidence ledger (mk-4xzwm.1).

Records what each session actually did and reports, without ever blocking,
when workflow-phase evidence is missing:

  read-before-edit   an existing code file was edited with no earlier Read/Edit/Write of it
  verify-after-edit  code was edited and no verification command ran afterwards
  decision-context   code was edited and no valid decision context was recorded

Documentation files (.md .txt .rst) are exempt from all three rules.

Storage is private and bounded. Per session there is an append-only JSONL
ledger (an audit trail, capped in size) and a small summary file that the
hooks read and update, so the cost of a hook call does not grow with the
length of the session. The state directory is created 0700 and its files 0600
whatever the umask. Rows hold hashes and short kinds only: no file paths, no
command text. Session files older than 14 days, or beyond the newest 200,
are pruned when a new session starts. Each ledger is capped at 256 KiB.

Each row carries the OODARC leg (`oodarc_role`) using the same vocabulary as
intercore's PhaseToOODARCRole, so rows join with the observation stream
instead of starting a second ledger.

Modes (CLAVAIN_PHASE_EVIDENCE_MODE): observe (default, record and warn),
off (do nothing). There is deliberately no enforcing mode yet; promoting a
rule to a gate is a separate decision made from ledger data.

Every failure degrades silently: observe mode must never break, slow or
print noise into a session. Commands:
  hook pre|post|stop   Claude Code hook; JSON payload on stdin, exit 0 always
  check [--session S] [--phase P] [--json]
                       report missing evidence for a session (and the OODARC
                       leg a lifecycle phase maps to); exit 0 always
  dispatch --context FILE [--role R]
                       record a dispatch and warn if its decision context is
                       missing or unusable; exit 0 always
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import shlex
import stat
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
DOC_SUFFIXES = {'.md', '.txt', '.rst'}

# Bounds. Every read and every file the hooks touch is capped.
MAX_STDIN = 4 << 20
MAX_LEDGER = 256 << 10
MAX_SUMMARY = 1 << 20
MAX_CONTEXT = 64 << 10
MAX_KNOWN = 2000
MAX_SESSIONS = 200
MAX_AGE = 14 * 86400
MAX_COMMAND = 4096

SHELL_BREAK = {';', ';;', '&&', '||', '|', '|&', '&', '(', ')'}
WRAPPERS = {'nice', 'ionice', 'timeout', 'time', 'command', 'env', 'exec', 'nohup', 'stdbuf', 'sudo'}
ASSIGN = re.compile(r'^[A-Za-z_]\w*=')
OPTION_ARG = re.compile(r'^(-.*|\d+(\.\d+)?[smhd]?)$')
BARE_VERIFIERS = {'pytest', 'bats', 'shellcheck', 'ruff', 'mypy', 'tsc', 'eslint', 'golangci-lint'}
PACKAGE_RUNNERS = {'npm', 'pnpm', 'yarn', 'bun'}
# Invocations of a bare verifier that do not verify anything: they print a version or
# help text, list or collect, write config, or (ruff format) rewrite files without checking.
NO_VERIFY_FLAGS = {
    'pytest': {'--version', '-V', '--help', '-h', '--fixtures', '--fixtures-per-test',
               '--markers', '--collect-only', '--collectonly', '--co', '--setup-plan'},
    'bats': {'--version', '-v', '--help', '-h'},
    'shellcheck': {'--version', '-V', '--help'},
    'ruff': {'--version', '-V', '--help', '-h'},
    'mypy': {'--version', '-V', '--help', '-h'},
    'tsc': {'--version', '-v', '--help', '-h', '--init', '--showConfig', '--all'},
    'eslint': {'--version', '-v', '--help', '-h', '--init', '--print-config'},
    'golangci-lint': {'--version', '--help', '-h'},
}
NO_VERIFY_SUBCOMMANDS = {
    'ruff': {'version', 'help', 'clean', 'server', 'config', 'linter', 'rule', 'analyze',
             'generate-shell-completion'},
    'golangci-lint': {'version', 'help', 'linters', 'cache', 'config', 'completion'},
}


def mode():
    return os.environ.get('CLAVAIN_PHASE_EVIDENCE_MODE', 'observe')


def state_dir():
    base = os.environ.get('CLAVAIN_PHASE_EVIDENCE_DIR')
    if base:
        return Path(base)
    root = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(root) / 'clavain' / 'phase-evidence'


def digest(text, size=16):
    return hashlib.sha256(str(text).encode('utf-8', 'replace')).hexdigest()[:size]


def safe_sid(raw):
    """Filename-safe session key. Anything altered or truncated gets a hash suffix so
    two different raw ids never share a file."""
    raw = str(raw)
    clean = re.sub(r'[^A-Za-z0-9._-]', '_', raw)
    if clean == raw and len(clean) <= 64 and clean not in ('', '.', '..'):
        return clean
    return clean[:48] + '-' + digest(raw)


def session_id(payload=None):
    """The session a record belongs to, or None. There is no shared fallback bucket."""
    raw = (payload or {}).get('session_id') or os.environ.get('DISPATCH_SESSION_ID') \
        or os.environ.get('CLAUDE_SESSION_ID')
    return safe_sid(raw) if raw else None


def open_regular(path, flags, follow=False):
    """Open without ever blocking on a FIFO or device, and refuse anything but a regular file."""
    flags |= os.O_NONBLOCK | os.O_CLOEXEC
    if not follow:
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, 'not a regular file')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_capped(path, limit, follow=False):
    fd = open_regular(path, os.O_RDONLY, follow)
    try:
        return os.read(fd, limit + 1)[:limit + 1], os.fstat(fd).st_size
    finally:
        os.close(fd)


def ensure_dir():
    d = state_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)  # also an existing directory, whatever its mode or the umask was
    return d


def prune(keep):
    """Drop session files past the age limit and the oldest beyond the count limit."""
    d = state_dir()
    sessions = {}
    for entry in os.scandir(d):
        for suffix in ('.jsonl', '.sum.json'):
            if entry.name.endswith(suffix):
                stem = entry.name[:-len(suffix)]
                try:
                    mtime = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                sessions[stem] = max(sessions.get(stem, 0), mtime)
    sessions.pop(keep, None)
    now = time.time()
    ordered = sorted(sessions, key=sessions.get, reverse=True)
    doomed = [s for s in ordered if now - sessions[s] > MAX_AGE]
    doomed += [s for s in ordered[MAX_SESSIONS - 1:] if s not in doomed]
    for stem in doomed:
        for suffix in ('.jsonl', '.sum.json'):
            try:
                os.unlink(d / (stem + suffix))
            except OSError:
                pass


def new_summary():
    return {'v': 1, 'seq': 0, 'edits': 0, 'last_edit': -1, 'last_verify': -1, 'context': False,
            'missing': 0, 'missing_ext': [], 'known': [], 'known_full': False,
            'warned': -1, 'truncated': False}


def parse_summary(raw):
    try:
        data = json.loads(raw)
    except ValueError:
        return new_summary()
    if not isinstance(data, dict) or data.get('v') != 1:
        return new_summary()
    return dict(new_summary(), **data)


def peek(sid):
    """Lock-free read of a session summary. Missing or unusable means empty."""
    try:
        raw, size = read_capped(state_dir() / f'{sid}.sum.json', MAX_SUMMARY)
    except OSError:
        return new_summary()
    return parse_summary(raw) if size <= MAX_SUMMARY else new_summary()


class Session:
    """Locked read-modify-write of one session's summary plus ledger appends."""

    def __init__(self, sid):
        self.sid = sid
        self.dirty = False

    def __enter__(self):
        d = ensure_dir()
        path = d / f'{self.sid}.sum.json'
        fresh = not os.path.lexists(path)
        self.fd = open_regular(path, os.O_RDWR | os.O_CREAT)
        try:
            os.fchmod(self.fd, 0o600)
            for _ in range(20):
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    time.sleep(0.01)
            else:
                raise OSError(errno.EAGAIN, 'summary busy')
            raw = os.read(self.fd, MAX_SUMMARY + 1)
            self.s = parse_summary(raw) if len(raw) <= MAX_SUMMARY else new_summary()
            if fresh:
                prune(self.sid)
        except BaseException:
            os.close(self.fd)
            raise
        return self

    def __exit__(self, *exc):
        try:
            if self.dirty and exc[0] is None:
                os.ftruncate(self.fd, 0)
                os.pwrite(self.fd, json.dumps(self.s, sort_keys=True).encode(), 0)
        finally:
            os.close(self.fd)
        return False

    def log(self, row):
        """Append one redacted row to the ledger (capped) and advance the sequence."""
        s = self.s
        s['seq'] += 1
        self.dirty = True
        if s['truncated']:
            return s['seq']
        fd = open_regular(state_dir() / f'{self.sid}.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        try:
            os.fchmod(fd, 0o600)
            if os.fstat(fd).st_size >= MAX_LEDGER:
                s['truncated'] = True
                row = {'kind': 'truncated'}
            row = dict(row, seq=s['seq'], ts=int(time.time()))
            os.write(fd, (json.dumps(row, sort_keys=True) + '\n').encode())
        finally:
            os.close(fd)
        return s['seq']

    def know(self, key):
        known = self.s['known']
        if key in known:
            return
        if len(known) >= MAX_KNOWN:
            self.s['known_full'] = True
        else:
            known.append(key)
        self.dirty = True


def norm(path):
    try:
        return os.path.realpath(path)
    except (TypeError, ValueError):
        return ''


def valid_context(path):
    """A decision context is usable when it is JSON with `reasons` and a nonempty `rationale`.
    Only a regular file is read, and only up to a small cap, so a FIFO cannot hang the hook."""
    if not path:
        return False
    try:
        raw, size = read_capped(path, MAX_CONTEXT, follow=True)
        if size > MAX_CONTEXT:
            return False
        data = json.loads(raw)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and isinstance(data.get('reasons'), list) \
        and isinstance(data.get('rationale'), str) and bool(data['rationale'].strip())


def is_code(path):
    return Path(path).suffix.lower() not in DOC_SUFFIXES


HELP_FLAGS = {'-h', '-help', '--help', '--version', '-V'}
PASSTHROUGH_HEADS = {'cargo'} | PACKAGE_RUNNERS  # their args after `--` go on to the tool they run
BOOLEAN_SHORT = set('qvxls')  # pytest-style short flags that take no value (for combined groups such as -qh)


def info_only(args, flags, passthrough=False, combined=True):
    """True when `args` carry a help/list/collect flag from `flags`. Long flags match
    by exact name, by `=value`, and by abbreviation (`--coll` for `--collect-only`);
    short ones inside a combined group (`-qh`) when only value-less flags precede them.
    Arguments after `--` are paths unless `passthrough` (the tool forwards them)."""
    for token in args:
        if token == '--':
            if passthrough:
                continue
            break
        if token.startswith('--'):
            name = token.split('=', 1)[0]
            if name in flags or (len(name) >= 4 and any(f.startswith(name) for f in flags if f.startswith('--'))):
                return True
        elif len(token) > 1 and token.startswith('-'):
            if token in flags:
                return True
            if combined:
                for ch in token[1:]:
                    if f'-{ch}' in flags:
                        return True
                    if ch not in BOOLEAN_SHORT:
                        break
    return False


def verifies(head, args):
    """False when a bare verifier invocation only prints, lists or rewrites (see NO_VERIFY_*)."""
    if info_only(args, NO_VERIFY_FLAGS.get(head, set())):
        return False
    sub = next((a for a in args if not a.startswith('-')), '')
    if sub in NO_VERIFY_SUBCOMMANDS.get(head, set()):
        return False
    if head == 'ruff' and sub == 'format':
        return '--check' in args or '--diff' in args  # plain format rewrites files
    return True


def verification_kind(cmd):
    """Name the verifier a shell command runs as a command, or None. Text that merely
    mentions a verifier (echo pytest, grep -r ruff) does not count."""
    try:
        lexer = shlex.shlex(cmd[:MAX_COMMAND].replace('\n', ' ; '), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    segments, current = [], []
    for token in tokens:
        if token in SHELL_BREAK:
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    for seg in segments:
        i = 0
        while i < len(seg):
            if ASSIGN.match(seg[i]):
                i += 1
            elif os.path.basename(seg[i]) in WRAPPERS:
                i += 1
                while i < len(seg) and OPTION_ARG.match(seg[i]):
                    i += 1
            else:
                break
        rest = seg[i:]
        if rest and os.path.basename(rest[0]) == 'uv' and rest[1:2] == ['run']:
            rest = rest[2:]
            while rest and rest[0].startswith('-'):
                rest = rest[1:]
        if not rest:
            continue
        head, args = os.path.basename(rest[0]), rest[1:]
        first = args[0] if args else ''
        if head in BARE_VERIFIERS:
            if verifies(head, args):
                return head
            continue
        if info_only(args, HELP_FLAGS, passthrough=head in PASSTHROUGH_HEADS, combined=head != 'go'):
            continue  # help or version output runs nothing, whatever the invocation form
        if head == 'go' and first in ('test', 'vet'):
            return f'go-{first}'
        if head == 'cargo' and first in ('test', 'check', 'clippy'):
            return f'cargo-{first}'
        if head in PACKAGE_RUNNERS:
            sub = args[1:2] if first == 'run' else args[:1]
            if sub and sub[0] in ('test', 'lint', 'check'):
                return f'{head}-{sub[0]}'
        if head == 'make' and first in ('test', 'check', 'lint'):
            return f'make-{first}'
        if re.fullmatch(r'python[\d.]*', head) and first == '-m' and args[1:2] \
                and args[1] in ('pytest', 'py_compile', 'unittest'):
            if args[1] == 'pytest' and not verifies('pytest', args[2:]):
                continue  # python -m pytest --version / --collect-only verifies nothing
            return f'python-{args[1]}'
        if head == 'bash' and first == '-n':
            return 'bash-n'
        if head == 'git' and first == 'diff' and '--check' in args:
            return 'git-diff-check'
    return None


def analyse(s):
    """Missing-evidence findings from a session summary."""
    findings = []
    if s['missing']:
        exts = ', '.join(s['missing_ext']) or 'unknown'
        findings.append({'evidence': 'read-before-edit',
                         'detail': f"{s['missing']} existing file(s) edited with no earlier read ({exts})"})
    if s['edits'] and s['last_verify'] < s['last_edit']:
        findings.append({'evidence': 'verify-after-edit',
                         'detail': f"{s['edits']} code edit(s), none followed by a verification command"})
    if s['edits'] and not s['context']:
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


def read_payload():
    data = sys.stdin.buffer.read(MAX_STDIN + 1)
    if len(data) > MAX_STDIN:
        return None
    try:
        payload = json.loads(data or b'{}')
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def hook(event):
    payload = read_payload()
    sid = session_id(payload) if payload is not None else None
    if not sid:
        return 0
    tool = payload.get('tool_name') or ''
    inp = payload.get('tool_input')
    inp = inp if isinstance(inp, dict) else {}
    if event == 'stop':
        if payload.get('stop_hook_active'):
            return 0
        s = peek(sid)
        findings = [f for f in analyse(s) if f['evidence'] != 'read-before-edit']
        if findings and s['warned'] < s['last_edit']:
            with Session(sid) as ses:
                ses.s['warned'] = ses.s['seq']
                ses.dirty = True
            emit(message(findings))
        return 0
    base = {'tool': tool, 'oodarc_role': TOOL_ROLE.get(tool, 'act' if tool == 'Bash' else 'observe'),
            'decision_context': valid_context(os.environ.get('CLAVAIN_DECISION_CONTEXT'))}
    path = norm(inp.get('file_path') or inp.get('notebook_path') or '')
    key = digest(path) if path else ''
    ext = Path(path).suffix.lower()[:12] if path else ''
    if event == 'pre':
        if tool in EDIT_TOOLS and path and is_code(path) and os.path.exists(path):
            s = peek(sid)
            if key not in s['known'] and not s['known_full']:
                with Session(sid) as ses:
                    ses.log(dict(base, kind='missing', evidence='read-before-edit', p=key, ext=ext))
                    ses.s['missing'] += 1
                    if len(ses.s['missing_ext']) < 5 and ext not in ses.s['missing_ext']:
                        ses.s['missing_ext'].append(ext or 'none')
                emit(f'phase evidence missing (observe mode, not blocking): read-before-edit: {path}')
        return 0
    if event != 'post':
        return 0
    if tool == 'Read' and path:
        with Session(sid) as ses:
            ses.log(dict(base, kind='read', p=key, ext=ext))
            ses.know(key)
    elif tool in EDIT_TOOLS and path:
        code = is_code(path)
        with Session(sid) as ses:
            n = ses.log(dict(base, kind='edit', p=key, ext=ext, code=code))
            ses.know(key)
            if code:
                ses.s['edits'] += 1
                ses.s['last_edit'] = n
            if base['decision_context']:
                ses.s['context'] = True
    elif tool == 'Bash':
        cmd = str(inp.get('command') or '')
        kind = verification_kind(cmd)
        if kind:
            with Session(sid) as ses:
                ses.s['last_verify'] = ses.log(dict(base, kind='verify', cmd_kind=kind, h=digest(cmd)))
                if base['decision_context']:
                    ses.s['context'] = True
    return 0


def check(args):
    sid = safe_sid(args.session) if args.session else session_id()
    s = peek(sid) if sid else new_summary()
    findings = analyse(s)
    role = PHASE_ROLE.get(args.phase or '')
    if args.phase and role is None:
        findings = findings + [{'evidence': 'unknown-phase', 'detail': args.phase}]
    needs = LEG_NEEDS.get(role, [])
    relevant = [f for f in findings if f['evidence'] in needs or f['evidence'] == 'unknown-phase'] \
        if args.phase else findings
    report = {'session': sid, 'mode': mode(), 'rows': s['seq'], 'phase': args.phase,
              'oodarc_role': role, 'missing': relevant}
    if args.json:
        print(json.dumps(report, sort_keys=True))
    elif relevant:
        print(message(relevant), file=sys.stderr)
    return 0


def dispatch(args):
    ok = valid_context(args.context)
    detail = 'ok' if ok else ('missing' if not args.context else 'unusable')
    if not ok:
        print(f'phase evidence missing (observe mode, not blocking): decision-context {detail} '
              f'for dispatch; record JSON reasons and a nonempty rationale', file=sys.stderr)
    sid = session_id()
    if sid:
        with Session(sid) as ses:
            ses.log({'kind': 'dispatch', 'role': (args.role or '')[:64], 'oodarc_role': 'act',
                     'decision_context': ok, 'context_state': detail})
            if ok:
                ses.s['context'] = True
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
    except BaseException:  # observe mode must never break a session, and prints nothing
        return 0


if __name__ == '__main__':
    sys.exit(main())
