#!/usr/bin/env python3
"""Deterministic suppression count and shrink-only baseline; source: bead mk-3czro.

Use only where a linter already runs. This is a comment-looking-line scanner,
not a lexer: markers inside strings may count, and TSX/regex edge cases or
multiline descriptions may be missed. Keep the scanner stable after adoption.
See the gardener skill for limits and integration with existing linters.

Adopt once with --adopt. Check/update using an explicit, independently trusted
--base-ref (the fetched target branch, never the topic branch's own HEAD).
No upward regeneration option exists. Existing malformed comments are baselined
by count, without tracking their position or requiring bulk rewrites.
"""
import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import tokenize

KINDS = ('nolint', 'noqa', 'type: ignore', 'eslint-disable',
         'ts-ignore/ts-expect-error', 'pylint: disable', 'ts-nocheck')
EXTENSIONS = {'.go', '.py', '.pyi', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts'}
PATTERNS = {
    'nolint': r'\bnolint(?::([^\s/]+))?(.*)',
    'noqa': r'\bnoqa(?::\s*([A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*))?(.*)',
    'type: ignore': r'\btype:\s*ignore(?:\[([^\]]+)\])?(.*)',
    'eslint-disable': r'\beslint-disable(?:-next-line|-line)?\s*(.*)',
    'ts-ignore/ts-expect-error': r'@ts-(?:ignore|expect-error)\b\s*(.*)',
    'pylint: disable': r'\bpylint:\s*disable(?:-next)?(?:\s*=\s*([^;#]*))?(.*)',
    'ts-nocheck': r'@ts-nocheck\b(.*)',
}


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True).stdout


def comments(text, suffix):
    """Yield comment-looking portions of lines, intentionally without lexing."""
    for line, content in enumerate(text.splitlines(), 1):
        marker = re.search(r'#|//|/\*|^\s*\*', content)
        if marker:
            yield line, content[marker.start():]


def suppression_matches(comment):
    for kind, pattern in PATTERNS.items():
        match = re.search(pattern, comment.rstrip(' */'), re.IGNORECASE if kind == 'noqa' else 0)
        if match:
            yield kind, match


def has_reason(text):
    reason = (text or '').strip(' #/*:;-')
    return bool(reason) and not any(re.match(pattern, reason) for pattern in PATTERNS.values())


def specific_and_reason(kind, match):
    if kind == 'eslint-disable':
        parts = match[1].split('--', 1)
        return bool(len(parts) == 2 and has_reason(parts[1]) and
                    re.fullmatch(r'[@\w/.-]+(?:[\s,]+[@\w/.-]+)*', parts[0].strip()))
    if kind == 'ts-ignore/ts-expect-error':
        return bool(re.search(r'\bTS\d+\b', match[1]) and
                    has_reason(re.sub(r'\bTS\d+\b', '', match[1])))
    if kind == 'ts-nocheck':
        return False
    rules = match[1] or ''
    if kind == 'nolint':
        valid = re.fullmatch(r'[a-z][a-z0-9-]*(?:,[a-z][a-z0-9-]*)*', rules)
        valid = valid and 'all' not in rules.split(',')
    elif kind == 'type: ignore':
        valid = re.fullmatch(r'[a-z][a-z0-9-]*(?:\s*,\s*[a-z][a-z0-9-]*)*', rules)
    elif kind == 'pylint: disable':
        valid = bool(rules.strip()) and all(rule.strip() not in {'all', 'C', 'R', 'W', 'E', 'F', 'I'} for rule in rules.split(','))
    else:
        valid = bool(rules)
    return bool(valid and has_reason(match[2]))


def scan(root):
    counts = dict.fromkeys(KINDS, 0)
    violations = dict.fromkeys(KINDS, 0)
    findings = []
    for raw in git(root, 'ls-files', '-z').split(b'\0'):
        if not raw:
            continue
        relative = raw.decode('utf-8')
        path = root / relative
        if path.suffix not in EXTENSIONS or path.is_symlink() or not path.is_file():
            continue
        try:
            raw_source = path.read_bytes()
            encoding = tokenize.detect_encoding(io.BytesIO(raw_source).readline)[0] if path.suffix in {'.py', '.pyi'} else 'utf-8'
            text = raw_source.decode(encoding)
        except (OSError, UnicodeError, SyntaxError) as error:
            raise ValueError(f'{relative}: cannot scan source: {error}') from error
        for line, comment in comments(text, path.suffix):
            for kind, match in suppression_matches(comment):
                counts[kind] += 1
                if not specific_and_reason(kind, match):
                    violations[kind] += 1
                    findings.append(f'{relative}:{line}: {kind} needs a specific rule and reason')
    return {'version': 1, 'counts': counts, 'violations': violations}, findings


def validate(data):
    if (not isinstance(data, dict) or data.get('version') != 1
            or set(data.get('counts', {})) != set(KINDS)
            or set(data.get('violations', {})) != set(KINDS)):
        raise ValueError('invalid suppression baseline schema')
    for value in [*data['counts'].values(), *data['violations'].values()]:
        if type(value) is not int or value < 0:
            raise ValueError('baseline counts must be nonnegative integers')
    if any(data['violations'][k] > data['counts'][k] for k in KINDS):
        raise ValueError('violation count exceeds suppression count')
    return data


def increases(new, old):
    return (sum(new['counts'].values()) > sum(old['counts'].values()) or
            any(new['violations'][k] > old['violations'][k] for k in KINDS))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--base-ref', help='trusted target ref, required for check/update')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--adopt', action='store_true')
    modes.add_argument('--update', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not args.adopt and args.base_ref is None:
        parser.error('--base-ref is required for checking and updating')
    args.base_ref = args.base_ref or 'HEAD'
    root = args.root.resolve()
    path = root / '.suppression-baseline.json'
    try:
        has_ref = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', args.base_ref + '^{commit}'], capture_output=True).returncode == 0
        if not has_ref and not (args.base_ref == 'HEAD' and (args.adopt or not path.exists())):
            raise ValueError('comparison ref does not resolve: ' + args.base_ref)
        if has_ref and not args.adopt:
            target = git(root, 'rev-parse', '--verify', args.base_ref + '^{commit}').strip()
            head = git(root, 'rev-parse', '--verify', 'HEAD^{commit}').strip()
            if target == head:
                raise ValueError('comparison ref resolves to the same commit as HEAD; use an independently fetched target ref')
        live, findings = scan(root)
        previous = None
        if has_ref and git(root, 'ls-tree', '--name-only', args.base_ref, '--', path.name).strip():
            previous = validate(json.loads(git(root, 'show', args.base_ref + ':./' + path.name)))
        baseline = validate(json.loads(path.read_text())) if path.exists() else None
        errors = []
        if args.adopt:
            if baseline is not None or previous is not None:
                errors.append('baseline already adopted; use --update to shrink')
        elif baseline is None:
            if previous is not None:
                errors.append('committed baseline was removed')
            errors.extend(findings)
        else:
            # Initial adoption is reviewed with its first PR. Later changes
            # compare with the baseline committed on the trusted target ref.
            if previous is not None and increases(baseline, previous):
                errors.append('baseline increased against ' + args.base_ref)
            if increases(live, baseline):
                errors.append('suppression count or malformed count exceeds baseline')
                errors.extend(findings)
            if not args.update and live != baseline:
                errors.append('baseline must match current counts; run --update to shrink')
        if args.update and baseline is None:
            errors.append('no baseline; use --adopt once')
        if not errors and (args.adopt or args.update):
            path.write_text(json.dumps(live, indent=2, sort_keys=True) + '\n')
        if args.json:
            print(json.dumps({'scan': live, 'findings': findings, 'errors': errors}, indent=2))
        else:
            print(json.dumps(live['counts'], sort_keys=True))
            for error in errors:
                print('ERROR ' + error)
            if not errors:
                for finding in findings:
                    print('BASELINED ' + finding)
                print('suppression check passed')
        return 1 if errors else 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('ERROR ' + str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
